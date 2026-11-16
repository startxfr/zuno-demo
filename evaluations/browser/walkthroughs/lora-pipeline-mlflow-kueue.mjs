// WP-289 / ADR-0618: the walkthrough of "RHOAI pipelines - from a dataset to a fine-tuned LoRA adapter", 5-minute
// version, for evaluations/browser/record.mjs. Option A of 2026-11-16 (zuno-demo-reorg).
//
// The rows of docs/demo/scenarios/rhoai/lora-pipeline-mlflow-kueue.md, as ai-dev-01: the Keycloak form (login), the
// OpenShift AI dashboard (dashboard), the project Zuno MLOps and the graph of the pipeline "MLOps: dataset-to-model
// LoRA/PEFT pipeline (tekos)", version v0-3-0-tekos (pipeline, row 0:45), the Training jobs page with the TrainJob
// lora-comage-4c28m (trainjob, row 1:45), the MLflow experiment mlops-comage and its runs (mlflow, row 2:45), then end.
// Rows 0:00 and 4:30 are words; row 3:45 is the evidence page of WP-133, not filmed.
//
// It signs in through the OpenShift sign-in (the provider chooser `openshift`, then Keycloak), the flow the
// model-catalog-registry take proved on 2026-11-16 (its code is copied here: a walkthrough's hash covers only the
// shared helpers and itself). Read only: it starts no run, creates, edits or deletes nothing, sends no prompt; owned()
// is empty. A request that would create or change something in the pipeline server or in MLflow (`sends`) is refused
// in a scout and fails a take. When a dialog covers the dashboard, or OpenShift asks to authorize access, the take
// stops and says so.
//
// NOT seen live, all guesses until demo333's scout: the menu under "Develop & train" (the catalog scout saw the group,
// collapsed, its links unread), the project's Pipelines tab and its table (the dashboard lists a pipeline by its display
// name), the graph's step names as text, whether a "Training jobs" page exists in RHOAI 3.6.0-ea.2 (an absent dashboard
// flag means off), MLflow's UI under /mlflow and its workspace choice. The scout opens every collapsed group of the
// menu and dumps its links with their addresses, then plays each screen and dumps its shapes.
import { click, describe, firstVisible, read, waitUntil, wordsOnScreen } from "./_helpers.mjs";

export const persona = "ai-dev-01";
export const page = "docs/demo/scenarios/rhoai/lora-pipeline-mlflow-kueue.md";
export const viewport = { width: 1280, height: 800 };
export const markers = ["login", "dashboard", "pipeline", "trainjob", "mlflow", "end"];
// The provider chooser and the sign-in (up to dashboard) are never shown as motion.
export const motion_from = "dashboard";
export const changes = [];
export const url = (domain) => `https://rh-ai.${domain}`;
// The requests that would start or change something: a pipeline run, an experiment or a version created in the
// pipeline server (its API is /apis/v2beta1); a run, an experiment, a tag or a model changed in MLflow (its searches
// are POSTs too, and are reads: not here). A scout refuses these when they are not a GET; a take fails if one was sent.
export const sends = /\/apis\/v2beta1\/(runs|recurringruns|experiments|pipelines|pipelines\/[^/]+\/versions)\/?(\?|$)|\/mlflow\/(ajax-)?api\/2\.0\/mlflow\/(runs|experiments|registered-models|model-versions)\/(create|update|delete|restore|set-[a-z-]+|delete-[a-z-]+|log-[a-z-]+|rename)/;   // guess

const PROVIDER = "openshift";   // the page: the OpenShift sign-in, Keycloak behind it
const PROVIDER_LINK = [`a[title='Log in with ${PROVIDER}']`, `a.idp:text-is('${PROVIDER}')`, `a:text-is('${PROVIDER}')`];   // seen live, 2026-11-16
const APPROVE = /\/oauth\/authorize\/approve|Authorize Access|Allow selected permissions/i;                               // guess: an OAuth grant page
const NAV = ["#page-sidebar", "nav[aria-label*='Global' i]", "nav"];                                                       // seen, 2026-11-16 (catalog scout)
const DIALOG = "[role='dialog'][aria-modal='true'], .pf-v5-c-backdrop, .pf-v6-c-backdrop";                                  // guess: a welcome or a tour
const DWELL_MS = 2000;   // a presenter's pause on each screen, so that every motion moment has frames to cut

