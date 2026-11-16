#!/usr/bin/env bash
# WP-288: the offline test of the walkthroughs written before their first scout (kagent, unifai-live-rag,
# lightspeed, identity-personas with its two takes, model-catalog-registry, mcp-tools-by-group, aap-audited-operations) and of the shared unifai* helpers. Runs record.mjs in the Playwright image against tests/fake-kagent.mjs,
# tests/fake-unifai.mjs and tests/fake-lightspeed.mjs, inside the container: no cluster, no `oc`, no persona password, no model call.
# It proves each walkthrough's own logic (phases, markers, what is created and deleted by id, the failures that must
# fail a take), NOT the real selectors: those are guesses until demo333's scout. tests/record-offline.sh stays the
# test of the recorder itself.
#   evaluations/browser/tests/walkthroughs-offline.sh            every demo
#   ONLY=lightspeed evaluations/browser/tests/walkthroughs-offline.sh   one demo
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
    sh -c 'npm install --no-audit --no-fund --silent >/dev/null 2>&1; for f in $FAKE; do node "tests/$f" >/dev/null & done; sleep 1; node record.mjs; rc=$?; echo "left: $(curl -s "http://127.0.0.1:$PORT/fake/count")$([ -n "${RECORD_BASE_URL_OWUI:-}" ] && curl -s "$RECORD_BASE_URL_OWUI/fake/count")"; exit $rc'
}
kagent() { take kagent fake-kagent.mjs 8098 "$@"; }
unifai() { take unifai-live-rag fake-unifai.mjs 8097 "$@"; }
lightspeed() { take lightspeed fake-lightspeed.mjs 8096 "$@"; }
rhoai() { take model-catalog-registry fake-rhoai.mjs 8095 "$@"; }
tools() { take mcp-tools-by-group fake-owui-tools.mjs 8094 "$@"; }
aap() { take aap-audited-operations fake-aap.mjs 8092 "$@"; }
identity() { take identity-personas "fake-unifai.mjs fake-open-webui.mjs" 8097 "$@" RECORD_BASE_URL_OWUI=http://127.0.0.1:8099; }
evalhub() { take evaluation-trustyai-evalhub fake-grafana.mjs 8095 "$@"; }
routing() { take ai-gateway-routing "fake-open-webui.mjs fake-grafana.mjs" 8095 "$@" RECORD_BASE_URL_OWUI=http://127.0.0.1:8099 RECORD_BASE_URL_GRAFANA=http://127.0.0.1:8095; }
wanted() { [[ -z "${ONLY:-}" || "$ONLY" == "$1" ]]; }
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
assert s["status"] == "done" and all(x["ok"] for x in s["steps"]) and s["refused_requests"] == [], s
grafana = ["approves OpenShift\x27s Authorize Access page for Grafana\x27s proxy as ai-ops-01", "closes Grafana\x27s product announcement by its cross"]
declared = {"kagent": ["clicks Skip wizard"], "evaluation-trustyai-evalhub": grafana, "ai-gateway-routing": grafana}.get(s["demo"], [])
assert len(s["changes"]) == len(declared) and all(c.startswith(w) for c, w in zip(s["changes"], declared)), s["changes"]
exec(sys.argv[2])
PY
}

if wanted kagent; then
echo "== kagent"
out="$(kagent k-scout RECORD_SCOUT=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "kagent: a scout exits 0, SCOUT: done" bash -c "test $rc -eq 0 && grep -q '^SCOUT: done$' <<<\"\$0\"" "$out"
expect "kagent: a scout creates no session and no wizard agent" grep -q 'left: {"sessions":1,"wizard_agents":0}' <<<"$out"
expect "kagent: scout.json reports every guess" scouted k-scout '
assert list(steps) == ["enter", "owned", "sessions-api", "wizard", "wizard-writes", "agents", "agent", "closed"], list(steps)
wz = steps["wizard"]
assert wz["shown"] == 1 and wz["beyond"] == [] and wz["storage_added"] == ["skipped"], wz
assert wz["sent"] == [{"method": "POST", "path": "/", "type": "text/plain", "action": "list-agents"}] and wz["sent"] == wz["page_load"], wz
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
out="$(kagent k-skip FAKE_SKIP_POSTS=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "kagent: a Skip wizard that sends more than its declared POST stops the take before anything is sent" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL \"Skip wizard\" sent POST /api/onboarding, beyond the one POST' <<<\"\$0\"" "$out"
expect "kagent: nothing created, stopped at the sign-in" markers k-skip '
assert names == ["login"] and m["created"] == [] and m["cleaned"] is None, m
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
expect "kagent: with no id in the address bar the session is found as the one new session, and deleted" bash -c "test $rc -eq 0 && grep -q 'id read from the session list' <<<\"\$0\" && grep -q 'left: {\"sessions\":1,' <<<\"\$0\"" "$out"
out="$(kagent k-button FAKE_ENTER=newline)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "kagent: when Enter only adds a line the Send button sends the question, once and as written" bash -c "test $rc -eq 0 && grep -q 'question 1 sent by the Send button' <<<\"\$0\" && grep -q 'left: {\"sessions\":1,' <<<\"\$0\"" "$out"
out="$(kagent k-dead FAKE_ENTER=dead)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "kagent: a question that is never sent fails the take before q1-sent, with no session" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL the question was typed but not sent: it is still in the chat input after Enter, the Send button, Ctrl+Enter' <<<\"\$0\" && grep -q 'left: {\"sessions\":1,' <<<\"\$0\"" "$out"
expect "kagent: that take stopped at the agent marker" markers k-dead '
assert [x["name"] for x in m["markers"]] == ["login", "agents", "agent"] and m["created"] == [], m'
out="$(kagent k-other FAKE_NO_URL=1 FAKE_OTHER_NAME=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "kagent: a new session that is not named like the question is not taken for the take's, and nothing is deleted" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL the session the first question created could not be told from the others.*may remain in kagent' <<<\"\$0\" && grep -q 'left: {\"sessions\":2,' <<<\"\$0\"" "$out"
fi
if wanted unifai-live-rag; then
echo "== unifai-live-rag"
out="$(unifai u-scout RECORD_SCOUT=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "unifai: a scout exits 0, SCOUT: done" bash -c "test $rc -eq 0 && grep -q '^SCOUT: done$' <<<\"\$0\"" "$out"
expect "unifai: a scout creates no session, ticks no row and no switch" grep -q 'left: {"sessions":1,"touched":0}' <<<"$out"
expect "unifai: scout.json reports every guess" scouted u-scout '
assert list(steps) == ["enter", "owned", "disclosure", "home", "documents", "chats", "workflows", "closed"], list(steps)
assert steps["disclosure"] == {**steps["disclosure"], "shown": True, "writes": [], "storage_added": ["session:ai-accepted"]}, steps["disclosure"]
assert steps["owned"]["count"] == 1 and steps["home"]["nav"] == {"documents": "a[href=\x27/documents\x27]", "chats": "a[href=\x27/agentic-chats\x27]"}, steps["home"]
assert steps["documents"]["ready"] is True and steps["documents"]["done"] == 2, steps["documents"]
assert steps["chats"]["available_chats"] == "1" and steps["chats"]["add_selector"] and steps["chats"]["session_open"] is False, steps["chats"]
w = steps["workflows"]
assert w["workflow_listed"] is True and w["workflow_exact_matches"] == 1 and w["confirm_button"] == 1 and w["cancel_button"] == 1, w
assert w["switches"] and not any(sw["on"] for sw in w["switches"]), w["switches"]
assert steps["closed"]["sessions"] == 1 and steps["closed"]["dialog_still_open"] is False
'
out="$(unifai u-pass)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "unifai: a good take exits 0, RESULT: PASS" bash -c "test $rc -eq 0 && grep -q '^RESULT: PASS$' <<<\"\$0\"" "$out"
expect "unifai: its session is gone, the earlier one is kept, nothing ticked" grep -q 'left: {"sessions":1,"touched":0}' <<<"$out"
expect "unifai: the log says the retriever is named on screen" grep -q 'the retriever consultant-01-documents is named on screen' <<<"$out"
expect "unifai: markers.json follows the contract" markers u-pass '
assert names == ["login", "home", "documents", "chat-new", "q1-sent", "q1-done", "q2-done", "end"], names
assert m["persona"] == "consultant-01" and m["motion_from"] == "home" and m["status"] == "pass", m
assert len(m["created"]) == 1 and m["created"][0]["kind"] == "session" and m["cleaned"] is True and m["owned"] == {"before": 1, "after": 1, "same": True}, m
assert all((d / x["png"]).stat().st_size > 0 for x in m["markers"]) and (d / "recording.webm").stat().st_size > 0
'
out="$(unifai u-accept FAKE_ACCEPT_POSTS=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "unifai: an Accept that writes to the server stops the take before anything is created" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL \"Accept\" on the AI Disclosure notice sent POST /api1/terms/approve' <<<\"\$0\"" "$out"
expect "unifai: stopped at the sign-in, nothing created" markers u-accept '
assert names == ["login"] and m["created"] == [] and m["cleaned"] is None, m
'
out="$(unifai u-nofiles FAKE_NO_FILES=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "unifai: a library without the demo files fails before anything is created" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL the Document Library does not show both demo files Done .*make demo start unifai-live-rag' <<<\"\$0\"" "$out"
out="$(unifai u-stuck FAKE_STUCK=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "unifai: an answer the page never draws fails the take, and its session is deleted" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL the answer holds ZN-CAR-7 but the page never drew it in the window within 60 s (its text is not on the page; 1 scrolling box' <<<\"\$0\" && grep -q 'left: {\"sessions\":1,' <<<\"\$0\"" "$out"
expect "unifai: nothing created, nothing to clean" markers u-nofiles '
assert names == ["login", "home"] and m["created"] == [] and m["cleaned"] is None and m["owned"]["same"] is True, m
'
out="$(unifai u-wrong FAKE_WRONG_ANSWER=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "unifai: an answer without the page's code fails the take" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL the answer to the 2:00 question does not hold ZN-CAR-7' <<<\"\$0\"" "$out"
expect "unifai: its session is deleted all the same" grep -q 'left: {"sessions":1,"touched":0}' <<<"$out"
out="$(unifai u-quota FAKE_REFUSE_MODEL=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "unifai: a refused model call fails at once with its message" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL answer 1 was refused or failed: 429: token quota exceeded for persona consultant-01' <<<\"\$0\"" "$out"
expect "unifai: stopped at q1-sent within 30 s, session deleted" markers u-quota '
assert names[-1] == "q1-sent" and m["markers"][-1]["t"] < 30 and m["cleaned"] is True and m["owned"]["same"] is True, m
'
out="$(unifai u-refused FAKE_REFUSE_DELETE=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "unifai: a refused delete fails the take and names the session" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL the session of consultant-01-my-documents (.*) was NOT deleted from consultant-01.s Agentic Chats' <<<\"\$0\"" "$out"
expect "unifai: markers.json says not cleaned, one more session owned" markers u-refused '
assert m["cleaned"] is False and m["owned"] == {"before": 1, "after": 2, "same": False} and len(names) == 8, m
'
fi
if wanted lightspeed; then
echo "== lightspeed"
out="$(lightspeed l-scout RECORD_SCOUT=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "lightspeed: a scout exits 0, SCOUT: done" bash -c "test $rc -eq 0 && grep -q '^SCOUT: done$' <<<\"\$0\"" "$out"
expect "lightspeed: a scout creates no conversation and dismisses nothing" grep -q 'left: {"conversations":1,"dismissed":0}' <<<"$out"
expect "lightspeed: scout.json reports every guess and the plugin's requests" scouted l-scout '
assert list(steps) == ["enter", "owned", "conversations-api", "console", "panel", "closed"], list(steps)
api = steps["conversations-api"]
assert api["status"] == 200 and api["count"] == 1 and api["top_keys"] == ["conversations"] and api["csrf_cookie"] is True, api
assert api["conversation_keys"] == ["conversation_id", "topic_summary", "last_message_timestamp"], api
assert steps["console"]["dialog_on_screen"] is False and steps["console"]["button_selector"] == "[data-test=\x27ols-plugin__popover-button\x27]", steps["console"]
p = steps["panel"]
assert p["input_selector"] == ".ols-plugin__popover textarea" and p["earlier_answers"] == 0 and p["panel_selector"], p
assert any(r.startswith("POST ") and r.endswith("/ols/authorized") for r in p["requests_seen"]), p["requests_seen"]
assert steps["closed"]["conversations"] == 1
assert "a topic" not in json.dumps(s), "a conversation topic reached scout.json"
'
out="$(lightspeed l-pass)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "lightspeed: a good take exits 0, RESULT: PASS" bash -c "test $rc -eq 0 && grep -q '^RESULT: PASS$' <<<\"\$0\"" "$out"
expect "lightspeed: its conversation is gone, the earlier one is kept" grep -q 'left: {"conversations":1,"dismissed":0}' <<<"$out"
expect "lightspeed: the log carries the three answers for the page" bash -c "grep -q 'answer 2 (.*): The pods running in zuno-ai-run' <<<\"\$0\" && grep -q 'answer 3 (.*): You do not have permission' <<<\"\$0\"" "$out"
expect "lightspeed: markers.json follows the contract" markers l-pass '
assert names == ["login", "console", "panel", "q1-sent", "q1-done", "q2-done", "q3-done", "end"], names
assert m["persona"] == "consultant-02" and m["motion_from"] == "console" and m["status"] == "pass", m
assert len(m["created"]) == 1 and m["created"][0]["kind"] == "conversation" and m["cleaned"] is True and m["owned"] == {"before": 1, "after": 1, "same": True}, m
assert all((d / x["png"]).stat().st_size > 0 for x in m["markers"]) and (d / "recording.webm").stat().st_size > 0
'
out="$(lightspeed l-safety FAKE_SAFETY=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "lightspeed: the safety-inspection warning fails the take at once" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL answer 1 was refused or failed: Lightspeed stopped on its safety inspection' <<<\"\$0\"" "$out"
expect "lightspeed: its conversation is deleted all the same" markers l-safety '
assert names[-1] == "q1-sent" and m["cleaned"] is True and m["owned"]["same"] is True, m
'
out="$(lightspeed l-quota FAKE_QUOTA=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "lightspeed: a refused first question fails at once, nothing created" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL answer 1 was refused or failed: HTTP 429 from Lightspeed$' <<<\"\$0\"" "$out"
expect "lightspeed: nothing to clean, the same conversations owned" markers l-quota '
assert m["created"] == [] and m["cleaned"] is None and m["owned"]["same"] is True and m["markers"][-1]["t"] < 30, m
'
out="$(lightspeed l-tour FAKE_TOUR=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "lightspeed: a dialog over the console stops the take, nothing dismissed" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL a dialog covers the console' <<<\"\$0\" && grep -q '\"dismissed\":0' <<<\"\$0\"" "$out"
out="$(lightspeed l-refused FAKE_REFUSE_DELETE=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "lightspeed: a refused delete fails the take and names the conversation" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL the conversation .* was NOT deleted from consultant-02.s Lightspeed history: DELETE answered HTTP 403' <<<\"\$0\"" "$out"
expect "lightspeed: markers.json says not cleaned, one more conversation owned" markers l-refused '
assert m["cleaned"] is False and m["owned"] == {"before": 1, "after": 2, "same": False} and len(names) == 8, m
'
fi
if wanted identity-personas; then
echo "== identity-personas"
out="$(identity i-scout RECORD_SCOUT=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "identity: a scout of both personas exits 0, SCOUT: done" bash -c "test $rc -eq 0 && grep -q '^SCOUT: done$' <<<\"\$0\"" "$out"
expect "identity: a scout creates no session, no chat, and clicks no workspace" grep -q 'left: {"sessions":1,"touched":0}{"chats":0,"toggled":0}' <<<"$out"
expect "identity: one scout.json per take, each as the page says, and takes.json" python3 - "$work/i-scout" <<'PY'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1]); t = json.loads((d / "takes.json").read_text())
assert t["status"] == "done" and [(x["name"], x["persona"], x["dir"], x["status"]) for x in t["takes"]] == [("consultant-02", "consultant-02", "consultant-02", "done"), ("sale-01", "sale-01", "sale-01", "done")], t
run = json.loads((d / "scout.json").read_text())   # the run's own scout.json, shaped like a single scout's
assert run["status"] == "done" and run["takes"] == ["consultant-02", "sale-01"] and len(run["walkthrough_sha256"]) == 64 and run["changes"] == [], run
assert [x["step"] for x in run["steps"]][:2] == ["consultant-02/enter", "consultant-02/owned"] and all(x["ok"] for x in run["steps"]), run["steps"]
assert sum(1 for x in run["steps"] if x["step"].startswith("sale-01/")) == 7 and all((d / x["png"]).stat().st_size > 0 for x in run["steps"])
for name, teams in (("consultant-02", ["agent-arkos", "agent-tekos", "consultant"]), ("sale-01", ["agent-comage", "sales"])):
    s = json.loads((d / name / "scout.json").read_text()); steps = {x["step"]: x for x in s["steps"]}
    assert s["take"] == name and s["persona"] == name and s["status"] == "done" and s["refused_requests"] == [], s
    assert list(steps) == ["enter", "owned", "disclosure", "unifai", "workspaces", "webui", "closed"], list(steps)
    assert steps["disclosure"]["shown"] is True and steps["disclosure"]["writes"] == [], steps["disclosure"]
    w = steps["workspaces"]
    assert w["as_the_page_says"] is True and sorted(k for k, v in w["listed"].items() if v) == sorted(teams) and w["overlay_on_screen"] is True, w
    assert steps["webui"]["chat_link_on_screen"] is False and steps["closed"]["chats"] == 1
