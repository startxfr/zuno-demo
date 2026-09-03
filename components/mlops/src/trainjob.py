"""Submit the LoRA training step as a Kubeflow TrainJob and wait for it.

ADR-0539 / WP-119. KFP remains the pipeline orchestrator (ADR-0302
decision 1 is unchanged): this module only moves ONE step's compute off
the KFP pod and onto a `trainer.kubeflow.org/v1alpha1 TrainJob`, which is
the shape ADR-0538 decision 4 already named as the conforming way to do
it. The DAG, the ordering, the caching and the ADR-0107 gate all stay
exactly where they were.

The training code itself does not change at all. `mlops.py`'s
`stage_train_lora` becomes a dispatcher: with MLOPS_TRAINJOB_ENABLED=true
it calls `submit_and_wait` here, otherwise it runs the existing in-process
path - which is still reachable as the CLI stage `train-lora-local`, and
which is what the TrainJob pod itself executes.

No new dependency: this talks to the API server with `requests` and the
pod's own ServiceAccount token, the same way `mlops.py` already builds
CA-aware sessions for the Model Registry.

Secrets never travel as literal values. `spec.trainer.env` has no
`envFrom`, so configuration is forwarded by allowlist as plain values,
while credentials are forwarded as `valueFrom.secretKeyRef` references.
Copying a credential's plaintext into the TrainJob spec would put it in
etcd, readable by anyone holding `get trainjobs` in the namespace;
`test_trainjob.py` asserts that this never happens rather than trusting
the convention.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

import requests

_SA_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"
_API = "https://kubernetes.default.svc"
_GROUP = "trainer.kubeflow.org/v1alpha1"

# Configuration forwarded as literal values. Prefix match, so a new
# MLOPS_*/S3_* ConfigMap key reaches the TrainJob pod without editing this
# list - the failure mode that would otherwise bite is a key that reaches
# the KFP step but not the trainer, which looks like a stage behaving
# differently for no visible reason.
_ENV_PREFIXES = ("MLOPS_", "S3_", "PG", "MODEL_REGISTRY_", "MLFLOW_", "ZUNO_")

# Never forwarded as literals, whatever their prefix: these are the
# credential env vars kfp-kubernetes injects into the submitter from
# Secrets. They are re-referenced below instead.
_NEVER_LITERAL = frozenset({
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "PGUSER", "PGPASSWORD",
    "DEMO_PERSONA_PASSWORD",
})

# Deliberately NOT forwarded at all. The acceptance-gate credentials are
# only needed by `evaluate`, and `evaluate` stays a KFP step - a training
# pod has no business holding a persona password.
_GATE_SUFFIX = "_FRONTEND_CLIENT_SECRET"


def _read(name: str) -> str:
    with open(os.path.join(_SA_DIR, name), "r", encoding="utf-8") as handle:
        return handle.read().strip()


def _session() -> "requests.Session":
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {_read('token')}"
    session.verify = os.path.join(_SA_DIR, "ca.crt")
    # The KFP v2 launcher_v2 binary (this module's actual parent process,
    # via emissary) sets REQUESTS_CA_BUNDLE/SSL_CERT_FILE for the user
    # command it execs, pointing at its own merged CA temp file - which on
    # this UBI image is missing the system CAs (it assumes the Debian path
    # /etc/ssl/certs/ca-certificates.crt) AND never includes the
    # kube-apiserver's own signer. `requests` only honors an explicit
    # `session.verify` when neither the call site nor Session.request()'s
    # own verify=None default triggers env lookup first - trust_env=False
    # is required so a launcher-set REQUESTS_CA_BUNDLE cannot silently
    # replace this session's correct SA ca.crt.
    session.trust_env = False
    return session


def _namespace() -> str:
    return os.getenv("MLOPS_TRAINJOB_NAMESPACE") or _read("namespace")


def _url(namespace: str, name: str = "") -> str:
    base = f"{_API}/apis/{_GROUP}/namespaces/{namespace}/trainjobs"
    return f"{base}/{name}" if name else base


def build_env(environ: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """The `spec.trainer.env` list: literals for config, refs for secrets.

    Separated from submission so the secret-hygiene property is unit
    testable without an API server.
    """
    environ = os.environ if environ is None else environ
    env: List[Dict[str, Any]] = []
    for key in sorted(environ):
        if key in _NEVER_LITERAL or key.endswith(_GATE_SUFFIX):
            continue
        if key.startswith(_ENV_PREFIXES):
            env.append({"name": key, "value": environ[key]})

    s3_secret = environ.get("MLOPS_TRAINJOB_S3_SECRET", "")
    pg_secret = environ.get("MLOPS_TRAINJOB_PG_SECRET", "")
    for secret, keys in ((s3_secret, ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")),
                         (pg_secret, ("PGUSER", "PGPASSWORD"))):
        if not secret:
            continue
        for key in keys:
            env.append({
                "name": key,
                "valueFrom": {"secretKeyRef": {"name": secret, "key": key}},
            })
    return env


def build_trainjob(*, run_id: str, agent: str, environ: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """The TrainJob body. Pure, so tests can assert on it directly."""
    environ = os.environ if environ is None else environ
    runtime = environ.get("MLOPS_TRAINJOB_RUNTIME", "mlops-lora")
    body: Dict[str, Any] = {
        "apiVersion": _GROUP,
        "kind": "TrainJob",
        "metadata": {
            # generateName, not name: a KFP retry of the same run_id must
            # not collide with the previous attempt's object. The run_id
            # label is what makes an attempt findable and reusable.
            "generateName": f"lora-{agent}-",
            "labels": {"zuno.io/run-id": run_id, "zuno.io/agent": agent,
                       "app.kubernetes.io/part-of": "mlops"},
        },
        "spec": {
            "runtimeRef": {"apiGroup": "trainer.kubeflow.org",
                           "kind": "TrainingRuntime", "name": runtime},
            "trainer": {
                "command": ["/opt/app-root/src/mlops-run"],
                # The in-process path, run inside the trainer pod. The
                # dispatcher in mlops.py would otherwise recurse.
                "args": ["train-lora-local", "--run-id", run_id],
                "env": build_env(environ),
            },
        },
    }
    return body


def _find_existing(session, namespace: str, run_id: str) -> Optional[Dict[str, Any]]:
    resp = session.get(_url(namespace), params={"labelSelector": f"zuno.io/run-id={run_id}"}, timeout=30)
    resp.raise_for_status()
    items = resp.json().get("items") or []
    # Prefer a finished-successful attempt, so a KFP retry costs seconds
    # rather than re-spending ~2h of burst-node GPU.
    for item in items:
        if _terminal(item) == "complete":
            return item
    return None


def _terminal(trainjob: Dict[str, Any]) -> Optional[str]:
    """Return 'complete', 'failed', or None if still running.

    The controller's exact condition vocabulary is not pinned by the CRD,
    so this matches case-insensitively on the two type names the Kubeflow
    Trainer controller documents, and falls back to jobsStatus counters.
    """
    status = trainjob.get("status") or {}
    for condition in status.get("conditions") or []:
        if str(condition.get("status")) != "True":
            continue
        kind = str(condition.get("type", "")).lower()
        if kind in ("complete", "succeeded"):
            return "complete"
        if kind == "failed":
            return "failed"
    for job in status.get("jobsStatus") or []:
        if int(job.get("failed") or 0) > 0:
            return "failed"
    return None


def submit_and_wait(*, run_id: str, agent: str) -> None:
    """Submit (or adopt) a TrainJob for this run and block until it ends.

    Raises SystemExit on failure or timeout, so the KFP task exits
    non-zero and `.after()` stops `merge-export` - the identical contract
    the in-process path had.
    """
    namespace = _namespace()
    session = _session()
    poll = int(os.getenv("MLOPS_TRAINJOB_POLL_SECONDS", "15"))
    deadline = time.time() + int(os.getenv("MLOPS_TRAINJOB_TIMEOUT_SECONDS", "14400"))

    existing = _find_existing(session, namespace, run_id)
    if existing is not None:
        name = existing["metadata"]["name"]
        print(f"[trainjob] reusing completed TrainJob {name} for run {run_id}", flush=True)
        return

    body = build_trainjob(run_id=run_id, agent=agent)
    resp = session.post(_url(namespace), json=body, timeout=60)
    if resp.status_code >= 400:
        raise SystemExit(f"TrainJob submission rejected ({resp.status_code}): {resp.text}")
    name = resp.json()["metadata"]["name"]
    print(f"[trainjob] submitted {name} (runtime={body['spec']['runtimeRef']['name']}, "
          f"run_id={run_id}, namespace={namespace})", flush=True)

    last = None
    while time.time() < deadline:
        time.sleep(poll)
        get = session.get(_url(namespace, name), timeout=30)
        if get.status_code >= 400:
            print(f"[trainjob] status read failed ({get.status_code}), retrying", flush=True)
            continue
        trainjob = get.json()
        state = _terminal(trainjob)
        summary = json.dumps((trainjob.get("status") or {}).get("jobsStatus") or [], sort_keys=True)
        if summary != last:
            print(f"[trainjob] {name}: {summary}", flush=True)
            last = summary
        if state == "complete":
            print(f"[trainjob] {name} completed", flush=True)
            return
        if state == "failed":
            raise SystemExit(
                f"TrainJob {name} failed. Inspect it with:\n"
                f"  oc get trainjob {name} -n {namespace} -o yaml\n"
                f"  oc logs -n {namespace} -l zuno.io/run-id={run_id} --all-containers --tail=200"
            )

    raise SystemExit(
        f"TrainJob {name} did not finish within MLOPS_TRAINJOB_TIMEOUT_SECONDS. "
        f"It is still running - this step failed, the job did not necessarily. "
        f"Check `oc get trainjob {name} -n {namespace}` before resubmitting."
    )


def enabled() -> bool:
    return os.getenv("MLOPS_TRAINJOB_ENABLED", "").strip().lower() in ("1", "true", "yes")


if __name__ == "__main__":  # pragma: no cover - operator convenience
    submit_and_wait(run_id=sys.argv[1], agent=sys.argv[2])
