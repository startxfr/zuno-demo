#!/usr/bin/env python3
"""The profile-driven stress runner: replayable scenario drivers run at a tunable aggressiveness (WP-305, ADR-0624).

A *driver* replays one demo scenario's real call path over in-cluster HTTP (no `oc`, no kubectl) and returns
`Day2Result` rows (platform/testing/day2_report.py). The runner picks the drivers a *profile* names, then runs each one
for a number of iterations or for a duration, at a concurrency and an optional rate, and prints:

  * the iteration rows of the drivers (one JSON array per line, as the stresstest collector already expects:
    every stdout line matching ^\\[.*\\]$ is a JSON array of rows),
  * one summary row per driver and shard: n, ok, err, 429, 5xx, p50/p95/p99 and the raw latencies a collector needs
    to merge shards (`--summarize` does the merge).

Informational only (ADR-0058): the runner exits 0 whatever the rows say; a failing driver is a row, never a crash.
Exit 2 is a runner error (unknown profile, bad overrides).

A *sampler* driver (`register(..., sampler=True, finish=...)`, WP-309) is a measurement, not a load: it is called every
`interval` seconds, beside the other drivers, from the start of the run to its end (shard 0 only), and its `finish(ctx,
samples)` turns what it collected into the final rows (the saturation signals of a load run: queue depth, cache
pressure, p95, connections). Its samples are not rows; a sampler error is one failing row.

A *budget guard* protects the shared model budgets: a driver stops after `max_consecutive_failures` consecutive
429/5xx answers (or timeouts), after `max_429` rejected calls in all, and the whole run stops once the drivers have
reported `max_tokens` tokens through `ctx.add_tokens()`. A tripped guard is a failing row that says so.

Order of a run (2026-11-21): the drivers run one after the other, except the families a profile lists under
`parallel_families`, whose drivers run together (see run_stages). `duration` is PER DRIVER: every driver it applies to
loops for that long, so a run lasts the sum of the sequential loops plus the longest loop of the parallel group.
`--plan-deadline` prints the Job deadline that follows from it (plan_deadline), for the Ansible plan task.

Environment (all optional except where a driver needs a call):
  STRESS_PROFILE        profile name (profile_<name>.yaml next to this file) or a path; default `smoke`
  STRESS_OVERRIDES      JSON object: iterations, concurrency, duration, rate, ramp, timeout, families, drivers, shards,
                        personas, max_tokens
  STRESS_RUN_ID         run identifier stamped on every request id (st-<run>-<driver>-<n>); default a timestamp
  STRESS_DIR            where driver_*.py and profile_*.yaml live; default this file's directory
  STRESS_SHARDS / JOB_COMPLETION_INDEX   the shard layout of an Indexed Job (set by the Job template)
  STRESS_FLUSH_SECONDS  a checkpoint array of the rows so far is printed this often (default 300), so a soak that hits
                        the Job deadline still leaves its rows behind
  KEYCLOAK_URL, EVAL_CLIENT_ID, EVAL_CLIENT_SECRET, DEMO_PERSONA_PASSWORD   the zuno-stresstest sign-in
  STRESS_PERSONAS       comma list of personas (default test-stress-consultant-01); WP-190 keys a budget by persona, so
                        concurrency N wants N personas
  AI_GATEWAY_URL, MCP_GATEWAY_URL   in-cluster service URLs
  STRESS_LOAD_QUOTA_CLASS   the X-Zuno-Quota-Class of the `load` family (default `loadtest`); empty = no header
  STRESS_QUOTA_CLASS        the class of every other driver that names one (default `stresstest`); empty = no header

    python3 platform/testing/stress_runner.py --list
    python3 platform/testing/stress_runner.py --dry-run --profile standard
    python3 platform/testing/stress_runner.py --summarize rows.json
    python3 platform/testing/stress_runner.py --plan-deadline --profile aggressive --dir evaluations/stress
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import math
import os
import pathlib
import re
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from day2_report import Day2Result  # noqa: E402

STATUS_RE = re.compile(r"status[=_ ](\d{3})")
SUMMARY_LAYER = "stress_summary"
LATENCY_SAMPLE_CAP = 5000

DEFAULTS: Dict[str, Any] = {
    "iterations": 1,
    "concurrency": 1,
    "duration": 0,        # seconds; > 0 switches a driver to a duration loop
    "rate": 0.0,          # iteration starts per second across the driver's workers; 0 = no cap
    "ramp": 0,            # seconds over which the workers start, evenly spread
    "timeout": 120,       # seconds per iteration
    "shards": 1,
    "max_consecutive_failures": 3,
    "max_429": 10,
    "max_tokens": 0,      # 0 = no cap on the tokens the drivers report
}


# -- drivers and the registry ------------------------------------------------------------------------------------


@dataclass
class Driver:
    id: str                      # the demo id the driver replays (ansible/demos/<id>)
    family: str                  # tools, models, experiences, rag, guardrails, quota, mesh, data, gitops, ...
    run: Callable[..., Any]      # (ctx, i) -> list of Day2Result; sync or async
    description: str = ""
    needs: Tuple[str, ...] = ()  # what must be deployed for it to mean anything, shown by --list
    mutating: bool = False       # changes cluster state: skipped unless the profile sets allow_mutating
    sampler: bool = False        # a measurement taken every `interval` seconds beside the load (WP-309), not a load
    interval: float = 15.0       # seconds between two samples of a sampler
    finish: Optional[Callable[..., Any]] = None  # (ctx, samples) -> rows, once, when the run ends (a sampler's report)


REGISTRY: Dict[str, Driver] = {}


def register(id: str, family: str, description: str = "", needs: Iterable[str] = (), mutating: bool = False,
             sampler: bool = False, interval: float = 15.0, finish: Optional[Callable[..., Any]] = None):
    """Decorator for a driver function `run(ctx, i) -> List[Day2Result]` (sync or async). For a sampler, `run` returns
    the sample (any value) and `finish(ctx, samples)` the rows."""

    def wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
        REGISTRY[id] = Driver(id=id, family=family, run=fn, description=description, needs=tuple(needs), mutating=mutating,
                              sampler=sampler, interval=float(interval), finish=finish)
        return fn

    return wrap


# The shared-budget guard (2026-11-19): a driver module may register a BLOCKING probe, `probe(ctx) -> fraction of the shared
# ai-gateway ServiceAccount's budget already spent (0..1), or None when it cannot tell`. Before each driver of the families the
# profile lists under `shared_budget_guard`, run_all calls the probes and skips the driver when one says the spent fraction is
# at or above `max_used`: those drivers ride the budget Open WebUI, Dify, kagent and OpenClaw share.
SHARED_BUDGET_PROBES: List[Callable[[Any], Optional[float]]] = []


class SharedBudgetUnknown(Exception):
    """Raised by a shared-budget probe that cannot tell, with the reason as its message (2026-11-21: the warning row of an
    aggressive campaign said "could not be read" and nothing else, so the cause had to be looked for on the cluster)."""


async def read_shared_budget(ctx: Any) -> Tuple[List[Optional[float]], List[str]]:
    """Calls every probe: (their answers, None = unknown; why each unknown one could not tell)."""
    fractions: List[Optional[float]] = []
    reasons: List[str] = []
    for probe in SHARED_BUDGET_PROBES:
        try:
            fraction = await asyncio.to_thread(probe, ctx)
            if fraction is None:
                reasons.append("the probe returned no value and no reason")
        except SharedBudgetUnknown as exc:
            fraction = None
            reasons.append(str(exc)[:400])
        except Exception as exc:  # noqa: BLE001 - an unreadable counter must not stop the run
            print(f"[stress] shared-budget probe failed: {type(exc).__name__}: {str(exc)[:120]}", file=sys.stderr, flush=True)
            fraction = None
            reasons.append(f"the probe raised {type(exc).__name__}: {str(exc)[:160]}")
        fractions.append(fraction)
    return fractions, reasons


def shared_budget_verdict(profile: Dict[str, Any], family: str, fractions: List[Optional[float]]) -> str:
    """'' when the driver may run, else the reason it is skipped. `fractions` are the probes' answers (None = unknown)."""
    guard = profile.get("shared_budget_guard") or {}
    if family not in (guard.get("families") or []):
        return ""
    limit = float(guard.get("max_used", 0.5))
    known = [f for f in fractions if f is not None]
    if known and max(known) >= limit:
        return f"the shared ai-gateway budget is {max(known):.0%} spent, the guard stops at {limit:.0%}: not draining what the other clients share"
    return ""


