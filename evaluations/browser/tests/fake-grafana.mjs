// WP-288: a stand-in for Grafana behind its OpenShift oauth-proxy, OpenShift's provider chooser and Keycloak, for
// the offline test of walkthroughs/evaluation-trustyai-evalhub.mjs and of walkthroughs/_grafana.mjs
// (tests/walkthroughs-offline.sh). It serves what the helper GUESSES the chain is (no scout has run yet): the proxy's
// page with "Log in with OpenShift", the chooser, the Keycloak form, then the dashboard zuno-trustyai with its three
// evaluation panels far down the page, each drawn only once it is near the screen and after a query (a POST, as in
// Grafana: a read). It proves the walkthrough's own logic, not Grafana's real selectors.
// Knobs: FAKE_AUTHORIZE=1 OpenShift shows "Authorize Access" after the sign-in (approving it counts as approved;
// =more: with a third permission; =other: for another client);
// FAKE_NO_DATA=1 the Garak panel shows "No data"; FAKE_STAR=1 the dashboard stars itself when opened (a write).
import http from "node:http";

const port = Number(process.env.FAKE_PORT || 8095);
let loads = 0;      // loads of the Five experiences dashboard
let stored = 0;     // entries written to Grafana's user storage (FAKE_NEWS=storage: the close of the announcement)
let approved = 0;   // "Authorize Access" approved: a take or a scout must leave it at 0
let writes = 0;     // writes received by Grafana's API: must stay 0 (FAKE_STAR=1 aside, refused in a scout)

// FAKE_NEWS=1: Grafana's announcement covers every signed-in page a moment after it loads, until it is closed (kept in
// the browser); FAKE_NEWS=server: closing it also saves a preference on the server; FAKE_NEWS=storage: closing it
// writes one entry to Grafana's user storage, as Grafana did on 2026-11-16; FAKE_NEWS=other: another dialog.
const NEWS = !process.env.FAKE_NEWS ? "" : `<div role="dialog" id="news" hidden style="position:fixed;top:80px;left:200px;width:800px;height:500px;background:#223;color:#fff;z-index:9">
<button aria-label="Close" id="news-close">x</button><span>${process.env.FAKE_NEWS === "other" ? "Your session is about to expire" : "NEW</span><h2>Grafana Assistant is now available to OSS users</h2><span>1/4"}</span></div>
<script>
setTimeout(() => { if (!localStorage.getItem("grafana.whatsnew.dismissed")) document.getElementById("news").hidden = false; }, 700);
document.getElementById("news-close").onclick = () => {
  localStorage.setItem("grafana.whatsnew.dismissed", "1");
  if (${process.env.FAKE_NEWS === "server"}) fetch("/api/user/preferences", { method: "PATCH", body: "{}" });
  if (${process.env.FAKE_NEWS === "storage"}) fetch("/apis/userstorage.grafana.app/v0alpha1/namespaces/default/user-storage/", { method: "POST", body: JSON.stringify({ metadata: { name: "grafana-whatsnew:1" }, spec: { data: { dismissed: "seen-1" } } }) });
  document.getElementById("news").hidden = true;
};
</script>`;
const page = (title, body) => `<!doctype html><title>${title}</title><body style="font:16px sans-serif;margin:24px">${body}${/Grafana$/.test(title) ? NEWS : ""}`;
const PROXY = page("Log In", `<form action="/oauth/start"><button>Log in with OpenShift</button></form>`);
const CHOOSER = page("Log in", `<h1>Log in with...</h1><a class="idp" title="Log in with startx-htpasswd_auth" href="/htpasswd">startx-htpasswd_auth</a><br>
<a class="idp" title="Log in with openshift" href="/kc">openshift</a>`);
const LOGIN = page("Sign in", `<form method="get" action="/cb"><input id="username" name="u"><input id="password" name="p" type="password"><button id="kc-login">Sign In</button></form>`);
// As seen live on 2026-11-16. FAKE_AUTHORIZE=more asks for one more permission; FAKE_AUTHORIZE=other is another client.
const AUTHORIZE = page("Authorize", `<h1>Authorize Access</h1><p>Service account ${process.env.FAKE_AUTHORIZE === "other" ? "some-other-proxy" : "grafana-oauth-proxy"} in project zuno-monitoring is requesting permission to access your account (ai-ops-01)</p>
<form action="/approve"><p>Requested permissions</p>
<label><input type="checkbox" name="scope" value="user:info" checked> user:info</label><br><label><input type="checkbox" name="scope" value="user:check-access" checked> user:check-access</label><br>
${process.env.FAKE_AUTHORIZE === "more" ? '<label><input type="checkbox" name="scope" value="user:full" checked> user:full</label><br>' : ""}
<input type="submit" name="approve" value="Allow selected permissions"> <input type="submit" name="deny" value="Deny"></form>`);

