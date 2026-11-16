// WP-288: a stand-in for Dify behind its front door, for the offline test of walkthroughs/dify.mjs and of
// walkthroughs/_dify.mjs (tests/walkthroughs-offline.sh). It serves what the helper GUESSES Dify is (nothing was seen
// live): the Keycloak form of the front door, Dify's own sign-in form (its password is FAKE_ADMIN_PASSWORD), Studio
// with three application cards, the Agent's page with a chat pane, the workflow's page with a run form. Like Dify,
// the workflow's editor saves the draft by itself when its page opens: a take must refuse that request in the
// browser, and `saved` counts the ones that reached the server. One earlier conversation and one earlier run exist.
// Knobs: FAKE_REFUSE_DELETE=1 the conversation's delete answers 403; FAKE_NO_CONVERSATION=1 a chat leaves no
// conversation; FAKE_RUN_FAILS=1 the workflow's run fails; FAKE_ADDRESSES=1 the Agent's answer holds a node name.
import crypto from "node:crypto";
import http from "node:http";

const port = Number(process.env.FAKE_PORT || 8094);
const AGENT = "11111111-1111-4111-8111-111111111111";
const DOCS = "22222222-2222-4222-8222-222222222222";
const FLOW = "33333333-3333-4333-8333-333333333333";
const conversations = new Set(["99999999-9999-4999-8999-999999999999"]);
const runs = [{ id: "88888888-8888-4888-8888-888888888888", status: "succeeded" }];
let saved = 0;

const LOGIN = `<!doctype html><title>Sign in</title><form method="get" action="/fd"><input id="username" name="u">
<input id="password" name="p" type="password"><button id="kc-login">Sign In</button></form>`;
const SIGNIN = `<!doctype html><title>Dify</title><h1>Hey, let's get started!</h1><form id="f"><input id="email" type="email" placeholder="Your email">
<input id="password" type="password" placeholder="Your password"><button type="submit">Sign in</button></form><p id="error"></p>
<script>
document.getElementById("f").onsubmit = async (e) => {
  e.preventDefault();
  const r = await fetch("/console/api/login", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: document.getElementById("email").value, password: btoa(document.getElementById("password").value) }) });
  if (r.status === 200) location.href = "/"; else document.getElementById("error").textContent = "Invalid email or password.";
};
</script>`;
// The left menu lists the web apps by the same names as Studio's cards; its entries open the web app, not the editor.
const MENU = `<aside style="position:fixed;left:0;top:60px;width:240px"><p>WEB APPS</p><a href="/webapp/agent" style="display:block">Zuno Agent</a><a href="/webapp/flow" style="display:block">Zuno Confluence Search</a></aside>`;
const shell = (body) => `<!doctype html><title>Dify</title><body style="font:16px sans-serif;margin:24px 24px 24px 280px">${MENU}<nav><a href="/">Home</a> <a href="/apps">Studio</a> <a href="/datasets">Knowledge</a></nav>${body}`;
const APPS = shell(`<main><h1>Studio</h1><div id="skeleton">loading cards</div><div id="cards" hidden>
<div class="card" style="border:1px solid #888;padding:8px;margin:8px" onclick="location.href='/app/${AGENT}/configuration'"><div>Zuno Agent</div><small>AGENT</small></div>
<div class="card" style="border:1px solid #888;padding:8px;margin:8px" onclick="location.href='/app/${DOCS}/workflow'"><div>Zuno Technical Documentation</div><small>CHATFLOW</small></div>
<div class="card" style="border:1px solid #888;padding:8px;margin:8px" onclick="location.href='/app/${FLOW}/workflow'"><div>Zuno Confluence Search</div><small>WORKFLOW</small></div></div></main>
<script>setTimeout(() => { document.getElementById("skeleton").remove(); document.getElementById("cards").hidden = false; }, 3000);   // skeleton cards first, as on 2026-11-16</script>`);
const csrf = `(document.cookie.split("; ").map((c) => c.split("=")).find(([n]) => n === "csrf_token") || [])[1] || ""`;
const AGENT_PAGE = shell(`<main><h1>Zuno Agent</h1><div id="spin" role="status">loading</div><section id="editor" hidden><button>Publish</button><h2>Debug & Preview</h2><div id="thread"></div>
<textarea placeholder="Talk to Bot" id="in" style="width:500px"></textarea></section></main>
<script>setTimeout(() => { document.getElementById("spin").remove(); document.getElementById("editor").hidden = false; }, 4000);   // the editor draws after its shell, as on 2026-11-16</script>
<script>
// The Agent's editor writes to its application by itself, by paths nobody guessed: on load, after a message, and
// when the page is left (a beacon). All must be refused; \`saved\` counts the ones that reached the server.
fetch("/console/api/apps/${AGENT}/model-config", { method: "POST", headers: { "X-CSRF-Token": ${csrf} }, body: "{}" }).catch(() => {});
fetch("/console/api/apps/${AGENT}/some-unguessed-autosave", { method: "PUT", headers: { "X-CSRF-Token": ${csrf} }, body: "{}" }).catch(() => {});
addEventListener("pagehide", () => { navigator.sendBeacon("/console/api/apps/${AGENT}/touch-on-leave", "{}"); });
</script>
<script>
document.getElementById("in").addEventListener("keydown", async (e) => {
  if (e.key !== "Enter") return;
  e.preventDefault();
  const text = e.target.value; e.target.value = "";
  const add = (line) => { const p = document.createElement("p"); p.textContent = line; document.getElementById("thread").appendChild(p); };
  add(text);
  const r = await fetch("/console/api/apps/${AGENT}/chat-messages", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": ${csrf} }, body: JSON.stringify({ query: text }) });
  for (const line of (await r.text()).split("\\n")) add(line);
});
</script>`);
const FLOW_PAGE = shell(`<main><h1>Zuno Confluence Search</h1><button id="run">Test Run</button><button>Publish</button>
<div>Start</div><div>confluence.page.search</div><div>Summarise</div><div>End</div>
<aside id="panel" hidden><label>Topic <input id="topic" placeholder="Topic"></label><button id="start">Start Run</button><div id="result"></div></aside></main>
<script>
// The editor saves the draft by itself, as Dify's does.
fetch("/console/api/apps/${FLOW}/workflows/draft", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": ${csrf} }, body: "{}" }).catch(() => {});
document.getElementById("run").onclick = () => { document.getElementById("panel").hidden = false; };
document.getElementById("start").onclick = async () => {
  const r = await fetch("/console/api/apps/${FLOW}/workflows/draft/run", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": ${csrf} }, body: JSON.stringify({ inputs: { topic: document.getElementById("topic").value } }) });
  document.getElementById("result").textContent = await r.text();
};
</script>`);

