// WP-289 / ADR-0618: the walkthrough of "Ansible Automation Platform - audited operations", 5-minute version, for
// evaluations/browser/record.mjs.
//
// The rows of docs/demo/scenarios/foundation/aap-audited-operations.md, as consultant-03 (Keycloak group aap_reader,
// AAP Team aap-reader-team, view only): the Keycloak form (login), AAP's first screen after the sign-in (home, row
// 0:00), the job and workflow templates (templates, row 0:45), the jobs narrowed to zuno-day0-check (jobs) and the
// Details tab of the latest run launched by zuno-mcp (job, row 2:00), the project zuno-demo (project, row 3:15), then
// end. Row 4:15 is words.
//
// The job is shown on its Details tab and its Output is never opened: the output of zuno-day0-check may print node
// names or paths. The take goes from the list to the Details page by its address, not by the job's link, which may
// open the Output first; the cut shows the two as stills. (The recorder also fails a take whose page shows a node
// name or a private address at a marker.)
//
// Read only. It launches, syncs, approves and edits nothing: every request to AAP other than GET, HEAD or OPTIONS is
// refused before it leaves the browser (guard() below), and a take or a scout that met one fails and names it. owned()
// lists the jobs consultant-03 launched (AAP's unified jobs it created): the same list before and after, nothing to
// delete. No model, no budget. AAP itself may create the user consultant-03 at its first sign-in (the Keycloak
// authenticator creates users), as the page's 0:00 row does.
//
// NOT seen live: AAP 2.7's screens on demo333. The Keycloak sign-in to AAP was proven once, on demo222 (WP-103,
// 2026-08-30), by a login round trip checked through the API, never with these screens. Every selector below is a
// guess from AAP's platform UI. The scout plays the same screens and dumps the shapes of what it meets on each one
// (tag, role, labels, the first classes), so the selectors can be written from them. Also untested: whether a reader
// sees jobs it did not launch. The scout counts them; the page's fallback is consultant-02.
import { click, describe, firstVisible, pageApi, waitUntil, wordsOnScreen } from "./_helpers.mjs";

export const persona = "consultant-03";
export const page = "docs/demo/scenarios/foundation/aap-audited-operations.md";
export const viewport = { width: 1280, height: 800 };
export const markers = ["login", "home", "templates", "jobs", "job", "project", "end"];
// The sign-in (login to home) is never shown as motion.
export const motion_from = "home";
export const changes = [];
export const url = (domain) => `https://aap.${domain}`;
// The requests a scout refuses on top of guard(): AAP's actions on an object (launch, sync, cancel, approve...).
export const sends = /\/api\/controller\/v2\/[a-z_]+\/\d+\/(launch|relaunch|cancel|update|approve|deny|copy|callback)\/?(\?|$)/;

const AUTHENTICATOR = "Keycloak zuno";   // the authenticator the aap_config role creates
const TEMPLATE = "zuno-day0-check";
const LAUNCHER = "zuno-mcp";             // the AAP user of aap-mcp: the agents' launches
const PROJECT = "zuno-demo";
const SOURCE = /github\.com\/startxfr\/zuno-demo/;

// AAP's sign-in page: the link of the Keycloak authenticator (guess: the gateway renders each SSO authenticator as a
// link to /api/gateway/social/login/<slug>/). When none is on screen, the link comes from the page's own
// /api/gateway/v1/ui_auth/ (guess), read with a GET.
const SSO = ["a[href*='/social/login/'][href*='keycloak' i]", `a:has-text('${AUTHENTICATOR}')`, `button:has-text('${AUTHENTICATOR}')`,
             `[aria-label*='${AUTHENTICATOR}' i]`];
const KEYCLOAK_FORM = "#kc-login";       // the stock Keycloak theme; AAP's own form may also have a #username
const PASSWORD = "input[type='password']";   // AAP's own sign-in form, drawn: never filled
const KEYCLOAK_ERROR = "#input-error, #kc-error-message, .kc-feedback-text, .alert-error";
const SHELL = ["nav button:has-text('Automation Execution')", "nav a:text-is('Jobs')", "nav a:text-is('Templates')", "nav"];   // guess: AAP's left menu
const NAV_GROUP = ["nav button:has-text('Automation Execution')"];                                                            // guess
const NAV = { templates: ["nav a:text-is('Templates')"], jobs: ["nav a:text-is('Jobs')"], projects: ["nav a:text-is('Projects')"] };   // guess
const ROUTE = { templates: "/execution/templates", jobs: "/execution/jobs", projects: "/execution/projects" };                // guess
const jobDetails = (id) => `/execution/jobs/playbook/${id}/details`;                                                          // guess
const projectDetails = (id) => `/execution/projects/${id}/details`;                                                           // guess
const MAIN = "main, [role='main']";
const FILTER = ["#filter-input", "main input[aria-label*='filter' i]", "main input[placeholder*='filter' i]", "main input[type='search']"];   // guess
const APPLY = ["[aria-label='apply filter']", "main button[aria-label*='search' i]"];                                          // guess; Enter otherwise
const LAUNCH = "main button[aria-label*='Launch' i], main [data-cy*='launch' i]";                                            // guess; read for its state, never clicked
const DIALOG = "[role='dialog'][aria-modal='true'], .pf-v5-c-backdrop, .pf-v6-c-backdrop";                                 // guess: a welcome or a tour
const DWELL_MS = 2000;   // a presenter's pause on each screen, so that every motion moment has frames to cut

