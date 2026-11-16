// WP-290: a stand-in for the OpenShift sign-in and the MaaS consumer portal's playground, for the offline test of
// walkthroughs/genai-playground.mjs (tests/walkthroughs-offline.sh). Shaped like the walkthrough's guesses and the
// WP-220 screenshots of 2026-11-06, not like the real portal: it proves the walkthrough's own logic, not its selectors.
// It serves the provider chooser and Keycloak, the portal's menu (AI asset endpoints, API keys, Playground), the
// playground of zuno-playground with its project "Zuno Playground", "Settings" and its tabs Model | Prompt | Knowledge
// | MCP, the MCP row zuno-mcp-gateway with its Auth lock, a message box, and an answer with metric chips 1.5 s after a
// question (POST /gen-ai/api/v1/responses). The page reads GET /gen-ai/api/v1/conversations when it loads.
// Knobs: FAKE_MCP_SAVED=1 the gateway shows "9 active" (a connection kept on the server); FAKE_OTHER_MODEL=1 the model
// shown is another one until gpt-oss-20b is chosen in its list; FAKE_SELECT_WRITE=1 that choice also PUTs a preference;
// FAKE_SSAR=1 the playground POSTs a SelfSubjectAccessReview when it loads; FAKE_CREATE_ONLY=1 the project shows
// "Create playground" and no playground. /fake/count says {answers, writes, locks}: the questions answered, the other
// non-GET requests that reached the stand-in, and the clicks on the MCP lock (must stay 0). No cluster, no model.
import http from "node:http";

const port = Number(process.env.FAKE_PORT || 8086);
const knob = (name) => process.env[name] === "1";
let answers = 0;
let writes = 0;
let locks = 0;

const CHOOSER = `<!doctype html><title>Log in</title><h1>Log in with...</h1>
<a class="idp" title="Log in with startx-htpasswd_auth" href="/htpasswd">startx-htpasswd_auth</a><br>
<a class="idp" title="Log in with openshift" href="/kc">openshift</a>`;
const LOGIN = `<!doctype html><title>Sign in</title><form method="get" action="/cb"><input id="username" name="u">
<input id="password" name="p" type="password"><button id="kc-login">Sign In</button></form>`;
const NAV = `<nav aria-label="Global" style="width:220px;float:left"><a href="/maas-consumer-portal/endpoints">AI asset endpoints</a><br>
<a href="/maas-consumer-portal/api-keys">API keys</a><br><a href="/maas-consumer-portal/gen-ai-studio/playground/default">Playground</a></nav>`;
const page = (body) => `<!doctype html><title>MaaS Consumer Portal (fake)</title><body style="font:16px sans-serif;margin:0">
<header style="text-align:right;padding:8px">ai-ops-01</header>${NAV}<main style="margin-left:240px;padding:16px">${body}</main>`;

