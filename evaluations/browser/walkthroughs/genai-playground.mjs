// WP-290 / ADR-0618: the walkthrough of "GenAI playground", 5-minute version, for evaluations/browser/record.mjs.
// Written scout first (zuno-demo-reorg, 2026-11-16): nothing of the playground was seen by a scout yet.
//
// The rows of docs/demo/scenarios/rhoai/genai-playground.md, as ai-ops-01, in the MaaS consumer portal: the Keycloak
// form of the OpenShift sign-in (login), the playground of the project Zuno Playground with Settings > Model (playground,
// row 0:00), the 0:45 question and its answer (q1-sent, q1-done), Settings > MCP as it is in this browser (mcp, the
// still of row 1:45), then end. The owner's choice of 2026-11-16: the MCP token is never pasted; the take shows the
// connection as it is. Rows 1:45 (a connected gateway) and 3:00 (a tool call) are filmed only if a connection saved
// by a person is found by a fresh browser, i.e. kept on the server: the scout says so, and TOOLS_ROW is then switched
// on by a later commit (markers q2-sent, q2-done, and the 3:00 prompt, narrow, from the page). The recorder is never
// given ai-ops-01's OpenShift token.
//
// What a take may send: every request to the portal's address that is not a GET, HEAD or OPTIONS is refused before
// it leaves the browser and fails the take, except while one question is answered (q1-sent to q1-done): that
// question is the take's one change, a model call on ai-ops-01's MaaS subscription; what it sent is logged by method
// and path. A scout sends no prompt and refuses every such request, listing them by step, so the review sees what the
// project, model and subscription choices send (unknown 3 of the survey). The MCP lock is never clicked, no token
// field is read, and the MCP panel is reported by shapes with any token-like text replaced.
//
// The scout reports, for the questions of the survey: whether this fresh browser finds the gateway connected (its
// tools cell, the Auth control's labels), the names (never the values) of the portal's browser-storage keys, the
// requests the page makes on its own whose path names a chat, a conversation or a response (a server-side chat store,
// unknown 2), and the shapes of each screen (unknown 5). What a chat leaves on the server is not known before that:
// owned() is empty until it is.
//
// The first scout (2026-11-16 16:11, demo333, at a6f7635b): the sign-in lands on /maas-consumer-portal/gen-ai-studio/assets;
// the menu link `nav a:text-is('Playground')` opens the playground of zuno-playground ("New chat", "Compare chat", no
// chat history list); Settings > Model shows the model gpt-oss-20b and the subscription gpt-oss-20b-agents (not the
// page's gpt-oss-20b-builders) in PatternFly menu toggles; Settings > MCP lists zuno-mcp-gateway with "0 active" and a
// lock: no saved connection in a fresh browser, the token is kept in the browser. zuno-demo-reorg's decision:
// TOOLS_ROW stays off, no token is given to the recorder, and the subscription shown is filmed as it is, never chosen.
// localStorage holds one key (mod-arch.namespace.lastUsed), sessionStorage none; the page reads its models, MCP
// servers, vector stores and status with GETs only, and asked for no chat store.
//
// Selectors: the portal's left menu "Playground", the playground's address
// /maas-consumer-portal/gen-ai-studio/playground/zuno-playground, the "Settings" button and its tabs Model, Prompt,
// Knowledge, MCP, the MCP row `zuno-mcp-gateway` with its "9 active" tools and its Auth lock, the "Send a message..."
// box and the metric chips are read from the WP-220 screenshots of 2026-11-06; everything else is a guess.
import { click, firstVisible, read, waitUntil, wordsOnScreen } from "./_helpers.mjs";

export const persona = "ai-ops-01";
export const page = "docs/demo/scenarios/rhoai/genai-playground.md";
export const viewport = { width: 1280, height: 800 };
// Rows 1:45 and 3:00 with a connected gateway: off until a scout finds the connection kept on the server.
const TOOLS_ROW = false;
export const markers = TOOLS_ROW ? ["login", "playground", "q1-sent", "q1-done", "mcp", "q2-sent", "q2-done", "end"]
                                 : ["login", "playground", "q1-sent", "q1-done", "mcp", "end"];
// The sign-in (login to playground) is never shown as motion.
export const motion_from = "playground";
export const changes = [];
export const prompts = { "0:45": "Réponds en une phrase : quelle est la capitale de la France ?" };
export const url = (domain) => `https://rh-ai.${domain}`;
// The requests a scout refuses on top of the guard below: a chat answer (guess: OGX's responses API behind the BFF).
export const sends = /\/(responses|chat|completions|conversations|messages)(\/|\?|$)/;   // guess

