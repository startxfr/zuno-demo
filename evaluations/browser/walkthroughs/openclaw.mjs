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
// What a take leaves, and the owner's decision of 2026-11-16 on it. It creates ONE session in consultant-02's
// assistant and deletes it in cleanup() through the Control UI's own menu, "Delete…" (a declared click), and fails if
// the session is still listed. The Control UI talks to its gateway over a WebSocket: there is no list or delete this
// file can call, so the sessions are those of the sidebar, told apart by their link (or, failing that, their text,
// kept in memory only and never written). The assistant gives the session a title of its own after the first
// answer (seen 2026-11-17): the take's session is the ONE row that was not there before, whatever its title. What the assistant may memorise from the one question (its own 10Gi
// volume) STAYS: no take can undo that; it is declared in `changes` and in the record notice.
//
// Seen by the scouts of 2026-11-16: the Control UI at /chat, connected; "New session", a select "Filter sessions by
// agent", and for each earlier session "Pin session" and "Open session menu" (shown on hover), whose entries are Pin
// session, Mark as unread, Rename…, Fork, Move to group, Archive session, Delete…; a textarea; "Collapse sidebar".
// The sidebar lists the earlier sessions' titles: they are on the pictures (collapsing it may be kept by the
// assistant, so it is not clicked). Connect writes one key to the browser's storage, openclaw-device-identity-v1:
// the browser of a take is new each time, so each take is a new device to the gateway. Seen by the take of 2026-11-17: the question sent, the Tool line, the answer.
// "Delete…" asks its confirmation in a NATIVE browser dialog (window.confirm), which a browser driven by Playwright
// answers Cancel by itself when nobody listens: the take of 2026-11-17 05:20 clicked Delete… and the session stayed
// (its video shows the menu, then nothing in the page). So the take listens to dialogs from its sign-in on: it accepts
// ONE dialog of type confirm, and only while cleanup() has just clicked Delete… on its own session; every other dialog
// is dismissed, counted and FAILS the take (a scout too). A dialog's text may quote a session's title: only its type
// and length are logged.
import { click, describe, firstVisible, newText, settled, waitUntil, wordsOnScreen } from "./_helpers.mjs";
import { INPUT, NEW_SESSION, SESSION_MENU, enterControlUi, removeSession, rows, unexpected } from "./_openclaw.mjs";

export const persona = "consultant-02";
export const secrets = ["OPENCLAW_UI_PASSWORD"];
export const page = "docs/demo/scenarios/experiences/openclaw.md";
export const viewport = { width: 1280, height: 800 };
export const markers = ["login", "ui", "session", "q-sent", "q-done", "end"];
export const motion_from = "ui";
export const changes = [
  "clicks Delete… in the menu of the session the take created and accepts the browser's native confirmation dialog it opens (one dialog, of type confirm, only then): that session is removed from the assistant",
  "the assistant may keep a memory of this one question (its 10Gi volume); no take can undo that",
];
// The write guard: the Control UI works over its WebSocket; no HTTP write to the assistant is declared, so any is
// aborted and fails the take (a scout reports it).
export const allows = [];
export const prompts = { "0:45": "Cherche dans Confluence les pages d'onboarding" };
export const url = (domain) => `https://assistant-zuno-claw-${persona}.${domain}`;
// The Control UI sends its messages over a WebSocket, which a request filter does not see: a scout sends nothing
// because scout() never types. An HTTP call that would create a session or send a message is refused all the same
// (guess: none is known).
export const sends = /\/api\/[^?]*(sessions?|messages?|chat)\b/i;

export const enter = (ctx) => enterControlUi(ctx, persona, changes);

const TOOL = /Confluence-page-search/i;                                                   // the page's row 0:45
const ANSWER_TIMEOUT_MS = 240000;

// The sessions the persona's sidebar lists (a WebSocket behind it: see the header).
export async function owned({ page }) {
  return (await rows(page)).map((row) => ({ kind: "session", id: row.id }));
}

