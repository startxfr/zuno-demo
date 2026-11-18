"""Judge Argo CD Applications for a demo's status (ADR-0616 clause 9), without trusting a stale status.

An Application's stored status stays Synced/Healthy when nothing reconciles it any more: on 2026-11-15 five rehearsals
passed on demo333 for 14 minutes after the Argo CD instance had been deleted. So before a status counts:
- Argo CD must be running: its application controller StatefulSet exists and is ready, or, where no such StatefulSet
  is found, an ArgoCD custom resource reports its controller running (status.applicationController Running, or
  status.phase Available);
- each Application must have been reconciled recently (status.reconciledAt within `max_age` seconds, 30 minutes by
  default).

    python3 platform/demo/argo_health.py < input.json     # used by ansible/demos/_lib/argo_apps.yml

Input: {"wanted": ["name" | {"name", "sync", "health"}], "applications": [...], "statefulsets": [...],
"argocds": [...], "max_age": 1800, "demo_id": "...", "layer": "status", "now": "<ISO time, tests only>"}.
Output: a JSON list of check rows (platform/testing/day2_report.py Day2Result).
"""
from __future__ import annotations

import datetime
import json
import sys
from typing import List, Optional, Tuple

DEFAULT_MAX_AGE = 1800
NOT_RUNNING = "Argo CD is not running: the Applications' status is stale"


def parse_time(value) -> Optional[datetime.datetime]:
    try:
        moment = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=datetime.timezone.utc)


def controller_alive(statefulsets: list, argocds: list) -> Tuple[bool, str]:
    """(alive, why): the application controller that reconciles the Applications."""
    for sts in statefulsets or []:
        name = (sts.get("metadata") or {}).get("name", "?")
        wanted = int((sts.get("spec") or {}).get("replicas", 1) or 0)
        ready = int((sts.get("status") or {}).get("readyReplicas", 0) or 0)
        if wanted > 0 and ready >= wanted:
            return True, f"{name} {ready}/{wanted} ready"
        return False, f"{name} {ready}/{wanted} ready"
    for instance in argocds or []:
        status = instance.get("status") or {}
        name = (instance.get("metadata") or {}).get("name", "?")
        if status.get("applicationController") == "Running" or status.get("phase") == "Available":
            return True, f"ArgoCD {name} {status.get('applicationController') or status.get('phase')}"
        return False, f"ArgoCD {name} phase {status.get('phase', 'absent')}"
    return False, "no application controller and no ArgoCD instance found"


def age_text(seconds: float) -> str:
    if seconds < 90:
        return f"{int(seconds)} s"
    if seconds < 5400:
        return f"{int(seconds // 60)} min"
    return f"{seconds / 3600:.1f} h"


def judge(data: dict) -> List[dict]:
    demo_id, layer = data.get("demo_id", "demo"), data.get("layer", "status")
    max_age = int(data.get("max_age") or DEFAULT_MAX_AGE)
    now = parse_time(data["now"]) if data.get("now") else datetime.datetime.now(datetime.timezone.utc)
    alive, why = controller_alive(data.get("statefulsets") or [], data.get("argocds") or [])
    by_name = {(a.get("metadata") or {}).get("name"): a for a in data.get("applications") or []}

    def row(check_id: str, passed: bool, detail: str) -> dict:
        return {"agent": demo_id, "layer": layer, "id": check_id, "category": "argo", "passed": bool(passed),
                "detail": detail, "duration_ms": 0}

    rows = [row("argo/application-controller", alive, why if alive else f"{NOT_RUNNING} ({why})")]
    for wanted in data.get("wanted") or []:
        name = wanted.get("name") if isinstance(wanted, dict) else wanted
        want_sync = (wanted.get("sync") if isinstance(wanted, dict) else None) or "Synced"
        want_health = (wanted.get("health") if isinstance(wanted, dict) else None) or "Healthy"
        app = by_name.get(name)
        if app is None:
            rows.append(row(f"argo/{name}", False, "absent/absent"))
            continue
        status = app.get("status") or {}
        sync = (status.get("sync") or {}).get("status", "absent")
        health = (status.get("health") or {}).get("status", "absent")
        state = f"{sync}/{health}"
        if not alive:
            rows.append(row(f"argo/{name}", False, f"{state} (stored), {NOT_RUNNING}"))
            continue
        reconciled = parse_time(status.get("reconciledAt")) if status.get("reconciledAt") else None
        if reconciled is None:
            rows.append(row(f"argo/{name}", False, f"{state}, never reconciled (no status.reconciledAt)"))
            continue
        age = max(0.0, (now - reconciled).total_seconds())
        fresh = age <= max_age
        ok = (want_sync == "any" or sync == want_sync) and (want_health == "any" or health == want_health)
        detail = f"{state}, reconciled {age_text(age)} ago"
        if not fresh:
            detail += f" (stale: over {age_text(max_age)})"
        rows.append(row(f"argo/{name}", ok and fresh, detail))
    return rows


def main() -> int:
    print(json.dumps(judge(json.load(sys.stdin))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
