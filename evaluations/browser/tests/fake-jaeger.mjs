// WP-288: a stand-in for the Tempo search UI (the Jaeger UI) behind its OpenShift oauth-proxy, for the offline test of
// walkthroughs/observability-trace.mjs (tests/walkthroughs-offline.sh). It serves what the walkthrough GUESSES (the
// search was never seen live): the proxy's page, the provider chooser, the Keycloak form, a search page driven by its
// address, a trace page with its spans, and a span's detail with a Tags accordion and a Process line.
// The search lists a trace from its second load on, as a real export does (FAKE_NO_TRACE=1: never; FAKE_TRACE_NOW=1:
// at once). Knobs: FAKE_AUTHORIZE=1 OpenShift shows "Authorize Access" for the Tempo UI's own client (=other: for another client);
// FAKE_ADDRESSES=1 the span's Process line holds the pod's address and its node; FAKE_NO_TAGS=1 the span has no
// zuno.* tag.
import http from "node:http";

const port = Number(process.env.FAKE_PORT || 8093);
let searches = 0;
let approved = 0;
let writes = 0;
const TRACE = "4bf92f3577b34da6a3ce929d0e0e4736";

const page = (title, body) => `<!doctype html><title>${title}</title><body style="font:15px sans-serif;margin:16px">${body}`;
const PROXY = page("Log In", `<form action="/oauth/start"><button>Log in with OpenShift</button></form>`);
const CHOOSER = page("Log in", `<h1>Log in with...</h1><a class="idp" title="Log in with openshift" href="/kc">openshift</a>`);
const LOGIN = page("Sign in", `<form method="get" action="/cb"><input id="username" name="u"><input id="password" name="p" type="password"><button id="kc-login">Sign In</button></form>`);
const AUTHORIZE = page("Authorize", `<h1>Authorize Access</h1><p>Service account ${process.env.FAKE_AUTHORIZE === "other" ? "some-other-proxy" : "tempo-tempo"} in project zuno-monitoring is requesting permission to access your account (ai-ops-01)</p>
<form action="/approve"><label><input type="checkbox" checked value="user:info"> user:info</label><label><input type="checkbox" checked value="user:check-access"> user:check-access</label>
<input type="submit" name="approve" value="Allow selected permissions"> <input type="submit" name="deny" value="Deny"></form>`);   // as seen live on 2026-11-16
// FAKE_ERROR_SPAN=1: the newest span is a failed call, as the one the rescout of 2026-11-16 opened.
const TAGS = process.env.FAKE_NO_TAGS === "1" ? [["http.method", "POST"]] : [...(process.env.FAKE_ERROR_SPAN === "1" ? [["error", "true"], ["otel.status_code", "ERROR"]] : []), ["zuno.persona", "consultant-02"], ["zuno.client", "unifai"], ["zuno.agent", "tekos"], ["zuno.task", "answer-technical-question"],
  ["zuno.classification", "C2"], ["zuno.model_kind", "local"], ["zuno.provider", "local-gpt-oss-maas"], ["zuno.model", "gpt-oss-20b"], ["zuno.latency_ms", "912"],
  ["zuno.estimated_cost_usd", "0.0004"], ["zuno.outcome", "success"], ["zuno.run_id", "run-1"]];
const PROCESS = process.env.FAKE_ADDRESSES === "1" ? "Process: ip = 10.131.2.14 k8s.node.name = ip-10-18-3-7.eu-west-3.compute.internal" : "Process: service.name = ai-gateway";

