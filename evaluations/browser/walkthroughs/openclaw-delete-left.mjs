// WP-290 / ADR-0618: NOT a demo's walkthrough: a one-purpose run for evaluations/browser/record.mjs that deletes, from
// consultant-02's OpenClaw assistant, the sessions two FAILED takes of openclaw.mjs left there on 2026-11-17 (02:31:
// the session was not found; 05:20: Delete… was answered Cancel, see openclaw.mjs's header), and nothing else. It has
// no demo page, no cut list, no GIF. The owner chose it on 2026-11-17 ("Suppression seule d'abord"); each run needs the
// owner's go, naming the ids below.
//
// It asks NO question and types nothing in the chat: the two sign-ins of openclaw.mjs (login), the connected Control
// UI (ui), then for each id of LEFT: its row's menu, "Delete…", the native confirm dialog accepted (one per session),
// and the proof that the sidebar lists exactly what it listed before, less that id. Then end.
//
// LEFT holds the ids to delete, as rows() of _openclaw.mjs makes them (a hash of the row's link): constants of this
// file, so its hash covers them, and no other session can be deleted by construction: a row is passed to the removal
// only if its id is in LEFT. The run REFUSES TO START (before any sign-in) while an entry is not a 16-hex id.
// It fails, deleting nothing, if a listed id is not in the sidebar; it fails if a listed id is still there after its
// Delete…, or if the sidebar lost or gained any other session (owned(): the rows that are NOT in LEFT must be the
// same before and after).
//
// A scout (RECORD_SCOUT=1) deletes nothing and may run with the placeholder: it lists each row as {id, age, rank},
// no title, and says which ids of LEFT are there. That is how the missing id is found: the row of the first failed
// take is matched against the picture by its rank and age, and the owner names both ids in the go.
import { enterControlUi, removeSession, rows, unexpected } from "./_openclaw.mjs";
import { waitUntil, wordsOnScreen } from "./_helpers.mjs";

export const persona = "consultant-02";
export const secrets = ["OPENCLAW_UI_PASSWORD"];
export const viewport = { width: 1280, height: 800 };
export const markers = ["login", "ui", "end"];
export const motion_from = "ui";
// The ids to delete. 3d799c91782010a2: the session of the failed take of 2026-11-17 05:20 (its markers.json).
// The second entry is a PLACEHOLDER for the session of the failed take of 02:31, whose id is in no file: replace it
// by the id a scout of this file reports for that row. While it is not a 16-hex id, a run refuses to start.
export const LEFT = ["3d799c91782010a2", "FILL-IN-THE-ID-OF-THE-02:31-SESSION-FROM-A-SCOUT"];
export const changes = [
  `clicks Delete… in the menu of each of the ${LEFT.length} sessions two failed takes left (ids listed in this file) and accepts the browser's native confirmation dialog each opens: those sessions are removed from consultant-02's assistant`,
];
// The write guard: the Control UI works over its WebSocket; no HTTP write to the assistant is declared.
export const allows = [];
export const url = (domain) => `https://assistant-zuno-claw-${persona}.${domain}`;
export const sends = /\/api\/[^?]*(sessions?|messages?|chat)\b/i;

const ID = /^[0-9a-f]{16}$/;
const unfilled = () => LEFT.filter((id) => !ID.test(id));

export async function enter(ctx) {
  if (!ctx.state.scout && unfilled().length) throw new Error(`refuses to start: LEFT holds ${unfilled().length} entry(ies) that are not a session id (a placeholder): fill it from a scout, with the owner's go`);
  if (new Set(LEFT).size !== LEFT.length) throw new Error("refuses to start: LEFT names the same id twice");
  await enterControlUi(ctx, persona, changes);
}

// What must NOT change: the sessions of the sidebar that are not in LEFT.
export async function owned({ page }) {
  return (await rows(page)).filter((row) => !LEFT.includes(row.id)).map((row) => ({ kind: "session", id: row.id }));
}

const same = (a, b) => a.length === b.length && a.every((id) => b.includes(id));

export async function run({ page, mark, log, state }) {
  if (state.password_field_still_on_screen) throw new Error("the Control UI still shows its password field after Connect: it must not be in a picture");
  const before = await rows(page);
  if (before.some((row) => row.by === "nothing") || new Set(before.map((row) => row.id)).size !== before.length) throw new Error("the sidebar's sessions are not told apart: nothing is deleted");
  const absent = LEFT.filter((id) => !before.some((row) => row.id === id));
  if (absent.length) throw new Error(`the sidebar does not list ${absent.join(", ")} (of ${LEFT.join(", ")}): nothing is deleted; scout again and check the ids`);
  await mark("ui");
  state.notes.listed_before = before.length;
  state.notes.deleted = 0;
  let expected = before.map((row) => row.id);
  for (const id of LEFT) {
    const row = (await rows(page)).find((one) => one.id === id);
    if (!row || !LEFT.includes(row.id)) throw new Error(`the session ${id} is no longer in the sidebar before its Delete…: stopped, ${state.notes.deleted} deleted so far`);
    await removeSession(page, state, row, { change: changes[0], changes, log });
    expected = expected.filter((one) => one !== id);
    // Gone when the sidebar lists exactly what it listed before, less the ids deleted so far.
    const gone = await waitUntil(page, { what: `the removal of ${id}`, timeoutMs: 20000, done: async () => same((await rows(page)).map((one) => one.id), expected) || undefined }).catch(() => false);
    if (!gone) {
      const now = (await rows(page)).map((one) => one.id);
      throw new Error(now.includes(id) ? `the session ${id} is STILL listed after Delete…: stopped, ${state.notes.deleted} deleted so far`
        : `after the Delete… of ${id} the sidebar does not list what it should (${now.length} rows, ${expected.length} expected): stopped, check consultant-02's assistant by hand`);
    }
    state.notes.deleted += 1;
    log(`session ${id} deleted through the Control UI's menu (${state.notes.deleted} of ${LEFT.length})`);
    await page.waitForTimeout(800);
  }
  state.notes.listed_after = expected.length;
  await mark("end");
  if (unexpected(state)) throw new Error(unexpected(state));
}

// For the price of the two sign-ins, nothing clicked: the rows by id, age and rank (never a title), and which ids of
// LEFT are there.
export async function scout({ page, base, step, state }) {
  if (!state.scout) throw new Error("scout() runs only in scout mode");
  await step("control-ui", async () => ({ on_its_own_address: page.url().startsWith(base), password_field_still_on_screen: state.password_field_still_on_screen,
    words: await wordsOnScreen(page, [/New session/, /Could not connect/]) }));
  await step("sessions", async () => {
    const list = await rows(page);
    const seen = { list: list.map((row) => ({ id: row.id, age: row.age, rank: row.index + 1, in_left: LEFT.includes(row.id) })), rows: list.length,
                   told_apart_by: [...new Set(list.map((row) => row.by))], distinct: new Set(list.map((row) => row.id)).size,
                   left: Object.fromEntries(LEFT.map((id) => [ID.test(id) ? id : "placeholder", ID.test(id) ? list.some((row) => row.id === id) : null])), placeholders: unfilled().length };
    if (seen.distinct !== seen.rows || seen.told_apart_by.includes("nothing")) throw new Error(`the sidebar's ${seen.rows} sessions are not told apart: a run could not find the listed ones`);
    return seen;
  });
  await step("closed", async () => {
    if (unexpected(state)) throw new Error(unexpected(state));
    return { nothing_typed: true, nothing_clicked: true, native_dialogs: 0 };
  });
}

// The run creates nothing: nothing to clean.
export async function cleanup() {
  return null;
}
