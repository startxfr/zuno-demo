// WP-289: a stand-in for the OpenShift sign-in and the OpenShift AI dashboard's model catalog, for the offline test
// of walkthroughs/model-catalog-registry.mjs (tests/walkthroughs-offline.sh). As the scout of 2026-11-16 saw it: the
// provider chooser and Keycloak, a home page with project cards, a collapsed "AI hub" menu group holding one link,
// "Models", the Models page with its tabs, the catalog's source buttons in a toggle group "Source label selection"
// ("Red Hat AI - validated models" among them, after a banner button and a link that carry the same words) and a card's
// page that shows a spinner before its content. Still GUESSED: the Models page opening on another tab than "Catalog"
// (live, it opens on Catalog), the cards' markup and the Deploy button. It proves the walkthrough's own logic, not the
// real selectors.
// Knobs: FAKE_DIALOG=1 a welcome dialog covers the dashboard; FAKE_CHECKBOX=1 the source filter is a checkbox;
// FAKE_APPROVE=1 OpenShift asks to authorize access after the sign-in; FAKE_NO_CATALOG=1 the Catalog tab shows no
// source and no card. /fake/count says how many deployments were
// started (a take and a scout must leave it at 0). No cluster, no model.
import http from "node:http";

const port = Number(process.env.FAKE_PORT || 8095);
let deploys = 0;

const CHOOSER = `<!doctype html><title>Log in</title><h1>Log in with...</h1>
<a class="idp" title="Log in with startx-htpasswd_auth" href="/htpasswd">startx-htpasswd_auth</a><br>
<a class="idp" title="Log in with openshift" href="/kc">openshift</a>`;
const LOGIN = `<!doctype html><title>Sign in</title><form method="get" action="/cb"><input id="username" name="u">
<input id="password" name="p" type="password"><button id="kc-login">Sign In</button></form>`;
const APPROVE = `<!doctype html><title>Authorize Access</title><h1>Authorize Access</h1>
<form method="post" action="/oauth/authorize/approve"><button>Allow selected permissions</button></form>`;

const MODELS = [
  { name: "granite-3.1-8b-instruct", source: "Red Hat AI" },
  { name: "llama-3.3-70b-instruct-quantized", source: "Red Hat AI validated" },
  { name: "mistral-small-24b-instruct", source: "Red Hat AI validated" },
  { name: "phi-4", source: "Other models" },
];

const STYLE = `<style>body{font:16px sans-serif;margin:0;display:flex} #page-sidebar{width:220px;min-height:100vh;background:#212427;color:#fff;padding:12px}
#page-sidebar [hidden]{display:none} #page-sidebar a,#page-sidebar button{color:#fff;display:block;margin:6px 0;background:none;border:0;font:inherit;cursor:pointer;text-align:left}
main{padding:24px;flex:1} .pf-v6-c-card{border:1px solid #888;margin:8px;padding:12px;display:inline-block;width:240px}
.modal{position:fixed;inset:0;background:rgba(0,0,0,.4)} .modal>div{background:#fff;margin:120px auto;width:400px;padding:24px}</style>`;

function shell(body, { dialog = false } = {}) {
  return `<!doctype html><title>Red Hat OpenShift AI (fake)</title>${STYLE}
<nav id="page-sidebar" aria-label="Global"><p>ai-dev-01</p><a href="/">Home</a>
<a href="/projects">Projects</a>
<button id="group" aria-expanded="false" onclick="this.setAttribute('aria-expanded','true');document.getElementById('cat').hidden=false">AI hub</button>
<a id="cat" href="/ai-hub/models" hidden>Models</a></nav>
<main>${body}</main>
${dialog ? `<div class="modal" role="dialog" aria-modal="true"><div><h2>Welcome to Red Hat OpenShift AI</h2><button onclick="this.closest('.modal').remove()">Close</button></div></div>` : ""}`;
}

function tabs(selected) {
  return `<div role="tablist">${[["Catalog", "/ai-hub/models/catalog"], ["Deployments", "/ai-hub/models"]].map(([name, href]) =>
    `<a role="tab" aria-selected="${name === selected}" href="${href}">${name}</a>`).join(" ")}</div>`;
}

// The source buttons as seen live: label -> the source of the models it shows.
const SOURCE_BUTTONS = [["all", "All models", ""], ["label-Red Hat AI validated", "Red Hat AI - validated models", "Red Hat AI validated"],
                        ["label-Red Hat AI", "Red Hat AI models", "Red Hat AI"], ["no-labels", "Other models", "Other models"]];

