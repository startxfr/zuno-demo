// WP-289: a stand-in for the OpenShift sign-in, the OpenShift AI dashboard's project, pipeline and training pages, and
// MLflow's UI under /mlflow, for the offline test of walkthroughs/lora-pipeline-mlflow-kueue.mjs
// (tests/walkthroughs-offline.sh). Its own file: tests/fake-rhoai.mjs (model-catalog-registry) stays as it is. Shaped
// like the walkthrough's GUESSES, not like RHOAI: it proves the walkthrough's own logic, not the real selectors.
// It serves the provider chooser and Keycloak (as seen live), the menu as the scout of 2026-11-16 dumped it (Home,
// Projects /projects, a collapsed "Develop & train" group with a sub-group "Pipelines", Experiments
// /develop-train/mlflow/experiments and Jobs /develop-train/training-jobs), the projects list, the project Zuno MLOps
// with its Pipelines tab (?section=pipelines-projects, the three pipelines by display name), the graph of the tekos
// version (drawn after a spinner, its steps as SVG text), the Jobs page that shows lora-comage-4c28m only at
// /develop-train/training-jobs/zuno-mlops, and the dashboard's Experiments page as the rescout of 2026-11-16 saw it:
// "No experiments" for Zuno MLOps and a "Launch MLflow" link to MLflow's own UI, which lists mlops-comage (its searches
// are POSTs). FAKE_DASHBOARD_FRAME=1 the Experiments page embeds MLflow in a frame instead; FAKE_MLFLOW_EMPTY=1 MLflow's
// own UI lists only "Default"; FAKE_NO_VERSION_NAME=1 the graph page names no version.
// Knobs: FAKE_NO_TRAINING=1 there is no Jobs page; FAKE_VERSION=v0-4-0 the graph is of v0-4-0-tekos;
// FAKE_MLFLOW_WORKSPACE=1 MLflow lists the experiment only once the workspace zuno-mlops is chosen; FAKE_WRITE=1 the
// experiment page sets a tag on a run (a write); FAKE_DIALOG=1 a welcome dialog covers the dashboard.
// /fake/count says {writes}: the non-GET requests that are not MLflow searches. No cluster.
import http from "node:http";

const port = Number(process.env.FAKE_PORT || 8087);
const knob = (name) => process.env[name] === "1";
let writes = 0;

const CHOOSER = `<!doctype html><title>Log in</title><h1>Log in with...</h1>
<a class="idp" title="Log in with startx-htpasswd_auth" href="/htpasswd">startx-htpasswd_auth</a><br>
<a class="idp" title="Log in with openshift" href="/kc">openshift</a>`;
const LOGIN = `<!doctype html><title>Sign in</title><form method="get" action="/cb"><input id="username" name="u">
<input id="password" name="p" type="password"><button id="kc-login">Sign In</button></form>`;
const STYLE = `<style>body{font:16px sans-serif;margin:0;display:flex} #page-sidebar{width:220px;min-height:100vh;background:#212427;color:#fff;padding:12px}
#page-sidebar [hidden]{display:none} #page-sidebar a,#page-sidebar button{color:#fff;display:block;margin:6px 0;background:none;border:0;font:inherit;cursor:pointer;text-align:left}
main{padding:24px;flex:1} .modal{position:fixed;inset:0;background:rgba(0,0,0,.4)} .modal>div{background:#fff;margin:120px auto;width:400px;padding:24px}</style>`;
const toggle = (id) => `onclick="this.setAttribute('aria-expanded','true');document.getElementById('${id}').hidden=false"`;

function shell(body, { dialog = false } = {}) {
  return `<!doctype html><title>Red Hat OpenShift AI (fake)</title>${STYLE}
<nav id="page-sidebar" aria-label="Global"><p>ai-dev-01</p><a href="/">Home</a><a href="/projects">Projects</a>
<button aria-expanded="false" ${toggle("hub")}>AI hub</button><div id="hub" hidden><a href="/ai-hub/models">Models</a></div>
<button aria-expanded="false" ${toggle("dev")}>Develop &amp; train</button><div id="dev" hidden>
<button aria-expanded="false" ${toggle("pipes")}>Pipelines</button><div id="pipes" hidden><a href="/develop-train/pipelines/definitions">Pipeline definitions</a><a href="/develop-train/pipelines/runs">Runs</a></div>
<a href="/develop-train/mlflow/experiments">Experiments</a>
${knob("FAKE_NO_TRAINING") ? "" : `<a href="/develop-train/training-jobs">Jobs</a>`}</div></nav>
<main>${body}</main>
${dialog ? `<div class="modal" role="dialog" aria-modal="true"><div><h2>Welcome to Red Hat OpenShift AI</h2></div></div>` : ""}`;
}

