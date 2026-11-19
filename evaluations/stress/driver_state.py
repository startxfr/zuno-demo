"""State drivers: the checks of the demos, evaluated from the stress Job over the Kubernetes API (WP-310, ADR-0624).

One driver per demo that has state assertions, named `<demo id>-state` (family `state`): `vault-pki-state`,
`gitops-day0-3-state`, `model-serving-llmd-mig-state`... Each evaluates the demo's own lists, read from
ansible/demos/<id>/{status,check}.yml by platform/testing/stress_state.py (the demos stay the single source: nothing is
copied here):

  cr_ready    a custom resource has a condition (default Ready), a phase, a state, an Accepted parent condition, or exists
  workloads   a Deployment or StatefulSet has all its replicas ready, a Pod is Ready
  argo_apps   the Argo CD Applications are Synced and Healthy AND Argo CD is alive and reconciled them recently
              (platform/demo/argo_health.py judges, as in the demos)

One row per assertion, with the same ids and details as the demos' own reports. Every read is a GET by name over
https://kubernetes.default.svc with the Job's own token (only `list` for a kind a demo reads by name prefix), so the Job's
ServiceAccount needs the read-only role generated from the same lists (stress_state.py rbac, applied by the namespaces
chart's stressReader switch). Without it each assertion fails with `status=403` and says what to enable.

The assertions are read from `state_assertions.json` next to the drivers in the Job, from the demos themselves in the repository.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time

import httpx

_EVALUATIONS = pathlib.Path(__file__).resolve().parents[1]
_PLATFORM = _EVALUATIONS.parent / "platform"
sys.path.insert(0, str(_PLATFORM / "testing"))
sys.path.insert(0, str(_PLATFORM / "demo"))

import argo_health  # noqa: E402
from stress_runner import register, row  # noqa: E402

SA_DIR = pathlib.Path("/var/run/secrets/kubernetes.io/serviceaccount")
DEFAULT_URL = "https://kubernetes.default.svc"
ENABLE_HINT = "enable the stress reader (zuno_stress_reader_enabled, the namespaces chart's stressReader)"


# -- the assertions -----------------------------------------------------------------------------------------------------


def load_assertions(env) -> dict:
    """{demo id: [assertion]}: the file shipped next to the drivers, else the demos of the repository."""
    flat = pathlib.Path(env.get("STRESS_DIR") or ".") / "state_assertions.json"
    if flat.is_file():
        return json.loads(flat.read_text())["demos"]
    import stress_state

    return stress_state.extract()["demos"]


# -- the Kubernetes API -------------------------------------------------------------------------------------------------


class Kube:
    """Just enough of the API: discovery of a kind's resource name, GET by name, LIST. `client` is an httpx.AsyncClient."""

    def __init__(self, client, base: str = DEFAULT_URL):
        self.client = client
        self.base = base.rstrip("/")
        self._discovery = {}

    async def resource(self, api_version: str, kind: str):
        """(resource name, namespaced) of a kind, from discovery; None when the cluster does not serve it."""
        if api_version not in self._discovery:
            path = "/api/v1" if "/" not in api_version else f"/apis/{api_version}"
            r = await self.client.get(self.base + path)
            self._discovery[api_version] = r.json().get("resources", []) if r.status_code == 200 else []
        for res in self._discovery[api_version]:
            if res.get("kind") == kind and "/" not in res.get("name", ""):
                return res["name"], bool(res.get("namespaced"))
        return None

    async def read(self, api_version: str, kind: str, name: str = "", namespace: str = ""):
        """(status, body, resource): GET by name, or LIST of the namespace (or the cluster) when `name` is empty."""
        found = await self.resource(api_version, kind)
        if found is None:
            return 404, {"error": "kind not served"}, ""
        resource, namespaced = found
        prefix = "/api/v1" if "/" not in api_version else f"/apis/{api_version}"
        path = prefix + (f"/namespaces/{namespace}" if namespaced and namespace else "") + f"/{resource}" + (f"/{name}" if name else "")
        r = await self.client.get(self.base + path)
        try:
            body = r.json()
        except ValueError:
            body = {}
        return r.status_code, body, resource


