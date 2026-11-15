// WP-286 / ADR-0617: what the walkthroughs of evaluations/browser/record.mjs share. Recorder side only: run.mjs
// (WP-243, the browser check) never imports this file.
//
// Rules every walkthrough follows:
// - Selectors are candidate lists, the first one being what the application showed live, with the date it was seen;
//   scout() reports which candidate matched, so a UI upgrade fails in a scout and not in a take.
// - "On screen" is decided by geometry and a hit test, not by Playwright's `visible`: an application may keep a
//   closed panel in the page, slid away or covered.
// - A take reads the persona's settings and never changes them: no switch, no checkbox, no settings form is clicked.
// - Whatever a take creates, it deletes by id, and says so.

// The first of these selectors that is on screen, or null; the locator carries the selector that matched.
export async function firstVisible(page, selectors) {
  for (const selector of selectors) {
    const found = page.locator(selector).first();
    if (await found.isVisible().catch(() => false)) return Object.assign(found, { matched: selector });
  }
  return null;
}

// True when an element matching the selector can really be seen: inside the viewport and not covered or slid away.
export async function onScreen(page, selector) {
  return page.evaluate((selector) => [...document.querySelectorAll(selector)].some((el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2 || r.right <= 0 || r.bottom <= 0 || r.left >= innerWidth || r.top >= innerHeight) return false;
    const x = Math.min(Math.max(r.left + r.width / 2, 0), innerWidth - 1);
    const y = Math.min(Math.max(r.top + r.height / 2, 0), innerHeight - 1);
    const top = document.elementFromPoint(x, y);
    return Boolean(top) && (el.contains(top) || top.contains(el));
  }), selector);
}

// One call to the application's own API from the page, with the signed-in session: {status, body}. The session token
// (read from localStorage under `tokenKey` when the application keeps one there) never leaves the browser.
export async function pageApi(page, method, path, tokenKey = "token") {
  return page.evaluate(async ([method, path, tokenKey]) => {
    const token = (tokenKey && localStorage.getItem(tokenKey)) || "";
    const r = await fetch(path, { method, credentials: "include", headers: token ? { Authorization: `Bearer ${token}` } : {} });
    let body = null;
    try { body = await r.json(); } catch { /* not JSON */ }
    return { status: r.status, body };
  }, [method, path, tokenKey]);
}

// The lines of text on screen now that were not there before: what a menu just showed.
export async function newText(page, before) {
  const seen = new Set(before.split("\n").map((l) => l.trim()));
  const after = await page.locator("body").innerText();
  return [...new Set(after.split("\n").map((l) => l.trim()).filter((l) => l && !seen.has(l)))].slice(0, 60);
}

// The buttons around an anchor (its nearest ancestor that holds at least three), then every other labelled button on
// screen: what a selector can be built from.
export async function buttons(page, anchor) {
  return page.evaluate((anchor) => {
    const describe = (b) => {
      const r = b.getBoundingClientRect();
      return { id: b.id || "", aria: b.getAttribute("aria-label") || "", title: b.getAttribute("title") || "",
               text: (b.innerText || "").trim().slice(0, 60), x: Math.round(r.left), y: Math.round(r.top),
               on_screen: r.width > 1 && r.height > 1 && r.right > 0 && r.bottom > 0 && r.left < innerWidth && r.top < innerHeight };
    };
    let box = document.querySelector(anchor);
    for (let i = 0; box && i < 10 && box.querySelectorAll("button").length < 3; i += 1) box = box.parentElement;
    const near = box ? [...box.querySelectorAll("button")] : [];
    const others = [...document.querySelectorAll("button")].filter((b) => !near.includes(b) && (b.id || b.getAttribute("aria-label")));
    return { near: near.map(describe), elsewhere: others.map(describe).filter((b) => b.on_screen).slice(0, 60) };
  }, anchor);
}

