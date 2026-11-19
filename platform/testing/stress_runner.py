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
  STRESS_PERSONAS       comma list of personas (default stress-consultant-01); WP-190 keys a budget by persona, so
                        concurrency N wants N personas
  AI_GATEWAY_URL, MCP_GATEWAY_URL   in-cluster service URLs

    python3 platform/testing/stress_runner.py --list
    python3 platform/testing/stress_runner.py --dry-run --profile standard
    python3 platform/testing/stress_runner.py --summarize rows.json
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


def load_drivers(directory: pathlib.Path) -> List[str]:
    """Import every driver_*.py of `directory` (each registers its drivers on import); returns the file names.
    Drivers import `from stress_runner import register`: when this file runs as a script it is the module
    `__main__`, so it is also aliased as `stress_runner` to keep one registry."""
    if "stress_runner" not in sys.modules and __name__ == "__main__":
        sys.modules["stress_runner"] = sys.modules["__main__"]
    sys.path.insert(0, str(directory))
    loaded = []
    for path in sorted(directory.glob("driver_*.py")):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[path.stem] = module
        spec.loader.exec_module(module)
        loaded.append(path.name)
    return loaded


def row(driver: str, layer: str, id: str, category: str, passed: bool, detail: str = "", ms: float = 0.0) -> Day2Result:
    return Day2Result(agent=driver, layer=layer, id=id, category=category, passed=passed, detail=detail, duration_ms=round(ms, 1))


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


def settings(profile: Dict[str, Any], overrides: Dict[str, Any], driver_id: str = "") -> Dict[str, Any]:
    """The effective knobs of one driver: DEFAULTS < profile.defaults < profile.drivers[<id>] < overrides."""
    merged = dict(DEFAULTS)
    merged.update(profile.get("defaults") or {})
    merged.update(profile.get("budget") or {})
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
        s = settings(profile, overrides, d.id)
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


# -- the run context ---------------------------------------------------------------------------------------------


class Ctx:
    """What a driver gets: an HTTP client, in-cluster URLs, persona tokens and the tagging headers."""

    def __init__(self, env: Optional[Dict[str, str]] = None, client: Any = None, run_id: str = "", personas: Optional[List[str]] = None):
        self.env = dict(os.environ if env is None else env)
        self.run_id = run_id or self.env.get("STRESS_RUN_ID") or time.strftime("%Y%m%d%H%M%S")
        self.ai_gateway = self.env.get("AI_GATEWAY_URL", "http://ai-gateway.zuno-ai-run.svc.cluster.local:8080").rstrip("/")
        self.mcp_gateway = self.env.get("MCP_GATEWAY_URL", "http://mcp-gateway.zuno-ai-run.svc.cluster.local:8080").rstrip("/")
        self.keycloak = self.env.get("KEYCLOAK_URL", "").rstrip("/")
        self.personas = personas or _as_list(self.env.get("STRESS_PERSONAS")) or ["stress-consultant-01"]  # a profile's pool is passed in
        self._client = client
        self._tokens: Dict[str, Tuple[str, float]] = {}
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


async def run_plan(plan: Plan, ctx: Ctx, guard: Guard, sink: Callable[[List[Day2Result]], None],
                   shard_index: int = 0, clock: Callable[[], float] = time.monotonic) -> Stats:
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
    machine = json.dumps({"n": stats.n, "ok": stats.ok, "err": stats.err, "c429": stats.c429, "c5xx": stats.c5xx,
                          "timeouts": stats.timeouts, "lat": sample, "guard": guard.reason}, separators=(",", ":"))
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
                                          "timeouts": 0, "lat": [], "guard": [], "shards": 0})
        for key in ("n", "ok", "err", "c429", "c5xx", "timeouts"):
            m[key] += int(s.get(key, 0))
        m["lat"] += s.get("lat", [])
        m["shards"] += 1
        if s.get("guard"):
            m["guard"].append(s["guard"])
    for m in merged.values():
        m["p50"], m["p95"], m["p99"] = (percentile(m["lat"], q) for q in (50, 95, 99))
        del m["lat"]
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
    """Runs the plans one driver after the other (the load is each driver's own concurrency) and returns every row.
    Rows are also emitted in checkpoints of `flush_seconds` and at the end of each driver."""
    out: List[Day2Result] = []
    pending: List[Day2Result] = []
    last_flush = [time.monotonic()]
    samplers = [p for p in plans if p.driver.sampler] if shard_index == 0 else []  # one sampler per run, not per shard
    plans = [p for p in plans if not p.driver.sampler]
    stop = asyncio.Event()
    sampling = {p.driver.id: ([], asyncio.ensure_future(_sample_loop(p.driver, ctx, stop))) for p in samplers}

    def sink(rows: List[Day2Result]) -> None:
        out.extend(rows)
        pending.extend(rows)
        if time.monotonic() - last_flush[0] >= flush_seconds:
            emit(list(pending))
            pending.clear()
            last_flush[0] = time.monotonic()

    for plan in plans:
        s = settings(profile, overrides, plan.driver.id)
        ctx.max_tokens = int(s["max_tokens"])
        guard = Guard(s["max_consecutive_failures"], s["max_429"])
        if ctx.token_budget_spent:
            sink([row(plan.driver.id, "stress", "token-budget", "guard", False,
                      f"skipped: {ctx.tokens_used} tokens already reported, cap is {ctx.max_tokens}")])
            continue
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
        emit(list(pending))
        pending.clear()
        last_flush[0] = time.monotonic()
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
    shards = int(os.environ.get("STRESS_SHARDS") or overrides.get("shards") or settings(profile, overrides)["shards"])
    index = int(os.environ.get("JOB_COMPLETION_INDEX", "0"))
    plans, warnings = build_plan(profile, overrides, REGISTRY, index, shards)
    for w in warnings:
        print(f"[stress] warning: {w}", file=sys.stderr)
    if args.dry_run:
        for p in plans:
            print(f"{p.driver.id:<28} {p.driver.family:<12} iterations={p.iterations} concurrency={p.concurrency} "
                  f"duration={p.duration:g} rate={p.rate:g} ramp={p.ramp:g} timeout={p.timeout:g}")
        print(f"profile={profile['name']} shard={index}/{shards} drivers={len(plans)}")
        return 0
    personas = _as_list(overrides.get("personas")) or _as_list(profile.get("personas"))
    ctx = Ctx(personas=personas or None)
    print(f"[stress] run {ctx.run_id} profile {profile['name']} shard {index}/{shards}: {len(plans)} driver(s)", file=sys.stderr, flush=True)
    asyncio.run(run_all(plans, ctx, profile, overrides, index, shards, float(os.environ.get("STRESS_FLUSH_SECONDS", "300"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
