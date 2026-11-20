"""Smoke tests of the components that have no tests of their own: they exist, they parse, and what their images copy is in the repository.

  - every COPY/ADD source of every components/**/Dockerfile and Containerfile exists (relative to the repository root, where most images are built,
    or to the Dockerfile's own directory, the context of the MCP server images): a renamed file would break the build only at the
    next release;
  - components/trustyai-eval/ragas_eval.py compiles, and its requirements are pinned with hashes;
  - components/aap-execution-environment/execution-environment.yml is a version 3 ansible-builder definition;
  - the planned MCP servers without code (google-workspace, lucidchart, web-search) say so in a README, and hold nothing else.

Run from the repository root:
    python3 platform/testing/tests/test_components_smoke.py
"""
from __future__ import annotations

import pathlib
import py_compile
import re
import tempfile
import unittest

import yaml

REPO = pathlib.Path(__file__).resolve().parents[3]
COMPONENTS = REPO / "components"


def dockerfiles():
    found = list(COMPONENTS.rglob("Dockerfile")) + list(COMPONENTS.rglob("Containerfile"))
    return sorted(p for p in found if "node_modules" not in p.parts)


def copy_sources(dockerfile: pathlib.Path):
    """The local sources of the COPY/ADD lines (a `--from=` stage copy and a URL are not local)."""
    text = re.sub(r"\\\n", " ", dockerfile.read_text())
    for line in text.splitlines():
        match = re.match(r"\s*(?:COPY|ADD)\s+(.*)", line, re.I)
        if not match:
            continue
        words = match.group(1).split()
        flags = [w for w in words if w.startswith("--")]
        if any(f.startswith("--from=") for f in flags) or any("://" in w for w in words):
            continue
        args = [w for w in words if not w.startswith("--")]
        if args and args[0].startswith("["):
            continue  # JSON form: not used by this repository's images
        yield from args[:-1]


class DockerfileSources(unittest.TestCase):
    def test_there_are_dockerfiles(self):
        self.assertGreaterEqual(len(dockerfiles()), 12)

    def test_every_copy_source_exists(self):
        problems = []
        for dockerfile in dockerfiles():
            for source in copy_sources(dockerfile):
                if "$" in source:
                    continue  # a build argument: not resolvable here
                candidates = [REPO / source, dockerfile.parent / source]
                pattern = source.rstrip("/")
                if not any(c.exists() or (any(ch in pattern for ch in "*?[") and list(c.parent.glob(c.name))) for c in candidates):
                    problems.append(f"{dockerfile.relative_to(REPO)}: COPY {source}")
        self.assertEqual(problems, [])


class DockerIgnore(unittest.TestCase):
    def test_the_root_dockerignore_excludes_nothing_an_image_copies(self):
        ignored = {line.strip().rstrip("/") for line in (REPO / ".dockerignore").read_text().splitlines()
                   if line.strip() and not line.startswith("#")}
        copied = set()
        for dockerfile in dockerfiles():
            for source in copy_sources(dockerfile):
                if (REPO / source).exists():  # built from the repository root
                    copied.add(source.rstrip("/"))
        clashes = sorted(c for c in copied for i in ignored if not i.startswith("**") and (c == i or c.startswith(i + "/")))
        self.assertEqual(clashes, [])
        self.assertIn("evaluations", {c.split("/")[0] for c in copied}, "the mlops Containerfile copies evaluations/: it must stay buildable")


class TrustyaiEval(unittest.TestCase):
    DIR = COMPONENTS / "trustyai-eval"

    def test_the_script_compiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            py_compile.compile(str(self.DIR / "ragas_eval.py"), cfile=str(pathlib.Path(tmp) / "x.pyc"), doraise=True)

    def test_requirements_are_pinned_with_hashes(self):
        text = (self.DIR / "requirements.txt").read_text()
        pins = re.findall(r"^[A-Za-z0-9_.\[\]-]+==", text, re.M)
        self.assertTrue(pins)
        self.assertGreaterEqual(len(re.findall(r"--hash=sha256:", text)), len(pins))


class ExecutionEnvironment(unittest.TestCase):
    def test_it_is_a_version_3_definition_with_a_base_image(self):
        definition = yaml.safe_load((COMPONENTS / "aap-execution-environment" / "execution-environment.yml").read_text())
        self.assertEqual(definition["version"], 3)
        self.assertTrue(definition["images"]["base_image"]["name"])


class PlannedServers(unittest.TestCase):
    def test_a_server_without_code_is_only_a_readme(self):
        for name in ("google-workspace", "lucidchart", "web-search"):
            files = sorted(p.name for p in (COMPONENTS / "mcp-servers" / name).iterdir())
            self.assertEqual(files, ["README.md"], f"{name} now holds code: give it tests and remove it from this list")


if __name__ == "__main__":
    unittest.main()
