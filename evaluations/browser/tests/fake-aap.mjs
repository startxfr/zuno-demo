// WP-289: a stand-in for AAP's platform UI and Keycloak, for the offline test of walkthroughs/aap-audited-operations.mjs
// (tests/walkthroughs-offline.sh). It is shaped like the walkthrough's GUESSES, not like a real AAP: it proves the
// walkthrough's own logic (the sign-in chain and its fallback, the read-only guard, the job opened by its Details
// address and never its Output, the failures), not its selectors.
// It serves: a sign-in page with AAP's own form and a "Keycloak zuno" link to /api/gateway/social/login/<slug>/, the
// gateway's /api/gateway/v1/ui_auth/, a Keycloak form (GET, same address), then pages under a left menu whose group
// "Automation Execution" is collapsed on /overview: the templates (launch buttons disabled), the jobs with a filter
// box (#filter-input, "apply filter"), a job's Output (with a node name in it) and Details, the projects and the
// project zuno-demo. The job links of the list open the Output, as AAP's may. The controller API answers the reads of
// jobs, unified jobs and projects. Every request that is not a GET is counted and refused.
// Jobs: 101 zuno-day1-check by admin, 102 zuno-day0-check by zuno-mcp, 103 zuno-day0-check by admin (the latest).
// Knobs: FAKE_SSO_HIDDEN=1 the sign-in page shows no Keycloak link; FAKE_LOGIN_LOOP=1 the sign-in comes back to AAP's
// sign-in page; FAKE_NO_MCP_JOB=1 no job launched by zuno-mcp; FAKE_UI_WRITE=1 the first screen POSTs a preference;
// FAKE_DIALOG=1 a dialog covers the first screen. /fake/count says {writes, outputs}: the non-GET requests that reached
// the stand-in and the Output pages served. No cluster.
import http from "node:http";

const port = Number(process.env.FAKE_PORT || 8092);
const SLUG = "ansible_base-authentication-authenticator_plugins-keycloak__keycloak-zuno";
const knob = (name) => process.env[name] === "1";
let writes = 0;
let outputs = 0;

const TEMPLATES = ["zuno-day0-check", "zuno-day1-build", "zuno-day1-check", "zuno-day1-check-workflow", "zuno-day1-install",
                   "zuno-day1-install-workflow", "zuno-day1-reconcile", "zuno-day2-check", "zuno-day3-test"];
const JOBS = [{ id: 101, name: "zuno-day1-check", by: "admin" }, { id: 102, name: "zuno-day0-check", by: "zuno-mcp" },
              { id: 103, name: "zuno-day0-check", by: "admin" }].filter((j) => !(knob("FAKE_NO_MCP_JOB") && j.by === "zuno-mcp"));

const page = (title, body) => `<!doctype html><title>${title}</title><style>body{font:15px sans-serif;margin:0} nav{position:fixed;left:0;top:0;width:220px;padding:12px}
main{margin-left:240px;padding:16px} nav a,nav button{display:block;margin:4px 0}</style>${body}`;

const LOGIN = page("Log in", `<main><h1>Log in to your account</h1><form onsubmit="return false"><input id="username" aria-label="Username">
<input id="password" type="password" aria-label="Password"><button type="submit">Log in</button></form>
${knob("FAKE_SSO_HIDDEN") ? "" : `<ul><li><a href="/api/gateway/social/login/${SLUG}/">Keycloak zuno</a></li></ul>`}</main>`);

const KEYCLOAK = page("Sign in to zuno", `<main><form method="get" action="/api/gateway/social/complete/${SLUG}/"><input id="username" name="u">
<input id="password" name="p" type="password"><button id="kc-login">Sign In</button></form></main>`);

function shell(path, user, main) {
  const open = path.startsWith("/execution/");
  return page("Ansible Automation Platform", `<nav aria-label="Global"><a href="/overview">Overview</a>
<button id="grp" aria-expanded="${open}" onclick="const g=document.getElementById('grp-items');g.hidden=!g.hidden">Automation Execution</button>
<div id="grp-items"${open ? "" : " hidden"}><a href="/execution/jobs">Jobs</a><a href="/execution/templates">Templates</a><a href="/execution/projects">Projects</a></div></nav>
<header style="position:fixed;right:16px;top:8px">${user}</header><main>${main}</main>`);
}

const table = (rows) => `<table><tbody>${rows.join("")}</tbody></table>`;

