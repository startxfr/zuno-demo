"""WP-190 phase 2: the model-call latency histogram has buckets past 10 s, so a
p95 over local-model calls (11 to 120 s) is not capped at 10000 ms.

Run from this directory:

    python3 tests/test_duration_buckets.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opentelemetry.sdk.metrics import MeterProvider  # noqa: E402
from opentelemetry.sdk.metrics.export import InMemoryMetricReader  # noqa: E402

from app import telemetry  # noqa: E402


def _record(values):
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader], views=telemetry.metric_views())
    hist = provider.get_meter("t").create_histogram("zuno.model_call_duration_ms", unit="ms")
    for v in values:
        hist.record(v, {"client": "unifai"})
    data = reader.get_metrics_data()
    point = data.resource_metrics[0].scope_metrics[0].metrics[0].data.data_points[0]
    return list(point.explicit_bounds), list(point.bucket_counts)


def test_buckets_reach_past_the_provider_timeout() -> None:
    bounds, _ = _record([1.0])
    assert bounds == list(telemetry.MODEL_CALL_DURATION_BUCKETS_MS)
    assert max(bounds) >= 180000


def test_a_two_minute_call_lands_in_a_finite_bucket() -> None:
    bounds, counts = _record([120000.0, 30000.0, 800.0])
    assert counts[-1] == 0, counts  # nothing in +Inf
    assert counts[bounds.index(120000)] == 1
    assert counts[bounds.index(30000)] == 1


def test_other_histograms_keep_the_default() -> None:
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader], views=telemetry.metric_views())
    provider.get_meter("t").create_histogram("something.else", unit="ms").record(1.0)
    data = reader.get_metrics_data()
    names = [m.name for sm in data.resource_metrics[0].scope_metrics for m in sm.metrics]
    assert "something.else" in names


TESTS = [v for k, v in dict(globals()).items() if k.startswith("test_")]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {exc!r}")
        else:
            print(f"PASS {test.__name__}")
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
