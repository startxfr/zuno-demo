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
export const persona = "sale-01";
export const page = "docs/demo/scenarios/experiences/open-webui.md";
export const viewport = { width: 1280, height: 800 };
export const markers = ["login", "home", "q1-sent", "q1-done", "code-picked", "q2-done", "tools", "end"];
// The first marker a motion segment of the cut may start at: the sign-in (login to home) is never shown as motion.
export const motion_from = "q1-sent";
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

// One call to Open WebUI's API from the page, with the signed-in session. The token stays in the browser.
async function api(page, method, path) {
  return page.evaluate(async ([method, path]) => {
    const token = localStorage.getItem("token") || "";
    const r = await fetch(path, { method, credentials: "include", headers: token ? { Authorization: `Bearer ${token}` } : {} });
    let body = null;
    try { body = await r.json(); } catch { /* not JSON */ }
    return { status: r.status, body };
  }, [method, path]);
}

// The assistant messages of the chat, as its API stores them: [{content, done}], oldest first; null when the
// answer has another shape than expected.
async function answers(page, chatId) {
  const got = await api(page, "GET", `/api/v1/chats/${chatId}`).catch(() => null);
  const history = got && got.status === 200 && got.body && got.body.chat && got.body.chat.history;
  if (!history || typeof history.messages !== "object") return null;
  return Object.values(history.messages).filter((m) => m && m.role === "assistant")
    .sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0))
    .map((m) => ({ content: String(m.content || ""), done: m.done === true }));
}

// Wait until the chat holds `count` finished answers. The chat's API says so (`done`); when it cannot be read, the
// fallback is the screen: the text of the page has not changed for five seconds.
async function answered(page, chatId, count) {
  const deadline = Date.now() + ANSWER_TIMEOUT_MS;
  let unreadable = 0;
  let last = "";
  let stableSince = Date.now();
  while (Date.now() < deadline) {
    const list = await answers(page, chatId);
    if (list === null) unreadable += 1;
    else if (list.length >= count && list.slice(0, count).every((m) => m.done && m.content.trim())) return list[count - 1].content;
    if (unreadable >= 5) {
      const text = await page.locator("body").innerText();
      if (text !== last) { last = text; stableSince = Date.now(); }
      else if (Date.now() - stableSince >= 5000) return "";
    }
    await page.waitForTimeout(500);
  }
  throw new Error(`answer ${count} did not finish within ${ANSWER_TIMEOUT_MS / 1000} s`);
}

async function ask(page, prompt, state) {
  if (state && state.scout) throw new Error("a scout never types in the chat input");
  const input = page.locator("#chat-input");
  await input.click();
  await page.keyboard.type(prompt, { delay: 25 });
  await page.keyboard.press("Enter");
}

// The first of these selectors that is on screen, or null; the locator carries the selector that matched.
async function firstVisible(page, selectors) {
  for (const selector of selectors) {
    const found = page.locator(selector).first();
    if (await found.isVisible().catch(() => false)) return Object.assign(found, { matched: selector });
  }
  return null;
}

// True when a link to an earlier chat can really be seen: inside the viewport and not covered or slid away. The
// collapsed sidebar of 0.12.5 keeps its buttons (the new-chat pencil stays on the rail) and may keep its chat links in
// the page, so neither a button nor Playwright's "visible" says whether the list is open.
async function chatLinkOnScreen(page) {
  return page.evaluate(() => [...document.querySelectorAll("a[href^='/c/']")].some((a) => {
    const r = a.getBoundingClientRect();
    if (r.width < 2 || r.height < 2 || r.right <= 0 || r.bottom <= 0 || r.left >= innerWidth || r.top >= innerHeight) return false;
    const x = Math.min(Math.max(r.left + r.width / 2, 0), innerWidth - 1);
    const y = Math.min(Math.max(r.top + r.height / 2, 0), innerHeight - 1);
    const top = document.elementFromPoint(x, y);
    return Boolean(top) && (a.contains(top) || top.contains(a));
  }));
}

