#!/usr/bin/env bash
# WP-287: the offline test of the terminal chain (ADR-0618 clauses 3 and 6). A real session of harmless commands is
# captured by terminal/capture.py on this host, then record.sh --terminal replays it in the vendored xterm.js inside
# the Playwright image, without a network, and films it. No cluster, no `oc`, no password.
#   evaluations/browser/tests/terminal-offline.sh
set -uo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
failed=0
expect() {   # expect <what> <command...>
  if "${@:2}"; then echo "ok    $1"; else echo "FAIL  $1"; failed=1; fi
}
expect "the vendored xterm.js files are the pinned ones" bash -c "cd '$here/terminal/vendor/xterm-6.0.0' && sha256sum --quiet -c SHA256SUMS"
expect "the replay page loads nothing from a network" bash -c "! grep -E 'https?://' '$here/terminal/replay.html'"

mkdir -p "$work/take" "$work/home"
python3 - "$here" "$work" <<'PY' || { echo "FAIL  the fixture session could not be captured"; exit 1; }
import pathlib, sys
here, work = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
sys.path.insert(0, str(here / "terminal"))
import capture
rows = [capture.Step("0:00", [capture.Command('echo "Vault is unsealed"')]),
        capture.Step("1:00", [capture.Command("seq 1 40"), capture.Command(r"printf '\033[32mgreen\033[0m and plain\n'")]),
        capture.Step("2:15", [capture.Command("echo " + " ".join(f"word{n:02d}" for n in range(1, 26)))])]
env = capture.clean_env("", {}, str(work / "home"))
passed, detail = capture.capture("fixture", rows, work / "take", env, [], cwd=work / "home")
sys.exit(0 if passed else 1)
PY
out="$(RECORD_TERMINAL_DUMP=1 "$here/record.sh" fixture "$work/take" --terminal 2>&1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "a terminal take exits 0" test "$rc" -eq 0
expect "its first line is the directory, its last RESULT: PASS" bash -c "head -1 <<<\"\$1\" | grep -q '^recording: ' && tail -1 <<<\"\$1\" | grep -q '^RESULT: PASS\$'" _ "$out"
expect "recording.webm is there, exactly one" test -s "$work/take/recording.webm" -a "$(ls "$work/take" | grep -c '\.webm$')" -eq 1
expect "markers.json: the rows' typed and done instants, at the session's own timing" python3 - "$work/take" <<'PY'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1]); m = json.loads((d / "markers.json").read_text()); s = json.loads((d / "terminal-steps.json").read_text())
names = [x["name"] for x in m["markers"]]
assert names == ["start", "00-00-typed", "00-00-done", "01-00-typed", "01-00-done", "02-15-typed", "02-15-done", "end"], names
ts = {x["name"]: x["t"] for x in m["markers"]}
assert list(ts.values()) == sorted(ts.values())
assert all((d / x["png"]).stat().st_size > 2000 for x in m["markers"])
assert m["status"] == "pass" and m["demo"] == "fixture" and m["motion_from"] == "start" and m["persona"] == ""
assert m["kind"] == "terminal" and m["created"] == [] and m["cleaned"] is None and m["owned"] is None
assert m["terminal"]["cols"] == 100 and m["terminal"]["rows"] == 30 and len(m["terminal"]["cast_sha256"]) == 64
assert m["terminal"]["font_px"] == 20 and m["viewport"] == {"width": 1232, "height": 808}, (m["terminal"], m["viewport"])
# Real timing: the video's distance between two markers is the session's own, plus the holds while images were saved.
first, last = s["steps"][0], s["steps"][-1]
session = last["done"] - first["typed"]
video = ts["02-15-done"] - ts["00-00-typed"]
held = m["terminal"]["held_seconds"]
assert 0 < held < 20 and session - 0.3 <= video <= session + held + 0.3, (video, session, held)
PY
expect "the screen at each marker is what the session showed" python3 - "$work/take" <<'PY'
import pathlib, sys
d = pathlib.Path(sys.argv[1])
def screen(name):
    return [l.rstrip() for l in (d / f"screen-{name}.txt").read_text().split("\n")]
