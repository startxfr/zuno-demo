#!/usr/bin/env python3
"""Names the exact fields that make an ArgoCD Application OutOfSync.

Motivation (ADR-0523/WP-081, 2026-08-26): `DSCInitialization`'s
`spec.monitoring.traces.storage.retention: 48h` came back from the cluster as
`48h0m0s`, so ArgoCD reported permanent OutOfSync and every `make d1
install/reconcile openshift-ai` timed out on its Synced/Healthy wait. The only
diagnostic the operator got was "no health message reported" - an OutOfSync
resource has no *health* message at all - which cost ~40 minutes of hunting for
a one-character difference. This prints that difference instead.

ArgoCD's own `managed-resources` API is the authority: it returns, per managed
resource, the desired manifest (`targetState`) and the live one after ArgoCD's
normalizers have run (`normalizedLiveState`). Comparing those two is exactly
the comparison ArgoCD itself made when it decided "OutOfSync", so this can
never disagree with the verdict it is explaining.

Desired-as-subset comparison, matching ArgoCD's semantics: fields present live
but absent from git (operator defaults, status, metadata the API server adds)
are NOT drift and are not reported. Only fields git actually declares are
compared.

Auth: the ArgoCD API does not accept OpenShift bearer tokens (verified: 401),
so this logs in with the local admin account from
`Secret/openshift-gitops-cluster`, the same credential `argocd login` uses. The
session is a stateless JWT - no cluster object is created.

Read-only and non-fatal by contract: it is called from
ansible/tasks/diagnose_gitops_app.yml, whose own contract is "strictly
read-only and never fails". Every failure path here (no route, no secret, admin
auth disabled, API unreachable, unparseable payload) prints nothing and exits
0, so it can never turn a diagnostic pass into a new failure. Pass --debug to
see why it came back empty.

Run from anywhere, with `oc` logged in:

    python3 platform/gitops/argocd_drift.py zuno-openshift-ai-d1
    python3 platform/gitops/argocd_drift.py zuno-openshift-ai-d1 --kind DSCInitialization
"""
from __future__ import annotations

import argparse
import base64
import json
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, Iterator, List, Optional, Tuple

ARGOCD_NAMESPACE = "openshift-gitops"
ARGOCD_ROUTE = "openshift-gitops-server"
ARGOCD_SECRET = "openshift-gitops-cluster"  # noqa: S105 - a Secret name, not a credential
HTTP_TIMEOUT = 15

# Values longer than this are truncated in the output: a finding line ends up
# in a terminal summary table, and a drifting field is occasionally a whole
# embedded config blob.
MAX_VALUE_CHARS = 120


def _debug(enabled: bool, message: str) -> None:
    if enabled:
        print(f"argocd_drift: {message}", file=sys.stderr)


def _oc(args: List[str]) -> Optional[str]:
    """Run an `oc` command, returning stdout or None if it failed at all."""
    try:
        done = subprocess.run(
            ["oc", *args], capture_output=True, text=True, timeout=HTTP_TIMEOUT
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout.strip()


def _api_call(url: str, token: Optional[str], payload: Optional[dict]) -> Optional[dict]:
    """GET (or POST when payload is given) the ArgoCD API. None on any failure.

    TLS verification is disabled deliberately: the ArgoCD route serves the
    cluster's own ingress certificate, which is not in the caller's trust store
    on a demo cluster, and this reads diagnostics from an in-cluster service the
    caller already has cluster-admin over.
    """
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT, context=context) as response:
            return json.loads(response.read().decode())
    except (urllib.error.URLError, ValueError, OSError):
        return None


def _login(debug: bool) -> Optional[Tuple[str, str]]:
    """Resolve the ArgoCD route and a session token. None if unavailable."""
    host = _oc(["get", "route", ARGOCD_ROUTE, "-n", ARGOCD_NAMESPACE,
                "-o", "jsonpath={.spec.host}"])
    if not host:
        _debug(debug, f"no route {ARGOCD_ROUTE} in {ARGOCD_NAMESPACE}")
        return None

    encoded = _oc(["get", "secret", ARGOCD_SECRET, "-n", ARGOCD_NAMESPACE,
                   "-o", "jsonpath={.data.admin\\.password}"])
    if not encoded:
        _debug(debug, f"no admin.password in Secret/{ARGOCD_SECRET}")
        return None
    try:
        password = base64.b64decode(encoded).decode()
    except (ValueError, UnicodeDecodeError):
        _debug(debug, "admin.password is not valid base64")
        return None

    base = f"https://{host}"
    session = _api_call(f"{base}/api/v1/session", None,
                        {"username": "admin", "password": password})
    token = (session or {}).get("token")
    if not token:
        _debug(debug, "admin session refused (admin.enabled=false, or wrong password)")
        return None
    return base, token


