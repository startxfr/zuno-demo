// WP-284 / ADR-0617: the walkthrough of Open WebUI's 5-minute version, for evaluations/browser/record.mjs.
//
// The rows of docs/demo/scenarios/experiences/open-webui.md, as sale-01: the Keycloak form (login), the home page with
// the sidebar collapsed so no earlier chat title is on screen (home), the 0:45 question (q1-sent, q1-done), the model
// picker on Zuno Code (code-picked) and the 1:45 question (q2-done), the tools panel with sale-01's connection
// "Zuno tools" switched on (tools), the menu closed (end). The prompts are the page's, verbatim (`node record.mjs --check open-webui`).
//
// It costs two model answers and one title on sale-01's budget and creates ONE chat. cleanup() deletes that chat and
// nothing else: its id is read from the address bar after the first send (the take starts from the home page, where
// no chat is open, so the id is the new chat's), and the delete is one call for that id to Open WebUI's own API, in
// the page, with the persona's own session. No list is walked and no menu is clicked, so no other chat can be hit.
// When the delete does not succeed the take fails and names the chat by its title.
import { buttons, click, closeMenus, describe, firstVisible, newText, onScreen, pageApi as api, switches, waitUntil, wordsOnScreen } from "./_helpers.mjs";

export const persona = "sale-01";
export const page = "docs/demo/scenarios/experiences/open-webui.md";
export const viewport = { width: 1280, height: 800 };
export const markers = ["login", "home", "q1-sent", "q1-done", "code-picked", "q2-done", "tools", "end"];
// The first marker a motion segment of the cut may start at: the sign-in (login to home) is never shown as motion.
// `home` is marked after the sign-in toast is gone, so the question being typed may be shown.
export const motion_from = "home";
// The settings this take is allowed to change: none. It reads the tools switch and never clicks it.
export const changes = [];
export const prompts = {
  "0:45": "In one short sentence, say what you can help me with.",
  "1:45": "write Python code that checks the format of an email address",
};
export const url = (domain) => `https://open-webui.${domain}`;

// The buttons the walkthrough opens, as candidates in order (the first is what Open WebUI 0.12.5 showed live on
// 2026-11-15): scout() reports which one matches.
const PICKER = ["#model-selector-model-button", "button[aria-label^='Selected model']", "#model-selector-0-button", "button[aria-label='Select a model']"];
// The Integrations button under the prompt opens a small menu with one row, "Tools 1"; that row opens the panel
// that lists the tool connections. The wrench beside it ("Available Tools", a count) opens nothing.
const TOOLS = ["#integration-menu-button", "button[aria-label='Integrations']"];
const TOOLS_ROW = ["[role='menu'] [role='menuitem']", "[role='menu'] button", "[role='menu'] div"];
const CONNECTION = "Zuno tools";   // the one entry sale-01 sees: the governed connection, with its switch on
const TOOL_WORDS = [/drive/i, /gmail/i, /diagram/i];   // the page's three tool names: reported by scout(), see run()
const CHAT_ID = /\/c\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/;
const ANSWER_TIMEOUT_MS = 180000;
// A link to an earlier chat. The collapsed sidebar of 0.12.5 keeps its buttons (the new-chat pencil stays on the
// rail) and may keep its chat links in the page: only a link really on screen says the list is open.
const CHAT_LINK = "a[href^='/c/']";

// The assistant messages of the chat, as its API stores them: [{content, done}], oldest first; null when the
// answer has another shape than expected.
async function answers(page, chatId) {
  const got = await api(page, "GET", `/api/v1/chats/${chatId}`).catch(() => null);
  const history = got && got.status === 200 && got.body && got.body.chat && got.body.chat.history;
  if (!history || typeof history.messages !== "object") return null;
  return Object.values(history.messages).filter((m) => m && m.role === "assistant")
    .sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0))
    .map((m) => ({ content: String(m.content || ""), done: m.done === true,
                   error: m.error ? String(m.error.content || m.error.message || m.error.detail || JSON.stringify(m.error)).slice(0, 200) : "" }));
}

