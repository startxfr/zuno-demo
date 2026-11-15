// WP-288 / ADR-0618: the walkthrough of "OpenShift Lightspeed", 5-minute version, for evaluations/browser/record.mjs.
//
// The rows of docs/demo/scenarios/experiences/lightspeed.md, as consultant-02 in the OpenShift console: the Keycloak
// form (login), the console's first screen (console), the Lightspeed panel and its prompt box (panel), the 0:45
// question (q1-sent, q1-done), the 2:00 question (q2-done) and the 3:15 question (q3-done), then end. The prompts are
// the page's, verbatim (`node record.mjs --check lightspeed`). The 2:00 and 3:15 prompts are marked untested on the
// page: the take prints the first 300 characters of each answer in its log, so the page's "You should see" cells can
// be set from what was seen; no check is made on their wording.
//
// It signs in through the console's provider chooser (`openshift`, the Keycloak provider) with the persona password
// and nothing else. It costs three answers on the ONE Lightspeed subscription (200,000 tokens per hour, shared by
// every console user and the probe). It creates ONE conversation, on the first question; cleanup() deletes it by the
// id Lightspeed's own answer carried, and nothing else. The known warning "a tool result failed the safety
// inspection" fails the take at once: ask for another take.
//
// It changes no setting: when the console shows its guided tour or any dialog over the page, the take stops and says
// so (dismissing the tour is saved in the user's console settings; that needs a declared change).
//
// NOT yet scouted, and the console plugin's source is not in this repository: EVERY selector and EVERY API path
// below is a guess from the upstream plugin (openshift/lightspeed-console), marked `guess`. scout() reports each one,
// and the plugin's own requests as the browser sees them; no take before a scout that passes.
import { buttons, click, describe, firstVisible, newText, read, switches, waitUntil, wordsOnScreen } from "./_helpers.mjs";

export const persona = "consultant-02";
export const page = "docs/demo/scenarios/experiences/lightspeed.md";
export const viewport = { width: 1280, height: 800 };
export const markers = ["login", "console", "panel", "q1-sent", "q1-done", "q2-done", "q3-done", "end"];
// The provider chooser and the sign-in (up to console) are never shown as motion.
export const motion_from = "console";
export const changes = [];
export const prompts = {
  "0:45": "In one sentence, what is a Pod in OpenShift?",
  "2:00": "Which pods are running in the zuno-ai-run namespace?",
  "3:15": "List the pods in the openshift-etcd namespace.",
};
export const url = (domain) => `https://console-openshift-console.${domain}`;
// The requests a scout refuses: a question, a conversation deleted, a feedback. Opening the panel may POST
// `/authorized`: that one is let through.
export const sends = /\/ols\/v1\/(streaming_query|query|feedback|conversations)(\/|\?|$)/;   // guess

const PROVIDER = "openshift";   // the page: log in with `openshift` (the Keycloak provider), not startx-htpasswd_auth
const PROVIDER_LINK = [`a[title='Log in with ${PROVIDER}']`, `a.idp:text-is('${PROVIDER}')`, `a:text-is('${PROVIDER}')`];   // guess
const OLS = "/api/proxy/plugin/lightspeed-console-plugin/ols";                                                             // guess
const OPEN = ["[data-test='ols-plugin__popover-button']", ".ols-plugin__popover-button", "button[aria-label*='Lightspeed' i]"];   // guess
const PANEL = ["[data-test='ols-plugin__popover']", ".ols-plugin__popover", "[class*='ols-plugin__popover']:not(button)"];       // guess
const INPUT = [".ols-plugin__popover textarea", "[class*='ols-plugin'] textarea", "textarea[placeholder*='message' i]"];        // guess
const ENTRY = [".ols-plugin__chat-entry--ai", "[class*='chat-entry--ai']", "[class*='ols-plugin__chat-entry']"];                // guess: an answer
const DIALOG = "[role='dialog'][aria-modal='true'], .pf-v5-c-backdrop, .pf-v6-c-backdrop";                                       // guess: the guided tour
const QUERY = /\/ols\/v1\/(streaming_query|query)(\?|$)/;                                                                       // guess
const SAFETY = /failed the safety inspection|stopped the operation/i;   // the known warning (page, Start section)
const ANSWER_TIMEOUT_MS = 180000;