http.createServer((req, res) => {
  const u = new URL(req.url, "http://x");
  const cookies = req.headers.cookie || "";
  const door = /(^|; )fd=1/.test(cookies);
  const signed = /(^|; )d=1/.test(cookies);
  const html = (body) => { res.writeHead(200, { "Content-Type": "text/html" }); res.end(body); };
  const json = (code, body) => { res.writeHead(code, { "Content-Type": "application/json" }); res.end(body === undefined ? "" : JSON.stringify(body)); };
  const body = (then) => { let raw = ""; req.on("data", (c) => { raw += c; }); req.on("end", () => then(raw)); };
  if (u.pathname === "/fake/count") return json(200, { conversations: conversations.size, runs: runs.length, saved });
  if (u.pathname === "/fd") { res.writeHead(302, { "Set-Cookie": "fd=1; Path=/", Location: "/" }); return res.end(); }
  if (!door) return html(LOGIN);
  if (u.pathname === "/console/api/login" && req.method === "POST") {
    return body((raw) => {
      const sent = Buffer.from(JSON.parse(raw).password || "", "base64").toString();
      if (JSON.parse(raw).email !== "dify-admin@zuno.local" || !process.env.FAKE_ADMIN_PASSWORD || sent !== process.env.FAKE_ADMIN_PASSWORD) return json(401, { code: "invalid" });
      res.writeHead(200, { "Content-Type": "application/json", "Set-Cookie": ["d=1; Path=/; HttpOnly", "csrf_token=abc; Path=/"] });
      return res.end("{}");
    });
  }
  if (!signed) return u.pathname.startsWith("/console/api") ? json(401, {}) : u.pathname === "/signin" ? html(SIGNIN) : (res.writeHead(302, { Location: "/signin" }), res.end());
  if (u.pathname.startsWith("/console/api") && req.headers["x-csrf-token"] !== "abc") return json(401, { code: "csrf" });
  if (u.pathname === "/console/api/account/profile") return json(200, { email: "dify-admin@zuno.local" });
  if (u.pathname === "/console/api/apps") {
    return json(200, { data: [{ id: AGENT, name: "Zuno Agent", mode: "agent-chat" }, { id: DOCS, name: "Zuno Technical Documentation", mode: "advanced-chat" }, { id: FLOW, name: "Zuno Confluence Search", mode: "workflow" }] });
  }
  if (u.pathname === `/console/api/apps/${AGENT}/chat-conversations`) return json(200, { data: [...conversations].reverse().map((id) => ({ id })) });
  const one = u.pathname.match(new RegExp(`^/console/api/apps/${AGENT}/chat-conversations/([^/]+)$`));
  if (one && req.method === "DELETE") {
    if (process.env.FAKE_REFUSE_DELETE === "1") return json(403, {});
    return conversations.delete(one[1]) ? json(204) : json(404, {});
  }
  if (u.pathname === `/console/api/apps/${AGENT}/chat-messages` && req.method === "POST") {
    return body(() => setTimeout(() => {
      if (process.env.FAKE_NO_CONVERSATION !== "1") conversations.add(crypto.randomUUID());
      res.writeHead(200, { "Content-Type": "text/plain" });
      res.end(`Used confluence.page.search\nMNGD2-AP001 Onboarding Chef de projet (SXSI)${process.env.FAKE_ADDRESSES === "1" ? "\nserved from ip-10-18-3-7.eu-west-3.compute.internal" : ""}`);
    }, 1200));
  }
  if (u.pathname === `/console/api/apps/${FLOW}/workflow-runs`) return json(200, { data: runs });
  if (u.pathname === `/console/api/apps/${FLOW}/workflows/draft/run` && req.method === "POST") {
    return body(() => {
      const run = { id: crypto.randomUUID(), status: "running" };
      runs.unshift(run);
      setTimeout(() => { run.status = process.env.FAKE_RUN_FAILS === "1" ? "failed" : "succeeded"; res.writeHead(200, { "Content-Type": "text/plain" }); res.end(`Start confluence.page.search Summarise End ${run.status}`); }, 1000);
    });
  }
  if (/\/workflows\/draft$|\/model-config$|\/some-unguessed-autosave$|\/touch-on-leave$/.test(u.pathname) && req.method !== "GET") { saved += 1; return json(200, {}); }
  if (u.pathname === "/console/api/workspaces/current") return json(200, { id: "w" });
  if (u.pathname === "/signin") { res.writeHead(302, { Location: "/" }); return res.end(); }
  // As Dify on 2026-11-16: the first page is Home, with Studio in its left menu and the web apps listed.
  // Its Recents cards carry the applications' names and open the WEB APP, not the editor (the trap of 2026-11-16).
  if (u.pathname === "/") return html(shell(`<main><h1>Welcome back, x</h1><h2>Recents</h2><div onclick="location.href='/webapp/agent'">Zuno Agent</div><div onclick="location.href='/webapp/flow'">Zuno Confluence Search</div></main>`));
  if (u.pathname.startsWith("/webapp/")) return html(shell(`<main><h1>Run Once</h1><button>Execute</button></main>`));
  // An address typed for Studio lands on Home, as a guess of what happened on 2026-11-16: Studio is reached by its link.
  if (u.pathname === "/apps" && req.headers["sec-fetch-site"] === "none") { res.writeHead(302, { Location: "/" }); return res.end(); }
  if (u.pathname === "/apps") return html(APPS);
  if (u.pathname === `/app/${AGENT}/configuration`) return html(AGENT_PAGE);
  if (u.pathname === `/app/${FLOW}/workflow` || u.pathname === `/app/${DOCS}/workflow`) return html(FLOW_PAGE);
  return json(404, {});
}).listen(port, "127.0.0.1");