const PROJECT = "Zuno MLOps";                                         // the display name of zuno-mlops (the page)
const PIPELINE = "MLOps: dataset-to-model LoRA/PEFT pipeline (tekos)";   // gitops/charts/mlops: displayName + " (tekos)"
const VERSION = "v0-3-0-tekos";                                       // the version demo333 listed on 2026-11-16
const STEPS = [/prepare-dataset/, /train-lora/, /\bevaluate\b/, /push-registry/];
const TRAINJOB = "lora-comage-4c28m";
const EXPERIMENT = "mlops-comage";
const WORKSPACE = "zuno-mlops";
const RUN_NAME = /wp126-\d{8}-\d{6}/;
// The menu: Projects is a link of its own (seen, 2026-11-16); the Training jobs page is a guess under "Develop & train".
const NAV_PROJECTS = ["nav a:text-is('Projects')"];
const NAV_DEVELOP = ["nav button:has-text('Develop & train')"];                                                            // seen collapsed, 2026-11-16
const NAV_TRAINING = ["nav a:text-is('Training jobs')", "nav a:text-is('Model training')", "nav a:text-is('Training')", "nav a[href*='training' i]"];   // guess
const PROJECT_LINK = [`main a:text-is('${PROJECT}')`, `main a:has-text('${PROJECT}')`];                                   // guess
const PIPELINES_TAB = ["main [role='tab']:has-text('Pipelines')", "main button:text-is('Pipelines')", "main a:text-is('Pipelines')"];   // guess
const PIPELINE_LINK = [`main a:text-is('${PIPELINE}')`, `main a:has-text('${PIPELINE}')`, `main button:has-text('${PIPELINE}')`];   // guess
const WORKSPACE_PICKER = ["button:has-text('Workspace')", "[aria-label*='workspace' i]", "[data-testid*='workspace' i]"];       // guess (MLflow)

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

async function visibleText(page, text, what, timeoutMs = 60000) {
  await waitUntil(page, { what, timeoutMs, done: async () => (await page.getByText(text).first().isVisible().catch(() => false)) || undefined });
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
}

