#!/usr/bin/env python3
"""Health of the OpenShift GitOps operator (ArgoCD's own installer), read-only.

Motivation (demo333, 2026-10-25): an operator upgrade 1.21.4 -> 1.22.0 failed on 2026-10-12
(its InstallPlan could not validate the ArgoCD CRD because the conversion webhook had no
endpoint while the old operator was being replaced). The old operator kept running, so
ArgoCD worked and nothing reported the problem for 13 days: CSV 1.21.4 stayed `Replacing`,
CSV 1.22.0 stayed `Pending`, and a Subscription on the moving `latest` channel with
`Automatic` approval could retry at any moment, in the middle of a demo.

This reads the Subscription, the CSVs, the InstallPlans and the Pods of the operator and of
ArgoCD (one JSON object on stdin) and lists what is not healthy:

- an InstallPlan in phase `Failed`;
- a CSV in phase `Replacing`, `Pending`, `Failed`, `Deleting` or `Unknown` (an upgrade that is
  neither finished nor rolled back);
- a Subscription whose conditions say `ResolutionFailed`, `InstallPlanMissing` or
  `InstallPlanFailed`;
- a Subscription that can upgrade on its own at any time: approval `Automatic` on a moving
  channel (`latest`) - unless `--allow-moving-channel`;
- a pod that is not Ready (Completed pods of finished Jobs and replaced replicas are ignored),
  in `CrashLoopBackOff`, or whose container was terminated within the last 15 minutes.

    {"subscription": {...}, "csvs": [...], "installplans": [...], "pods": [...]} | python3 check_gitops_operator.py

Exit 0 and `{"ok": true}` when nothing is found, 1 with the findings otherwise, 2 for bad input.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from typing import Any, Dict, List, Optional

UNHEALTHY_CSV_PHASES = ("Replacing", "Pending", "Failed", "Deleting", "Unknown")
BAD_SUBSCRIPTION_CONDITIONS = ("ResolutionFailed", "InstallPlanMissing", "InstallPlanFailed")
MOVING_CHANNELS = ("latest",)
RECENT_RESTART_SECONDS = 900


def _parse(ts: Optional[str]) -> Optional[datetime.datetime]:
    if not ts:
        return None
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def check(doc: Dict[str, Any], now: Optional[datetime.datetime] = None, allow_moving_channel: bool = False) -> List[str]:
    now = now or datetime.datetime.now(datetime.timezone.utc)
    findings: List[str] = []
    sub = doc.get("subscription") or {}
    spec = sub.get("spec") or {}
    for cond in (sub.get("status") or {}).get("conditions") or []:
        if cond.get("type") in BAD_SUBSCRIPTION_CONDITIONS and cond.get("status") == "True":
            findings.append(f"Subscription {cond['type']}: {(cond.get('message') or cond.get('reason') or '')[:200]}")
    if not allow_moving_channel and spec.get("installPlanApproval") == "Automatic" and spec.get("channel") in MOVING_CHANNELS:
        findings.append(f"Subscription on the moving channel '{spec['channel']}' with Automatic approval: an upgrade can "
                        f"start at any time (use a version channel and Manual approval)")
    for csv in doc.get("csvs") or []:
        phase = (csv.get("status") or {}).get("phase")
        if phase in UNHEALTHY_CSV_PHASES:
            findings.append(f"CSV {csv['metadata']['name']} is {phase}: an upgrade is stuck "
                            f"({((csv.get('status') or {}).get('message') or '')[:120]})")
    for plan in doc.get("installplans") or []:
        if (plan.get("status") or {}).get("phase") == "Failed":
            cond = next(iter((plan.get("status") or {}).get("conditions") or []), {})
            findings.append(f"InstallPlan {plan['metadata']['name']} Failed: {(cond.get('message') or '')[:200]}")
    for pod in doc.get("pods") or []:
        phase = (pod.get("status") or {}).get("phase")
        if phase == "Succeeded" or (pod.get("metadata") or {}).get("deletionTimestamp"):
            continue
        name = pod["metadata"]["name"]
        for cs in (pod.get("status") or {}).get("containerStatuses") or []:
            waiting = (cs.get("state") or {}).get("waiting") or {}
            terminated = (cs.get("lastState") or {}).get("terminated") or {}
            finished = _parse(terminated.get("finishedAt"))
            if waiting.get("reason") in ("CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull", "CreateContainerError"):
                findings.append(f"Pod {name} ({cs['name']}) is {waiting['reason']}")
            elif phase == "Running" and not cs.get("ready"):
                findings.append(f"Pod {name} ({cs['name']}) is not Ready")
            elif finished and (now - finished).total_seconds() < RECENT_RESTART_SECONDS:
                findings.append(f"Pod {name} ({cs['name']}) was terminated ({terminated.get('reason')}) "
                                f"{int((now - finished).total_seconds())}s ago")
        if phase not in ("Running", "Succeeded") and not (pod.get("status") or {}).get("containerStatuses"):
            findings.append(f"Pod {name} is {phase}")
    return findings


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--allow-moving-channel", action="store_true",
                        help="do not report a Subscription on `latest` with Automatic approval")
    args = parser.parse_args(argv)
    try:
        doc = json.load(sys.stdin)
        findings = check(doc, allow_moving_channel=args.allow_moving_channel)
    except (ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": f"bad input: {exc}"}))
        return 2
    print(json.dumps({"ok": not findings, "findings": findings}, indent=2))
    return 0 if not findings else 1


if __name__ == "__main__":
    sys.exit(main())
