// WP-289 / ADR-0618: the walkthrough of "RHOAI pipelines - from a dataset to a fine-tuned LoRA adapter", 5-minute
// version, for evaluations/browser/record.mjs. Option A of 2026-11-16 (zuno-demo-reorg).
//
// The rows of docs/demo/scenarios/rhoai/lora-pipeline-mlflow-kueue.md, as ai-dev-01: the Keycloak form (login), the
// OpenShift AI dashboard (dashboard), the project Zuno MLOps and the graph of the pipeline "MLOps: dataset-to-model
// LoRA/PEFT pipeline (tekos)", its latest tekos version (pipeline, row 0:45), the Jobs page with the TrainJob
// lora-comage-4c28m (trainjob, row 1:45), then end. Row 2:45 (the MLflow experiment mlops-comage) is off on this cluster:
// see MLFLOW_ROW below. Rows 0:00 and 4:30 are words; row 3:45 is the evidence page of WP-133, not filmed.
//
// It signs in through the OpenShift sign-in (the provider chooser `openshift`, then Keycloak), the flow the
// model-catalog-registry take proved on 2026-11-16 (its code is copied here: a walkthrough's hash covers only the
// shared helpers and itself). Read only: it starts no run, creates, edits or deletes nothing, sends no prompt; owned()
// is empty. A request that would create or change something in the pipeline server or in MLflow (`sends`) is refused
// in a scout and fails a take. When a dialog covers the dashboard, or OpenShift asks to authorize access, the take
// stops and says so.
//
// The first scout (2026-11-16 at 5477cf1a, demo333) signed in and dumped the menu, with addresses: Projects /projects;
// under "Develop & train", Pipeline definitions /develop-train/pipelines/definitions, Experiments (MLflow)
// /develop-train/mlflow/experiments and Jobs (the training jobs) /develop-train/training-jobs. Its screens failed: the
// Projects link was not found in time (the menu took 48 s to show under load), "Training jobs" is labelled "Jobs", and
// /mlflow/ alone timed out. Now each page is reached by its menu link's address (the group "Develop & train" opened
// first), or by the address itself when the link is not on screen; waits are longer; MLflow is the dashboard's own
// Experiments page, its text looked for in the page and in any frame it embeds. Still NOT seen: the project's
// Pipelines tab, the graph's step names as text, the Jobs page's project choice, MLflow's workspace choice.
import { click, describe, firstVisible, read, waitUntil, wordsOnScreen } from "./_helpers.mjs";

export const persona = "ai-dev-01";
export const page = "docs/demo/scenarios/rhoai/lora-pipeline-mlflow-kueue.md";
export const viewport = { width: 1280, height: 800 };
// Row 2:45 (MLflow) is off: demo333's rescouts of 2026-11-16 (19:54 and 20:41) found no experiment in MLflow's
// workspace zuno-mlops, in its GenAI view or its Model training view, and the dashboard lists none for Zuno MLOps. The
// GIF ends at the training job. The MLflow screen stays in this file, tested offline (RECORD_MLFLOW_ROW=1, which only the
// offline test sets; record.sh never does), for when an experiment is logged on this cluster.
const MLFLOW_ROW = process.env.RECORD_MLFLOW_ROW === "1";
export const markers = MLFLOW_ROW ? ["login", "dashboard", "pipeline", "trainjob", "mlflow", "end"] : ["login", "dashboard", "pipeline", "trainjob", "end"];
// The provider chooser and the sign-in (up to dashboard) are never shown as motion.
export const motion_from = "dashboard";
// MLflow's view toggle "Model training" is a radio, which the shared click() refuses unless it is declared here. Declared
// by zuno-demo-reorg's decision of 2026-11-16 (option A), on one condition: the switch sends no write. While it is
// clicked, every request that is not a GET, HEAD or OPTIONS (MLflow's searches, POSTs that read, aside) is refused
// before it leaves the browser and fails the take or the scout: then the decision is option B (no MLflow row).
const TRAINING_VIEW_DECLARED = true;
const TRAINING_CHANGE = "switches MLflow's own UI from its GenAI view to its Model training view (a view of the page, nothing saved on the server)";
export const changes = MLFLOW_ROW && TRAINING_VIEW_DECLARED ? [TRAINING_CHANGE] : [];
export const url = (domain) => `https://rh-ai.${domain}`;
// The requests that would start or change something: a pipeline run, an experiment or a version created in the
// pipeline server (its API is /apis/v2beta1); a run, an experiment, a tag or a model changed in MLflow (its searches
// are POSTs too, and are reads: not here). A scout refuses these when they are not a GET; a take fails if one was sent.
export const sends = /\/apis\/v2beta1\/(runs|recurringruns|experiments|pipelines|pipelines\/[^/]+\/versions)\/?(\?|$)|(ajax-)?api\/2\.0\/mlflow\/(runs|experiments|registered-models|model-versions)\/(create|update|delete|restore|set-[a-z-]+|delete-[a-z-]+|log-[a-z-]+|rename)/;   // guess

