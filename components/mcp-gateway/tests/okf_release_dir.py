"""The admitted agents release these tests read the real agents and tool
policy from (ADR-0580, WP-165): agents/ and policies/tools/ left the
repository; platform/okf/release_cache.py extracts and verifies the release
pinned in platform/okf/agents.lock once (or ZUNO_OKF_RELEASE_DIR)."""
import pathlib
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "platform" / "okf"))

import release_cache  # noqa: E402

RELEASE_DIR = release_cache.release_dir()
AGENTS_DIR = str(RELEASE_DIR / "agents")
TOOL_POLICY_PATH = str(RELEASE_DIR / "policies" / "tools" / "tool-policy.yaml")