PY
out="$(identity i-pass)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "identity: a good run of both takes exits 0, RESULT: PASS as its only RESULT line" bash -c "test $rc -eq 0 && grep -q '^RESULT: PASS$' <<<\"\$0\" && test \$(grep -c '^RESULT:' <<<\"\$0\") -eq 1" "$out"
expect "identity: both chats are gone, no workspace clicked, no tool switch clicked" grep -q 'left: {"sessions":1,"touched":0}{"chats":0,"toggled":0}' <<<"$out"
expect "identity: the log carries each persona's answer for the page" bash -c "grep -q 'answer of consultant-02 to the 2:30 question' <<<\"\$0\" && grep -q 'answer of sale-01 to the 3:30 question' <<<\"\$0\"" "$out"
expect "identity: each take's sub-directory follows the single-take contract" python3 - "$work/i-pass" <<'PY'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1]); t = json.loads((d / "takes.json").read_text())
assert t["demo"] == "identity-personas" and t["status"] == "pass" and [x["status"] for x in t["takes"]] == ["pass", "pass"], t
assert not (d / "markers.json").exists() and not list(d.glob("*.webm"))
for name in ("consultant-02", "sale-01"):
    m = json.loads((d / name / "markers.json").read_text())
    assert [x["name"] for x in m["markers"]] == ["login", "unifai", "workspaces", "webui", "q-sent", "q-done", "end"], m["markers"]
    assert m["take"] == name and m["persona"] == name and m["kind"] == "browser" and m["status"] == "pass" and m["motion_from"] == "unifai", m
    assert len(m["created"]) == 1 and m["created"][0]["kind"] == "chat" and m["cleaned"] is True and m["owned"] == {"before": 1, "after": 1, "same": True}, m
    assert all((d / name / x["png"]).stat().st_size > 0 for x in m["markers"]) and (d / name / "recording.webm").stat().st_size > 0
    assert len(list((d / name).glob("*.webm"))) == 1