// Every request to AAP's own address that could change something is refused before it leaves the browser: only GET,
// HEAD and OPTIONS pass (the Keycloak form is another address). Installed before the first page and kept for the
// whole take; state.refused keeps what was refused (method and path).
async function guard(page, base, state) {
  state.refused = [];
  const origin = new URL(base).origin;
  await page.route((u) => u.origin === origin, (route) => {
    const r = route.request();
    if (["GET", "HEAD", "OPTIONS"].includes(r.method())) return route.fallback();
    state.refused.push(`${r.method()} ${new URL(r.url()).pathname}`);
    return route.abort();
  });
}

function noWrites(state, where) {
  if (state.refused && state.refused.length) {
    throw new Error(`AAP's page wanted to send ${state.refused.join(", ")} (${where}): refused before it left the browser, nothing was written; `
      + "a take of this page changes nothing in AAP, see the scout");
  }
}

async function noDialog(page, where) {
  const dialog = page.locator(DIALOG).first();
  if (await dialog.isVisible().catch(() => false)) {
    const text = (await dialog.innerText().catch(() => "")).replace(/\s+/g, " ").trim().slice(0, 80);
    throw new Error(`a dialog covers ${where} ("${text}"): a take dismisses nothing it does not know; see the scout`);
  }
}

// The text is drawn inside AAP's main area.
async function shown(page, text, what, timeoutMs = 60000) {
  await waitUntil(page, { what, timeoutMs, done: async () => (await page.locator(MAIN).first().getByText(text).first().isVisible().catch(() => false)) || undefined });
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
}

// One read of AAP's controller API with the persona's session (its cookie, no token): {status, body}.
const api = (page, path) => pageApi(page, "GET", `/api/controller/v2/${path}`, null);
const results = (got) => (got && got.status === 200 && got.body && Array.isArray(got.body.results) ? got.body.results : null);

// From the left menu to one of AAP's lists: the menu's link, its group opened first when the link is not on screen;
// the list's address when the menu offers neither. Navigation only. Says which way it went.
async function go(page, base, which) {
  let link = await firstVisible(page, NAV[which]);
  let group = "";
  if (!link) {
    const toggle = await firstVisible(page, NAV_GROUP);
    if (toggle) {
      group = toggle.matched;
      await click(toggle, { changes });
      link = await waitUntil(page, { what: `the ${which} link in the left menu`, timeoutMs: 10000,
                                     done: async () => (await firstVisible(page, NAV[which])) || undefined }).catch(() => null);
    }
  }
  if (link) {
    await click(link, { changes });
    return `menu ${group ? group + " then " : ""}${link.matched}`;
  }
  await page.goto(`${base}${ROUTE[which]}`);
  return `address ${ROUTE[which]} (no menu link among ${NAV[which].join(" | ")})`;
}

