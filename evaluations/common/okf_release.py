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


# ADR-0508 clause 3 / ADR-0615 clause 5: the versions the evaluations read.
# Profile 1.0 is okf_version "0.2" (upstream OKF, a quoted string) plus
# zuno.profile "1.0"; the legacy okf_version values v0.2 and v0.3 carry no
# zuno.profile and stay readable until WP-268 removes them. This module is their
# OKF hook: every check reads an agent's declarations through the functions
# below, never from the files directly. It keeps its own copy of the rule
# (ADR-0508 clause 4); platform/okf/tests/test_okf_version_dispatch.py checks
# that every copy accepts and refuses the same documents.
UPSTREAM_OKF_VERSION = "0.2"
ZUNO_PROFILES = ("1.0",)
LEGACY_OKF_VERSIONS = ("v0.2", "v0.3")
SUPPORTED_OKF_VERSIONS_TEXT = (f'okf_version "{UPSTREAM_OKF_VERSION}" with zuno.profile '
                               f'{", ".join(ZUNO_PROFILES)}, or legacy {", ".join(LEGACY_OKF_VERSIONS)}')


def okf_document_version(front: dict) -> str:
    """The version a document's frontmatter follows: "v0.2" or "v0.3" (legacy)
    or "1.0" (profile). ValueError, naming the cause, for any other pair."""
    version = front.get("okf_version")
    zuno = front.get("zuno")
    profile = zuno.get("profile") if isinstance(zuno, dict) else None
    if version is None:
        raise ValueError(f"missing okf_version (supported: {SUPPORTED_OKF_VERSIONS_TEXT})")
    if isinstance(version, str) and version in LEGACY_OKF_VERSIONS:
        if profile is not None:
            raise ValueError(f'zuno.profile is only valid with okf_version "{UPSTREAM_OKF_VERSION}" '
                             f"(this document says okf_version {version!r})")
        return version
    if isinstance(version, str) and version == UPSTREAM_OKF_VERSION:
        if isinstance(profile, str) and profile in ZUNO_PROFILES:
            return profile
        raise ValueError(f"unsupported zuno.profile {profile!r} (supported: {', '.join(ZUNO_PROFILES)})")
    raise ValueError(f"unsupported okf_version {version!r} (supported: {SUPPORTED_OKF_VERSIONS_TEXT})")


def read_document(path: pathlib.Path) -> dict:
    """Frontmatter of an OKF document, refused by name when it has no
    frontmatter block or an unsupported (or missing) version."""
    import yaml

    parts = path.read_text(encoding="utf-8").split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"{path}: expected a leading '---' YAML frontmatter block")
    front = yaml.safe_load(parts[1]) or {}
    try:
        okf_document_version(front)
    except ValueError as exc:
        raise ValueError(f"{path}: {exc}") from None
    return front


def has_agent(root: pathlib.Path, agent: str) -> bool:
    """Whether `root` holds this agent's bundle (for callers that search several layouts)."""
    return (root / "agents" / agent / "agent.okf.md").is_file()


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