PY
out="$(identity i-teams FAKE_WRONG_TEAMS=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "identity: a workspace the page does not give sale-01 fails its take, and only its take" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL sale-01: the workspace selector of sale-01 is not the page.s: not expected consultant' <<<\"\$0\"" "$out"
expect "identity: consultant-02 passed, sale-01 stopped before any question, nothing left" python3 - "$work/i-teams" "$out" <<'PY'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1]); t = json.loads((d / "takes.json").read_text())
assert t["status"] == "fail" and [x["status"] for x in t["takes"]] == ["pass", "fail"], t
m = json.loads((d / "sale-01" / "markers.json").read_text())
assert [x["name"] for x in m["markers"]] == ["login", "unifai"] and m["created"] == [] and m["cleaned"] is None and m["owned"]["same"] is True, m
assert '{"chats":0,"toggled":0}' in sys.argv[2]
PY
out="$(identity i-refused FAKE_REFUSE_DELETE=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "identity: a refused delete fails both takes, each named, the second still played" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL consultant-02: the chat .* was NOT deleted from consultant-02.s history.*; sale-01: the chat .* was NOT deleted from sale-01.s history' <<<\"\$0\"" "$out"
fi
if wanted model-catalog-registry; then
echo "== model-catalog-registry"
out="$(rhoai r-scout RECORD_SCOUT=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "model-catalog-registry: a scout exits 0, SCOUT: done, nothing deployed" bash -c "test $rc -eq 0 && grep -q '^SCOUT: done$' <<<\"\$0\" && grep -q 'left: {\"deploys\":0}' <<<\"\$0\"" "$out"
expect "model-catalog-registry: scout.json reports every guess" scouted r-scout '
assert list(steps) == ["enter", "owned", "dashboard", "menu", "catalog", "card", "closed"], list(steps)
d = steps["dashboard"]
assert d["dialog_on_screen"] is False and d["nav_selector"] == "#page-sidebar" and d["catalog_link"] == "" and d["group"].endswith("AI hub\x27)"), d
n = steps["menu"]
assert n["link"] == "nav a:text-is(\x27Models\x27)" and n["tab"] == "main [role=\x27tab\x27]:has-text(\x27Catalog\x27)" and n["url"].endswith("/ai-hub/models/catalog"), n
assert n["title"] == "Models" and n["words"]["Catalog"] and n["controls"], n
c = steps["catalog"]
assert c["cards"] == 4 and c["filter_selector"] == "[aria-label=\x27Source label selection\x27] button:has-text(\x27validated\x27)", c
assert c["filter_is"].startswith("button") and "checkbox_inside=false" in c["filter_is"] and all(c["words"].values()), c
k = steps["card"]
assert k["url"].endswith("/ai-hub/models/catalog/granite-3.1-8b-instruct") and k["title_selector"] == "[data-testid=\x27app-page-title\x27]" and k["words"]["Deploy"], k
'
out="$(rhoai r-nocat RECORD_SCOUT=1 FAKE_NO_CATALOG=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "model-catalog-registry: no catalog on screen, the scout still dumps the Models page and opens no card" bash -c "test $rc -eq 1 && grep -q '^SCOUT: failed catalog, card' <<<"\$0"" "$out"
expect "model-catalog-registry: scout.json keeps the menu step, the card step names why" python3 -c '
import json, sys
s = json.load(open(sys.argv[1])); steps = {x["step"]: x for x in s["steps"]}
assert steps["menu"]["ok"] and steps["menu"]["url"].endswith("/ai-hub/models/catalog") and steps["menu"]["controls"], steps["menu"]
assert not steps["card"]["ok"] and "the catalog was not seen" in steps["card"]["error"], steps["card"]
assert steps["closed"]["url"].endswith("/ai-hub/models/catalog"), steps["closed"]   # no project card was opened
' "$work/r-nocat/scout.json"
out="$(rhoai r-pass)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "model-catalog-registry: a good take exits 0, RESULT: PASS, nothing deployed" bash -c "test $rc -eq 0 && grep -q '^RESULT: PASS$' <<<\"\$0\" && grep -q 'left: {\"deploys\":0}' <<<\"\$0\"" "$out"
expect "model-catalog-registry: the log names the validated card it opened" grep -q 'card opened: llama-3.3-70b-instruct-quantized' <<<"$out"
expect "model-catalog-registry: markers.json follows the contract, read only" markers r-pass '
assert names == ["login", "dashboard", "catalog", "validated", "card", "end"], names
assert m["persona"] == "ai-dev-01" and m["motion_from"] == "dashboard" and m["status"] == "pass", m
assert m["created"] == [] and m["cleaned"] is None and m["owned"] == {"before": 0, "after": 0, "same": True}, m
ts = [x["t"] for x in m["markers"]]
assert all(b - a >= 1.9 for a, b in zip(ts[1:4], ts[2:5])), ts   # a presenter pause on every screen: frames to cut
assert all((d / x["png"]).stat().st_size > 0 for x in m["markers"]) and (d / "recording.webm").stat().st_size > 0
'
out="$(rhoai r-dialog FAKE_DIALOG=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "model-catalog-registry: a dialog over the dashboard stops the take" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL a dialog covers the dashboard' <<<\"\$0\"" "$out"
out="$(rhoai r-checkbox FAKE_CHECKBOX=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "model-catalog-registry: a source filter that is a checkbox is not clicked" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL refused to click a checkbox' <<<\"\$0\"" "$out"
out="$(rhoai r-approve FAKE_APPROVE=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "model-catalog-registry: an OAuth grant page stops the take, nothing granted" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL OpenShift asks ai-dev-01 to authorize' <<<\"\$0\"" "$out"
fi
if wanted evaluation-trustyai-evalhub; then
echo "== evaluation-trustyai-evalhub (Grafana)"
out="$(evalhub g-scout RECORD_SCOUT=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "grafana: a scout exits 0, SCOUT: done" bash -c "test $rc -eq 0 && grep -q '^SCOUT: done$' <<<\"\$0\"" "$out"
expect "grafana: a scout approves nothing and writes nothing" grep -q 'left: {"approved":0,"writes":0}' <<<"$out"
expect "grafana: scout.json reports the sign-in chain and what each panel shows" scouted g-scout '
assert list(steps) == ["enter", "owned", "chain", "dashboard", "panel-jobs", "panel-ragas", "panel-garak", "closed"], list(steps)
chain = steps["chain"]["chain"]
assert [c["step"] for c in chain] == ["proxy", "chooser", "keycloak", "grafana"] and steps["chain"]["authorize_shown"] is False, chain
assert chain[0]["matched"].startswith("button:has-text") and chain[1]["matched"] == "a[title=\x27Log in with openshift\x27]", chain
assert steps["owned"]["count"] == 0 and "from=now-7d" in steps["dashboard"]["url"] and steps["dashboard"]["title_on_screen"] is True, steps["dashboard"]
for name, word, view in (("panel-jobs", "ragas-eval", "viewPanel=panel-4"), ("panel-ragas", "faithfulness", "viewPanel=panel-6"), ("panel-garak", "MitigationBypass", "viewPanel=panel-7")):
    p = steps[name]
    assert p["no_data"] is False and p["whole_panel"] is True and any(word in line for line in p["lines"]), p
    assert p["view"] == view and p["not_in_window"] == [] and view in p["url"], p
    assert not any("loading" in line for line in p["lines"]), p["lines"]   # read after its query settled
