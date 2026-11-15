#!/usr/bin/env bash
# WP-288: the offline test of the walkthroughs written before their first scout (kagent). Runs record.mjs in the
# Playwright image against tests/fake-kagent.mjs, inside the container: no cluster, no `oc`, no persona password, no model call.
# It proves each walkthrough's own logic (phases, markers, what is created and deleted by id, the failures that must
# fail a take), NOT the real selectors: those are guesses until demo333's scout. tests/record-offline.sh stays the
# test of the recorder itself.
#   evaluations/browser/tests/walkthroughs-offline.sh
set -uo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
failed=0
take() {   # take <demo> <fake> <port> <name> [VAR=1 ...]: one recorder run; prints its output, returns its exit code
  local demo="$1" fake="$2" port="$3" name="$4"
  mkdir -p "$work/$name"
  local knobs=()
  for knob in "${@:5}"; do knobs+=(-e "$knob"); done
  podman run --rm -e DEMO="$demo" -e APPS_DOMAIN=fake.invalid -e PERSONA_PASSWORD=offline-test -e OUT=/out \
    -e RECORD_BASE_URL="http://127.0.0.1:$port" -e FAKE="$fake" -e PORT="$port" "${knobs[@]+"${knobs[@]}"}" \
    -v "$here:/work:Z" -v "$work/$name:/out:Z" -w /work mcr.microsoft.com/playwright:v1.48.0-jammy \
    sh -c 'npm install --no-audit --no-fund --silent >/dev/null 2>&1; node "tests/$FAKE" >/dev/null & sleep 1; node record.mjs; rc=$?; echo "left: $(curl -s "http://127.0.0.1:$PORT/fake/count")"; exit $rc'
}
kagent() { take kagent fake-kagent.mjs 8098 "$@"; }
expect() {   # expect <what> <command...>
  if "${@:2}"; then echo "ok    $1"; else echo "FAIL  $1"; failed=1; fi
}
markers() {   # markers <dir> <python assertions on m>
  python3 - "$work/$1" "$2" <<'PY'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1]); m = json.loads((d / "markers.json").read_text())
names = [x["name"] for x in m["markers"]]
exec(sys.argv[2])
PY
}
scouted() {   # scouted <dir> <python assertions on s and steps>
  python3 - "$work/$1" "$2" <<'PY'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1]); s = json.loads((d / "scout.json").read_text())
steps = {x["step"]: x for x in s["steps"]}
assert s["status"] == "done" and all(x["ok"] for x in s["steps"]) and s["refused_requests"] == [] and s["changes"] == [], s
exec(sys.argv[2])
PY
}

echo "== kagent"
out="$(kagent k-scout RECORD_SCOUT=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "kagent: a scout exits 0, SCOUT: done" bash -c "test $rc -eq 0 && grep -q '^SCOUT: done$' <<<\"\$0\"" "$out"
expect "kagent: a scout creates no session and no wizard agent" grep -q 'left: {"sessions":1,"wizard_agents":0}' <<<"$out"
expect "kagent: scout.json reports every guess" scouted k-scout '
assert list(steps) == ["enter", "owned", "sessions-api", "agents", "agent", "closed"], list(steps)
api = steps["sessions-api"]
assert [t["status"] for t in api["tried"]] == [400, 200] and api["used"] == "/api/sessions?user_id=admin@kagent.dev" and api["count"] == 1, api
assert api["tried"][1]["session_keys"] == ["id", "name"], api
assert steps["agents"]["wizard_on_screen"] is False and steps["agents"]["agent_selector"].startswith("a[href*="), steps["agents"]
a = steps["agent"]
assert a["input_selector"] == "textarea[placeholder*=\x27message\x27 i]" and a["session_open"] is False and all(a["tools_on_screen"].values()), a
assert a["session_links"] == 1 and a["session_link_shapes"] == ["/agents/zuno-kagent/zuno-sre/chat/<uuid>"], a
assert steps["closed"]["sessions"] == 1
'
out="$(kagent k-pass)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "kagent: a good take exits 0, RESULT: PASS" bash -c "test $rc -eq 0 && grep -q '^RESULT: PASS$' <<<\"\$0\"" "$out"
expect "kagent: its session is gone, the earlier one is kept, no wizard agent" grep -q 'left: {"sessions":1,"wizard_agents":0}' <<<"$out"
expect "kagent: markers.json follows the contract" markers k-pass '
assert names == ["login", "agents", "agent", "q1-sent", "q1-done", "q2-sent", "q2-done", "end"], names
assert m["persona"] == "ai-ops-01" and m["motion_from"] == "agents" and m["status"] == "pass", m
assert len(m["created"]) == 1 and m["created"][0]["kind"] == "session" and m["cleaned"] is True and m["owned"] == {"before": 1, "after": 1, "same": True}, m
assert all((d / x["png"]).stat().st_size > 0 for x in m["markers"]) and (d / "recording.webm").stat().st_size > 0
'
out="$(kagent k-leak FAKE_LEAK=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "kagent: an answer to the Secret question that is not a refusal fails the take" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL the answer to the Secret question does not read as a refusal' <<<\"\$0\"" "$out"
expect "kagent: the image to review exists, and the session is deleted all the same" markers k-leak '
assert names[-1] == "q2-done" and (d / "q2-done.png").stat().st_size > 0 and m["cleaned"] is True and m["owned"]["same"] is True, m
'
out="$(kagent k-refused FAKE_REFUSE_DELETE=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "kagent: a refused delete fails the take and names the session" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL the session .* of zuno-sre was NOT deleted from kagent: DELETE answered HTTP 403' <<<\"\$0\"" "$out"
expect "kagent: markers.json says not cleaned, one more session owned" markers k-refused '
assert m["cleaned"] is False and m["owned"] == {"before": 1, "after": 2, "same": False} and len(names) == 8, m
'
out="$(kagent k-noid FAKE_NO_URL=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "kagent: a session whose id was never read is reported, not silent" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL .*a session of zuno-sre starting with \"Which pods of zuno-ai-run are not Running, and how many are?\" may remain' <<<\"\$0\"" "$out"

expect "the password is in no file of any take" bash -c "! grep -r -l offline-test '$work' >/dev/null"
[[ $failed -eq 0 ]] && echo "RESULT: PASS" || echo "RESULT: FAIL"
exit $failed