http.createServer((req, res) => {
  const u = new URL(req.url, "http://x");
  const signed = /(^|; )s=1/.test(req.headers.cookie || "");
  const html = (body) => { res.writeHead(200, { "Content-Type": "text/html" }); res.end(body); };
  const json = (code, body) => { res.writeHead(code, { "Content-Type": "application/json" }); res.end(JSON.stringify(body)); };
  const to = (location, cookie) => { res.writeHead(302, { Location: location, ...(cookie ? { "Set-Cookie": cookie } : {}) }); res.end(); };
  if (u.pathname === "/fake/count") return json(200, { approved, writes });
  if (u.pathname === "/oauth/start") return html(CHOOSER);
  if (u.pathname === "/kc") return html(LOGIN);
  if (u.pathname === "/cb") return process.env.FAKE_AUTHORIZE ? html(AUTHORIZE) : to("/", "s=1; Path=/");
  if (u.pathname === "/approve") { if (u.searchParams.has("approve")) approved += 1; return to("/", u.searchParams.has("approve") ? "s=1; Path=/" : ""); }
  if (!signed) return html(PROXY);
  if (req.method !== "GET") { writes += 1; return json(200, {}); }
  if (u.pathname === "/" ) return to("/search");
  if (u.pathname === "/search") {
    const asked = u.searchParams.get("service") === "ai-gateway" && u.searchParams.get("operation") === "model_call"
      && (u.searchParams.get("tags") || "") === JSON.stringify({ "zuno.persona": "consultant-02", "zuno.agent": "tekos" }) && u.searchParams.get("lookback") === "15m"
      // the 15 minutes as two instants in microseconds, or the search is not bounded (as on 2026-11-16)
      && Math.abs(Number(u.searchParams.get("end")) / 1000 - Date.now()) < 120000 && Math.abs(Number(u.searchParams.get("end")) - Number(u.searchParams.get("start")) - 15 * 60e6) < 5e6;
    if (u.searchParams.has("service")) searches += 1;
    const listed = asked && process.env.FAKE_NO_TRACE !== "1" && (searches >= 2 || process.env.FAKE_TRACE_NOW === "1");
    return html(page("Jaeger UI", `<div id="jaeger-ui-root"><form class="SearchForm"><label>Service <input value="${u.searchParams.get("service") || ""}"></label>
<label>Operation <input value="${u.searchParams.get("operation") || ""}"></label><label>Tags <input value="${asked ? "zuno.persona=consultant-02" : ""}"></label>
<span>Last 15 Minutes</span><button type="button">Find Traces</button></form>
<div class="SearchResults">${listed ? `<div class="ResultItem"><a class="ResultItemTitle--item" href="/trace/${TRACE}">unifai: workflow.run ${TRACE.slice(0, 7)}</a><span>14 Spans</span></div>` : "<p>No trace results. Try another query.</p>"}</div></div>`));
  }
  if (u.pathname === `/trace/${TRACE}`) {
    return html(page("Jaeger UI", `<div id="jaeger-ui-root"><h1 class="TracePageHeader">unifai: workflow.run</h1>
<div class="span-row"><a class="span-name">unifai workflow.run</a></div>
<div class="span-row"><a class="span-name" id="mc" role="switch" aria-checked="false">ai-gateway model_call</a></div><div id="detail"></div>
<div class="span-row"><a class="span-name">ai-gateway model_call</a></div></div>
<script>
const tags = ${JSON.stringify(TAGS)};
document.getElementById("mc").onclick = () => {
  document.getElementById("detail").innerHTML = '<div class="detail-row"><div class="AccordianKeyValues"><a class="AccordianKeyValues--header" id="th" role="switch" aria-checked="false">Tags: ' + tags.slice(0, 2).map((t) => t.join("=")).join(" ") + '</a><table id="tt" hidden></table></div>'
    + '<a class="AccordianKeyValues--header">${PROCESS}</a></div>';
  document.getElementById("th").onclick = () => {
    const t = document.getElementById("tt"); t.hidden = false;
    t.innerHTML = tags.map(([k, v]) => "<tr><td>" + k + "</td><td>" + v + "</td></tr>").join("");
  };
};
</script>`));
  }
  return json(404, {});
}).listen(port, "127.0.0.1");