const OTHER = "publishers/zuno-ai-run/models/qwen3.5-9b";
const MODEL = "publishers/zuno-ai-run/models/gpt-oss-20b";
const PLAYGROUND = `<div>Project <button id="project">Zuno Playground</button></div><h1>Playground</h1>
<button id="settings">Settings</button>
<div id="panel" hidden><div role="tablist">${["Model", "Prompt", "Knowledge", "MCP"].map((t) => `<button role="tab" aria-selected="false" data-tab="${t}">${t}</button>`).join("")}</div>
<section data-for="Model" hidden><p>Model <button id="model" aria-haspopup="listbox" aria-label="Model">${knob("FAKE_OTHER_MODEL") ? OTHER : MODEL}</button></p>
<ul role="listbox" id="models" hidden><li role="option">${MODEL}</li><li role="option">${OTHER}</li></ul>
<p>Subscription <button aria-haspopup="listbox" aria-label="Subscription">gpt-oss-20b-ocp-ai-ops</button></p></section>
<section data-for="MCP" hidden><table><tr><th>Name</th><th>Tools</th><th>Auth</th></tr>
<tr><td>zuno-mcp-gateway</td><td>${knob("FAKE_MCP_SAVED") ? "9 active" : "-"}</td><td><button aria-label="${knob("FAKE_MCP_SAVED") ? "Authorized" : "Authorize"}" onclick="fetch('/fake/lock')">lock</button></td></tr></table></section></div>
<div id="chat"></div><textarea placeholder="Send a message..." id="box"></textarea>
<script>
const $ = (id) => document.getElementById(id);
fetch("/gen-ai/api/v1/conversations");
${knob("FAKE_SSAR") ? `fetch("/api/k8s/apis/authorization.k8s.io/v1/selfsubjectaccessreviews", { method: "POST", body: "{}" });` : ""}
$("settings").onclick = () => { $("panel").hidden = !$("panel").hidden; };
document.querySelectorAll("[role=tab]").forEach((t) => t.onclick = () => {
  document.querySelectorAll("[role=tab]").forEach((o) => o.setAttribute("aria-selected", String(o === t)));
  document.querySelectorAll("section[data-for]").forEach((s) => { s.hidden = s.dataset.for !== t.dataset.tab; });
});
$("model").onclick = () => { $("models").hidden = false; };
document.querySelectorAll("#models [role=option]").forEach((o) => o.onclick = () => {
  $("model").textContent = o.textContent; $("models").hidden = true;
  ${knob("FAKE_SELECT_WRITE") ? `fetch("/gen-ai/api/v1/preferences", { method: "PUT", body: "{}" });` : ""}
});
$("box").addEventListener("keydown", async (e) => {
  if (e.key !== "Enter") return;
  e.preventDefault();
  const text = $("box").value; $("box").value = "";
  const q = document.createElement("p"); q.textContent = text; $("chat").appendChild(q);
  const r = await fetch("/gen-ai/api/v1/responses", { method: "POST", body: JSON.stringify({ input: text }) });
  const { answer } = await r.json();
  setTimeout(() => { const a = document.createElement("p"); a.innerHTML = answer + ' <span>773ms</span> <span>169 T/s</span> <span>TTFT: 630ms</span>'; $("chat").appendChild(a); }, 1500);
});
</script>`;

http.createServer((req, res) => {
  const u = new URL(req.url, "http://fake");
  const signed = /(?:^|; )sid=ai-ops-01/.test(req.headers.cookie || "");
  const html = (body, status = 200) => { res.writeHead(status, { "content-type": "text/html" }); res.end(body); };
  const json = (body, status = 200) => { res.writeHead(status, { "content-type": "application/json" }); res.end(JSON.stringify(body)); };
  if (u.pathname === "/fake/count") return json({ answers, writes, locks });
  if (u.pathname === "/fake/lock") { locks += 1; return json({}); }
  if (req.method === "POST" && u.pathname === "/gen-ai/api/v1/responses") { answers += 1; return json({ answer: "La capitale de la France est Paris." }); }
  if (req.method !== "GET") { writes += 1; return json({}); }
  if (u.pathname === "/kc") return html(LOGIN);
  if (u.pathname === "/cb") { res.writeHead(302, { location: "/maas-consumer-portal/", "set-cookie": `sid=${u.searchParams.get("u")}; Path=/` }); return res.end(); }
  if (!signed) return html(CHOOSER);
  if (u.pathname === "/gen-ai/api/v1/conversations") return json({ data: [] });
  if (u.pathname === "/maas-consumer-portal/" || u.pathname === "/maas-consumer-portal/endpoints") return html(page("<h1>AI asset endpoints</h1>"));
  if (u.pathname === "/maas-consumer-portal/gen-ai-studio/playground/default") return html(page(`<div>Project <button>Default project</button></div><button>Create playground</button>`));
  if (u.pathname === "/maas-consumer-portal/gen-ai-studio/playground/zuno-playground") {
    return html(page(knob("FAKE_CREATE_ONLY") ? `<div>Project <button>Zuno Playground</button></div><button>Create playground</button>` : PLAYGROUND));
  }
  return html(page("<h1>Not found</h1>"), 404);
}).listen(port, "127.0.0.1");