# -- the judgements (ported from ansible/demos/_lib/cr_ready.yml and workloads.yml) -------------------------------------------


def condition_status(obj: dict, condition: str) -> str:
    for c in (obj.get("status") or {}).get("conditions") or []:
        if c.get("type") == condition:
            return str(c.get("status", "absent"))
    return "absent"


def parent_statuses(obj: dict, condition: str) -> list:
    """For each parent of the status (HTTPRoute...), the status of `condition`, or "absent"."""
    out = []
    for parent in (obj.get("status") or {}).get("parents") or []:
        found = [c.get("status") for c in parent.get("conditions") or [] if c.get("type") == condition]
        out.append(str(found[0]) if found else "absent")
    return out


def judge_cr(a: dict, candidates: list):
    """(passed, detail) of one cr_ready entry over the objects that match its name or prefix."""
    if not candidates:
        return False, "not found"
    phase = a.get("phase")
    in_phase = [c for c in candidates if phase is not None and (c.get("status") or {}).get("phase") == phase]
    obj = (in_phase + candidates)[0]
    status = obj.get("status") or {}
    label = "" if "name" in a else f"{obj['metadata']['name']}: "
    if a.get("exists"):
        return True, label + "exists"
    if phase is not None:
        got = status.get("phase", "absent")
        return got == phase, f"{label}phase {got}"
    if "state" in a:
        got = status.get("state", "absent")
        return got == a["state"], f"{label}state {got}"
    if "parents" in a:
        wanted = a["parents"]
        seen = parent_statuses(obj, wanted)
        real = [s for s in seen if s != "absent"]
        return bool(real) and all(s == "True" for s in real), f"{label}{wanted} {','.join(seen)}"
    condition = a.get("condition", "Ready")
    got = condition_status(obj, condition)
    return got == str(a.get("expect", "True")), f"{label}{condition}={got}"


def judge_workload(a: dict, obj: dict):
    if not obj:
        return False, "not found"
    if a["kind"] == "Pod":
        ready = condition_status(obj, "Ready")
        return ready == "True", f"Ready={ready}"
    desired = int((obj.get("spec") or {}).get("replicas", 1) or 0)
    ready = int((obj.get("status") or {}).get("readyReplicas", 0) or 0)
    return desired > 0 and ready >= desired, f"{ready}/{desired} ready"


def refused(status: int, resource: str, name: str) -> str:
    return f"status={status} forbidden: the Job's ServiceAccount cannot read {resource} {name}: {ENABLE_HINT}"


# -- the evaluation -----------------------------------------------------------------------------------------------------


# What a 404 does not mean: a one-shot Job is garbage-collected after its TTL (a Job that EXISTS and failed still fails the row),
# and some demos name objects that a later phase of the roadmap delivers. Listed by (driver, kind, name); delete the entry
# when the phase is rolled out so the row judges for real again.
NOT_YET: dict = {}  # empty since WP-297 is Done: zuno-diagnose-praxis is live (Accepted, Ready) on demo333, 2026-11-19


def not_expected_yet(driver: str, a: dict) -> str:
    """The reason a missing object is not a failure, else ''."""
    if a.get("kind") == "Job":
        return "the one-shot Job is gone (its TTL passed); only an existing failed Job fails"
    return NOT_YET.get((driver, a.get("kind", ""), a.get("name", "")), "")


async def _cr(kube, driver: str, a: dict):
    ns, label = a.get("namespace", ""), a.get("name") or a["name_prefix"] + "*"
    rid = f"{a['kind'].lower()}/{ns or '-'}/{label}"
    status, body, resource = await kube.read(a["api_version"], a["kind"], a.get("name", ""), ns)
    if status in (401, 403):
        return row(driver, "state", rid, "custom-resource", False, refused(status, resource or a["kind"], label))
    if status == 404 and "name" in a:
        why = "" if isinstance(body, dict) and body.get("error") == "kind not served" else not_expected_yet(driver, a)
        return row(driver, "state", rid, "custom-resource", bool(why), f"status=404 skipped: {why}" if why else "status=404 not found")
    if status != 200:
        return row(driver, "state", rid, "custom-resource", False, f"status={status} {str(body)[:120]}")
    if "name" in a:
        candidates = [body]
    else:
        candidates = [i for i in body.get("items", []) if i["metadata"]["name"].startswith(a["name_prefix"])]
    passed, detail = judge_cr(a, candidates)
    return row(driver, "state", rid, "custom-resource", passed, detail)