// A table panel: its header cells and its rows, each cell an element of its own (a take checks that a header is drawn
// inside the window). In the dashboard's grid a panel is 420 px wide and its last column is cut off, as in Grafana on
// 2026-11-16; alone over the page (viewPanel) it has the page's width. FAKE_NARROW=1: the last header is cut off (an ellipsis) even alone.
const cell = (text) => `<span style="display:inline-block;width:150px;white-space:nowrap">${text}</span> `;
const cut = (text) => `<span style="display:inline-block;width:14px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis">${text}</span> `;
const table = (headers, rows) => `<div style="white-space:nowrap">${headers.map((h, i) => (process.env.FAKE_NARROW === "1" && i === headers.length - 1 ? cut(h) : cell(h))).join("")}</div>${rows.map((row) => `<div style="white-space:nowrap">${row.map(cell).join("")}</div>`).join("")}`;
const section = (title, i, body, alone) => `<section data-testid="data-testid Panel header ${title}" data-i="${i}" style="border:1px solid #888;padding:8px;min-height:160px;overflow:hidden;width:${alone ? 1100 : 420}px"><header><h2>${title}</h2></header><div class="content">${body}</div></section>`;
// viewPanel in the address: `panel-<id>`, as Grafana names it now (FAKE_VIEW=old: only the bare `<id>` is understood).
const viewed = (u) => { const v = u.searchParams.get("viewPanel") || ""; const m = v.match(process.env.FAKE_VIEW === "old" ? /^(\d+)$/ : /^panel-(\d+)$/); return m ? Number(m[1]) : 0; };

const GARAK = process.env.FAKE_NO_DATA === "1" ? null : [["mitigation.MitigationBypass", "qwen3.5-9b-wesh", "dan.DAN", "1.00"]];
const PANELS = [
  [1, "Exchanges evaluated, by outcome", ["outcome", "count"], [["clean", "412"], ["detected", "3"]]],
  [4, "Garak / RAGAS job outcomes", ["job", "succeeded", "failed"], [["garak-security", "1", "0"], ["garak-smoke", "1", "0"], ["ragas-eval", "1", "0"]]],
  [6, "RAGAS scores (real UnifAI retrievals)", ["metric", "question", "score"], [["faithfulness", "Comment configurer ?", "0.91"], ["llm_context_precision", "Comment configurer ?", "0.83"]]],
  [7, "Garak attack success rate (jailbreak probes)", ["detector", "model", "probe", "attack success rate"], GARAK],
];
const BODIES = PANELS.map(([, , headers, rows]) => (rows ? table(headers, rows) : "No data"));
const dashboard = (only) => page("TrustyAI evaluation & guardrails - Grafana", `<header><h1>Zuno Platform / TrustyAI evaluation & guardrails</h1><span>Last 7 days</span> <span>ai-ops-01</span></header>
<main><div class="react-grid-layout">${PANELS.map(([id, title], i) => (only && only !== id ? "" : `<div style="height:${only ? 20 : i ? 520 : 300}px"></div>${section(title, i, "", Boolean(only))}`)).join("")}
<div style="height:600px"></div></div></main>
<script>
const bodies = ${JSON.stringify(BODIES)};
if (${process.env.FAKE_STAR === "1"}) fetch("/api/user/stars/dashboard/uid/zuno-trustyai", { method: "POST" });
// A panel queries and draws only once it is near the screen, like Grafana.
const seen = new IntersectionObserver((entries) => {
  for (const e of entries) {
    if (!e.isIntersecting || e.target.dataset.asked) continue;
    e.target.dataset.asked = "1";
    const content = e.target.querySelector(".content");
    content.innerHTML = '<div aria-label="Panel loading bar">loading</div>';
    fetch("/api/ds/query", { method: "POST", body: "{}" }).then(() => setTimeout(() => { content.innerHTML = bodies[Number(e.target.dataset.i)]; }, 900));
  }
});
document.querySelectorAll("section").forEach((s) => seen.observe(s));
</script>`);

