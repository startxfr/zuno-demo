// WP-284: a stand-in for Open WebUI and Keycloak, for the offline test of record.mjs (tests/record-offline.sh).
// It serves what walkthroughs/open-webui.mjs looks for and nothing more: the sign-in form, a chat page, and the two
// API calls of a chat (read, delete). FAKE_REFUSE_DELETE=1 makes the delete answer 403; FAKE_NO_URL=1
// keeps the address bar on the home page after a send (the chat exists, its id is never shown). No cluster, no model.
import http from "node:http";
import crypto from "node:crypto";

const port = Number(process.env.FAKE_PORT || 8099);
const chats = new Map();   // id -> {title, messages: {id: {role, content, done, timestamp}}}

const LOGIN = `<!doctype html><title>Sign in</title><form method="get" action="/"><input id="username" name="u">
<input id="password" name="p" type="password"><button id="kc-login">Sign In</button></form>`;

const CHAT = `<!doctype html><title>Open WebUI (fake)</title>
<style>body{font:16px sans-serif;margin:24px} #chat-input{border:1px solid #888;min-height:40px;padding:8px} .menu{border:1px solid #888;padding:8px;margin:4px 0}</style>
<button id="model-selector-0-button" aria-label="Select a model">Zuno</button>
<div id="models" class="menu" hidden><div id="pick-code">Zuno Code</div></div>
<p>Zuno picks the model</p>
<div id="messages"></div>
<div id="chat-input" contenteditable="true"></div>
<button aria-label="Integrations" id="tools-button">+</button>
<div id="tools" class="menu" hidden><div>Zuno tools</div><div>Drive search</div><div>Gmail read</div><div>Diagram generation</div></div>
<script>
localStorage.setItem("token", "fake-session");
const $ = (id) => document.getElementById(id);
$("model-selector-0-button").onclick = () => { $("models").hidden = !$("models").hidden; };
$("pick-code").onclick = () => { $("model-selector-0-button").textContent = "Zuno Code"; $("models").hidden = true; };
$("tools-button").onclick = () => { $("tools").hidden = false; };
document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("tools").hidden = true; });
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
  const r = await fetch("/fake/send", { method: "POST", body: JSON.stringify({ id: m ? m[1] : null, text, model: $("model-selector-0-button").textContent }) });
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
      setTimeout(() => {
        answer.content = model === "Zuno Code" ? "Here:\n```python\ndef is_email(s):\n    return '@' in s\n```" : "I can help you with questions.";
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
  if (url.pathname === "/fake/count") return json(res, 200, { chats: chats.size });
  if (url.pathname === "/" || url.pathname.startsWith("/c/")) {
    res.writeHead(200, { "content-type": "text/html" });
    return res.end(CHAT.replace("__NO_URL__", process.env.FAKE_NO_URL === "1" ? "true" : "false"));
  }
  json(res, 404, { detail: "Not found" });
}).listen(port, "127.0.0.1", () => console.log(`fake open-webui on 127.0.0.1:${port}`));