assert steps["closed"]["writes"] == 0
'
out="$(evalhub g-pass)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "grafana: a good take exits 0, RESULT: PASS" bash -c "test $rc -eq 0 && grep -q '^RESULT: PASS$' <<<\"\$0\"" "$out"
expect "grafana: nothing approved, nothing written" grep -q 'left: {"approved":0,"writes":0}' <<<"$out"
expect "grafana: markers.json: nothing created, nothing owned, one marker per panel" markers g-pass '
assert names == ["login", "dashboard", "jobs", "ragas", "garak", "end"], names
assert m["persona"] == "ai-ops-01" and m["motion_from"] == "dashboard" and m["status"] == "pass", m
assert m["created"] == [] and m["cleaned"] is None and m["owned"] == {"before": 0, "after": 0, "same": True}, m
assert all((d / x["png"]).stat().st_size > 0 for x in m["markers"]) and (d / "recording.webm").stat().st_size > 0
'
out="$(evalhub g-nodata FAKE_NO_DATA=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "grafana: a panel that shows No data fails the take and names its row" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL the panel \"Garak attack success rate (jailbreak probes)\" (row 2:30) shows \"No data\"' <<<\"\$0\"" "$out"
out="$(evalhub g-authorize FAKE_AUTHORIZE=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "grafana: the declared Authorize Access page is approved once, and the take passes" bash -c "test $rc -eq 0 && grep -q '^RESULT: PASS$' <<<\"\$0\" && grep -q 'left: {\"approved\":1,\"writes\":0}' <<<\"\$0\"" "$out"
out="$(evalhub g-authorize-scout FAKE_AUTHORIZE=1 RECORD_SCOUT=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "grafana: a scout approves it too, and its chain says so" scouted g-authorize-scout '
c = steps["chain"]
assert c["authorize_shown"] is True and c["authorized"] is True and [x["step"] for x in c["chain"]] == ["proxy", "chooser", "keycloak", "authorize", "grafana"], c
assert c["chain"][-1]["matched"] == "input[name=\x27approve\x27]", c["chain"]
'
out="$(evalhub g-authorize-more FAKE_AUTHORIZE=more)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "grafana: an Authorize Access page that asks for one more permission stops the take, nothing approved" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL OpenShift asks ai-ops-01 to authorize Grafana.s proxy (\"Authorize Access\") and the take stops there: it asks for more than user:info and user:check-access (user:full)' <<<\"\$0\" && grep -q 'left: {\"approved\":0,\"writes\":0}' <<<\"\$0\"" "$out"
out="$(evalhub g-authorize-other FAKE_AUTHORIZE=other)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "grafana: an Authorize Access page of another client stops the take, nothing approved" bash -c "test $rc -eq 1 && grep -q 'the take stops there: the page is not the one the owner approved (not on it: grafana-oauth-proxy)' <<<\"\$0\" && grep -q 'left: {\"approved\":0,\"writes\":0}' <<<\"\$0\"" "$out"
out="$(evalhub g-oldview FAKE_VIEW=old)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "grafana: a Grafana that names a panel by its bare id is filmed all the same" bash -c "test $rc -eq 0 && grep -q 'alone over the page (viewPanel=4)' <<<\"\$0\"" "$out"
out="$(evalhub g-narrow FAKE_NARROW=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "grafana: a key column header that is cut off, even with the panel alone, fails the take before its marker" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL the panel \"Garak / RAGAS job outcomes\" (row 0:45) does not show failed inside the window' <<<\"\$0\"" "$out"
expect "grafana: that take stopped at the dashboard marker" markers g-narrow '
assert names == ["login", "dashboard"], names'
out="$(routing r-narrow FAKE_NARROW=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "routing: a provider column that is cut off fails the dashboard take" bash -c "test $rc -eq 1 && grep -q 'dashboard: .*does not show provider inside the window' <<<\"\$0\"" "$out"
out="$(evalhub g-news FAKE_NEWS=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "grafana: the product announcement is closed and the take passes, nothing written" bash -c "test $rc -eq 0 && grep -q '^RESULT: PASS$' <<<\"\$0\" && grep -q 'left: {\"approved\":0,\"writes\":0}' <<<\"\$0\"" "$out"
out="$(evalhub g-news-scout FAKE_NEWS=1 RECORD_SCOUT=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "grafana: a scout reports the announcement, how it was closed and what the close stored" scouted g-news-scout '
n = steps["dashboard"]["news"]
assert n == {"shown": 1, "closed_by": "[role=\x27dialog\x27] button[aria-label=\x27Close\x27]", "refused": [], "allowed": [], "storage_added": ["local:grafana.whatsnew.dismissed"], "declared": True}, n
assert steps["dashboard"]["dialog_on_screen"] is False
'
out="$(evalhub g-news-server FAKE_NEWS=server)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "grafana: a close that wants to save a preference is refused in the browser and stops the take" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL closing Grafana.s announcement wanted to send PATCH /api/user/preferences to Grafana: refused before it left the browser' <<<\"\$0\" && grep -q 'left: {\"approved\":0,\"writes\":0}' <<<\"\$0\"" "$out"
out="$(evalhub g-news-stored FAKE_NEWS=storage RECORD_SCOUT=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "grafana: the one declared write of the close (Grafana's user storage) is let through, once, and reported by its keys" scouted g-news-stored '
n = steps["dashboard"]["news"]
assert n["refused"] == [] and n["shown"] == 1 and len(n["allowed"]) == 1, n
assert n["allowed"][0]["request"] == "POST /apis/userstorage.grafana.app/v0alpha1/namespaces/default/user-storage/" and n["allowed"][0]["keys"] == ["metadata", "spec", "spec.data"] and n["allowed"][0]["bytes"] > 0, n
assert "seen-1" not in json.dumps(s)
'
expect "grafana: that write reached Grafana's user storage, and nothing else was written" grep -q 'left: {"approved":0,"writes":0,"stored":1}' <<<"$out"
out="$(evalhub g-news-other FAKE_NEWS=other)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "grafana: another dialog stops the take, nothing dismissed" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL a dialog covers Grafana and it is not its product announcement (\"xYour session is about to expire\")' <<<\"\$0\"" "$out"
out="$(evalhub g-star FAKE_STAR=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "grafana: a write to Grafana during the take fails it" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL the take sent POST /api/user/stars/dashboard/uid/zuno-trustyai to Grafana' <<<\"\$0\"" "$out"
out="$(evalhub g-star-scout FAKE_STAR=1 RECORD_SCOUT=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "grafana: in a scout that write is refused before it leaves the browser, and fails the scout" bash -c "test $rc -eq 1 && grep -q '^SCOUT: failed' <<<\"\$0\" && grep -q 'left: {\"approved\":0,\"writes\":0}' <<<\"\$0\"" "$out"
fi
if wanted ai-gateway-routing; then
echo "== ai-gateway-routing (two takes of two screens)"
out="$(routing r-scout RECORD_SCOUT=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "routing: a scout of both takes exits 0, SCOUT: done" bash -c "test $rc -eq 0 && grep -q '^SCOUT: done$' <<<\"\$0\"" "$out"
expect "routing: a scout approves, writes and creates nothing" grep -q 'left: {"approved":0,"writes":0}{"chats":0,"toggled":0}' <<<"$out"
expect "routing: each take's scout.json reports its own screens" python3 - "$work/r-scout" <<'PY'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1])
chat = {x["step"]: x for x in json.loads((d / "chat" / "scout.json").read_text())["steps"]}
dash = {x["step"]: x for x in json.loads((d / "dashboard" / "scout.json").read_text())["steps"]}
assert list(chat) == ["enter", "owned", "picker", "closed"] and chat["picker"]["zuno_code_listed"] is True and chat["picker"]["label"] == "Zuno", chat
assert list(dash) == ["enter", "owned", "chain", "dashboard", "panel-providers", "closed"], list(dash)
assert "var-client=open-webui" in dash["dashboard"]["url"] and "from=now-1h" in dash["dashboard"]["url"], dash["dashboard"]
assert dash["panel-providers"]["names_a_local_model"] is True and dash["panel-providers"]["names_codestral"] is False, dash["panel-providers"]
assert dash["panel-providers"]["view"] == "viewPanel=panel-5" and dash["panel-providers"]["not_in_window"] == ["mistral-codestral"], dash["panel-providers"]
assert json.loads((d / "scout.json").read_text())["status"] == "done"
PY
out="$(routing r-pass)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "routing: a good run of both takes exits 0, RESULT: PASS" bash -c "test $rc -eq 0 && grep -q '^RESULT: PASS$' <<<\"\$0\"" "$out"
expect "routing: the chat is gone, nothing written to Grafana" grep -q 'left: {"approved":0,"writes":0}{"chats":0,"toggled":0}' <<<"$out"
expect "routing: the dashboard take waited for the Codestral row" bash -c "grep -q 'does not name mistral-codestral yet: waiting' <<<\"\$0\" && grep -q 'the panel names mistral-codestral; a local model for open-webui in the hour: local-gpt-oss-maas' <<<\"\$0\"" "$out"
expect "routing: each take has its own markers and its own motion_from" python3 - "$work/r-pass" <<'PY'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1])
chat = json.loads((d / "chat" / "markers.json").read_text()); dash = json.loads((d / "dashboard" / "markers.json").read_text())
assert [x["name"] for x in chat["markers"]] == ["login", "home", "picker", "code-picked", "q-sent", "q-done", "end"] and chat["motion_from"] == "home", chat
assert [x["name"] for x in dash["markers"]] == ["login", "dashboard", "providers", "end"] and dash["motion_from"] == "dashboard", dash
assert chat["persona"] == "sale-01" and len(chat["created"]) == 1 and chat["cleaned"] is True and chat["owned"]["same"] is True, chat
assert dash["persona"] == "ai-ops-01" and dash["created"] == [] and dash["cleaned"] is None and dash["owned"] == {"before": 0, "after": 0, "same": True}, dash
assert chat["status"] == dash["status"] == "pass" and (d / "dashboard" / "recording.webm").stat().st_size > 0
PY
fi
if wanted mcp-tools-by-group; then
echo "== mcp-tools-by-group"
out="$(tools t-scout RECORD_SCOUT=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "tools: a scout of both personas exits 0, SCOUT: done, no chat, no search" bash -c "test $rc -eq 0 && grep -q '^SCOUT: done$' <<<\"\$0\" && grep -q 'left: {\"chats\":0,\"searches\":0}' <<<\"\$0\"" "$out"
expect "tools: one scout.json per take, the home page with no earlier chat on screen" python3 - "$work/t-scout" <<'PY'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1]); t = json.loads((d / "takes.json").read_text())
assert [(x["name"], x["status"]) for x in t["takes"]] == [("sale-01", "done"), ("consultant-02", "done")], t
for name in ("sale-01", "consultant-02"):
    s = json.loads((d / name / "scout.json").read_text()); steps = {x["step"]: x for x in s["steps"]}
    assert list(steps) == ["enter", "owned", "home", "closed"] and s["refused_requests"] == [], s
    assert steps["home"]["chat_link_on_screen"] is False and all(steps["home"]["words"].values()) and steps["closed"]["chats"] == 1, steps
