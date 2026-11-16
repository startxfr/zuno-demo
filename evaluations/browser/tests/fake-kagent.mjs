// WP-288: a stand-in for kagent, its front door and Keycloak, for the offline test of walkthroughs/kagent.mjs
// (tests/walkthroughs-offline.sh). It serves what the walkthrough GUESSES kagent shows (no scout has run yet): the
// sign-in form, the onboarding wizard with "Skip wizard", the agent list, the agent's chat page with its five tools,
// and a session API (list, delete). It proves the walkthrough's own logic, not kagent's real selectors.
// The session list always holds one earlier session. Knobs: FAKE_REFUSE_DELETE=1 the delete answers 403;
// FAKE_SKIP_POSTS=1 "Skip wizard" writes to the server; FAKE_LEAK=1 the Secret question is answered with data instead of a refusal; FAKE_NO_URL=1 the address bar never
// shows the session's id (the walkthrough then finds it as the one new session of the list, named like its question);
// FAKE_OTHER_NAME=1 names that session otherwise, so it cannot be told apart. No cluster, no model.
import http from "node:http";
import crypto from "node:crypto";

const port = Number(process.env.FAKE_PORT || 8098);
const EARLIER = "11111111-1111-1111-1111-111111111111";
const sessions = new Map([[EARLIER, { messages: [] }]]);
let wizardAgents = 0;   // agents the wizard created: a take or a scout must leave it at 0

const LOGIN = `<!doctype html><title>Sign in</title><form method="get" action="/signin"><input id="username" name="u">
<input id="password" name="p" type="password"><button id="kc-login">Sign In</button></form>`;

const APP = `<!doctype html><title>kagent (fake)</title>
<style>body{font:16px sans-serif;margin:24px} textarea{width:600px;height:40px} .card{border:1px solid #888;padding:8px;margin:8px 0;display:block}</style>
<div id="wizard" hidden><h2>Welcome to kagent</h2><button id="create" onclick="fetch('/fake/wizard',{method:'POST'})">Create my first agent</button>
<button onclick="localStorage.setItem('skipped','1');${process.env.FAKE_SKIP_POSTS === "1" ? "fetch('/api/onboarding',{method:'POST'});" : ""}render()">Skip wizard</button></div>
<div id="list" hidden><h2>Agents</h2><a class="card" href="/agents/zuno-kagent/zuno-sre/chat">zuno-sre</a></div>
<div id="chat" hidden><h2>zuno-kagent/zuno-sre</h2>
<aside><a href="/agents/zuno-kagent/zuno-sre/chat/${EARLIER}">An earlier session</a>
<ul><li>k8s.resource.read</li><li>k8s.resource.list</li><li>k8s.events.read</li><li>k8s.logs.read</li><li>metrics.query</li></ul></aside>
<div id="messages"></div><form onsubmit="return false"><textarea id="in" placeholder="Send a message..."></textarea><button type="button" id="send">Send</button></form></div>
<script>
const $ = (id) => document.getElementById(id);
let sid = (location.pathname.match(/\\/chat\\/([^/]+)$/) || [])[1] || "";
// Like kagent on 2026-11-16: the agent list shows first, and the wizard replaces it a moment after in a browser
// that has not skipped it. FAKE_SKIP_POSTS=1 makes the skip write to the server, which a take must refuse.
let late = false;
function render() {
  const chat = location.pathname.startsWith("/agents/zuno-kagent/zuno-sre");
  const wizard = late && !localStorage.getItem("skipped") && !chat;
  // The agent list is read by a server action: a POST to the current path with a Next-Action id, like Next.js.
  if ($("list").hidden && !wizard && !chat) fetch(location.pathname, { method: "POST", headers: { "next-action": "list-agents", "content-type": "text/plain;charset=UTF-8" }, body: "[]" });
  $("wizard").hidden = !wizard;
  $("list").hidden = wizard || chat;
  $("chat").hidden = !chat;
}
render();
setTimeout(() => { late = true; render(); }, 1500);
async function show() {
  if (!sid) return;
  const r = await fetch("/api/sessions/" + sid);
  if (r.status !== 200) return;
  const list = (await r.json()).data.messages;
  if ($("messages").children.length === list.length) return;
  $("messages").innerHTML = "";
  for (const m of list) { const p = document.createElement("p"); p.textContent = m.text; $("messages").appendChild(p); }
}
setInterval(show, 300);
// FAKE_ENTER=newline: Enter only adds a line, as kagent did on 2026-11-16; the Send button sends.
// FAKE_ENTER=dead: nothing sends at all.
const mode = ${JSON.stringify(process.env.FAKE_ENTER || "")};
async function send() {
  const text = $("in").value; $("in").value = "";
  const r = await fetch("/api/a2a/zuno-kagent/zuno-sre", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, session: sid }) });
  const made = (await r.json()).session;
  if (!sid) { sid = made; if (!${process.env.FAKE_NO_URL === "1"}) history.replaceState(null, "", "/agents/zuno-kagent/zuno-sre/chat/" + sid); }
}
$("in").addEventListener("keydown", (e) => {
  if (e.key !== "Enter" || mode) return;
  e.preventDefault();
  send();
});
$("send").addEventListener("click", () => { if (mode !== "dead") send(); });
</script>`;

