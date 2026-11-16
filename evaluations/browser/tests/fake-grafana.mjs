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
let approved = 0;   // "Authorize Access" approved: a take or a scout must leave it at 0
let writes = 0;     // writes received by Grafana's API: must stay 0 (FAKE_STAR=1 aside, refused in a scout)

const page = (title, body) => `<!doctype html><title>${title}</title><body style="font:16px sans-serif;margin:24px">${body}`;
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

const PANELS = [
  ["Exchanges evaluated, by outcome", ["clean 412", "detected 3"]],
  ["Garak / RAGAS job outcomes", ["garak-security succeeded 1", "garak-smoke succeeded 1", "ragas-eval succeeded 1"]],
  ["RAGAS scores (real UnifAI retrievals)", ["Comment configurer un cluster OpenShift ? faithfulness 0.91", "Comment configurer un cluster OpenShift ? llm_context_precision 0.83"]],
  ["Garak attack success rate (jailbreak probes)", ["__GARAK__"]],
];
const DASHBOARD = page("TrustyAI evaluation & guardrails - Grafana", `<header><h1>Zuno Platform / TrustyAI evaluation & guardrails</h1><span>Last 7 days</span> <span>ai-ops-01</span></header>
<main><div class="react-grid-layout">${PANELS.map(([title], i) => `<div style="height:${i ? 520 : 300}px"></div>
<section data-testid="data-testid Panel header ${title}" data-i="${i}" style="border:1px solid #888;padding:8px;min-height:160px"><header><h2>${title}</h2></header><div class="content"></div></section>`).join("")}
<div style="height:600px"></div></div></main>
<script>
const rows = ${JSON.stringify(PANELS.map(([, lines]) => lines))};
if (${process.env.FAKE_STAR === "1"}) fetch("/api/user/stars/dashboard/uid/zuno-trustyai", { method: "POST" });
// A panel queries and draws only once it is near the screen, like Grafana.
const seen = new IntersectionObserver((entries) => {
  for (const e of entries) {
    if (!e.isIntersecting || e.target.dataset.asked) continue;
    e.target.dataset.asked = "1";
    const content = e.target.querySelector(".content");
    content.innerHTML = '<div aria-label="Panel loading bar">loading</div>';
    fetch("/api/ds/query", { method: "POST", body: "{}" }).then(() => setTimeout(() => {
      content.innerHTML = "";
      for (const line of rows[Number(e.target.dataset.i)]) { const p = document.createElement("div"); p.textContent = line; content.appendChild(p); }
    }, 900));
  }
});
document.querySelectorAll("section").forEach((s) => seen.observe(s));
</script>`).replace("__GARAK__", process.env.FAKE_NO_DATA === "1" ? "No data" : "mitigation.MitigationBypass qwen3.5-9b-wesh 1.00");

http.createServer((req, res) => {
  const u = new URL(req.url, "http://x");
  const cookies = req.headers.cookie || "";
  const signed = /(^|; )s=1/.test(cookies);
  const html = (body) => { res.writeHead(200, { "Content-Type": "text/html" }); res.end(body); };
  const json = (code, body) => { res.writeHead(code, { "Content-Type": "application/json" }); res.end(JSON.stringify(body)); };
  const to = (location, cookie) => { res.writeHead(302, { Location: location, ...(cookie ? { "Set-Cookie": cookie } : {}) }); res.end(); };
  if (u.pathname === "/fake/count") return json(200, { approved, writes });
  if (u.pathname === "/oauth/start") return html(CHOOSER);
  if (u.pathname === "/kc") return html(LOGIN);
  if (u.pathname === "/cb") return process.env.FAKE_AUTHORIZE ? html(AUTHORIZE) : to("/", "s=1; Path=/");
  if (u.pathname === "/approve") { if (u.searchParams.has("approve")) approved += 1; return to("/", u.searchParams.has("approve") ? "s=1; Path=/" : ""); }
  if (!signed) return u.pathname.startsWith("/api") ? json(401, {}) : html(PROXY);
  if (u.pathname === "/api/ds/query") return json(200, { results: {} });
  if (u.pathname.startsWith("/api/") && req.method !== "GET") { writes += 1; return json(200, {}); }
  if (u.pathname === "/") return html(page("Home - Grafana", `<main><h1>Welcome to Grafana</h1><span>ai-ops-01</span></main>`));
  if (u.pathname.startsWith("/d/zuno-trustyai")) return html(DASHBOARD);
  if (u.pathname.startsWith("/d/zuno-three-experiences")) {
    // ai-gateway-routing: the Codestral row reaches the panel late, as a real call does: from the second load of the
    // dashboard on (FAKE_NO_PROOF=1: never).
    loads += 1;
    const rows = ["open-webui local-gpt-oss-maas success 1"].concat(loads >= 2 && process.env.FAKE_NO_PROOF !== "1" ? ["open-webui mistral-codestral success 2"] : []);
    return html(page("Five experiences - Grafana", `<header><h1>Zuno Platform / Five experiences</h1><span>Last 1 hour</span> <span>client ${u.searchParams.get("var-client") || "All"}</span></header>
<main><div class="react-grid-layout"><div style="height:700px"><h3>Same models, same routing</h3></div>
<section data-testid="data-testid Panel header Which provider served each experience (over range)" style="border:1px solid #888;padding:8px"><header><h2>Which provider served each experience (over range)</h2></header>
${rows.map((row) => `<div>${row}</div>`).join("")}</section><div style="height:600px"></div></div></main>`));
  }
  return json(404, {});
}).listen(port, "127.0.0.1");
