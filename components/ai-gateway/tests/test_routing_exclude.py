"""ADR-0581 (WP-164 lot 2): forbidden model roles become an `exclude` list that only narrows,
and the generated model-routing policy is mounted with the baked copy as fallback."""

from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
import yaml  # noqa: E402

from app.model_routing_policy import ModelRoutingPolicy  # noqa: E402
from app.routing import RoutingError, RoutingTable  # noqa: E402
from app.routing_watch import RoutingWatcher  # noqa: E402


class _StubTable(RoutingTable):
    def __init__(self, config):
        self._routing_path = "<stub>"
        self._config = config


_PROVIDERS = {
    "providers": [
        {"name": "local", "kind": "local", "eligible_for": ["C1", "C2", "C3"]},
        {"name": "local-gpt-oss", "kind": "local", "eligible_for": ["C1", "C2", "C3"]},
        {"name": "openai", "kind": "saas", "eligible_for": ["C1", "C2"]},
    ]
}


def _names(candidates):
    return [c.name for c in candidates]


def test_exclude_drops_the_names_and_keeps_the_order():
    table = _StubTable(_PROVIDERS)
    assert _names(table.candidates_for("C1", exclude=["local-gpt-oss"])) == ["local", "openai"]


def test_exclude_runs_before_prefer_so_a_preferred_excluded_name_is_not_used():
    table = _StubTable(_PROVIDERS)
    got = table.candidates_for("C1", prefer=["local-gpt-oss", "openai"], exclude=["local-gpt-oss"])
    assert _names(got) == ["openai", "local"]


def test_strict_preference_whose_names_are_all_excluded_fails_closed():
    table = _StubTable(_PROVIDERS)
    with pytest.raises(RoutingError):
        table.candidates_for("C1", prefer=["local-gpt-oss"], strict=True, exclude=["local-gpt-oss"])


def test_excluding_every_eligible_provider_fails_closed():
    table = _StubTable(_PROVIDERS)
    with pytest.raises(RoutingError, match="excluded"):
        table.candidates_for("C3", exclude=["local", "local-gpt-oss"])


def test_exclude_never_resurrects_an_ineligible_provider():
    table = _StubTable(_PROVIDERS)
    assert _names(table.candidates_for("C3", exclude=["openai"])) == ["local", "local-gpt-oss"]


def _write(path: pathlib.Path, doc) -> str:
    path.write_text(yaml.safe_dump(doc))
    return str(path)


def test_policy_loads_an_exclude_only_entry(tmp_path):
    path = _write(tmp_path / "p.yaml", {"preferences": [{"agent": "a", "task": "t", "exclude": ["openai"]}]})
    policy = ModelRoutingPolicy(path, fallback_path=None)
    assert policy.exclude_for("a", "t") == ["openai"]
    assert policy.preference_for("a", "t") is None
    assert policy.exclude_for("a", "other") is None


def test_policy_keeps_prefer_and_exclude_of_one_entry(tmp_path):
    entry = {"agent": "a", "task": "t", "prefer": ["local"], "strict": True, "exclude": ["openai"]}
    policy = ModelRoutingPolicy(_write(tmp_path / "p.yaml", {"preferences": [entry]}), fallback_path=None)
    assert policy.preference_for("a", "t") == ["local"]
    assert policy.strict_for("a", "t") is True
    assert policy.exclude_for("a", "t") == ["openai"]


def test_missing_mounted_file_falls_back_to_the_baked_copy(tmp_path):
    baked = _write(tmp_path / "baked.yaml", {"preferences": [{"agent": "a", "task": "t", "prefer": ["local"]}]})
    policy = ModelRoutingPolicy(str(tmp_path / "mounted.yaml"), fallback_path=baked)
    assert policy.preference_for("a", "t") == ["local"]
    assert policy.path == str(tmp_path / "mounted.yaml")


def test_watcher_switches_from_the_fallback_to_the_mounted_file_when_it_appears(tmp_path):
    baked = _write(tmp_path / "baked.yaml", {"preferences": [{"agent": "a", "task": "t", "prefer": ["local"]}]})
    mounted = tmp_path / "mounted.yaml"
    policy = ModelRoutingPolicy(str(mounted), fallback_path=baked)
    watcher = RoutingWatcher({policy.path: policy.reload})
    _write(mounted, {"preferences": [{"agent": "a", "task": "t", "prefer": ["openai"], "exclude": ["local"]}]})
    assert watcher.check_once() == [str(mounted)]
    assert policy.preference_for("a", "t") == ["openai"]
    assert policy.exclude_for("a", "t") == ["local"]