function catalog() {
  const filter = SOURCE_BUTTONS.map(([id, label, source]) => process.env.FAKE_CHECKBOX === "1" && source === "Red Hat AI validated"
    ? `<button id="${id}" aria-pressed="false"><input type="checkbox" id="only"> ${label}</button>`
    : `<button class="source" id="${id}" data-source="${source}" aria-pressed="${id === "all"}">${label}</button>`).join(" ");
  return shell(`<h1 data-testid="app-page-title">Models</h1>${tabs("Catalog")}
<button onclick="location.href='/ai-hub/models/catalog?banner=1'">Explore Red Hat AI - validated models</button>
<a href="/ai-hub/models/catalog?all=validated">Show all Red Hat AI - validated models</a>
<div role="group" aria-label="Source label selection" id="filters">${filter}</div><div id="cards"></div>
<script>
const MODELS = ${JSON.stringify(MODELS)};
function show(source) {
  document.getElementById("cards").innerHTML = MODELS.filter((m) => !source || m.source === source).map((m) =>
    '<div class="pf-v6-c-card" data-testid="model-catalog-card"><a href="/ai-hub/models/catalog/' + m.name + '">' + m.name + '</a><p>' + m.source + '</p></div>').join("");
}
show("");
document.querySelectorAll("button.source").forEach((b) => { b.onclick = () => {
  document.querySelectorAll("button.source").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  show(b.dataset.source);
}; });
const only = document.getElementById("only");
if (only) only.onchange = () => show(only.checked ? "Red Hat AI validated" : "");
</script>`);
}

function card(name) {
  const m = MODELS.find((x) => x.name === name);
  if (!m) return null;
  // Like the live page: a spinner first, the card's content 1.5 s later.
  return shell(`<p><a href="/ai-hub/models/catalog">Model Catalog</a> / ${m.name}</p><div id="detail"><svg role="progressbar" aria-valuetext="Loading..." width="40" height="40"><circle cx="20" cy="20" r="15"/></svg></div>
<script>setTimeout(() => { document.getElementById("detail").innerHTML = ${JSON.stringify(`<h1 data-testid="app-page-title">${m.name}</h1><p>${m.source}</p>
<h2>Performance</h2><p>Validated on 1 x H100: 1,200 tokens per second.</p>
<button onclick="fetch('/api/k8s/apis/serving.kserve.io/v1beta1/namespaces/x/inferenceservices',{method:'POST'})">Deploy</button>`)}; }, 1500);</script>`);
}

http.createServer((req, res) => {
  const u = new URL(req.url, "http://x");
  const signed = /(^|; )s=1/.test(req.headers.cookie || "");
  const html = (body, code = 200) => { res.writeHead(code, { "Content-Type": "text/html" }); res.end(body); };
  const json = (code, body) => { res.writeHead(code, { "Content-Type": "application/json" }); res.end(JSON.stringify(body)); };
  if (u.pathname === "/fake/count") return json(200, { deploys });
  if (u.pathname === "/kc") return html(LOGIN);
  if (u.pathname === "/cb") {
    res.writeHead(302, { "Set-Cookie": "s=1; Path=/", Location: process.env.FAKE_APPROVE === "1" ? "/oauth/authorize/approve" : "/" });
    return res.end();
  }
  if (u.pathname === "/oauth/authorize/approve") return html(APPROVE);
  if (!signed) return u.pathname.startsWith("/api") ? json(401, {}) : html(CHOOSER);
  if (/\/inferenceservices$/.test(u.pathname) && req.method === "POST") { deploys += 1; return json(201, {}); }
  if (u.pathname === "/ai-hub/models") return html(shell(`<h1 data-testid="app-page-title">Models</h1>${tabs("Deployments")}<p>No deployments.</p>`));
  if (u.pathname === "/ai-hub/models/catalog") {
    return html(process.env.FAKE_NO_CATALOG === "1" ? shell(`<h1 data-testid="app-page-title">Models</h1>${tabs("Catalog")}<p>Loading...</p>`) : catalog());
  }
  const one = u.pathname.match(/^\/ai-hub\/models\/catalog\/([^/]+)$/);
  if (one) return html(card(decodeURIComponent(one[1])) || "not found", card(decodeURIComponent(one[1])) ? 200 : 404);
  return html(shell(`<h1>Projects</h1><div class="pf-v6-c-card"><a href="/projects/zuno-ai-build">Zuno AI Build</a></div>
<p>Red Hat OpenShift AI</p>`, { dialog: process.env.FAKE_DIALOG === "1" }));
}).listen(port, "127.0.0.1");
