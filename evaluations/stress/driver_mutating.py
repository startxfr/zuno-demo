"""The three mutating stress drivers (WP-310 batch 2, ADR-0624), run only with `allow_mutating` and only as `stress-mutate-01`.

  delegation-approval   Arkos is asked to have Tekos launch a cluster audit (a delegated WRITE). The pending approval is
                        read from the session's stream and REJECTED (never approved: an approval starts a real AAP job),
                        then the answered and a made-up request id must both give 409 `approval_not_pending`. The
                        session is cancelled and deleted whatever happens. Port of evaluations/arkos/approval_proof.py reject.
  unifai-live-rag       a uniquely named small document is uploaded to the persona's Personal library, indexed until DONE,
                        then deleted and checked absent (evaluations/unifai_rag_library.py). Nothing else in the library is touched.
  image-signing-refusal an unsigned, tag-referenced image is offered to the dedicated test namespace `zuno-stress-admission`
                        (label policy.rhtas.com/include=true) as a DRY-RUN pod create: the image-signing admission webhook
                        must refuse it. Nothing is stored, so there is nothing to clean up. It needs a namespaced create on
                        pods, granted only when `stressImageProof.enabled` (namespaces chart, default off).

The persona is a constant, never `ctx.persona`: a dedicated Keycloak user (keycloak chart `evalPersonas`, a copy of consultant-01
in `/zuno-evaluation`), so what these drivers create or spend is attributable and no demo or load persona is ever used.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys
import tempfile
import threading
import time
import uuid

_STRESS = pathlib.Path(__file__).resolve().parent
_EVALUATIONS = _STRESS.parent
for _p in (str(_STRESS), str(_EVALUATIONS), str(_EVALUATIONS / "common"), str(_EVALUATIONS / "tekos")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import unifai_rag_library as lib  # noqa: E402
import unifai_target as ut  # noqa: E402
from stress_runner import register, row  # noqa: E402

MUTATE_PERSONA = "stress-mutate-01"
APPROVAL_PROMPT = ("Call the Tekos delegation tool right now and ask it to launch a fresh cluster audit with its audit tool "
                   "(aap.cluster.audit), then tell me the job link it returns. Do not answer from memory.")
WAIT_REQUEST_SECONDS = 240
FINAL_STATES = ("COMPLETED", "FAILED", "CANCELLED")
UNKNOWN_REQUEST = "00000000-dead-beef-0000-000000000000"
ADMISSION_NAMESPACE = "zuno-stress-admission"
UNSIGNED_IMAGE = "registry.access.redhat.com/ubi9/ubi-minimal:latest"  # a tag, not a digest: refused by the webhook in any mode


def _target(ctx, agent: str, team_default: str):
    return ut.UnifaiTarget(ctx.env.get("DEMO_PERSONA_PASSWORD", ""),
                           ui_url=ctx.env.get("UNIFAI_URL") or "https://unifai-ui-zuno-unifai." + ctx.env.get("CLUSTER_BASE_DOMAIN", "apps.invalid"),
                           agent=agent, team_name=ctx.env.get("UNIFAI_TEAM_NAME") or team_default)


# -- delegation-approval --------------------------------------------------------------------------------------------


def unseen_requests(events: list, seen: set) -> list:
    return [e for e in events if e.get("type") == "approval_required" and e.get("request_id") not in seen]


def judge_approval(result: dict) -> tuple:
    """(passed, detail) of one rejected approval: asked, rejected (200), and both stale probes answered 409 approval_not_pending."""
    if not result.get("asked"):
        return False, f"no approval_required within {WAIT_REQUEST_SECONDS} s (event types: {result.get('types')}): the agent did not delegate a write"
    problems = []
    if result.get("answer") != 200:
        problems.append(f"rejecting answered {result.get('answer')}")
    for label in ("stale", "unknown"):
        if result.get(label) != 409:
            problems.append(f"the {label} request id answered {result.get(label)} instead of 409")
    state = result.get("final") or "unfinished"
    detail = f"status=200 rejected after {result.get('seconds')} s, stale={result.get('stale')} unknown={result.get('unknown')} final={state}"
    return (not problems), (detail if not problems else f"status={result.get('answer')} " + "; ".join(problems))


def approval_turn(ctx, wait: float = WAIT_REQUEST_SECONDS, sleep=time.sleep) -> dict:
    """One delegated write asked, its approval rejected, the session cancelled and deleted. Blocking; always cleans up."""
    t = _target(ctx, "arkos", "agent-arkos")
    result: dict = {"asked": False}
    sid = ""
    c = None
    try:
        c = t.client(MUTATE_PERSONA)
        sid = t.create(MUTATE_PERSONA, t.workflow_id(MUTATE_PERSONA), None)
        base = f"{t.ui_url}/api2/sessions"
        events: list = []

        def listen() -> None:
            try:
                with c.stream("GET", f"{base}/session.subscribe", params={"sessionId": sid, **t._team_body()}, timeout=None) as r:
                    for line in r.iter_lines():
                        try:
                            e = json.loads(line) if line.strip() else None
                        except ValueError:
                            continue
                        if e:
                            events.append(e)
            except Exception:  # noqa: BLE001 - the stream ends with the session
                pass

        threading.Thread(target=listen, daemon=True).start()
        sleep(2)
        c.post(f"{base}/user.session.submit", json={"sessionId": sid, "inputs": {"user_prompt": APPROVAL_PROMPT}, **t._team_body()})
        started = time.monotonic()
        seen: set = set()
        found = None
        while time.monotonic() - started < wait and found is None:
            found = next(iter(unseen_requests(events, seen)), None)
            if found is None:
                sleep(1)
        result["types"] = sorted({str(e.get("type")) for e in events})
        if found is None:
            return result
        seen.add(found["request_id"])
        result["asked"] = True
        result["seconds"] = round(time.monotonic() - started, 1)
        feedback = "stresstest - do not retry this operation"
        answer = c.post(f"{base}/session.approval", json={"sessionId": sid, "requestId": found["request_id"], "decision": "reject",
                                                           "feedback": feedback, **t._team_body()})
        result["answer"] = answer.status_code
        for label, rid in (("stale", found["request_id"]), ("unknown", UNKNOWN_REQUEST)):
            r = c.post(f"{base}/session.approval", json={"sessionId": sid, "requestId": rid, "decision": "approve",
                                                         "feedback": "stale probe", **t._team_body()})
            result[label] = r.status_code
        for _ in range(24):  # the agent may ask again after a refusal: reject it too, then wait for the end
            for extra in unseen_requests(events, seen):
                seen.add(extra["request_id"])
                c.post(f"{base}/session.approval", json={"sessionId": sid, "requestId": extra["request_id"], "decision": "reject",
                                                         "feedback": feedback, **t._team_body()})
            state = c.get(f"{base}/session.status.get", params={"sessionId": sid, **t._team_body()}).text.strip().strip('"')
            if state in FINAL_STATES:
                result["final"] = state
                break
            sleep(5)
        return result
    finally:
        try:
            if sid and c is not None:
                c.post(f"{t.ui_url}/api2/sessions/session.cancel", json={"sessionId": sid, **t._team_body()})  # 409 once completed
        finally:
            t.cleanup()


@register("delegation-approval", family="mutating", mutating=True,
          description="a delegated write asked of Arkos, its approval REJECTED, stale ids answer 409; session cancelled and deleted",
          needs=("unifai", "agent-arkos team", f"the dedicated persona {MUTATE_PERSONA}"))
async def delegation_approval(ctx, i):
    started = time.monotonic()
    result = await asyncio.to_thread(approval_turn, ctx)
    passed, detail = judge_approval(result)
    return [row("delegation-approval", "mutating", "reject-and-stale", "mutating", passed, detail, (time.monotonic() - started) * 1000)]


# -- unifai-live-rag ------------------------------------------------------------------------------------------------


def doc_name(run_id: str, i: int) -> str:
    """A bare, unique file name: one document per iteration, recognisable as the stress run's."""
    safe = "".join(ch for ch in run_id if ch.isalnum() or ch == "-")[:40] or "run"
    return f"stress-rag-{safe}-{i}-{uuid.uuid4().hex[:6]}.md"


