#!/usr/bin/env python3
"""ADR-0538/WP-116 tests for src/mlflow_tracking.py.

Deliberately a separate file from test_mlops.py: that one imports mlops.py
and therefore needs boto3/psycopg/torch-era dependencies, while this module
needs only httpx - so these tests actually run in a bare checkout, which is
the point of the repo's standalone-script convention.

What they lock down: ADR-0538 decision 2 (tracking is best-effort and NEVER
fails a pipeline run) and the two protocol details discovered live against
the operand - the `/mlflow` path prefix and the X-MLFLOW-WORKSPACE header -
either of which a refactor could silently drop, leaving tracking that
returns 404/400 while every run still reports success.

Run from components/mlops:

    python3 tests/test_mlflow_tracking.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import unittest.mock as mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import mlflow_tracking as mt  # noqa: E402


class _Resp:
    content = b"{}"

    def raise_for_status(self):
        return None

    def json(self):
        return {}


def _recording_client(seen):
    class _Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, method, url, headers=None, **kwargs):
            seen["method"], seen["url"], seen["headers"] = method, url, headers
            return _Resp()

    return _Client


def test_disabled_without_a_tracking_uri() -> None:
    """Empty URI is the normal state on a cluster with no mlflow component:
    it must cost nothing, not even a connection attempt."""
    with mock.patch.dict(os.environ, {"MLFLOW_TRACKING_URI": ""}, clear=False):
        with mock.patch.object(mt.httpx, "Client") as client:
            assert mt.log_training(agent="comage", run_id="r1", manifest={}) is None
            mt.log_gate(agent="comage", run_id="r1", result={"overall": "PASS"})
        client.assert_not_called()


def test_never_raises_when_the_server_is_unreachable() -> None:
    """ADR-0538 decision 2: a tracking outage cannot fail a training run."""
    env = {"MLFLOW_TRACKING_URI": "https://x/mlflow", "MLFLOW_WORKSPACE": "zuno-mlops",
           "MLFLOW_TRACKING_TOKEN": "t"}
    with mock.patch.dict(os.environ, env, clear=False):
        with mock.patch.object(mt.httpx, "Client", side_effect=RuntimeError("down")):
            assert mt.log_training(agent="comage", run_id="r1", manifest={}) is None
            mt.log_gate(agent="comage", run_id="r1", result={"overall": "FAIL"})


def test_requests_carry_the_path_prefix_and_workspace_header() -> None:
    seen: dict = {}
    env = {"MLFLOW_TRACKING_URI": "https://mlflow.svc:8443/mlflow",
           "MLFLOW_WORKSPACE": "zuno-mlops", "MLFLOW_TRACKING_TOKEN": "tok"}
    with mock.patch.dict(os.environ, env, clear=False):
        with mock.patch.object(mt.httpx, "Client", _recording_client(seen)):
            mt._call("GET", "experiments/get-by-name", params={"experiment_name": "x"})
    # The /mlflow prefix is load-bearing: without it the server answers 404
    # even with a valid token and a correct workspace (live-verified).
    assert seen["url"] == (
        "https://mlflow.svc:8443/mlflow/api/2.0/mlflow/experiments/get-by-name"
    ), seen["url"]
    assert seen["headers"]["X-MLFLOW-WORKSPACE"] == "zuno-mlops"
    assert seen["headers"]["Authorization"] == "Bearer tok"


def test_a_trailing_slash_in_the_uri_does_not_double_up() -> None:
    seen: dict = {}
    env = {"MLFLOW_TRACKING_URI": "https://mlflow.svc:8443/mlflow/",
           "MLFLOW_WORKSPACE": "zuno-mlops", "MLFLOW_TRACKING_TOKEN": "tok"}
    with mock.patch.dict(os.environ, env, clear=False):
        with mock.patch.object(mt.httpx, "Client", _recording_client(seen)):
            mt._call("POST", "runs/create", json={})
    assert "//api" not in seen["url"], seen["url"]


def test_log_batch_drops_non_numeric_metrics_and_none_params() -> None:
    """train_stats carries whatever the trainer produced; a string in there
    must not make the whole batch 400 and lose the numeric metrics with it."""
    seen: dict = {}
    env = {"MLFLOW_TRACKING_URI": "https://mlflow.svc:8443/mlflow",
           "MLFLOW_WORKSPACE": "zuno-mlops", "MLFLOW_TRACKING_TOKEN": "tok"}
    captured = {}

    class _Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, method, url, headers=None, json=None, **kwargs):
            captured.update(json or {})
            return _Resp()

    with mock.patch.dict(os.environ, env, clear=False):
        with mock.patch.object(mt.httpx, "Client", _Client):
            mt._log_batch("run-1",
                          params={"base_model": "qwen", "lora_r": 8, "missing": None},
                          metrics={"train_loss": 0.42, "note": "n/a", "flag": True})
    assert {p["key"] for p in captured["params"]} == {"base_model", "lora_r"}
    assert [m["key"] for m in captured["metrics"]] == ["train_loss"]


TESTS = [
    test_disabled_without_a_tracking_uri,
    test_never_raises_when_the_server_is_unreachable,
    test_requests_carry_the_path_prefix_and_workspace_header,
    test_a_trailing_slash_in_the_uri_does_not_double_up,
    test_log_batch_drops_non_numeric_metrics_and_none_params,
]


def main() -> int:
    failed = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS {test.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