function answer(text) {
  if (/Secret/.test(text)) return process.env.FAKE_LEAK === "1" ? "Here is the data: root_token: s.FAKEFAKEFAKE" : "I cannot read Secret or ConfigMap data.";
  return "k8s.resource.list called. 20 pods are Running, 0 are not Running.";
}

http.createServer((req, res) => {
  const u = new URL(req.url, "http://x");
  const signed = /(^|; )s=1/.test(req.headers.cookie || "");
  const json = (code, body) => { res.writeHead(code, { "Content-Type": "application/json" }); res.end(JSON.stringify(body)); };
  const one = u.pathname.match(/^\/api\/sessions\/([^/]+)$/);
  if (u.pathname === "/fake/count") return json(200, { sessions: sessions.size, wizard_agents: wizardAgents });
  if (u.pathname === "/fake/wizard") { wizardAgents += 1; return json(200, {}); }
  if (u.pathname === "/signin") { res.writeHead(302, { "Set-Cookie": "s=1; Path=/", Location: "/" }); return res.end(); }
  if (!signed) { res.writeHead(200, { "Content-Type": "text/html" }); return res.end(LOGIN); }
  if (req.method === "POST" && req.headers["next-action"]) return json(200, { agents: ["zuno-sre"] });
  if (u.pathname === "/api/onboarding") return json(200, {});
  if (u.pathname === "/api/sessions" && req.method === "GET") {
    // Like the guess: the bare path answers only with the user id the UI uses.
    if (u.searchParams.get("user_id") !== "admin@kagent.dev") return json(400, { error: "user_id is required" });
    return json(200, { data: [...sessions.keys()].map((id) => ({ id, name: sessions.get(id).name || "a session" })) });
  }
  if (one && req.method === "GET") return sessions.has(one[1]) ? json(200, { data: sessions.get(one[1]) }) : json(404, {});
  if (one && req.method === "DELETE") {
    if (process.env.FAKE_REFUSE_DELETE === "1") return json(403, { error: "forbidden" });
    return sessions.delete(one[1]) ? json(200, { message: "deleted" }) : json(404, {});
  }
  if (u.pathname.startsWith("/api/a2a/") && req.method === "POST") {
    let raw = "";
    req.on("data", (c) => { raw += c; });
    req.on("end", () => {
      const { text, session } = JSON.parse(raw);
      const id = session || crypto.randomUUID();
      if (!sessions.has(id)) sessions.set(id, { messages: [], name: process.env.FAKE_OTHER_NAME === "1" ? "Somebody else's question" : text.slice(0, 40) });
      const s = sessions.get(id);
      s.messages.push({ text });
      setTimeout(() => { if (sessions.has(id)) s.messages.push({ text: answer(text) }); }, 1200);
      json(200, { session: id });
    });
    return undefined;
  }
  res.writeHead(200, { "Content-Type": "text/html" });
  return res.end(APP);
}).listen(port, "127.0.0.1");
