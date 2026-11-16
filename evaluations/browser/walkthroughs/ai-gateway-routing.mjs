// WP-288 / ADR-0618: the walkthrough of "AI gateway routing", 5-minute version, for evaluations/browser/record.mjs.
//
// Two takes of two different screens, each in its own browser and its own video (`takes`, each with its own markers):
//   chat       sale-01 on Open WebUI, rows 0:00 and 0:45: the Keycloak form (login), a new chat (home), the model
//              picker open on Zuno and Zuno Code (picker), Zuno Code chosen (code-picked), the page's code question
//              (q-sent, q-done), end.
//   dashboard  ai-ops-01 on Grafana, row 2:00: the Keycloak form (login), the dashboard "Five experiences" over the
//              last hour with client = open-webui (dashboard), the panel "Which provider served each experience
//              (over range)" (providers), end.
// Rows 3:15 and 4:15 are words. The prompt is the page's, verbatim (`node record.mjs --check ai-gateway-routing`).
//
// chat costs one Zuno Code answer and its chat title (two Codestral calls, as the page says) on sale-01's budget and
// creates ONE chat, deleted by its id. dashboard is read only: nothing created, nothing saved in Grafana. It is
// played after chat and waits, up to four minutes, until the panel names `mistral-codestral`: the call of the first
// take needs about a minute to reach the dashboard. Without it the take fails: the row's proof would not be on
// screen. Whether the panel also shows a local model for Open WebUI depends on somebody having asked Zuno in the
// hour (the page's Start asks the presenter to); it is logged, not required.
//
// Open WebUI's selectors were seen live on 2026-11-15 (the picker's are the open-webui walkthrough's); Grafana's
// chain and panel selectors are guesses (_grafana.mjs). scout() reports both, sends nothing and creates nothing.
import { click, firstVisible, newText, onScreen, owui, owuiAnswered, owuiAsk, owuiChats, owuiDeleteChat, owuiHome, wordsOnScreen } from "./_helpers.mjs";
import { grafana, grafanaDashboard, grafanaNewsSeen, grafanaPanel, grafanaSignIn, grafanaWrites } from "./_grafana.mjs";

export const takes = [
  { name: "chat", persona: "sale-01", markers: ["login", "home", "picker", "code-picked", "q-sent", "q-done", "end"], motion_from: "home" },
  { name: "dashboard", persona: "ai-ops-01", markers: ["login", "dashboard", "providers", "end"], motion_from: "dashboard" },
];
export const page = "docs/demo/scenarios/governance/ai-gateway-routing.md";
export const viewport = { width: 1280, height: 800 };
// The lists of the first take; each take carries its own above.
export const markers = takes[0].markers;
export const motion_from = takes[0].motion_from;
// The one declared change (the owner's decision of 2026-11-16): OpenShift's "Authorize Access" page for Grafana's proxy,
// approved for ai-ops-01 if it shows (the first time that persona comes through the proxy). Nothing else is changed.
export const changes = [grafana.AUTHORIZE_CHANGE];
export const prompts = { "0:45": "write Python code that checks the format of an email address" };
export const url = owui.url;
// A scout refuses a chat message to Open WebUI and any write to Grafana.
export const sends = new RegExp(`/api/(chat/completions|chat/completed|v1/chats/new|v1/chats/[^/]+$|v1/tasks/)|${grafana.writes.source}`);

// The picker of Open WebUI 0.12.5, as the open-webui walkthrough found it live on 2026-11-15.
const PICKER = ["#model-selector-model-button", "button[aria-label^='Selected model']", "#model-selector-0-button", "button[aria-label='Select a model']"];
const MODELS = ["Zuno", "Zuno Code"];
const DASHBOARD = { uid: "zuno-three-experiences", title: "Five experiences", from: "now-1h", client: "open-webui" };   // gitops/charts/grafana
const PANEL = "Which provider served each experience (over range)";
const PROOF = "mistral-codestral";        // the page: the code question went to Codestral
const LOCAL = /local-[a-z0-9-]+/;         // the page: a local model for the warm-up question, if one was asked
const WAIT_FOR_PROOF_MS = 240000;