// One call to Lightspeed's API through the console's proxy, in the page, with the console's own CSRF token (cookie
// `csrf-token`, header X-CSRFToken: the console refuses a write without it).
async function ols(page, method, path) {
  const run = method === "GET" ? (fn, arg) => read(page, fn, arg) : (fn, arg) => page.evaluate(fn, arg);   // only a GET is read again
  return run(async ([method, url]) => {
    const csrf = (document.cookie.split("; ").find((c) => c.startsWith("csrf-token=")) || "").slice("csrf-token=".length);
    const r = await fetch(url, { method, credentials: "include", headers: csrf ? { "X-CSRFToken": csrf } : {} });
    let body = null;
    try { body = await r.json(); } catch { /* not JSON */ }
    return { status: r.status, body };
  }, [method, `${OLS}${path}`]);
}

const listed = (body) => (Array.isArray(body) ? body : body && Array.isArray(body.conversations) ? body.conversations : null);

async function conversations(page) {
  const got = await ols(page, "GET", "/v1/conversations").catch(() => ({ status: 0, body: null }));
  const list = listed(got.body);
  if (got.status !== 200 || !list) throw new Error(`the conversation list could not be read (${OLS}/v1/conversations: HTTP ${got.status})`);
  return list.map((c) => c && (c.conversation_id || c.id)).filter(Boolean).map(String);
}

// Open the Lightspeed panel and wait for its prompt box: the selectors that matched.
async function openPanel(page) {
  const open = await firstVisible(page, OPEN);
  if (!open) throw new Error(`the Lightspeed button was not found (${OPEN.join(" | ")})`);
  await click(open, { changes });
  const input = await waitUntil(page, { what: "the Lightspeed prompt box", timeoutMs: 30000, done: async () => (await firstVisible(page, INPUT)) || undefined });
  await page.waitForTimeout(800);
  return { open: open.matched, input: input.matched };
}

// Ask one question and wait until Lightspeed's own answer stream has ended: {text, conversation}. An HTTP error (a
// quota: 429) or the safety warning fails at once.
async function answer(page, prompt, state, what) {
  if (state.scout) throw new Error("a scout never types in the prompt box");
  const input = await firstVisible(page, INPUT);
  if (!input) throw new Error(`the Lightspeed prompt box was not found (${INPUT.join(" | ")})`);
  const before = await page.locator("body").innerText();
  const sent = page.waitForResponse((r) => QUERY.test(r.url()) && r.request().method() === "POST", { timeout: 60000 });
  sent.catch(() => {});
  await input.click();
  await page.keyboard.type(prompt, { delay: 25 });
  await page.keyboard.press("Enter");
  if (state.afterSend) { await state.afterSend(); state.afterSend = null; }
  const response = await sent.catch(() => { throw new Error(`${what}: no request to Lightspeed's query API was seen after Enter (${QUERY.source})`); });
  if (response.status() >= 400) {
    if (!state.conversationId) state.sent = false;   // the first question was refused: no conversation was created
    throw new Error(`${what} was refused or failed: HTTP ${response.status()} from Lightspeed`);
  }
  const ended = await Promise.race([response.finished(), new Promise((r) => setTimeout(() => r("timeout"), ANSWER_TIMEOUT_MS))]);
  if (ended === "timeout") throw new Error(`${what} did not finish within ${ANSWER_TIMEOUT_MS / 1000} s`);
  const stream = await response.text().catch(() => "");
  const posted = (() => { try { return JSON.parse(response.request().postData() || "{}"); } catch { return {}; } })();
  const conversation = (stream.match(/"conversation_id"\s*:\s*"([^"]+)"/) || [])[1] || posted.conversation_id || "";
  // Recorded before any check on the answer: a first answer that fails below has still created its conversation.
  if (conversation && !state.conversationId) {
    state.conversationId = conversation;
    state.created.push({ kind: "conversation", id: conversation });
  }
  await page.waitForTimeout(1500);   // the last tokens drawn
  const entry = await firstVisible(page, ENTRY);
  const text = entry ? (await page.locator(entry.matched).last().innerText()).trim() : (await newText(page, before)).filter((l) => l !== prompt).join("\n");
  if (SAFETY.test(text) || SAFETY.test(await page.locator("body").innerText())) {
    throw new Error(`${what} was refused or failed: Lightspeed stopped on its safety inspection (a known warning, take again)`);
  }
  if (!text) throw new Error(`${what} is empty on screen`);
  return { text, conversation };
}

