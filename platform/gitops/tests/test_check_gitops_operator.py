"""platform/gitops/check_gitops_operator.py. Run from the repository root:
    python3 platform/gitops/tests/test_check_gitops_operator.py
"""
from __future__ import annotations

import datetime
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import check_gitops_operator as c  # noqa: E402

NOW = datetime.datetime(2026, 10, 25, 15, 0, tzinfo=datetime.timezone.utc)


def sub(channel="gitops-1.22", approval="Manual", conditions=()):
    return {"spec": {"channel": channel, "installPlanApproval": approval},
            "status": {"conditions": [{"type": t, "status": "True", "message": "m"} for t in conditions]}}


def csv(name, phase):
    return {"metadata": {"name": name}, "status": {"phase": phase}}


def pod(name, ready=True, waiting=None, finished=None, phase="Running"):
    status = {"name": "c", "ready": ready, "state": {"waiting": {"reason": waiting}} if waiting else {"running": {}}}
    if finished:
        status["lastState"] = {"terminated": {"reason": "OOMKilled", "finishedAt": finished}}
    return {"metadata": {"name": name}, "status": {"phase": phase, "containerStatuses": [status]}}


def healthy(**over):
    doc = {"subscription": sub(), "csvs": [csv("g.v1.22.2", "Succeeded")], "installplans": [], "pods": [pod("p")]}
    doc.update(over)
    return doc


class Check(unittest.TestCase):
    def test_a_healthy_operator_reports_nothing(self):
        self.assertEqual(c.check(healthy(), NOW), [])

    def test_the_stuck_upgrade_of_demo333_is_reported(self):
        doc = healthy(
            subscription=sub("latest", "Automatic", ["ResolutionFailed", "InstallPlanMissing"]),
            csvs=[csv("g.v1.21.4", "Replacing"), csv("g.v1.22.0", "Pending")],
            installplans=[{"metadata": {"name": "install-6fs6l"},
                           "status": {"phase": "Failed", "conditions": [{"message": "conversion webhook failed"}]}}])
        findings = c.check(doc, NOW)
        text = "\n".join(findings)
        for expected in ("ResolutionFailed", "InstallPlanMissing", "moving channel", "g.v1.21.4 is Replacing",
                         "g.v1.22.0 is Pending", "install-6fs6l Failed"):
            self.assertIn(expected, text)

    def test_a_moving_channel_is_allowed_on_request_and_manual_approval_is_fine(self):
        self.assertEqual(c.check(healthy(subscription=sub("latest", "Automatic")), NOW, allow_moving_channel=True), [])
        self.assertEqual(c.check(healthy(subscription=sub("latest", "Manual")), NOW), [])

    def test_crashloop_not_ready_and_recent_termination_are_reported(self):
        recent = (NOW - datetime.timedelta(minutes=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        old = (NOW - datetime.timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        findings = c.check(healthy(pods=[pod("a", waiting="CrashLoopBackOff"), pod("b", ready=False),
                                         pod("c", finished=recent), pod("d", finished=old)]), NOW)
        self.assertEqual(len(findings), 3)
        self.assertFalse(any("Pod d" in f for f in findings))

    def test_completed_pods_and_replaced_replicas_are_ignored(self):
        done = pod("job", phase="Succeeded", ready=False)
        gone = pod("old", ready=False)
        gone["metadata"]["deletionTimestamp"] = "2026-10-25T14:00:00Z"
        self.assertEqual(c.check(healthy(pods=[done, gone]), NOW), [])


if __name__ == "__main__":
    unittest.main()