function view(path, query, user) {
  if (path === "/overview") {
    return `<h1>Welcome to Ansible Automation Platform</h1><p>Jobs, templates and projects you can see.</p>`
      + (knob("FAKE_DIALOG") ? `<div role="dialog" aria-modal="true">Welcome to the new platform. Take the tour?</div>` : "")
      + (knob("FAKE_UI_WRITE") ? `<script>fetch("/api/gateway/v1/user_preferences/", {method: "POST", body: "{}"})</script>` : "");
  }
  if (path === "/execution/templates") {
    return `<h1>Templates</h1>` + table(TEMPLATES.map((t) => `<tr><td><a href="/execution/templates/job-template/1/details">${t}</a></td>`
      + `<td><button aria-label="Launch template" disabled>Launch</button></td></tr>`));
  }
  if (path === "/execution/jobs") {
    const name = query.get("name") || "";
    const rows = JOBS.filter((j) => !name || j.name === name).sort((a, b) => b.id - a.id)
      .map((j) => `<tr><td><a href="/execution/jobs/playbook/${j.id}/output">${j.id} - ${j.name}</a></td><td>Successful</td><td>${j.by}</td></tr>`);
    return `<h1>Jobs</h1><input id="filter-input" aria-label="filter"><button aria-label="apply filter"
onclick="location.href='/execution/jobs?name='+encodeURIComponent(document.getElementById('filter-input').value)">Go</button>` + table(rows);
  }
  const job = path.match(/^\/execution\/jobs\/playbook\/(\d+)\/(output|details)$/);
  if (job) {
    const found = JOBS.find((j) => j.id === Number(job[1]));
    if (!found) return null;
    const tabs = `<div role="tablist"><a role="tab" href="/execution/jobs/playbook/${found.id}/output" aria-selected="${job[2] === "output"}">Output</a>`
      + `<a role="tab" href="/execution/jobs/playbook/${found.id}/details" aria-selected="${job[2] === "details"}">Details</a></div>`;
    if (job[2] === "output") {
      outputs += 1;
      return `<h1>${found.id} - ${found.name}</h1>${tabs}<pre>TASK [day0 check] ok: [ip-10-1-2-3.ec2.internal]</pre>`;
    }
    return `<h1>${found.id} - ${found.name}</h1>${tabs}<dl><dt>Status</dt><dd>Successful</dd><dt>Job template</dt><dd>${found.name}</dd>`
      + `<dt>Launched by</dt><dd>${found.by}</dd><dt>Project</dt><dd>zuno-demo</dd><dt>Revision</dt><dd>0123abcd</dd></dl>`;
  }
  if (path === "/execution/projects") return `<h1>Projects</h1>` + table([`<tr><td><a href="/execution/projects/7/details">zuno-demo</a></td><td>Successful</td></tr>`]);
  if (path === "/execution/projects/7/details") {
    return `<h1>zuno-demo</h1><dl><dt>Source control URL</dt><dd>https://github.com/startxfr/zuno-demo.git</dd>`
      + `<dt>Source control branch</dt><dd>devel</dd><dt>Revision</dt><dd>0123abcd</dd></dl><button aria-label="Sync project" disabled>Sync</button>`;
  }
  return null;
}

function json(res, status, body) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

http.createServer((req, res) => {
  const url = new URL(req.url, "http://fake");
  const user = (/(?:^|; )sid=([a-z0-9-]+)/.exec(req.headers.cookie || "") || [])[1] || "";
  if (url.pathname === "/fake/count") return json(res, 200, { writes, outputs });
  if (req.method !== "GET") { writes += 1; return json(res, 403, { detail: "the stand-in refuses every write" }); }
  if (url.pathname === "/api/gateway/v1/ui_auth/") return json(res, 200, { show_login_form: true, ssos: [{ name: "Keycloak zuno", login_url: `/api/gateway/social/login/${SLUG}/` }] });
  if (url.pathname === `/api/gateway/social/login/${SLUG}/`) { res.writeHead(302, { location: "/fake-keycloak/auth" }); return res.end(); }
  if (url.pathname === "/fake-keycloak/auth") { res.writeHead(200, { "content-type": "text/html" }); return res.end(KEYCLOAK); }
  if (url.pathname === `/api/gateway/social/complete/${SLUG}/`) {
    const headers = { location: "/" };
    if (!knob("FAKE_LOGIN_LOOP")) headers["set-cookie"] = `sid=${url.searchParams.get("u")}; Path=/`;
    res.writeHead(302, headers);
    return res.end();
  }
  if (url.pathname.startsWith("/api/controller/v2/")) {
    if (!user) return json(res, 401, { detail: "Authentication credentials were not provided." });
    const q = url.searchParams;
    if (url.pathname === "/api/controller/v2/jobs/") {
      const list = JOBS.filter((j) => (!q.get("name") || j.name === q.get("name")) && (!q.get("created_by__username") || j.by === q.get("created_by__username")))
        .sort((a, b) => b.id - a.id);
      return json(res, 200, { count: list.length, results: list.slice(0, Number(q.get("page_size") || 25)).map((j) => ({ id: j.id, type: "job", name: j.name })) });
    }
    if (url.pathname === "/api/controller/v2/unified_jobs/") return json(res, 200, { count: 0, results: [] });
    if (url.pathname === "/api/controller/v2/projects/") return json(res, 200, { count: 1, results: [{ id: 7, name: "zuno-demo" }] });
    return json(res, 404, { detail: "Not found" });
  }
  if (url.pathname === "/") {
    if (user) { res.writeHead(302, { location: "/overview" }); return res.end(); }
    res.writeHead(200, { "content-type": "text/html" });
    return res.end(LOGIN);
  }
  if (!user) { res.writeHead(302, { location: "/" }); return res.end(); }
  const main = view(url.pathname, url.searchParams, user);
  if (main === null) { res.writeHead(404, { "content-type": "text/html" }); return res.end(page("Not found", "<main>Not found</main>")); }
  res.writeHead(200, { "content-type": "text/html" });
  res.end(shell(url.pathname, user, main));
}).listen(port, "127.0.0.1", () => console.log(`fake aap on 127.0.0.1:${port}`));