const PROVIDER = "openshift";   // the page: the OpenShift sign-in, Keycloak behind it
const PROVIDER_LINK = [`a[title='Log in with ${PROVIDER}']`, `a.idp:text-is('${PROVIDER}')`, `a:text-is('${PROVIDER}')`];   // seen live, 2026-11-16
const APPROVE = /\/oauth\/authorize\/approve|Authorize Access|Allow selected permissions/i;                               // guess: an OAuth grant page
const NAV = ["#page-sidebar", "nav[aria-label*='Global' i]", "nav"];                                                       // seen, 2026-11-16 (catalog scout)
const DIALOG = "[role='dialog'][aria-modal='true'], .pf-v5-c-backdrop, .pf-v6-c-backdrop";                                  // guess: a welcome or a tour
const DWELL_MS = 2000;   // a presenter's pause on each screen, so that every motion moment has frames to cut

const PROJECT = "Zuno MLOps";                                         // the display name of zuno-mlops (the page)
const PIPELINE = "MLOps: dataset-to-model LoRA/PEFT pipeline (tekos)";   // gitops/charts/mlops: displayName + " (tekos)"
// Any tekos version: v0-3-0 and v0-4-0 have the same steps (git: 9fd84fbe, decc2c0e). demo333 listed only v0-3-0 at
// 01:25 on 2026-11-16; the rescout of 18:50 opened v0-4-0-tekos by default. The version shown is reported.
const VERSION = /^v\d+-\d+-\d+-tekos$/;
const STEPS = [/prepare-dataset/, /train-lora/, /\bevaluate\b/, /push-registry/];
const TRAINJOB = "lora-comage-4c28m";
const EXPERIMENT = "mlops-comage";
const WORKSPACE = "zuno-mlops";
const RUN_NAME = /wp126-\d{8}-\d{6}/;
// The menu, by the addresses the scout of 2026-11-16 dumped.
const HREF = { projects: "/projects", jobs: "/develop-train/training-jobs", mlflow: "/develop-train/mlflow/experiments" };
const NAV_DEVELOP = ["nav button:has-text('Develop & train')"];                                                            // seen collapsed, 2026-11-16
const PROJECT_LINK = [`main a:text-is('${PROJECT}')`, `main a:has-text('${PROJECT}')`];                                   // guess
const PROJECT_PAGE = "/projects/zuno-mlops";                                                                                // guess: the dashboard's route
const PIPELINES_TAB = ["main [role='tab']:has-text('Pipelines')", "main button:text-is('Pipelines')", "main a:text-is('Pipelines')"];   // guess
const PIPELINE_LINK = [`main a:text-is('${PIPELINE}')`, `main a:has-text('${PIPELINE}')`, `main button:has-text('${PIPELINE}')`];   // guess
const PROJECT_PICKER = ["main button:has-text('Project')", "[data-testid*='project-selector' i]", "main [aria-label*='project' i]"];   // guess
const WORKSPACE_PICKER = ["button:has-text('Workspace')", "[aria-label*='workspace' i]", "[data-testid*='workspace' i]"];       // guess (MLflow)
// Every wait of this walkthrough, capped by RECORD_WAIT_CAP_MS when it is set: the offline test only (its stand-in
// answers at once, and its failing cases would otherwise sit through every long wait). record.sh never sets it.
const WAIT_CAP_MS = Number(process.env.RECORD_WAIT_CAP_MS) || 0;
function wait(ms) {
  return WAIT_CAP_MS ? Math.min(ms, WAIT_CAP_MS) : ms;
}
const SLOW_MS = wait(90000);   // the menu took 48 s to show under load (scout of 2026-11-16)
// A page still loading: the rescout of 2026-11-16 (dfdf7322) checked the graph page while it showed "Loading" and a spinner.
const LOADING = "main [role='progressbar'], main .pf-v6-c-spinner, main .pf-v5-c-spinner";
const VERSIONS = /\bv\d+-\d+-\d+-[a-z0-9-]+\b/g;   // version names as the chart makes them (v0-3-0-tekos)
const NO_EXPERIMENTS = /No experiments/i;                                                                                  // seen, 2026-11-16 rescout
const LAUNCH_MLFLOW = ["main a:has-text('Launch MLflow')", "a:has-text('Launch MLflow')"];                                // seen, 2026-11-16 rescout
// MLflow 3.15's own UI (the rescout of 18:50): a toggle GenAI | Model training, GenAI selected, whose Home said "Create
// your first experiment"; a left menu Home, Experiments, Prompts. Looked for in MLflow's own frames only (the page,
// once Launch MLflow is followed, or a frame the dashboard embeds), never in the dashboard's menu.
// Seen in the rescout of 2026-11-16 19:54: a <div role="button" aria-pressed="false">Model training</div> beside "GenAI".
const TRAINING_VIEW = ["[role='button'][aria-pressed]:has-text('Model training')", "[role='radio']:has-text('Model training')", "button:has-text('Model training')"];
const EXPERIMENTS_LINK = ["nav a:has-text('Experiments')", "a[href*='experiments']:has-text('Experiments')", "a:text-is('Experiments')"];   // guess