# A driver module that cannot be imported (a missing helper in the Job's file set, a typo) must not kill the run: the
# modules that did import still run, and each failure becomes one failing row (main emits them): {module name: exception}.
LOAD_FAILURES: Dict[str, str] = {}


def load_drivers(directory: pathlib.Path) -> List[str]:
    """Import every driver_*.py of `directory` (each registers its drivers on import); returns the file names.
    Drivers import `from stress_runner import register`: when this file runs as a script it is the module
    `__main__`, so it is also aliased as `stress_runner` to keep one registry."""
    if "stress_runner" not in sys.modules and __name__ == "__main__":
        sys.modules["stress_runner"] = sys.modules["__main__"]
    sys.path.insert(0, str(directory))
    loaded = []
    for path in sorted(directory.glob("driver_*.py")):
        known = sys.modules.get(path.stem)
        if known is not None and getattr(known, "__file__", None) == str(path):
            # Already loaded: running the file again would register new function objects under the same ids while every
            # holder of the first module (a test, a patch) keeps the old ones.
            loaded.append(path.name)
            continue
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[path.stem] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:  # noqa: BLE001 - one broken module must not stop the others
            sys.modules.pop(path.stem, None)
            LOAD_FAILURES[path.stem] = f"{type(exc).__name__}: {str(exc)[:200]}"
            print(f"[stress] cannot import {path.name}: {LOAD_FAILURES[path.stem]}", file=sys.stderr, flush=True)
            continue
        LOAD_FAILURES.pop(path.stem, None)
        loaded.append(path.name)
    return loaded


def load_failure_rows() -> List[Day2Result]:
    """One failing row per driver module that could not be imported (driver = the module name)."""
    return [row(module, "stress", "driver-import", "guard", False, f"status=500 cannot import the driver module: {why}")
            for module, why in sorted(LOAD_FAILURES.items())]


def row(driver: str, layer: str, id: str, category: str, passed: bool, detail: str = "", ms: float = 0.0) -> Day2Result:
    return Day2Result(agent=driver, layer=layer, id=id, category=category, passed=passed, detail=detail, duration_ms=round(ms, 1))


# The quota class a driver asks for with the trusted header X-Zuno-Quota-Class (honoured only for the zuno-stresstest
# client). One helper instead of a string per driver (2026-11-21): the `load` family pushes, so it asks for `loadtest`
# (250,000 tokens an hour per user) where it used to ask for `stresstest` (2,000 tokens per 5 minutes per user), a
# budget far too small for a load. Every other driver stays on `stresstest`: the functional drivers spend a few tokens,
# and `quotas` proves the 429 by exhausting that small budget.
QUOTA_HEADER = "X-Zuno-Quota-Class"
LOAD_FAMILY = "load"