// The switches on screen ([role=switch]) with their state and the text beside them: [{label, on}]. Read, never clicked.
export async function switches(page) {
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

// Close every open menu ([role=menu]) with Escape; throws when one stays open.
export async function closeMenus(page) {
  for (let i = 0; i < 3 && await page.locator("[role='menu']").first().isVisible().catch(() => false); i += 1) {
    await page.keyboard.press("Escape");
    await page.waitForTimeout(400);
  }
  if (await page.locator("[role='menu']").first().isVisible().catch(() => false)) throw new Error("a menu did not close");
}

// Which of these words (regular expressions) can be read on screen now: {source: true|false}.
export async function wordsOnScreen(page, words) {
  const found = {};
  for (const word of words) found[word.source] = await page.getByText(word).first().isVisible().catch(() => false);
  return found;
}

// The elements on screen that carry a role or are a control (button, link, input), inside `scope` (a selector, the
// whole page by default): tag, id, role, aria-* and data-state attributes, the first classes, 60 characters of text.
// What scout() dumps so a selector is written from the real element, not from a screenshot.
export async function describe(page, scope = "body", limit = 80) {
  return page.evaluate(([scope, limit]) => {
    const root = document.querySelector(scope);
    if (!root) return [];
    return [...root.querySelectorAll("[role], button, a[href], input, textarea, select")].filter((el) => {
      const r = el.getBoundingClientRect();
      return r.width > 1 && r.height > 1 && r.right > 0 && r.bottom > 0 && r.left < innerWidth && r.top < innerHeight;
    }).slice(0, limit).map((el) => {
      const attrs = {};
      for (const a of el.attributes) if (a.name.startsWith("aria-") || a.name === "data-state" || a.name === "type") attrs[a.name] = a.value.slice(0, 80);
      return { tag: el.tagName.toLowerCase(), id: el.id || "", role: el.getAttribute("role") || "", attrs,
               classes: [...el.classList].slice(0, 4), text: (el.innerText || el.value || "").trim().split("\n")[0].slice(0, 60) };
    });
  }, [scope, limit]);
}

// Click, unless the target is a control that changes a setting: a switch, a checkbox, a radio button, or anything
// inside one. A walkthrough that must change one lists it in its exported `changes` and passes that name here; the
// take's guard shows the list. Everything a walkthrough clicks goes through this.
export async function click(locator, { change = "", changes = [], timeout = 15000 } = {}) {
  const setting = await locator.evaluate((el) => {
    const hit = el.closest("[role='switch'], [role='checkbox'], [role='radio'], input[type='checkbox'], input[type='radio']")
      || el.querySelector("[role='switch'], [role='checkbox'], [role='radio'], input[type='checkbox'], input[type='radio']");
    return hit ? (hit.getAttribute("role") || hit.getAttribute("type") || "control") : "";
  }, undefined, { timeout });
  if (setting && !(change && changes.includes(change))) {
    throw new Error(`refused to click a ${setting}: a take never changes the persona's settings (not declared in \`changes\`)`);
  }
  await locator.click({ timeout });
}

// The error messages on screen now: error toasts and alerts, as text. A model refusal (HTTP 429, a quota, an error
// bubble) shows here long before any timeout.
export async function errorsOnScreen(page) {
  return page.evaluate(() => {
    const seen = [];
    for (const el of document.querySelectorAll("[data-sonner-toast][data-type='error'], [role='alert'], .toast-error")) {
      const r = el.getBoundingClientRect();
      const text = (el.innerText || "").trim().replace(/\s+/g, " ");
      if (r.width > 1 && r.height > 1 && text && /\b(429|rate.?limit|quota|too many requests|exceeded|denied|refused|unauthori[sz]ed|forbidden|failed|error)\b/i.test(text)) seen.push(text.slice(0, 200));
    }
    return seen;
  });
}

// Poll until done() returns something other than undefined, and fail AT ONCE when failed() returns a message or an
// error is on screen, instead of waiting out the timeout: a refused model call must not cost three minutes.
export async function waitUntil(page, { what, done, failed = async () => "", timeoutMs = 180000, everyMs = 500 }) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = await done();
    if (value !== undefined) return value;
    const why = (await failed()) || (await errorsOnScreen(page))[0] || "";
    if (why) throw new Error(`${what} was refused or failed: ${why}`);
    await page.waitForTimeout(everyMs);
  }
  throw new Error(`${what} did not finish within ${Math.round(timeoutMs / 1000)} s`);
}

