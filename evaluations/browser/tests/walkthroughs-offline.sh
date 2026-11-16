#!/usr/bin/env bash
# WP-288: the offline test of the walkthroughs written before their first scout (kagent, unifai-live-rag,
# lightspeed, identity-personas with its two takes, model-catalog-registry, mcp-tools-by-group, aap-audited-operations, quotas, lora-pipeline-mlflow-kueue, genai-playground) and of the shared unifai* helpers. Runs record.mjs in the Playwright image against tests/fake-kagent.mjs,
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
    sh -c 'npm install --no-audit --no-fund --silent >/dev/null 2>&1; for f in $FAKE; do node "tests/$f" >/dev/null & done; sleep 1; node record.mjs; rc=$?; echo "left: $(curl -s "http://127.0.0.1:$PORT/fake/count")$([ -n "${RECORD_BASE_URL_OWUI:-}" ] && curl -s "$RECORD_BASE_URL_OWUI/fake/count")$([ -n "${RECORD_BASE_URL_GRAFANA:-}" ] && [ "$PORT" != 8095 ] && curl -s "$RECORD_BASE_URL_GRAFANA/fake/count")$([ -n "${RECORD_BASE_URL_TEMPO:-}" ] && curl -s "$RECORD_BASE_URL_TEMPO/fake/count")"; exit $rc'
}
kagent() { take kagent fake-kagent.mjs 8098 "$@"; }
unifai() { take unifai-live-rag fake-unifai.mjs 8097 "$@"; }
lightspeed() { take lightspeed fake-lightspeed.mjs 8096 "$@"; }
rhoai() { take model-catalog-registry fake-rhoai.mjs 8095 "$@"; }
tools() { take mcp-tools-by-group fake-owui-tools.mjs 8094 "$@"; }
aap() { take aap-audited-operations fake-aap.mjs 8092 "$@"; }
quotas() { take quotas fake-quotas.mjs 8089 "$@" RECORD_BASE_URL_GITHUB=http://127.0.0.1:8088; }
lora() { take lora-pipeline-mlflow-kueue fake-rhoai-lora.mjs 8087 "$@"; }
genai() { take genai-playground fake-genai.mjs 8086 "$@"; }
identity() { take identity-personas "fake-unifai.mjs fake-open-webui.mjs" 8097 "$@" RECORD_BASE_URL_OWUI=http://127.0.0.1:8099; }
evalhub() { take evaluation-trustyai-evalhub fake-grafana.mjs 8095 "$@"; }
routing() { take ai-gateway-routing "fake-open-webui.mjs fake-grafana.mjs" 8095 "$@" RECORD_BASE_URL_OWUI=http://127.0.0.1:8099 RECORD_BASE_URL_GRAFANA=http://127.0.0.1:8095; }
# dify types a second credential: the recorder's (DIFY_ADMIN_PASSWORD) and the stand-in's own copy of it.
dify() { local name="$1"; shift; take dify fake-dify.mjs 8094 "$name" DIFY_ADMIN_PASSWORD=offline-admin-secret FAKE_ADMIN_PASSWORD=offline-admin-secret "$@"; }
guardrails() { local name="$1"; shift; take guardrails "fake-dify.mjs fake-grafana.mjs" 8094 "$name" DIFY_ADMIN_PASSWORD=offline-admin-secret FAKE_ADMIN_PASSWORD=offline-admin-secret RECORD_BASE_URL_DIFY=http://127.0.0.1:8094 RECORD_BASE_URL_GRAFANA=http://127.0.0.1:8095 "$@"; }
agents() { take unifai-agents fake-unifai.mjs 8097 "$@" FAKE_TEAM_MODE=1; }
trace() { take observability-trace "fake-unifai.mjs fake-jaeger.mjs" 8097 "$@" FAKE_TEAM_MODE=1 RECORD_BASE_URL_TEMPO=http://127.0.0.1:8093; }
maas() { take maas-portal-api-keys fake-maas-portal.mjs 8092 "$@" RECORD_BASE_URL=http://127.0.0.1:8092/maas-consumer-portal RECORD_BASE_URL_MAAS=http://127.0.0.1:8092/zuno-ai-run/gpt-oss-20b; }
claw() { local name="$1"; shift; take openclaw fake-openclaw.mjs 8091 "$name" OPENCLAW_UI_PASSWORD=offline-claw-secret FAKE_UI_PASSWORD=offline-claw-secret "$@"; }
a2a() { take a2a-delegation-approval fake-unifai.mjs 8097 "$@" FAKE_TEAM_MODE=1 FAKE_APPROVALS=1; }
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
declared = {"kagent": ["clicks Skip wizard"], "a2a-delegation-approval": ["clicks Approve on the approval card of aap.cluster.audit"], "evaluation-trustyai-evalhub": grafana, "ai-gateway-routing": grafana, "guardrails": grafana, "quotas": grafana}.get(s["demo"], [])
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
assert steps["templates"]["pager"] == "1 - 10 of 25" and steps["templates"]["words"]["zuno-day3-test"] is False and steps["templates"]["columns_cut"] == [], steps["templates"]
assert steps["jobs"]["columns_cut"] == ["Started"] and steps["jobs"]["pager"] == "1 - 2 of 2", steps["jobs"]
assert [v for k, v in steps["job"]["words"].items() if "Success" in k] == [True], steps["job"]
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
assert m["notes"]["session_refreshes"] >= 1 and m["notes"]["session_refresh_bytes"] == "2" and m["notes"]["session_refresh_keys"] == "none", m.get("notes")
assert m["notes"]["job"] == 102 and m["notes"]["zuno_mcp_jobs_visible"] == 1, m.get("notes")
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
if wanted dify; then
echo "== dify (a second credential)"
out="$(dify d-scout RECORD_SCOUT=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "dify: a scout exits 0, SCOUT: done" bash -c "test $rc -eq 0 && grep -q '^SCOUT: done$' <<<\"\$0\"" "$out"
expect "dify: a scout creates no conversation, runs nothing, and no save of an application reached Dify" grep -q 'left: {"conversations":1,"runs":1,"saved":0}' <<<"$out"
expect "dify: scout.json reports the sign-in, the applications and the run form" scouted d-scout '
assert list(steps) == ["enter", "owned", "sign-in", "studio", "api", "agent", "workflow", "run-form", "closed"], list(steps)
assert steps["sign-in"]["second_form"] is True and steps["sign-in"]["apps"] == {"Zuno Agent": "agent-chat", "Zuno Technical Documentation": "advanced-chat", "Zuno Confluence Search": "workflow"}, steps["sign-in"]
assert steps["api"] == {**steps["api"], "conversations": 1, "workflow_runs": 1, "profile_status": 200}, steps["api"]
assert steps["agent"]["selector"] == "textarea[placeholder*=\x27Talk\x27 i]" and steps["agent"]["url"].endswith("/app/<id>/configuration"), steps["agent"]
assert steps["workflow"]["run_selector"] and steps["run-form"]["start_selector"] and steps["run-form"]["fields"] == 1, steps["run-form"]
assert steps["closed"]["saves_refused"] == ["POST /console/api/apps/<id>/workflows/draft"], steps["closed"]
'
out="$(dify d-pass)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "dify: a good take exits 0, RESULT: PASS" bash -c "test $rc -eq 0 && grep -q '^RESULT: PASS$' <<<\"\$0\"" "$out"
expect "dify: its conversation is gone, its run stays, no save of an application reached Dify" grep -q 'left: {"conversations":1,"runs":2,"saved":0}' <<<"$out"
expect "dify: the log says the run cannot be deleted and which saves were refused" bash -c "grep -q 'succeeded; it stays in the application.s run log' <<<\"\$0\" && grep -q 'saves of the applications refused in the browser: POST /console/api/apps/<id>/workflows/draft' <<<\"\$0\"" "$out"
expect "dify: markers.json follows the contract" markers d-pass '
assert names == ["login", "studio", "agent", "q-sent", "q-done", "workflow", "run-form", "run-done", "end"], names
assert m["persona"] == "consultant-02" and m["motion_from"] == "studio" and m["status"] == "pass", m
assert len(m["created"]) == 1 and m["created"][0]["kind"] == "conversation" and m["cleaned"] is True and m["owned"] == {"before": 1, "after": 1, "same": True}, m
'
out="$(dify d-refused FAKE_REFUSE_DELETE=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "dify: a refused delete fails the take and names the conversation" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL the conversation .* of Zuno Agent was NOT deleted: DELETE answered HTTP 403' <<<\"\$0\"" "$out"
out="$(dify d-none FAKE_NO_CONVERSATION=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "dify: a chat that leaves no conversation passes, and the log says nothing was there to delete" bash -c "test $rc -eq 0 && grep -q 'its debug chat left none to delete' <<<\"\$0\"" "$out"
out="$(dify d-runfails FAKE_RUN_FAILS=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "dify: a failed workflow run fails the take, the conversation is deleted all the same" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL the workflow.s run failed' <<<\"\$0\" && grep -q 'left: {\"conversations\":1,' <<<\"\$0\"" "$out"
out="$(dify d-addresses FAKE_ADDRESSES=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "dify: an answer with a node name fails the take (the recorder's guard)" bash -c "test $rc -eq 1 && grep -q 'the page showed node names or private IP addresses' <<<\"\$0\"" "$out"
out="$(dify d-wrong DIFY_ADMIN_PASSWORD=offline-wrong-secret)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "dify: a wrong administrator password stops at Dify's form, nothing created" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL Dify refused its administrator.s sign-in' <<<\"\$0\" && grep -q 'left: {\"conversations\":1,\"runs\":1,\"saved\":0}' <<<\"\$0\"" "$out"
out="$(dify d-empty DIFY_ADMIN_PASSWORD= 2>&1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "dify: without its second credential the recorder does not start" bash -c "test $rc -eq 2 && grep -q 'DIFY_ADMIN_PASSWORD is required by this walkthrough' <<<\"\$0\"" "$out"
expect "record.sh takes a declared secret from the environment by name, and refuses to start without it" bash -c "
  cd '$here' && sed -n 's/^export const secrets = \[\(.*\)\];.*\$/\1/p' walkthroughs/dify.mjs | grep -q DIFY_ADMIN_PASSWORD \
  && grep -q 'more+=(-e \"\$name\")' record.sh && ! grep -q 'DIFY_ADMIN_PASSWORD' record.sh"
fi
if wanted guardrails; then
echo "== guardrails (Dify with its second credential, then Grafana)"
out="$(guardrails gr-scout RECORD_SCOUT=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "guardrails: a scout of both takes exits 0, SCOUT: done" bash -c "test $rc -eq 0 && grep -q '^SCOUT: done$' <<<\"\$0\"" "$out"
expect "guardrails: a scout sends nothing to Dify and writes nothing to Grafana" grep -q 'left: {"conversations":1,"runs":1,"saved":0}{"approved":0,"writes":0}' <<<"$out"
expect "guardrails: each take's scout.json reports its own screens" python3 - "$work/gr-scout" <<'PY'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1])
agent = {x["step"]: x for x in json.loads((d / "agent" / "scout.json").read_text())["steps"]}
dash = {x["step"]: x for x in json.loads((d / "dashboard" / "scout.json").read_text())["steps"]}
assert list(agent) == ["enter", "owned", "sign-in", "agent", "closed"] and agent["sign-in"]["second_form"] is True and agent["agent"]["selector"], agent
assert list(dash) == ["enter", "owned", "chain", "dashboard", "panel-detections", "closed"], list(dash)
p = dash["panel-detections"]
assert p["view"] == "viewPanel=panel-4" and p["names_dify_detected"] is False and p["not_in_window"] == ["dify (detected)"], p
assert json.loads((d / "scout.json").read_text())["status"] == "done"
PY
out="$(guardrails gr-pass)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "guardrails: a good run of both takes exits 0, RESULT: PASS" bash -c "test $rc -eq 0 && grep -q '^RESULT: PASS$' <<<\"\$0\"" "$out"
expect "guardrails: the conversation is gone, nothing written to Grafana" grep -q 'left: {"conversations":1,"runs":1,"saved":0}{"approved":0,"writes":0}' <<<"$out"
expect "guardrails: the dashboard take waited for the detection" bash -c "grep -q 'does not name dify (detected) yet: waiting' <<<\"\$0\" && grep -q 'the panel names dify (detected); its legend also names: open-webui (clean)' <<<\"\$0\"" "$out"
expect "guardrails: each take has its own markers; the conversation is cleaned" python3 - "$work/gr-pass" <<'PY'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1])
agent = json.loads((d / "agent" / "markers.json").read_text()); dash = json.loads((d / "dashboard" / "markers.json").read_text())
assert [x["name"] for x in agent["markers"]] == ["login", "agent", "q-sent", "q-done", "end"] and agent["motion_from"] == "agent", agent
assert [x["name"] for x in dash["markers"]] == ["login", "dashboard", "detections", "end"] and dash["motion_from"] == "dashboard", dash
assert agent["persona"] == "consultant-02" and len(agent["created"]) == 1 and agent["cleaned"] is True and agent["owned"]["same"] is True, agent
assert dash["persona"] == "ai-ops-01" and dash["created"] == [] and dash["cleaned"] is None, dash
PY
out="$(guardrails gr-noproof FAKE_NO_PROOF=1)"; rc=$?
echo "$out" | sed 's/^/    /' | tail -5
expect "guardrails: without the detection on the panel the dashboard take fails" bash -c "test $rc -eq 1 && grep -q 'dashboard: .*does not name dify (detected) within 4 minutes' <<<\"\$0\"" "$out"
fi
if wanted quotas; then
echo "== quotas"
out="$(quotas q-scout RECORD_SCOUT=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "quotas: a scout exits 0, SCOUT: done, nothing written to Grafana or GitHub" bash -c "test $rc -eq 0 && grep -q '^SCOUT: done$' <<<\"\$0\" && grep -q 'left: {\"writes\":0,\"github_writes\":0}' <<<\"\$0\"" "$out"
expect "quotas: the scout reads the class table and the evidence on GitHub in the window, and panel 7 alone with its columns" scouted q-scout '
assert list(steps) == ["enter", "owned", "chain", "classes", "classes-shapes", "dashboard", "panel", "evidence", "closed"], list(steps)
for name in ("classes", "evidence"):
    assert steps[name]["lead_uncovered"] is True and steps[name]["absent"] == [] and steps[name]["url"].endswith("/blob/devel/docs/demo/scenarios/governance/quotas.md"), steps[name]
    assert steps[name]["scrolled"]["steps"] > 0 and 60 <= steps[name]["lead_top"] <= 300, steps[name]
assert steps["panel"]["view"] == "viewPanel=panel-7" and steps["panel"]["no_data"] is False and steps["panel"]["not_in_window"] == [], steps["panel"]
assert steps["dashboard"]["title_on_screen"] is True and steps["closed"]["writes"] == 0, steps["dashboard"]
'
out="$(quotas q-pass)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "quotas: a good take exits 0, RESULT: PASS, nothing written" bash -c "test $rc -eq 0 && grep -q '^RESULT: PASS$' <<<\"\$0\" && grep -q 'left: {\"writes\":0,\"github_writes\":0}' <<<\"\$0\"" "$out"
expect "quotas: the markers in order, nothing created or owned, no node name at a marker" markers q-pass '
assert names == ["login", "classes", "dashboard", "panel", "evidence", "end"] and m["motion_from"] == "classes" and m["status"] == "pass", m
assert m["created"] == [] and m["cleaned"] is None and m["owned"] == {"before": 0, "after": 0, "same": True} and m["private_addresses"]["flagged"] is False, m
assert all((d / x["png"]).stat().st_size > 0 for x in m["markers"]) and (d / "recording.webm").stat().st_size > 0
'
out="$(quotas q-nodata FAKE_NO_DATA=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "quotas: a panel with No data fails the take and names the page's Start" bash -c "test $rc -eq 1 && grep -q 'RESULT: FAIL.*shows \"No data\": no token spend in the last 24 hours' <<<\"\$0\"" "$out"
out="$(quotas q-down FAKE_GITHUB_DOWN=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "quotas: GitHub out of reach fails the take and names option B" bash -c "test $rc -eq 1 && grep -q 'RESULT: FAIL.*could not be reached.*fall back to option B' <<<\"\$0\"" "$out"
out="$(quotas q-banner FAKE_GITHUB_BANNER=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "quotas: a banner over the page on GitHub fails the take: the layout fights the scroll" bash -c "test $rc -eq 1 && grep -q 'RESULT: FAIL.*not wholly inside the window on GitHub.*fall back to option B' <<<\"\$0\" && grep -q 'github_writes\":0' <<<\"\$0\"" "$out"
out="$(quotas q-reset FAKE_GITHUB_RESET=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "quotas: a GitHub page that scrolls itself back once is scrolled again, the take passes" bash -c "test $rc -eq 0 && grep -q '^RESULT: PASS$' <<<\"\$0\" && grep -q 'classes: .*\"rounds\":[2-3]' <<<\"\$0\"" "$out"
out="$(quotas q-star FAKE_STAR=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "quotas: a dashboard that writes to Grafana fails the take" bash -c "test $rc -eq 1 && grep -q 'RESULT: FAIL.*sent POST /api/user/stars/dashboard/uid/zuno-three-experiences to Grafana' <<<\"\$0\"" "$out"
fi
if wanted lora-pipeline-mlflow-kueue; then
echo "== lora-pipeline-mlflow-kueue"
out="$(lora l-scout RECORD_SCOUT=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "lora: a scout exits 0, SCOUT: done, nothing started or changed" bash -c "test $rc -eq 0 && grep -q '^SCOUT: done$' <<<\"\$0\" && grep -q 'left: {\"writes\":0}' <<<\"\$0\"" "$out"
expect "lora: the scout dumps the menu's links with their addresses, then plays the three screens" scouted l-scout '
assert list(steps) == ["enter", "owned", "menu", "pipeline", "pipeline-shapes", "trainjob", "trainjob-shapes", "mlflow", "mlflow-shapes", "closed"], list(steps)
links = {l["text"]: l["href"] for l in steps["menu"]["links"]}
assert links.get("Jobs") == "/develop-train/training-jobs" and links.get("Experiments") == "/develop-train/mlflow/experiments" and links.get("Projects") == "/projects", links
assert steps["pipeline"]["version"] == {"v0-3-0-tekos": True, "v0-4-0-tekos": False} and steps["pipeline"]["merge_export_on_screen"] is False, steps["pipeline"]
assert steps["trainjob"]["how"] == ["menu nav a[href=\x27/develop-train/training-jobs\x27]", "address /develop-train/training-jobs/zuno-mlops"], steps["trainjob"]
assert steps["mlflow"]["workspace"] == "none chosen" and steps["mlflow"]["embedded"] is True and steps["mlflow"]["how"] == ["menu nav a[href=\x27/develop-train/mlflow/experiments\x27]"], steps["mlflow"]
assert steps["pipeline"]["how"][0] == "menu nav a[href=\x27/projects\x27]" and any(f.startswith("/mlflow/") for f in steps["mlflow-shapes"]["frames"]), (steps["pipeline"], steps["mlflow-shapes"]["frames"])
'
out="$(lora l-pass)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "lora: a good take exits 0, RESULT: PASS, nothing started or changed" bash -c "test $rc -eq 0 && grep -q '^RESULT: PASS$' <<<\"\$0\" && grep -q 'left: {\"writes\":0}' <<<\"\$0\"" "$out"
expect "lora: the markers in order, nothing created or owned, no node name at a marker" markers l-pass '
assert names == ["login", "dashboard", "pipeline", "trainjob", "mlflow", "end"] and m["motion_from"] == "dashboard" and m["status"] == "pass", m
assert m["created"] == [] and m["cleaned"] is None and m["owned"] == {"before": 0, "after": 0, "same": True} and m["private_addresses"]["flagged"] is False, m
assert all((d / x["png"]).stat().st_size > 0 for x in m["markers"]) and (d / "recording.webm").stat().st_size > 0
'
out="$(lora l-ws FAKE_MLFLOW_WORKSPACE=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "lora: MLflow listing the experiment only in its workspace: the workspace zuno-mlops is chosen, the take passes" bash -c "test $rc -eq 0 && grep -q 'mlflow: {.*\"workspace\":\"button:has-text(.Workspace.)\"' <<<\"\$0\"" "$out"
out="$(lora l-notrain FAKE_NO_TRAINING=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "lora: no Jobs page fails the take and names the terminal row" bash -c "test $rc -eq 1 && grep -q 'RESULT: FAIL the Jobs page (/develop-train/training-jobs) does not show lora-comage-4c28m' <<<\"\$0\"" "$out"
out="$(lora l-v4 FAKE_VERSION=v0-4-0)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "lora: a graph of another version than v0-3-0-tekos fails the take: the page's row names it" bash -c "test $rc -eq 1 && grep -q 'RESULT: FAIL the graph on screen is not of the version v0-3-0-tekos' <<<\"\$0\"" "$out"
out="$(lora l-write FAKE_WRITE=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "lora: a page that writes to MLflow fails the take; MLflow's searches (POSTs) do not" bash -c "test $rc -eq 1 && grep -q 'RESULT: FAIL.*sent POST /mlflow/ajax-api/2.0/mlflow/runs/set-tag' <<<\"\$0\"" "$out"
out="$(lora l-dialog FAKE_DIALOG=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "lora: a dialog over the dashboard fails the take, nothing dismissed" bash -c "test $rc -eq 1 && grep -q 'RESULT: FAIL a dialog covers the dashboard' <<<\"\$0\"" "$out"
fi
if wanted unifai-agents; then
echo "== unifai-agents (two personas, a team workspace)"
out="$(agents a-scout RECORD_SCOUT=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "agents: a scout of both personas exits 0, SCOUT: done" bash -c "test $rc -eq 0 && grep -q '^SCOUT: done$' <<<\"\$0\"" "$out"
expect "agents: a scout creates no session, opens no team setting" grep -q 'left: {"sessions":2,"touched":0}' <<<"$out"
expect "agents: each persona's scout.json reports its selector, the hub and the dialog" python3 - "$work/a-scout" <<'PY'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1])
for name, teams in (("consultant-02", ["agent-arkos", "agent-tekos", "consultant"]), ("ai-ops-01", ["agent-tekos", "ops"])):
    s = json.loads((d / name / "scout.json").read_text()); steps = {x["step"]: x for x in s["steps"]}
    assert list(steps) == ["enter", "owned", "selector", "hub", "workflows", "closed"] and all(x["ok"] for x in s["steps"]), s
    assert steps["selector"]["listed"] == {t: True for t in teams}, steps["selector"]
    assert steps["hub"]["team_id_read"] is True and steps["hub"]["sessions"] == 1 and steps["hub"]["session_open"] is True and steps["hub"]["add_selector"], steps["hub"]
    assert steps["workflows"] == {**steps["workflows"], "workflow_exact_matches": 1, "start_button": 1, "switches": 1}, steps["workflows"]
    assert "Earlier" not in json.dumps(s) and s["changes"] == [], s["changes"]
PY
out="$(agents a-pass)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "agents: a good run of both personas exits 0, RESULT: PASS" bash -c "test $rc -eq 0 && grep -q '^RESULT: PASS$' <<<\"\$0\"" "$out"
expect "agents: both sessions are gone, the other member's is kept, no team setting opened" grep -q 'left: {"sessions":2,"touched":0}' <<<"$out"
expect "agents: the log carries the answers and what each persona's screen names" bash -c "grep -q 'answer 2 (.*): Common causes' <<<\"\$0\" && grep -q 'answer 1 (.*): k8s.events.read: the pod a2a-gateway' <<<\"\$0\" && grep -q 'a k8s read tool IS named' <<<\"\$0\" && grep -q 'a k8s read tool is NOT named' <<<\"\$0\"" "$out"
expect "agents: each persona has its own markers, its own session, cleaned" python3 - "$work/a-pass" <<'PY'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1])
c = json.loads((d / "consultant-02" / "markers.json").read_text()); o = json.loads((d / "ai-ops-01" / "markers.json").read_text())
assert [x["name"] for x in c["markers"]] == ["login", "workspaces", "hub", "q1-sent", "q1-done", "q2-sent", "q2-done", "end"] and c["motion_from"] == "workspaces", c
assert [x["name"] for x in o["markers"]] == ["login", "hub", "q-sent", "q-done", "end"] and o["motion_from"] == "hub", o
for m in (c, o):
    assert m["status"] == "pass" and len(m["created"]) == 1 and m["cleaned"] is True and m["owned"] == {"before": 1, "after": 1, "same": True}, m
