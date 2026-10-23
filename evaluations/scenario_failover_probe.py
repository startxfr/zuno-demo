#!/usr/bin/env python3
"""Single-agent, single-turn live chat probe for WP-105/ADR-0536's node
failover drill (`make d3 scenario-failover-node`).

WP-156: the turn now runs on UnifAI (ADR-0561), which serves the agents,
through the UnifAI UI route - the only door from outside UnifAI's pods
(NetworkPolicy unifai-internal-apis). The persona signs in as a browser does
(evaluations/common/unifai_target.py) and drives AGENT's workflow in its
group-bound team workspace `agent-<agent>`; credentials are
DEMO_PERSONA_PASSWORD and UNIFAI_URL, no OIDC client secret.

Unlike its pre-UnifAI version, this probe CAN report which provider
answered: UnifAI's LLM element asks the ai-gateway why it answered
(`GET /v1/routing-decisions/{request_id}`, WP-148, chart
`gatewayLLM.routingLookup`) and carries the decision on the assistant
message as `metadata.llm_response.routing` - provider, model,
classification, fallback. It is reported as `routing`/`provider`. The
lookup is best effort by design (a 2s, swallowed call) and absent when the
final answer merges several agents' results, so `provider` may be null with
`ok: true`; scenario_failover_verify.py then falls back to the
`zuno_model_calls_total` counter delta, as before. The routing is that of
the turn's LAST model call (the one that wrote the answer), which is the
call the drill is about: a ReAct turn may call the model several times, all
under the same agent/task routing preference.

Usage:
    AGENT=tekos UNIFAI_URL=... DEMO_PERSONA_PASSWORD=... \\
        python3 evaluations/scenario_failover_probe.py --persona consultant-01 --message "..."
    AGENT=comage ... python3 evaluations/scenario_failover_probe.py --persona sale-01 --message "..."

Prints one JSON object to stdout:
    {"agent", "persona", "ok", "session_id", "provider", "routing", "detail"}.
Exit code 0 whether or not the chat call itself succeeded - failure is
reported IN the JSON body, not via process exit, because the caller (the
inject playbook) needs to keep going and interpret a failed baseline call as
a precondition problem, not crash the whole drill.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

# Default matches run_scenarios.py's own default so a bare invocation
# without AGENT= still does something sane for manual testing.
AGENT = os.getenv("AGENT", "tekos")

# In the repo this file sits in evaluations/, the transport in
# evaluations/common/; the probe Job mounts both flat under /gate.
_here = pathlib.Path(__file__).parent.resolve()
for _candidate in (_here / "common", _here):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))
from unifai_target import UnifaiTarget  # noqa: E402


def probe(persona: str, message: str, timeout_seconds: float = 90, target: UnifaiTarget = None) -> dict:
    out = {"agent": AGENT, "persona": persona, "ok": False, "session_id": None, "provider": None, "routing": None}
    try:
        if target is None:
            target = UnifaiTarget(
                os.getenv("DEMO_PERSONA_PASSWORD", ""),
                agent=AGENT,
                team_name=os.getenv("UNIFAI_TEAM_NAME") or f"agent-{AGENT}",
            )
        run = target.run(persona, message, timeout=timeout_seconds)
    except Exception as exc:  # noqa: BLE001 - sign-in/transport failure is a failed probe, not a crash
        return dict(out, detail=str(exc))
    finally:
        # Best-effort cleanup of the session this probe just created, same
        # posture as every other evaluations/*/*.py script - a demo
        # persona's real session list must not accumulate synthetic drill
        # turns.
        if target is not None:
            try:
                target.cleanup()
            except Exception:  # noqa: BLE001 - cleanup never fails a probe
                pass

    routing = run.raw.get("routing")
    out.update(session_id=run.session_id, routing=routing, provider=(routing or {}).get("provider"))
    if run.status != 200:
        return dict(out, detail=f"status={run.status} body={str(run.raw)[:500]}")
    if not run.reply:
        return dict(out, detail=f"turn completed with no answer: {str(run.raw)[:500]}")
    return dict(
        out,
        ok=True,
        detail="chat call succeeded" + ("" if routing else "; no routing decision on the answer (lookup off or merged answer)"),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persona", required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=90)
    args = parser.parse_args()

    print(json.dumps(probe(args.persona, args.message, args.timeout_seconds)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