const PORTAL = "/maas-consumer-portal";
const PLAYGROUND = `${PORTAL}/gen-ai-studio/playground/zuno-playground`;          // seen in the WP-220 screenshot
const PROJECT = "Zuno Playground";
const MODEL = "publishers/zuno-ai-run/models/gpt-oss-20b";
const SUBSCRIPTION = /^gpt-oss-20b-[a-z0-9-]+$/;   // the subscription shown (gpt-oss-20b-agents in the scout): read, never chosen
const SERVER = "zuno-mcp-gateway";
const PROVIDER = "openshift";
const PROVIDER_LINK = [`a[title='Log in with ${PROVIDER}']`, `a.idp:text-is('${PROVIDER}')`, `a:text-is('${PROVIDER}')`];   // seen live, 2026-11-16
const APPROVE = /\/oauth\/authorize\/approve|Authorize Access|Allow selected permissions/i;
const NAV_PLAYGROUND = ["nav a:text-is('Playground')", "a:text-is('Playground')"];                                         // WP-220 screenshot
const CREATE = ["button:has-text('Create playground')", "a:has-text('Create playground')"];                                 // never clicked
const SETTINGS = ["button:has-text('Settings')", "[aria-label='Settings']"];                                               // WP-220 screenshot
const TAB = (name) => [`[role='tab']:has-text('${name}')`, `button:text-is('${name}')`, `button:has-text('${name}')`];      // WP-220: Model | Prompt | Knowledge | MCP
// PatternFly menu toggles (the scout of 2026-11-16); the model is chosen only when another one is shown.
const MODEL_PICKER = ["button.pf-v6-c-menu-toggle:has-text('publishers/')", "button.pf-v5-c-menu-toggle:has-text('publishers/')",
                      "[aria-label*='model' i][aria-haspopup]", "button[aria-haspopup]:has-text('publishers/')"];   // guess
const INPUT = ["textarea[placeholder*='Send a message' i]", "[contenteditable='true'][aria-label*='message' i]", "textarea"];   // WP-220 screenshot: "Send a message..."
const CHIPS = /TTFT|T\/s/;                                                                                                  // WP-220 screenshot: "TTFT: 630ms", "169 T/s"
const DIALOG = "[role='dialog'][aria-modal='true'], .pf-v5-c-backdrop, .pf-v6-c-backdrop";
const STORE = /conversation|responses|chat|histor|session|thread/i;   // a request path that may name a chat kept on the server
const TOKENISH = /sha256~\S+|[A-Za-z0-9_\-.]{40,}/g;                 // what a report never carries
const DWELL_MS = 2000;

// Every request to the portal's address is noted (method and path, never the query or the body); one that is not a
// GET, HEAD or OPTIONS is refused unless a question is being answered (state.answering, a take only).
async function guard(page, base, state) {
  state.requests = [];
  state.refused = [];
  state.answering = false;
  state.sent = [];
  const origin = new URL(base).origin;
  await page.route((u) => u.origin === origin, (route) => {
    const r = route.request();
    const seen = `${r.method()} ${new URL(r.url()).pathname}`;
    if (!state.requests.includes(seen) && state.requests.length < 400) state.requests.push(seen);
    if (["GET", "HEAD", "OPTIONS"].includes(r.method())) return route.fallback();
    if (state.answering && !state.scout) { state.sent.push(seen); return route.fallback(); }
    state.refused.push(seen);
    return route.abort();
  });
}

function noWrites(state, where) {
  if (state.refused.length) {
    throw new Error(`the portal wanted to send ${[...new Set(state.refused)].join(", ")} (${where}): refused before it left the browser; `
      + "see the scout, which lists what each screen sends");
  }
}

// The requests seen since `from` (an index into state.requests), the store-like ones apart.
function since(state, from) {
  const list = state.requests.slice(from);
  return { requests: list.slice(0, 80), store_like: list.filter((r) => STORE.test(r.split(" ")[1] || "")) };
}

async function noDialog(page, where) {
  const dialog = page.locator(DIALOG).first();
  if (await dialog.isVisible().catch(() => false)) {
    const text = (await dialog.innerText().catch(() => "")).replace(TOKENISH, "[redacted]").replace(/\s+/g, " ").slice(0, 80);
    throw new Error(`a dialog covers ${where} ("${text}"): a take dismisses nothing; see the scout`);
  }
}