// Wait until the chat holds `count` finished answers. The chat's API says so (`done`); when it cannot be read, the
// fallback is the screen: the text of the page has not changed for five seconds. A refused model call (an `error`
// on the message, or an error toast: HTTP 429, a quota) fails the take at once, with its message.
async function answered(page, chatId, count) {
  let unreadable = 0;
  let last = "";
  let stableSince = Date.now();
  let refused = "";
  return waitUntil(page, {
    what: `answer ${count}`, timeoutMs: ANSWER_TIMEOUT_MS,
    failed: async () => refused,
    done: async () => {
      const list = await answers(page, chatId);
      if (list === null) unreadable += 1;
      else {
        refused = (list.find((m) => m.error) || {}).error || "";
        if (refused) return undefined;
        if (list.length >= count && list.slice(0, count).every((m) => m.done && m.content.trim())) return list[count - 1].content;
      }
      if (unreadable >= 5) {
        const text = await page.locator("body").innerText();
        if (text !== last) { last = text; stableSince = Date.now(); }
        else if (Date.now() - stableSince >= 5000) return "";
      }
      return undefined;
    },
  });
}

async function ask(page, prompt, state) {
  if (state && state.scout) throw new Error("a scout never types in the chat input");
  const input = page.locator("#chat-input");
  await input.click();
  await page.keyboard.type(prompt, { delay: 25 });
  await page.keyboard.press("Enter");
}

// Open the tools panel: the Integrations button, then the menu's "Tools" row. Returns the selectors that matched.
// Nothing in the panel is clicked: its entries are switches, and a click would turn sale-01's tools off.
async function openToolsPanel(page) {
  const button = await firstVisible(page, TOOLS);
  if (!button) throw new Error(`the tools button under the prompt was not found (${TOOLS.join(" | ")})`);
  await click(button, { changes });
  await page.locator("[role='menu']").first().waitFor({ timeout: 15000 });
  let row = null;
  for (const selector of TOOLS_ROW) {
    const found = page.locator(selector).filter({ hasText: /^\s*Tools(?![A-Za-z])/ }).last();   // last: the innermost match
    if (await found.isVisible().catch(() => false)) { row = Object.assign(found, { matched: `${selector} with text Tools` }); break; }
  }
  if (!row) throw new Error("the Tools row of the Integrations menu was not found");
  await click(row, { changes });
  await page.getByText(CONNECTION, { exact: true }).first().waitFor({ timeout: 15000 });
  return { button: button.matched, row: row.matched };
}

// Sign in and reach the home page of a new chat, sidebar closed, sign-in toast gone: where run() marks `home` and
// where scout() starts looking.
export async function enter({ page, base, mark, keycloak }) {
  // The sidebar is closed before the first screen is drawn: sale-01's earlier chat titles never appear in the take.
  await page.addInitScript(() => { try { localStorage.setItem("sidebar", "false"); } catch { /* another origin */ } });
  await page.goto(`${base}/oauth/oidc/login`);
  await page.waitForSelector("#username", { timeout: 30000 });
  // The marker and its PNG show the EMPTY form: nothing is taken once the password is typed, even masked. The motion
  // a cut may use starts at q1-sent, after the sign-in.
  await mark("login");
  await keycloak(persona);

  await page.waitForSelector("#chat-input", { timeout: 60000 });
  if (CHAT_ID.test(page.url())) await page.goto(`${base}/`);   // a new chat: the home page, no chat open
  await page.waitForSelector("#chat-input", { timeout: 60000 });
  await page.waitForTimeout(600);   // the sidebar's own animation, when it has one
  // The toggle is clicked only when an earlier chat is really on screen: on a sidebar already collapsed it would
  // OPEN the list (first live take, 2026-11-15).
  if (await onScreen(page, CHAT_LINK)) {
    const toggle = await firstVisible(page, ["#sidebar-toggle-button", "button[aria-label='Toggle Sidebar']", "button[aria-label='Close Sidebar']"]);
    if (!toggle) throw new Error("the sidebar is open and its toggle button was not found");
    await click(toggle, { changes });
    await page.waitForTimeout(800);
  }
  if (await onScreen(page, CHAT_LINK)) throw new Error("an earlier chat is still listed on screen: the sidebar did not close");
  // The sign-in toast ("You're now logged in.") must be gone before the home marker, or it is in the GIF.
  await page.getByText("You're now logged in").first().waitFor({ state: "hidden", timeout: 20000 });
  await page.getByText("Zuno picks the model").first().waitFor({ timeout: 30000 });
  if (CHAT_ID.test(page.url())) throw new Error("a chat is already open on the home page: the take must start from a new chat");
  await page.waitForTimeout(1000);
}