def rag_cycle(ctx, i: int, timeout: float = 300) -> list:
    """Upload one small document, wait until it is DONE, delete it, check it is gone. Blocking; always deletes. Returns result dicts."""
    t = _target(ctx, "tekos", "agent-tekos")
    name = doc_name(ctx.run_id or "run", i)
    out = []
    client = t.client(MUTATE_PERSONA)
    api = f"{t.ui_url}/api1"
    try:
        with tempfile.TemporaryDirectory(prefix="stress-rag-") as tmp:
            path = pathlib.Path(tmp) / name
            path.write_text(f"# Stress document {name}\n\nThe stress test vault code word is {uuid.uuid4().hex[:8]}.\n")
            up = lib.upload_files(client, api, [path])
            out += up
            if all(r["ok"] for r in up):
                out += lib.wait_done(client, api, [name], timeout=timeout)
    finally:
        try:
            out += lib.delete_named(client, api, [name])
            left = [s for s in lib.list_sources(client, api) if s["source_name"] == name]
            out.append({"action": "verify-gone", "name": name, "ok": not left, "result": "gone" if not left else "STILL PRESENT"})
        except Exception as exc:  # noqa: BLE001 - reported as a failing cleanup row
            out.append({"action": "cleanup", "name": name, "ok": False, "result": f"{type(exc).__name__}: {str(exc)[:120]}"})
        t.cleanup()
    return out