// The requests sent so far that `sends` names and that are not a GET: a take fails if there is one.
function writesSeen(page) {
  const seen = [];
  page.on("request", (r) => { if (r.method() !== "GET" && sends.test(r.url())) seen.push(`${r.method()} ${new URL(r.url()).pathname}`); });
  return () => [...new Set(seen)];
}

async function noDialog(page, where) {
  if (await page.locator(DIALOG).first().isVisible().catch(() => false)) {
    throw new Error(`a dialog covers the ${where}: a take dismisses nothing that is saved in the user's settings; see the scout`);
  }
}

async function visibleText(page, text, what, timeoutMs = SLOW_MS) {
  await waitUntil(page, { what, timeoutMs, done: async () => (await page.getByText(text).first().isVisible().catch(() => false)) || undefined });
  await page.waitForLoadState("networkidle", { timeout: wait(30000) }).catch(() => {});
}

// Click the first of these on screen, waiting for one up to `timeoutMs`; says which matched.
async function clickOne(page, selectors, what, timeoutMs = wait(60000)) {
  const found = await waitUntil(page, { what, timeoutMs, done: async () => (await firstVisible(page, selectors)) || undefined })
    .catch(() => { throw new Error(`${what} was not found (${selectors.join(" | ")})`); });
  await click(found, { changes });
  await page.waitForLoadState("networkidle", { timeout: wait(30000) }).catch(() => {});
  return found.matched;
}

// Every collapsed group of the left menu opened (navigation only), then its links: [{text, href}], for the scout.
async function menuLinks(page) {
  for (let round = 0; round < 3; round += 1) {
    const closed = page.locator("nav button[aria-expanded='false']");
    const count = await closed.count();
    if (!count) break;
    for (let i = count - 1; i >= 0; i -= 1) await click(closed.nth(i), { changes }).catch(() => {});
    await page.waitForTimeout(500);
  }
  return read(page, () => [...document.querySelectorAll("nav a[href]")].map((a) => ({ text: (a.innerText || "").trim().slice(0, 60), href: new URL(a.href).pathname })));
}

