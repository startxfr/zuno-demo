"""Load the Blender add-on outside Blender (ADR-0610, WP-245).

The add-on imports bpy, bmesh and mathutils at module level. Its pure parts (endpoints, extract_code, check_script,
_stream_chat, _post) are what the unit tests, the golden-path probe and the prompt-set measurement reuse, so this
module installs minimal stand-ins for those three modules just long enough to import it, then restores sys.modules.
Nothing here can run a bpy script: that needs Blender (test_in_blender.py).
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import types

ADDON = pathlib.Path(__file__).resolve().parent / "zuno_3d_generator.py"
_STUBBED = ("bpy", "bmesh", "mathutils")


def _stub_bpy() -> types.ModuleType:
    class _Base:  # Operator, Panel and PropertyGroup are subclassed by the add-on
        pass

    def _prop(*_args, **_kwargs):
        return None

    bpy = types.ModuleType("bpy")
    bpy.types = types.SimpleNamespace(Operator=_Base, Panel=_Base, PropertyGroup=_Base,
                                      Scene=type("Scene", (), {}))
    bpy.props = types.SimpleNamespace(StringProperty=_prop, BoolProperty=_prop, PointerProperty=_prop)
    bpy.registered = []
    bpy.utils = types.SimpleNamespace(register_class=bpy.registered.append, unregister_class=bpy.registered.remove)
    bpy.app = types.SimpleNamespace(timers=types.SimpleNamespace(is_registered=lambda _f: False,
                                                                 register=lambda *_a, **_k: None,
                                                                 unregister=lambda _f: None))
    bpy.path = types.SimpleNamespace(abspath=lambda p: p)
    return bpy


def load_addon(path: pathlib.Path = ADDON) -> types.ModuleType:
    """Import the add-on with stand-in bpy/bmesh/mathutils, restoring sys.modules afterwards."""
    saved = {name: sys.modules.get(name) for name in _STUBBED}
    sys.modules["bpy"] = _stub_bpy()
    sys.modules["bmesh"] = types.ModuleType("bmesh")
    sys.modules["mathutils"] = types.ModuleType("mathutils")
    try:
        spec = importlib.util.spec_from_file_location("zuno_3d_generator", str(path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