// Shapes of a part of the page, safe for a report: tag, role, aria labels, type, the first classes and 60 characters
// of an element's own text, any token-like run replaced. An input's value is never read.
function shapesOf([scope, tokenish, limit]) {
  const re = new RegExp(tokenish, "g");
  const root = document.querySelector(scope) || document.body;
  return [...root.querySelectorAll("[role], button, a[href], input, textarea, select, td, th, label")].filter((el) => {
    const r = el.getBoundingClientRect();
    return r.width > 1 && r.height > 1 && r.bottom > 0 && r.top < innerHeight;
  }).slice(0, limit).map((el) => {
    const attrs = {};
    for (const a of el.attributes) if (a.name.startsWith("aria-") || a.name === "type" || a.name === "data-testid") attrs[a.name] = a.value.replace(re, "[redacted]").slice(0, 80);
    const own = ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) ? "" : (el.innerText || "").trim().split("\n")[0];
    return { tag: el.tagName.toLowerCase(), role: el.getAttribute("role") || "", attrs, classes: [...el.classList].slice(0, 4), text: own.replace(re, "[redacted]").slice(0, 60) };
  });
}
const shapes = (page, scope = "body", limit = 60) => read(page, shapesOf, [scope, TOKENISH.source, limit]).catch(() => []);

// The settings panel open on one of its tabs (the Settings button only when no tab is on screen: it toggles).
async function settingsTab(page, name) {
  if (!(await firstVisible(page, TAB(name)))) {
    const open = await firstVisible(page, SETTINGS);
    if (!open) throw new Error(`neither the Settings button (${SETTINGS.join(" | ")}) nor its ${name} tab is on screen`);
    await click(open, { changes });
  }
  const tab = await waitUntil(page, { what: `the ${name} tab of the settings`, timeoutMs: 15000, done: async () => (await firstVisible(page, TAB(name))) || undefined });
  if ((await tab.getAttribute("aria-selected").catch(() => null)) !== "true") await click(tab, { changes });
  await page.waitForTimeout(800);
  return tab.matched;
}

// The MCP row as this browser shows it: present, its tools cell, the labels of its Auth control. Never clicked.
async function mcpRow(page) {
  return read(page, ([server, tokenish]) => {
    const re = new RegExp(tokenish, "g");
    const row = [...document.querySelectorAll("tr, [role='row']")].find((r) => (r.innerText || "").includes(server));
    if (!row) return { listed: false };
    const cells = [...row.querySelectorAll("td, [role='cell'], [role='gridcell']")].map((c) => (c.innerText || "").trim().replace(re, "[redacted]").slice(0, 40));
    const auth = [...row.querySelectorAll("button, [role='button'], svg, [aria-label], [title]")].map((el) => ({
      tag: el.tagName.toLowerCase(), label: (el.getAttribute("aria-label") || el.getAttribute("title") || "").replace(re, "[redacted]").slice(0, 60),
      classes: [...el.classList].slice(0, 4) }));
    const tools = cells.find((c) => /\bactive\b|\btools?\b/i.test(c)) || "";
    return { listed: true, cells, tools, auth: auth.slice(0, 12), connected: /\b[1-9]\d* active\b/i.test(row.innerText || "") };
  }, [SERVER, TOKENISH.source]);
}

async function signIn({ page, base, mark, keycloak }) {
  await page.goto(`${base}${PORTAL}/`);
  const provider = await waitUntil(page, { what: "the OpenShift sign-in page", timeoutMs: 60000,
    done: async () => (await firstVisible(page, [...PROVIDER_LINK, "#username"])) || undefined });
  if (provider.matched !== "#username") await click(provider, { changes });
  await page.waitForSelector("#username", { timeout: 30000 });
  await mark("login");   // the EMPTY Keycloak form: nothing is marked once the password is typed
  await keycloak(persona);
  await waitUntil(page, { what: "the MaaS consumer portal", timeoutMs: 90000, done: async () => {
    if (APPROVE.test(page.url()) || APPROVE.test(await page.locator("body").innerText().catch(() => ""))) {
      throw new Error(`OpenShift asks ${persona} to authorize the portal's access: a take grants nothing; sign in once by hand, then take again`);
    }
    return (page.url().startsWith(`${base}${PORTAL}`) && (await firstVisible(page, NAV_PLAYGROUND))) || undefined;
  } });
  await page.waitForLoadState("networkidle", { timeout: 60000 }).catch(() => {});
}