assert c["created"][0]["id"] != o["created"][0]["id"]
PY
out="$(agents a-refused FAKE_REFUSE_DELETE=1)"; rc=$?
echo "$out" | sed 's/^/    /' | tail -4
expect "agents: a refused delete fails the take and names the session" bash -c "test $rc -eq 1 && grep -q 'was NOT deleted' <<<\"\$0\"" "$out"
out="$(agents a-addresses FAKE_ADDRESSES=1)"; rc=$?
echo "$out" | sed 's/^/    /' | tail -4
expect "agents: a cluster answer that names a node fails ai-ops-01's take, its session deleted all the same" bash -c "test $rc -eq 1 && grep -q 'ai-ops-01: .*the page showed node names or private IP addresses' <<<\"\$0\" && grep -q 'left: {\"sessions\":2,' <<<\"\$0\"" "$out"
fi
if wanted observability-trace; then
echo "== observability-trace (UnifAI team chat, then the Tempo search UI)"
out="$(trace t-scout RECORD_SCOUT=1 FAKE_TRACE_NOW=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "trace: a scout of both takes exits 0, SCOUT: done" bash -c "test $rc -eq 0 && grep -q '^SCOUT: done$' <<<\"\$0\"" "$out"
expect "trace: a scout creates no session, approves nothing, writes nothing to the Tempo UI" grep -q 'left: {"sessions":2,"touched":0}{"approved":0,"writes":0}' <<<"$out"
expect "trace: the scout opens the newest trace and a model_call span, read only" python3 - "$work/t-scout" <<'PY'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1])
chat = {x["step"]: x for x in json.loads((d / "chat" / "scout.json").read_text())["steps"]}
tr = {x["step"]: x for x in json.loads((d / "trace" / "scout.json").read_text())["steps"]}
assert list(chat) == ["enter", "owned", "selector", "hub", "closed"] and chat["hub"]["team_id_read"] is True and chat["hub"]["sessions"] == 1, chat
assert list(tr) == ["enter", "owned", "chain", "search", "trace", "tags", "closed"], list(tr)
assert [c["step"] for c in tr["chain"]["chain"]] == ["proxy", "chooser", "keycloak", "application"] and tr["chain"]["authorize_shown"] is False, tr["chain"]
assert tr["search"]["results"] == 1 and "service=ai-gateway" in tr["search"]["url"] and "lookback=15m" in tr["search"]["url"], tr["search"]
assert tr["trace"]["model_call_spans"] == 2 and tr["trace"]["url"].endswith("/trace/<id>"), tr["trace"]
assert len(tr["tags"]["tags"]) == 12 and tr["tags"]["in_window"] == {"zuno.persona": True, "zuno.client": True, "zuno.agent": True} and tr["tags"]["private_addresses"] == 0, tr["tags"]
PY
out="$(trace t-pass)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "trace: a good run of both takes exits 0, RESULT: PASS" bash -c "test $rc -eq 0 && grep -q '^RESULT: PASS$' <<<\"\$0\"" "$out"
expect "trace: the session is gone, nothing approved, nothing written" grep -q 'left: {"sessions":2,"touched":0}{"approved":0,"writes":0}' <<<"$out"
expect "trace: the trace take searched again until a trace showed" bash -c "grep -q 'the search finds no trace yet: searching again' <<<\"\$0\" && grep -q 'the search lists 1 trace' <<<\"\$0\" && grep -q 'page shows no question text' <<<\"\$0\"" "$out"
expect "trace: each take has its own markers; the session is cleaned" python3 - "$work/t-pass" <<'PY'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1])
chat = json.loads((d / "chat" / "markers.json").read_text()); tr = json.loads((d / "trace" / "markers.json").read_text())
assert [x["name"] for x in chat["markers"]] == ["login", "hub", "q-sent", "q-done", "end"] and chat["motion_from"] == "hub", chat
assert [x["name"] for x in tr["markers"]] == ["login", "search", "trace", "tags", "end"] and tr["motion_from"] == "search", tr
assert chat["persona"] == "consultant-02" and len(chat["created"]) == 1 and chat["cleaned"] is True and chat["owned"]["same"] is True, chat
assert tr["persona"] == "ai-ops-01" and tr["created"] == [] and tr["cleaned"] is None, tr
assert tr["notes"] == {"traces_listed": 1} and "notes" not in chat, (tr.get("notes"), chat.get("notes"))   # a walkthrough's own notes
PY
out="$(trace t-authorize FAKE_AUTHORIZE=1 RECORD_SCOUT=1 FAKE_TRACE_NOW=1)"; rc=$?
echo "$out" | sed 's/^/    /' | tail -3
expect "trace: the Tempo UI's declared Authorize Access page is approved once, and the scout goes on" bash -c "test $rc -eq 0 && grep -q 'left: .*{\"approved\":1,\"writes\":0}' <<<\"\$0\"" "$out"
expect "trace: its scout.json says so, and declares the change" python3 - "$work/t-authorize" <<'PY'
import json, pathlib, sys
s = json.loads((pathlib.Path(sys.argv[1]) / "trace" / "scout.json").read_text()); steps = {x["step"]: x for x in s["steps"]}
assert steps["chain"]["authorized"] is True and [c["step"] for c in steps["chain"]["chain"]] == ["proxy", "chooser", "keycloak", "authorize", "application"], steps["chain"]
assert len(s["changes"]) == 1 and s["changes"][0].startswith("approves OpenShift's Authorize Access page for the Tempo search UI's proxy as ai-ops-01"), s["changes"]
PY
out="$(trace t-authorize-other FAKE_AUTHORIZE=other RECORD_SCOUT=1)"; rc=$?
echo "$out" | sed 's/^/    /' | tail -3
expect "trace: an Authorize Access page of another client stops the scout, nothing approved" bash -c "test $rc -eq 1 && grep -q 'left: .*{\"approved\":0,\"writes\":0}' <<<\"\$0\"" "$out"
out="$(trace t-addresses FAKE_ADDRESSES=1)"; rc=$?
echo "$out" | sed 's/^/    /' | tail -3
expect "trace: a span whose Process line holds an address fails the trace take (the recorder's guard)" bash -c "test $rc -eq 1 && grep -q 'trace: .*the page showed node names or private IP addresses' <<<\"\$0\"" "$out"
out="$(trace t-notags FAKE_NO_TAGS=1)"; rc=$?
echo "$out" | sed 's/^/    /' | tail -3
expect "trace: a span without its zuno tags fails the take before its marker" bash -c "test $rc -eq 1 && grep -q 'trace: .*the model_call span does not show its tags' <<<\"\$0\"" "$out"
fi
if wanted genai-playground; then
echo "== genai-playground"
out="$(genai g-scout RECORD_SCOUT=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "genai: a scout exits 0, SCOUT: done, no question asked, nothing written, the lock never clicked" bash -c "test $rc -eq 0 && grep -q '^SCOUT: done$' <<<\"\$0\" && grep -q 'left: {\"answers\":0,\"writes\":0,\"locks\":0}' <<<\"\$0\"" "$out"
expect "genai: the scout reports each screen, the MCP row as this browser sees it, the store-like requests and the storage keys by name" scouted g-scout '
assert list(steps) == ["enter", "owned", "sign-in", "playground", "playground-shapes", "model", "model-shapes", "mcp", "mcp-shapes", "storage", "closed"], list(steps)
assert steps["playground"]["url"] == "/maas-consumer-portal/gen-ai-studio/playground/zuno-playground" and steps["playground"]["create_button"] is False, steps["playground"]
assert steps["mcp"]["row"]["listed"] is True and steps["mcp"]["row"]["connected"] is False and steps["mcp"]["row"]["tools"] == "0 active", steps["mcp"]
assert "GET /gen-ai/api/v1/conversations" in steps["storage"]["store_like_requests"] and isinstance(steps["storage"]["keys"]["local"], list), steps["storage"]
assert steps["model"]["chosen"] == [] and steps["model"]["before"] == {"model": True, "subscription": "gpt-oss-20b-agents"} and steps["model"]["subscription_shown"] == "gpt-oss-20b-agents", steps["model"]
'
out="$(genai g-saved RECORD_SCOUT=1 FAKE_MCP_SAVED=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "genai: a connection kept on the server is found by the fresh browser of a scout, by its tools cell" scouted g-saved '
assert steps["mcp"]["row"]["connected"] is True and steps["mcp"]["row"]["tools"] == "9 active", steps["mcp"]
'
out="$(genai g-ssar RECORD_SCOUT=1 FAKE_SSAR=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "genai: a scout refuses what the page POSTs on its own, lists it in its step, and fails at the end" bash -c "test $rc -eq 1 && grep -q 'scout closed: FAILED.*POST /api/k8s/apis/authorization.k8s.io/v1/selfsubjectaccessreviews' <<<\"\$0\" && grep -q 'left: {\"answers\":0,\"writes\":0,' <<<\"\$0\"" "$out"
out="$(genai g-pass)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "genai: a good take exits 0, RESULT: PASS, one question answered, nothing else written, the lock never clicked" bash -c "test $rc -eq 0 && grep -q '^RESULT: PASS$' <<<\"\$0\" && grep -q 'left: {\"answers\":1,\"writes\":0,\"locks\":0}' <<<\"\$0\" && grep -q 'the 0:45 question sent POST /gen-ai/api/v1/responses' <<<\"\$0\"" "$out"
expect "genai: the markers of rows 0:00 and 0:45 and the MCP still, nothing created or owned" markers g-pass '
assert names == ["login", "playground", "q1-sent", "q1-done", "mcp", "end"] and m["motion_from"] == "playground" and m["status"] == "pass", m
assert m["created"] == [] and m["cleaned"] is None and m["owned"] == {"before": 0, "after": 0, "same": True} and m["private_addresses"]["flagged"] is False, m
assert all((d / x["png"]).stat().st_size > 0 for x in m["markers"]) and (d / "recording.webm").stat().st_size > 0
'
out="$(genai g-model FAKE_OTHER_MODEL=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "genai: another model shown is changed in its list, the choice sends nothing, the take passes" bash -c "test $rc -eq 0 && grep -q '\"chosen\":\[{\"what\":\"model\",\"sent\":\[\]}\]' <<<\"\$0\"" "$out"
out="$(genai g-write FAKE_OTHER_MODEL=1 FAKE_SELECT_WRITE=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "genai: a model choice that would write is refused in the browser and fails the take" bash -c "test $rc -eq 1 && grep -q 'RESULT: FAIL.*wanted to send PUT /gen-ai/api/v1/preferences' <<<\"\$0\" && grep -q '\"writes\":0' <<<\"\$0\"" "$out"
out="$(genai g-create FAKE_CREATE_ONLY=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "genai: a project with no playground fails the take, Create playground never pressed" bash -c "test $rc -eq 1 && grep -q 'RESULT: FAIL.*shows \"Create playground\" instead of its playground' <<<\"\$0\" && grep -q 'left: {\"answers\":0,\"writes\":0,' <<<\"\$0\"" "$out"
fi
if wanted maas-portal-api-keys; then
echo "== maas-portal-api-keys (a secret created during the take)"
out="$(maas m-scout RECORD_SCOUT=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "maas: a scout exits 0, SCOUT: done" bash -c "test $rc -eq 0 && grep -q '^SCOUT: done$' <<<\"\$0\"" "$out"
expect "maas: a scout creates no key" grep -q 'left: {"keys":1,"live":1,"checks":0}' <<<"$out"
expect "maas: scout.json reports the list's shape and the dialog, no key value" scouted m-scout '
assert list(steps) == ["enter", "owned", "portal", "keys", "create-dialog", "closed"], list(steps)
assert steps["keys"]["list_path"] == "/maas-consumer-portal/api/v1/api-keys" and steps["keys"]["fields"] == ["id", "name", "status", "subscription"] and steps["keys"]["not_revoked"] == 1, steps["keys"]
assert steps["create-dialog"]["subscription_on_screen"] is True and steps["create-dialog"]["submit_selector"] and steps["create-dialog"]["name_selector"], steps["create-dialog"]
assert "sk-oai-" not in json.dumps(s)
'
out="$(maas m-pass 2>&1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "maas: a good take exits 0, RESULT: PASS" bash -c "test $rc -eq 0 && grep -q '^RESULT: PASS$' <<<\"\$0\"" "$out"
expect "maas: its key is revoked (one more key, no more live key)" grep -q 'left: {"keys":2,"live":1,"checks":0}' <<<"$out"
expect "maas: the log says the key was revoked and proved refused" grep -q 'revoked (delete HTTP 204); the gateway now answers 403 with it' <<<"$out"
expect "maas: markers.json follows the contract" markers m-pass '
assert names == ["login", "portal", "keys", "create-form", "created", "calls", "answer", "end"], names
assert m["persona"] == "ai-dev-01" and m["status"] == "pass" and len(m["created"]) == 1 and m["created"][0]["kind"] == "api-key" and m["cleaned"] is True and m["owned"] == {"before": 1, "after": 1, "same": True}, m
'
expect "maas: the key the server made is in no file of the take and in no line of its output; the page drew the mask" python3 - "$work/m-pass" "$out" <<'PY'
import pathlib, re, sys
d = pathlib.Path(sys.argv[1])
key = re.compile(rb"sk-oai-[A-Za-z0-9_-]{8,}")
for f in d.rglob("*"):
    if f.is_file() and f.suffix in (".json", ".txt", ".log"): assert not key.search(f.read_bytes()), f