PY
out="$(tools t-pass)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "tools: a good run of both takes exits 0, RESULT: PASS" bash -c "test $rc -eq 0 && grep -q '^RESULT: PASS$' <<<\"\$0\" && test \$(grep -c '^RESULT:' <<<\"\$0\") -eq 1" "$out"
expect "tools: the four chats are gone, one Confluence search ran" grep -q 'left: {"chats":0,"searches":1}' <<<"$out"
expect "tools: the log carries the tools answers and sale-01's 2:45 answer, never consultant-02's 1:30 answer" bash -c "grep -q 'answer of sale-01 to the 0:00 question' <<<\"\$0\" && grep -q 'answer of consultant-02 to the 0:45 question' <<<\"\$0\" && grep -q 'answer of sale-01 to the 2:45 question' <<<\"\$0\" && grep -q 'answer of consultant-02 to the 1:30 question: [0-9]* chars, not logged' <<<\"\$0\" && ! grep -q 'FAKE-CONFLUENCE-TITLE' <<<\"\$0\"" "$out"
expect "tools: the Confluence tool call is seen, the answer's end and the tool call inside the window, sale-01 saw no Confluence tool" bash -c "grep -q 'Confluence tool call on screen (text=/View Result from' <<<\"\$0\" && grep -q 'its end inside the window after 0 scroll(s), the tool call inside it too$' <<<\"\$0\" && grep -q 'a Confluence tool name on screen after sale-01.s answer: no' <<<\"\$0\"" "$out"
expect "tools: each take's markers, two chats created and deleted, the chip taken before the answer and q2-done after it" python3 - "$work/t-pass" <<'PY'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1]); t = json.loads((d / "takes.json").read_text())
assert t["status"] == "pass" and [x["status"] for x in t["takes"]] == ["pass", "pass"], t
want = {"sale-01": ["login", "home", "q1-sent", "q1-done", "home-2", "q2-sent", "q2-done", "end"],
        "consultant-02": ["login", "home", "q1-sent", "q1-done", "home-2", "q2-sent", "chip", "q2-done", "end"]}
