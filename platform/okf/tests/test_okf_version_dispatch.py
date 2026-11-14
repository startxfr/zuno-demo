"""ADR-0615 clause 5 / WP-263: every OKF reader hook applies the same version dispatch rule.

ADR-0508 clause 4 keeps one parser per component, so the rule below is written once in each
hook, not shared:

| okf_version                      | zuno.profile            | result                               |
|----------------------------------|-------------------------|--------------------------------------|
| "v0.2" or "v0.3"                 | absent                  | legacy document                      |
| "0.2"                            | "1.0"                   | profile 1.0                          |
| "0.2"                            | absent or another value | refused: unsupported zuno.profile    |
| anything else (unquoted 0.2 too) | -                       | refused: unsupported okf_version     |

and a legacy version with a zuno.profile is refused. This test feeds the same frontmatter
mappings to every copy and asserts identical results:

- `okf_document_version` of admit_okf_bundle.py, okf_narrowing.py, the mcp-gateway and
  a2a-gateway hooks, mlops, evaluations/common/okf_release.py and check_docs.py;
- the `_agents_okf_version_error` expression of ansible/roles/agents/tasks/check.yml,
  rendered with Jinja (empty means accepted).

Then, when the conformance cases are available (ZUNO_OKF_CONFORMANCE_DIR or the admitted
release, see platform/okf/release_cache.py), it does the same on every agent and task document
of every case. The version functions are pure: the heavy dependencies of mlops (boto3,
requests, botocore, httpx) are stubbed only when they are not installed.

Run from the repository root:
    python3 platform/okf/tests/test_okf_version_dispatch.py
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import types
import unittest
from typing import Callable, Dict, List, Optional, Tuple

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "platform" / "okf"))

import release_cache  # noqa: E402

CASES = release_cache.conformance_dir()
SKIP = "no OKF conformance cases (set ZUNO_OKF_CONFORMANCE_DIR); case documents not checked"
ANSIBLE_CHECK = ROOT / "ansible" / "roles" / "agents" / "tasks" / "check.yml"
ANSIBLE_TASK = "agents | fail if a catalog-only agent's OKF bundle is structurally invalid"

ONLY_WITH_UPSTREAM = 'zuno.profile is only valid with okf_version "0.2"'

# (description, frontmatter, accepted version or None, needle of the refusal or None)
TABLE: List[Tuple[str, dict, Optional[str], Optional[str]]] = [
    ("legacy v0.2", {"okf_version": "v0.2", "type": "agent"}, "v0.2", None),
    ("legacy v0.3", {"okf_version": "v0.3", "type": "task", "zuno": {"allowed_tools": ["t"]}}, "v0.3", None),
    ("profile 1.0", {"okf_version": "0.2", "type": "agent", "zuno": {"profile": "1.0", "status": "active"}},
     "1.0", None),
    ("0.2 without zuno", {"okf_version": "0.2", "type": "agent"}, None, "unsupported zuno.profile None"),
    ("0.2 with a null zuno", {"okf_version": "0.2", "zuno": None}, None, "unsupported zuno.profile None"),
    ("0.2 without zuno.profile", {"okf_version": "0.2", "zuno": {"status": "active"}}, None,
     "unsupported zuno.profile None"),
    ("0.2 with zuno.profile 2.0", {"okf_version": "0.2", "zuno": {"profile": "2.0"}}, None,
     "unsupported zuno.profile '2.0'"),
    ("0.2 with an unquoted zuno.profile 1.0", {"okf_version": "0.2", "zuno": {"profile": 1.0}}, None,
     "unsupported zuno.profile 1.0"),
    ("unquoted okf_version 0.2", {"okf_version": 0.2, "zuno": {"profile": "1.0"}}, None,
     "unsupported okf_version 0.2"),
    ("okf_version v0.9", {"okf_version": "v0.9"}, None, "unsupported okf_version 'v0.9'"),
    ("okf_version v0.1", {"okf_version": "v0.1", "zuno": {"status": "active"}}, None,
     "unsupported okf_version 'v0.1'"),
    ("okf_version 0.3 with zuno.profile 1.0", {"okf_version": "0.3", "zuno": {"profile": "1.0"}}, None,
     "unsupported okf_version '0.3'"),
    ("okf_version 1.0 with zuno.profile 1.0", {"okf_version": "1.0", "zuno": {"profile": "1.0"}}, None,
     "unsupported okf_version '1.0'"),
    ("integer okf_version", {"okf_version": 2}, None, "unsupported okf_version 2"),
    ("no okf_version", {"type": "agent"}, None, "missing okf_version"),
    ("null okf_version", {"okf_version": None}, None, "missing okf_version"),
    ("empty frontmatter", {}, None, "missing okf_version"),
    ("legacy v0.3 with zuno.profile", {"okf_version": "v0.3", "zuno": {"profile": "1.0"}}, None,
     ONLY_WITH_UPSTREAM),
    ("legacy v0.2 with zuno.profile", {"okf_version": "v0.2", "zuno": {"profile": "2.0"}}, None,
     ONLY_WITH_UPSTREAM),
]


def _load(name: str, path: pathlib.Path, extra_path: Optional[pathlib.Path] = None) -> types.ModuleType:
    """Import a hook by file path under a unique name: both gateways name their package `app`."""
    if extra_path is not None:
        sys.path.insert(0, str(extra_path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _stub_if_missing(name: str, **attributes) -> None:
    try:
        importlib.import_module(name)
    except ImportError:
        module = types.ModuleType(name)
        for key, value in attributes.items():
            setattr(module, key, value)
        sys.modules[name] = module


def _mlops() -> types.ModuleType:
    _stub_if_missing("boto3")
    _stub_if_missing("requests")
    _stub_if_missing("httpx")
    _stub_if_missing("botocore")
    _stub_if_missing("botocore.exceptions", ClientError=type("ClientError", (Exception,), {}))
    src = ROOT / "components" / "mlops" / "src"
    return _load("wp263_mlops", src / "mlops.py", extra_path=src)


def _ansible_expression() -> str:
    tasks = yaml.safe_load(ANSIBLE_CHECK.read_text(encoding="utf-8"))
    task = next(t for t in tasks if t.get("name") == ANSIBLE_TASK)
    return task["vars"]["_agents_okf_version_error"]


def python_hooks() -> Dict[str, Callable[[dict], str]]:
    """Repository path of each hook -> its okf_document_version."""
    supply_chain = ROOT / "platform" / "supply-chain"
    return {
        "platform/supply-chain/admit_okf_bundle.py": _load(
            "wp263_admit", supply_chain / "admit_okf_bundle.py", extra_path=supply_chain).okf_document_version,
        "platform/supply-chain/okf_narrowing.py": _load(
            "wp263_narrowing", supply_chain / "okf_narrowing.py").okf_document_version,
        "components/mcp-gateway/app/agent_declarations.py": _load(
            "wp263_mcp_gateway", ROOT / "components" / "mcp-gateway" / "app" / "agent_declarations.py"
        ).okf_document_version,
        "components/a2a-gateway/app/agent_declarations.py": _load(
            "wp263_a2a_gateway", ROOT / "components" / "a2a-gateway" / "app" / "agent_declarations.py"
        ).okf_document_version,
        "components/mlops/src/mlops.py": _mlops().okf_document_version,
        "evaluations/common/okf_release.py": _load(
            "wp263_evaluations", ROOT / "evaluations" / "common" / "okf_release.py").okf_document_version,
        "platform/docs/check_docs.py": _load(
            "wp263_check_docs", ROOT / "platform" / "docs" / "check_docs.py",
            extra_path=ROOT / "platform" / "docs").okf_document_version,
    }


# Hooks of check_okf_read_boundary.py that hold no copy of the rule, and why.
DELEGATING_HOOKS = {
    "platform/okf/generate_stack_config.py": "reads every document through admit_okf_bundle.checked_frontmatter",
    "platform/okf/release_cache.py": "verifies and extracts the release; parses no document",
}


def ansible_hook() -> Callable[[dict], str]:
    """The check.yml expression as a function: the accepted marker, or ValueError with its message."""
    import jinja2

    template = jinja2.Environment().from_string(_ansible_expression())

    def check(front: dict) -> str:
        error = template.render(catalog_okf={"key": "fixture", "value": front}).strip()
        if error:
            raise ValueError(error)
        return "accepted"

    return check


def outcome(hook: Callable[[dict], str], front: dict) -> Tuple[str, str]:
    try:
        return "accepted", hook(front)
    except ValueError as exc:
        return "refused", str(exc)


class DispatchTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.python = python_hooks()
        cls.ansible = staticmethod(ansible_hook())

    def test_every_hook_of_the_read_boundary_is_covered(self):
        """A hook added to check_okf_read_boundary.py must join this test or say why it holds no copy."""
        import check_okf_read_boundary

        self.assertEqual(set(check_okf_read_boundary.HOOKS), set(self.python) | set(DELEGATING_HOOKS))

    def test_every_python_hook_follows_the_table(self):
        for description, front, version, needle in TABLE:
            for name, hook in self.python.items():
                with self.subTest(row=description, hook=name):
                    state, detail = outcome(hook, dict(front))
                    if version is not None:
                        self.assertEqual((state, detail), ("accepted", version))
                    else:
                        self.assertEqual(state, "refused", detail)
                        self.assertIn(needle, detail)

    def test_the_ansible_check_follows_the_table(self):
        for description, front, version, needle in TABLE:
            with self.subTest(row=description):
                state, detail = outcome(self.ansible, dict(front))
                if version is not None:
                    self.assertEqual(state, "accepted", detail)
                else:
                    self.assertEqual(state, "refused")
                    self.assertIn(needle, detail)

    def test_every_hook_gives_the_same_answer(self):
        for description, front, _, _ in TABLE:
            with self.subTest(row=description):
                answers = {name: outcome(hook, dict(front))[0] for name, hook in self.python.items()}
                answers["ansible check.yml"] = outcome(self.ansible, dict(front))[0]
                self.assertEqual(len(set(answers.values())), 1, answers)


def _frontmatter(path: pathlib.Path) -> dict:
    parts = path.read_text(encoding="utf-8").split("---", 2)
    return (yaml.safe_load(parts[1]) or {}) if len(parts) == 3 and not parts[0].strip() else {}


class ConformanceDocuments(unittest.TestCase):
    """Every agent and task document of every conformance case gets the same answer from every hook,
    and the refusal cases of the dispatch rule are refused with the error their expected.json names."""

    def test_every_case_document_gets_the_same_answer(self):
        if CASES is None:
            self.skipTest(SKIP)
        hooks = dict(python_hooks(), **{"ansible check.yml": ansible_hook()})
        cases = sorted(p for p in CASES.iterdir() if p.is_dir())
        self.assertTrue(cases)
        for case in cases:
            expected = json.loads((case / "expected.json").read_text())["admission"]["error"]
            documents = sorted(case.glob("agents/*/agent.okf.md")) + sorted(case.glob("agents/*/tasks/*.md"))
            refusals: List[str] = []
            for document in documents:
                front = _frontmatter(document)
                with self.subTest(case=case.name, document=document.relative_to(case).as_posix()):
                    answers = {name: outcome(hook, dict(front)) for name, hook in hooks.items()}
                    self.assertEqual(len({state for state, _ in answers.values()}), 1, answers)
                    state, detail = answers["platform/supply-chain/admit_okf_bundle.py"]
                    if state == "refused":
                        refusals.append(detail)
            with self.subTest(case=case.name):
                if expected is None:
                    self.assertEqual(refusals, [])
                elif "okf_version" in expected or "zuno.profile" in expected:
                    self.assertTrue(any(expected in r for r in refusals), (expected, refusals))


if __name__ == "__main__":
    unittest.main()