// Open the tools panel: the Integrations button, then the menu's "Tools" row. Returns the selectors that matched.
// Nothing in the panel is clicked: its entries are switches, and a click would turn sale-01's tools off.
async function openToolsPanel(page) {
  const button = await firstVisible(page, TOOLS);
  if (!button) throw new Error(`the tools button under the prompt was not found (${TOOLS.join(" | ")})`);
  await button.click();
  await page.locator("[role='menu']").first().waitFor({ timeout: 15000 });
  let row = null;
  for (const selector of TOOLS_ROW) {
    const found = page.locator(selector).filter({ hasText: /^\s*Tools(?![A-Za-z])/ }).last();   // last: the innermost match
    if (await found.isVisible().catch(() => false)) { row = Object.assign(found, { matched: `${selector} with text Tools` }); break; }
  }
  if (!row) throw new Error("the Tools row of the Integrations menu was not found");
  await row.click();
  await page.getByText(CONNECTION, { exact: true }).first().waitFor({ timeout: 15000 });
  return { button: button.matched, row: row.matched };
}

// The switches on screen ([role=switch]) with their state and the text beside them: [{label, on}].
async function connectionSwitches(page) {
  return page.evaluate(() => [...document.querySelectorAll("[role='switch']")].filter((sw) => {
    const r = sw.getBoundingClientRect();
    return r.width > 1 && r.height > 1;
  }).map((sw) => {
    let box = sw.parentElement;
    for (let i = 0; box && i < 4 && !(box.innerText || "").trim(); i += 1) box = box.parentElement;
    return { label: ((box && box.innerText) || "").trim().split("\n")[0].slice(0, 60),
             on: sw.getAttribute("aria-checked") === "true" || sw.getAttribute("data-state") === "checked" };
  }));
}

async function closeMenus(page) {
  for (let i = 0; i < 3 && await page.locator("[role='menu']").first().isVisible().catch(() => false); i += 1) {
    await page.keyboard.press("Escape");
    await page.waitForTimeout(400);
  }
  if (await page.locator("[role='menu']").first().isVisible().catch(() => false)) throw new Error("the tools menu did not close");
}

// Sign in and reach the home page of a new chat, sidebar closed, sign-in toast gone: where run() marks `home` and
// where scout() starts looking.
async function home({ page, base, mark, keycloak }) {
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
  if (await chatLinkOnScreen(page)) {
    const toggle = await firstVisible(page, ["#sidebar-toggle-button", "button[aria-label='Toggle Sidebar']", "button[aria-label='Close Sidebar']"]);
    if (!toggle) throw new Error("the sidebar is open and its toggle button was not found");
    await toggle.click();
    await page.waitForTimeout(800);
  }
  if (await chatLinkOnScreen(page)) throw new Error("an earlier chat is still listed on screen: the sidebar did not close");
  // The sign-in toast ("You're now logged in.") must be gone before the home marker, or it is in the GIF.
  await page.getByText("You're now logged in").first().waitFor({ state: "hidden", timeout: 20000 });
  await page.getByText("Zuno picks the model").first().waitFor({ timeout: 30000 });
  if (CHAT_ID.test(page.url())) throw new Error("a chat is already open on the home page: the take must start from a new chat");
  await page.waitForTimeout(1000);
}

export async function run({ page, base, mark, log, keycloak, state }) {
  await home({ page, base, mark, keycloak });
  await mark("home");

  state.sent = true;   // from here a chat may exist, even if its id is never read: cleanup() must not stay silent
  await ask(page, prompts["0:45"], state);
  await mark("q1-sent");
  await page.waitForURL(CHAT_ID, { timeout: 60000 });
  state.chatId = page.url().match(CHAT_ID)[1];
  log(`chat ${state.chatId} created`);
  await answered(page, state.chatId, 1);
  await page.waitForTimeout(1500);
  await mark("q1-done");

  const picker = await firstVisible(page, PICKER);
  if (!picker) throw new Error("the model picker was not found");
  await picker.click();
  await page.getByText("Zuno Code", { exact: true }).first().click({ timeout: 15000 });
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
  const switches = await connectionSwitches(page);
  if (switches.some((sw) => !sw.on)) throw new Error(`a tool connection is switched off in the tools panel: ${JSON.stringify(switches)}`);
  await page.waitForTimeout(800);
  await mark("tools");

  await closeMenus(page);
  await page.waitForTimeout(800);
  await mark("end");
}

// The lines of text on screen now that were not there before: what a menu just showed.
async function newText(page, before) {
  const seen = new Set(before.split("\n").map((l) => l.trim()));
  const after = await page.locator("body").innerText();
  return [...new Set(after.split("\n").map((l) => l.trim()).filter((l) => l && !seen.has(l)))].slice(0, 60);
}

