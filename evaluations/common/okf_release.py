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
