"""MLflow experiment tracking for the MLOps pipeline (ADR-0538/WP-116).

Mirrors each pipeline run into MLflow so the RHOAI dashboard's Experiments
page can compare runs - the LoRA flow's own record of truth stays the S3
manifests (ADR-0302 decision 3), which is why every function here is
best-effort: **a tracking outage must never fail a training or evaluation
run** (ADR-0538 decision 2). Nothing in this module raises.

Deliberately speaks the REST API directly instead of pulling in the mlflow
client. Three reasons, all discovered live 2026-09-02 while standing the
server up:

  * the server is multi-tenant and needs a workspace header on every
    request (`X-MLFLOW-WORKSPACE`, verified in the operand's own
    mlflow/utils/workspace_utils.py) - the stock client has no first-class
    way to add it short of a request-header-provider plugin;
  * it authenticates with a Kubernetes bearer token, which the pod already
    carries at the standard ServiceAccount path;
  * the API surface used here is five calls, against a heavyweight
    dependency in a GPU training image.

The base URL must include the operand's `/mlflow` path prefix - it is what
the CR reports in `status.address.url`, and requests without it answer 404
even when the workspace header is right.

TLS: the server carries an OpenShift service-serving certificate, so
callers must have run mlops._install_internal_ca() first (it folds the
service CA into certifi). This module never disables verification.

Env contract:
  MLFLOW_TRACKING_URI  base URL incl. /mlflow; EMPTY = tracking disabled
                       (every function becomes a no-op, no warning spam)
  MLFLOW_WORKSPACE     workspace/namespace; defaults to the pod's own
  MLFLOW_TRACKING_TOKEN
                       overrides the ServiceAccount token (backfill/CLI use)
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("mlops.mlflow")

_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
_NAMESPACE_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
_TIMEOUT = float(os.environ.get("MLFLOW_TRACKING_TIMEOUT", "20"))


def tracking_uri() -> str:
    return os.environ.get("MLFLOW_TRACKING_URI", "").strip().rstrip("/")


def _workspace() -> str:
    ws = os.environ.get("MLFLOW_WORKSPACE", "").strip()
    if ws:
        return ws
    try:
        return Path(_NAMESPACE_PATH).read_text().strip()
    except OSError:
        return ""


def _token() -> str:
    tok = os.environ.get("MLFLOW_TRACKING_TOKEN", "").strip()
    if tok:
        return tok
    try:
        return Path(_TOKEN_PATH).read_text().strip()
    except OSError:
        return ""


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "X-MLFLOW-WORKSPACE": _workspace(),
        "Content-Type": "application/json",
    }


def _call(method: str, path: str, **kwargs) -> Optional[Dict[str, Any]]:
    """One REST call. Returns the parsed body, or None on any failure."""
    base = tracking_uri()
    if not base:
        return None
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.request(
                method, f"{base}/api/2.0/mlflow/{path}", headers=_headers(), **kwargs
            )
        resp.raise_for_status()
        return resp.json() if resp.content else {}
    except Exception as exc:  # noqa: BLE001 - tracking is never fatal
        logger.warning("mlflow %s %s failed (run unaffected): %s", method, path, exc)
        return None


def _experiment_id(name: str) -> Optional[str]:
    """Get-or-create, in that order: two pipeline stages of the same run
    both land here, and the second must not fail on RESOURCE_ALREADY_EXISTS."""
    found = _call("GET", "experiments/get-by-name", params={"experiment_name": name})
    if found and found.get("experiment", {}).get("experiment_id"):
        return found["experiment"]["experiment_id"]
    created = _call("POST", "experiments/create", json={"name": name})
    if created and created.get("experiment_id"):
        return created["experiment_id"]
    # A concurrent creator can win the race between the two calls above.
    found = _call("GET", "experiments/get-by-name", params={"experiment_name": name})
    return (found or {}).get("experiment", {}).get("experiment_id")


def _find_run(experiment_id: str, run_id_tag: str) -> Optional[str]:
    body = _call(
        "POST", "runs/search",
        json={"experiment_ids": [experiment_id],
              "filter": f"tags.zuno_run_id = '{run_id_tag}'",
              "max_results": 1},
    )
    runs = (body or {}).get("runs") or []
    return runs[0]["info"]["run_id"] if runs else None


def _log_batch(run_id: str, params: Dict[str, Any], metrics: Dict[str, Any]) -> None:
    now = int(time.time() * 1000)
    payload = {
        "run_id": run_id,
        "params": [{"key": k, "value": str(v)} for k, v in params.items() if v is not None],
        "metrics": [
            {"key": k, "value": float(v), "timestamp": now, "step": 0}
            for k, v in metrics.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        ],
    }
    if payload["params"] or payload["metrics"]:
        _call("POST", "runs/log-batch", json=payload)


def log_training(
    *,
    agent: str,
    run_id: str,
    manifest: Dict[str, Any],
    experiment_prefix: str = "mlops",
    start_time_ms: Optional[int] = None,
    end_run: bool = False,
) -> Optional[str]:
    """Mirror a train_manifest into a new MLflow run. Returns its run id.

    `start_time_ms`/`end_run` exist for the backfill path
    (components/mlops/tooling/backfill_mlflow.py), which recreates a
    historical run rather than opening the live one the evaluate stage
    later appends to.
    """
    if not tracking_uri():
        return None
    experiment_id = _experiment_id(f"{experiment_prefix}-{agent}")
    if not experiment_id:
        return None
    created = _call(
        "POST", "runs/create",
        json={
            "experiment_id": experiment_id,
            "run_name": run_id,
            "start_time": start_time_ms or int(time.time() * 1000),
            # zuno_run_id is the join key the evaluate stage searches on -
            # MLflow's own run_id is server-generated and unknown to the
            # next pipeline stage, which only knows the pipeline run id.
            "tags": [
                {"key": "zuno_run_id", "value": run_id},
                {"key": "zuno_agent", "value": agent},
                {"key": "zuno_classification", "value": str(manifest.get("classification", ""))},
            ],
        },
    )
    mlflow_run_id = (created or {}).get("run", {}).get("info", {}).get("run_id")
    if not mlflow_run_id:
        return None

    stats = manifest.get("train_stats") or {}
    _log_batch(
        mlflow_run_id,
        params={
            "base_model": manifest.get("base_model"),
            "lora_r": manifest.get("lora_r"),
            "lora_alpha": manifest.get("lora_alpha"),
            "lora_dropout": manifest.get("lora_dropout"),
            "cpu_safe": manifest.get("cpu_safe"),
            "example_count": manifest.get("example_count"),
            "adapter_s3_prefix": manifest.get("adapter_s3_prefix"),
        },
        metrics={k: v for k, v in stats.items()},
    )
    if end_run:
        _call("POST", "runs/update",
              json={"run_id": mlflow_run_id, "status": "FINISHED",
                    "end_time": int(time.time() * 1000)})
    logger.info("mlflow: logged training run %s to experiment %s", run_id, experiment_id)
    return mlflow_run_id


def log_gate(
    *,
    agent: str,
    run_id: str,
    result: Dict[str, Any],
    experiment_prefix: str = "mlops",
) -> None:
    """Append the ADR-0107 gate outcome to the run log_training opened.

    Falls back to creating a run if none is found: a gate can be re-run
    against a training run that predates this integration, and a missing
    parent must not lose the gate result.
    """
    if not tracking_uri():
        return
    experiment_id = _experiment_id(f"{experiment_prefix}-{agent}")
    if not experiment_id:
        return
    mlflow_run_id = _find_run(experiment_id, run_id)
    if not mlflow_run_id:
        created = _call(
            "POST", "runs/create",
            json={"experiment_id": experiment_id, "run_name": run_id,
                  "start_time": int(time.time() * 1000),
                  "tags": [{"key": "zuno_run_id", "value": run_id},
                           {"key": "zuno_agent", "value": agent}]},
        )
        mlflow_run_id = (created or {}).get("run", {}).get("info", {}).get("run_id")
        if not mlflow_run_id:
            return

    metrics: Dict[str, Any] = {
        # Booleans as 0/1 so the Experiments page can chart and sort them;
        # the textual verdict stays in params for a human reading one run.
        "gate_passed": 1.0 if result.get("overall") == "PASS" else 0.0,
        "scenario_rate": result.get("scenario_rate"),
        "scenario_threshold": result.get("scenario_threshold"),
        "security_ok": 1.0 if result.get("security_ok") else 0.0,
        "gate_checks_ok": 1.0 if result.get("gate_checks_ok") else 0.0,
    }
    for half in ("register_conformance", "tool_calling_conformance"):
        block = result.get(half)
        if isinstance(block, dict):
            metrics[f"{half}_passed"] = 1.0 if block.get("passed") else 0.0
    if "peft_regression_ok" in result:  # WP-114's fourth gate input
        metrics["peft_regression_ok"] = 1.0 if result["peft_regression_ok"] else 0.0

    _log_batch(
        mlflow_run_id,
        params={"gate_overall": result.get("overall"),
                "classification": result.get("classification")},
        metrics=metrics,
    )
    _call("POST", "runs/update",
          json={"run_id": mlflow_run_id,
                "status": "FINISHED" if result.get("overall") == "PASS" else "FAILED",
                "end_time": int(time.time() * 1000)})
    logger.info("mlflow: logged gate result for run %s", run_id)
