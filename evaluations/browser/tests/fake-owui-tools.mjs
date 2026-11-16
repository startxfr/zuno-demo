// WP-289: a stand-in for Open WebUI and Keycloak, for the offline test of walkthroughs/mcp-tools-by-group.mjs
// (tests/walkthroughs-offline.sh). Its own file, so the stand-in of the other Open WebUI walkthroughs stays as it is.
// It serves what the shared owui* helpers look for (seen live on 0.12.5): the sign-in form, a chat page whose sidebar
// keeps an earlier chat off screen, a sign-in toast for 2.5 s, "Zuno picks the model", and a chat's read and delete.
// The persona is the name typed in the sign-in form (a cookie). The answers depend on the persona and the prompt:
// the tools question lists three tools for sale-01, six for consultant-02 (the Confluence tool names among them); the
// Confluence question shows consultant-02 a tool call ("Executing search_confluence") 1 s after the send, then its
// result and the answer, naming a page "FAKE-CONFLUENCE-TITLE", 2.5 s later; sale-01 gets a refusal and no tool call.
// Knobs: FAKE_NO_TOOL_CALL=1 consultant-02's answer comes with no tool call; FAKE_ANSWER_WITH_CHIP=1 the answer's text
// shows at the same time as the tool call. /fake/count says how many chats remain and how many Confluence searches
// ran. No cluster, no model.
import http from "node:http";
import crypto from "node:crypto";

const port = Number(process.env.FAKE_PORT || 8094);
const EARLIER = "00000000-0000-0000-0000-000000000000";   // an earlier chat: listed, never touched by a take
const chats = new Map();   // id -> {title, persona, messages: {id: {role, content, done, timestamp, chip}}}
let searches = 0;

const LOGIN = `<!doctype html><title>Sign in</title><form method="get" action="/"><input id="username" name="u">
<input id="password" name="p" type="password"><button id="kc-login">Sign In</button></form>`;

const CHAT = `<!doctype html><title>Open WebUI (fake)</title>
<style>body{font:16px sans-serif;margin:24px} #chat-input{border:1px solid #888;min-height:40px;padding:8px} .chip{border:1px solid #888;border-radius:8px;padding:4px 8px;display:inline-block}</style>
<div id="sidebar" style="position:fixed;top:0;left:-400px;width:300px"><a href="/c/${EARLIER}">An earlier chat</a></div>
<button id="sidebar-toggle-button" onclick="document.getElementById('sidebar').style.left='0px'">toggle</button>
<div id="toast">You're now logged in.</div>
<p>Zuno picks the model</p>
<p>Find our onboarding pages in Confluence</p>
<div id="messages"></div>
<div id="chat-input" contenteditable="true"></div>
<script>
localStorage.setItem("token", "fake-session");
setTimeout(() => document.getElementById("toast").remove(), 2500);
const $ = (id) => document.getElementById(id);
async function show() {
  const m = location.pathname.match(/^\\/c\\/(.+)$/);
  if (!m) return;
  const r = await fetch("/api/v1/chats/" + m[1]);
  if (r.status !== 200) return;
  const list = Object.values((await r.json()).chat.history.messages).sort((a, b) => a.timestamp - b.timestamp);
  const box = document.createElement("div");
  for (const msg of list) {
    if (msg.chip) { const c = document.createElement("div"); c.className = "chip"; c.textContent = msg.chip; box.appendChild(c); }
    if (msg.content) { const p = document.createElement("p"); p.textContent = msg.content; box.appendChild(p); }
  }
  if ($("messages").innerHTML !== box.innerHTML) $("messages").innerHTML = box.innerHTML;
}
setInterval(show, 100);
$("chat-input").addEventListener("keydown", async (e) => {
  if (e.key !== "Enter") return;
  e.preventDefault();
  const text = $("chat-input").textContent;
  $("chat-input").textContent = "";
  const m = location.pathname.match(/^\\/c\\/(.+)$/);
  const r = await fetch("/fake/send", { method: "POST", body: JSON.stringify({ id: m ? m[1] : null, text }) });
  const { id } = await r.json();
  if (!m) history.pushState({}, "", "/c/" + id);
});
</script>`;

