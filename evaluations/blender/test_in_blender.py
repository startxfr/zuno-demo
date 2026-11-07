"""Runs INSIDE Blender (ADR-0610, WP-245): replay bpy scripts through the add-on's own Run operator.

    blender --background --factory-startup --python evaluations/blender/test_in_blender.py -- \
        evaluations/blender/zuno_3d_generator.py [--render-dir DIR] [script.py ...]

Registers the add-on, checks its operators, then runs each script in an empty scene through Run (static check, exec
as one undo step, all or nothing) and prints one `RESULT_JSON {...}` line per script: Blender's outcome, the objects,
modifiers and materials it built. With --render-dir, a successful script is rendered to <DIR>/<script>.png (Cycles on
the CPU, camera framed on the new objects) for a human look. With no script, runs a built-in sample and a script the
static check must refuse.
"""
import importlib.util
import json
import math
import os
import sys

import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
addon_path, rest = args[0], args[1:]
render_dir = None
if "--render-dir" in rest:
    i = rest.index("--render-dir")
    render_dir = rest[i + 1]
    rest = rest[:i] + rest[i + 2:]
scripts = rest

spec = importlib.util.spec_from_file_location("zuno_3d_generator", addon_path)
z = importlib.util.module_from_spec(spec)
spec.loader.exec_module(z)
z.register()
print("REGISTERED ops:", sorted(n for n in dir(bpy.ops.zuno3d) if not n.startswith("_")))

SAMPLE = '''import bpy
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.75))
top = bpy.context.active_object
top.name = "TableTop"
top.scale = (1.2, 0.7, 0.04)
top.modifiers.new("Bevel", "BEVEL")
for x in (-0.55, 0.55):
    for y in (-0.3, 0.3):
        bpy.ops.mesh.primitive_cylinder_add(radius=0.04, depth=0.7, location=(x, y, 0.35))
'''
REFUSED = "import os\nos.system('echo refused')\n"


def _empty_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def _render(names, path):
    """Frame the new objects with a camera and a sun, render a small Cycles CPU image."""
    objs = [bpy.data.objects[n] for n in names if bpy.data.objects[n].type in {"MESH", "CURVE", "SURFACE", "META", "FONT"}]
    if not objs:
        return False
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    center, size = (lo + hi) / 2, max((hi - lo).length, 0.5)
    cam = bpy.data.objects.new("ProbeCamera", bpy.data.cameras.new("ProbeCamera"))
    bpy.context.scene.collection.objects.link(cam)
    cam.location = center + Vector((1.0, -1.3, 0.8)).normalized() * size * 1.6
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    sun = bpy.data.objects.new("ProbeSun", bpy.data.lights.new("ProbeSun", "SUN"))
    sun.rotation_euler = (math.radians(50), 0, math.radians(30))
    bpy.context.scene.collection.objects.link(sun)
    scene = bpy.context.scene
    scene.camera = cam
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 16
    scene.render.resolution_x, scene.render.resolution_y = 480, 360
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    for helper in (cam, sun):
        bpy.data.objects.remove(helper, do_unlink=True)
    return True


def run_text(code, label):
    _empty_scene()
    text = bpy.data.texts.get(z.TEXT_NAME) or bpy.data.texts.new(z.TEXT_NAME)
    text.clear()
    text.write(z.extract_code(code))
    problems = z.check_script(text.as_string())
    try:
        outcome, error = sorted(bpy.ops.zuno3d.run())[0], ""
    except RuntimeError as exc:  # the operator's ERROR report surfaces as a RuntimeError in background mode
        outcome, error = "CANCELLED", str(exc).strip().splitlines()[-1][:200]
    names = sorted(o.name for o in bpy.data.objects)
    result = {"script": label, "outcome": outcome, "error": error, "check": problems[:3],
              "objects": len(names),
              "modifiers": sum(len(bpy.data.objects[n].modifiers) for n in names),
              "materials": len({m.name for n in names for m in getattr(bpy.data.objects[n].data, "materials", []) or []
                                if m is not None}),
              "names": names[:8], "render": ""}
    if render_dir and outcome == "FINISHED" and names:
        os.makedirs(render_dir, exist_ok=True)
        path = os.path.join(os.path.abspath(render_dir), os.path.splitext(label)[0] + ".png")
        if _render(names, path):
            result["render"] = path
    print("RESULT_JSON " + json.dumps(result), flush=True)


if scripts:
    for path in scripts:
        with open(path, encoding="utf-8") as fh:
            run_text(fh.read(), os.path.basename(path))
else:
    run_text(SAMPLE, "sample-table.py")
    run_text(REFUSED, "refused-os.py")
z.unregister()
print("UNREGISTERED ok")
