#!/usr/bin/env python3
"""WP-156: offline tests for evaluations/demo_presenter_probe.py on the UnifAI
target. No network: a fake target stands in for UnifaiTarget.

    cd evaluations && python3 -m pytest tests/test_demo_presenter_probe.py -q
"""
from __future__ import annotations

import pathlib
import sys

EVAL = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EVAL))

import demo_presenter_probe as probe  # noqa: E402


class FakeTarget:
    def __init__(self, teams, workflows=("comage",), team_id="t-comage", fail_create=()):
        self._teams = list(teams)
        self._workflows = list(workflows)
        self.team_id = team_id
        self._fail_create = set(fail_create)
        self.created = []

    def client(self, persona):
        return object()

    def visible_workflows(self, persona):
        return self._workflows

    def teams(self, persona):
        return [{"team_id": n, "name": n} for n in self._teams]

    def create_team(self, persona, name, groups):
        if name in self._fail_create:
            raise RuntimeError("400 already exists")
        self.created.append((name, tuple(groups)))
        self._teams.append(name)
        return {"team_id": name, "name": name}


def test_all_projects_present_passes_and_says_classification_is_not_checked():
    t = FakeTarget(["agent-comage", "webinar-public", "webinar-confidential", "webinar-restricted"])
    r = probe.probe_auth_and_projects("sale-01", target=t)
    assert r["auth_ok"] and r["missing"] == [] and r["created"] == []
    assert {p["title"] for p in r["projects"]} == set(probe.REQUIRED_PROJECTS)
    assert all(p["classification"] is None for p in r["projects"])
    assert "classification not checked" in r["detail"]


def test_missing_projects_are_reported_not_created_without_the_flag():
    t = FakeTarget(["agent-comage", "webinar-public"])
    r = probe.probe_auth_and_projects("sale-01", target=t)
    assert r["auth_ok"] and r["missing"] == ["webinar-confidential", "webinar-restricted"] and t.created == []


def test_ensure_projects_creates_teams_for_both_business_groups_and_relists():
    t = FakeTarget(["agent-comage", "webinar-public"], fail_create={"webinar-restricted"})
    r = probe.probe_auth_and_projects("sale-01", ensure_projects=True, target=t)
    assert t.created == [("webinar-confidential", ("consultant", "sales"))]
    assert r["created"] == ["webinar-confidential"] and r["missing"] == ["webinar-restricted"]
    assert "create_failures" in r["detail"]


def test_agent_not_visible_is_an_auth_failure_with_the_reason():
    r = probe.probe_auth_and_projects("sale-01", target=FakeTarget([], workflows=[], team_id=""))
    assert not r["auth_ok"] and "not a member of team agent-comage" in r["detail"]


def test_sign_in_error_is_a_failed_row_not_an_exception():
    class Broken(FakeTarget):
        def client(self, persona):
            raise RuntimeError("UnifAI login did not reach Keycloak's kc-form-login")

    r = probe.probe_auth_and_projects("sale-01", target=Broken([]))
    assert not r["auth_ok"] and "kc-form-login" in r["detail"] and r["missing"] == list(probe.REQUIRED_PROJECTS)
