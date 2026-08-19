"""Tests for local-model cost estimation in app/telemetry.py.

Local providers ("local", "local-gpt-oss") have no per-token meter - they
are priced per-second of call duration via _COST_PER_SECOND_LOCAL,
apportioned from this cluster's actual GPU node economics (ADR-0351: the
shared g7e.4xlarge MIG host vs. the dedicated g7e.2xlarge host for
local-gpt-oss). Unlike remote/SaaS cost, local cost is billed whether the
call succeeded or errored, since GPU time is consumed either way.

Run from this directory:

    python3 tests/test_local_cost_estimation.py
"""
from __future__ import annotations

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import telemetry  # noqa: E402

_ONE_HOUR_MS = 3_600_000.0


# --- _estimate_cost_usd unit tests --------------------------------------


def test_local_cost_ignores_token_counts() -> None:
    cost_low = telemetry._estimate_cost_usd("local", 0, 0, latency_ms=1000.0)
    cost_high = telemetry._estimate_cost_usd("local", 999_999, 999_999, latency_ms=1000.0)
    assert cost_low == cost_high
    assert cost_low == telemetry._COST_PER_SECOND_LOCAL["local"] * 1.0


def test_local_qwen_rate_is_half_the_shared_node_rate() -> None:
    cost = telemetry._estimate_cost_usd("local", 0, 0, latency_ms=_ONE_HOUR_MS)
    assert abs(cost - 2.00) < 1e-9


def test_local_gpt_oss_rate_is_the_full_dedicated_node_rate() -> None:
    cost = telemetry._estimate_cost_usd("local-gpt-oss", 0, 0, latency_ms=_ONE_HOUR_MS)
    assert abs(cost - 3.36) < 1e-9
    assert telemetry._COST_PER_SECOND_LOCAL["local-gpt-oss"] != telemetry._COST_PER_SECOND_LOCAL["local"]


def test_remote_cost_still_token_based_ignores_latency() -> None:
    cost_short = telemetry._estimate_cost_usd("openai", 1000, 1000, latency_ms=1.0)
    cost_long = telemetry._estimate_cost_usd("openai", 1000, 1000, latency_ms=999_999.0)
    expected = sum(telemetry._COST_PER_1K_TOKENS["openai"])
    assert cost_short == cost_long == expected


def test_unknown_provider_still_defaults_to_zero() -> None:
    cost = telemetry._estimate_cost_usd("made-up-provider", 100, 100, latency_ms=5000.0)
    assert cost == 0.0


# --- model_call_span gating integration tests ---------------------------


class _FakeCostCounter:
    def __init__(self):
        self.calls = []

    def add(self, value, attrs):
        self.calls.append((value, attrs))


def _run_span(provider, raise_exc=False, record=None):
    fake = _FakeCostCounter()
    with mock.patch.object(telemetry, "_cost_counter", fake):
        try:
            with telemetry.model_call_span(provider, "test-model", "C1") as call:
                if record is not None:
                    call.record_usage(*record)
                if raise_exc:
                    raise RuntimeError("boom")
        except RuntimeError:
            pass
    return fake.calls


def test_local_success_with_no_token_usage_still_bills_gpu_time() -> None:
    calls = _run_span("local")
    assert len(calls) == 1
    cost, attrs = calls[0]
    assert cost > 0.0
    assert attrs["outcome"] == "success"


def test_local_error_still_bills_gpu_time() -> None:
    calls = _run_span("local", raise_exc=True)
    assert len(calls) == 1
    cost, attrs = calls[0]
    assert cost > 0.0
    assert attrs["outcome"] == "error"


def test_local_gpt_oss_error_also_bills_gpu_time() -> None:
    """The exact case that silently priced at $0 before this fix -
    local-gpt-oss wasn't even a key in the old token-rate table."""
    calls = _run_span("local-gpt-oss", raise_exc=True)
    assert len(calls) == 1
    cost, _attrs = calls[0]
    assert cost > 0.0


def test_remote_error_with_no_token_usage_bills_nothing() -> None:
    calls = _run_span("openai", raise_exc=True)
    assert calls == []


def test_remote_success_with_token_usage_bills_token_rate() -> None:
    calls = _run_span("openai", record=(1000, 1000))
    assert len(calls) == 1
    cost, _attrs = calls[0]
    assert cost == sum(telemetry._COST_PER_1K_TOKENS["openai"])


TESTS = [
    test_local_cost_ignores_token_counts,
    test_local_qwen_rate_is_half_the_shared_node_rate,
    test_local_gpt_oss_rate_is_the_full_dedicated_node_rate,
    test_remote_cost_still_token_based_ignores_latency,
    test_unknown_provider_still_defaults_to_zero,
    test_local_success_with_no_token_usage_still_bills_gpu_time,
    test_local_error_still_bills_gpu_time,
    test_local_gpt_oss_error_also_bills_gpu_time,
    test_remote_error_with_no_token_usage_bills_nothing,
    test_remote_success_with_token_usage_bills_token_rate,
]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
