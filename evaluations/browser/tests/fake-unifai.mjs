// WP-288: a stand-in for UnifAI and Keycloak, for the offline test of walkthroughs/unifai-live-rag.mjs and of the
// shared unifai* helpers (tests/walkthroughs-offline.sh). It serves what the fork's UI source says UnifAI shows (no
// scout has run yet): "Login using SSO", the sidebar links, the Document Library with the two demo files Done, the
// chats page with "Add new chat from flow", its dialog (search box, workflows with a Human-in-the-Loop switch, Cancel,
// Add) and the session API (/api2/sessions/*). A session exists as soon as Add is clicked, as in UnifAI.
// For identity-personas it also has the Personal | Team switch and the workspace selector, whose teams are the
// signed-in user's (FAKE_WRONG_TEAMS=1 gives sale-01 the workspace `consultant` too); clicking a workspace counts as
// touched. The session list always holds one earlier session. Knobs: FAKE_REFUSE_DELETE=1 the delete answers success false;
// FAKE_WRONG_ANSWER=1 the first answer lacks ZN-CAR-7; FAKE_NO_FILES=1 the library is empty; FAKE_REFUSE_MODEL=1 the
// answer carries a rate-limit error. No cluster, no model.
import http from "node:http";
import crypto from "node:crypto";

const port = Number(process.env.FAKE_PORT || 8097);
const EARLIER = "22222222-2222-2222-2222-222222222222";
const sessions = new Map([[EARLIER, { blueprint: "consultant-01-my-assistant", status: "COMPLETED", messages: [] }]]);
// unifai-agents (FAKE_TEAM_MODE=1): one earlier session of another member in the team workspace agent-tekos.
if (process.env.FAKE_TEAM_MODE === "1") sessions.set("33333333-3333-3333-3333-333333333333", { blueprint: "tekos", status: "COMPLETED", messages: [], team: "team-agent-tekos" });
let touched = 0;   // clicks on a row's checkbox or a Human-in-the-Loop switch: a take or a scout must leave it at 0

const WELCOME = `<!doctype html><title>UnifAI (fake)</title><h1>Welcome to UnifAI</h1><button onclick="location.href='/api1/auth/login'">Login using SSO</button>`;
const LOGIN = `<!doctype html><title>Sign in</title><form method="get" action="/cb"><input id="username" name="u">
<input id="password" name="p" type="password"><button id="kc-login">Sign In</button></form>`;
const FILES = process.env.FAKE_NO_FILES === "1" ? "" : ["travel-and-expense-policy.md", "on-call-rota-handbook.md"].map((f) =>
  `<tr><td><input type="checkbox" onclick="fetch('/fake/touched',{method:'POST'})"></td><td>${f}</td><td>consultant-01</td><td>Done</td></tr>`).join("");