// The buttons around the prompt box (the nearest ancestor of #chat-input that holds at least three), then every
// other labelled button on screen: what a selector can be built from.
async function buttons(page) {
  return page.evaluate(() => {
    const describe = (b) => {
      const r = b.getBoundingClientRect();
      return { id: b.id || "", aria: b.getAttribute("aria-label") || "", title: b.getAttribute("title") || "",
               text: (b.innerText || "").trim().slice(0, 60), x: Math.round(r.left), y: Math.round(r.top),
               on_screen: r.width > 1 && r.height > 1 && r.right > 0 && r.bottom > 0 && r.left < innerWidth && r.top < innerHeight };
    };
    let box = document.querySelector("#chat-input");
    for (let i = 0; box && i < 10 && box.querySelectorAll("button").length < 3; i += 1) box = box.parentElement;
    const near = box ? [...box.querySelectorAll("button")] : [];
    const others = [...document.querySelectorAll("button")].filter((b) => !near.includes(b) && (b.id || b.getAttribute("aria-label")));
    return { prompt_box: near.map(describe), elsewhere: others.map(describe).filter((b) => b.on_screen).slice(0, 60) };
  });
}

// What a take will meet, for the price of a sign-in: the home page, the model picker's menu and the tools panel with
// its connections and their switches. Nothing is typed, no prompt is sent, no switch is clicked, no chat exists
// afterwards.
export async function scout({ page, base, keycloak, step, state, mark }) {
  if (!state.scout) throw new Error("scout() runs only in scout mode");
  const entered = await step("home", async () => {
    await home({ page, base, mark, keycloak });
    return { url: page.url().replace(/[?#].*/, ""), chat_link_on_screen: await chatLinkOnScreen(page), buttons: await buttons(page) };
  });
  if (!entered.ok) return;
  await step("picker", async () => {
    const before = await page.locator("body").innerText();
    const picker = await firstVisible(page, PICKER);
    if (!picker) throw new Error(`no model picker among ${PICKER.join(" | ")}`);
    const label = (await picker.innerText()).trim();
    await picker.click();
    await page.waitForTimeout(1000);
    const text = await newText(page, before);
    return { selector: picker.matched, label, text, zuno_code_listed: text.some((l) => l === "Zuno Code"),
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
             switches: await connectionSwitches(page), tool_words_on_screen: await wordsOnScreen(page) };
  });
  await closeMenus(page).catch(() => {});
  await step("closed", async () => {
    await page.waitForTimeout(600);
    if (CHAT_ID.test(page.url())) throw new Error("a chat is open after the scout");
    const typed = (await page.locator("#chat-input").innerText().catch(() => "")).trim();
    if (typed) throw new Error("the chat input is not empty after the scout");
    return { url: page.url().replace(/[?#].*/, ""), menu_still_open: await page.locator("[role='menu']").first().isVisible().catch(() => false),
             switches_after: await connectionSwitches(page) };
  });
}

// Which of the page's three tool words can be read on screen now.
async function wordsOnScreen(page) {
  const found = {};
  for (const word of TOOL_WORDS) found[word.source] = await page.getByText(word).first().isVisible().catch(() => false);
  return found;
}

// Delete the chat this take created, by its id, and nothing else. Nothing sent: nothing to delete. Sent but the id
// was never read (the address bar did not change in time): one more look at the address bar; without an id nothing is
// deleted, and the take says a chat may remain.
export async function cleanup({ page, log, state }) {
  if (!state.sent) return { chat_deleted: false };
  const id = state.chatId || (page.url().match(CHAT_ID) || [])[1];
  if (!id) {
    throw new Error(`the first question was sent but the chat's id was never read: a chat titled like "${prompts["0:45"]}" `
      + `may remain in ${persona}'s history, check it by hand`);
  }
  const before = await api(page, "GET", `/api/v1/chats/${id}`).catch(() => null);
  const title = (before && before.body && before.body.title) || "(title not read)";
  const gone = await api(page, "DELETE", `/api/v1/chats/${id}`).catch((e) => ({ status: 0, body: String(e).slice(0, 80) }));
  const after = await api(page, "GET", `/api/v1/chats/${id}`).catch(() => ({ status: 0 }));
  if (gone.status !== 200 || gone.body === false || after.status === 200 || after.status === 0) {
    throw new Error(`the chat "${title}" (${id}) was NOT deleted from ${persona}'s history: DELETE answered HTTP ${gone.status}, `
      + `a read after it HTTP ${after.status}; delete it by hand`);
  }
  log(`chat ${id} deleted ("${title}")`);
  return { chat_deleted: true };
}