// What sale-01 owns in Open WebUI: its chats, by id, every page of the list. Read in its own session; the recorder
// compares the list after sign-in with the list after cleanup, and they must be the same.
export async function owned({ page }) {
  const found = [];
  for (let n = 1; n <= 50; n += 1) {
    const got = await api(page, "GET", `/api/v1/chats/?page=${n}`);
    if (got.status !== 200 || !Array.isArray(got.body)) throw new Error(`the chat list could not be read (page ${n}: HTTP ${got.status})`);
    const fresh = got.body.filter((c) => c && c.id && !found.some((f) => f.id === c.id));
    if (!fresh.length) break;
    found.push(...fresh.map((c) => ({ kind: "chat", id: String(c.id) })));
  }
  return found;
}

export async function run({ page, mark, log, state }) {
  await mark("home");

  state.sent = true;   // from here a chat may exist, even if its id is never read: cleanup() must not stay silent
  await ask(page, prompts["0:45"], state);
  await mark("q1-sent");
  await page.waitForURL(CHAT_ID, { timeout: 60000 });
  state.chatId = page.url().match(CHAT_ID)[1];
  state.created.push({ kind: "chat", id: state.chatId });
  log(`chat ${state.chatId} created`);
  await answered(page, state.chatId, 1);
  await page.waitForTimeout(1500);
  await mark("q1-done");

  const picker = await firstVisible(page, PICKER);
  if (!picker) throw new Error("the model picker was not found");
  await click(picker, { changes });
  await click(page.getByText("Zuno Code", { exact: true }).first(), { changes });
  await page.waitForTimeout(800);
  if (!/Zuno Code/.test(await picker.innerText())) throw new Error("the model picker does not show Zuno Code after the choice");
  await mark("code-picked");
  await ask(page, prompts["1:45"], state);
  const code = await answered(page, state.chatId, 2);
  if (code && !/```[\s\S]*?```/.test(code)) throw new Error("the Zuno Code answer holds no complete code block");
  await page.locator("pre, .cm-editor, code.hljs").first().waitFor({ timeout: 15000 });
  await page.waitForTimeout(1500);
  await mark("q2-done");
  if (page.url().match(CHAT_ID)?.[1] !== state.chatId) throw new Error("the second question opened another chat than the first");

  // The page's row says "Three tools for sale-01: Drive search, Gmail read, diagram generation". Open WebUI 0.12.5
  // does not show tool names here: the panel lists the connection "Zuno tools" with its switch (seen live,
  // 2026-11-15). The moment is that panel, the connection listed and switched on; the switch is never clicked.
  await openToolsPanel(page);
  const found = await switches(page);
  if (found.some((sw) => !sw.on)) throw new Error(`a tool connection is switched off in the tools panel: ${JSON.stringify(found)}`);
  await page.waitForTimeout(800);
  await mark("tools");

  await closeMenus(page);
  await page.waitForTimeout(800);
  await mark("end");
}

