# Blender workstation client (ADR-0610)

The Blender add-on, its test harness and the prompt-set measurement of
[ADR-0610](../../docs/adr/0610-generate-blender-objects-as-bpy-scripts-from-a-local-model-through-the-ai-gateway.md)
([WP-244](../../docs/roadmap/work-packages/wp-244-blender-workstation-experience-client.md),
[WP-245](../../docs/roadmap/work-packages/wp-245-blender-prompt-set-and-golden-path-probe.md)). Demonstration script:
[docs/demo/blender-3d.md](../../docs/demo/blender-3d.md).

| File | What it is |
|---|---|
| `zuno_3d_generator.py` | The add-on. Install it in Blender (below). |
| `bpy_stub.py` | Loads the add-on outside Blender (stand-in `bpy`), for the tests, the probe and the measurement. |
| `device_login.py` | A device sign-in of the public client `blender` with no human, as an evaluation persona. |
| `test_in_blender.py` | Runs inside headless Blender: replays scripts through the add-on's **Run**, optionally renders them. |
| `measure_prompts.py`, `prompts.json` | The clause 8 measurement: every prompt through the real entry, replayed in Blender. |
| `results/` | Dated measurement summaries (no token, no script text). |

## Install the add-on

1. Blender 4.2 LTS (4.0 or newer works).
2. Download `zuno_3d_generator.py` (on GitHub: this file, **Raw**, save as).
3. **Edit > Preferences > Add-ons**, the menu at the top right, **Install from Disk**, pick the file, tick
   **Zuno 3D generator (demo)**.
4. In the 3D Viewport press **N**, tab **Zuno 3D**. **Cluster domain** defaults to `apps.demo333.startx.fr`.
5. **Sign in**, then **Open sign-in page**: sign in in the browser as a member of the admitted group (demo333:
   `ocp-ai-dev`, persona **ai-dev-01**). If the browser already holds another Keycloak session, sign out first
   (`https://keycloak.<domain>/realms/zuno/protocol/openid-connect/logout`).
6. Type a prompt, **Generate script** (about 10 s), read the script in the Text Editor (`zuno_3d_script.py`),
   **Run script**. A script that fails keeps nothing.

## Tests

```bash
python3 evaluations/tests/test_blender_addon.py     # static check, SSE parsing, device sign-in helpers
python3 evaluations/tests/test_blender_measure.py   # how a measured run is judged
blender --background --factory-startup --python evaluations/blender/test_in_blender.py -- \
    evaluations/blender/zuno_3d_generator.py --render-dir /tmp/renders   # a sample built, a script refused
```

The golden-path moment `blender` (`evaluations/golden_path_probe.py`, `make demo golden-path ONLY=blender`) checks
the live chain end to end with the persona `eval-ai-dev-01`.

## Measure the prompt set

```bash
python3 evaluations/blender/measure_prompts.py --blender /path/to/blender --render \
    --results evaluations/blender/results/prompt-set-gpt-oss-20b-$(date +%F).json
```

Needs `oc` logged in (the evaluation persona's password is read from `zuno-ai-run/acceptance-gate-credentials`).
Each prompt runs twice; a prompt is **stage-ready** when both runs build a scene.