// Sign in through the console's provider chooser and Keycloak, and reach the console with no dialog over it.
export async function enter({ page, base, mark, keycloak }) {
  await page.goto(`${base}/`);
  const provider = await waitUntil(page, { what: "the console's sign-in page", timeoutMs: 60000,
    done: async () => (await firstVisible(page, [...PROVIDER_LINK, "#username"])) || undefined });
  if (provider.matched !== "#username") await click(provider, { changes });
  await page.waitForSelector("#username", { timeout: 30000 });
  await mark("login");   // the EMPTY Keycloak form: nothing is marked once the password is typed
  await keycloak(persona);
  await page.waitForURL((u) => u.href.startsWith(base), { timeout: 60000 });
  await waitUntil(page, { what: "the console and its Lightspeed button", timeoutMs: 90000, done: async () => (await firstVisible(page, OPEN)) || undefined });
  await page.waitForLoadState("networkidle", { timeout: 60000 }).catch(() => {});
  await page.waitForTimeout(1500);
}

export async function owned({ page }) {
  return (await conversations(page)).map((id) => ({ kind: "conversation", id }));
}

export async function run({ page, mark, log, state }) {
  if (await page.locator(DIALOG).first().isVisible().catch(() => false)) {
    throw new Error("a dialog covers the console (its guided tour?): a take dismisses nothing that is saved in the user's settings; see scout step console");
  }
  await mark("console");

  await openPanel(page);
  if (await firstVisible(page, ENTRY)) throw new Error("the Lightspeed panel already shows a conversation: the take must start from an empty one");
  await mark("panel");

  state.sent = true;   // from here a conversation may exist, even if its id is never read: cleanup() must not stay silent
  state.afterSend = () => mark("q1-sent");
  const first = await answer(page, prompts["0:45"], state, "answer 1");
  if (!state.conversationId) throw new Error("Lightspeed's first answer carried no conversation id");
  log(`conversation ${state.conversationId} created`);
  log(`answer 1 (${first.text.length} chars): ${first.text.replace(/\s+/g, " ").slice(0, 300)}`);
  await mark("q1-done");

  const second = await answer(page, prompts["2:00"], state, "answer 2");
  log(`answer 2 (${second.text.length} chars): ${second.text.replace(/\s+/g, " ").slice(0, 300)}`);
  if (second.conversation && second.conversation !== state.conversationId) throw new Error("the second question opened another conversation than the first");
  await mark("q2-done");

  const third = await answer(page, prompts["3:15"], state, "answer 3");
  log(`answer 3 (${third.text.length} chars): ${third.text.replace(/\s+/g, " ").slice(0, 300)}`);
  if (third.conversation && third.conversation !== state.conversationId) throw new Error("the third question opened another conversation than the first");
  await mark("q3-done");

  await page.waitForTimeout(800);
  await mark("end");
}

