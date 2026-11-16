#!/usr/bin/env bash
# WP-284: the offline test of the recorder. Runs record.mjs with walkthroughs/open-webui.mjs in the Playwright image
# against tests/fake-open-webui.mjs, inside the container: no cluster, no `oc`, no persona password, no model call.
# It proves the recorder's own work (video, markers, PNGs, markers.json, exit codes, the chat deleted by its id, a
# refused delete failing the take with the chat's title, a chat whose id was never read reported and not silent, a
# refused model call failing at once, the persona's items compared before and after, the click guard), not
# Open WebUI's real selectors. The first case is the scout: a sign-in and the menus, no prompt, no chat, no video. The last case waits out the walkthrough's 60 s for the address bar.
#   evaluations/browser/tests/record-offline.sh
set -uo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
failed=0
take() {   # take <name> [VAR=1 ...]: one recorder run with these knobs set; prints its output, returns its exit code
  mkdir -p "$work/$1"
  local knobs=()
  for knob in "${@:2}"; do knobs+=(-e "$knob"); done
  podman run --rm -e DEMO=open-webui -e APPS_DOMAIN=fake.invalid -e PERSONA_PASSWORD=offline-test -e OUT=/out \
    -e RECORD_BASE_URL=http://127.0.0.1:8099 "${knobs[@]+"${knobs[@]}"}" \
    -v "$here:/work:Z" -v "$work/$1:/out:Z" -w /work mcr.microsoft.com/playwright:v1.48.0-jammy \
    sh -c 'npm install --no-audit --no-fund --silent >/dev/null 2>&1; node tests/fake-open-webui.mjs >/dev/null & sleep 1; node record.mjs; rc=$?; echo "chats left: $(curl -s http://127.0.0.1:8099/fake/count)"; exit $rc'
}
expect() {   # expect <what> <command...>
  if "${@:2}"; then echo "ok    $1"; else echo "FAIL  $1"; failed=1; fi
}
out="$(take scout RECORD_SCOUT=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "a scout exits 0" test "$rc" -eq 0
expect "its last recorder line is SCOUT: done" grep -q '^SCOUT: done$' <<<"$out"
expect "a scout creates no chat and clicks no tool switch" grep -q 'chats left: {"chats":0,"toggled":0}' <<<"$out"
expect "a scout leaves no video and no markers.json" bash -c "! ls '$work/scout' | grep -q -E '\.webm$|^markers\.json$'"
expect "scout.json names the selectors, the elements and the walkthrough's hash" python3 - "$work/scout" "$here" <<'PY'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1]); s = json.loads((d / "scout.json").read_text())
steps = {x["step"]: x for x in s["steps"]}
assert list(steps) == ["enter", "owned", "home", "picker", "tools", "closed"], list(steps)
assert steps["owned"]["count"] == 1 and len(s["walkthrough_sha256"]) == 64, s
assert any(el["role"] == "switch" and el["attrs"].get("aria-checked") == "true" for el in steps["tools"]["menu"]), steps["tools"]["menu"]
assert any(el["text"] == "Zuno Code" for el in steps["picker"]["added"]), steps["picker"]["added"]
assert s["status"] == "done" and all(x["ok"] for x in s["steps"]) and s["refused_requests"] == [], s
assert all((d / x["png"]).stat().st_size > 0 for x in s["steps"])
import subprocess
here = pathlib.Path(sys.argv[2])
check = json.loads(subprocess.run(["node", str(here / "record.mjs"), "--check", "open-webui", "--json"], check=True, capture_output=True, text=True).stdout)
assert check["walkthrough_sha256"] == s["walkthrough_sha256"] and check["changes"] == [] and check["motion_from"] == "home", check
import hashlib
h = hashlib.sha256()
for rel in ("evaluations/browser/walkthroughs/_helpers.mjs", "evaluations/browser/walkthroughs/open-webui.mjs"):
    h.update(rel.encode() + b"\0" + (here.parents[1] / rel).read_bytes() + b"\0")