assert not key.search(sys.argv[2].encode()), "a key in the recorder's output"
assert "the portal received a masked value" in sys.argv[2]
PY
out="$(maas m-refused FAKE_REFUSE_REVOKE=1)"; rc=$?
echo "$out" | sed 's/^/    /' | tail -3
expect "maas: a key that still answers after its revoke fails the take and names it, never its value" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL the key k-[0-9a-f]* named zuno-demo-gif-[0-9]* was NOT revoked: its delete answered HTTP 403 and the gateway still answers 200 with it; revoke it by hand' <<<\"\$0\" && ! grep -q 'sk-oai-[A-Za-z0-9_-]\{8,\}' <<<\"\$0\"" "$out"
out="$(maas m-noid FAKE_NO_ID=1)"; rc=$?
echo "$out" | sed 's/^/    /' | tail -3
expect "maas: a create answer without an id: the key is found by this take's own name and revoked" bash -c "test $rc -eq 0 && grep -q 'left: {\"keys\":2,\"live\":1,' <<<\"\$0\"" "$out"
out="$(maas m-reread FAKE_REREAD=1)"; rc=$?
echo "$out" | sed 's/^/    /' | tail -3
expect "maas: a portal that sends the shown key back to its server stops the take, and the key is revoked" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL the portal sent the key it was shown back to its server (PUT /maas-consumer-portal/api/v1/check)' <<<\"\$0\" && grep -q 'left: {\"keys\":2,\"live\":1,\"checks\":1}' <<<\"\$0\"" "$out"
fi
if wanted openclaw; then
echo "== openclaw (a second credential typed in a plain field; no take yet)"
out="$(claw c-scout RECORD_SCOUT=1 2>&1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "openclaw: a scout exits 0, SCOUT: done, and sends nothing" bash -c "test $rc -eq 0 && grep -q '^SCOUT: done$' <<<\"\$0\" && grep -q 'left: {\"sent\":0}' <<<\"\$0\"" "$out"
expect "openclaw: scout.json describes the connected Control UI and keeps no session title" scouted c-scout '
assert list(steps) == ["enter", "owned", "control-ui", "controls", "composer", "closed"], list(steps)
ui = steps["control-ui"]
assert ui["on_its_own_address"] is True and ui["password_field_still_on_screen"] is False and ui["new_session_selector"] and ui["storage_added"] == ["local:openclaw.control.settings"], ui
assert steps["composer"]["selector"] == "textarea" and any(c["label"] == "Session menu" for c in steps["controls"]["controls"]), steps["controls"]
assert "FAKE-EARLIER-SESSION-TITLE" not in json.dumps(s)
'
expect "openclaw: the password typed in the plain field was masked in the scout's pictures' page (no file holds it)" bash -c "! grep -r -l offline-claw-secret '$work/c-scout' >/dev/null"
out="$(claw c-take 2>&1)"; rc=$?
echo "$out" | sed 's/^/    /' | tail -3
expect "openclaw: a take is refused by the walkthrough itself, before anything is sent" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL openclaw is not taken yet: a take would leave a session' <<<\"\$0\" && grep -q 'left: {\"sent\":0}' <<<\"\$0\"" "$out"
out="$(claw c-unmask RECORD_SCOUT=1 FAKE_UNMASK=1 2>&1)"; rc=$?
echo "$out" | sed 's/^/    /' | tail -3
expect "openclaw: a field that does not stay masked is emptied and stops the scout" bash -c "test $rc -eq 1 && grep -q 'left: {\"sent\":0}' <<<\"\$0\"" "$out"
expect "openclaw: scout.json says the field did not stay masked" python3 - "$work/c-unmask" <<'PY'
import json, pathlib, sys
s = json.loads((pathlib.Path(sys.argv[1]) / "scout.json").read_text())
assert "did not stay masked" in s["steps"][0]["error"], s["steps"][0]
PY
out="$(claw c-wrong RECORD_SCOUT=1 OPENCLAW_UI_PASSWORD=offline-claw-wrong 2>&1)"; rc=$?
echo "$out" | sed 's/^/    /' | tail -3
expect "openclaw: a wrong Control UI password stops at the gate" python3 - "$work/c-wrong" <<'PY'
import json, pathlib, sys
s = json.loads((pathlib.Path(sys.argv[1]) / "scout.json").read_text())
assert "could not connect to its gateway" in s["steps"][0]["error"], s["steps"][0]
PY
fi
if wanted a2a-delegation-approval; then
echo "== a2a-delegation-approval (the take clicks Approve)"
out="$(a2a x-scout RECORD_SCOUT=1)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "a2a: a scout exits 0, SCOUT: done, creates no session and launches nothing" bash -c "test $rc -eq 0 && grep -q '^SCOUT: done$' <<<\"\$0\" && grep -q 'left: {\"sessions\":2,\"touched\":0,\"launches\":0}' <<<\"\$0\"" "$out"
expect "a2a: scout.json reports the hub of agent-arkos and declares the Approve click" scouted x-scout '
assert list(steps) == ["enter", "owned", "selector", "hub", "workflows", "closed"], list(steps)
assert steps["selector"]["listed"]["agent-arkos"] is True and steps["hub"]["team_id_read"] is True and steps["workflows"]["workflow_exact_matches"] == 1, steps
'
out="$(a2a x-pass)"; rc=$?
echo "$out" | sed 's/^/    /'
expect "a2a: a good take exits 0, RESULT: PASS" bash -c "test $rc -eq 0 && grep -q '^RESULT: PASS$' <<<\"\$0\"" "$out"
expect "a2a: its session is gone and exactly one AAP job was launched" grep -q 'left: {"sessions":2,"touched":0,"launches":1}' <<<"$out"
expect "a2a: markers.json follows the contract and notes the job" markers x-pass '
assert names == ["login", "hub", "q-sent", "card", "approved", "q-done", "end"], names
assert m["status"] == "pass" and len(m["created"]) == 1 and m["cleaned"] is True and m["owned"]["same"] is True, m
assert m["notes"] == {"approvals": 1, "rejections": 0, "aap_job": "1401"}, m["notes"]
'
out="$(a2a x-second FAKE_SECOND_CARD=1)"; rc=$?
echo "$out" | sed 's/^/    /' | tail -3
expect "a2a: a second card is rejected: still one job" bash -c "test $rc -eq 0 && grep -q 'a second approval card came: rejected' <<<\"\$0\" && grep -q '\"launches\":1}' <<<\"\$0\"" "$out"
out="$(a2a x-other FAKE_OTHER_TOOL=1)"; rc=$?
echo "$out" | sed 's/^/    /' | tail -3
expect "a2a: a card for another tool is never approved; the take fails, rejects it and deletes its session" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL the approval card on screen does not name aap.cluster.audit: nothing is approved' <<<\"\$0\" && grep -q 'left: {\"sessions\":2,\"touched\":0,\"launches\":0}' <<<\"\$0\"" "$out"
out="$(a2a x-nodelegation FAKE_NO_DELEGATION=1)"; rc=$?
echo "$out" | sed 's/^/    /' | tail -3
expect "a2a: a turn without delegation fails the take and says the turn was spent; nothing launched" bash -c "test $rc -eq 1 && grep -q '^RESULT: FAIL Arkos answered without delegating' <<<\"\$0\" && grep -q '\"launches\":0}' <<<\"\$0\"" "$out"
fi
expect "the password is in no file of any take" bash -c "! grep -r -l offline-test '$work' >/dev/null"
expect "no declared secret value is in any file of any take" bash -c "! grep -r -l -e offline-admin-secret -e offline-wrong-secret -e offline-claw-secret -e offline-claw-wrong '$work' >/dev/null"
expect "no key created during a take is in any text file of any take" bash -c "! grep -r -l -I -E 'sk-oai-[A-Za-z0-9_-]{8,}' '$work' >/dev/null"
[[ $failed -eq 0 ]] && echo "RESULT: PASS" || echo "RESULT: FAIL"
exit $failed