def quota_class(env: Dict[str, str], family: str = "") -> str:
    """The class of a driver of `family`: STRESS_LOAD_QUOTA_CLASS (default `loadtest`) for the load family,
    STRESS_QUOTA_CLASS (default `stresstest`) for the others. An empty value means "send no header"."""
    if family == LOAD_FAMILY:
        return (env.get("STRESS_LOAD_QUOTA_CLASS", "loadtest") or "").strip()
    return (env.get("STRESS_QUOTA_CLASS", "stresstest") or "").strip()


def quota_headers(ctx: Any, family: str = "") -> Dict[str, str]:
    """{X-Zuno-Quota-Class: <class>} for a driver of `family`, or {} when the class is empty (the persona's group decides)."""
    cls = quota_class(ctx.env, family)
    return {QUOTA_HEADER: cls} if cls else {}


# -- profiles and the plan ---------------------------------------------------------------------------------------


@dataclass
class Plan:
    driver: Driver
    iterations: int
    concurrency: int
    duration: float
    rate: float
    ramp: float
    timeout: float


def load_profile(name_or_path: str, directory: pathlib.Path) -> Dict[str, Any]:
    import yaml

    path = pathlib.Path(name_or_path)
    if not path.is_file():
        path = directory / f"profile_{name_or_path}.yaml"
    if not path.is_file():
        raise ValueError(f"unknown profile {name_or_path!r} (looked for {path})")
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError(f"profile {path.name} must be a mapping")
    data.setdefault("name", path.stem.replace("profile_", ""))
    return data


def parse_overrides(raw: str) -> Dict[str, Any]:
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise ValueError(f"STRESS_OVERRIDES is not JSON: {exc}")
    if not isinstance(data, dict):
        raise ValueError("STRESS_OVERRIDES must be a JSON object")
    return {k: v for k, v in data.items() if v not in (None, "", [])}


def _as_list(value: Any) -> List[str]:
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return [str(v) for v in (value or [])]


def settings(profile: Dict[str, Any], overrides: Dict[str, Any], driver_id: str = "", family: str = "") -> Dict[str, Any]:
    """The effective knobs of one driver: DEFAULTS < profile.defaults < budget < profile.family_defaults[<family>] <
    profile.drivers[<id>] < overrides."""
    merged = dict(DEFAULTS)
    merged.update(profile.get("defaults") or {})
    merged.update(profile.get("budget") or {})
    merged.update((profile.get("family_defaults") or {}).get(family) or {})
    merged.update((profile.get("drivers") or {}).get(driver_id) or {})
    for key in ("iterations", "concurrency", "duration", "rate", "ramp", "timeout", "shards", "max_tokens"):
        if key in overrides:
            merged[key] = overrides[key]
    return merged


def select_drivers(profile: Dict[str, Any], overrides: Dict[str, Any], registry: Dict[str, Driver]) -> Tuple[List[Driver], List[str]]:
    """The drivers a run covers, and the warnings (unknown ids, skipped mutating drivers)."""
    warnings: List[str] = []
    # Naming drivers on the command line bypasses the profile's family filter (an explicit `families` still applies).
    families = _as_list(overrides.get("families") or ("" if overrides.get("drivers") else profile.get("families")))
    include = _as_list(overrides.get("drivers") or profile.get("include"))
    exclude = _as_list(profile.get("exclude"))
    for wanted in include + exclude:
        if wanted not in registry:
            warnings.append(f"unknown driver {wanted!r}")
    chosen = []
    for d in sorted(registry.values(), key=lambda d: (d.family, d.id)):
        if families and d.family not in families:
            continue
        if include and d.id not in include:
            continue
        if d.id in exclude:
            continue
        if d.mutating and not profile.get("allow_mutating"):
            warnings.append(f"driver {d.id!r} changes cluster state: skipped (profile does not set allow_mutating)")
            continue
        chosen.append(d)
    return chosen, warnings


def shard_split(total: int, index: int, shards: int) -> int:
    """This shard's share of `total` iterations: the remainder goes to the first shards."""
    base, extra = divmod(int(total), max(shards, 1))
    return base + (1 if index < extra else 0)


def build_plan(profile: Dict[str, Any], overrides: Dict[str, Any], registry: Dict[str, Driver],
               shard_index: int = 0, shards: Optional[int] = None) -> Tuple[List[Plan], List[str]]:
    drivers, warnings = select_drivers(profile, overrides, registry)
    plans = []
    for d in drivers:
        s = settings(profile, overrides, d.id, d.family)
        k = int(shards if shards is not None else s["shards"])
        conc = max(1, math.ceil(int(s["concurrency"]) / max(k, 1)))
        plans.append(Plan(
            driver=d,
            iterations=shard_split(s["iterations"], shard_index, k),
            concurrency=conc,
            duration=float(s["duration"]),
            rate=float(s["rate"]) / max(k, 1),
            ramp=float(s["ramp"]),
            timeout=float(s["timeout"]),
        ))
    return plans, warnings


def parallel_families(profile: Dict[str, Any]) -> List[str]:
    """The families whose drivers run together (profile key `parallel_families`, default none)."""
    return _as_list(profile.get("parallel_families"))


def run_stages(plans: List[Plan], profile: Dict[str, Any]) -> List[List[Plan]]:
    """The plans in the order they run, as stages: a stage of one plan is a sequential driver, the stage of several is
    the parallel group. Every plan whose driver family is listed in `parallel_families` joins ONE group (the listed
    families run together, not family by family), placed where its first member stood; the other plans keep their order.
    Without the key every stage holds one plan: the behaviour before 2026-11-21."""
    together = set(parallel_families(profile))
    stages: List[List[Plan]] = []
    group: Optional[List[Plan]] = None
    for plan in plans:
        if plan.driver.family in together:
            if group is None:
                group = []
                stages.append(group)
            group.append(plan)
        else:
            stages.append([plan])
    return stages


