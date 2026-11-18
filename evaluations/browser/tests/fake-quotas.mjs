// WP-289: a stand-in for Grafana (behind its OpenShift oauth-proxy, the provider chooser and Keycloak) and for the
// quotas page on GitHub, for the offline test of walkthroughs/quotas.mjs (tests/walkthroughs-offline.sh). Its own file:
// tests/fake-grafana.mjs, the coder's, stays as it is. Like it, it is shaped like the GUESSES of _grafana.mjs and of
// the walkthrough, not like the real sites: it proves the walkthrough's own logic, not their selectors.
// Grafana, on FAKE_PORT (8089): the proxy's "Log in with OpenShift", the chooser, the Keycloak form, then the dashboard
// zuno-three-experiences, whose panel 7 is a table (group, client, Value) far down the page, or alone over the page
// with `viewPanel=panel-7`. GitHub, on GITHUB_PORT (8088): the page at /startxfr/zuno-demo/blob/devel/..., as the scout
// of 2026-11-16 saw it: a 167 px header that scrolls away, a 320 px file tree, a sticky 56 px file toolbar, then the
// rendered Markdown with the class table and the evidence list among long paragraphs.
// Knobs: FAKE_NO_DATA=1 the panel shows "No data"; FAKE_STAR=1 the dashboard stars itself when opened (a write);
// FAKE_GITHUB_DOWN=1 nothing listens on GITHUB_PORT; FAKE_GITHUB_BANNER=1 a fixed banner covers the top of the page;
// FAKE_GITHUB_RESET=1 the page scrolls itself back to its top once, half a second after the first scroll.
// /fake/count on FAKE_PORT says {writes, github_writes}: the non-GET requests to Grafana's API (queries aside) and to
// the GitHub stand-in. No cluster.
import http from "node:http";

const port = Number(process.env.FAKE_PORT || 8089);
const githubPort = Number(process.env.GITHUB_PORT || 8088);
let writes = 0;
let githubWrites = 0;

const html = (res, body, headers = {}) => { res.writeHead(200, { "content-type": "text/html", ...headers }); res.end(body); };
const json = (res, status, body) => { res.writeHead(status, { "content-type": "application/json" }); res.end(JSON.stringify(body)); };
const page = (title, body) => `<!doctype html><title>${title}</title><body style="font:16px sans-serif;margin:24px">${body}`;

