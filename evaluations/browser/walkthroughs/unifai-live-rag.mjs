// WP-288 / ADR-0618: the walkthrough of "UnifAI - live RAG on your own documents", 5-minute version, for
// evaluations/browser/record.mjs.
//
// The rows of docs/demo/unifai-live-rag.md, as consultant-01 in the Personal workspace: the Keycloak form (login),
// UnifAI's first screen (home), the Document Library with the two demo files Done (documents), a new chat on the
// workflow consultant-01-my-documents (chat-new), the 2:00 question (q1-sent, q1-done) and the 3:15 question
// (q2-done), then end. The prompts are the page's, verbatim (`node record.mjs --check unifai-live-rag`).
//
// It uploads nothing: `make demo start unifai-live-rag` uploads the two files before the session (ADR-0616), and the
// take fails at `documents` when they are not both listed and Done. It costs two answers of the workflow on
// consultant-01's budget and creates ONE session, when the workflow is chosen. cleanup() deletes that session by the
// id UnifAI's own create call returned, and nothing else.
//
// NOT yet scouted: every selector is a guess read from the fork's UI source (see _helpers.mjs, "UnifAI"). The sign-in,
// the session list, the new chat, the question, the wait for an answer and the delete are the shared unifai* helpers,
// for unifai-agents, observability-trace and a2a-delegation-approval to reuse.
import { click, describe, firstVisible, newText, switches, unifai, unifaiAnswered, unifaiAsk, unifaiDeleteSession, unifaiGo,
         unifaiNewChat, unifaiOpenWorkflows, unifaiSessions, unifaiSignIn, wordsOnScreen } from "./_helpers.mjs";

export const persona = "consultant-01";
export const page = "docs/demo/unifai-live-rag.md";
export const viewport = { width: 1280, height: 800 };
export const markers = ["login", "home", "documents", "chat-new", "q1-sent", "q1-done", "q2-done", "end"];
// The sign-in (login to home) is never shown as motion.
export const motion_from = "home";
// The settings this take is allowed to change: none. It ticks no row of the library and no Human-in-the-Loop switch.
export const changes = [];
export const prompts = {
  "2:00": "Which code goes on a rental car booking?",
  "3:15": "What is the hotel ceiling in Madrid?",
};
export const url = unifai.url;
export const sends = unifai.sends;

const WORKFLOW = "consultant-01-my-documents";
const FILES = ["travel-and-expense-policy.md", "on-call-rota-handbook.md"];   // what `make demo start` uploaded
const EXPECTED = "ZN-CAR-7";                                                  // the page's answer to the 2:00 question
const RETRIEVER = "consultant-01-documents";                                  // the page: shown by the Live workflow panel

// The library's state as the screen shows it: which demo file is listed, and how many rows say Done.
async function library(page) {
  const listed = {};
  for (const file of FILES) listed[file] = await page.getByText(file, { exact: true }).first().isVisible().catch(() => false);
  return { listed, done: await page.getByText("Done", { exact: true }).count() };
}

export async function enter(ctx) {
  await unifaiSignIn(ctx, persona);
}

export async function owned({ page }) {
  return unifaiSessions(page);
}

export async function run({ page, mark, log, state }) {
  await mark("home");

  await unifaiGo(page, "documents", { changes });
  await page.getByText(FILES[0], { exact: true }).first().waitFor({ timeout: 30000 }).catch(() => {});
  const lib = await library(page);
  const absent = FILES.filter((file) => !lib.listed[file]);
  if (absent.length || lib.done < FILES.length) {
    throw new Error(`the Document Library does not show both demo files Done (${absent.length ? "not listed: " + absent.join(", ") : lib.done + " Done"}): `
      + "run `make demo start unifai-live-rag` first, this take uploads nothing");
  }
  await page.waitForTimeout(1000);
  await mark("documents");

  await unifaiGo(page, "chats", { changes });
  const id = await unifaiNewChat(page, WORKFLOW, state, { changes });
  log(`session ${id} created (${WORKFLOW})`);
  await page.waitForTimeout(1000);
  await mark("chat-new");

  await unifaiAsk(page, prompts["2:00"], state);
  await mark("q1-sent");
  const first = await unifaiAnswered(page, id, 1);
  if (!first.includes(EXPECTED)) throw new Error(`the answer to the 2:00 question does not hold ${EXPECTED}: not the page's answer`);
  await page.getByText(EXPECTED).first().waitFor({ timeout: 30000 });
  await page.waitForTimeout(1500);
  log(`the retriever ${RETRIEVER} is ${(await wordsOnScreen(page, [new RegExp(RETRIEVER)]))[RETRIEVER] ? "" : "NOT "}named on screen`);
  await mark("q1-done");

  await unifaiAsk(page, prompts["3:15"], state);
  const second = await unifaiAnswered(page, id, 2);
  if (!second.trim()) throw new Error("the answer to the 3:15 question is empty");
  await page.waitForTimeout(2500);   // the last tokens drawn
  if ((page.url().match(unifai.SESSION_ID) || [])[1] !== id) log(`the address bar does not show the session ${id}`);
  await mark("q2-done");

  await page.waitForTimeout(800);
  await mark("end");
}

