"""ADR-0579 clause 3 (WP-164 lot 3): per-agent guardrail modes can only harden the mode."""

from __future__ import annotations

import os
import pathlib
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml  # noqa: E402

from app import guardrails  # noqa: E402
from app.routing_watch import RoutingWatcher  # noqa: E402


def _modes(tmp_path: pathlib.Path, doc) -> guardrails.AgentModes:
    path = tmp_path / "guardrails-modes.yaml"
    path.write_text(yaml.safe_dump(doc))
    return guardrails.AgentModes(str(path))


def _mode_for(agent_modes, classification, agent="", by_class=None):
    with mock.patch.object(guardrails, "GUARDRAILS_DETECTOR_URL", "http://d"), \
         mock.patch.object(guardrails, "GUARDRAILS_BACKEND", "builtin"), \
         mock.patch.object(guardrails, "MODE_BY_CLASSIFICATION", by_class or {}), \
         mock.patch.object(guardrails, "agent_modes", agent_modes):
        return guardrails.mode_for(classification, agent)


def test_an_agent_mode_hardens_the_class_mode(tmp_path):
    modes = _modes(tmp_path, {"minimum_mode_by_classification": {"C1": "observe"}, "agents": {"tekos": "block"}})
    assert _mode_for(modes, "C1", "tekos", {"C1": "observe"}) == "block"
    assert _mode_for(modes, "C1", "arkos", {"C1": "observe"}) == "observe"


def test_an_agent_mode_never_relaxes_the_class_mode(tmp_path):
    modes = _modes(tmp_path, {"agents": {"tekos": "off"}})
    assert _mode_for(modes, "C3", "tekos", {"C3": "block"}) == "block"
    assert _mode_for(modes, "C2", "tekos", {}) == "observe"  # unlisted class: DEFAULT_MODE


def test_the_corp_minimum_raises_a_laxer_class_mode(tmp_path):
    modes = _modes(tmp_path, {"minimum_mode_by_classification": {"c3": "block"}, "agents": {}})
    assert _mode_for(modes, "C3", "", {"C3": "observe"}) == "block"
    assert _mode_for(modes, "C1", "", {"C1": "off"}) == "off"


def test_an_unconfigured_backend_stays_off_whatever_the_agent(tmp_path):
    modes = _modes(tmp_path, {"agents": {"tekos": "block"}})
    with mock.patch.object(guardrails, "GUARDRAILS_DETECTOR_URL", ""), \
         mock.patch.object(guardrails, "GUARDRAILS_BACKEND", "builtin"), \
         mock.patch.object(guardrails, "agent_modes", modes):
        assert guardrails.mode_for("C1", "tekos") == "off"


def test_unknown_modes_are_ignored_and_a_missing_file_is_empty(tmp_path):
    modes = _modes(tmp_path, {"minimum_mode_by_classification": {"C1": "panic"}, "agents": {"tekos": "loud"}})
    assert modes.minimum == {} and modes.agents == {}
    missing = guardrails.AgentModes(str(tmp_path / "absent.yaml"))
    assert missing.minimum == {} and missing.agents == {}
    assert guardrails.AgentModes("").agents == {}


def test_a_bad_file_keeps_the_loaded_modes_and_the_watcher_reloads_a_good_one(tmp_path):
    modes = _modes(tmp_path, {"agents": {"tekos": "block"}})
    path = pathlib.Path(modes.path)
    path.write_text("agents: [unclosed")
    modes.reload()
    assert modes.agents == {"tekos": "block"}
    watcher = RoutingWatcher({modes.path: modes.reload})
    path.write_text(yaml.safe_dump({"agents": {"tekos": "observe", "arkos": "block"}}))
    assert watcher.check_once() == [modes.path]
    assert modes.agents == {"tekos": "observe", "arkos": "block"}