// What a take will meet, for the price of a sign-in: the home page, the model picker's menu and the tools panel with
// its connections and their switches. Nothing is typed, no prompt is sent, no switch is clicked, no chat exists
// afterwards.
export async function scout({ page, step, state }) {
  if (!state.scout) throw new Error("scout() runs only in scout mode");
  await step("home", async () => ({ url: page.url().replace(/[?#].*/, ""), chat_link_on_screen: await onScreen(page, CHAT_LINK),
                                    buttons: await buttons(page, "#chat-input") }));
  await step("picker", async () => {
    const before = await page.locator("body").innerText();
    const picker = await firstVisible(page, PICKER);
    if (!picker) throw new Error(`no model picker among ${PICKER.join(" | ")}`);
    const label = (await picker.innerText()).trim();
    const controls = await describe(page);
    await click(picker, { changes });
    await page.waitForTimeout(1000);
    const text = await newText(page, before);
    const now = await describe(page);
    return { selector: picker.matched, label, text, added: now.filter((el) => !controls.some((c) => JSON.stringify(c) === JSON.stringify(el))).slice(0, 40), zuno_code_listed: text.some((l) => l === "Zuno Code"),
             zuno_code_exact_matches: await page.getByText("Zuno Code", { exact: true }).count() };
  });
  await page.keyboard.press("Escape");
  await page.waitForTimeout(500);
  // The panel's entries are switches: the scout reads them and never clicks one (it would turn the tools off).
  await step("tools", async () => {
    const before = await page.locator("body").innerText();
    const matched = await openToolsPanel(page);
    await page.waitForTimeout(800);
    return { selector: matched.button, row_selector: matched.row, text: await newText(page, before),
             menu_text: (await page.locator("[role='menu']").first().innerText().catch(() => "")).split("\n").map((l) => l.trim()).filter(Boolean),
             connection_listed: await page.getByText(CONNECTION, { exact: true }).first().isVisible().catch(() => false),
             switches: await switches(page), menu: await describe(page, "[role='menu']"), tool_words_on_screen: await wordsOnScreen(page, TOOL_WORDS) };
  });
  await closeMenus(page).catch(() => {});
  await step("closed", async () => {
    await page.waitForTimeout(600);
    if (CHAT_ID.test(page.url())) throw new Error("a chat is open after the scout");
    const typed = (await page.locator("#chat-input").innerText().catch(() => "")).trim();
    if (typed) throw new Error("the chat input is not empty after the scout");
    return { url: page.url().replace(/[?#].*/, ""), menu_still_open: await page.locator("[role='menu']").first().isVisible().catch(() => false),
             switches_after: await switches(page) };
  });
}

// Delete the chat this take created, by its id, and nothing else: true when it is gone, null when nothing was sent
// (nothing to delete); a failure throws. Nothing sent: nothing to delete. Sent but the id
// was never read (the address bar did not change in time): one more look at the address bar; without an id nothing is
// deleted, and the take says a chat may remain.
export async function cleanup({ page, log, state }) {
  if (!state.sent) return null;
  const id = state.chatId || (page.url().match(CHAT_ID) || [])[1];
  if (!id) {
    throw new Error(`the first question was sent but the chat's id was never read: a chat titled like "${prompts["0:45"]}" `
      + `may remain in ${persona}'s history, check it by hand`);
  }
  if (!state.created.some((c) => c.id === id)) state.created.push({ kind: "chat", id });
  const before = await api(page, "GET", `/api/v1/chats/${id}`).catch(() => null);
  const title = (before && before.body && before.body.title) || "(title not read)";
  const gone = await api(page, "DELETE", `/api/v1/chats/${id}`).catch((e) => ({ status: 0, body: String(e).slice(0, 80) }));
  const after = await api(page, "GET", `/api/v1/chats/${id}`).catch(() => ({ status: 0 }));
  if (gone.status !== 200 || gone.body === false || after.status === 200 || after.status === 0) {
    throw new Error(`the chat "${title}" (${id}) was NOT deleted from ${persona}'s history: DELETE answered HTTP ${gone.status}, `
      + `a read after it HTTP ${after.status}; delete it by hand`);
  }
  log(`chat ${id} deleted ("${title}")`);
  return true;
}