def judge_rag(results: list) -> list:
    """[(id, passed, detail)]: the indexing and the cleanup are judged apart, so a leftover document is never hidden by a pass."""
    indexed = [r for r in results if r["action"] in ("upload", "wait")]
    cleanup = [r for r in results if r["action"] in ("delete", "verify-gone", "cleanup")]
    ok_index = bool(indexed) and all(r["ok"] for r in indexed) and any(r["action"] == "wait" for r in indexed)
    waited = next((r for r in indexed if r["action"] == "wait"), {})
    rows = [("upload-indexed", ok_index, f"status=200 indexed in {waited.get('seconds')} s" if ok_index else
             "status=500 " + ", ".join(f"{r['action']}:{r.get('result')}" for r in indexed if not r["ok"]) if indexed else "status=500 nothing uploaded")]
    ok_clean = bool(cleanup) and all(r["ok"] for r in cleanup)
    rows.append(("cleanup", ok_clean, "status=200 the document is deleted and gone" if ok_clean else
                 "status=500 LEFT BEHIND: " + ", ".join(f"{r['action']}:{r.get('result')}" for r in cleanup if not r["ok"])))
    return rows


@register("unifai-live-rag", family="mutating", mutating=True,
          description="a uniquely named document uploaded to the persona's Personal library, indexed until DONE, then deleted",
          needs=("unifai", "the RAG pipeline", f"the dedicated persona {MUTATE_PERSONA}"))
async def unifai_live_rag(ctx, i):
    started = time.monotonic()
    results = await asyncio.to_thread(rag_cycle, ctx, i)
    ms = (time.monotonic() - started) * 1000
    return [row("unifai-live-rag", "mutating", rid, "mutating", ok, detail, ms) for rid, ok, detail in judge_rag(results)]


# -- image-signing-refusal ------------------------------------------------------------------------------------------


def unsigned_pod() -> dict:
    """A pod that satisfies the restricted SCC (so a refusal can only come from the image policy), image referenced by TAG."""
    return {"apiVersion": "v1", "kind": "Pod",
            "metadata": {"generateName": "stress-unsigned-", "labels": {"zuno.io/stresstest": "image-signing-refusal"}},
            "spec": {"restartPolicy": "Never", "automountServiceAccountToken": False,
                     "securityContext": {"runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"}},
                     "containers": [{"name": "unsigned", "image": UNSIGNED_IMAGE, "command": ["sleep", "1"],
                                     "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}}}]}}


def judge_admission(status: int, body_text: str) -> tuple:
    """(passed, detail) of a dry-run create of the unsigned pod: the image policy must refuse it."""
    text = (body_text or "")[:300].replace("\n", " ")
    low = text.lower()
    if status in (200, 201, 202):
        return False, f"status={status} the unsigned image was ADMITTED (dry run): the image-signing webhook does not cover {ADMISSION_NAMESPACE}"
    if status == 404:
        return False, f"status=404 the namespace {ADMISSION_NAMESPACE} does not exist: enable stressImageProof in the namespaces chart"
    if status == 403 and "cannot create resource" in low:
        return False, f"status=403 the Job may not create pods in {ADMISSION_NAMESPACE}: stressImageProof.enabled grants it. {text[:120]}"
    if status in (400, 403, 422) and any(w in low for w in ("digest", "signature", "policy", "sigstore", "admission webhook")):
        return True, f"status={status} refused by the image policy: {text[:160]}"
    return False, f"status={status} refused, but not by the image policy: {text[:160]}"


@register("image-signing-refusal", family="mutating", mutating=True,
          description=f"an unsigned tag-referenced image offered to {ADMISSION_NAMESPACE} as a dry-run pod: the image policy must refuse it",
          needs=(f"namespace {ADMISSION_NAMESPACE} (policy.rhtas.com/include=true)", "stressImageProof.enabled"))
async def image_signing_refusal(ctx, i):
    import driver_state as ds

    started = time.monotonic()
    async with ds._client(ctx) as http:
        r = await http.post(f"{ctx.env.get('KUBE_URL', ds.DEFAULT_URL)}/api/v1/namespaces/{ADMISSION_NAMESPACE}/pods",
                            params={"dryRun": "All"}, json=unsigned_pod())
    passed, detail = judge_admission(r.status_code, r.text)
    return [row("image-signing-refusal", "mutating", "unsigned-refused", "mutating", passed, detail, (time.monotonic() - started) * 1000)]