export async function run({ page, mark, log, state }) {
  const earlier = await rows(page);
  if (earlier.some((row) => row.by === "nothing")) throw new Error("the sidebar's sessions are not told apart (a row without link or text): the take could not find its own session to delete it, nothing is sent");
  state.before = earlier.map((row) => row.id);
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
  if (unexpected(state)) throw new Error(unexpected(state));
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
  // ONE session menu is opened, its entries read by their label, and it is closed with Escape: nothing is chosen.
  // Opening a menu is not a setting. This is what tells whether a session can be deleted from the Control UI.
  await step("session-menu", async () => {
    const menus = page.locator(SESSION_MENU.join(", "));
    const count = await menus.count();
    if (!count) return { menus: 0 };
    const before = await describe(page, "body", 200);
    // The button shows only when its session's row is hovered (rescout of 2026-11-16: a plain click timed out): the
    // row is hovered first; if the button still does not show, it is clicked where it is (a menu button, never a
    // switch).
    const button = menus.first();
    await button.locator("xpath=..").hover({ timeout: 5000 }).catch(() => {});
    await page.waitForTimeout(400);
    if (await button.isVisible().catch(() => false)) await button.click({ timeout: 5000 });
    else await button.dispatchEvent("click");
    await page.waitForTimeout(800);
    const items = page.locator("[role='menuitem'], [role='menu'] button, [role='menu'] a, [role='menu'] li");
    const labels = [];
    for (let i = 0; i < Math.min(await items.count(), 15); i += 1) {
      if (await items.nth(i).isVisible().catch(() => false)) labels.push(((await items.nth(i).innerText().catch(() => "")) || (await items.nth(i).getAttribute("aria-label")) || "").trim().replace(/\s+/g, " ").slice(0, 40));
    }
    const opened = (await describe(page, "body", 200)).length - before.length;
    await page.keyboard.press("Escape");
    await page.waitForTimeout(500);
    const still = await page.locator("[role='menu']").first().isVisible().catch(() => false);
    if (still) { await page.mouse.click(640, 400); await page.waitForTimeout(400); }   // a click on the empty middle of the page closes it
    return { menus: count, entries: labels, delete_like: labels.filter((l) => /delete|remove|supprim|trash|archive/i.test(l)), controls_added_by_the_menu: opened,
             closed: !(await page.locator("[role='menu']").first().isVisible().catch(() => false)) };
  });
  await step("composer", async () => {
    const input = await firstVisible(page, INPUT);
    return { selector: input ? input.matched : null, textareas: await page.locator("textarea").count() };
  });
  // A take finds its own session as the one row that was not there before it: the rows must be told apart.
  await step("sessions", async () => {
    const list = await rows(page);
    // Each row by its id, its age as the sidebar words it and its rank from the top: never its title.
    const seen = { list: list.map((row) => ({ id: row.id, age: row.age, rank: row.index + 1 })), rows: list.length, told_apart_by: [...new Set(list.map((row) => row.by))], distinct: new Set(list.map((row) => row.id)).size };
    if (seen.distinct !== seen.rows || seen.told_apart_by.includes("nothing")) throw new Error(`the sidebar's ${seen.rows} sessions are not told apart (${seen.distinct} distinct, by ${seen.told_apart_by.join(", ")}): a take could not find its own session`);
    return seen;
  });
  await step("closed", async () => {
    if (unexpected(state)) throw new Error(unexpected(state));
    return { nothing_typed: true, sessions_opened: 0, native_dialogs: 0 };
  });
}

// Delete the session this take created, through the Control UI's own menu, and nothing else: the ONE session of the
// sidebar that was not there before the take. None new: nothing to delete (said in the log). Several new: nothing is
// deleted and the take fails (another device of the persona may have opened one). The session must be gone afterwards.
export async function cleanup({ page, log, state }) {
  if (!state.sent) return null;
  const now = await rows(page);
  const fresh = now.filter((row) => !state.before.includes(row.id));
  if (!fresh.length) throw new Error("a question was sent but the sidebar lists no new session: the take's session could not be found, check consultant-02's assistant by hand");
  if (fresh.length > 1) throw new Error(`the sidebar lists ${fresh.length} new sessions: the take's cannot be told from another's, nothing was deleted; check consultant-02's assistant by hand`);
  state.created.push({ kind: "session", id: fresh[0].id });
  const strays = state.dialogs.seen.length;
  await removeSession(page, state, fresh[0], { change: changes[0], changes, log });
  const gone = await waitUntil(page, { what: "the session's removal", timeoutMs: 20000, done: async () => {
    // Gone when the sidebar lists again only what it listed before the take (a session renamed meanwhile is still one more).
    const left = await rows(page);
    return (left.length <= state.before.length && left.every((row) => state.before.includes(row.id))) || undefined;
  } }).catch(() => false);
  if (!gone) throw new Error(`the session the take created (${fresh[0].id}, the newest of the sidebar) is STILL listed after Delete…: delete it by hand in consultant-02's assistant`);
  log(`session ${fresh[0].id} deleted through the Control UI's menu; what the assistant memorised of the question stays`);
  if (state.dialogs.seen.length > strays) throw new Error(`${unexpected(state)}; the take's session was deleted all the same`);
  return true;
}