// What a take will meet, for the price of a sign-in: the first screen, the library, the chats page and the workflow
// list. No workflow is confirmed, no session is created, nothing is typed in a chat, no row is ticked.
export async function scout({ page, step, state }) {
  if (!state.scout) throw new Error("scout() runs only in scout mode");
  const before = (await unifaiSessions(page).catch(() => [])).length;
  await step("home", async () => ({ url: page.url().replace(/[?#].*/, ""),
                                    nav: { documents: ((await firstVisible(page, unifai.NAV.documents)) || {}).matched || "",
                                           chats: ((await firstVisible(page, unifai.NAV.chats)) || {}).matched || "" },
                                    words: await wordsOnScreen(page, [/Personal/, /Team/, /Documents/, /Agentic Chats/]),
                                    controls: await describe(page, "body", 60) }));
  await step("documents", async () => {
    const selector = await unifaiGo(page, "documents", { changes });
    await page.getByText(FILES[0], { exact: true }).first().waitFor({ timeout: 30000 }).catch(() => {});
    const lib = await library(page);
    return { selector, url: page.url().replace(/[?#].*/, ""), ...lib, ready: FILES.every((f) => lib.listed[f]) && lib.done >= FILES.length,
             words: await wordsOnScreen(page, [/Document Library/, /consultant-01/, /Done/]), switches: await switches(page) };
  });
  await step("chats", async () => {
    const selector = await unifaiGo(page, "chats", { changes });
    await page.waitForTimeout(1500);
    const text = await page.locator("body").innerText();
    return { selector, url: page.url().replace(/[?#].*/, ""),
             add_selector: ((await firstVisible(page, unifai.ADD_CHAT)) || {}).matched || "",
             input_selector: ((await firstVisible(page, unifai.INPUT)) || {}).matched || "",   // may be absent until a chat is open
             // How many earlier sessions of the persona the take would show beside the chat (their count, never a title).
             available_chats: (text.match(/Available Chats \((\d+)\)/) || [])[1] || "",
             // No dump of this page's controls: it lists the persona's earlier sessions, and their titles and
             // previews must not reach scout.json.
             session_open: unifai.SESSION_ID.test(page.url()) };
  });
  await step("workflows", async () => {
    const text = await page.locator("body").innerText();
    const { dialog, row, add, search } = await unifaiOpenWorkflows(page, WORKFLOW, { changes });
    await page.waitForTimeout(800);
    const found = { add_selector: add, search_selector: search, workflow_listed: await row.isVisible().catch(() => false),
                    workflow_exact_matches: await dialog.getByText(WORKFLOW, { exact: true }).count(),
                    confirm_button: await dialog.getByRole("button", { name: "Add", exact: true }).count(),
                    cancel_button: await dialog.getByRole("button", { name: "Cancel", exact: true }).count(),
                    text: (await newText(page, text)).slice(0, 30), switches: await switches(page), dialog: await describe(page, unifai.DIALOG, 60) };
    await click(dialog.getByRole("button", { name: "Cancel", exact: true }).first(), { changes });
    await dialog.waitFor({ state: "hidden", timeout: 15000 });
    return found;
  });
  await step("closed", async () => {
    await page.waitForTimeout(600);
    const after = (await unifaiSessions(page)).length;
    if (after !== before) throw new Error(`${persona} owns ${after} sessions after the scout, ${before} before it`);
    return { url: page.url().replace(/[?#].*/, ""), sessions: after, dialog_still_open: await page.locator(unifai.DIALOG).first().isVisible().catch(() => false) };
  });
}

export async function cleanup({ page, log, state }) {
  const done = await unifaiDeleteSession(page, state, persona);
  if (done) log(`session ${state.sessionId} deleted (${WORKFLOW})`);
  return done;
}