async function settle(page) {
  await page.waitForLoadState("networkidle", { timeout: wait(60000) }).catch(() => {});
  await page.waitForTimeout(800);
}

// A page of the menu, by its address: its link (the group "Develop & train" opened first when the link is hidden),
// or the address itself when the menu shows no such link. Navigation only. Says which way it went.
async function goMenu(page, base, href) {
  await waitUntil(page, { what: "the left menu", timeoutMs: SLOW_MS, done: async () => (await firstVisible(page, NAV)) || undefined });
  const selector = [`nav a[href='${href}']`];
  let link = await firstVisible(page, selector);
  if (!link) {
    const group = await firstVisible(page, NAV_DEVELOP);
    if (group && (await group.getAttribute("aria-expanded").catch(() => null)) !== "true") { await click(group, { changes }); await page.waitForTimeout(800); }
    link = await firstVisible(page, selector);
  }
  if (link) { await click(link, { changes }); await settle(page); return `menu ${link.matched}`; }
  await page.goto(`${base}${href}`);
  await settle(page);
  return `address ${href}`;
}

// The first frame (the page, or a frame it embeds) where this text is drawn, or null.
async function frameWith(page, text, exact = false) {
  for (const frame of page.frames()) if (await frame.getByText(text, { exact }).first().isVisible().catch(() => false)) return frame;
  return null;
}
async function waitFrameWith(page, text, what, timeoutMs = SLOW_MS, exact = false) {
  return waitUntil(page, { what, timeoutMs, done: async () => (await frameWith(page, text, exact)) || undefined });
}
// The first of these selectors on screen in any frame (or in MLflow's own frames only, `mlflowOnly`): the locator, with
// the selector that matched.
const isMlflow = (frame) => { try { return /^\/mlflow(\/|$)/.test(new URL(frame.url()).pathname); } catch { return false; } };
async function anyFrame(page, selectors, mlflowOnly = false) {
  for (const frame of page.frames().filter((f) => !mlflowOnly || isMlflow(f))) {
    for (const selector of selectors) {
      const found = frame.locator(selector).first();
      if (await found.isVisible().catch(() => false)) return Object.assign(found, { matched: selector });
    }
  }
  return null;
}

// Switch MLflow's own UI to its Model training view (the declared change), watching what the switch sends for 3 s: every
// request is noted by method and path; one that is not a GET, HEAD or OPTIONS, nor one of MLflow's searches, is
// refused. Returns {sent, refused}.
async function switchView(page, toggle) {
  const sent = [];
  const refused = [];
  const watch = (route) => {
    const r = route.request();
    const path = new URL(r.url()).pathname;
    sent.push(`${r.method()} ${path}`);
    if (["GET", "HEAD", "OPTIONS"].includes(r.method()) || /\/search$/.test(path)) return route.fallback();
    refused.push(`${r.method()} ${path}`);
    return route.abort();
  };
  await page.route("**/*", watch);
  try {
    await click(toggle, { change: TRAINING_CHANGE, changes });
    await page.waitForTimeout(3000);
  } finally {
    await page.unroute("**/*", watch);
  }
  await settle(page);
  return { sent: [...new Set(sent)].slice(0, 30), refused: [...new Set(refused)] };
}