const APP = `<!doctype html><title>UnifAI (fake)</title>
<style>body{font:16px sans-serif;margin:0;display:flex} nav{width:200px;padding:16px} main{padding:16px;flex:1} textarea{width:600px;height:40px}
[role=dialog]{position:fixed;top:40px;left:240px;width:700px;border:1px solid #888;background:#fff;padding:16px} .flow{padding:6px;display:flex;gap:12px}</style>
<nav><button id="personal">Personal</button><button id="team"><svg width="8" height="8"></svg>Team</button>
<div id="teambox" hidden><button id="selector"><span id="selected">Select team</span><svg class="lucide lucide-chevron-down" width="8" height="8"></svg></button>
<div id="overlay" class="fixed inset-0" style="position:fixed;inset:0" hidden></div>
<div id="teams" style="position:relative;z-index:2" hidden></div></div>
<a href="/documents">Documents</a><br><a href="/agentic-chats">Agentic Chats</a></nav>
<main>
<div id="home" hidden><h2>Get to know UnifAI</h2></div>
<div id="docs" hidden><h2>Document Library</h2><table>${FILES}</table></div>
<div id="chats" hidden><span id="count"></span> <button title="Add new chat from flow" id="add">+</button>
<div id="thread" style="height:140px;overflow-y:auto;border:1px solid #888"><div id="messages"></div></div><textarea id="in" hidden placeholder="Type your message..."></textarea><div id="live"></div></div>
<div role="dialog" id="notice" hidden style="top:200px"><h3>AI Disclosure</h3><p>You are about to use a Red Hat tool that utilizes AI technology.</p>
<input type="checkbox" id="dont-show-again" onclick="fetch('/fake/touched',{method:'POST'})"><label for="dont-show-again">Don't show message again</label>
<button id="accept">Accept</button></div>
<div role="dialog" id="dialog" hidden><h3>Add New Chat from Flow</h3><input placeholder="Search workflows..." id="search">
<div id="flows"></div><button id="cancel">Cancel</button><button id="confirm">Add</button></div>
</main>
<script>
const $ = (id) => document.getElementById(id);
// Like UnifAI on 2026-11-16: the "AI Disclosure" notice covers the application a moment after each sign-in, until
// Accept; the acceptance is kept in the tab's sessionStorage. Ticking its checkbox counts as touched, and Accept
// then writes to the server, as in UnifAI. FAKE_ACCEPT_POSTS=1 makes Accept alone write, which a take must refuse.
if (sessionStorage.getItem("ai-accepted")) $("notice").remove();
else setTimeout(() => { $("notice").hidden = false; }, 700);
if ($("accept")) $("accept").onclick = () => {
  if ($("dont-show-again").checked || __ACCEPT_POSTS__) fetch("/api1/terms/approve", { method: "POST" });
  sessionStorage.setItem("ai-accepted", "true"); $("notice").remove();
};
// The Team switch and the workspace selector: screen state only, as in UnifAI. The teams are the signed-in user's.
const USER = (document.cookie.split("; ").find((c) => c.startsWith("u=")) || "u=").slice(2);
const TEAMS = { "consultant-02": ["agent-arkos", "agent-tekos", "consultant"], "ai-ops-01": ["agent-tekos", "ops"], "sale-01": __SALE_TEAMS__ }[USER] || [];
// FAKE_TEAM_MODE=1 (unifai-agents): a workspace's entry is a button, "name N members", and choosing it is screen state
// only, as in UnifAI's Sidebar.tsx; a gear (team settings) and "Create a new team" sit beside it and count as touched.
const TEAM_MODE = __TEAM_MODE__;
let team = "";   // the chosen team workspace: gone at a page reload, as in UnifAI
function scope() {
  document.querySelector("a[href='/agentic-chats']").textContent = team ? "Collaboration Hub" : "Agentic Chats";
  $("add").title = team ? "New session from workflow" : "Add new chat from flow";
  $("dialog").querySelector("h3").textContent = team ? "Start New Session" : "Add New Chat from Flow";
  $("confirm").textContent = team ? "Start Session" : "Add";
}
$("team").onclick = () => { $("teambox").hidden = false; $("selected").textContent = "Select team"; };
$("personal").onclick = () => { $("teambox").hidden = true; team = ""; scope(); };
$("selector").onclick = () => {
  $("teams").innerHTML = "";
  for (const name of TEAMS) {
    if (!TEAM_MODE) { const row = document.createElement("div"); row.textContent = name; row.onclick = () => fetch("/fake/touched", { method: "POST" }); $("teams").appendChild(row); continue; }
    const row = document.createElement("div");
    const pick = document.createElement("button"); pick.innerHTML = name + "<span>3 members</span>";
    pick.onclick = () => { team = name; $("selected").textContent = name; $("teams").hidden = true; $("overlay").hidden = true; scope(); };
    const gear = document.createElement("button"); gear.innerHTML = "<svg width=8 height=8></svg>"; gear.onclick = () => fetch("/fake/touched", { method: "POST" });
    row.append(pick, gear); $("teams").appendChild(row);
  }
  if (TEAM_MODE) { const create = document.createElement("button"); create.textContent = "Create a new team"; create.onclick = () => fetch("/fake/touched", { method: "POST" }); $("teams").appendChild(create); }
  $("teams").hidden = false; $("overlay").hidden = false;
};
$("overlay").onclick = () => { $("teams").hidden = true; $("overlay").hidden = true; };
const PERSONAL_FLOWS = ["consultant-01-my-assistant", "consultant-01-my-documents"];
let picked = "";
let sid = (location.pathname.match(/^\\/agentic-chats\\/(.+)$/) || [])[1] || "";
function route() {
  $("home").hidden = location.pathname !== "/";
  $("docs").hidden = location.pathname !== "/documents";
  $("chats").hidden = !location.pathname.startsWith("/agentic-chats");
}
route();
// The sidebar's links do not reload the page (a single-page application): the chosen team survives them.
for (const a of document.querySelectorAll("nav a")) a.onclick = (e) => { e.preventDefault(); history.pushState(null, "", a.getAttribute("href")); sid = ""; $("messages").innerHTML = ""; show.sig = ""; route(); };
function flows() {
  $("flows").innerHTML = "";
  for (const name of (team ? ["tekos", "arkos"] : PERSONAL_FLOWS).filter((f) => f.includes($("search").value))) {
    const row = document.createElement("div"); row.className = "flow";
    const label = document.createElement("span"); label.textContent = name; label.onclick = () => { picked = name; };
    const hitl = document.createElement("button"); hitl.setAttribute("role", "switch"); hitl.setAttribute("aria-checked", "false");
    hitl.style.cssText = "width:30px;height:16px"; hitl.onclick = () => fetch("/fake/touched", { method: "POST" });
    row.append(label); if (!team) row.append(hitl);   // no Human-in-the-Loop switch in the team dialog (SessionModals.tsx)
    $("flows").appendChild(row);
  }
}
$("search").oninput = flows;
$("add").onclick = () => { picked = ""; $("search").value = ""; flows(); $("dialog").hidden = false; };
$("cancel").onclick = () => { $("dialog").hidden = true; };
$("confirm").onclick = async () => {
  if (!picked) return;
  const r = await fetch("/api2/sessions/user.session.create", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(team ? { blueprintId: picked, teamId: "team-" + team } : { blueprintId: picked }) });
  sid = await r.json();
  history.replaceState(null, "", "/agentic-chats/" + sid);
  $("dialog").hidden = true; $("in").hidden = false;
};
async function show() {
  if ($("chats").hidden) return;
  const list = await (await fetch("/api2/sessions/session.user.list?limit=100&offset=0" + (team ? "&userId=team-" + team + "&teamId=team-" + team : ""))).json();
  $("count").textContent = "Available Chats (" + list.sessions.length + ")";
  if (!sid) return;
  $("in").hidden = false;
  const r = await fetch("/api2/sessions/session.chat.get?sessionId=" + sid);
  if (r.status !== 200) return;
  const chat = await r.json();
  // As UnifAI on 2026-11-16: the thread does not follow, and an answer is behind the agent's card, drawn only once
  // the thread has been scrolled to its end (FAKE_STUCK=1: never drawn). An answer once drawn stays drawn.
  const end = $("thread").scrollTop + $("thread").clientHeight >= $("thread").scrollHeight - 4;
  const sig = chat.messages.length + ":" + end;
  if (sig === show.sig) return;
  show.sig = sig;
  show.revealed = show.revealed || new Set();
  $("messages").innerHTML = "";
  chat.messages.forEach((m, i) => {
    if (m.role === "assistant") {
      const card = document.createElement("div"); card.style.height = "160px"; card.textContent = "Consultant-01-Rag Complete ... Show full log"; $("messages").appendChild(card);
      if (end && !${process.env.FAKE_STUCK === "1"}) show.revealed.add(i);
      if (!show.revealed.has(i)) { const hole = document.createElement("div"); hole.style.height = "60px"; $("messages").appendChild(hole); return; }
    }
    const p = document.createElement("p"); p.textContent = m.role === "user" ? m.content : m.role + ": " + m.content; $("messages").appendChild(p);
  });
  if (chat.messages.some((m) => m.role === "assistant")) $("live").textContent = "Live workflow: retriever consultant-01-documents";
}
setInterval(show, 300);
$("in").addEventListener("keydown", async (e) => {
  if (e.key !== "Enter") return;
  e.preventDefault();
  const text = $("in").value; $("in").value = "";
  await fetch("/api2/sessions/user.session.submit", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sessionId: sid, inputs: { user_prompt: text } }) });
});
</script>`;

