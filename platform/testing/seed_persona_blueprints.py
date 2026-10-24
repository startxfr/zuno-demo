#!/usr/bin/env python3
"""WP-175: two personal test blueprints in UnifAI for every business persona of realm zuno.

  test-<persona>-chat   one agent node on the platform LLM (the ai-gateway, the persona's own token)
  test-<persona>-a2a    the persona's question delegated over A2A to an agent the persona is entitled to,
                        served by the a2a-gateway (ADR-0585), again with the persona's own token

Each persona signs in to the UnifAI UI through realm zuno (the real browser OIDC flow, evaluations/common/
unifai_target.py) and saves the blueprints in its personal workspace, so nobody else sees them. The script is
idempotent (a blueprint with the same name is updated) and `--cleanup` deletes what it created.

    UNIFAI_URL=https://unifai-ui-zuno-unifai.apps.<domain> DEMO_PERSONA_PASSWORD=... \
        python3 platform/testing/seed_persona_blueprints.py [--personas sale-01,board-02] [--validate] [--cleanup]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

A2A_GATEWAY_URL = os.getenv("A2A_GATEWAY_URL", "http://a2a-gateway.zuno-ai-run.svc:8080").rstrip("/")
AI_GATEWAY_URL = os.getenv("AI_GATEWAY_URL", "http://ai-gateway.zuno-ai-run.svc:8080").rstrip("/")

# Business persona -> the agent its A2A blueprint delegates to (one of the persona's agent_* groups, an agent
# the admitted release carries as an active bundle). The 11 negative-test personas are deliberately absent.
PERSONA_AGENT: Dict[str, str] = {
    "sale-01": "comage", "sale-02": "comage", "recrut-01": "comage",
    "consultant-01": "tekos", "consultant-02": "tekos", "consultant-03": "tekos",
    "ai-dev-01": "tekos", "ai-ops-01": "tekos", "paas-dev-01": "tekos", "paas-ops-01": "tekos",
    "adv-01": "advantage", "adv-02": "advantage",
    "finance-01": "finage", "finance-02": "finage",
    "board-01": "advantage", "board-02": "advantage",
}

_USER_NODE = {"rid": "user_question_node_rid", "name": "User Question Node", "type": "user_question_node",
              "config": {"type": "user_question_node"}}
_FINAL_NODE = {"rid": "final_answer_node_rid", "name": "Final Answer Node", "type": "final_answer_node",
               "config": {"type": "final_answer_node"}}


def blueprint_names(persona: str) -> List[str]:
    return [f"test-{persona}-chat", f"test-{persona}-a2a"]


def chat_blueprint(persona: str) -> Dict[str, Any]:
    return {
        "name": f"test-{persona}-chat",
        "description": f"Test blueprint of {persona}: one agent on the platform LLM (WP-175).",
        "llms": [{
            "rid": "zuno_gateway_llm_rid", "name": "zuno-gateway", "type": "openai_compatible",
            "config": {
                "type": "openai_compatible", "model_name": "auto", "base_url": f"{AI_GATEWAY_URL}/v1",
                "api_key": "EMPTY", "forward_user_token": True,
                "default_headers": {"X-Zuno-Run-Id": "{session_id}"},
            },
        }],
        "nodes": [
            _USER_NODE, _FINAL_NODE,
            {"rid": "agent_rid", "name": "Assistant", "type": "custom_agent_node",
             "config": {"type": "custom_agent_node", "llm": "zuno_gateway_llm_rid",
                        "system_message": "You are a concise assistant. Answer the user's question in a few sentences."}},
        ],
        "plan": [
            {"uid": "user_input", "node": "user_question_node_rid"},
            {"uid": "assistant", "after": "user_input", "node": "agent_rid"},
            {"uid": "finalize", "after": "assistant", "node": "final_answer_node_rid"},
        ],
    }


def a2a_blueprint(persona: str, agent: str) -> Dict[str, Any]:
    return {
        "name": f"test-{persona}-a2a",
        "description": f"Test blueprint of {persona}: the question is delegated to the {agent} agent over A2A (WP-175).",
        "nodes": [
            _USER_NODE, _FINAL_NODE,
            {"rid": "a2a_agent_rid", "name": f"Agent {agent} (A2A)", "type": "a2a_agent_node",
             "config": {
                 "type": "a2a_agent_node", "base_url": f"{A2A_GATEWAY_URL}/agents/{agent}",
                 "auth_method": "forward_user_token",
                 "additional_headers": {"X-Zuno-Run-Id": "{session_id}"},
             }},
        ],
        "plan": [
            {"uid": "user_input", "node": "user_question_node_rid"},
            {"uid": "delegate", "after": "user_input", "node": "a2a_agent_rid"},
            {"uid": "finalize", "after": "delegate", "node": "final_answer_node_rid"},
        ],
    }


def blueprints_for(persona: str) -> List[Dict[str, Any]]:
    return [chat_blueprint(persona), a2a_blueprint(persona, PERSONA_AGENT[persona])]


def to_yaml(blueprint: Dict[str, Any]) -> str:
    return yaml.safe_dump(blueprint, sort_keys=False, allow_unicode=True)


class Seeder:
    def __init__(self, target: Any) -> None:
        self.target = target
        self.ui = target.ui_url

    def _existing(self, persona: str) -> Dict[str, str]:
        r = self.target.client(persona).get(f"{self.ui}/api2/blueprints/available.blueprints.summary.get")
        r.raise_for_status()
        return {item["name"]: item["blueprint_id"] for item in r.json()}

    def save(self, persona: str, blueprint: Dict[str, Any]) -> str:
        client, raw = self.target.client(persona), to_yaml(blueprint)
        existing = self._existing(persona).get(blueprint["name"])
        if existing:
            r = client.put(f"{self.ui}/api2/blueprints/blueprint.update",
                           json={"blueprintId": existing, "blueprintRaw": raw})
            if r.status_code not in (200, 201):
                raise RuntimeError(f"{persona}/{blueprint['name']}: update failed {r.status_code} {r.text[:300]}")
            return existing
        r = client.post(f"{self.ui}/api2/blueprints/blueprint.save", json={"blueprintRaw": raw})
        if r.status_code not in (200, 201):
            raise RuntimeError(f"{persona}/{blueprint['name']}: save failed {r.status_code} {r.text[:300]}")
        return r.json().get("blueprint_id", "")

    def validate(self, persona: str, blueprint_id: str) -> Optional[str]:
        """None when the blueprint validates, else the first error."""
        r = self.target.client(persona).post(
            f"{self.ui}/api2/blueprints/blueprint.validate", json={"blueprintId": blueprint_id, "timeoutSeconds": 15},
        )
        if r.status_code != 200:
            return f"validate answered {r.status_code}: {r.text[:200]}"
        body = r.json()
        if body.get("is_valid", body.get("valid", True)):
            return None
        errors = [m for m in (body.get("messages") or []) if str(m.get("severity", "")).lower() == "error"]
        return str((errors or [body])[0])[:300]

    def cleanup(self, persona: str) -> int:
        existing, removed = self._existing(persona), 0
        for name in blueprint_names(persona):
            if name in existing:
                r = self.target.client(persona).delete(
                    f"{self.ui}/api2/blueprints/remove.blueprint", params={"blueprintId": existing[name]},
                )
                removed += r.status_code in (200, 204)
        return removed


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--personas", default="all", help="comma-separated persona names, or 'all' (default)")
    parser.add_argument("--validate", action="store_true", help="validate each blueprint after saving it")
    parser.add_argument("--cleanup", action="store_true", help="delete the test blueprints instead of creating them")
    parser.add_argument("--dry-run", action="store_true", help="print the YAML and exit without calling UnifAI")
    args = parser.parse_args(argv)

    personas = list(PERSONA_AGENT) if args.personas == "all" else [p.strip() for p in args.personas.split(",") if p.strip()]
    unknown = [p for p in personas if p not in PERSONA_AGENT]
    if unknown:
        print(f"unknown or non-business persona(s): {', '.join(unknown)}", file=sys.stderr)
        return 2
    if args.dry_run:
        for persona in personas:
            for blueprint in blueprints_for(persona):
                print(f"--- {persona} / {blueprint['name']}\n{to_yaml(blueprint)}")
        return 0

    from evaluations.common.unifai_target import UnifaiTarget  # needs httpx: only on a real run

    password = os.getenv("DEMO_PERSONA_PASSWORD", "")
    if not password:
        print("DEMO_PERSONA_PASSWORD is required", file=sys.stderr)
        return 2
    seeder = Seeder(UnifaiTarget(password))
    failures = 0
    for persona in personas:
        try:
            if args.cleanup:
                print(f"{persona}: removed {seeder.cleanup(persona)} blueprint(s)")
                continue
            for blueprint in blueprints_for(persona):
                blueprint_id = seeder.save(persona, blueprint)
                problem = seeder.validate(persona, blueprint_id) if args.validate else None
                status = "ok" if problem is None else f"INVALID: {problem}"
                failures += problem is not None
                print(f"{persona}: {blueprint['name']} {blueprint_id} {status}")
        except Exception as exc:  # one persona failing must not hide the others
            failures += 1
            print(f"{persona}: FAILED {exc}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
