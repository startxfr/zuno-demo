"""ADR-0592 (WP-189): experience clients (Open WebUI, OpenClaw) are loaded next
to the agents from EXPERIENCE_CLIENTS_DIR, under their logical agent name:

- a client's tasks, access groups and classification are read; it is active;
- a client named like an agent fails the whole load closed;
- a client never enters a delegation chain, as delegator or target;
- a missing clients directory declares no client and is not an error.

Run from the component directory:

    cd components/mcp-gateway && python3 tests/test_experience_clients.py
"""
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import app.*

import yaml  # noqa: E402

from app.agent_chain import Chain, DelegationLimits, Hop, verify_chain  # noqa: E402
from app.agent_declarations import KIND_AGENT, KIND_EXPERIENCE_CLIENT, AgentDeclarationStore  # noqa: E402


def _md(front: dict) -> str:
    return "---\n" + yaml.safe_dump(front) + "---\n\nbody\n"


def _write(root: pathlib.Path, rel: str, front: dict) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_md(front))


def _task(tools):
    return {"okf_version": "v0.3", "type": "task", "title": "t", "zuno": {"allowed_tools": tools}}


class ExperienceClients(unittest.TestCase):
    def setUp(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.agents, self.clients = tmp / "agents", tmp / "experience-clients"
        _write(self.agents, "tekos/agent.okf.md", {
            "okf_version": "v0.3", "type": "agent", "title": "Tekos", "description": "d",
            "zuno": {"name": "tekos", "status": "active", "tasks": ["answer"],
                     "access": {"groups": ["agent_tekos"]},
                     "delegation": {"targets": [{"agent": "open-webui", "task": "chat"}]}}})
        _write(self.agents, "tekos/tasks/answer.md", _task(["search_confluence"]))
        self.add_client("open-webui")

    def add_client(self, name):
        _write(self.clients, f"{name}/client.okf.md", {
            "okf_version": "v0.3", "type": "experience-client", "title": name, "description": "d",
            "zuno": {"name": name, "tasks": ["chat"], "classification": "C1",
                     "access": {"groups": ["sales", "consultant"]}}})
        _write(self.clients, f"{name}/tasks/chat.md", _task(["list_drive_files", "read_gmail"]))

    def store(self, clients_dir=None):
        return AgentDeclarationStore(str(self.agents), str(clients_dir or self.clients))

    def test_a_client_is_loaded_with_its_tasks_groups_and_classification(self):
        store = self.store()
        self.assertIsNone(store.load_error)
        client = store.get("open-webui")
        self.assertEqual(client.kind, KIND_EXPERIENCE_CLIENT)
        self.assertEqual(client.status, "active")
        self.assertEqual(client.tasks, {"chat": ["list_drive_files", "read_gmail"]})
        self.assertEqual(client.access_groups, ["sales", "consultant"])
        self.assertEqual(client.classification, "C1")
        self.assertEqual(store.get("tekos").kind, KIND_AGENT)

    def test_a_client_named_like_an_agent_fails_the_load_closed(self):
        self.add_client("tekos")
        store = self.store()
        self.assertIn("has the name of an agent", store.load_error)
        self.assertFalse(store.loaded)
        self.assertIsNone(store.get("open-webui"))

    def test_a_client_with_another_type_fails_the_load_closed(self):
        _write(self.clients, "open-webui/client.okf.md", {
            "okf_version": "v0.3", "type": "agent", "title": "x", "zuno": {"name": "open-webui", "tasks": []}})
        self.assertIn("type must be 'experience-client'", self.store().load_error)

    def test_a_profile10_client_is_loaded(self):
        # ADR-0615 clause 5: okf_version "0.2" (a string) with zuno.profile "1.0".
        _write(self.clients, "open-webui/client.okf.md", {
            "okf_version": "0.2", "type": "experience-client", "title": "open-webui", "description": "d",
            "zuno": {"profile": "1.0", "name": "open-webui", "tasks": ["chat"], "classification": "C1",
                     "access": {"groups": ["sales"]}}})
        _write(self.clients, "open-webui/tasks/chat.md", {
            "okf_version": "0.2", "type": "task", "title": "t",
            "zuno": {"profile": "1.0", "allowed_tools": ["read_gmail"]}})
        store = self.store()
        self.assertIsNone(store.load_error)
        self.assertEqual(store.get("open-webui").tasks, {"chat": ["read_gmail"]})

    def test_a_client_without_a_supported_profile_fails_the_load_closed(self):
        for zuno_profile, needle in (({}, "unsupported zuno.profile None"),
                                     ({"profile": "2.0"}, "unsupported zuno.profile '2.0'")):
            with self.subTest(needle=needle):
                _write(self.clients, "open-webui/client.okf.md", {
                    "okf_version": "0.2", "type": "experience-client", "title": "open-webui",
                    "zuno": dict(zuno_profile, name="open-webui", tasks=["chat"])})
                store = self.store()
                self.assertIn(needle, store.load_error)
                self.assertFalse(store.loaded)
                self.assertIsNone(store.get("tekos"))

    def test_a_missing_clients_directory_declares_no_client(self):
        store = self.store(clients_dir=self.agents.parent / "absent")
        self.assertIsNone(store.load_error)
        self.assertIsNone(store.get("open-webui"))
        self.assertIsNotNone(store.get("tekos"))

    def test_a_client_is_never_a_delegation_target(self):
        reason = verify_chain(Chain((Hop("tekos", "answer"),)), "open-webui", "chat",
                              ["agent_tekos", "sales"], self.store(), DelegationLimits("/nonexistent"))
        self.assertIn("experience client", reason)

    def test_a_client_never_delegates(self):
        reason = verify_chain(Chain((Hop("open-webui", "chat"),)), "tekos", "answer",
                              ["agent_tekos", "sales"], self.store(), DelegationLimits("/nonexistent"))
        self.assertIn("experience client", reason)


if __name__ == "__main__":
    unittest.main()
