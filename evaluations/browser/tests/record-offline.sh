#!/usr/bin/env bash
# WP-284: the offline test of the recorder. Runs record.mjs with walkthroughs/open-webui.mjs in the Playwright image
# against tests/fake-open-webui.mjs, inside the container: no cluster, no `oc`, no persona password, no model call.
# It proves the recorder's own work (video, markers, PNGs, markers.json, exit codes, the chat deleted by its id, a
# refused delete failing the take with the chat's title, a chat whose id was never read reported and not silent), not
# Open WebUI's real selectors. The first case is the scout: a sign-in and the menus, no prompt, no chat, no video. The last case waits out the walkthrough's 60 s for the address bar.
#   evaluations/browser/tests/record-offline.sh
set -uo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
failed=0
take() {   # take <name> <FAKE_REFUSE_DELETE> [FAKE_NO_URL] [RECORD_SCOUT]: prints the recorder's output, returns its exit code
  mkdir -p "$work/$1"
  podman run --rm -e DEMO=open-webui -e APPS_DOMAIN=fake.invalid -e PERSONA_PASSWORD=offline-test -e OUT=/out \
    -e RECORD_BASE_URL=http://127.0.0.1:8099 -e FAKE_REFUSE_DELETE="$2" -e FAKE_NO_URL="${3:-0}" -e RECORD_SCOUT="${4:-0}" \
    -v "$here:/work:Z" -v "$work/$1:/out:Z" -w /work mcr.microsoft.com/playwright:v1.48.0-jammy \
    sh -c 'npm install --no-audit --no-fund --silent >/dev/null 2>&1; node tests/fake-open-webui.mjs >/dev/null & sleep 1; node record.mjs; rc=$?; echo "chats left: $(curl -s http://127.0.0.1:8099/fake/count)"; exit $rc'
}
expect() {   # expect <what> <command...>
  if "${@:2}"; then echo "ok    $1"; else echo "FAIL  $1"; failed=1; fi
}
out="$(take scout 0 0 1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "a scout exits 0" test "$rc" -eq 0
expect "its last recorder line is SCOUT: done" grep -q '^SCOUT: done$' <<<"$out"
expect "a scout creates no chat and clicks no tool switch" grep -q 'chats left: {"chats":0,"toggled":0}' <<<"$out"
expect "a scout leaves no video and no markers.json" bash -c "! ls '$work/scout' | grep -q -E '\.webm$|^markers\.json$'"
expect "scout.json names the selectors and what each menu showed" python3 - "$work/scout" <<'PY'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1]); s = json.loads((d / "scout.json").read_text())
steps = {x["step"]: x for x in s["steps"]}
assert list(steps) == ["home", "picker", "tools", "closed"], list(steps)
assert s["status"] == "done" and all(x["ok"] for x in s["steps"]) and s["refused_requests"] == [], s
assert all((d / x["png"]).stat().st_size > 0 for x in s["steps"])
assert steps["home"]["chat_link_on_screen"] is False
near = steps["home"]["buttons"]["near"] + steps["home"]["buttons"]["elsewhere"]
assert any(b["aria"] == "Integrations" for b in near) and any(b["id"] == "model-selector-model-button" for b in near), near
assert steps["picker"]["selector"] == "#model-selector-model-button" and steps["picker"]["label"] == "Zuno"
assert steps["picker"]["zuno_code_listed"] is True and "Zuno Code" in steps["picker"]["text"]
assert steps["tools"]["selector"] == "#integration-menu-button" and steps["tools"]["connection_listed"] is True
assert steps["tools"]["row_selector"].startswith("[role='menu'] [role='menuitem']"), steps["tools"]
assert steps["tools"]["switches"] == [{"label": "Zuno tools", "on": True}], steps["tools"]["switches"]
assert not any(steps["tools"]["tool_words_on_screen"].values())
assert steps["closed"]["menu_still_open"] is False
PY
out="$(take pass 0)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "a good take exits 0" test "$rc" -eq 0
expect "its last recorder line is RESULT: PASS" grep -q '^RESULT: PASS$' <<<"$out"
expect "the chat it created is gone and no tool switch was clicked" grep -q 'chats left: {"chats":0,"toggled":0}' <<<"$out"
expect "recording.webm is there and not empty" test -s "$work/pass/recording.webm"
expect "exactly one webm" test "$(ls "$work/pass" | grep -c '\.webm$')" -eq 1
expect "markers.json follows the contract" python3 - "$work/pass" <<'PY'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1]); m = json.loads((d / "markers.json").read_text())
names = [x["name"] for x in m["markers"]]
assert names == ["login", "home", "q1-sent", "q1-done", "code-picked", "q2-done", "tools", "end"], names
ts = [x["t"] for x in m["markers"]]
assert ts == sorted(ts) and all(isinstance(t, (int, float)) for t in ts), ts
assert all((d / x["png"]).stat().st_size > 0 and x["png"] == x["name"] + ".png" for x in m["markers"])
assert m["demo"] == "open-webui" and m["persona"] == "sale-01" and m["viewport"] == {"width": 1280, "height": 800}
assert m["status"] == "pass" and m["chat_deleted"] is True and m["started"].endswith("Z"), m
assert m["motion_from"] == "q1-sent" and m["motion_from"] in names, m
home = [x["t"] for x in m["markers"] if x["name"] == "home"][0]
assert home >= 2.5, f"home marked at {home} s, before the sign-in toast was gone"
PY
out="$(take refused 1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "a refused delete exits 1" test "$rc" -eq 1
expect "it names the chat by its title" grep -q '^RESULT: FAIL .*the chat "Fake chat about In one short sentenc" .*was NOT deleted' <<<"$out"
expect "markers.json says fail, chat not deleted, all markers kept" python3 - "$work/refused" <<'PY'
import json, pathlib, sys
m = json.loads((pathlib.Path(sys.argv[1]) / "markers.json").read_text())
assert m["status"] == "fail" and m["chat_deleted"] is False and len(m["markers"]) == 8, m
PY
out="$(take noid 0 1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "a chat whose id was never read exits 1" test "$rc" -eq 1
expect "it says a chat may remain, with the prompt as its title" grep -q '^RESULT: FAIL .*a chat titled like "In one short sentence, say what you can help me with." may remain' <<<"$out"
expect "markers.json says fail, chat not deleted, stopped after q1-sent" python3 - "$work/noid" <<'PY'
import json, pathlib, sys
m = json.loads((pathlib.Path(sys.argv[1]) / "markers.json").read_text())
assert m["status"] == "fail" and m["chat_deleted"] is False, m
assert [x["name"] for x in m["markers"]] == ["login", "home", "q1-sent"], m
PY
expect "the password is in no file of the take" bash -c "! grep -r -l offline-test '$work' >/dev/null"
[[ $failed -eq 0 ]] && echo "RESULT: PASS" || echo "RESULT: FAIL"
exit $failed