// Click the first of these on screen, waiting for one up to `timeoutMs`; says which matched.
async function clickOne(page, selectors, what, timeoutMs = 30000) {
  const found = await waitUntil(page, { what, timeoutMs, done: async () => (await firstVisible(page, selectors)) || undefined })
    .catch(() => { throw new Error(`${what} was not found (${selectors.join(" | ")})`); });
  await click(found, { changes });
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
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

// The screens of the rows, in order: each returns what it found, for the log (a take) or the step (a scout).
const SCREENS = [
  { name: "pipeline", show: async ({ page }) => {
    const how = [await clickOne(page, NAV_PROJECTS, "the Projects link of the menu")];
    how.push(await clickOne(page, PROJECT_LINK, `the project ${PROJECT}`));
    const tab = await waitUntil(page, { what: "the project's Pipelines tab", timeoutMs: 30000, done: async () => (await firstVisible(page, PIPELINES_TAB)) || undefined })
      .catch(() => { throw new Error(`the project's Pipelines tab was not found (${PIPELINES_TAB.join(" | ")})`); });
    if ((await tab.getAttribute("aria-selected").catch(() => null)) !== "true") { await click(tab, { changes }); how.push(tab.matched); }
    how.push(await clickOne(page, PIPELINE_LINK, `the pipeline ${PIPELINE}`, 60000));
    await waitUntil(page, { what: "the pipeline's graph", timeoutMs: 60000, done: async () => {
      const seen = await wordsOnScreen(page, STEPS);
      return Object.values(seen).every(Boolean) || undefined;
    } }).catch(() => { throw new Error(`the graph's steps (${STEPS.map((s) => s.source).join(", ")}) are not all on screen`); });
    await noDialog(page, "pipeline's graph");
    const version = await wordsOnScreen(page, [new RegExp(VERSION), /v0-4-0-tekos/]);
    if (!version[VERSION]) throw new Error(`the graph on screen is not of the version ${VERSION} (${JSON.stringify(version)}): the page's 0:45 row names it`);
    return { how, url: new URL(page.url()).pathname, version, merge_export_on_screen: await page.getByText(/merge-export/).first().isVisible().catch(() => false) };
  } },
  { name: "trainjob", show: async ({ page }) => {
    let link = await firstVisible(page, NAV_TRAINING);
    if (!link) {
      const group = await firstVisible(page, NAV_DEVELOP);
      if (group && (await group.getAttribute("aria-expanded").catch(() => null)) !== "true") await click(group, { changes });
      await page.waitForTimeout(600);
      link = await firstVisible(page, NAV_TRAINING);
      if (!link) {
        // A sub-group of "Develop & train" may hold it: open those that are closed.
        const inner = page.locator("nav button[aria-expanded='false']");
        for (let i = (await inner.count()) - 1; i >= 0; i -= 1) await click(inner.nth(i), { changes }).catch(() => {});
        await page.waitForTimeout(600);
        link = await firstVisible(page, NAV_TRAINING);
      }
    }
    if (!link) throw new Error(`no Training jobs page in the menu (${NAV_TRAINING.join(" | ")}): the row's other way is \`oc get trainjob\`, a terminal row; see the scout's menu`);
    await click(link, { changes });
    await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
    if (!(await page.getByText(TRAINJOB).first().isVisible().catch(() => false)) && !(await page.getByText(PROJECT).first().isVisible().catch(() => false))) {
      // The page may open on another project: its project selector, then Zuno MLOps.
      await clickOne(page, ["main button:has-text('Project')", "[data-testid*='project-selector' i]", "main [aria-label*='project' i]"], "the project selector", 15000);
      await clickOne(page, [`[role='menu'] :text-is('${PROJECT}')`, `[role='listbox'] :text-is('${PROJECT}')`, `text=${PROJECT}`], `the project ${PROJECT} in the selector`, 15000);
    }
    await visibleText(page, TRAINJOB, `the TrainJob ${TRAINJOB}`);
    await noDialog(page, "Training jobs page");
    return { link: link.matched, url: new URL(page.url()).pathname, words: await wordsOnScreen(page, [/Complete|Succeeded/, new RegExp(TRAINJOB)]) };
  } },
  { name: "mlflow", show: async ({ page, base }) => {
    await page.goto(`${base}/mlflow`);
    await page.waitForLoadState("networkidle", { timeout: 60000 }).catch(() => {});
    let workspace = "";
    const listed = await waitUntil(page, { what: `the experiment ${EXPERIMENT}`, timeoutMs: 30000, done: async () => (await page.getByText(EXPERIMENT, { exact: true }).first().isVisible().catch(() => false)) || undefined }).catch(() => false);
    if (!listed) {
      workspace = await clickOne(page, WORKSPACE_PICKER, "MLflow's workspace picker", 15000);
      await clickOne(page, [`[role='option']:has-text('${WORKSPACE}')`, `[role='menuitem']:has-text('${WORKSPACE}')`, `text=${WORKSPACE}`], `the workspace ${WORKSPACE}`, 15000);
      await visibleText(page, EXPERIMENT, `the experiment ${EXPERIMENT} in the workspace ${WORKSPACE}`, 30000);
    }
    await click(page.getByText(EXPERIMENT, { exact: true }).first(), { changes });
    await visibleText(page, RUN_NAME, `a run of ${EXPERIMENT}`);
    await noDialog(page, "MLflow experiment");
    return { workspace: workspace || "none chosen", url: page.url().replace(/[?].*/, ""), words: await wordsOnScreen(page, [/base_model/, /lora_r\b/, /gate_passed/, /train_loss|loss/]) };
  } },
];

export async function enter({ page, base, mark, keycloak, state }) {
  state.writes = writesSeen(page);
  await page.goto(`${base}/`);
  const provider = await waitUntil(page, { what: "the OpenShift sign-in page", timeoutMs: 60000,
    done: async () => (await firstVisible(page, [...PROVIDER_LINK, "#username"])) || undefined });
  if (provider.matched !== "#username") await click(provider, { changes });
  await page.waitForSelector("#username", { timeout: 30000 });
  await mark("login");   // the EMPTY Keycloak form: nothing is marked once the password is typed
  await keycloak(persona);
  await waitUntil(page, { what: "the OpenShift AI dashboard", timeoutMs: 90000, done: async () => {
    if (APPROVE.test(page.url()) || APPROVE.test(await page.locator("body").innerText().catch(() => ""))) {
      throw new Error(`OpenShift asks ${persona} to authorize the dashboard's access: a take grants nothing; sign in once by hand, then take again`);
    }
    return (page.url().startsWith(base) && (await firstVisible(page, NAV))) || undefined;
  } });
  await page.waitForLoadState("networkidle", { timeout: 60000 }).catch(() => {});
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
  await page.waitForLoadState("networkidle", { timeout: 60000 }).catch(() => {});
  for (const screen of SCREENS) {
    await step(screen.name, async () => screen.show(ctx));
    await step(`${screen.name}-shapes`, async () => ({ url: page.url().replace(/[?#].*/, ""), main: await describe(page, "main, body", 60).catch(() => []) }));
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
