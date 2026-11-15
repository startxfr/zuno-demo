// WP-288: a stand-in for the OpenShift console, its sign-in chooser, Keycloak and the Lightspeed plugin, for the
// offline test of walkthroughs/lightspeed.mjs (tests/walkthroughs-offline.sh). It serves what the walkthrough GUESSES
// the console shows (no scout has run yet): the provider chooser, the console with the Lightspeed button, the panel
// with its prompt box, a streamed answer that carries the conversation id, and a conversation API (list, delete; the
// delete needs the console's CSRF header). It proves the walkthrough's own logic, not the real selectors.
// The conversation list always holds one earlier conversation. Knobs: FAKE_REFUSE_DELETE=1 the delete answers 403;
// FAKE_SAFETY=1 the first answer is the safety-inspection warning; FAKE_QUOTA=1 the query answers 429; FAKE_TOUR=1 a
// guided-tour dialog covers the console. No cluster, no model.
import http from "node:http";
import crypto from "node:crypto";

const port = Number(process.env.FAKE_PORT || 8096);
const OLS = "/api/proxy/plugin/lightspeed-console-plugin/ols";
const conversations = new Set(["33333333-3333-3333-3333-333333333333"]);
let dismissed = 0;   // clicks on the guided tour's "Skip tour": a take or a scout must leave it at 0

const CHOOSER = `<!doctype html><title>Log in</title><h1>Log in with...</h1>
<a class="idp" title="Log in with startx-htpasswd_auth" href="/htpasswd">startx-htpasswd_auth</a><br>
<a class="idp" title="Log in with openshift" href="/kc">openshift</a>`;
const LOGIN = `<!doctype html><title>Sign in</title><form method="get" action="/cb"><input id="username" name="u">
<input id="password" name="p" type="password"><button id="kc-login">Sign In</button></form>`;

const CONSOLE = `<!doctype html><title>OpenShift console (fake)</title>
<style>body{font:16px sans-serif;margin:24px} .ols-plugin__popover{position:fixed;right:24px;bottom:80px;width:460px;border:1px solid #888;background:#fff;padding:12px}
.ols-plugin__popover-button{position:fixed;right:24px;bottom:24px} textarea{width:420px;height:40px}
.tour{position:fixed;inset:0;background:rgba(0,0,0,.4)}</style>
<h1>Projects</h1><p>consultant-02</p>
${process.env.FAKE_TOUR === "1" ? `<div class="tour" role="dialog" aria-modal="true"><p>Welcome to the Developer Perspective</p><button onclick="fetch('/fake/dismissed',{method:'POST'});this.parentElement.remove()">Skip tour</button></div>` : ""}
<button class="ols-plugin__popover-button" data-test="ols-plugin__popover-button" aria-label="Red Hat OpenShift Lightspeed" id="open">*</button>
<div class="ols-plugin__popover" data-test="ols-plugin__popover" id="panel" hidden><h3>Red Hat OpenShift Lightspeed</h3>
<div id="entries"></div><textarea id="in" placeholder="Send a message..."></textarea></div>
<script>
const $ = (id) => document.getElementById(id);
const csrf = () => (document.cookie.split("; ").find((c) => c.startsWith("csrf-token=")) || "").slice(11);
let conversation = "";
$("open").onclick = () => { $("panel").hidden = !$("panel").hidden; fetch("${OLS}/authorized", { method: "POST", headers: { "X-CSRFToken": csrf() } }); };
$("in").addEventListener("keydown", async (e) => {
  if (e.key !== "Enter") return;
  e.preventDefault();
  const query = $("in").value; $("in").value = "";
  const mine = document.createElement("div"); mine.className = "ols-plugin__chat-entry ols-plugin__chat-entry--user"; mine.textContent = query; $("entries").appendChild(mine);
  const r = await fetch("${OLS}/v1/streaming_query", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
                                                      body: JSON.stringify(conversation ? { query, conversation_id: conversation } : { query }) });
  const ai = document.createElement("div"); ai.className = "ols-plugin__chat-entry ols-plugin__chat-entry--ai"; $("entries").appendChild(ai);
  if (r.status !== 200) { ai.textContent = "Error " + r.status; return; }
  const reader = r.body.getReader(); const decoder = new TextDecoder(); let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\\n"); buffer = lines.pop();
    for (const line of lines.filter(Boolean)) {
      const event = JSON.parse(line);
      if (event.event === "start") conversation = event.data.conversation_id;
      if (event.event === "token") ai.textContent += event.data.token;
    }
  }
});
</script>`;