// 2026-11-20: the portal keeps its last project (ai-tenants, a namespace RHOAI generates, with no playground) even on
// .../playground/zuno-playground: the page shows "Zuno Playground" but asks the BFF about ai-tenants and offers "Create
// playground". A presenter picks the project in the Project dropdown; so does the take, once. Never the user menu.
const PROJECT_TOGGLE = "button.pf-v6-c-menu-toggle, button.pf-v5-c-menu-toggle";
const PROJECT_OPTION = [`[role='menuitem']:has-text('${PROJECT}')`, `[role='option']:has-text('${PROJECT}')`,
                        `button:text-is('${PROJECT}')`, `li:has-text('${PROJECT}') button`];   // guess, read by the scout

async function pickProject(page) {
  const toggles = page.locator(PROJECT_TOGGLE);
  const n = await toggles.count();
  for (let i = 0; i < n; i++) {
    const toggle = toggles.nth(i);
    if (!(await toggle.isVisible().catch(() => false))) continue;
    const text = ((await toggle.innerText().catch(() => "")) || "").trim();
    if (!text || text === persona || text.startsWith("publishers/")) continue;
    await click(toggle, { changes });
    const option = await waitUntil(page, { what: `the project ${PROJECT} in the Project dropdown`, timeoutMs: 15000,
      done: async () => (await firstVisible(page, PROJECT_OPTION)) || undefined });
    await click(option, { changes });
    await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
    return `${text} -> ${PROJECT} (${option.matched})`;
  }
  return "";
}

// The playground of Zuno Playground, by its menu link, then its address when the link led to another project, then the
// Project dropdown when the page still shows "Create playground".
async function playground(page, base) {
  const from = await clickNav(page);
  if (!page.url().includes(PLAYGROUND)) await page.goto(`${base}${PLAYGROUND}`);
  let picked = null;
  await waitUntil(page, { what: "the playground of Zuno Playground", timeoutMs: 60000, done: async () => {
    if (await firstVisible(page, CREATE)) {
      if (picked === null) { picked = await pickProject(page); return undefined; }
      throw new Error(`the project ${PROJECT} shows "Create playground" instead of its playground`
        + `${picked ? ` (also after the Project dropdown: ${picked})` : " (no Project dropdown found)"}: never pressed (the page's rule); the playground must exist`);
    }
    return ((await page.getByText(PROJECT).first().isVisible().catch(() => false)) && (await firstVisible(page, INPUT))) || undefined;
  } });
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
  return { menu: from, project: picked || "from the address", url: new URL(page.url()).pathname };
}

async function clickNav(page) {
  const link = await firstVisible(page, NAV_PLAYGROUND);
  if (!link) return "no menu link";
  await click(link, { changes });
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
  return link.matched;
}

// The text of the first element on screen matching `re` (a hidden list option does not count), or "".
async function shownText(page, re) {
  const all = page.getByText(re);
  for (let i = 0; i < Math.min(await all.count(), 10); i += 1) {
    if (await all.nth(i).isVisible().catch(() => false)) return (await all.nth(i).innerText().catch(() => "")).trim();
  }
  return "";
}

// Settings > Model: the model the page names, chosen only when another one is shown (the choice runs under the
// guard: whatever it would send is refused and listed); the subscription shown is read, never chosen.
async function modelSettings(page, state) {
  const tab = await settingsTab(page, "Model");
  const shown = async () => ({ model: await page.getByText(MODEL).first().isVisible().catch(() => false),
                               subscription: await shownText(page, SUBSCRIPTION) });
  const before = await shown();
  const chosen = [];
  for (const [what, pickers, value] of [["model", MODEL_PICKER, MODEL]]) {
    if (before[what]) continue;
    const picker = await firstVisible(page, pickers);
    if (!picker) throw new Error(`the ${what} ${value} is not shown and no ${what} picker was found (${pickers.join(" | ")})`);
    const from = state.requests.length;
    await click(picker, { changes });
    const option = await waitUntil(page, { what: `the ${what} ${value} in its list`, timeoutMs: 15000,
      done: async () => (await firstVisible(page, [`[role='option']:has-text('${value}')`, `[role='menuitem']:has-text('${value}')`, `li:has-text('${value}')`])) || undefined });
    await click(option, { changes });
    await page.waitForTimeout(800);
    chosen.push({ what, sent: since(state, from).requests.filter((r) => !/^(GET|HEAD|OPTIONS) /.test(r)) });
  }
  const after = await shown();
  if (!after.model) throw new Error(`Settings > Model does not show ${MODEL} (${JSON.stringify(after)})`);
  if (!after.subscription) throw new Error("Settings > Model shows no gpt-oss-20b subscription");
  return { tab, before, chosen, subscription_shown: after.subscription };
}