for name, names in want.items():
    m = json.loads((d / name / "markers.json").read_text())
    assert [x["name"] for x in m["markers"]] == names and m["motion_from"] == "home" and m["status"] == "pass", m
    assert len(m["created"]) == 2 and {c["kind"] for c in m["created"]} == {"chat"} and m["cleaned"] is True and m["owned"] == {"before": 1, "after": 1, "same": True}, m
    assert all((d / name / x["png"]).stat().st_size > 0 for x in m["markers"]) and (d / name / "recording.webm").stat().st_size > 0
c = {x["name"]: x["t"] for x in json.loads((d / "consultant-02" / "markers.json").read_text())["markers"]}
assert 0.5 < c["chip"] - c["q2-sent"] < 2.5, c   # the stand-in shows the tool call 1 s after the send, its answer 2.5 s later
assert c["q2-done"] - c["chip"] > 3, c           # the answer, then 1.5 s
PY
out="$(tools t-nochip FAKE_NO_TOOL_CALL=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "tools: no tool call on screen fails consultant-02's take at once, sale-01 passes, nothing left" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL consultant-02: no Confluence tool call on screen for consultant-02' <<<\"\$0\" && grep -q 'the answer finished with no Confluence tool call on screen' <<<\"\$0\" && grep -q 'left: {\"chats\":0,' <<<\"\$0\" && ! grep -q 'FAKE-CONFLUENCE-TITLE' <<<\"\$0\"" "$out"
out="$(tools t-other FAKE_OTHER_TOOL=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "tools: a Drive tool call is not taken for the Confluence one: consultant-02's take fails, no search, nothing left" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL consultant-02: no Confluence tool call on screen for consultant-02' <<<\"\$0\" && grep -q 'left: {\"chats\":0,\"searches\":0}' <<<\"\$0\" && ! grep -q 'marker chip' <<<\"\$0\"" "$out"
out="$(tools t-long FAKE_LONG_ANSWER=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "tools: a long answer is scrolled to its end before q2-done, the tool call above it, no title in the log" bash -c "test $rc -eq 0 && grep -q 'its end inside the window after [1-9][0-9]* scroll(s), the tool call above it$' <<<\"\$0\" && ! grep -q 'FAKE-CONFLUENCE-TITLE' <<<\"\$0\"" "$out"
fi
if wanted aap-audited-operations; then
echo "== aap-audited-operations"
out="$(aap a-scout RECORD_SCOUT=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "aap: a scout exits 0, SCOUT: done, nothing written but the session refreshes, no Output opened" bash -c "test $rc -eq 0 && grep -q '^SCOUT: done$' <<<\"\$0\" && grep -q 'left: {\"writes\":0,\"outputs\":0,\"sessions\":[1-9]' <<<\"\$0\"" "$out"
expect "aap: the scout plays every screen, dumps its shapes, finds job 102 (zuno-mcp's, not the latest) and no launch action" scouted a-scout '
assert list(steps) == ["enter", "owned", "sign-in", "home", "home-shapes", "templates", "templates-shapes", "jobs", "jobs-shapes", "job", "job-shapes",
                       "project", "project-shapes", "guard"], list(steps)
