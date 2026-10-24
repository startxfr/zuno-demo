"""WP-175: the shape of the persona test blueprints, without any cluster.

Run from this directory:

    python3 tests/test_seed_persona_blueprints.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

TESTING_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TESTING_DIR))
import seed_persona_blueprints as seed  # noqa: E402

REPO_ROOT = TESTING_DIR.parents[1]
REALM = REPO_ROOT / "gitops/charts/keycloak/files/realm-zuno.json"


def _realm_users() -> dict:
    import json

    users = json.loads(REALM.read_text())["users"]
    return {u["username"]: set(u.get("groups") or []) for u in users}


def test_every_persona_gets_exactly_two_blueprints_one_over_a2a() -> None:
    for persona in seed.PERSONA_AGENT:
        blueprints = seed.blueprints_for(persona)
        assert [b["name"] for b in blueprints] == seed.blueprint_names(persona)
        kinds = [{n["type"] for n in b["nodes"]} for b in blueprints]
        assert "a2a_agent_node" not in kinds[0] and "custom_agent_node" in kinds[0]
        assert "a2a_agent_node" in kinds[1]


def test_plans_reference_only_declared_nodes_and_steps() -> None:
    for persona in seed.PERSONA_AGENT:
        for blueprint in seed.blueprints_for(persona):
            rids = {n["rid"] for n in blueprint["nodes"]}
            uids = {s["uid"] for s in blueprint["plan"]}
            assert len(uids) == len(blueprint["plan"])
            for step in blueprint["plan"]:
                assert step["node"] in rids
                assert step.get("after", next(iter(uids))) in uids
            agent = next((n for n in blueprint["nodes"] if n["type"] == "custom_agent_node"), None)
            if agent:
                assert agent["config"]["llm"] in {llm["rid"] for llm in blueprint["llms"]}
            assert yaml.safe_load(seed.to_yaml(blueprint)) == blueprint


def test_the_a2a_target_is_an_agent_the_persona_is_entitled_to() -> None:
    users = _realm_users()
    for persona, agent in seed.PERSONA_AGENT.items():
        assert persona in users, persona
        assert any(g.lstrip("/") == f"agent_{agent}" for g in users[persona]), f"{persona} lacks agent_{agent}"


def test_negative_test_personas_are_not_seeded() -> None:
    assert not [p for p in seed.PERSONA_AGENT if "only-user" in p]
    assert len(seed.PERSONA_AGENT) == 16


def test_the_user_token_is_forwarded_only_to_in_cluster_urls() -> None:
    for persona in seed.PERSONA_AGENT:
        chat, a2a = seed.blueprints_for(persona)
        llm = chat["llms"][0]["config"]
        assert llm["forward_user_token"] is True and ".svc" in llm["base_url"]
        node = a2a["nodes"][-1]["config"]
        assert node["auth_method"] == "forward_user_token" and ".svc" in node["base_url"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