// The applications' addresses: the cluster's, or the offline test's stand-ins.
const webui = (domain) => process.env.RECORD_BASE_URL_OWUI || owui.url(domain);
const dash = (domain) => process.env.RECORD_BASE_URL_GRAFANA || grafana.url(domain);

async function openDashboard(page, domain) {
  // The time range and the `client` variable are in the address only: nothing is saved in Grafana.
  await grafanaDashboard(page, dash(domain), DASHBOARD.uid, { from: DASHBOARD.from, vars: { client: DASHBOARD.client } });
  await page.getByText(DASHBOARD.title).first().waitFor({ timeout: 30000 });
}

export async function enter(ctx) {
  const { page, domain, mark, keycloak, take, state } = ctx;
  if (take.name === "dashboard") {
    state.writes = grafanaWrites(page);
    await grafanaSignIn({ ...ctx, base: dash(domain) }, take.persona, { changes });
    return;
  }
  // The sidebar is closed before the first screen is drawn: sale-01's earlier chat titles never appear in the take.
  await page.addInitScript(() => { try { localStorage.setItem("sidebar", "false"); } catch { /* storage refused */ } });
  await page.goto(`${webui(domain)}/oauth/oidc/login`);
  await page.waitForSelector("#username", { timeout: 30000 });
  await mark("login");   // the EMPTY form: nothing is marked once the password is typed
  await keycloak(take.persona);
  await owuiHome(page, webui(domain), { changes });
}

export async function owned({ page, take }) {
  return take.name === "dashboard" ? [] : owuiChats(page);
}

async function runChat({ page, mark, log, state }) {
  await mark("home");
  const picker = await firstVisible(page, PICKER);
  if (!picker) throw new Error(`the model picker was not found (${PICKER.join(" | ")})`);
  const before = await page.locator("body").innerText();
  await click(picker, { changes });
  await page.getByText("Zuno Code", { exact: true }).first().waitFor({ timeout: 15000 });
  await page.waitForTimeout(800);
  const listed = await newText(page, before);
  if (!listed.includes("Zuno Code")) throw new Error("the model picker does not list Zuno Code");
  await mark("picker");

  await click(page.getByText("Zuno Code", { exact: true }).first(), { changes });
  await page.waitForTimeout(800);
  if (!/Zuno Code/.test(await picker.innerText())) throw new Error("the model picker does not show Zuno Code after the choice");
  await mark("code-picked");

  state.sent = true;   // from here a chat may exist, even if its id is never read: cleanup() must not stay silent
  await owuiAsk(page, prompts["0:45"], state);
  await mark("q-sent");
  await page.waitForURL(owui.CHAT_ID, { timeout: 60000 });
  state.chatId = page.url().match(owui.CHAT_ID)[1];
  state.created.push({ kind: "chat", id: state.chatId });
  log(`chat ${state.chatId} created`);
  const code = await owuiAnswered(page, state.chatId, 1);
  if (code && !/```[\s\S]*?```/.test(code)) throw new Error("the Zuno Code answer holds no complete code block");
  await page.locator("pre, .cm-editor, code.hljs").first().waitFor({ timeout: 15000 });
  await page.waitForTimeout(1500);
  await mark("q-done");
  await page.waitForTimeout(800);
  await mark("end");
}

