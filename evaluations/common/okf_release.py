"""Where the evaluations read agent definitions and corp policies (ADR-0580, WP-165).

Agents (`agents/<name>/...`) and the corp policies (`policies/tools/`,
`policies/model-routing/`, ...) left this repository for the
startxfr/zuno-demo-agents release pinned in platform/okf/agents.lock. The
platform's own policies (`policies/data-classification/`, ...) stay here.

`okf_root(repo_root)` returns the directory under which `agents/` and the
corp `policies/` are found, for the three places these scripts run:

- ZUNO_OKF_RELEASE_DIR, when set: an extracted release, used as is;
- a checkout (platform/okf/agents.lock exists under repo_root): the
  release extracted and verified once by platform/okf/release_cache.py;
- otherwise the layout of the acceptance-gate and stresstest Jobs and of the
  mlops image, which place the release's files under repo_root itself.
"""
from __future__ import annotations

import os
import pathlib
import sys


def okf_root(repo_root: pathlib.Path) -> pathlib.Path:
    override = os.environ.get("ZUNO_OKF_RELEASE_DIR")
    if override:
        return pathlib.Path(override)
    if (repo_root / "platform" / "okf" / "agents.lock").is_file():
        sys.path.insert(0, str(repo_root / "platform" / "okf"))
        import release_cache  # noqa: E402

        return release_cache.release_dir()
    return repo_root


# ADR-0508 clause 3 / ADR-0579 clause 6: the OKF schema versions the evaluations
# read. This module is their OKF hook: every check reads an agent's declarations
# through the functions below, never from the files directly.
SUPPORTED_OKF_VERSIONS = ("v0.2", "v0.3")


def read_document(path: pathlib.Path) -> dict:
    """Frontmatter of an OKF document, refused by name when it has no
    frontmatter block or an unsupported (or missing) okf_version."""
    import yaml

    parts = path.read_text(encoding="utf-8").split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"{path}: expected a leading '---' YAML frontmatter block")
    front = yaml.safe_load(parts[1]) or {}
    version = front.get("okf_version")
    supported = ", ".join(SUPPORTED_OKF_VERSIONS)
    if version is None:
        raise ValueError(f"{path}: missing okf_version (supported: {supported})")
    if version not in SUPPORTED_OKF_VERSIONS:
        raise ValueError(f"{path}: unsupported okf_version {version!r} (supported: {supported})")
    return front


def agent_declaration(root: pathlib.Path, agent: str) -> dict:
    """The `zuno` block of agents/<agent>/agent.okf.md."""
    return read_document(root / "agents" / agent / "agent.okf.md").get("zuno") or {}


def task_declarations(root: pathlib.Path, agent: str) -> dict:
    """task name -> the `zuno` block of its task document, for every task the
    agent lists and every task file beside them. A listed task whose file is
    missing is an error, not a skip."""
    tasks_dir = root / "agents" / agent / "tasks"
    names = set(agent_declaration(root, agent).get("tasks") or [])
    if tasks_dir.is_dir():
        names |= {p.stem for p in tasks_dir.glob("*.md")}
    return {name: read_document(tasks_dir / f"{name}.md").get("zuno") or {} for name in sorted(names)}