// The screens of the rows, in order: each returns what it found, for the log (a take) or the step (a scout).
const SCREENS = [
  { name: "pipeline", show: async ({ page, base }) => {
    const how = [await goMenu(page, base, HREF.projects)];
    const project = await waitUntil(page, { what: `the project ${PROJECT}`, timeoutMs: wait(60000), done: async () => (await firstVisible(page, PROJECT_LINK)) || undefined }).catch(() => null);
    if (project) { await click(project, { changes }); how.push(project.matched); } else { await page.goto(`${base}${PROJECT_PAGE}`); how.push(`address ${PROJECT_PAGE}`); }
    await settle(page);
    const tab = await waitUntil(page, { what: "the project's Pipelines tab", timeoutMs: wait(60000), done: async () => (await firstVisible(page, PIPELINES_TAB)) || undefined }).catch(() => null);
    if (!tab) { await page.goto(`${base}${PROJECT_PAGE}?section=pipelines-projects`); how.push("address ?section=pipelines-projects"); await settle(page); }
    else if ((await tab.getAttribute("aria-selected").catch(() => null)) !== "true") { await click(tab, { changes }); how.push(tab.matched); await settle(page); }
    how.push(await clickOne(page, PIPELINE_LINK, `the pipeline ${PIPELINE}`, SLOW_MS));
    // The graph, drawn: its four steps on screen and no spinner left, twice in a row 1.5 s apart.
    let ready = 0;
    await waitUntil(page, { what: "the pipeline's graph", timeoutMs: SLOW_MS, everyMs: 1500, done: async () => {
      const seen = await wordsOnScreen(page, STEPS);
      const loading = await page.locator(LOADING).first().isVisible().catch(() => false);
      ready = Object.values(seen).every(Boolean) && !loading ? ready + 1 : 0;
      return ready >= 2 || undefined;
    } }).catch(() => { throw new Error(`the graph's steps (${STEPS.map((s) => s.source).join(", ")}) are not all on screen with no spinner left`); });
    await noDialog(page, "pipeline's graph");
    // The version names drawn on the page: another version than the page's fails the take; none drawn is reported.
    const shownVersions = await read(page, (source) => [...new Set((document.querySelector("main") || document.body).innerText.match(new RegExp(source, "g")) || [])], VERSIONS.source).catch(() => []);
    if (shownVersions.length && !shownVersions.some((v) => VERSION.test(v))) {
      throw new Error(`the graph on screen is of ${shownVersions.join(", ")}, not a tekos version: the page's 0:45 row names the tekos pipeline`);
    }
    return { how, url: new URL(page.url()).pathname, versions_shown: shownVersions,
             merge_export_on_screen: await page.getByText(/merge-export/).first().isVisible().catch(() => false) };
  } },
  { name: "trainjob", show: async ({ page, base }) => {
    const how = [await goMenu(page, base, HREF.jobs)];
    let shown = await waitFrameWith(page, TRAINJOB, `the TrainJob ${TRAINJOB}`, wait(30000)).catch(() => null);
    if (!shown && !new URL(page.url()).pathname.includes("zuno-mlops")) {
      // The dashboard's project pages carry the namespace last (guess): the Jobs page of zuno-mlops.
      await page.goto(`${base}${HREF.jobs}/zuno-mlops`);
      await settle(page);
      how.push(`address ${HREF.jobs}/zuno-mlops`);
      shown = await waitFrameWith(page, TRAINJOB, `the TrainJob ${TRAINJOB}`, wait(30000)).catch(() => null);
    }
    if (!shown) {
      const picker = await firstVisible(page, PROJECT_PICKER);
      if (picker) {
        await click(picker, { changes });
        how.push(picker.matched);
        await clickOne(page, [`[role='menu'] :text-is('${PROJECT}')`, `[role='listbox'] :text-is('${PROJECT}')`, `[role='option']:has-text('${PROJECT}')`], `the project ${PROJECT} in the selector`, wait(15000));
        shown = await waitFrameWith(page, TRAINJOB, `the TrainJob ${TRAINJOB}`, wait(30000)).catch(() => null);
      }
    }
    if (!shown) {
      throw new Error(`the Jobs page (${HREF.jobs}) does not show ${TRAINJOB}: the row's other way is \`oc get trainjob\`, a terminal row; see the scout's shapes`);
    }
    await noDialog(page, "Jobs page");
    return { how, url: new URL(page.url()).pathname, words: await wordsOnScreen(page, [/Complete|Succeeded/, new RegExp(TRAINJOB)]) };
  } },
  { name: "mlflow", show: async ({ page, base }) => {
    const how = [await goMenu(page, base, HREF.mlflow)];
    let workspace = "";
    let frame = await waitFrameWith(page, EXPERIMENT, `the experiment ${EXPERIMENT}`, wait(60000), true).catch(() => null);
    let dashboardList = "";
    let toggleSent = null;
    if (!frame && await frameWith(page, NO_EXPERIMENTS)) {
      // The rescout of 2026-11-16: the dashboard's Experiments page for Zuno MLOps said "No experiments". MLflow's own UI,
      // behind "Launch MLflow", is opened in the same page (its address, never a new tab) and looked at.
      dashboardList = "No experiments";
      const launch = await anyFrame(page, LAUNCH_MLFLOW);
      const href = launch ? await launch.getAttribute("href").catch(() => null) : null;
      if (!href) throw new Error(`the dashboard lists no experiment for ${PROJECT} ("No experiments") and offers no Launch MLflow link (${LAUNCH_MLFLOW.join(" | ")})`);
      const target = new URL(href, page.url());
      await page.goto(target.href);
      await settle(page);
      how.push(`Launch MLflow: ${target.host === new URL(base).host ? "" : target.host}${target.pathname}`);
      frame = await waitFrameWith(page, EXPERIMENT, `the experiment ${EXPERIMENT} in MLflow's own UI`, wait(60000), true).catch(() => null);
    }
    if (!frame) {
      // MLflow's own UI: its Experiments page ("Create experiment" is never pressed).
      const list = await anyFrame(page, EXPERIMENTS_LINK, true);
      if (list) { await click(list, { changes }); how.push(list.matched); await settle(page); }
      frame = await waitFrameWith(page, EXPERIMENT, `the experiment ${EXPERIMENT} in MLflow's Experiments`, wait(30000), true).catch(() => null);
    }
    if (!frame && TRAINING_VIEW_DECLARED) {
      const toggle = await anyFrame(page, TRAINING_VIEW, true);
      if (toggle) {
        toggleSent = await switchView(page, toggle);
        how.push(toggle.matched);
        if (toggleSent.refused.length) {
          throw new Error(`switching MLflow to its Model training view wanted to send ${toggleSent.refused.join(", ")}: refused before it left the browser; `
            + "the declared switch must send no write (zuno-demo-reorg's condition): option B, no MLflow row");
        }
      }
      frame = await waitFrameWith(page, EXPERIMENT, `the experiment ${EXPERIMENT} in MLflow's training view`, wait(30000), true).catch(() => null);
    }
    if (!frame) {
      const picker = await anyFrame(page, WORKSPACE_PICKER, true);
      const onIt = picker ? new RegExp(WORKSPACE).test(await picker.innerText().catch(() => "")) : false;
      if (!picker || onIt) {
        const where = page.frames().find(isMlflow) || page.mainFrame();
        const listed = await where.evaluate(() => [...document.querySelectorAll("td a, [role='gridcell'] a, [role='row'] a")].map((a) => (a.innerText || "").trim()).filter(Boolean).slice(0, 12)).catch(() => []);
        const toggle = !TRAINING_VIEW_DECLARED && await anyFrame(page, TRAINING_VIEW, true);
        const seen = `MLflow's own UI ${onIt ? `in the workspace ${WORKSPACE} ` : ""}lists ${listed.length ? listed.join(", ") : "none"}`
          + `${dashboardList ? `, the dashboard says "No experiments" for ${PROJECT}` : ""} (${how.join(" > ")})`;
        const view = TRAINING_VIEW_DECLARED ? (toggleSent ? "in MLflow's Model training view too" : "and MLflow's Model training switch was not found") : "";
        throw new Error(toggle
          ? `no experiment ${EXPERIMENT} outside MLflow's "Model training" view, a radio a take switches only as a declared change, the owner's decision: ${seen}`
          : `no experiment ${EXPERIMENT} ${view}: ${seen}; row 2:45 may have nothing to show on this cluster (its fallback: the WP-116 record)`);
      }
      await click(picker, { changes });
      workspace = picker.matched;
      const option = await waitUntil(page, { what: `the workspace ${WORKSPACE}`, timeoutMs: wait(15000),
        done: async () => (await anyFrame(page, [`[role='option']:has-text('${WORKSPACE}')`, `[role='menuitem']:has-text('${WORKSPACE}')`, `li:has-text('${WORKSPACE}')`])) || undefined });
      await click(option, { changes });
      frame = await waitFrameWith(page, EXPERIMENT, `the experiment ${EXPERIMENT} in the workspace ${WORKSPACE}`, wait(30000), true);
    }
    await click(frame.getByText(EXPERIMENT, { exact: true }).first(), { changes });
    const runs = await waitFrameWith(page, RUN_NAME, `a run of ${EXPERIMENT}`);
    await noDialog(page, "MLflow experiment");
    const words = {};
    for (const word of [/base_model/, /lora_r\b/, /gate_passed/, /train_loss|loss/]) words[word.source] = await runs.getByText(word).first().isVisible().catch(() => false);
    return { how, dashboard_list: dashboardList || "listed", workspace: workspace || "none chosen", training_view: toggleSent || "not needed",
             embedded: runs !== page.mainFrame(), url: page.url().replace(/[?#].*/, ""), words };
  } },
].filter((screen) => MLFLOW_ROW || screen.name !== "mlflow");

export async function enter({ page, base, mark, keycloak, state }) {
  state.writes = writesSeen(page);
  await page.goto(`${base}/`);
  const provider = await waitUntil(page, { what: "the OpenShift sign-in page", timeoutMs: wait(60000),
    done: async () => (await firstVisible(page, [...PROVIDER_LINK, "#username"])) || undefined });
  if (provider.matched !== "#username") await click(provider, { changes });
  await page.waitForSelector("#username", { timeout: wait(30000) });
  await mark("login");   // the EMPTY Keycloak form: nothing is marked once the password is typed
  await keycloak(persona);
  await waitUntil(page, { what: "the OpenShift AI dashboard", timeoutMs: wait(90000), done: async () => {
    if (APPROVE.test(page.url()) || APPROVE.test(await page.locator("body").innerText().catch(() => ""))) {
      throw new Error(`OpenShift asks ${persona} to authorize the dashboard's access: a take grants nothing; sign in once by hand, then take again`);
    }
    return (page.url().startsWith(base) && (await firstVisible(page, NAV))) || undefined;
  } });
  await page.waitForLoadState("networkidle", { timeout: wait(60000) }).catch(() => {});
  await page.waitForTimeout(1500);
}

// Nothing a persona owns is touched: the take is read only. The recorder compares this list before and after.
export async function owned() {
  return [];
}

export async function run(ctx) {
  const { page, mark, log, state } = ctx;
  await noDialog(page, "dashboard");
  await mark("dashboard");
  await page.waitForTimeout(DWELL_MS);
  for (const screen of SCREENS) {
    const found = await screen.show(ctx);
    log(`${screen.name}: ${JSON.stringify(found)}`);
    await page.waitForTimeout(DWELL_MS);
    await mark(screen.name);
  }
  await page.waitForTimeout(1000);
  await mark("end");
  const wrote = state.writes();
  if (wrote.length) throw new Error(`the take sent ${wrote.join(", ")}: it must start and change nothing`);
}

// What a take will meet, for the price of a sign-in: the menu with every group opened and its links (text and
// address), then each screen as a step and its shapes. Nothing is started, created or changed.
export async function scout(ctx) {
  const { page, base, step, state } = ctx;
  if (!state.scout) throw new Error("scout() runs only in scout mode");
  await step("menu", async () => ({ url: page.url().replace(/[?#].*/, ""), dialog_on_screen: await page.locator(DIALOG).first().isVisible().catch(() => false),
                                    links: await menuLinks(page) }));
  await page.goto(`${base}/`);
  await page.waitForLoadState("networkidle", { timeout: wait(60000) }).catch(() => {});
  for (const screen of SCREENS) {
    await step(screen.name, async () => screen.show(ctx));
    await step(`${screen.name}-shapes`, async () => ({ url: page.url().replace(/[?#].*/, ""), main: await describe(page, "main, body", 60).catch(() => []),
                                                       frames: page.frames().map((f) => { try { return new URL(f.url()).pathname; } catch { return ""; } }).filter(Boolean) }));
  }
  await step("closed", async () => {
    const wrote = state.writes();
    if (wrote.length) throw new Error(`the scout sent ${wrote.join(", ")}`);
    return { writes: 0 };
  });
}

export async function cleanup() {
  return null;
}