async def _workload(kube, driver: str, a: dict):
    api = "v1" if a["kind"] == "Pod" else "apps/v1"
    rid = f"{a['kind'].lower()}/{a['namespace']}/{a['name']}"
    status, body, resource = await kube.read(api, a["kind"], a["name"], a["namespace"])
    if status in (401, 403):
        return row(driver, "state", rid, "workload", False, refused(status, resource or a["kind"], a["name"]))
    if status != 200:
        return row(driver, "state", rid, "workload", False, "status=404 not found" if status == 404 else f"status={status} {str(body)[:120]}")
    passed, detail = judge_workload(a, body)
    return row(driver, "state", rid, "workload", passed, detail)


async def _argo(kube, driver: str, a: dict):
    apps, denied = [], {}
    for wanted in a["apps"]:
        status, body, resource = await kube.read("argoproj.io/v1alpha1", "Application", wanted["name"], a["namespace"])
        if status == 200:
            apps.append(body)
        elif status in (401, 403):
            denied[wanted["name"]] = refused(status, resource or "applications", wanted["name"])
    status, sts, _ = await kube.read("apps/v1", "StatefulSet", a["controller"], a["namespace"])
    rows = argo_health.judge({"wanted": a["apps"], "applications": apps, "statefulsets": [sts] if status == 200 else [],
                              "argocds": [], "max_age": a["max_age"], "demo_id": driver, "layer": "state"})
    out = []
    for r in rows:
        detail = denied.get(r["id"].split("/", 1)[-1], r["detail"]) if r["id"] != "argo/application-controller" else (
            refused(status, "statefulsets", a["controller"]) if status in (401, 403) else r["detail"])
        out.append(row(driver, "state", r["id"], "argo", bool(r["passed"]) and not detail.startswith("status="), detail))
    return out


async def evaluate(kube, driver: str, assertions: list) -> list:
    """One row per assertion of a demo (the Argo CD unit gives one per Application plus one for the controller)."""
    rows = []
    for a in assertions:
        try:
            if a["type"] == "cr":
                rows.append(await _cr(kube, driver, a))
            elif a["type"] == "workload":
                rows.append(await _workload(kube, driver, a))
            elif a["type"] == "argo":
                rows += await _argo(kube, driver, a)
        except httpx.HTTPError as exc:
            rows.append(row(driver, "state", f"{a.get('type')}/{a.get('name', a.get('kind', '?'))}", "state", False, f"{type(exc).__name__}: {str(exc)[:160]}"))
    return rows


def _client(ctx) -> "httpx.AsyncClient":
    """An httpx client for the API server with the Job's own token and CA. Replaced by a mock transport in the tests."""
    token = ctx.env.get("KUBE_TOKEN") or (SA_DIR / "token").read_text().strip()
    ca = SA_DIR / "ca.crt"
    return httpx.AsyncClient(timeout=30, verify=str(ca) if ca.is_file() else True, headers={"Authorization": f"Bearer {token}"})


def _register(demo: str, assertions: list):
    driver_id = f"{demo}-state"

    @register(driver_id, family="state",
              description=f"the {len(assertions)} state assertion(s) of ansible/demos/{demo}, read-only over the Kubernetes API",
              needs=("the stress reader role (stressReader)",))
    async def run(ctx, i):
        started = time.monotonic()
        async with _client(ctx) as http:
            rows = await evaluate(Kube(http, ctx.env.get("KUBE_URL", DEFAULT_URL)), driver_id, assertions)
        for r in rows:
            r.duration_ms = r.duration_ms or round((time.monotonic() - started) * 1000, 1)
        return rows

    return run


for _demo, _assertions in load_assertions(os.environ).items():
    _register(_demo, _assertions)
