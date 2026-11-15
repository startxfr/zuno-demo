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

rm -f "$work/take/terminal.cast"
out="$("$here/record.sh" fixture "$work/take" --terminal 2>&1)"; rc=$?
expect "without a cast the take is a usage error (exit 2)" test "$rc" -eq 2
[[ $failed -eq 0 ]] && echo "RESULT: PASS" || echo "RESULT: FAIL"
exit $failed
