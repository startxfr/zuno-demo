// WP-284: a stand-in for Open WebUI and Keycloak, for the offline test of record.mjs (tests/record-offline.sh).
// It serves what walkthroughs/open-webui.mjs looks for and nothing more: the sign-in form, a chat page, and the two
// API calls of a chat (read, delete). Like 0.12.5 with its sidebar collapsed, the page keeps a new-chat button on screen
// and an earlier chat's link off screen; its toggle would bring that link on screen. A sign-in toast shows for 2.5 s.
// The tools are as seen live on 2026-11-15: the Integrations button opens a role=menu with one row "Tools 1", which
// opens a panel with the connection "Zuno tools" and its switch (on); the wrench "Available Tools" opens nothing. FAKE_REFUSE_DELETE=1 makes the delete answer 403;
// FAKE_REFUSE_MODEL=1 makes every answer an error (429); FAKE_STRAY_CHAT=1 creates a second chat the take does not
// know about, on the first send; the chat list always holds one earlier chat. FAKE_NO_URL=1
// keeps the address bar on the home page after a send (the chat exists, its id is never shown). No cluster, no model.
import http from "node:http";
import crypto from "node:crypto";

const port = Number(process.env.FAKE_PORT || 8099);
let toggled = 0;            // clicks on the tool connection's switch: a take or a scout must leave it at 0
const EARLIER = "00000000-0000-0000-0000-000000000000";   // sale-01's earlier chat: listed, never touched by a take
const chats = new Map();   // id -> {title, messages: {id: {role, content, done, timestamp}}}

const LOGIN = `<!doctype html><title>Sign in</title><form method="get" action="/"><input id="username" name="u">
<input id="password" name="p" type="password"><button id="kc-login">Sign In</button></form>`;

const CHAT = `<!doctype html><title>Open WebUI (fake)</title>
<style>body{font:16px sans-serif;margin:24px} #chat-input{border:1px solid #888;min-height:40px;padding:8px} .menu{border:1px solid #888;padding:8px;margin:4px 0}</style>
<button id="model-selector-model-button" aria-label="Selected model: Zuno">Zuno</button>
<div id="models" class="menu" hidden><div id="pick-code" role="option">Zuno Code</div></div>
<div id="sidebar" style="position:fixed;top:0;left:-400px;width:300px"><a href="/c/00000000-0000-0000-0000-000000000000">An earlier chat of sale-01</a></div>
<button id="sidebar-new-chat-button">new chat</button>
<button id="sidebar-toggle-button" onclick="document.getElementById('sidebar').style.left='0px'">toggle</button>
<div id="toast">You're now logged in.</div>
<p>Zuno picks the model</p>
<div id="messages"></div>
<div id="chat-input" contenteditable="true"></div>
<button aria-label="Integrations" id="integration-menu-button">+</button>
<button aria-label="Available Tools">wrench 1</button>
<div id="tools" role="menu" class="menu" hidden><div role="menuitem" id="tools-row"><div>Tools</div><div>1</div></div>
<div id="tools-panel" hidden><div>Zuno tools</div><button role="switch" aria-checked="true" id="zuno-switch" style="width:30px;height:16px"></button></div></div>
<script>
localStorage.setItem("token", "fake-session");
setTimeout(() => document.getElementById("toast").remove(), 2500);
const $ = (id) => document.getElementById(id);
$("model-selector-model-button").onclick = () => { $("models").hidden = !$("models").hidden; };
$("pick-code").onclick = () => { $("model-selector-model-button").textContent = "Zuno Code"; $("model-selector-model-button").setAttribute("aria-label", "Selected model: Zuno Code"); $("models").hidden = true; };
$("integration-menu-button").onclick = () => { $("tools").hidden = false; };
$("tools-row").onclick = () => { $("tools-panel").hidden = false; };
$("zuno-switch").onclick = () => { $("zuno-switch").setAttribute("aria-checked", "false"); fetch("/fake/toggled", { method: "POST" }); };
document.addEventListener("keydown", (e) => { if (e.key === "Escape") { $("tools").hidden = true; $("tools-panel").hidden = true; } });
async function show() {
  const m = location.pathname.match(/^\\/c\\/(.+)$/);
  if (!m) return;
  const r = await fetch("/api/v1/chats/" + m[1]);
  if (r.status !== 200) return;
  const list = Object.values((await r.json()).chat.history.messages);
  $("messages").innerHTML = "";
  for (const msg of list) {
    const el = document.createElement(msg.content.includes("\`\`\`") ? "pre" : "p");
    el.textContent = msg.role + ": " + msg.content;
    $("messages").appendChild(el);
  }
}
setInterval(show, 300);
$("chat-input").addEventListener("keydown", async (e) => {
  if (e.key !== "Enter") return;
  e.preventDefault();
  const text = $("chat-input").textContent;
  $("chat-input").textContent = "";
  const m = location.pathname.match(/^\\/c\\/(.+)$/);
  const r = await fetch("/fake/send", { method: "POST", body: JSON.stringify({ id: m ? m[1] : null, text, model: $("model-selector-model-button").textContent }) });
  const { id } = await r.json();
  if (!m && !__NO_URL__) history.pushState({}, "", "/c/" + id);
});
</script>`;