function answer(text, user) {
  if (/can help me with/.test(text)) return "I answer technical questions about OpenShift and the Zuno platform.";
  if (/zuno-ai-run/.test(text)) {
    if (user !== "ai-ops-01") return "Common causes: a failing probe, an image pull error, a missing Secret.";
    return "k8s.events.read: the pod a2a-gateway-7c9d failed its startup probe." + (process.env.FAKE_ADDRESSES === "1" ? " It runs on ip-10-18-3-7.eu-west-3.compute.internal." : "");
  }
  if (/rental car/.test(text)) return process.env.FAKE_WRONG_ANSWER === "1" ? "The documents do not say." : "The code is ZN-CAR-7 (travel-and-expense-policy.md).";
  return "The documents do not give a hotel ceiling for Madrid.";
}

http.createServer((req, res) => {
  const u = new URL(req.url, "http://x");
  const signed = /(^|; )s=1/.test(req.headers.cookie || "");
  const json = (code, body) => { res.writeHead(code, { "Content-Type": "application/json" }); res.end(JSON.stringify(body)); };
  const body = (then) => { let raw = ""; req.on("data", (c) => { raw += c; }); req.on("end", () => then(raw ? JSON.parse(raw) : {})); };
  const id = u.searchParams.get("sessionId") || "";
  const user = decodeURIComponent(((req.headers.cookie || "").match(/(?:^|; )u=([^;]*)/) || [])[1] || "");
  if (u.pathname === "/fake/count") return json(200, { sessions: sessions.size, touched });
  if (u.pathname === "/fake/touched") { touched += 1; return json(200, {}); }
  if (u.pathname === "/api1/terms/approve") return json(200, { approved: true });
  if (u.pathname === "/api1/auth/login") { res.writeHead(200, { "Content-Type": "text/html" }); return res.end(LOGIN); }
  if (u.pathname === "/cb") { res.writeHead(302, { "Set-Cookie": ["s=1; Path=/", `u=${encodeURIComponent(u.searchParams.get("u") || "")}; Path=/`], Location: "/" }); return res.end(); }
  if (!signed) {
    if (u.pathname.startsWith("/api")) return json(401, { error: "not signed in" });
    res.writeHead(200, { "Content-Type": "text/html" }); return res.end(WELCOME);
  }
  if (u.pathname === "/api2/sessions/session.user.list") {
    const wanted = u.searchParams.get("teamId") || undefined;   // a team workspace's sessions, or the personal ones
    const all = [...sessions.keys()].filter((k) => sessions.get(k).team === wanted).map((session_id) => ({ session_id, blueprint_id: sessions.get(session_id).blueprint }));
    return json(200, { sessions: all, pagination: { total: all.length, limit: 100, offset: 0, has_more: false } });
  }
  if (u.pathname === "/api2/sessions/user.session.create" && req.method === "POST") {
    return body((b) => { const made = crypto.randomUUID(); sessions.set(made, { blueprint: b.blueprintId, status: "PENDING", messages: [], team: b.teamId || undefined }); json(200, made); });
  }
  if (u.pathname === "/api2/sessions/user.session.submit" && req.method === "POST") {
    return body((b) => {
      const s = sessions.get(b.sessionId);
      if (!s) return json(404, {});
      s.status = "RUNNING";
      s.messages.push({ role: "user", content: b.inputs.user_prompt });
      setTimeout(() => {
        const refused = process.env.FAKE_REFUSE_MODEL === "1";
        s.messages.push({ role: "assistant", content: refused ? "" : answer(b.inputs.user_prompt, user),
                          metadata: refused ? { error: { type: "rate_limited", message: "429: token quota exceeded for persona consultant-01", retry_after: 60 } } : {} });
        s.status = "COMPLETED";
      }, 1200);
      return json(202, { sessionId: b.sessionId });
    });
  }
  if (u.pathname === "/api2/sessions/session.status.get") return sessions.has(id) ? json(200, sessions.get(id).status) : json(500, { error: "not found" });
  if (u.pathname === "/api2/sessions/session.chat.get") {
    return sessions.has(id) ? json(200, { messages: sessions.get(id).messages, output: "", status: sessions.get(id).status, status_message: null }) : json(500, { error: "not found" });
  }
  if (u.pathname === "/api2/sessions/session.cancel") return json(409, {});
  if (u.pathname === "/api2/sessions/session.delete" && req.method === "DELETE") {
    if (process.env.FAKE_REFUSE_DELETE === "1") return json(200, { success: false });
    return json(200, { success: sessions.delete(id) });
  }
  res.writeHead(200, { "Content-Type": "text/html" });
  return res.end(APP.replace("__TEAM_MODE__", process.env.FAKE_TEAM_MODE === "1" ? "true" : "false").replace("__ACCEPT_POSTS__", process.env.FAKE_ACCEPT_POSTS === "1" ? "true" : "false").replace("__SALE_TEAMS__", JSON.stringify(process.env.FAKE_WRONG_TEAMS === "1" ? ["agent-comage", "sales", "consultant"] : ["agent-comage", "sales"])));
}).listen(port, "127.0.0.1");
