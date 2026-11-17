// WP-290 / ADR-0618: what the walkthroughs of a persona's OpenClaw assistant share (openclaw.mjs,
// openclaw-delete-left.mjs): the two sign-ins, the native dialogs, the sessions of the sidebar and the removal of one
// through the Control UI's own menu. A walkthrough's hash (walkthrough_sha256) covers _helpers.mjs and its own file,
// NOT this one: after a change here, both walkthroughs are scouted again by hand.
//
// Seen live on 2026-11-16 and 2026-11-17, see openclaw.mjs's header: the Control UI at /chat, "New session", one
// "Open session menu" button per session (shown on hover), the menu's entries, and "Delete…" asking its confirmation
// in a NATIVE browser dialog.
import crypto from "node:crypto";
import { click, firstVisible, read, waitUntil } from "./_helpers.mjs";

export const UI_PASSWORD = ["input[placeholder='optional' i]"];                                  // seen by the browser check (run.mjs)
export const CONNECT = ["button:has-text('Connect')"];                                           // seen by the browser check
export const NEW_SESSION = ["button:has-text('New session')", "a:has-text('New session')", "button:has-text('Nouvelle session')"];   // the first seen live, 2026-11-16
export const INPUT = ["textarea", "[contenteditable='true']"];                                   // "textarea" seen live, 2026-11-16
export const SESSION_MENU = ["button[aria-label='Open session menu']", "button[title='Open session menu']"];   // seen live, 2026-11-16

// The native dialogs of the page, from the sign-in on. A browser driven by Playwright answers Cancel by itself when
// nobody listens, so every dialog is answered here: ONE dialog of type confirm is accepted each time removeSession()
// has just clicked Delete… (`armed`); every other one is dismissed and kept in `seen`, for the walkthrough to fail on.
// A dialog's text may quote a session's title: only its type and length are logged.
// state.dialogs: {armed: boolean, accepted: count, seen: [type]}.
export function watchDialogs(page, state, log) {
  state.dialogs = { armed: false, accepted: 0, seen: [] };
  page.on("dialog", async (dialog) => {
    const kind = dialog.type();
    if (state.dialogs.armed && kind === "confirm") {
      state.dialogs.armed = false;   // one per Delete… click
      state.dialogs.accepted += 1;
      log(`Delete… asked its confirmation in a native ${kind} dialog (${dialog.message().length} chars): accepted`);
      await dialog.accept().catch(() => {});
      return;
    }
    state.dialogs.seen.push(kind);
    log(`a native ${kind} dialog (${dialog.message().length} chars) the walkthrough does not expect: dismissed`);
    await dialog.dismiss().catch(() => {});
  });
}
export const unexpected = (state) => (state.dialogs && state.dialogs.seen.length ? `the page opened ${state.dialogs.seen.length} native dialog(s) the walkthrough does not expect (${state.dialogs.seen.join(", ")}): dismissed` : "");

// The two sign-ins: the front door's Keycloak form (marker login, on the EMPTY form), then the Control UI's own
// password, typed masked by the recorder, and Connect. Leaves state.storage_added and
// state.password_field_still_on_screen.
export async function enterControlUi({ page, base, mark, keycloak, typeSecret, state, log }, persona, changes) {
  watchDialogs(page, state, log);
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

// The sessions of the sidebar: one per "Open session menu" button. A session's row is the largest box around its
// button that holds no other session's button (and is no taller than a row): on 2026-11-17 the button's parent was a
// box without text, every row got the same id, and the take's own session, renamed by the assistant, was not found.
// Each row is known by an id made here from its link's address or, when it has none, from its text without its age
// ("now", "3h", "10d"); two rows with the same text are told apart by their rank among them. A hash, so that no title
// is ever kept, logged or written. [{id, index, by}].
export async function rows(page) {
  const seen = await read(page, (selector) => [...document.querySelectorAll(selector)].map((button) => {
    let row = button.parentElement;
    for (let up = row && row.parentElement; up && up !== document.body; up = up.parentElement) {
      if (up.querySelectorAll(selector).length > 1 || up.querySelector("textarea") || up.getBoundingClientRect().height > 120) break;
      row = up;
    }
    const link = row.matches("a[href]") ? row : row.querySelector("a[href]");
    // The row's words without its buttons: a button shown only under the pointer must not change the row's id.
    const words = row.cloneNode(true);
    for (const el of words.querySelectorAll("button, [role='button'], svg")) el.remove();
    const AGE = /\b(just now|now|\d+\s*(s|sec|m|min|h|hr|d|w|mo|y)\w*)(\s+ago)?\b/gi;
    const ages = (words.textContent || "").match(AGE) || [];
    return { link: link ? link.getAttribute("href") : "", age: ages.length ? ages[ages.length - 1].trim() : "", text: (words.textContent || "").replace(/\b(just now|now|\d+\s*(s|sec|m|min|h|hr|d|w|mo|y)\w*)(\s+ago)?\b/gi, "").replace(/\s+/g, " ").trim() };
  }), SESSION_MENU.join(", "));
  const met = new Map();
  return seen.map((row, index) => {
    const linked = Boolean(row.link && row.link !== "#");
    const key = linked ? row.link : row.text;
    const rank = (met.get(key) || 0) + 1;
    met.set(key, rank);
    return { index, age: row.age, by: linked ? "link" : row.text ? "text" : "nothing", id: crypto.createHash("sha256").update(rank > 1 ? `${key}\n#${rank}` : key).digest("hex").slice(0, 16) };
  });
}

// Remove ONE session through the Control UI's own menu: its row (as rows() gave it) is hovered, its menu opened,
// "Delete…" clicked and its confirmation accepted. `change` is the declared change the clicks belong to. Whether the
// session is gone is for the caller to prove.
export async function removeSession(page, state, row, { change, changes, log }) {
  const button = page.locator(SESSION_MENU.join(", ")).nth(row.index);
  await button.locator("xpath=..").hover({ timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(400);
  if (await button.isVisible().catch(() => false)) await button.click({ timeout: 5000 }); else await button.dispatchEvent("click");
  const entry = page.locator("[role='menuitem'], [role='menu'] button, [role='menu'] li").filter({ hasText: /^\s*Delete/ }).first();
  await entry.waitFor({ timeout: 10000 });
  // "Delete…" asks before it deletes, in a native confirm dialog: ONE is accepted, and only from this click on (the
  // same declared change). A confirmation drawn in the page instead, if one shows, is confirmed the same way.
  const accepted = state.dialogs.accepted;
  state.dialogs.armed = true;
  try {
    await click(entry, { change, changes });
    const confirm = page.locator("[role='dialog'] button, [role='alertdialog'] button").filter({ hasText: /^\s*(Delete|Confirm|Yes)/ }).first();
    const how = await waitUntil(page, { what: "the confirmation of Delete…", timeoutMs: 8000, everyMs: 250,
      done: async () => (state.dialogs.accepted > accepted ? "native" : (await confirm.isVisible().catch(() => false)) ? "page" : undefined) }).catch(() => "");
    if (how === "page") await click(confirm, { change, changes });
    if (!how) log("Delete… was clicked and asked no confirmation the take knows (no native confirm dialog, none in the page)");
  } finally {
    state.dialogs.armed = false;
  }
}
