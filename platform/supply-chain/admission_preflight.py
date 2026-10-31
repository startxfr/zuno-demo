#!/usr/bin/env python3
"""Ask the cluster's admission webhook what it thinks of UnifAI images before a pin is written (WP-178).

zuno's verifier (`verify_unifai_images.py`) checks signatures offline with cosign. The cluster admits pods with the
Sigstore policy-controller, which has its own, narrower view: it only knows ECDSA transparency-log keys (an image
whose signature sits only in the Ed25519 Rekor v2 log verifies with cosign but not at admission) and it checks the
signature identity, not the attestations. In `enforce` mode that difference would refuse a pod zuno had accepted, in the
middle of a rollout. So the pin scripts run this after the offline verification: for each digest, a server-side dry-run
of a minimal Pod in an opted-in namespace (`zuno-unifai`) is sent through the real webhook, and any admission
warning or refusal about the image stops the pin with the webhook's own words.

    refs = ["quay.io/zuno/unifai-ui@sha256:..."]
    results = preflight(refs)          # [verify_unifai_images.Result, ...]

When the cluster cannot answer (no `oc`, no connection, the namespace is not opted in) it raises `PreflightUnavailable`:
a pin written without the cluster is still correct for zuno's verifier, so the callers print a notice and go on, but
they never report an unverified admission as a pass.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from typing import Callable, List, Optional

import verify_unifai_images as v

NAMESPACE = "zuno-unifai"
OPT_IN_LABEL = "policy.rhtas.com/include"
# What a policy-controller verdict about an image looks like in `oc create --dry-run=server` output.
VERDICT = re.compile(r"failed policy:|signature keyless validation failed|no matching policies|no signatures found|"
                     r"validation failed|denied the request", re.IGNORECASE)
IGNORED = re.compile(r"would violate PodSecurity", re.IGNORECASE)

Runner = Callable[[List[str], Optional[str]], "subprocess.CompletedProcess[str]"]


class PreflightUnavailable(RuntimeError):
    """The cluster cannot say what the admission webhook would do (the pin is not blocked)."""


def _run(args: List[str], stdin: Optional[str] = None) -> "subprocess.CompletedProcess[str]":
    try:
        return subprocess.run(args, input=stdin, capture_output=True, text=True, timeout=120)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise PreflightUnavailable(f"`{args[0]}` is not usable: {exc}") from exc


def pod_manifest(reference: str, namespace: str = NAMESPACE) -> str:
    return json.dumps({"apiVersion": "v1", "kind": "Pod",
                       "metadata": {"name": "zuno-admission-preflight", "namespace": namespace},
                       "spec": {"containers": [{"name": "c", "image": reference, "command": ["sleep", "1"]}]}})


def verdict(output: str) -> List[str]:
    """The admission lines about an image: every line of the dry-run output but the PodSecurity noise."""
    return [line.strip() for line in output.splitlines() if line.strip() and not IGNORED.search(line) and VERDICT.search(line)]


def check_opted_in(runner: Runner = _run, namespace: str = NAMESPACE) -> None:
    done = runner(["oc", "get", "namespace", namespace, "-o", "json"], None)
    if done.returncode != 0:
        raise PreflightUnavailable(f"cannot read namespace {namespace}: {done.stderr.strip()[:160] or 'no answer'}")
    labels = (json.loads(done.stdout).get("metadata") or {}).get("labels") or {}
    if labels.get(OPT_IN_LABEL) != "true":
        raise PreflightUnavailable(f"namespace {namespace} is not opted in to the admission webhook "
                                   f"({OPT_IN_LABEL}=true): the dry-run would prove nothing")


def preflight(references: List[str], runner: Runner = _run, namespace: str = NAMESPACE) -> List[v.Result]:
    check_opted_in(runner, namespace)
    results: List[v.Result] = []
    for reference in references:
        done = runner(["oc", "create", "--dry-run=server", "-f", "-"], pod_manifest(reference, namespace))
        text = (done.stdout or "") + "\n" + (done.stderr or "")
        if done.returncode != 0 and not VERDICT.search(text):
            raise PreflightUnavailable(f"the dry-run of {reference} failed without an admission verdict: {text.strip()[:200]}")
        lines = verdict(text)
        if done.returncode != 0 or lines:
            results.append(v.Result(reference, False, "admission: " + " | ".join(lines)[:400]))
        else:
            results.append(v.Result(reference, True, "admitted by the webhook without a warning"))
    return results


def _stderr(message: str) -> None:
    print(message, file=sys.stderr)


def run_or_skip(references: List[str], enabled: bool = True, runner: Runner = _run,
                log: Callable[[str], None] = _stderr) -> List[v.Result]:
    """For the pin scripts: the results, or [] with a notice when the cluster cannot answer or the check is disabled."""
    if not enabled:
        return []
    try:
        return preflight(references, runner)
    except PreflightUnavailable as exc:
        log(f"admission preflight skipped: {exc}")
        return []
