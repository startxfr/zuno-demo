// WP-290: a stand-in for the Red Hat AI portal (maas-consumer-portal), its OpenShift sign-in and the MaaS gateway, for
// the offline test of walkthroughs/maas-portal-api-keys.mjs and of the recorder's created-secret mechanism
// (tests/walkthroughs-offline.sh). It serves what the walkthrough GUESSES (nothing was seen live): the provider
// chooser, the Keycloak form, the portal with its API keys page, a create dialog, and a key API (list, create, delete)
// that answers the key ONCE, in the create call. The page draws whatever key value it receives, large, and logs it to
// its console: if the recorder did not mask it, it would be on the pictures.
// The gateway (/zuno-ai-run/gpt-oss-20b) answers 401 without a key, 200 with a live one, 403 with a revoked one.
// One earlier key exists. Knobs: FAKE_REFUSE_REVOKE=1 the delete answers 403 and the key stays live;
// FAKE_NO_ID=1 the create answer carries no id; FAKE_REREAD=1 the portal asks the server to check the key it was
// given (a masked key then fails that check: the take must say so).
import crypto from "node:crypto";
import http from "node:http";

const port = Number(process.env.FAKE_PORT || 8092);
const keys = new Map([["k-earlier", { name: "an earlier key", status: "active", secret: "sk-oai-EARLIEREARLIEREARLIER" }]]);
let checks = 0;   // FAKE_REREAD: how many times the portal sent a key back to the server

const page = (title, body) => `<!doctype html><title>${title}</title><body style="font:16px sans-serif;margin:24px">${body}`;
const CHOOSER = page("Log in", `<h1>Log in with...</h1><a class="idp" title="Log in with openshift" href="/kc">openshift</a>`);
const LOGIN = page("Sign in", `<form method="get" action="/cb"><input id="username" name="u"><input id="password" name="p" type="password"><button id="kc-login">Sign In</button></form>`);
const PORTAL = page("Red Hat AI portal", `<nav><a href="#endpoints">AI asset endpoints</a> <a href="#keys" id="nav-keys">API keys</a> <a href="#playground">Playground</a></nav>
<main><div id="keys" hidden><h1>API keys</h1><button id="create">Create API key</button><ul id="list"></ul></div>
<div role="dialog" id="dialog" hidden style="border:1px solid #888;padding:16px"><h2>Create API key</h2><label>Name <input type="text" id="name"></label>
<label>Subscription <select id="sub"><option>gpt-oss-20b-ocp-ai-dev</option></select></label><span>gpt-oss-20b-ocp-ai-dev</span>
<button type="button" id="cancel">Cancel</button><button type="submit" id="submit">Create</button></div>
<div id="once" hidden><h2>Copy your key now, it is shown once</h2><p id="value" style="font-size:28px"></p></div></main>
<script>
const $ = (id) => document.getElementById(id);
async function list() {
  // As the portal on 2026-11-16: the list is read by a POST to .../api-keys/search.
  const body = await (await fetch("/maas-consumer-portal/maas/api/v1/api-keys/search", { method: "POST", headers: { "Content-Type": "application/json", "X-Portal": "1" }, body: JSON.stringify({ filters: {}, pagination: { limit: 50 } }) })).json();
  $("list").innerHTML = "";
  for (const k of body.data.items) { const li = document.createElement("li"); li.textContent = k.name + " (" + k.status + ")"; $("list").appendChild(li); }
}
$("nav-keys").onclick = (e) => { e.preventDefault(); $("keys").hidden = false; list(); };
$("create").onclick = () => { $("dialog").hidden = false; };
$("cancel").onclick = () => { $("dialog").hidden = true; };
$("submit").onclick = async () => {
  const r = await fetch("/maas-consumer-portal/maas/api/v1/api-keys", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: $("name").value, subscription: $("sub").value }) });
  const made = await r.json();
  $("dialog").hidden = true; $("once").hidden = false; $("value").textContent = made.key; console.log("key shown once: " + made.key);
  if (${process.env.FAKE_REREAD === "1"}) fetch("/maas-consumer-portal/maas/api/v1/check", { method: "PUT", body: made.key });
  list();
};
</script>`);

http.createServer((req, res) => {
  const u = new URL(req.url, "http://x");
  const signed = /(^|; )s=1/.test(req.headers.cookie || "");
  const html = (body) => { res.writeHead(200, { "Content-Type": "text/html" }); res.end(body); };
  const json = (code, body) => { res.writeHead(code, { "Content-Type": "application/json" }); res.end(body === undefined ? "" : JSON.stringify(body)); };
  const body = (then) => { let raw = ""; req.on("data", (c) => { raw += c; }); req.on("end", () => then(raw)); };
  if (u.pathname === "/fake/count") return json(200, { keys: keys.size, live: [...keys.values()].filter((k) => k.status === "active").length, checks });
  // The MaaS gateway: no session, only the key.
  if (u.pathname.startsWith("/zuno-ai-run/gpt-oss-20b/")) {
    const sent = (req.headers.authorization || "").replace(/^Bearer /, "");
    const key = [...keys.values()].find((k) => k.secret === sent);
    if (!key) return json(401, { error: "unauthenticated" });
    if (key.status !== "active") return json(403, { error: "revoked" });
    if (u.pathname.endsWith("/v1/models")) return json(200, { data: [{ id: "gpt-oss-20b" }] });
    return body(() => json(200, { choices: [{ message: { role: "assistant", content: "I can answer questions and help you write and review text and code." } }], usage: { prompt_tokens: 21, completion_tokens: 15, total_tokens: 36 } }));
  }
  if (u.pathname === "/kc") return html(LOGIN);
  if (u.pathname === "/cb") { res.writeHead(302, { Location: "/maas-consumer-portal/", "Set-Cookie": "s=1; Path=/" }); return res.end(); }
  if (!signed) return u.pathname.includes("/api/") ? json(401, {}) : html(CHOOSER);
  if (u.pathname === "/maas-consumer-portal/maas/api/v1/check") { checks += 1; return json(200, {}); }
  if (u.pathname === "/maas-consumer-portal/maas/api/v1/api-keys/search" && req.method === "POST") {
    if (req.headers["x-portal"] !== "1") return json(400, { error: "the portal's own header is missing" });
    // As the portal on 2026-11-16: the list is not `data` itself but inside it.
    return json(200, { data: { items: [...keys].map(([id, k]) => ({ id, name: k.name, status: k.status, subscription: "gpt-oss-20b-ocp-ai-dev" })), total: keys.size } });
  }
  if (u.pathname === "/maas-consumer-portal/maas/api/v1/api-keys" && req.method === "POST") {
    return body((raw) => {
      const id = "k-" + crypto.randomUUID().slice(0, 8);
      const secret = "sk-oai-" + crypto.randomBytes(18).toString("base64url");
      keys.set(id, { name: JSON.parse(raw).name, status: "active", secret });
      json(201, process.env.FAKE_NO_ID === "1" ? { key: secret, name: JSON.parse(raw).name } : { id, key: secret, name: JSON.parse(raw).name });
    });
  }
  if (u.pathname === "/maas-consumer-portal/maas/api/v1/api-keys/search") return json(405, {});
  const one = u.pathname.match(/^\/maas-consumer-portal\/maas\/api\/v1\/api-keys\/([^/]+)$/);
  if (one && req.method === "DELETE") {
    if (process.env.FAKE_REFUSE_REVOKE === "1" || !keys.has(one[1])) return json(403, {});
    keys.get(one[1]).status = "revoked";
    return json(204);
  }
  return html(PORTAL);
}).listen(port, "127.0.0.1");
