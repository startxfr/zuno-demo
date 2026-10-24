"""Compatibility re-export: the UnifAI evaluation transport now lives in
evaluations/common/unifai_target.py and is shared by every agent (WP-155
wave 0). Importing `unifai_target` from evaluations/tekos keeps working."""
from __future__ import annotations

import importlib.util
import pathlib
import sys

_PATH = pathlib.Path(__file__).resolve().parent.parent / "common" / "unifai_target.py"
_NAME = "zuno_eval_common_unifai_target"

if _NAME not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_NAME, _PATH)
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules[_NAME] = _mod  # needed by @dataclass before exec completes
    _spec.loader.exec_module(_mod)

_shared = sys.modules[_NAME]
UnifaiError = _shared.UnifaiError
UnifaiRun = _shared.UnifaiRun
UnifaiTarget = _shared.UnifaiTarget
UNIFAI_URL = _shared.UNIFAI_URL
VERIFY_TLS = _shared.VERIFY_TLS
wanted_tools = _shared.wanted_tools
routing_of = _shared.routing_of
login_name = _shared.login_name
tempo_rag_searches = _shared.tempo_rag_searches