const TITLE = "One group across the experiences: tokens (over range)";
const ROWS = [["sales", "open-webui", "1840"], ["sales", "openclaw-sale-01", "2124"], ["consultant", "open-webui", "960"]];
const table = () => (process.env.FAKE_NO_DATA === "1" ? "<div>No data</div>"
  : `<table><thead><tr>${["Time", "group", "client", "Value"].map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>`
    + ROWS.map((r) => `<tr><td>2026-11-16 12:00:00</td>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("") + "</tbody></table>");
const section = (alone) => `<section data-testid="data-testid Panel header ${TITLE}" style="border:1px solid #888;padding:8px;width:${alone ? 1100 : 420}px">
<header><h2>${TITLE}</h2></header>${table()}</section>`;

http.createServer((req, res) => {
  const u = new URL(req.url, "http://fake");
  const signed = /(?:^|; )grafana_session=ai-ops-01/.test(req.headers.cookie || "");
  if (u.pathname === "/fake/count") return json(res, 200, { writes, github_writes: githubWrites });
  if (u.pathname === "/api/ds/query") return json(res, 200, { results: {} });
  if (u.pathname.startsWith("/api/") && req.method !== "GET") { writes += 1; return json(res, 200, {}); }
  if (u.pathname === "/oauth/start") return html(res, page("Log in", `<h1>Log in with...</h1><a class="idp" title="Log in with openshift" href="/kc">openshift</a>`));
  if (u.pathname === "/kc") return html(res, page("Sign in", `<form method="get" action="/cb"><input id="username" name="u"><input id="password" name="p" type="password"><button id="kc-login">Sign In</button></form>`));
  if (u.pathname === "/cb") { res.writeHead(302, { location: "/", "set-cookie": `grafana_session=${u.searchParams.get("u")}; Path=/` }); return res.end(); }
  if (!signed) return html(res, page("Log In", `<form action="/oauth/start"><button>Log in with OpenShift</button></form>`));
  if (u.pathname === "/") return html(res, page("Home - Grafana", `<main><h1>Welcome to Grafana</h1><span>ai-ops-01</span></main>`));
  if (u.pathname.startsWith("/d/zuno-three-experiences")) {
    const alone = (u.searchParams.get("viewPanel") || "") === "panel-7";
    const star = process.env.FAKE_STAR === "1" ? `<script>fetch("/api/user/stars/dashboard/uid/zuno-three-experiences", {method: "POST"})</script>` : "";
    return html(res, page("Five experiences - Grafana", `<header><h1>Zuno Platform / Five experiences</h1><span>Last 24 hours</span> <span>client ${u.searchParams.get("var-client") || "All"}</span></header>
<main><div class="react-grid-layout">${alone ? section(true) : `<h3>Same backend, five experiences</h3><div style="height:900px"></div><h3>One budget across the experiences</h3>${section(false)}`}
<div style="height:600px"></div></div></main>${star}`));
  }
  return json(res, 404, {});
}).listen(port, "127.0.0.1");

// The page on GitHub: long enough that both places must be scrolled to.
const filler = (n) => Array.from({ length: n }, (_, i) => `<p>Paragraph ${i + 1} of the page, words that take a line or two on the screen, as a real page does.</p>`).join("\n");
const GITHUB = `<!doctype html><title>quotas.md - startxfr/zuno-demo</title><body style="font:16px sans-serif;margin:0">
<div style="height:167px;background:#111;color:#fff">GitHub header, startxfr / zuno-demo, Code Issues Pull requests</div>
<div style="display:flex"><div style="width:320px;flex:none;background:#f6f6f6">Files<br>docs/demo/scenarios/governance</div><div style="flex:1">
<div style="position:sticky;top:0;height:56px;background:#eee;z-index:5">quotas.md  Preview Code Blame  361 lines</div>
${process.env.FAKE_GITHUB_RESET === "1" ? `<script>addEventListener("scroll", function once() { removeEventListener("scroll", once); setTimeout(() => scrollTo(0, 0), 500); });</script>` : ""}
${process.env.FAKE_GITHUB_BANNER === "1" ? `<div style="position:fixed;top:0;left:0;right:0;height:300px;background:#fc0;z-index:9">Sign up to GitHub</div>` : ""}
<article class="markdown-body" style="max-width:1000px;margin:0 auto;padding:16px">
<h1>Scenario: quotas</h1>${filler(25)}
<p>The classes come from the signed agents release (<a href="#">policies/quotas/quota-policy.yaml</a>):</p>
<table><thead><tr><th>Class</th><th>Who runs under it</th><th>Per user (persona)</th><th>Per group</th><th><code>fail_mode</code></th></tr></thead><tbody>
<tr><td><code>standard</code></td><td>everyone, by default</td><td>10,000,000 tokens per 24 h</td><td>100,000,000 per 24 h</td><td>open</td></tr>
<tr><td><code>evaluation</code></td><td>members of <code>zuno-evaluation</code></td><td>20,000,000 per 24 h</td><td>200,000,000 per 24 h</td><td>open</td></tr>
<tr><td><code>intensive</code></td><td>no task opts in today</td><td>500,000 per 24 h</td><td>5,000,000 per 24 h</td><td>closed</td></tr>
<tr><td><code>stresstest</code></td><td>the group named by <code>QUOTA_STRESSTEST_GROUP</code> (off)</td><td>2,000 per 5 min</td><td>8,000 per 5 min</td><td>closed</td></tr>
</tbody></table>${filler(30)}
<p><strong>Evidence of the shared budget (2026-11-03, ai-gateway build 36, <a href="#">WP-190 proof</a>).</strong> sale-01 and its OpenClaw service account were put in a group under the <code>stresstest</code> class:</p>
<ul><li>01:10-01:12, sale-01's OpenClaw assistant, one large turn: 200, 2,124 tokens;</li>
<li>01:12:40, Open WebUI as sale-01: 429 <code>{"error":"quota_exceeded","quota_class":"stresstest","dimension":"user","budget_tokens":2000,"window":"5m"}</code>;</li>
<li>01:12-01:14, UnifAI (team <code>agent-comage</code>): the card "Rate limit reached";</li>
<li>01:14:00, OpenClaw, a short turn: 429, the same body, in 0.03 s.</li></ul>${filler(30)}
</article></div></div>`;
if (process.env.FAKE_GITHUB_DOWN !== "1") {
  http.createServer((req, res) => {
    if (req.method !== "GET") { githubWrites += 1; return json(res, 403, {}); }
    if (req.url.split("?")[0] === "/startxfr/zuno-demo/blob/devel/docs/demo/scenarios/governance/quotas.md") return html(res, GITHUB);
    return json(res, 404, {});
  }).listen(githubPort, "127.0.0.1");
}