assert h.hexdigest() == s["walkthrough_sha256"], "the hash is not the one Python computes from the two files"
assert s["changes"] == [] and s["when"].endswith("Z") and s["when"] >= s["started"], s
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
out="$(take pass)"; rc=$?
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
assert m["kind"] == "browser" and m["demo"] == "open-webui" and m["persona"] == "sale-01" and m["viewport"] == {"width": 1280, "height": 800}
assert m["status"] == "pass" and m["started"].endswith("Z") and "chat_deleted" not in m, m
assert len(m["created"]) == 1 and m["created"][0]["kind"] == "chat" and set(m["created"][0]) == {"kind", "id"}, m["created"]
assert m["cleaned"] is True and m["owned"] == {"before": 1, "after": 1, "same": True}, m
assert m["motion_from"] == "home" and m["motion_from"] in names, m
home = [x["t"] for x in m["markers"] if x["name"] == "home"][0]
assert home >= 2.5, f"home marked at {home} s, before the sign-in toast was gone"
PY
out="$(take refused FAKE_REFUSE_DELETE=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "a refused delete exits 1" test "$rc" -eq 1
expect "it names the chat by its title" grep -q '^RESULT: FAIL .*the chat "Fake chat about In one short sentenc" .*was NOT deleted' <<<"$out"
expect "markers.json says fail, chat not deleted, all markers kept" python3 - "$work/refused" <<'PY'
import json, pathlib, sys
m = json.loads((pathlib.Path(sys.argv[1]) / "markers.json").read_text())
assert m["status"] == "fail" and m["cleaned"] is False and len(m["created"]) == 1 and len(m["markers"]) == 8, m
assert m["owned"] == {"before": 1, "after": 2, "same": False}, m["owned"]
PY
out="$(take noid FAKE_NO_URL=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "a chat whose id was never read exits 1" test "$rc" -eq 1
expect "it says a chat may remain, with the prompt as its title" grep -q '^RESULT: FAIL .*a chat titled like "In one short sentence, say what you can help me with." may remain' <<<"$out"
expect "markers.json says fail, chat not deleted, stopped after q1-sent" python3 - "$work/noid" <<'PY'
import json, pathlib, sys
m = json.loads((pathlib.Path(sys.argv[1]) / "markers.json").read_text())
assert m["status"] == "fail" and m["cleaned"] is False and m["created"] == [], m
assert [x["name"] for x in m["markers"]] == ["login", "home", "q1-sent"], m
assert m["owned"]["same"] is False, m["owned"]   # the chat exists: the comparison sees what the cleanup could not
PY
out="$(take quota FAKE_REFUSE_MODEL=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "a refused model call exits 1" test "$rc" -eq 1
expect "it fails at once with the model's message, not after the timeout" grep -q '^RESULT: FAIL answer 1 was refused or failed: 429: token quota exceeded for group sales' <<<"$out"
expect "its chat is deleted all the same" grep -q 'chats left: {"chats":0,"toggled":0}' <<<"$out"
expect "markers.json says fail but cleaned, and the same items owned" python3 - "$work/quota" <<'PY'
import json, pathlib, sys
m = json.loads((pathlib.Path(sys.argv[1]) / "markers.json").read_text())
assert m["status"] == "fail" and m["cleaned"] is True and m["owned"]["same"] is True, m
assert m["markers"][-1]["name"] == "q1-sent" and m["markers"][-1]["t"] < 30, m["markers"]
PY
out="$(take addresses FAKE_ADDRESSES=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "an answer with a node name and a private address fails the take" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL the page showed node names or private IP addresses (3 at once, at ' <<<\"\$0\"" "$out"
expect "its chat is deleted all the same" grep -q 'chats left: {"chats":0,"toggled":0}' <<<"$out"
expect "markers.json counts them per marker and keeps none; neither does the log" python3 - "$work/addresses" "$out" <<'PY'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1]); raw = (d / "markers.json").read_text(); m = json.loads(raw)
seen = m["private_addresses"]
assert seen["flagged"] is True and seen["count"] == 3 and seen["at"] and "login" not in seen["at"], seen
assert all(isinstance(x["private_addresses"], int) for x in m["markers"]) and m["markers"][0]["private_addresses"] == 0, m["markers"]
assert m["status"] == "fail" and m["cleaned"] is True and m["owned"]["same"] is True, m
for text in (raw, sys.argv[2]):
    assert "10.130" not in text and "compute.internal" not in text and "ip-10-18" not in text
PY
expect "a clean take says so" python3 - "$work/pass" <<'PY'
import json, pathlib, sys
m = json.loads((pathlib.Path(sys.argv[1]) / "markers.json").read_text())
assert m["private_addresses"] == {"flagged": False, "count": 0, "at": []} and all(x["private_addresses"] == 0 for x in m["markers"]), m
PY
expect "a scout reports the count per step" python3 - "$work/scout" <<'PY'
import json, pathlib, sys
s = json.loads((pathlib.Path(sys.argv[1]) / "scout.json").read_text())
assert s["private_addresses"] == {"flagged": False, "count": 0, "at": []} and all(x["private_addresses"] == 0 for x in s["steps"]), s
PY
out="$(take stray FAKE_STRAY_CHAT=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "a chat the take did not create fails the take" test "$rc" -eq 1
expect "it says the persona owns one more item" grep -q "^RESULT: FAIL sale-01 does not own the same items after the take: 1 more, 0 fewer" <<<"$out"
expect "markers.json: its own chat cleaned, ownership not the same" python3 - "$work/stray" <<'PY'
import json, pathlib, sys
m = json.loads((pathlib.Path(sys.argv[1]) / "markers.json").read_text())
assert m["status"] == "fail" and m["cleaned"] is True and m["owned"] == {"before": 1, "after": 2, "same": False}, m
PY
out="$(podman run --rm -v "$here:/work:Z" -w /work mcr.microsoft.com/playwright:v1.48.0-jammy \
  sh -c 'node tests/fake-open-webui.mjs >/dev/null & sleep 1; node tests/helpers-offline.mjs; rc=$?; echo "chats left: $(curl -s http://127.0.0.1:8099/fake/count)"; exit $rc')"; rc=$?
echo "$out" | sed 's/^/    /'
expect "the helpers refuse to click a switch unless it is a declared change" test "$rc" -eq 0
expect "the refused click never reached the switch" grep -q '"toggled":1}' <<<"$out"   # 1: only the declared click
expect "the password is in no file of the take" bash -c "! grep -r -l offline-test '$work' >/dev/null"
[[ $failed -eq 0 ]] && echo "RESULT: PASS" || echo "RESULT: FAIL"
exit $failed