const PIPELINES = ["MLOps: dataset-to-model LoRA/PEFT pipeline", "MLOps: dataset-to-model LoRA/PEFT pipeline (comage)", "MLOps: dataset-to-model LoRA/PEFT pipeline (tekos)"];
const VERSION = { "v0-4-0": "v0-4-0-tekos", comage: "v0-3-0-comage" }[process.env.FAKE_VERSION] || "v0-3-0-tekos";

function view(path, query) {
  if (path === "/") return `<h1>Welcome, ai-dev-01</h1><p>Your projects</p>`;
  if (path === "/projects") return `<h1>Projects</h1><table><tr><td><a href="/projects/zuno-ai-run">Zuno AI Run</a></td></tr><tr><td><a href="/projects/zuno-mlops">Zuno MLOps</a></td></tr></table>`;
  if (path === "/projects/zuno-mlops") {
    const onPipelines = query.get("section") === "pipelines-projects";
    const tabs = ["Overview", "Workbenches", "Pipelines"].map((t) => `<button role="tab" aria-selected="${(t === "Pipelines") === onPipelines}"
onclick="location.href='/projects/zuno-mlops${t === "Pipelines" ? "?section=pipelines-projects" : ""}'">${t}</button>`).join("");
    return `<h1>Zuno MLOps</h1><div role="tablist">${tabs}</div>` + (onPipelines
      ? `<table>${PIPELINES.map((p, i) => `<tr><td><a href="/pipelines/zuno-mlops/p${i}/view">${p}</a></td></tr>`).join("")}</table>` : `<p>Overview of the project.</p>`);
  }
  if (path === "/pipelines/zuno-mlops/p2/view") {
    const graph = `<h1>${PIPELINES[2]}</h1>${knob("FAKE_NO_VERSION_NAME") ? "" : `<p>Version: <span>${VERSION}</span></p>`}<button>Create run</button>
<p>LoRA/PEFT adapter pipeline for tekos - prepare-dataset -> train-lora -> evaluate -> push-registry (ADR-0301/ADR-0302)</p>
<svg width="900" height="160">${["component", "component-2", "component-3", "component-4"].map((s, i) => `<rect x="${20 + i * 220}" y="40" width="180" height="40" fill="#ddd"/><text x="${30 + i * 220}" y="65">${s}</text>`).join("")}</svg>`;
    // Drawn after a spinner, as the rescout of 2026-11-16 caught the page ("Loading").
    return `<div id="graph"><div role="progressbar">Loading</div></div><script>setTimeout(() => { document.getElementById("graph").innerHTML = ${JSON.stringify(graph)}; }, 2500);</script>`;
  }
  if (path === "/develop-train/training-jobs" && !knob("FAKE_NO_TRAINING")) return `<h1>Jobs</h1><p>Select a project to see its training jobs.</p>`;
  if (path === "/develop-train/training-jobs/zuno-mlops" && !knob("FAKE_NO_TRAINING")) return `<h1>Jobs</h1><p>Project: Zuno MLOps</p><table><tr><td>lora-comage-4c28m</td><td>Complete</td><td>2026-09-08</td></tr></table>`;
  if (path === "/develop-train/mlflow/experiments") {
    if (knob("FAKE_DASHBOARD_FRAME")) return `<h1>Experiments</h1><iframe src="/mlflow/" title="MLflow" style="width:100%;height:560px;border:1px solid #ccc"></iframe>`;
    return `<h1>Experiments</h1><p>Project <button>Zuno MLOps</button> <a href="/projects/zuno-mlops">Go to Zuno MLOps</a> <a href="/mlflow/" target="_blank">Launch MLflow</a></p>
<input placeholder="Search"><table><tr><th>Name</th></tr><tr><td>No experiments</td></tr></table>`;
  }
  return null;
}