DEADLINE_MARGIN = 900  # seconds beside the loops: the pod start (pip install), the sign-ins, the samplers' last read


def plan_deadline(profile: Dict[str, Any], overrides: Dict[str, Any], registry: Dict[str, Driver],
                  margin: int = DEADLINE_MARGIN) -> Dict[str, Any]:
    """The Job deadline a campaign needs, from the profile, the overrides and the drivers they select. Pure.

    `duration` is per driver, so the loops add up: a sequential driver in a duration loop lasts its duration plus one
    timeout (the iterations in flight when the loop ends are allowed to finish), and the parallel group lasts as long as
    its longest member. Before 2026-11-21 the deadline was max(profile deadline, duration + 900) whatever the number of
    drivers: DURATION=3600 on five families gave a Job that could not finish in time.

      no duration loop              the profile's job.deadline_seconds (sized for its iteration counts)
      only duration loops           max(profile deadline, loops + margin)
      loops and iteration drivers   profile deadline + loops (the profile deadline covers the iteration drivers)

    Returns {"deadline", "loops", "sequential_loops", "parallel_loops", "iteration_drivers", "detail"}; samplers do
    not count (they run beside the load)."""
    base = int((profile.get("job") or {}).get("deadline_seconds") or 1800)
    plans, _warnings = build_plan(profile, overrides, registry)
    plans = [p for p in plans if not p.driver.sampler]
    total = 0.0
    sequential = parallel = iteration = 0
    for stage in run_stages(plans, profile):
        looping = [p for p in stage if p.duration > 0]
        iteration += len(stage) - len(looping)
        if not looping:
            continue
        total += max(p.duration + p.timeout for p in looping)
        if len(stage) > 1:
            parallel += len(looping)
        else:
            sequential += 1
    loops = int(math.ceil(total))
    if not loops:
        deadline, how = base, "no duration loop: the profile's deadline"
    elif iteration:
        deadline, how = base + loops, f"profile deadline {base}s for {iteration} iteration driver(s) + {loops}s of loops"
    else:
        deadline, how = max(base, loops + margin), f"max(profile deadline {base}s, {loops}s of loops + {margin}s)"
    return {"deadline": int(deadline), "loops": loops, "sequential_loops": sequential, "parallel_loops": parallel,
            "iteration_drivers": iteration,
            "detail": f"{sequential} sequential loop(s), {parallel} loop(s) in the parallel group: {how}"}


# -- the run context ---------------------------------------------------------------------------------------------


class Ctx:
    """What a driver gets: an HTTP client, in-cluster URLs, persona tokens and the tagging headers."""

    def __init__(self, env: Optional[Dict[str, str]] = None, client: Any = None, run_id: str = "", personas: Optional[List[str]] = None):
        self.env = dict(os.environ if env is None else env)
        self.run_id = run_id or self.env.get("STRESS_RUN_ID") or time.strftime("%Y%m%d%H%M%S")
        self.ai_gateway = self.env.get("AI_GATEWAY_URL", "http://ai-gateway.zuno-ai-run.svc.cluster.local:8080").rstrip("/")
        self.mcp_gateway = self.env.get("MCP_GATEWAY_URL", "http://mcp-gateway.zuno-ai-run.svc.cluster.local:8080").rstrip("/")
        self.keycloak = self.env.get("KEYCLOAK_URL", "").rstrip("/")
        self.personas = personas or _as_list(self.env.get("STRESS_PERSONAS")) or ["test-stress-consultant-01"]  # a profile's pool is passed in
        self._client = client
        self._tokens: Dict[str, Tuple[str, float]] = {}
        self._token_locks: Dict[str, asyncio.Lock] = {}
        self.tokens_used = 0
        self.max_tokens = 0
        self.guard_note = ""

    @property
    def http(self):
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(timeout=120)
        return self._client

    def add_tokens(self, n: Any) -> None:
        try:
            self.tokens_used += int(n)
        except (TypeError, ValueError):
            pass

    @property
    def token_budget_spent(self) -> bool:
        return bool(self.max_tokens) and self.tokens_used >= self.max_tokens

    def request_id(self, driver: str, i: int, step: str = "") -> str:
        return f"st-{self.run_id}-{driver}-{i}{('-' + step) if step else ''}"

    def trace_headers(self, driver: str, i: int, step: str = "") -> Dict[str, str]:
        """Tags the request as stresstest traffic: the request id joins the span, X-Zuno-Traffic is recorded as a span
        attribute by the gateways that read it (WP-306) and ignored by the others."""
        return {"X-Zuno-Request-Id": self.request_id(driver, i, step), "X-Zuno-Traffic": "stresstest"}

    async def token(self, persona: str) -> str:
        """A zuno-stresstest token of `persona` (password grant), cached until 30 s before it expires."""
        cached = self._tokens.get(persona)
        if cached and cached[1] > time.time():
            return cached[0]
        if not self.keycloak:
            raise RuntimeError("KEYCLOAK_URL is not set")
        # One sign-in per persona at a time (2026-11-21): the drivers of a parallel group share the persona pool, and
        # Keycloak's brute-force protection counts concurrent sign-ins of one user (see the blocking sign-ins below).
        async with self._token_locks.setdefault(persona, asyncio.Lock()):
            cached = self._tokens.get(persona)
            if cached and cached[1] > time.time():
                return cached[0]
            r = await self.http.post(
                f"{self.keycloak}/realms/zuno/protocol/openid-connect/token",
                data={"grant_type": "password", "client_id": self.env.get("EVAL_CLIENT_ID", "zuno-stresstest"),
                      "client_secret": self.env.get("EVAL_CLIENT_SECRET", ""), "username": persona,
                      "password": self.env.get("DEMO_PERSONA_PASSWORD", "")})
            if r.status_code != 200:
                raise RuntimeError(f"Keycloak refused the token of {persona}: status={r.status_code}")
            body = r.json()
            self._tokens[persona] = (body["access_token"], time.time() + max(int(body.get("expires_in", 300)) - 30, 30))
            return body["access_token"]

    def for_worker(self, index: int) -> "WorkerCtx":
        return WorkerCtx(self, index)