// Sign in: AAP's sign-in page, its Keycloak link (or the address ui_auth gives), the Keycloak form, back to AAP.
async function signIn({ page, base, mark, keycloak, state }) {
  const chain = [];
  state.aap = { chain };
  await page.goto(`${base}/`);
  let first = await waitUntil(page, { what: "AAP's sign-in page", timeoutMs: 60000,
                                      done: async () => (await firstVisible(page, [...SSO, KEYCLOAK_FORM, PASSWORD])) || undefined });
  if (first.matched === PASSWORD) {
    // AAP's own form is drawn: its Keycloak link may come a moment later. The form itself is never filled.
    first = (await waitUntil(page, { what: "the Keycloak link", timeoutMs: 5000, done: async () => (await firstVisible(page, SSO)) || undefined }).catch(() => null)) || first;
  }
  let form = first.matched === KEYCLOAK_FORM;
  if (SSO.includes(first.matched)) {
    chain.push({ step: "sso-link", url: page.url().replace(/[?#].*/, ""), matched: first.matched });
    await click(first, { changes });
    form = Boolean(await waitUntil(page, { what: "the Keycloak form", timeoutMs: 20000,
                                           done: async () => (await firstVisible(page, [KEYCLOAK_FORM])) || undefined }).catch(() => null));
  }
  if (!form) {
    // No link on the sign-in page, or one that led elsewhere: the gateway's own list of sign-in methods.
    const got = await pageApi(page, "GET", "/api/gateway/v1/ui_auth/", null).catch(() => null);
    const sso = got && got.status === 200 && got.body && Array.isArray(got.body.ssos) ? got.body.ssos.find((s) => s && s.name === AUTHENTICATOR) : null;
    if (!sso || !sso.login_url) throw new Error(`no way to the Keycloak sign-in: no link among ${SSO.join(" | ")}, and /api/gateway/v1/ui_auth/ answered HTTP ${got ? got.status : 0} without "${AUTHENTICATOR}"`);
    chain.push({ step: "ui_auth", url: new URL(sso.login_url, base).pathname, matched: "ui_auth" });
    await page.goto(new URL(sso.login_url, base).href);
    await page.waitForSelector(KEYCLOAK_FORM, { timeout: 30000 });
  }
  await mark("login");   // the EMPTY Keycloak form: nothing is marked once the password is typed
  await keycloak(persona);
  let loginSince = 0;
  await waitUntil(page, { what: "AAP after the Keycloak sign-in", timeoutMs: 90000, done: async () => {
    if (!page.url().startsWith(base)) {
      const error = page.locator(KEYCLOAK_ERROR).first();
      if (await error.isVisible().catch(() => false)) {
        throw new Error(`Keycloak refused the sign-in of ${persona}: "${(await error.innerText().catch(() => "")).trim().slice(0, 80)}"`);
      }
      return undefined;
    }
    // AAP's own sign-in page again, for more than a moment: the sign-in did not hold (the page's first fallback).
    if (await firstVisible(page, SSO)) {
      loginSince = loginSince || Date.now();
      if (Date.now() - loginSince > 8000) throw new Error("the Keycloak sign-in came back to AAP's sign-in page: see the page's If something goes wrong");
      return undefined;
    }
    loginSince = 0;
    return (await firstVisible(page, SHELL)) || undefined;
  } });
  chain.push({ step: "home", url: page.url().replace(/[?#].*/, ""), matched: (await firstVisible(page, SHELL)).matched });
  await page.waitForLoadState("networkidle", { timeout: 60000 }).catch(() => {});
  await page.waitForTimeout(1500);
}

// The screens of the rows, in order: each returns what it found, for the log (a take) or the step (a scout).
const SCREENS = [
  { name: "home", show: async ({ page }) => {
    await noDialog(page, "AAP's first screen");
    return { url: page.url().replace(/[?#].*/, ""), persona_on_screen: await page.getByText(persona, { exact: true }).first().isVisible().catch(() => false) };
  } },
  { name: "templates", show: async ({ page, base }) => {
    const how = await go(page, base, "templates");
    await shown(page, TEMPLATE, "the templates list");
    await noDialog(page, "the templates");
    const launch = page.locator(LAUNCH);
    const enabled = [];
    for (let i = 0; i < Math.min(await launch.count(), 40); i += 1) enabled.push(await launch.nth(i).isEnabled().catch(() => false));
    return { how, url: page.url().replace(/[?#].*/, ""), launch_actions: enabled.length, launch_enabled: enabled.filter(Boolean).length,
             words: await wordsOnScreen(page, [/zuno-day0-check/, /zuno-day3-test/, /-workflow\b/]) };
  } },
  { name: "jobs", show: async ({ page, base, state }) => {
    const how = await go(page, base, "jobs");
    await waitUntil(page, { what: "the jobs list", timeoutMs: 60000, done: async () => (await page.locator(MAIN).first().getByText(/zuno-/).first().isVisible().catch(() => false)) || undefined });
    let filter = "";
    const input = await firstVisible(page, FILTER);
    if (input) {
      await click(input, { changes });
      await page.keyboard.type(TEMPLATE, { delay: 40 });
      const apply = await firstVisible(page, APPLY);
      if (apply) await click(apply, { changes }); else await page.keyboard.press("Enter");
      filter = `${input.matched}, then ${apply ? apply.matched : "Enter"}`;
    }
    await shown(page, TEMPLATE, `the ${TEMPLATE} jobs`);
    // The run to open: the latest zuno-day0-check job launched by zuno-mcp that this persona can see.
    const all = await api(page, `jobs/?name=${TEMPLATE}&order_by=-id&page_size=1`);
    const byAgent = await api(page, `jobs/?name=${TEMPLATE}&created_by__username=${LAUNCHER}&order_by=-id&page_size=1`);
    const found = results(byAgent);
    state.job = found && found.length ? found[0].id : null;
    const seen = { visible: all && all.body ? all.body.count : `HTTP ${all ? all.status : 0}`, by_agent: byAgent && byAgent.body ? byAgent.body.count : `HTTP ${byAgent ? byAgent.status : 0}` };
    if (!state.job) {
      throw new Error(`${persona} sees no ${TEMPLATE} job launched by ${LAUNCHER} (${TEMPLATE} jobs it sees: ${seen.visible}; by ${LAUNCHER}: ${seen.by_agent}): `
        + "the page's Start asks for one (the delegation scenario with Approve); its fallback is the consultant-02 profile");
    }
    return { how, filter: filter || `no filter box among ${FILTER.join(" | ")}: the whole list`, url: page.url().replace(/[#].*/, ""), jobs: seen, job: state.job };
  } },
  { name: "job", show: async ({ page, base, state }) => {
    if (!state.job) throw new Error("no job to open (see the jobs screen)");
    // By its address: the job's link may open the Output first, and the Output is never on screen.
    await page.goto(`${base}${jobDetails(state.job)}`);
    await shown(page, LAUNCHER, `the Details of job ${state.job}`);
    if (!/\/details\/?$/.test(new URL(page.url()).pathname)) throw new Error(`the job's Details are not at ${jobDetails(state.job)}: AAP went to ${new URL(page.url()).pathname}`);
    await noDialog(page, "the job's Details");
    return { url: new URL(page.url()).pathname, words: await wordsOnScreen(page, [/Launched by/i, /Revision/i, /Successful|Failed|Running/, /Output/]) };
  } },
  { name: "project", show: async ({ page, base }) => {
    const how = await go(page, base, "projects");
    await shown(page, PROJECT, "the projects list");
    let open = "";
    const link = await firstVisible(page, [`main a:text-is('${PROJECT}')`, `[role='main'] a:text-is('${PROJECT}')`]);
    if (link) { await click(link, { changes }); open = link.matched; } else {
      const found = results(await api(page, `projects/?name=${PROJECT}`));
      if (!found || !found.length) throw new Error(`the project ${PROJECT} is neither a link on screen nor readable by ${persona}`);
      await page.goto(`${base}${projectDetails(found[0].id)}`);
      open = `address ${projectDetails(found[0].id)}`;
    }
    await shown(page, SOURCE, `the project ${PROJECT} and its source`);
    await noDialog(page, "the project");
    return { how, open, url: new URL(page.url()).pathname, words: await wordsOnScreen(page, [/\bdevel\b/, /Revision/i, /Source control/i]) };
  } },
];

export async function enter(ctx) {
  await guard(ctx.page, ctx.base, ctx.state);
  await signIn(ctx);
  noWrites(ctx.state, "the sign-in");
}

// What consultant-03 launched in AAP: the unified jobs it created, by id. The recorder compares the list read after the
// sign-in with the list after the clean-up: a take launches nothing, so they must be the same.
export async function owned({ page }) {
  const got = await api(page, `unified_jobs/?created_by__username=${persona}&order_by=-id&page_size=200`);
  const list = results(got);
  if (!list) throw new Error(`the jobs ${persona} launched could not be read (HTTP ${got ? got.status : 0})`);
  return list.map((j) => ({ kind: String(j.type || "job"), id: String(j.id) }));
}

export async function run(ctx) {
  const { page, mark, log, state } = ctx;
  log(`sign-in: ${state.aap.chain.map((c) => `${c.step} ${c.matched}`).join(", ")}`);
  for (const screen of SCREENS) {
    const found = await screen.show(ctx);
    noWrites(state, screen.name);
    log(`${screen.name}: ${JSON.stringify(found)}`);
    if (screen.name === "templates" && found.launch_enabled) log(`templates: ${found.launch_enabled} launch action(s) enabled for ${persona}: the page says none, check the take`);
    await page.waitForTimeout(DWELL_MS);
    await mark(screen.name);
  }
  await page.waitForTimeout(1000);
  await mark("end");
}

// The same screens as a take, without video. Each screen is a step, then a step `<screen>-shapes` that dumps what is
// on screen whatever the first one met (tag, role, aria labels, the first classes, 60 characters of a control's
// text), so every guess above can be checked and rewritten.
export async function scout(ctx) {
  const { page, step, state } = ctx;
  if (!state.scout) throw new Error("scout() runs only in scout mode");
  await step("sign-in", async () => ({ chain: state.aap.chain }));
  for (const screen of SCREENS) {
    await step(screen.name, async () => screen.show(ctx));
    await step(`${screen.name}-shapes`, async () => ({ url: page.url().replace(/[?#].*/, ""), nav: await describe(page, "nav", 40).catch(() => []),
                                                       main: await describe(page, MAIN, 60).catch(() => []) }));
  }
  await step("guard", async () => {
    noWrites(state, "the scout");
    return { refused: state.refused };
  });
}

// Nothing was created: the take only reads.
export async function cleanup() {
  return null;
}