// The lines on screen now that were not in `before`, once the screen has changed and then stayed the same for
// `quietMs` with none of the `busy` selectors visible: an answer that has finished, for an application whose API does
// not say so. Lines equal to one of `ignore` (the prompt just typed) do not count as an answer.
export async function settled(page, { what, before, ignore = [], busy = [], quietMs = 6000, timeoutMs = 180000 }) {
  const old = new Set(before.split("\n").map((l) => l.trim()));
  const skip = new Set(ignore.map((l) => l.trim()));
  let last = null;
  let stableSince = Date.now();
  return waitUntil(page, {
    what, timeoutMs,
    done: async () => {
      const text = await page.locator("body").innerText();
      if (text !== last) { last = text; stableSince = Date.now(); return undefined; }
      const fresh = [...new Set(text.split("\n").map((l) => l.trim()).filter((l) => l && !old.has(l) && !skip.has(l)))];
      if (!fresh.length) return undefined;
      for (const selector of busy) {
        if (await page.locator(selector).first().isVisible().catch(() => false)) { stableSince = Date.now(); return undefined; }
      }
      return Date.now() - stableSince >= quietMs ? fresh : undefined;
    },
  });
}

// ---- Open WebUI: what open-webui and identity-personas share (seen live on 0.12.5, 2026-11-15) ---------------------
export const owui = {
  url: (domain) => `https://open-webui.${domain}`,
  CHAT_ID: /\/c\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/,
  // A link to an earlier chat. The collapsed sidebar of 0.12.5 keeps its buttons (the new-chat pencil stays on the
  // rail) and may keep its chat links in the page: only a link really on screen says the list is open.
  CHAT_LINK: "a[href^='/c/']",
  ANSWER_TIMEOUT_MS: 180000,
};