function json(res, status, body) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

http.createServer((req, res) => {
  const url = new URL(req.url, "http://fake");
  const chat = url.pathname.match(/^\/api\/v1\/chats\/([0-9a-f-]{36})$/);
  if (url.pathname === "/oauth/oidc/login") { res.writeHead(200, { "content-type": "text/html" }); return res.end(LOGIN); }
  if (url.pathname === "/fake/send" && req.method === "POST") {
    let raw = "";
    req.on("data", (c) => { raw += c; });
    return req.on("end", () => {
      const { id, text, model } = JSON.parse(raw);
      const chatId = id || crypto.randomUUID();
      if (!chats.has(chatId)) chats.set(chatId, { title: "Fake chat about " + text.slice(0, 20), messages: {} });
      const messages = chats.get(chatId).messages;
      const now = Date.now();
      messages[crypto.randomUUID()] = { role: "user", content: text, done: true, timestamp: now };
      const answer = { role: "assistant", content: "", done: false, timestamp: now + 1 };
      messages[crypto.randomUUID()] = answer;
      if (process.env.FAKE_STRAY_CHAT === "1" && !id) chats.set(crypto.randomUUID(), { title: "A chat the take did not create", messages: {} });
      setTimeout(() => {
        if (process.env.FAKE_REFUSE_MODEL === "1") {
          answer.error = { content: "429: token quota exceeded for group sales" };
          answer.done = true;
          return;
        }
        answer.content = model === "Zuno Code" ? "Here:\n```python\ndef is_email(s):\n    return '@' in s\n```"
          // FAKE_ADDRESSES=1: an answer as Lightspeed gave on 2026-11-16, with a pod's address and its node's name.
          : process.env.FAKE_ADDRESSES === "1" ? "I can help. ai-gateway-7d9 runs at 10.130.2.14 on ip-10-18-3-7.eu-west-3.compute.internal."
          : "I can help you with questions.";
        answer.done = true;
      }, 1500);
      json(res, 200, { id: chatId });
    });
  }
  if (chat && req.method === "GET") {
    const found = chats.get(chat[1]);
    return found ? json(res, 200, { id: chat[1], title: found.title, chat: { history: { messages: found.messages } } }) : json(res, 404, { detail: "Not found" });
  }
  if (chat && req.method === "DELETE") {
    if (process.env.FAKE_REFUSE_DELETE === "1") return json(res, 403, { detail: "refused" });
    return json(res, 200, chats.delete(chat[1]));
  }
  if (url.pathname === "/api/v1/chats/" && req.method === "GET") {
    const all = [{ id: EARLIER, title: "An earlier chat of sale-01" }, ...[...chats].map(([id, c]) => ({ id, title: c.title }))];
    return json(res, 200, url.searchParams.get("page") === "1" ? all : []);
  }
  if (url.pathname === "/fake/toggled") { toggled += 1; return json(res, 200, {}); }
  if (url.pathname === "/fake/count") return json(res, 200, { chats: chats.size, toggled });
  if (url.pathname === "/" || url.pathname.startsWith("/c/")) {
    res.writeHead(200, { "content-type": "text/html" });
    return res.end(CHAT.replace("__NO_URL__", process.env.FAKE_NO_URL === "1" ? "true" : "false"));
  }
  json(res, 404, { detail: "Not found" });
}).listen(port, "127.0.0.1", () => console.log(`fake open-webui on 127.0.0.1:${port}`));