const TOOLS = {
  "sale-01": "I can use: search_drive, read_gmail, generate_diagram.",
  "consultant-02": "I can use: search_drive, read_gmail, generate_diagram, search_confluence, read_confluence_page, search_technical_docs.",
};

function json(res, status, body) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

function who(req) {
  return (/(?:^|; )who=([a-z0-9-]+)/.exec(req.headers.cookie || "") || [])[1] || "";
}

// The assistant's answer, as Open WebUI's API stores it while it streams: content and `done` filled in over time.
function answer(persona, text, message) {
  const later = (ms, fn) => setTimeout(fn, ms);
  if (/Which tools/.test(text)) return later(1500, () => { message.content = TOOLS[persona] || "I have no tools."; message.done = true; });
  if (!/Confluence/.test(text)) return later(1500, () => { message.content = "I can help you with questions."; message.done = true; });
  if (persona !== "consultant-02" || process.env.FAKE_NO_TOOL_CALL === "1") {
    return later(1500, () => { message.content = persona === "consultant-02" ? "Here are some pages: FAKE-CONFLUENCE-TITLE." : "I cannot search Confluence for you."; message.done = true; });
  }
  const content = "Here are the onboarding pages: FAKE-CONFLUENCE-TITLE, a guide for new consultants, with its link.";
  later(1000, () => {
    searches += 1;
    message.chip = "Executing search_confluence";
    if (process.env.FAKE_ANSWER_WITH_CHIP === "1") message.content = content;
  });
  later(3500, () => { message.chip = "View Result from search_confluence"; message.content = content; message.done = true; });
}

http.createServer((req, res) => {
  const url = new URL(req.url, "http://fake");
  const chat = url.pathname.match(/^\/api\/v1\/chats\/([0-9a-f-]{36})$/);
  if (url.pathname === "/oauth/oidc/login") { res.writeHead(200, { "content-type": "text/html" }); return res.end(LOGIN); }
  if (url.pathname === "/fake/send" && req.method === "POST") {
    let raw = "";
    req.on("data", (c) => { raw += c; });
    return req.on("end", () => {
      const { id, text } = JSON.parse(raw);
      const persona = who(req);
      const chatId = id || crypto.randomUUID();
      if (!chats.has(chatId)) chats.set(chatId, { title: "Fake chat about " + text.slice(0, 20), persona, messages: {} });
      const messages = chats.get(chatId).messages;
      const now = Date.now();
      messages[crypto.randomUUID()] = { role: "user", content: text, done: true, timestamp: now };
      const message = { role: "assistant", content: "", done: false, timestamp: now + 1 };
      messages[crypto.randomUUID()] = message;
      answer(persona, text, message);
      json(res, 200, { id: chatId });
    });
  }
  if (chat && req.method === "GET") {
    const found = chats.get(chat[1]);
    return found ? json(res, 200, { id: chat[1], title: found.title, chat: { history: { messages: found.messages } } }) : json(res, 404, { detail: "Not found" });
  }
  if (chat && req.method === "DELETE") return json(res, 200, chats.delete(chat[1]));
  if (url.pathname === "/api/v1/chats/" && req.method === "GET") {
    const mine = [...chats].filter(([, c]) => c.persona === who(req)).map(([id, c]) => ({ id, title: c.title }));
    return json(res, 200, url.searchParams.get("page") === "1" ? [{ id: EARLIER, title: "An earlier chat" }, ...mine] : []);
  }
  if (url.pathname === "/fake/count") return json(res, 200, { chats: chats.size, searches });
  if (url.pathname === "/" || url.pathname.startsWith("/c/")) {
    const headers = { "content-type": "text/html" };
    if (url.searchParams.get("u")) headers["set-cookie"] = `who=${url.searchParams.get("u")}; Path=/`;
    res.writeHead(200, headers);
    return res.end(CHAT);
  }
  json(res, 404, { detail: "Not found" });
}).listen(port, "127.0.0.1", () => console.log(`fake open-webui (tools) on 127.0.0.1:${port}`));