http.createServer((req, res) => {
  const u = new URL(req.url, "http://x");
  const cookies = req.headers.cookie || "";
  const signed = /(^|; )s=1/.test(cookies);
  const html = (body) => { res.writeHead(200, { "Content-Type": "text/html" }); res.end(body); };
  const json = (code, body) => { res.writeHead(code, { "Content-Type": "application/json" }); res.end(JSON.stringify(body)); };
  const to = (location, cookie) => { res.writeHead(302, { Location: location, ...(cookie ? { "Set-Cookie": cookie } : {}) }); res.end(); };
  if (u.pathname === "/fake/count") return json(200, { approved, writes, ...(stored ? { stored } : {}) });
  if (u.pathname.startsWith("/apis/userstorage.grafana.app/") && req.method === "POST" && signed) { stored += 1; return json(201, {}); }
  if (u.pathname === "/oauth/start") return html(CHOOSER);
  if (u.pathname === "/kc") return html(LOGIN);
  if (u.pathname === "/cb") return process.env.FAKE_AUTHORIZE ? html(AUTHORIZE) : to("/", "s=1; Path=/");
  if (u.pathname === "/approve") { if (u.searchParams.has("approve")) approved += 1; return to("/", u.searchParams.has("approve") ? "s=1; Path=/" : ""); }
  if (!signed) return u.pathname.startsWith("/api") ? json(401, {}) : html(PROXY);
  if (u.pathname === "/api/ds/query") return json(200, { results: {} });
  if (u.pathname.startsWith("/api/") && req.method !== "GET") { writes += 1; return json(200, {}); }
  if (u.pathname === "/") return html(page("Home - Grafana", `<main><h1>Welcome to Grafana</h1><span>ai-ops-01</span></main>`));
  if (u.pathname.startsWith("/d/zuno-trustyai")) return html(dashboard(viewed(u)));
  if (u.pathname.startsWith("/d/zuno-three-experiences")) {
    // ai-gateway-routing: the Codestral row reaches the panel late, as a real call does: from the second load of the
    // panel alone on (FAKE_NO_PROOF=1: never).
    const only = viewed(u);
    if (only) loads += 1;
    const rows = [["open-webui", "success", "local-gpt-oss-maas"]].concat(loads >= 2 && process.env.FAKE_NO_PROOF !== "1" ? [["open-webui", "success", "mistral-codestral"]] : []);
    const title = "Which provider served each experience (over range)";
    return html(page("Five experiences - Grafana", `<header><h1>Zuno Platform / Five experiences</h1><span>Last 1 hour</span> <span>client ${u.searchParams.get("var-client") || "All"}</span></header>
<main><div class="react-grid-layout">${only && only !== 5 ? "" : `<div style="height:${only ? 20 : 700}px"><h3>Same models, same routing</h3></div>
${section(title, 0, table(["client", "outcome", "provider"], rows), Boolean(only))}`}<div style="height:600px"></div></div></main>`));
  }
  return json(404, {});
}).listen(port, "127.0.0.1");