assert [c["step"] for c in steps["sign-in"]["chain"]] == ["sso-link", "home"] and steps["owned"]["count"] == 0, steps["sign-in"]
assert steps["jobs"]["job"] == 102 and steps["jobs"]["jobs"] == {"visible": 2, "by_agent": 1} and steps["jobs"]["filter"].startswith("#filter-input"), steps["jobs"]
assert steps["templates"]["launch_actions"] > 0 and steps["templates"]["launch_enabled"] == 0, steps["templates"]
assert steps["job"]["url"] == "/execution/jobs/playbook/102/details" and steps["project"]["words"]["\\bdevel\\b"] is True, (steps["job"], steps["project"])
assert all(steps[n]["main"] and steps[n]["nav"] for n in ("templates-shapes", "jobs-shapes", "job-shapes", "project-shapes")), "shapes"
assert steps["guard"]["refused"] == [] and s["private_addresses"]["flagged"] is False, s
assert steps["guard"]["session_refresh"]["count"] >= 1 and steps["guard"]["session_refresh"]["path"] == "/api/gateway/v1/session/" and steps["guard"]["session_refresh"]["keys"] == [], steps["guard"]
assert set(steps["job"]["below_the_window"]) == {"an execution node", "an instance group"}, steps["job"]
'
out="$(aap a-pass)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "aap: a good take exits 0, RESULT: PASS, nothing written but the session refreshes (logged), no Output opened" bash -c "test $rc -eq 0 && grep -q '^RESULT: PASS$' <<<\"\$0\" && grep -q 'left: {\"writes\":0,\"outputs\":0,\"sessions\":[1-9]' <<<\"\$0\" && grep -q 'session refreshes let through (POST /api/gateway/v1/session/): [1-9][0-9]* (body bytes 2, keys none)' <<<\"\$0\" && grep -q 'aap: back to AAP after the Keycloak sign-in' <<<\"\$0\"" "$out"
expect "aap: the markers in order, nothing created, the jobs launched by consultant-03 the same, no node name at a marker" markers a-pass '
assert names == ["login", "home", "templates", "jobs", "job", "project", "end"] and m["motion_from"] == "home" and m["status"] == "pass", m
assert m["created"] == [] and m["cleaned"] is None and m["owned"] == {"before": 0, "after": 0, "same": True} and m["private_addresses"]["flagged"] is False, m
assert all((d / x["png"]).stat().st_size > 0 for x in m["markers"]) and (d / "recording.webm").stat().st_size > 0
'
expect "aap: the log names the sign-in chain, the job opened and the project's source" bash -c "grep -q 'sign-in: sso-link a\[href\*=' <<<\"\$0\" && grep -q '\"job\":102' <<<\"\$0\" && grep -q 'project: .*\"open\":\"main a:text-is' <<<\"\$0\"" "$out"
out="$(aap a-uiauth FAKE_SSO_HIDDEN=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "aap: no Keycloak link on AAP's sign-in page: the address from ui_auth, AAP's own form never filled" bash -c "test $rc -eq 0 && grep -q 'sign-in: ui_auth ui_auth' <<<\"\$0\" && grep -q 'left: {\"writes\":0,' <<<\"\$0\"" "$out"
out="$(aap a-loop FAKE_LOGIN_LOOP=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "aap: a sign-in that comes back to AAP's sign-in page fails the take and says so" bash -c "test $rc -eq 1 && grep -q 'RESULT: FAIL.*came back to AAP.s sign-in page' <<<\"\$0\"" "$out"
out="$(aap a-nojob FAKE_NO_MCP_JOB=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "aap: no zuno-day0-check job by zuno-mcp fails the take, with what the reader sees and the fallback" bash -c "test $rc -eq 1 && grep -q 'RESULT: FAIL.*sees no zuno-day0-check job launched by zuno-mcp (zuno-day0-check jobs it sees: 1; by zuno-mcp: 0)' <<<\"\$0\"" "$out"
out="$(aap a-write FAKE_UI_WRITE=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "aap: a page that wants to write is refused in the browser and fails the take, nothing reaches AAP" bash -c "test $rc -eq 1 && grep -q 'RESULT: FAIL.*wanted to send POST /api/gateway/v1/user_preferences/' <<<\"\$0\" && grep -q 'left: {\"writes\":0,' <<<\"\$0\"" "$out"
out="$(aap a-dialog FAKE_DIALOG=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "aap: a dialog over the first screen fails the take, nothing dismissed" bash -c "test $rc -eq 1 && grep -q 'RESULT: FAIL.*a dialog covers AAP.s first screen' <<<\"\$0\"" "$out"
out="$(aap a-body FAKE_SESSION_BODY=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "aap: a session refresh with a body is let through, its keys' names logged, never a value" bash -c "test $rc -eq 0 && grep -q 'keys theme, expires_in, padding)' <<<\"\$0\" && ! grep -q 'dark' <<<\"\$0\" && grep -q 'left: {\"writes\":0,' <<<\"\$0\"" "$out"
out="$(aap a-low FAKE_DETAILS_LOW=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "aap: the execution node or instance group inside the window on the Details fails the take, by kind" bash -c "test $rc -eq 1 && grep -q 'RESULT: FAIL.*the job.s Details show an execution node, an instance group inside the window' <<<\"\$0\" && ! grep -q 'aap-controller-task' <<<\"\$0\"" "$out"
out="$(aap a-hang FAKE_HANG=1 RECORD_DEADLINE_MS=25000)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "aap: a take that hangs stops at the overall deadline and logs the phase it was in" bash -c "test $rc -eq 1 && grep -q 'aap: STOPPED at \"templates\" after' <<<\"\$0\" && grep -q '^RESULT: FAIL' <<<\"\$0\"" "$out"
fi
expect "the password is in no file of any take" bash -c "! grep -r -l offline-test '$work' >/dev/null"
[[ $failed -eq 0 ]] && echo "RESULT: PASS" || echo "RESULT: FAIL"
exit $failed
