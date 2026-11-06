#!/usr/bin/env python3
"""Live proof of the human approval of a delegated write (ADR-0409) on a cluster running UnifAI >= 0.1.61.

Arkos is asked to have Tekos launch a cluster audit (`aap.cluster.audit`, `access: write`, listed in
`delegation.write_allowed`). The bundle must carry `spec.delegation.approval: ask`. The pending request is read
from the session's HITL stream (`GET session.subscribe`, event `approval_required`) and answered with
`POST session.approval`.

    python3 approval_proof.py approve|reject|silence [--rule]

- `approve`: the write reaches the mcp-gateway and AAP starts a REAL job (`zuno-day0-check`, about 6 minutes).
- `reject`: nothing runs. `silence`: no answer for 330 s, the request ends as a refusal after about 300 s.
- `--rule`: first sets the strongest session auto-approval rule (`approve_all`); the request must still appear and
  wait ("an auto-approval does not cross the hop"). Needs UnifAI >= 0.1.62: until the worker loads the session
  metadata for its gate (fork R-539) the rule is saved but never applied, and this check cannot pass.

Environment (no secret is printed or written): DEMO_PERSONA_PASSWORD, UNIFAI_URL, KEYCLOAK_URL, and optionally
UNIFAI_TEAM_NAME (default `agent-arkos`) or UNIFAI_TEAM_ID. Arkos does not always delegate on a plain prompt, so
the prompt is directive; if no request shows up the script says so and exits 2. After a reject or a silence Arkos
may ask again every few minutes: the session is cancelled at the end.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import threading
import time

os.environ.setdefault("AGENT", "arkos")
os.environ.setdefault("TASK_NAME", "draft-architecture-testimonial")
os.environ.setdefault("UNIFAI_TEAM_NAME", "agent-arkos")
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tekos"))
from run_scenarios import _unifai  # noqa: E402

sys.path.insert(0, str(HERE.parent / "common"))

PERSONA = os.getenv("APPROVAL_PROOF_PERSONA", "eval-consultant-01")
PROMPT = ("Call the Tekos delegation tool right now and ask it to launch a fresh cluster audit with its audit tool "
          "(aap.cluster.audit), then tell me the job link it returns. Do not answer from memory.")
WAIT_REQUEST_SECONDS = 240
SILENCE_SECONDS = 330


def main(argv: list) -> int:
    args = [a for a in argv if not a.startswith("--")]
    mode = args[0] if args else "approve"
    if mode not in ("approve", "reject", "silence"):
        print(__doc__)
        return 64
    t = _unifai()
    c = t.client(PERSONA)
    sid = t.create(PERSONA, t.workflow_id(PERSONA), None)
    base = f"{t.ui_url}/api2/sessions"
    print("SESSION", sid, flush=True)
    try:
        if "--rule" in argv:
            body = {"sessionId": sid, "nodeUid": None, "toolName": None, "action": "auto_approve", **t._team_body()}
            print("RULE set", c.post(f"{base}/session.approval.rule", json=body).status_code, flush=True)
        events: list = []
        found = threading.Event()

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
                            if e.get("type") == "approval_required":
                                found.set()
            except Exception as exc:  # the stream ends with the session
                print("stream ended", type(exc).__name__, flush=True)

        threading.Thread(target=listen, daemon=True).start()
        time.sleep(2)
        print("submit", c.post(f"{base}/user.session.submit", json={"sessionId": sid, "inputs": {"user_prompt": PROMPT}, **t._team_body()}).status_code, flush=True)
        started = time.monotonic()
        if not found.wait(timeout=WAIT_REQUEST_SECONDS):
            print(f"NO approval_required within {WAIT_REQUEST_SECONDS} s; event types:", sorted({str(e.get('type')) for e in events}), flush=True)
            return 2
        ev = next(e for e in events if e.get("type") == "approval_required")
        shown = {k: ev.get(k) for k in ("request_id", "approval_type", "tool_name", "tool_args", "tool_access_mode", "display_name")}
        print("APPROVAL_REQUIRED after", round(time.monotonic() - started, 1), "s:", json.dumps(shown)[:600], flush=True)
        if mode == "silence":
            print("SILENCE: no answer for", SILENCE_SECONDS, "s", flush=True)
            time.sleep(SILENCE_SECONDS)
        else:
            feedback = "live proof - do not retry this operation"
            d = c.post(f"{base}/session.approval", json={"sessionId": sid, "requestId": ev["request_id"], "decision": mode, "feedback": feedback, **t._team_body()})
            print("ANSWER", mode, d.status_code, d.text[:140], flush=True)
        state = ""
        for _ in range(60):
            state = c.get(f"{base}/session.status.get", params={"sessionId": sid, **t._team_body()}).text.strip().strip('"')
            if state in ("COMPLETED", "FAILED", "CANCELLED"):
                break
            time.sleep(5)
        print("FINAL", state, flush=True)
        return 0
    finally:
        r = c.post(f"{base}/session.cancel", json={"sessionId": sid, **t._team_body()})  # 409 once completed: fine
        print("cancel", r.status_code, flush=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