function answer(query) {
  if (process.env.FAKE_SAFETY === "1") return "Lightspeed stopped the operation because a tool result failed the safety inspection";
  if (/openshift-etcd/.test(query)) return "You do not have permission to list pods in the namespace openshift-etcd.";
  if (/zuno-ai-run/.test(query)) return "The pods running in zuno-ai-run are ai-gateway-7d9, mcp-gateway-5c4 and a2a-gateway-66b.";
  return "A Pod is the smallest deployable unit in OpenShift: one or more containers that share storage and network.";
}

http.createServer((req, res) => {
  const u = new URL(req.url, "http://x");
  const cookies = req.headers.cookie || "";
  const signed = /(^|; )s=1/.test(cookies);
  const json = (code, body) => { res.writeHead(code, { "Content-Type": "application/json" }); res.end(JSON.stringify(body)); };
  const html = (body) => { res.writeHead(200, { "Content-Type": "text/html" }); res.end(body); };
  const csrfOk = () => req.headers["x-csrftoken"] === "fake-csrf";
  const one = u.pathname.match(new RegExp(`^${OLS}/v1/conversations/([^/]+)$`));
  if (u.pathname === "/fake/count") return json(200, { conversations: conversations.size, dismissed });
  if (u.pathname === "/fake/dismissed") { dismissed += 1; return json(200, {}); }
  if (u.pathname === "/kc") return html(LOGIN);
  if (u.pathname === "/cb") { res.writeHead(302, { "Set-Cookie": ["s=1; Path=/", "csrf-token=fake-csrf; Path=/"], Location: "/" }); return res.end(); }
  if (!signed) return u.pathname.startsWith("/api") ? json(401, {}) : html(CHOOSER);
  if (u.pathname === `${OLS}/authorized`) return json(200, { user_id: "consultant-02" });
  if (u.pathname === `${OLS}/v1/conversations` && req.method === "GET") {
    return json(200, { conversations: [...conversations].map((conversation_id) => ({ conversation_id, topic_summary: "a topic", last_message_timestamp: 1 })) });
  }
  if (one && req.method === "DELETE") {
    if (!csrfOk() || process.env.FAKE_REFUSE_DELETE === "1") return json(403, { error: "forbidden" });
    return conversations.delete(one[1]) ? json(200, { response: "deleted" }) : json(404, {});
  }
  if (u.pathname === `${OLS}/v1/streaming_query` && req.method === "POST") {
    let raw = "";
    req.on("data", (c) => { raw += c; });
    req.on("end", () => {
      if (!csrfOk()) return json(403, { error: "csrf" });
      if (process.env.FAKE_QUOTA === "1") return json(429, { detail: "token quota exceeded" });
      const body = JSON.parse(raw);
      const id = body.conversation_id || crypto.randomUUID();
      conversations.add(id);
      res.writeHead(200, { "Content-Type": "text/plain" });
      res.write(JSON.stringify({ event: "start", data: { conversation_id: id } }) + "\n");
      const words = answer(body.query).split(" ");
      let i = 0;
      const timer = setInterval(() => {
        if (i < words.length) { res.write(JSON.stringify({ event: "token", data: { token: (i ? " " : "") + words[i] } }) + "\n"); i += 1; return; }
        clearInterval(timer);
        res.end(JSON.stringify({ event: "end", data: {} }) + "\n");
      }, 80);
      return undefined;
    });
    return undefined;
  }
  return html(CONSOLE);
}).listen(port, "127.0.0.1");