// What a take will meet, for the price of a sign-in: the console's first screen (a dialog over it?), the Lightspeed
// button, the panel and its prompt box, the plugin's own requests, and what the conversation API answers. Nothing is
// typed, no question is sent, no dialog is dismissed, no conversation exists afterwards.
export async function scout({ page, step, state }) {
  if (!state.scout) throw new Error("scout() runs only in scout mode");
  const seen = [];
  page.on("request", (r) => { if (/lightspeed|\/ols\//i.test(r.url())) seen.push(`${r.method()} ${new URL(r.url()).pathname}`); });
  let before = null;
  await step("conversations-api", async () => {
    const got = await ols(page, "GET", "/v1/conversations").catch(() => ({ status: 0, body: null }));
    const list = listed(got.body);
    before = list ? list.length : null;
    // The shape only: field names, never a conversation's topic or content.
    return { path: `${OLS}/v1/conversations`, status: got.status, top_keys: got.body && !Array.isArray(got.body) ? Object.keys(got.body).slice(0, 12) : [],
             count: before, conversation_keys: list && list[0] ? Object.keys(list[0]).slice(0, 20) : [],
             csrf_cookie: await read(page, () => document.cookie.split("; ").some((c) => c.startsWith("csrf-token="))) };
  });
  await step("console", async () => ({ url: page.url().replace(/[?#].*/, ""), dialog_on_screen: await page.locator(DIALOG).first().isVisible().catch(() => false),
                                       dialog_text: (await page.locator(DIALOG).first().innerText().catch(() => "")).split("\n").map((l) => l.trim()).filter(Boolean).slice(0, 12),
                                       button_selector: ((await firstVisible(page, OPEN)) || {}).matched || "",
                                       words: await wordsOnScreen(page, [/consultant-02/, /Cluster ID/, /Skip tour/, /Get started/]) }));
  await step("panel", async () => {
    const text = await page.locator("body").innerText();
    const matched = await openPanel(page);
    const input = page.locator(matched.input).first();
    return { button_selector: matched.open, input_selector: matched.input, input_placeholder: (await input.getAttribute("placeholder")) || "",
             panel_selector: ((await firstVisible(page, PANEL)) || {}).matched || "", earlier_answers: await page.locator(ENTRY.join(", ")).count(),
             text: (await newText(page, text)).slice(0, 30), switches: await switches(page), buttons: await buttons(page, matched.input),
             controls: await describe(page, ((await firstVisible(page, PANEL)) || {}).matched || "body", 60), requests_seen: [...new Set(seen)].slice(0, 30) };
  });
  await step("closed", async () => {
    const input = await firstVisible(page, INPUT);
    const typed = input ? (await input.inputValue().catch(() => "")).trim() : "";
    if (typed) throw new Error("the prompt box is not empty after the scout");
    const after = before === null ? null : (await conversations(page)).length;
    if (before !== null && after !== before) throw new Error(`${persona} owns ${after} conversations after the scout, ${before} before it`);
    return { url: page.url().replace(/[?#].*/, ""), conversations: after, requests_seen: [...new Set(seen)].slice(0, 30) };
  });
}

// Delete the conversation this take created, by its id, and nothing else: true when it is gone, null when nothing was
// sent; a failure throws. Sent but no id read: nothing is deleted, and the take says a conversation may remain.
export async function cleanup({ page, log, state }) {
  if (!state.sent) return null;
  const id = state.conversationId || "";
  if (!id) {
    throw new Error(`the first question was sent but the conversation's id was never read: a conversation starting with `
      + `"${prompts["0:45"]}" may remain for ${persona} in Lightspeed, check it by hand`);
  }
  if (!state.created.some((c) => c.id === id)) state.created.push({ kind: "conversation", id });
  const gone = await ols(page, "DELETE", `/v1/conversations/${encodeURIComponent(id)}`).catch((e) => ({ status: 0, body: String(e).slice(0, 80) }));
  const left = await conversations(page).catch(() => null);
  if (gone.status < 200 || gone.status >= 300 || left === null || left.includes(id)) {
    throw new Error(`the conversation ${id} was NOT deleted from ${persona}'s Lightspeed history: DELETE answered HTTP ${gone.status}, `
      + `${left === null ? "the list could not be read after it" : "it is still listed"}; delete it by hand`);
  }
  log(`conversation ${id} deleted`);
  return true;
}