class WorkerCtx:
    """One worker's view: the shared Ctx plus the persona the worker signs in as."""

    def __init__(self, base: Ctx, index: int):
        self._base = base
        self.worker = index
        self.persona = base.personas[index % len(base.personas)]

    def __getattr__(self, name: str):
        return getattr(self._base, name)

    async def token(self, persona: Optional[str] = None) -> str:
        return await self._base.token(persona or self.persona)


# -- blocking sign-ins shared by the drivers (WP-311 follow-up) ---------------------------------------------------
# Keycloak's brute-force protection counts every failed or concurrent sign-in of ONE user: many drivers and per-agent Jobs
# signing in as the same persona at once get refused for a minute. A driver caches the session it gets, signs in under a lock
# per (persona, client), and retries once after a pause before the row fails.
SIGNIN_ATTEMPTS = 2
SIGNIN_BACKOFF = 8.0  # seconds, plus up to the same again of jitter
_SIGNIN_LOCKS: Dict[Any, threading.Lock] = {}
_SIGNIN_GUARD = threading.Lock()


def signin_lock(key: Any) -> threading.Lock:
    with _SIGNIN_GUARD:
        return _SIGNIN_LOCKS.setdefault(key, threading.Lock())


def retry_signin(fn: Callable[[], Any], attempts: int = SIGNIN_ATTEMPTS, backoff: float = SIGNIN_BACKOFF,
                 sleep: Callable[[float], None] = time.sleep, jitter: Callable[[], float] = lambda: __import__("random").random()) -> Any:
    """Calls the blocking sign-in `fn`; on an exception waits (backoff + jitter) and tries again, up to `attempts`. Blocking."""
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception:  # noqa: BLE001 - the last attempt re-raises, whatever the sign-in raised
            if attempt == attempts:
                raise
            sleep(backoff * (1 + jitter()))


def cached_signin(cache: Dict[Any, Tuple[Any, float]], key: Any, ttl: float, fn: Callable[[], Any],
                  now: Callable[[], float] = time.time, **retry: Any) -> Any:
    """The cached session of `key`, else one sign-in (`fn`, with retry) under the key's lock: concurrent callers of one persona
    wait for that sign-in and reuse it instead of each signing in. Blocking."""
    hit = cache.get(key)
    if hit and hit[1] > now():
        return hit[0]
    with signin_lock(key):
        hit = cache.get(key)
        if hit and hit[1] > now():
            return hit[0]
        value = retry_signin(fn, **retry)
        cache[key] = (value, now() + ttl)
        return value


# -- the budget guard --------------------------------------------------------------------------------------------


def row_status(r: Day2Result) -> Optional[int]:
    m = STATUS_RE.search(r.detail or "")
    return int(m.group(1)) if m else None


class Guard:
    """Stops a driver that keeps getting 429/5xx/timeouts, so a smoke run cannot drain a shared model budget."""

    def __init__(self, max_consecutive: int, max_429: int):
        self.max_consecutive = max(int(max_consecutive), 1)
        self.max_429 = max(int(max_429), 1)
        self.consecutive = 0
        self.total_429 = 0
        self.reason = ""

    @property
    def tripped(self) -> bool:
        return bool(self.reason)

    def record(self, status: Optional[int], timed_out: bool = False) -> None:
        bad = timed_out or status == 429 or (status is not None and status >= 500)
        if status == 429:
            self.total_429 += 1
        self.consecutive = self.consecutive + 1 if bad else 0
        if not self.reason and self.consecutive >= self.max_consecutive:
            self.reason = f"{self.consecutive} consecutive 429/5xx/timeouts (last status={status if status else 'timeout'})"
        elif not self.reason and self.total_429 >= self.max_429:
            self.reason = f"{self.total_429} calls rejected with 429"


# -- the scheduler -----------------------------------------------------------------------------------------------


@dataclass
class Stats:
    n: int = 0
    ok: int = 0
    err: int = 0
    c429: int = 0
    c5xx: int = 0
    timeouts: int = 0
    lat: List[float] = field(default_factory=list)
    timeline: Dict[int, List[int]] = field(default_factory=dict)  # {wall-clock second // 10 * 10: [iterations, failed]} (WP-311)


class RateLimiter:
    """At most `rate` iteration starts per second across all the workers of a driver."""

    def __init__(self, rate: float):
        self.interval = 1.0 / rate if rate > 0 else 0.0
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        if not self.interval:
            return
        async with self._lock:
            now = time.monotonic()
            start = max(now, self._next)
            self._next = start + self.interval
        if start > now:
            await asyncio.sleep(start - now)


async def _call(driver: Driver, wctx: WorkerCtx, i: int, timeout: float) -> Tuple[List[Day2Result], bool]:
    """One iteration: the driver's rows and whether it timed out. An exception is a failing row."""
    try:
        if asyncio.iscoroutinefunction(driver.run):
            rows = await asyncio.wait_for(driver.run(wctx, i), timeout)
        else:
            rows = await asyncio.wait_for(asyncio.get_running_loop().run_in_executor(None, driver.run, wctx, i), timeout)
        return list(rows or []), False
    except asyncio.TimeoutError:
        return [row(driver.id, "stress", "timeout", "error", False, f"iteration {i} exceeded {timeout:g}s")], True
    except Exception as exc:  # noqa: BLE001 - one broken iteration is a row, never a crash
        return [row(driver.id, "stress", "exception", "error", False, f"{type(exc).__name__}: {str(exc)[:200]}")], False