// Enter: the guard, then the sign-in. A take stops on a refused request; a scout lists it and goes on, so that it
// reaches every screen (its step `closed` fails at the end when anything was refused).
export async function enter(ctx) {
  ctx.state.scout = Boolean(ctx.state.scout);
  await guard(ctx.page, ctx.base, ctx.state);
  await signIn(ctx);
  if (!ctx.state.scout) noWrites(ctx.state, "the sign-in");
}

// What a chat leaves on the server is not known yet (the scout looks for a store): nothing is listed.
export async function owned() {
  return [];
}

export async function run(ctx) {
  const { page, base, mark, log, state } = ctx;
  const where = await playground(page, base);
  const model = await modelSettings(page, state);
  await noDialog(page, "the playground");
  noWrites(state, "the playground");
  log(`playground: ${JSON.stringify({ ...where, ...model })}`);
  await page.waitForTimeout(DWELL_MS);
  await mark("playground");

  // 0:45: the one question, typed; what it sends is let through and logged.
  const input = await firstVisible(page, INPUT);
  if (!input) throw new Error(`the message box was not found (${INPUT.join(" | ")})`);
  const chips = await page.getByText(CHIPS).count();
  await click(input, { changes });
  state.answering = true;
  await page.keyboard.type(prompts["0:45"], { delay: 25 });
  await page.keyboard.press("Enter");
  await mark("q1-sent");
  await waitUntil(page, { what: "the answer and its metric chips", timeoutMs: 180000,
    done: async () => ((await page.getByText(/Paris/).first().isVisible().catch(() => false)) && (await page.getByText(CHIPS).count()) > chips) || undefined });
  await page.waitForTimeout(1500);
  state.answering = false;
  log(`the 0:45 question sent ${[...new Set(state.sent)].join(", ") || "nothing seen"}`);
  await mark("q1-done");

  // 1:45, the still: Settings > MCP as this browser shows it; the lock is never clicked.
  await settingsTab(page, "MCP");
  const row = await mcpRow(page);
  noWrites(state, "Settings > MCP");
  log(`mcp: ${JSON.stringify(row)}`);
  if (!row.listed) throw new Error(`the MCP server ${SERVER} is not listed in Settings > MCP`);
  if (TOOLS_ROW && !row.connected) throw new Error(`TOOLS_ROW is on but this browser finds ${SERVER} not connected: the connection is not kept on the server`);
  await page.waitForTimeout(DWELL_MS);
  await mark("mcp");
  await page.waitForTimeout(1000);
  await mark("end");
}

// What a take will meet, without sending any prompt: each screen, what it sent (refused when not a read), and the
// answers to the survey's questions. Nothing is typed in the message box.
export async function scout(ctx) {
  const { page, base, step, state } = ctx;
  if (!state.scout) throw new Error("scout() runs only in scout mode");
  let from = 0;
  const part = () => { const p = since(state, from); from = state.requests.length; return p; };
  await step("sign-in", async () => ({ url: page.url().replace(/[?#].*/, ""), ...part() }));
  await step("playground", async () => ({ ...(await playground(page, base)), create_button: Boolean(await firstVisible(page, CREATE)),
                                          words: await wordsOnScreen(page, [/New chat/, /Compare chat/, /Chat history|History|Recent/i]), ...part() }));
  await step("playground-shapes", async () => ({ main: await shapes(page, "main, body", 60) }));
  await step("model", async () => ({ ...(await modelSettings(page, state)), ...part() }));
  await step("model-shapes", async () => ({ panel: await shapes(page, "body", 80) }));
  await step("mcp", async () => ({ tab: await settingsTab(page, "MCP"), row: await mcpRow(page), ...part() }));
  await step("mcp-shapes", async () => ({ panel: await shapes(page, "body", 80) }));
  await step("storage", async () => ({ keys: await read(page, () => ({ local: Object.keys(localStorage).slice(0, 60), session: Object.keys(sessionStorage).slice(0, 60) })),
                                       store_like_requests: state.requests.filter((r) => STORE.test(r.split(" ")[1] || "")).slice(0, 40) }));
  await step("closed", async () => {
    // The message box only (the scout of 2026-11-16 counted another text box: the chat shows a welcome message).
    const box = await firstVisible(page, INPUT.slice(0, 2));
    const typed = box ? ((await box.inputValue().catch(() => null)) ?? (await box.innerText().catch(() => ""))) : "";
    if (typed.trim()) throw new Error("the message box is not empty after the scout");
    noWrites(state, "the scout");
    return { refused: [], requests_seen: state.requests.length };
  });
}

export async function cleanup() {
  return null;
}