// MLflow 3.15's own UI as the rescout of 2026-11-16 saw it: a workspace picker, a toggle GenAI | Model training on
// GenAI, a left menu Home | Experiments; the GenAI Home says "Create your first experiment". The training view's
// Experiments page lists the experiments of the workspace chosen (zuno-mlops, or "default" with FAKE_MLFLOW_WORKSPACE),
// in either view; with FAKE_MLFLOW_TRAINING_ONLY=1 only in the training view (a radio: the take's declared switch);
// FAKE_TOGGLE_WRITE=1 that switch POSTs a preference.
const MLFLOW_HOME = `<!doctype html><title>MLflow</title><body style="font:16px sans-serif"><header>MLflow
<button id="ws">Workspace: ${knob("FAKE_MLFLOW_WORKSPACE") ? "default" : "zuno-mlops"}</button>
<div role="listbox" id="wslist" hidden><div role="option" id="pick">zuno-mlops</div></div>
<div role="radiogroup"><button role="radio" aria-checked="true" id="genai">GenAI</button><button role="radio" aria-checked="false" id="training">Model training</button></div></header>
<nav><a href="#home" id="home">Home</a> <a href="#experiments" id="exp">Experiments</a> <a href="#prompts">Prompts</a></nav>
<main id="view"><h2>Home</h2><p>Recent Experiments: Create your first experiment</p><button>Create experiment</button></main>
<script>
const $ = (id) => document.getElementById(id);
let mode = "genai", ws = ${JSON.stringify(knob("FAKE_MLFLOW_WORKSPACE") ? "default" : "zuno-mlops")}, page = "home";
function render() {
  if (page !== "experiments") return;
  const rows = (mode === "training" || !${knob("FAKE_MLFLOW_TRAINING_ONLY")}) && ws === "zuno-mlops"
    ? '<tr><td><a href="/mlflow/experiments/0">Default</a></td></tr>' + (${knob("FAKE_MLFLOW_EMPTY")} ? "" : '<tr><td><a href="/mlflow/experiments/7">mlops-comage</a></td></tr>')
    : "<tr><td>No experiments</td></tr>";
  $("view").innerHTML = "<h2>Experiments</h2><table>" + rows + "</table>";
}
$("ws").onclick = () => { $("wslist").hidden = false; };
$("pick").onclick = () => { ws = "zuno-mlops"; $("ws").textContent = "Workspace: zuno-mlops"; $("wslist").hidden = true; render(); };
$("training").onclick = () => {
  ${knob("FAKE_TOGGLE_WRITE") ? `fetch("/mlflow/ajax-api/2.0/mlflow/users/preferences", { method: "POST", body: "{}" });` : ""}
  mode = "training"; $("training").setAttribute("aria-checked", "true"); $("genai").setAttribute("aria-checked", "false"); render();
};
$("exp").onclick = (e) => { e.preventDefault(); page = "experiments"; render(); };
fetch("/mlflow/ajax-api/2.0/mlflow/experiments/search", { method: "POST", body: "{}" });
</script>`;
const MLFLOW_EXPERIMENT = `<!doctype html><title>mlops-comage - MLflow</title><body style="font:16px sans-serif"><main><h2>mlops-comage</h2>
<table><tr><th>Run Name</th><th>base_model</th><th>lora_r</th><th>train_loss</th></tr><tr><td>wp126-20260908-195101</td><td>qwen35-9b</td><td>16</td><td>1.23</td></tr></table></main>
<script>fetch("/mlflow/ajax-api/2.0/mlflow/runs/search", { method: "POST", body: "{}" });
${knob("FAKE_WRITE") ? `fetch("/mlflow/ajax-api/2.0/mlflow/runs/set-tag", { method: "POST", body: "{}" });` : ""}</script>`;

http.createServer((req, res) => {
  const u = new URL(req.url, "http://fake");
  const signed = /(?:^|; )sid=ai-dev-01/.test(req.headers.cookie || "");
  const send = (body, status = 200) => { res.writeHead(status, { "content-type": "text/html" }); res.end(body); };
  if (u.pathname === "/fake/count") { res.writeHead(200, { "content-type": "application/json" }); return res.end(JSON.stringify({ writes })); }
  if (req.method !== "GET") {
    if (!/\/search$/.test(u.pathname)) writes += 1;
    res.writeHead(200, { "content-type": "application/json" });
    return res.end("{}");
  }
  if (u.pathname === "/kc") return send(LOGIN);
  if (u.pathname === "/cb") { res.writeHead(302, { location: "/", "set-cookie": `sid=${u.searchParams.get("u")}; Path=/` }); return res.end(); }
  if (!signed) return send(CHOOSER);
  if (u.pathname === "/mlflow" || u.pathname === "/mlflow/") return send(MLFLOW_HOME);
  if (u.pathname === "/mlflow/experiments/7") return send(MLFLOW_EXPERIMENT);
  const body = view(u.pathname, u.searchParams);
  if (body === null) return send(shell("<h1>Not found</h1>"), 404);
  return send(shell(body, { dialog: knob("FAKE_DIALOG") && u.pathname === "/" }));
}).listen(port, "127.0.0.1");
