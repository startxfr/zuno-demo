"""WP-157 changes from the live V-checks:

- V12: MaaS's quota 429 is `text/plain` with no Retry-After header, so the
  gateway computes the delay from the policy windows (app/quota_windows.py),
  measured from the first MaaS call it saw for the caller's counter keys
  (Limitador starts a window at its first hit, V7). The WP-148 contract is
  unchanged: HTTP 429, `quota_exceeded` body, Retry-After header.
- V13: with QUOTA_CLOSED_CLASS_MAAS_ONLY on, a `closed` class (stresstest)
  is refused when no MaaS path answers, instead of being served by a direct
  SaaS fallback; an `open` class still falls back.

No network: providers are fakes. Run from this directory:

    python3 tests/test_wp157_v_findings.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from unittest import mock  # noqa: E402

import httpx  # noqa: E402
import openai  # noqa: E402

from app import main as app_main  # noqa: E402
from app import quota_windows  # noqa: E402
import test_wp157_maas_switches as switches  # noqa: E402
from test_wp157_maas_switches import _Env, _post  # noqa: E402

_ON = {"MAAS_QUOTA_429_PASSTHROUGH": "true"}
_WINDOWS = {"standard": {"user": 86400, "group": 86400, "project": 86400}, "stresstest": {"user": 300, "group": 300}}


def _plain_429() -> openai.RateLimitError:
    """What MaaS really answers (V7/V12): text/plain, no Retry-After."""
    request = httpx.Request("POST", "https://maas/zuno-ai-run/qwen/v1/chat/completions")
    response = httpx.Response(
        429, headers={"content-type": "text/plain"}, content=b"Too Many Requests", request=request,
    )
    return openai.RateLimitError("Too Many Requests", response=response, body=None)


class _Clock:
    def __init__(self, now: float = 1_000_000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


def _fresh_clock(now: float = 1_000_000.0):
    tick = _Clock(now)
    return tick, quota_windows.WindowClock(windows=_WINDOWS, clock=tick)


# -- V12: computed Retry-After -------------------------------------------------

def test_generated_windows_file_is_readable() -> None:
    windows = quota_windows.WindowClock().windows
    assert windows.get("standard", {}).get("user") == 86400
    assert windows.get("stresstest", {}).get("user") == 300


def test_retry_after_counts_from_the_first_call_of_the_window() -> None:
    tick, clock = _fresh_clock()
    clock.hit("standard", "alice", "agent_tekos|sales", None)
    tick.now += 3600
    clock.hit("standard", "alice", "agent_tekos|sales", None)  # a later call does not restart it
    assert clock.retry_after("standard", "alice", "agent_tekos|sales", None) == 86400 - 3600


def test_retry_after_takes_the_longest_remaining_window() -> None:
    tick, clock = _fresh_clock()
    clock.hit("standard", None, "agent_tekos|sales", None)  # the group window starts first
    tick.now += 600
    clock.hit("standard", "alice", "agent_tekos|sales", None)  # the user window starts later
    tick.now += 100
    assert clock.retry_after("standard", "alice", "agent_tekos|sales", None) == 86400 - 100


def test_an_expired_window_restarts_at_the_next_call() -> None:
    tick, clock = _fresh_clock()
    clock.hit("stresstest", "alice", "g", None)
    tick.now += 301
    clock.hit("stresstest", "alice", "g", None)
    tick.now += 60
    assert clock.retry_after("stresstest", "alice", "g", None) == 240


def test_unknown_start_falls_back_to_the_full_class_window() -> None:
    _tick, clock = _fresh_clock()
    assert clock.retry_after("stresstest", "bob", "g", None) == 300
    assert clock.retry_after("no-such-class", "bob", "g", None) is None


def test_a_plain_maas_429_gets_a_computed_retry_after() -> None:
    tick, clock = _fresh_clock()
    with mock.patch.object(quota_windows, "clock", clock):
        with _Env({}, env=_ON):
            assert _post().status_code == 200  # first call: the windows start
        tick.now += 1000
        with _Env({"local-maas": _plain_429()}, env=_ON) as env:
            r = _post()
    assert r.status_code == 429, r.text
    assert r.headers.get("retry-after") == str(86400 - 1000)
    body = r.json()
    assert body["error"] == "quota_exceeded" and body["quota_class"] == "standard"
    assert env.built == ["local-maas"], "a MaaS 429 must not fall back"


def test_a_plain_maas_429_on_the_streaming_path_too() -> None:
    _tick, clock = _fresh_clock()
    with mock.patch.object(quota_windows, "clock", clock):
        with _Env({"local-maas": _plain_429()}, env=_ON):
            r = _post(stream=True)
    assert r.status_code == 429, r.text
    # This call itself started the windows, so the whole window remains.
    assert r.headers.get("retry-after") == "86400"


def test_subscription_window_wins_over_the_policy_window() -> None:
    """Live drill 2026-10-24: the 1 h subscription limit tripped and the
    gateway sent 86026 s (the 24 h policy window). With the provider's
    maas_quota_window, the delay is what remains of that 1 h."""
    tick, clock = _fresh_clock()
    cfg = dict(switches._CFGS["local-maas"], maas_quota_window="1h")
    with mock.patch.object(quota_windows, "clock", clock), \
            mock.patch.dict(switches._CFGS, {"local-maas": cfg}):
        with _Env({}, env=_ON):
            assert _post().status_code == 200  # the subscription window starts
        tick.now += 1000
        with _Env({"local-maas": _plain_429()}, env=_ON):
            r = _post()
    assert r.status_code == 429, r.text
    assert r.headers.get("retry-after") == str(3600 - 1000)


def test_subscription_window_unknown_start_is_the_whole_window() -> None:
    _tick, clock = _fresh_clock()
    assert clock.retry_after("standard", "a", "g", None, provider="p", model_window="1h") == 3600


def test_subscription_window_restarts_after_it_expires() -> None:
    tick, clock = _fresh_clock()
    clock.hit_model("p", "1h")
    tick.now += 3700
    clock.hit_model("p", "1h")
    tick.now += 100
    assert clock.retry_after("standard", "a", "g", None, provider="p", model_window="1h") == 3500


def test_maas_quota_window_matches_the_ai_gateway_subscription() -> None:
    """provider-routing.yaml repeats the window of each model's ai-gateway
    MaaSSubscription; the two must not drift."""
    import pathlib
    import yaml

    root = pathlib.Path(__file__).resolve().parents[3]
    routing = yaml.safe_load((root / "platform/ai-gateway/provider-routing.yaml").read_text())
    values = yaml.safe_load((root / "gitops/charts/models/values.yaml").read_text())

    def models(node):
        if isinstance(node, dict):
            if "publishedName" in node:
                yield node
            for child in node.values():
                yield from models(child)
        elif isinstance(node, list):
            for child in node:
                yield from models(child)

    windows = {}
    for model in models(values):
        for sub in model.get("subscriptions") or []:
            if str(sub.get("user", "")).endswith(":ai-gateway"):
                windows[model["publishedName"]] = {r["window"] for r in sub.get("tokenRateLimits") or []}
    checked = 0
    for entry in routing["providers"]:
        if not entry.get("via_maas"):
            continue
        published = entry["endpoint"].rstrip("/").split("/")[-2]
        assert entry.get("maas_quota_window"), f"{entry['name']}: via_maas without maas_quota_window"
        assert windows.get(published) == {entry["maas_quota_window"]}, (
            f"{entry['name']}: maas_quota_window {entry['maas_quota_window']} != "
            f"{published} ai-gateway subscription window(s) {windows.get(published)}"
        )
        checked += 1
    assert checked >= 4


def test_flag_off_records_nothing() -> None:
    _tick, clock = _fresh_clock()
    with mock.patch.object(quota_windows, "clock", clock):
        with _Env({}):
            assert _post().status_code == 200
    assert clock._starts == {} and clock._model_starts == {}


# -- V13: closed class refused without a MaaS path ------------------------------

_MAAS_DOWN = {"local-maas": RuntimeError("Error code: 500")}
_CLOSED_ON = {"QUOTA_FAIL_MODES_ENFORCED": "true", "QUOTA_CLOSED_CLASS_MAAS_ONLY": "true"}


def test_v13_today_stresstest_is_served_by_a_saas_fallback() -> None:
    with _Env(_MAAS_DOWN, env={"QUOTA_FAIL_MODES_ENFORCED": "true"}) as env:
        r = _post(headers={"X-Zuno-Quota-Class": "stresstest"})
    assert r.status_code == 200, r.text
    assert env.built == ["local-maas", "openai"]


def test_closed_class_is_refused_when_no_maas_path_answers() -> None:
    with _Env(_MAAS_DOWN, env=_CLOSED_ON) as env:
        r = _post(headers={"X-Zuno-Quota-Class": "stresstest"})
    assert r.status_code >= 500, r.text
    assert env.built == ["local-maas"], "a candidate outside MaaS served a closed class"


def test_closed_class_is_still_served_through_maas() -> None:
    with _Env({}, env=_CLOSED_ON) as env:
        r = _post(headers={"X-Zuno-Quota-Class": "stresstest"})
    assert r.status_code == 200
    assert env.built == ["local-maas"]


def test_open_class_keeps_its_fallbacks() -> None:
    with _Env(_MAAS_DOWN, env=_CLOSED_ON) as env:
        r = _post()
    assert r.status_code == 200, r.text
    assert env.built == ["local-maas", "local"]


def test_closed_class_switch_defaults_off() -> None:
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("QUOTA_CLOSED_CLASS_MAAS_ONLY", None)
        from app import quota_fail_modes
        assert quota_fail_modes.closed_class_maas_only() is False


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok   {name}")
            except AssertionError as exc:
                failed += 1
                print(f"FAIL {name}: {exc}")
    sys.exit(1 if failed else 0)
