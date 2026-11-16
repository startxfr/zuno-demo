// WP-290 / ADR-0618: the walkthrough of "OpenClaw", 5-minute version, for evaluations/browser/record.mjs.
//
// The rows of docs/demo/scenarios/experiences/openclaw.md, as consultant-02 on its own assistant: the Keycloak form
// of the front door (login), the Control UI connected (ui, row 0:00), a new session (session), the page's question
// (q-sent) and its answer with the Confluence tool line (q-done, row 0:45), then end. Rows 2:30 to 4:15 are words.
// The prompt is the page's, verbatim (`node record.mjs --check openclaw`).
//
// TWO credentials (the owner's decision of 2026-11-16, "like guardrails"): the persona password at the front door,
// and the Control UI's own password (Secret openclaw-ui of zuno-claw-consultant-02), held by the recorder
// (`secrets`) and typed by it into the Control UI's one field, masked: the browser check fills that field by its
// placeholder "optional" and it may be a plain text field, so the recorder masks it before typing and refuses to
// type if it cannot. Nothing is marked or described while it is being filled.
//
// NOT TAKEN YET, on purpose. The Control UI talks to its gateway over a WebSocket: there is no list or delete this
// file can call as the persona, and the assistant keeps a memory of its own. So what a take would leave (one session
// in consultant-02's assistant, and whatever the assistant memorises) cannot be removed by any means known today.
// run() therefore refuses to start (`DELETE`: how a session is deleted, unknown) until a scout has shown the session
// list's controls and the owner has decided. scout() does everything up to the connected Control UI and describes
// it; it sends nothing, opens no session, and stores no session title.
import { click, describe, firstVisible, newText, read, settled, waitUntil, wordsOnScreen } from "./_helpers.mjs";

export const persona = "consultant-02";
export const secrets = ["OPENCLAW_UI_PASSWORD"];
export const page = "docs/demo/scenarios/experiences/openclaw.md";
export const viewport = { width: 1280, height: 800 };
export const markers = ["login", "ui", "session", "q-sent", "q-done", "end"];
export const motion_from = "ui";
export const changes = [];
export const prompts = { "0:45": "Cherche dans Confluence les pages d'onboarding" };
export const url = (domain) => `https://assistant-zuno-claw-${persona}.${domain}`;
// The Control UI sends its messages over a WebSocket, which a request filter does not see: a scout sends nothing
// because scout() never types. An HTTP call that would create a session or send a message is refused all the same
// (guess: none is known).
export const sends = /\/api\/[^?]*(sessions?|messages?|chat)\b/i;

// How the take deletes the session it created: unknown until a scout (see the header). null: run() refuses.
const DELETE = null;
const UI_PASSWORD = ["input[placeholder='optional' i]"];                                  // seen by the browser check (run.mjs)
const CONNECT = ["button:has-text('Connect')"];                                           // seen by the browser check
const NEW_SESSION = ["button:has-text('New session')", "a:has-text('New session')", "button:has-text('Nouvelle session')"];   // guess (the page's row 0:00)
const INPUT = ["textarea", "[contenteditable='true']"];                                   // guess
const TOOL = /Confluence-page-search/i;                                                   // the page's row 0:45
const ANSWER_TIMEOUT_MS = 240000;

export async function enter({ page, base, mark, keycloak, typeSecret, state }) {
  await page.goto(`${base}/`);
  await page.waitForSelector("#username", { timeout: 30000 });
  await mark("login");   // the EMPTY Keycloak form: nothing is marked once a password is typed
  await keycloak(persona);
  // The Control UI, not connected yet: its password field and Connect. Nothing is described while it is filled.
  const field = await waitUntil(page, { what: "the Control UI behind the front door", timeoutMs: 90000,
    done: async () => (page.url().startsWith(base) && (await firstVisible(page, UI_PASSWORD))) || undefined });
  const keys = () => read(page, () => Object.keys(localStorage).map((k) => "local:" + k).concat(Object.keys(sessionStorage).map((k) => "session:" + k))).catch(() => []);
  const before = await keys();
  await typeSecret(page.locator(field.matched).last(), "OPENCLAW_UI_PASSWORD");
  const connect = await firstVisible(page, CONNECT);
  if (!connect) throw new Error(`the Control UI's Connect button was not found (${CONNECT.join(" | ")})`);
  await click(connect, { changes });
  await waitUntil(page, { what: "the Control UI connected to its gateway", timeoutMs: 60000, done: async () => {
    if (/Could not connect/i.test(await page.locator("body").innerText().catch(() => ""))) throw new Error("the Control UI could not connect to its gateway with its password");
    return (await firstVisible(page, NEW_SESSION)) || undefined;
  } });
  await page.waitForTimeout(1500);
  // What the Control UI keeps in the browser after Connect, by name only (a kept password would be one of these).
  state.storage_added = (await keys()).filter((k) => !before.includes(k));
  state.password_field_still_on_screen = Boolean(await firstVisible(page, UI_PASSWORD));
}