async function runDashboard({ page, domain, mark, log, state }) {
  await openDashboard(page, domain);
  await mark("dashboard");
  // The first take's call reaches the dashboard about a minute after it was made: look, wait, load again.
  const deadline = Date.now() + WAIT_FOR_PROOF_MS;
  let shown = await grafanaPanel(page, PANEL);
  while (!shown.lines.some((line) => line.includes(PROOF)) && Date.now() < deadline) {
    log(`the panel does not name ${PROOF} yet: waiting`);
    await page.waitForTimeout(20000);
    await openDashboard(page, domain);
    shown = await grafanaPanel(page, PANEL);
  }
  if (shown.no_data || !shown.lines.some((line) => line.includes(PROOF))) {
    throw new Error(`the panel "${PANEL}" does not name ${PROOF} for ${DASHBOARD.client} within ${WAIT_FOR_PROOF_MS / 60000} minutes of the code question: the row's proof is not on screen`);
  }
  const local = shown.lines.map((line) => (line.match(LOCAL) || [])[0]).find(Boolean);
  log(`the panel names ${PROOF}; a local model for ${DASHBOARD.client} in the hour: ${local || "NONE (nobody asked Zuno in Open WebUI in the last hour)"}`);
  await page.waitForTimeout(800);
  await mark("providers");
  await page.waitForTimeout(800);
  await mark("end");
  const wrote = state.writes();
  if (wrote.length) throw new Error(`the take sent ${wrote.join(", ")} to Grafana: it must change nothing there`);
}

export async function run(ctx) {
  return ctx.take.name === "dashboard" ? runDashboard(ctx) : runChat(ctx);
}

// What the takes will meet, for the price of the two sign-ins. chat: the picker and what it lists (nothing chosen,
// nothing typed). dashboard: the sign-in chain, the dashboard's address with its variable, and what the panel shows
// now (the proof of a take is not there yet: no question was asked).
export async function scout({ page, domain, step, state, take }) {
  if (!state.scout) throw new Error("scout() runs only in scout mode");
  if (take.name === "dashboard") {
    await step("chain", async () => ({ ...state.grafana, url: page.url().replace(/[?#].*/, "") }));
    await step("dashboard", async () => {
      await openDashboard(page, domain);
      return { url: page.url().replace(/[#].*/, ""), news: grafanaNewsSeen(page), dialog_on_screen: await page.locator("[role='dialog']").first().isVisible().catch(() => false), title_on_screen: await page.getByText(DASHBOARD.title).first().isVisible().catch(() => false),
               words: await wordsOnScreen(page, [/Last 1 hour/, /open-webui/, /Same models, same routing/]) };
    });
    await step("panel-providers", async () => {
      const shown = await grafanaPanel(page, PANEL);
      return { title: PANEL, ...shown, names_codestral: shown.lines.some((l) => l.includes(PROOF)), names_a_local_model: shown.lines.some((l) => LOCAL.test(l)) };
    });
    await step("closed", async () => {
      const wrote = state.writes();
      if (wrote.length) throw new Error(`the scout sent ${wrote.join(", ")} to Grafana`);
      return { writes: 0 };
    });
    return;
  }
  const before = (await owuiChats(page)).length;
  await step("picker", async () => {
    const text = await page.locator("body").innerText();
    const picker = await firstVisible(page, PICKER);
    if (!picker) throw new Error(`no model picker among ${PICKER.join(" | ")}`);
    const label = (await picker.innerText()).trim();
    await click(picker, { changes });
    await page.waitForTimeout(1000);
    const listed = await newText(page, text);
    return { selector: picker.matched, label, text: listed.slice(0, 20), zuno_code_listed: listed.includes("Zuno Code"),
             zuno_code_exact_matches: await page.getByText("Zuno Code", { exact: true }).count() };
  });
  await page.keyboard.press("Escape");
  await step("closed", async () => {
    await page.waitForTimeout(600);
    if (owui.CHAT_ID.test(page.url())) throw new Error("a chat is open after the scout");
    const after = (await owuiChats(page)).length;
    if (after !== before) throw new Error(`sale-01 owns ${after} chats after the scout, ${before} before it`);
    return { chats: after, chat_link_on_screen: await onScreen(page, owui.CHAT_LINK) };
  });
}

export async function cleanup({ page, log, state, take }) {
  return take.name === "dashboard" ? null : owuiDeleteChat(page, state, take.persona, prompts["0:45"], log);
}