TIMELINE_BUCKET = 10
TIMELINE_CAP = 2000  # buckets kept per driver and shard (five and a half hours)


async def run_plan(plan: Plan, ctx: Ctx, guard: Guard, sink: Callable[[List[Day2Result]], None],
                   shard_index: int = 0, clock: Callable[[], float] = time.monotonic,
                   wall: Callable[[], float] = time.time) -> Stats:
    """Runs one driver: `iterations` iterations, or a loop until `duration` seconds have passed, on `concurrency`
    workers. Rows go to `sink` as they complete; the returned Stats feed the summary row."""
    stats = Stats()
    limiter = RateLimiter(plan.rate)
    counter = {"next": 0}
    deadline = clock() + plan.duration if plan.duration > 0 else None

    def take() -> Optional[int]:
        if guard.tripped or ctx.token_budget_spent:
            return None
        if deadline is not None:
            if clock() >= deadline:
                return None
        elif counter["next"] >= plan.iterations:
            return None
        counter["next"] += 1
        return counter["next"] - 1

    async def worker(w: int) -> None:
        if plan.ramp > 0 and plan.concurrency > 1:
            await asyncio.sleep(plan.ramp * w / plan.concurrency)
        wctx = ctx.for_worker(shard_index * plan.concurrency + w)
        while True:
            i = take()
            if i is None:
                return
            await limiter.wait()
            started = clock()
            rows, timed_out = await _call(plan.driver, wctx, i, plan.timeout)
            elapsed = (clock() - started) * 1000
            statuses = [s for s in (row_status(r) for r in rows) if s is not None]
            worst = max(statuses) if statuses else None
            if 429 in statuses:
                worst = 429
            ok = bool(rows) and all(r.passed for r in rows)
            stats.n += 1
            stats.ok += 1 if ok else 0
            stats.err += 0 if ok else 1
            stats.c429 += 1 if 429 in statuses else 0
            stats.c5xx += 1 if any(s >= 500 for s in statuses) else 0
            stats.timeouts += 1 if timed_out else 0
            stats.lat.append(elapsed)
            bucket = stats.timeline.setdefault(int(wall() // TIMELINE_BUCKET * TIMELINE_BUCKET), [0, 0])
            bucket[0] += 1
            bucket[1] += 0 if ok else 1
            guard.record(worst, timed_out)
            for r in rows:
                r.id = f"s{shard_index}.i{i}/{r.id}"
                if not r.duration_ms:
                    r.duration_ms = round(elapsed, 1)
            sink(rows)

    await asyncio.gather(*(worker(w) for w in range(plan.concurrency)))
    return stats


def percentile(values: List[float], q: float) -> float:
    """Nearest-rank percentile of `values` (0 for an empty list)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(q / 100.0 * len(ordered)) - 1))]


def summary_row(driver: Driver, stats: Stats, guard: Guard, shard_index: int, shards: int, mode: str) -> Day2Result:
    """One row per driver and shard. The machine-readable stats follow ` | ` so shards can be merged."""
    lat = sorted(stats.lat)
    sample = [round(v) for v in lat[:: max(1, len(lat) // LATENCY_SAMPLE_CAP)]]
    human = (f"{mode}: n={stats.n} ok={stats.ok} err={stats.err} 429={stats.c429} 5xx={stats.c5xx} timeouts={stats.timeouts} "
             f"p50={percentile(lat, 50):.0f}ms p95={percentile(lat, 95):.0f}ms p99={percentile(lat, 99):.0f}ms"
             + (f" - BUDGET GUARD: {guard.reason}" if guard.tripped else ""))
    timeline = [[b, v[0], v[1]] for b, v in sorted(stats.timeline.items())][-TIMELINE_CAP:]
    machine = json.dumps({"n": stats.n, "ok": stats.ok, "err": stats.err, "c429": stats.c429, "c5xx": stats.c5xx,
                          "timeouts": stats.timeouts, "lat": sample, "guard": guard.reason, "tl": timeline, "fam": driver.family}, separators=(",", ":"))
    passed = stats.n > 0 and stats.err == 0 and not guard.tripped
    return row(driver.id, SUMMARY_LAYER, f"summary:s{shard_index}of{shards}", "summary", passed, f"{human} | {machine}")


def merge_summaries(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merges the per-shard summary rows (dicts) of a collected run into one record per driver."""
    merged: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        if r.get("layer") != SUMMARY_LAYER or " | " not in r.get("detail", ""):
            continue
        try:
            s = json.loads(r["detail"].rsplit(" | ", 1)[1])
        except ValueError:
            continue
        m = merged.setdefault(r["agent"], {"driver": r["agent"], "n": 0, "ok": 0, "err": 0, "c429": 0, "c5xx": 0,
                                          "timeouts": 0, "lat": [], "guard": [], "shards": 0, "tl": {}, "family": ""})
        m["family"] = s.get("fam") or m["family"]
        for bucket, n, err in s.get("tl", []):
            cell = m["tl"].setdefault(int(bucket), [0, 0])
            cell[0] += int(n)
            cell[1] += int(err)
        for key in ("n", "ok", "err", "c429", "c5xx", "timeouts"):
            m[key] += int(s.get(key, 0))
        m["lat"] += s.get("lat", [])
        m["shards"] += 1
        if s.get("guard"):
            m["guard"].append(s["guard"])
    for m in merged.values():
        m["p50"], m["p95"], m["p99"] = (percentile(m["lat"], q) for q in (50, 95, 99))
        del m["lat"]
        m["timeline"] = [[b, v[0], v[1]] for b, v in sorted(m.pop("tl").items())]
    return sorted(merged.values(), key=lambda m: m["driver"])


def render_table(merged: List[Dict[str, Any]]) -> str:
    if not merged:
        return "no stress summary rows"
    width = max(6, max(len(m["driver"]) for m in merged))
    lines = [f"{'driver':<{width}}  {'n':>5} {'ok':>5} {'err':>5} {'429':>4} {'5xx':>4} {'p50':>7} {'p95':>7} {'p99':>7}  guard"]
    for m in merged:
        lines.append(f"{m['driver']:<{width}}  {m['n']:>5} {m['ok']:>5} {m['err']:>5} {m['c429']:>4} {m['c5xx']:>4} "
                     f"{m['p50']:>6.0f}ms {m['p95']:>6.0f}ms {m['p99']:>6.0f}ms  {'; '.join(m['guard']) or '-'}")
    return "\n".join(lines)


# -- the run -----------------------------------------------------------------------------------------------------


def _emit(rows: List[Day2Result]) -> None:
    if rows:
        print(json.dumps([asdict(r) for r in rows], separators=(",", ":")), flush=True)


async def _sample_loop(driver: Driver, ctx: Ctx, stop: "asyncio.Event") -> List[Any]:
    """Call a sampler at once, then every `interval` seconds, until the run ends; one last sample is taken at the end.
    Returns the samples; an exception raised by a sample is kept as the sample (the report says so)."""
    wctx = ctx.for_worker(0)
    samples: List[Any] = []

    async def take() -> None:
        try:
            if asyncio.iscoroutinefunction(driver.run):
                samples.append(await driver.run(wctx, len(samples)))
            else:
                samples.append(await asyncio.get_running_loop().run_in_executor(None, driver.run, wctx, len(samples)))
        except Exception as exc:  # noqa: BLE001
            samples.append(exc)

    await take()
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=max(driver.interval, 0.01))
        except asyncio.TimeoutError:
            await take()
    await take()
    return samples


async def _finish_sampler(driver: Driver, ctx: Ctx, samples: List[Any]) -> List[Day2Result]:
    if driver.finish is None:
        return [row(driver.id, "stress", "sampler", "sampler", False, "a sampler needs a finish(ctx, samples) function")]
    try:
        rows = driver.finish(ctx, samples)
        if asyncio.iscoroutine(rows):
            rows = await rows
        return list(rows or [])
    except Exception as exc:  # noqa: BLE001
        return [row(driver.id, "stress", "sampler", "sampler", False, f"{type(exc).__name__}: {str(exc)[:200]}")]


async def run_all(plans: List[Plan], ctx: Ctx, profile: Dict[str, Any], overrides: Dict[str, Any],
                  shard_index: int, shards: int, flush_seconds: float = 300.0,
                  emit: Callable[[List[Day2Result]], None] = _emit) -> List[Day2Result]:
    """Runs the plans and returns every row: one driver after the other (the load is each driver's own concurrency),
    except the drivers of the profile's `parallel_families`, which run together as one stage (run_stages). Each driver has
    its own Guard and its own summary row either way; the token cap is one count for the whole run.
    Rows are also emitted in checkpoints of `flush_seconds` and at the end of each driver."""
    out: List[Day2Result] = []
    pending: List[Day2Result] = []
    last_flush = [time.monotonic()]
    samplers = [p for p in plans if p.driver.sampler] if shard_index == 0 else []  # one sampler per run, not per shard
    plans = [p for p in plans if not p.driver.sampler]
    stop = asyncio.Event()
    sampling = {p.driver.id: ([], asyncio.ensure_future(_sample_loop(p.driver, ctx, stop))) for p in samplers}

    def flush() -> None:
        emit(list(pending))
        pending.clear()
        last_flush[0] = time.monotonic()

    def sink(rows: List[Day2Result]) -> None:
        out.extend(rows)
        pending.extend(rows)
        if time.monotonic() - last_flush[0] >= flush_seconds:
            flush()

    warned_unreadable = [False]
    guarded_families = (profile.get("shared_budget_guard") or {}).get("families") or []

    async def run_one(plan: Plan, s: Dict[str, Any]) -> None:
        guard = Guard(s["max_consecutive_failures"], s["max_429"])
        if ctx.token_budget_spent:
            sink([row(plan.driver.id, "stress", "token-budget", "guard", False,
                      f"skipped: {ctx.tokens_used} tokens already reported, cap is {ctx.max_tokens}")])
            return
        if SHARED_BUDGET_PROBES and plan.driver.family in guarded_families:
            fractions, reasons = await read_shared_budget(ctx)
            if not any(f is not None for f in fractions) and not warned_unreadable[0]:
                warned_unreadable[0] = True  # one row per run, not one per driver
                sink([row(plan.driver.id, "stress", "shared-budget-unknown", "guard", False,
                          "WARNING: the shared ai-gateway budget could not be read: " + "; ".join(reasons)
                          + ". The guard is SKIPPED and the drivers of its families run without it")])
            why = shared_budget_verdict(profile, plan.driver.family, fractions)
            if why:
                sink([row(plan.driver.id, "stress", "shared-budget", "guard", False, f"status=429 skipped: {why}")])
                return
        mode = f"{plan.duration:g}s loop" if plan.duration > 0 else f"{plan.iterations} iteration(s)"
        print(f"[stress] {plan.driver.id} ({plan.driver.family}): {mode}, concurrency {plan.concurrency}", file=sys.stderr, flush=True)
        stats = await run_plan(plan, ctx, guard, sink, shard_index)
        extra = []
        if guard.tripped:
            extra.append(row(plan.driver.id, "stress", "budget-guard", "guard", False, f"stopped: {guard.reason}"))
        if ctx.token_budget_spent:
            extra.append(row(plan.driver.id, "stress", "token-budget", "guard", False,
                             f"stopped: {ctx.tokens_used} tokens reported, cap is {ctx.max_tokens}"))
        summary = summary_row(plan.driver, stats, guard, shard_index, shards, mode)
        sink(extra + [summary])
        flush()

    for stage in run_stages(plans, profile):
        knobs = [settings(profile, overrides, p.driver.id, p.driver.family) for p in stage]
        # The token cap lives on the shared Ctx. A sequential driver sets its own; the drivers of the parallel group
        # share one count, so the group runs under the smallest cap its members declare (0, no cap, when none does).
        caps = [int(k["max_tokens"]) for k in knobs if int(k["max_tokens"]) > 0]
        ctx.max_tokens = min(caps) if caps else 0
        if len(stage) > 1:
            print(f"[stress] parallel group: {', '.join(p.driver.id for p in stage)}", file=sys.stderr, flush=True)
        await asyncio.gather(*(run_one(p, k) for p, k in zip(stage, knobs)))
    stop.set()
    for plan in samplers:
        samples, task = sampling[plan.driver.id]
        try:
            samples.extend(await asyncio.wait_for(task, timeout=max(plan.timeout, 30)))
        except Exception as exc:  # noqa: BLE001 - a stuck sampler is a row, the load rows are already out
            task.cancel()
            samples.append(exc)
        sink(await _finish_sampler(plan.driver, ctx, samples))
        emit(list(pending))
        pending.clear()
    if ctx._client is not None and hasattr(ctx._client, "aclose"):
        await ctx._client.aclose()
    return out


def list_drivers(registry: Dict[str, Driver]) -> str:
    width = max((len(d.id) for d in registry.values()), default=10)
    return "\n".join(f"{d.id:<{width}}  {d.family:<12} {'mutating ' if d.mutating else ''}{d.description}"
                     for d in sorted(registry.values(), key=lambda d: (d.family, d.id))) or "no driver registered"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--profile", default=os.environ.get("STRESS_PROFILE", "smoke"))
    ap.add_argument("--dir", default=os.environ.get("STRESS_DIR", str(HERE)), help="where driver_*.py and profile_*.yaml are")
    ap.add_argument("--list", action="store_true", help="list the registered drivers and exit")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and exit, call nothing")
    ap.add_argument("--summarize", metavar="FILE", help="merge the summary rows of a collected run ('-' = stdin) and print the table")
    ap.add_argument("--plan-deadline", action="store_true",
                    help="print the Job deadline of the profile and STRESS_OVERRIDES as one JSON object and exit, call nothing")
    args = ap.parse_args(argv)

    if args.summarize:
        text = sys.stdin.read() if args.summarize == "-" else pathlib.Path(args.summarize).read_text()
        rows: List[Dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("["):
                rows += json.loads(line)
        if not rows and text.strip().startswith("["):
            rows = json.loads(text)
        print(render_table(merge_summaries(rows)))
        return 0

    directory = pathlib.Path(args.dir)
    load_drivers(directory)
    if args.list:
        print(list_drivers(REGISTRY))
        return 0
    try:
        profile = load_profile(args.profile, directory)
        overrides = parse_overrides(os.environ.get("STRESS_OVERRIDES", ""))
    except ValueError as exc:
        print(f"stress_runner: {exc}", file=sys.stderr)
        return 2
    if args.plan_deadline:
        answer = plan_deadline(profile, overrides, REGISTRY)
        # A driver module that does not import here (a workstation without httpx) hides its drivers from the count: say so,
        # and never go below what the deadline was before this helper (duration + margin).
        answer["unloaded"] = sorted(LOAD_FAILURES)
        if LOAD_FAILURES and "duration" in overrides:
            answer["deadline"] = max(answer["deadline"], int(float(overrides["duration"])) + DEADLINE_MARGIN)
        print(json.dumps(answer))
        return 0
    shards = int(os.environ.get("STRESS_SHARDS") or overrides.get("shards") or settings(profile, overrides)["shards"])
    index = int(os.environ.get("JOB_COMPLETION_INDEX", "0"))
    plans, warnings = build_plan(profile, overrides, REGISTRY, index, shards)
    for w in warnings:
        print(f"[stress] warning: {w}", file=sys.stderr)
    if args.dry_run:
        for p in plans:
            print(f"{p.driver.id:<28} {p.driver.family:<12} iterations={p.iterations} concurrency={p.concurrency} "
                  f"duration={p.duration:g} rate={p.rate:g} ramp={p.ramp:g} timeout={p.timeout:g}")
        together = parallel_families(profile)
        print(f"profile={profile['name']} shard={index}/{shards} drivers={len(plans)}"
              + (f" parallel_families={','.join(together)}" if together else ""))
        return 0
    personas = _as_list(overrides.get("personas")) or _as_list(profile.get("personas"))
    ctx = Ctx(personas=personas or None)
    print(f"[stress] run {ctx.run_id} profile {profile['name']} shard {index}/{shards}: {len(plans)} driver(s)", file=sys.stderr, flush=True)
    if index == 0 and LOAD_FAILURES:  # reported once, not once per shard
        _emit(load_failure_rows())
    asyncio.run(run_all(plans, ctx, profile, overrides, index, shards, float(os.environ.get("STRESS_FLUSH_SECONDS", "300"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