def last(rows):
    return [r for r in rows if r][-1]
assert last(screen("start")) == "$", screen("start")[:3]
assert last(screen("00-00-typed")) == '$ echo "Vault is unsealed"', last(screen("00-00-typed"))
done = [r for r in screen("00-00-done") if r]
assert done[-2:] == ["Vault is unsealed", "$"], done
typed = [r for r in screen("01-00-typed") if r]
assert typed == ["$ seq 1 40"], typed            # Ctrl-L cleared the screen between the two rows
rows = [r for r in screen("01-00-done") if r]
assert rows[-2:] == ["green and plain", "$"] and "40" in rows and "1" not in rows, rows[-6:]   # 40 lines scrolled a 30-row window
wrapped = [r for r in screen("02-15-typed") if r]
assert len(wrapped) == 2 and len(wrapped[0]) == 100 and wrapped[0].startswith("$ echo word01"), wrapped   # a long line wraps at 100 columns
assert all(len(r) <= 100 for name in ("01-00-done", "02-15-done") for r in screen(name))
PY
expect "no credential and no host path went into the container's files" bash -c "! grep -r -l -E 'KUBECONFIG|$HOME' '$work/take' >/dev/null"

# A wide table: the demo asks for a wider window (demo.yml `record: {cols, rows}`), the commands stay as they are.
mkdir -p "$work/wide"
python3 - "$here" "$work" <<'PY' || { echo "FAIL  the wide fixture session could not be captured"; exit 1; }
import pathlib, sys
here, work = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
sys.path.insert(0, str(here / "terminal"))
import capture
line = "NAME" + " " * 60 + "READY   STATUS    VAULT-SEALED   VAULT-ACTIVE   VAULT-VERSION".ljust(70)   # 134 columns
rows = [capture.Step("0:00", [capture.Command(f"printf '%s|\\n' '{line}'"), capture.Command("stty size")])]
passed, detail = capture.capture("fixture", rows, work / "wide", capture.clean_env("", {}, str(work / "home")), [],
                                 cwd=work / "home", cols=136, rows=24)
sys.exit(0 if passed else 1)
PY
out="$(RECORD_TERMINAL_DUMP=1 "$here/record.sh" fixture "$work/wide" --terminal 2>&1)"; rc=$?
echo "$out" | tail -1 | sed 's/^/    /'
expect "a 136x24 take exits 0" test "$rc" -eq 0
expect "the wide table is on one line, the picture follows the window and stays wider than the GIF" python3 - "$work/wide" <<'PY'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1]); m = json.loads((d / "markers.json").read_text())
rows = [r.rstrip() for r in (d / "screen-00-00-done.txt").read_text().split("\n") if r.strip()]
table = [r for r in rows if r.startswith("NAME")]
assert len(table) == 1 and len(table[0]) == 135 and table[0].endswith("|"), [len(r) for r in rows]
assert "24 136" in rows, rows
assert m["terminal"]["cols"] == 136 and m["terminal"]["rows"] == 24 and m["terminal"]["font_px"] == 15, m["terminal"]
assert 960 <= m["viewport"]["width"] <= 1300 and m["viewport"]["height"] < 808, m["viewport"]
cast = json.loads((d / "terminal.cast").read_text().splitlines()[0])
assert (cast["width"], cast["height"]) == (136, 24), cast
PY

rm -f "$work/take/terminal.cast"
out="$("$here/record.sh" fixture "$work/take" --terminal 2>&1)"; rc=$?
expect "without a cast the take is a usage error (exit 2)" test "$rc" -eq 2
[[ $failed -eq 0 ]] && echo "RESULT: PASS" || echo "RESULT: FAIL"
exit $failed