def _walk(desired: Any, live: Any, path: str = "") -> Iterator[Tuple[str, Any, Any]]:
    """Yield (path, desired, live) for every leaf git declares that differs.

    Desired-as-subset: keys only present in `live` are skipped entirely, which
    is what keeps operator-defaulted fields out of the report.
    """
    if isinstance(desired, dict) and isinstance(live, dict):
        for key, sub_desired in desired.items():
            child = f"{path}.{key}" if path else key
            if key not in live:
                yield child, sub_desired, None
                continue
            yield from _walk(sub_desired, live[key], child)
        return

    if isinstance(desired, list) and isinstance(live, list):
        if len(desired) != len(live):
            yield path, f"<{len(desired)} items>", f"<{len(live)} items>"
            return
        for index, (sub_desired, sub_live) in enumerate(zip(desired, live)):
            yield from _walk(sub_desired, sub_live, f"{path}[{index}]")
        return

    if desired != live:
        yield path, desired, live


def _render(value: Any) -> str:
    if value is None:
        return "<absent>"
    text = value if isinstance(value, str) else json.dumps(value)
    if len(text) > MAX_VALUE_CHARS:
        text = text[:MAX_VALUE_CHARS] + "..."
    return json.dumps(text) if isinstance(value, str) else text


def _out_of_sync(base: str, token: str, application: str) -> Optional[set]:
    """The (kind, name) pairs ArgoCD itself reports as OutOfSync.

    Restricting the diff to these is what keeps the output honest. Without it,
    a resource covered by the Application's `ignoreDifferences` reports a false
    positive: ArgoCD strips ignored fields from `normalizedLiveState`, so a
    subtree present in git looks "absent live" while ArgoCD is - correctly -
    calling the whole app Synced.
    """
    payload = _api_call(f"{base}/api/v1/applications/{application}", token, None)
    if payload is None:
        return None
    resources = ((payload.get("status") or {}).get("resources")) or []
    return {
        (item.get("kind"), item.get("name"))
        for item in resources
        if item.get("status") not in (None, "Synced")
    }


def _drift_lines(items: List[dict], kind_filter: Optional[str],
                 out_of_sync: Optional[set]) -> List[str]:
    lines: List[str] = []
    for item in items:
        kind = item.get("kind", "?")
        name = item.get("name", "?")
        if kind_filter and kind != kind_filter:
            continue
        if out_of_sync is not None and (kind, name) not in out_of_sync:
            continue
        # Both are JSON *strings*; an empty targetState means the resource
        # exists live but not in git (prune candidate), which ArgoCD already
        # reports clearly on its own.
        try:
            desired = json.loads(item.get("targetState") or "null")
            live = json.loads(item.get("normalizedLiveState") or "null")
        except ValueError:
            continue
        if desired is None or live is None:
            continue
        for path, want, got in _walk(desired, live):
            # metadata churn (resourceVersion, managedFields, annotations the
            # API server rewrites) is noise, never the answer.
            if path.startswith("metadata.") and not path.startswith("metadata.name"):
                continue
            lines.append(f"{kind}/{name} {path}: git={_render(want)} live={_render(got)}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print the field-level drift behind an OutOfSync ArgoCD Application."
    )
    parser.add_argument("application", help="Application name, e.g. zuno-openshift-ai-d1")
    parser.add_argument("--kind", help="only report drift for this resource kind")
    parser.add_argument("--max-lines", type=int, default=20,
                        help="cap the number of reported fields (default 20)")
    parser.add_argument("--debug", action="store_true",
                        help="explain empty output on stderr")
    args = parser.parse_args()

    session = _login(args.debug)
    if not session:
        return 0
    base, token = session

    payload = _api_call(
        f"{base}/api/v1/applications/{args.application}/managed-resources", token, None
    )
    if payload is None:
        _debug(args.debug, f"managed-resources unavailable for {args.application}")
        return 0

    out_of_sync = _out_of_sync(base, token, args.application)
    if out_of_sync is not None and not out_of_sync:
        _debug(args.debug, "every managed resource is Synced")
        return 0

    lines = _drift_lines(payload.get("items") or [], args.kind, out_of_sync)
    if not lines:
        _debug(args.debug, "no field-level drift found")
        return 0

    for line in lines[: args.max_lines]:
        print(line)
    if len(lines) > args.max_lines:
        print(f"...and {len(lines) - args.max_lines} more drifting field(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