// The assistant messages of the chat, as its API stores them: [{content, done}], oldest first; null when the
// answer has another shape than expected.
async function owuiAnswers(page, chatId) {
  const got = await pageApi(page, "GET", `/api/v1/chats/${chatId}`).catch(() => null);
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
export async function owuiAnswered(page, chatId, count) {
  let unreadable = 0;
  let last = "";
  let stableSince = Date.now();
  let refused = "";
  return waitUntil(page, {
    what: `answer ${count}`, timeoutMs: owui.ANSWER_TIMEOUT_MS,
    failed: async () => refused,
    done: async () => {
      const list = await owuiAnswers(page, chatId);
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

export async function owuiAsk(page, prompt, state) {
  if (state && state.scout) throw new Error("a scout never types in the chat input");
  const input = page.locator("#chat-input");
  await input.click();
  await page.keyboard.type(prompt, { delay: 25 });
  await page.keyboard.press("Enter");
}

// From a signed-in Open WebUI to the home page of a new chat, sidebar closed, sign-in toast gone. The caller has
// set localStorage `sidebar` to "false" before the first screen (an init script), so earlier chat titles never show.
export async function owuiHome(page, base, { changes = [] } = {}) {
  await page.waitForSelector("#chat-input", { timeout: 60000 });
  if (owui.CHAT_ID.test(page.url())) await page.goto(`${base}/`);   // a new chat: the home page, no chat open
  await page.waitForSelector("#chat-input", { timeout: 60000 });
  await page.waitForTimeout(600);   // the sidebar's own animation, when it has one
  // The toggle is clicked only when an earlier chat is really on screen: on a sidebar already collapsed it would
  // OPEN the list (first live take, 2026-11-15).
  if (await onScreen(page, owui.CHAT_LINK)) {
    const toggle = await firstVisible(page, ["#sidebar-toggle-button", "button[aria-label='Toggle Sidebar']", "button[aria-label='Close Sidebar']"]);
    if (!toggle) throw new Error("the sidebar is open and its toggle button was not found");
    await click(toggle, { changes });
    await page.waitForTimeout(800);
  }
  if (await onScreen(page, owui.CHAT_LINK)) throw new Error("an earlier chat is still listed on screen: the sidebar did not close");
  // The sign-in toast ("You're now logged in.") must be gone before the home marker, or it is in the GIF.
  await page.getByText("You're now logged in").first().waitFor({ state: "hidden", timeout: 20000 });
  await page.getByText("Zuno picks the model").first().waitFor({ timeout: 30000 });
  if (owui.CHAT_ID.test(page.url())) throw new Error("a chat is already open on the home page: the take must start from a new chat");
  await page.waitForTimeout(1000);
}

// What the persona owns in Open WebUI: its chats, by id, every page of the list. Read in its own session; the
// recorder compares the list after sign-in with the list after cleanup, and they must be the same.
export async function owuiChats(page) {
  const found = [];
  for (let n = 1; n <= 50; n += 1) {
    const got = await pageApi(page, "GET", `/api/v1/chats/?page=${n}`);
    if (got.status !== 200 || !Array.isArray(got.body)) throw new Error(`the chat list could not be read (page ${n}: HTTP ${got.status})`);
    const fresh = got.body.filter((c) => c && c.id && !found.some((f) => f.id === c.id));
    if (!fresh.length) break;
    found.push(...fresh.map((c) => ({ kind: "chat", id: String(c.id) })));
  }
  return found;
}

// Delete the chat this take created, by its id, and nothing else: true when it is gone, null when nothing was sent
// (nothing to delete); a failure throws. Nothing sent: nothing to delete. Sent but the id
// was never read (the address bar did not change in time): one more look at the address bar; without an id nothing is
// deleted, and the take says a chat may remain.
export async function owuiDeleteChat(page, state, persona, firstPrompt, log = () => {}) {
  if (!state.sent) return null;
  const id = state.chatId || (page.url().match(owui.CHAT_ID) || [])[1];
  if (!id) {
    throw new Error(`the first question was sent but the chat's id was never read: a chat titled like "${firstPrompt}" `
      + `may remain in ${persona}'s history, check it by hand`);
  }
  if (!state.created.some((c) => c.id === id)) state.created.push({ kind: "chat", id });
  const before = await pageApi(page, "GET", `/api/v1/chats/${id}`).catch(() => null);
  const title = (before && before.body && before.body.title) || "(title not read)";
  const gone = await pageApi(page, "DELETE", `/api/v1/chats/${id}`).catch((e) => ({ status: 0, body: String(e).slice(0, 80) }));
  const after = await pageApi(page, "GET", `/api/v1/chats/${id}`).catch(() => ({ status: 0 }));
  if (gone.status !== 200 || gone.body === false || after.status === 200 || after.status === 0) {
    throw new Error(`the chat "${title}" (${id}) was NOT deleted from ${persona}'s history: DELETE answered HTTP ${gone.status}, `
      + `a read after it HTTP ${after.status}; delete it by hand`);
  }
  log(`chat ${id} deleted ("${title}")`);
  return true;
}

// ---- UnifAI: what unifai-live-rag, unifai-agents, observability-trace and a2a-delegation-approval share ----------
//
// Read from the fork's UI source (ui/client/src, v0.1.72) on 2026-11-15, NOT yet seen live by a scout: every selector
// below is a guess until one. The API paths are the UI's own (/api2/sessions/*, the session cookie, no token).
// A UnifAI session exists from the moment its workflow is chosen in "Add New Chat from Flow" (user.session.create),
// before any question: unifaiNewChat() records its id at once, and unifaiDeleteSession() deletes that id only.
export const unifai = {
  url: (domain) => `https://unifai-ui-zuno-unifai.${domain}`,
  SESSION_ID: /\/agentic-chats\/([A-Za-z0-9_-]{8,})/,
  // The requests a scout refuses: a session created, a prompt submitted, a session deleted or cancelled.
  sends: /\/api2\/sessions\/(user\.session\.(create|submit|execute)|session\.(delete|cancel|approval))/,
  SSO: ["button:has-text('Login using SSO')"],                                            // guess (Login.tsx)
  NAV: { documents: ["a[href='/documents']", "nav >> text=Documents"],                    // guess (Sidebar.tsx)
         chats: ["a[href='/agentic-chats']", "nav >> text=Agentic Chats"] },              // guess (Sidebar.tsx)
  ADD_CHAT: ["button[title='Add new chat from flow']"],                                   // guess (ExecutionTab.tsx)
  DIALOG: "[role='dialog']",                                                              // guess (Radix dialog)
  SEARCH: ["[role='dialog'] input[placeholder='Search workflows...']"],                   // guess (WorkflowsPanel.tsx)
  INPUT: ["main textarea", "textarea"],                                                   // guess (ChatInterface.tsx)
  ANSWER_TIMEOUT_MS: 240000,
};

// Sign in through "Login using SSO" and Keycloak, and wait for the first screen. The `login` marker is the EMPTY
// Keycloak form; nothing is marked once the password is typed.
export async function unifaiSignIn({ page, base, mark, keycloak }, persona) {
  await page.goto(`${base}/`);
  const sso = page.locator(unifai.SSO[0]).first();
  await sso.waitFor({ timeout: 30000 });
  await click(sso);
  await page.waitForSelector("#username", { timeout: 30000 });
  await mark("login");
  await keycloak(persona);
  await page.waitForURL((u) => u.href.startsWith(base), { timeout: 60000 });
  const nav = await waitUntil(page, { what: "UnifAI's first screen", timeoutMs: 60000,
                                      done: async () => (await firstVisible(page, unifai.NAV.chats)) || undefined });
  await page.waitForTimeout(1000);
  return nav.matched;
}

// The persona's own sessions in its Personal workspace, by id, every page of the list: [{kind: "session", id}].
export async function unifaiSessions(page) {
  const found = [];
  for (let offset = 0; offset < 5000; offset += 100) {
    const got = await pageApi(page, "GET", `/api2/sessions/session.user.list?limit=100&offset=${offset}`, "");
    const list = got.body && (Array.isArray(got.body) ? got.body : got.body.sessions);
    if (got.status !== 200 || !Array.isArray(list)) throw new Error(`the session list could not be read (offset ${offset}: HTTP ${got.status})`);
    for (const s of list) if (s && s.session_id && !found.some((f) => f.id === String(s.session_id))) found.push({ kind: "session", id: String(s.session_id) });
    if (Array.isArray(got.body) || !got.body.pagination || !got.body.pagination.has_more || !list.length) break;
  }
  return found;
}

// Go to a page of the sidebar by its link (a click, as the presenter does).
export async function unifaiGo(page, where, { changes = [] } = {}) {
  const link = await firstVisible(page, unifai.NAV[where]);
  if (!link) throw new Error(`the sidebar entry for ${where} was not found (${unifai.NAV[where].join(" | ")})`);
  await click(link, { changes });
  await page.waitForTimeout(800);
  return link.matched;
}

// Open "Add New Chat from Flow" and show the workflow in its list. Returns the dialog and the workflow's row; nothing
// is created yet. The list's entries carry a Human-in-the-Loop switch: it is never clicked (the click guard refuses).
export async function unifaiOpenWorkflows(page, workflow, { changes = [] } = {}) {
  const add = await firstVisible(page, unifai.ADD_CHAT);
  if (!add) throw new Error(`the new-chat button was not found (${unifai.ADD_CHAT.join(" | ")})`);
  await click(add, { changes });
  const dialog = page.locator(unifai.DIALOG).first();
  await dialog.waitFor({ timeout: 15000 });
  const search = await firstVisible(page, unifai.SEARCH);
  if (search) { await search.click(); await page.keyboard.type(workflow, { delay: 20 }); }   // a search box, not a setting
  const row = dialog.getByText(workflow, { exact: true }).first();
  await row.waitFor({ timeout: 15000 });
  return { dialog, row, add: add.matched, search: search ? search.matched : "" };
}

// Create the take's session: choose the workflow and confirm. The id is the answer of UnifAI's own create call, so it
// is this take's session and no other; it is recorded in state.created before anything else happens.
export async function unifaiNewChat(page, workflow, state, { changes = [] } = {}) {
  if (state.scout) throw new Error("a scout never creates a session");
  const { dialog, row } = await unifaiOpenWorkflows(page, workflow, { changes });
  await click(row, { changes });
  state.creating = workflow;   // from here a session may exist even if its id is never read
  const [created] = await Promise.all([
    page.waitForResponse((r) => /\/api2\/sessions\/user\.session\.create/.test(r.url()) && r.request().method() === "POST", { timeout: 60000 }),
    click(dialog.getByRole("button", { name: "Add", exact: true }), { changes }),
  ]);
  const body = await created.json().catch(() => null);
  const id = typeof body === "string" ? body : (body && (body.sessionId || body.session_id)) || "";
  if (created.status() >= 300 || !id) throw new Error(`the session of ${workflow} was not created (HTTP ${created.status()})`);
  state.sessionId = String(id);
  state.created.push({ kind: "session", id: state.sessionId });
  await dialog.waitFor({ state: "hidden", timeout: 15000 });
  await waitUntil(page, { what: "the chat input", timeoutMs: 30000, done: async () => (await firstVisible(page, unifai.INPUT)) || undefined });
  return state.sessionId;
}

export async function unifaiAsk(page, prompt, state) {
  if (state && state.scout) throw new Error("a scout never types in the chat input");
  const input = await firstVisible(page, unifai.INPUT);
  if (!input) throw new Error(`the chat input was not found (${unifai.INPUT.join(" | ")})`);
  await input.click();
  await page.keyboard.type(prompt, { delay: 25 });
  await page.keyboard.press("Enter");
}

// Wait until the session holds `count` assistant messages and is COMPLETED: the text of the last one. A FAILED or
// CANCELLED session, or an error attached to a message (a rate limit, a quota), fails at once with its message.
export async function unifaiAnswered(page, sessionId, count) {
  let refused = "";
  return waitUntil(page, {
    what: `answer ${count}`, timeoutMs: unifai.ANSWER_TIMEOUT_MS, everyMs: 1000,
    failed: async () => refused,
    done: async () => {
      const got = await pageApi(page, "GET", `/api2/sessions/session.chat.get?sessionId=${encodeURIComponent(sessionId)}`, "").catch(() => null);
      if (!got || got.status !== 200 || !got.body) return undefined;
      const messages = (Array.isArray(got.body.messages) ? got.body.messages : []).filter((m) => m && m.role === "assistant");
      const error = messages.map((m) => m.metadata && m.metadata.error).find(Boolean);
      if (error) { refused = String(error.message || error.type || JSON.stringify(error)).slice(0, 200); return undefined; }
      if (got.body.status === "FAILED" || got.body.status === "CANCELLED") {
        refused = `the session is ${got.body.status}: ${String(got.body.status_message || "").slice(0, 160)}`;
        return undefined;
      }
      if (messages.length >= count && got.body.status === "COMPLETED") return String(messages[count - 1].content || "");
      return undefined;
    },
  });
}

// Delete the session this take created, by its id, and nothing else: true when it is gone, null when the take never
// chose a workflow; a failure throws and names the session. A session still running is cancelled first.
export async function unifaiDeleteSession(page, state, persona) {
  if (!state.creating) return null;
  const id = state.sessionId || "";
  if (!id) {
    throw new Error(`the workflow ${state.creating} was chosen but the session's id was never read: a session of `
      + `${state.creating} may remain in ${persona}'s Agentic Chats, check it by hand`);
  }
  if (!state.created.some((c) => c.id === id)) state.created.push({ kind: "session", id });
  const q = `sessionId=${encodeURIComponent(id)}`;
  const status = await pageApi(page, "GET", `/api2/sessions/session.status.get?${q}`, "").catch(() => null);
  if (status && ["PENDING", "QUEUED", "RUNNING"].includes(status.body)) {
    await page.evaluate((id) => fetch("/api2/sessions/session.cancel", { method: "POST", credentials: "include",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sessionId: id }) }).then((r) => r.status).catch(() => 0), id);
    await page.waitForTimeout(1500);
  }
  const gone = await pageApi(page, "DELETE", `/api2/sessions/session.delete?${q}`, "").catch((e) => ({ status: 0, body: String(e).slice(0, 80) }));
  const left = await unifaiSessions(page).catch(() => null);
  if (gone.status !== 200 || !gone.body || gone.body.success !== true || left === null || left.some((s) => s.id === id)) {
    throw new Error(`the session of ${state.creating} (${id}) was NOT deleted from ${persona}'s Agentic Chats: DELETE answered `
      + `HTTP ${gone.status}, ${left === null ? "the list could not be read after it" : "it is still listed"}; delete it by hand`);
  }
  return true;
}