// Nothing this file can list as the persona (a WebSocket, see the header).
export async function owned() {
  return [];
}

export async function run({ page, mark, log, state }) {
  if (!DELETE) {
    throw new Error("openclaw is not taken yet: a take would leave a session (and the assistant's memory of it) that nothing known can delete; "
      + "scout it, then the owner decides (walkthrough header)");
  }
  if (state.password_field_still_on_screen) throw new Error("the Control UI still shows its password field after Connect: it must not be in a picture");
  await mark("ui");
  const fresh = await firstVisible(page, NEW_SESSION);
  await click(fresh, { changes });
  await waitUntil(page, { what: "the message box", timeoutMs: 20000, done: async () => (await firstVisible(page, INPUT)) || undefined });
  await page.waitForTimeout(800);
  await mark("session");
  const before = await page.locator("body").innerText();
  const input = await firstVisible(page, INPUT);
  state.sent = true;
  await input.click();
  await page.keyboard.type(prompts["0:45"], { delay: 25 });
  await page.keyboard.press("Enter");
  await waitUntil(page, { what: "the question in the session", timeoutMs: 20000, done: async () => (await newText(page, before)).some((line) => line.includes(prompts["0:45"])) || undefined });
  await mark("q-sent");
  const answer = await settled(page, { what: "the answer", before, ignore: [prompts["0:45"]], quietMs: 8000, timeoutMs: ANSWER_TIMEOUT_MS });
  if (!answer.some((line) => TOOL.test(line))) throw new Error("the answer shows no Zuno Confluence-page-search tool line: not the page's row 0:45");
  log(`answer: ${answer.length} new lines, the tool line is on screen`);
  await page.waitForTimeout(1000);
  await mark("q-done");
  await page.waitForTimeout(800);
  await mark("end");
}

// What a take will meet, for the price of the two sign-ins: the connected Control UI, its controls by kind (no text
// of the session list is kept: its entries are the titles of earlier sessions), the message box, the model selector.
export async function scout({ page, base, step, state }) {
  if (!state.scout) throw new Error("scout() runs only in scout mode");
  await step("control-ui", async () => ({ url: page.url().replace(/[?#].*/, ""), on_its_own_address: page.url().startsWith(base),
    storage_added: state.storage_added, password_field_still_on_screen: state.password_field_still_on_screen,
    new_session_selector: ((await firstVisible(page, NEW_SESSION)) || {}).matched || "",
    words: await wordsOnScreen(page, [/New session/, /\bzuno\b/, /Could not connect/, /Bob/]) }));
  await step("controls", async () => {
    // Tags, roles and labels only: never the text of an element, which may be a session's title.
    const seen = await describe(page, "body", 120);
    return { controls: seen.map((el) => ({ tag: el.tag, role: el.role, label: el.attrs["aria-label"] || el.attrs.title || "", placeholder: el.attrs.placeholder || "" }))
                           .filter((el) => el.label || el.placeholder || el.role).slice(0, 60),
             delete_like: seen.filter((el) => /delete|remove|trash|supprim/i.test(`${el.attrs["aria-label"] || ""} ${el.attrs.title || ""}`)).length };
  });
  await step("composer", async () => {
    const input = await firstVisible(page, INPUT);
    return { selector: input ? input.matched : null, textareas: await page.locator("textarea").count() };
  });
  await step("closed", async () => ({ nothing_typed: true, sessions_opened: 0 }));
}

// Nothing is created while run() refuses. When a take exists, this deletes its session by the means the scout found.
export async function cleanup({ state }) {
  if (!state.sent) return null;
  throw new Error("a question was sent and this walkthrough does not know how to delete its session: check consultant-02's assistant by hand");
}
