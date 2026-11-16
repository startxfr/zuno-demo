// WP-289 / ADR-0618: the walkthrough of "MCP tools by group", 5-minute version, for evaluations/browser/record.mjs.
//
// Two takes in Open WebUI, one per persona, each in its own browser context and its own video (`takes`), in the order
// of the page: sale-01 plays the rows 0:00 and 2:45, consultant-02 the rows 0:45 and 1:30. Each take asks two
// questions, each in a NEW chat: the tools question (q1-sent, q1-done), then, from a new chat's home page (home-2),
// the Confluence question (q2-sent). A new chat for the second question keeps the first answer off screen: consultant-02's
// list of tools names the Confluence tool, which would read as a tool call. The prompts are the page's, verbatim
// (`node record.mjs --check mcp-tools-by-group`); the 1:30 suggestion card is not clicked, its prompt is typed.
//
// Row 1:30 is a search of the REAL company Confluence, as consultant-02: its answer names real pages. The owner
// accepted on 2026-11-16 that the GIF shows them, the list and the answer (the first take, 2026-11-16 11:20, stopped at
// the tool call). consultant-02's take marks `chip` the moment the Confluence tool call shows, before the answer
// streams under it, then `q2-done` once the answer has finished and its end is inside the window. The log never copies
// that answer, only its length: the titles are on the pictures, where the owner looks at them, and nowhere else.
//
// sale-01's 2:45: the page expects no Confluence tool call and an answer saying so. Seen on 2026-11-16: a red cross on
// a Drive search the model tried instead, then a refusal in its own words. The take does not fail on the wording; it
// logs the answer's first 400 characters (sale-01 cannot read Confluence) and whether a Confluence tool name is on
// screen. The tools answers (0:00, 0:45) are logged the same way, so the page's "You should see" cells can be set from
// what was seen (the owner's decision: the contrast is shown by a question, not by the tools button).
//
// Each take costs two answers on its persona's budget (consultant-02's second one runs one Confluence search with its
// own identity) and creates TWO Open WebUI chats, each deleted by its id in cleanup(). No setting is changed: the
// tools switch is never touched.
//
// Open WebUI's selectors are the shared owui* helpers, seen live on 2026-11-15. The tool call (CHIP below) was seen
// live once, by the take of 2026-11-16. A take that never sees it fails, and logs only the shapes of the new elements,
// never their text.
import { describe, firstVisible, onScreen, owui, owuiAnswered, owuiAsk, owuiChats, owuiDeleteChat, owuiHome, pageApi, read, waitUntil,
         wordsOnScreen } from "./_helpers.mjs";

const TOOLS_PROMPT = "Which tools can you use for me? List their names.";
const CONFLUENCE_PROMPT = "Find our onboarding pages in Confluence.";

export const takes = [
  { name: "sale-01", persona: "sale-01" },
  { name: "consultant-02", persona: "consultant-02", motion_from: "home",
    markers: ["login", "home", "q1-sent", "q1-done", "home-2", "q2-sent", "chip", "q2-done", "end"] },
];
export const page = "docs/demo/scenarios/governance/mcp-tools-by-group.md";
export const viewport = { width: 1280, height: 800 };
// sale-01's markers; consultant-02's take has its own (above): one more, `chip`, before its answer.
export const markers = ["login", "home", "q1-sent", "q1-done", "home-2", "q2-sent", "q2-done", "end"];
// The sign-in (login to home) is never shown as motion.
export const motion_from = "home";
export const changes = [];
export const prompts = {
  "0:00": TOOLS_PROMPT,
  "0:45": TOOLS_PROMPT,
  "1:30": CONFLUENCE_PROMPT,
  "2:45": CONFLUENCE_PROMPT,
};
export const url = owui.url;
export const sends = /\/api\/(chat\/completions|chat\/completed|v1\/chats\/new|v1\/chats\/[^/]+$|v1\/tasks\/)/;

// The rows each persona plays, and whether its Confluence question shows a Confluence tool call.
const ROWS = {
  "sale-01": { tools: "0:00", confluence: "2:45", chip: false },
  "consultant-02": { tools: "0:45", confluence: "1:30", chip: true },
};
// The Confluence tool call on screen. Seen live on 2026-11-16 (Open WebUI 0.12.5): "View Result from
// zuno-mcp_confluence.page.search" with a green check, 2.4 s after the send; the "Executing" wording before the result
// is a guess. The tool must be a Confluence one: a Drive search, the model's other choice (seen for sale-01), is not.
const CHIP = ["text=/View Result from\\s+\\S*confluence/i", "text=/Executing\\s+\\S*confluence/i"];
const CONFLUENCE_TOOL = /confluence\.page\.(search|read)|search_confluence|read_confluence/i;

// While waiting for the chip: has the answer of the chat in the address bar already finished? Asked once a second, a
// read of the chat by its id; "" while it runs. An answer that finished with no Confluence tool call on screen fails
// the take at once.
function answerFinished(page) {
  let last = 0;
  return async () => {
    if (Date.now() - last < 1000) return "";
    last = Date.now();
    const id = (page.url().match(owui.CHAT_ID) || [])[1];
    if (!id) return "";
    const got = await pageApi(page, "GET", `/api/v1/chats/${id}`).catch(() => null);
    const messages = got && got.status === 200 && got.body && got.body.chat && got.body.chat.history && got.body.chat.history.messages;
    const done = messages && Object.values(messages).some((m) => m && m.role === "assistant" && m.done === true);
    return done ? "the answer finished with no Confluence tool call on screen" : "";
  };
}

// Ask one question in the chat open on screen; returns the new chat's id, recorded for cleanup() at once.
async function askInNewChat(page, prompt, state, log) {
  const chat = { sent: true, chatId: "", prompt };   // from here a chat may exist, even if its id is never read
  state.chats.push(chat);
  await owuiAsk(page, prompt, state);
  return async () => {
    await page.waitForURL(owui.CHAT_ID, { timeout: 60000 });
    chat.chatId = page.url().match(owui.CHAT_ID)[1];
    state.created.push({ kind: "chat", id: chat.chatId });
    log(`chat ${chat.chatId} created`);
    return chat.chatId;
  };
}

// The shapes (tag, role, classes) of the elements under <main> or <body>, never their text: what a failed take logs
// so the chip's selector can be written from the real element without copying a Confluence title.
async function shapes(page) {
  return (await describe(page, "body", 120)).map((el) => `${el.tag}${el.role ? `[role=${el.role}]` : ""}${el.classes.length ? "." + el.classes.join(".") : ""}`);
}

// Every scrolling box around the element brought to its end, in the page (a scroll of the view: nothing is changed);
// returns how many moved.
function toEnd(el) {
  let moved = 0;
  const boxes = [];
  for (let box = el.parentElement; box && box !== document.body; box = box.parentElement) boxes.push(box);
  if (document.scrollingElement) boxes.push(document.scrollingElement);
  for (const box of boxes) {
    const scrolls = box === document.scrollingElement || /auto|scroll/.test(getComputedStyle(box).overflowY);
    if (scrolls && box.scrollHeight > box.clientHeight + 4 && box.scrollTop + box.clientHeight < box.scrollHeight - 4) {
      box.scrollTop = box.scrollHeight;
      moved += 1;
    }
  }
  return moved;
}

// The end of consultant-02's answer inside the window. Open WebUI follows a streaming answer, but a long list may end
// under the fold: the boxes around the tool call are brought to their end until a look finds nothing left to move.
// Says how many scrolls it took and whether the tool call is still inside the window (a long list pushes it above;
// the `chip` still shows it anyway).
async function answerEnd(page, chip) {
  let moved = 0;
  await waitUntil(page, { what: "the end of the answer inside the window", timeoutMs: 15000, everyMs: 700,
                          done: async () => { const n = await read(chip, toEnd); moved += n; return n === 0 ? true : undefined; } });
  const box = await chip.boundingBox().catch(() => null);
  const view = page.viewportSize();
  return { moved, chipInside: Boolean(box && box.height > 0 && box.y >= 0 && box.y + box.height <= view.height) };
}

// Sign in and reach the home page of a new chat, sidebar closed, sign-in toast gone.
export async function enter({ page, base, mark, keycloak, persona }) {
  if (!ROWS[persona]) throw new Error(`no rows for the persona ${persona}`);
  // The sidebar is closed before the first screen is drawn: earlier chat titles never appear in the take.
  await page.addInitScript(() => { try { localStorage.setItem("sidebar", "false"); } catch { /* another origin */ } });
  await page.goto(`${base}/oauth/oidc/login`);
  await page.waitForSelector("#username", { timeout: 30000 });
  await mark("login");   // the EMPTY Keycloak form: nothing is marked once the password is typed
  await keycloak(persona);
  await owuiHome(page, base, { changes });
}

// What the persona owns in Open WebUI: its chats, by id. The recorder compares the list before and after the take.
export async function owned({ page }) {
  return owuiChats(page);
}

export async function run({ page, base, mark, log, state, persona }) {
  const rows = ROWS[persona];
  state.chats = [];
  await mark("home");

  // The tools question (0:00 or 0:45).
  const first = await askInNewChat(page, TOOLS_PROMPT, state, log);
  await mark("q1-sent");
  const firstId = await first();
  const tools = await owuiAnswered(page, firstId, 1);
  await page.waitForTimeout(1500);
  log(`answer of ${persona} to the ${rows.tools} question (${tools.length} chars): ${tools.replace(/\s+/g, " ").slice(0, 400)}`);
  await mark("q1-done");

  // The Confluence question (1:30 or 2:45), in a new chat.
  await page.goto(`${base}/`);
  await owuiHome(page, base, { changes });
  await mark("home-2");
  const second = await askInNewChat(page, CONFLUENCE_PROMPT, state, log);
  await mark("q2-sent");

  let chip = null;
  if (rows.chip) {
    // consultant-02: a still the moment the Confluence tool call shows, before the answer streams under it.
    try {
      chip = await waitUntil(page, { what: "a Confluence tool call on screen", timeoutMs: 120000, everyMs: 150, failed: answerFinished(page),
                                     done: async () => (await firstVisible(page, CHIP)) || undefined });
    } catch (e) {
      log(`no Confluence tool call seen; the elements on screen (shapes only): ${(await shapes(page).catch(() => [])).join(" ")}`);
      await second().catch(() => {});   // the chat's id, for cleanup(), when the address bar shows it
      throw new Error(`no Confluence tool call on screen for ${persona} (${CHIP.join(" | ")}): ${e.message}`);
    }
    await mark("chip");
    log(`Confluence tool call on screen (${chip.matched})`);
  }

  const secondId = await second();
  const answer = await owuiAnswered(page, secondId, 1);
  await page.waitForTimeout(1500);
  if (chip) {
    // The real Confluence pages are on screen from here: the log keeps the answer's length only.
    const shown = await answerEnd(page, chip);
    log(`answer of ${persona} to the ${rows.confluence} question: ${answer.length} chars, not logged (real Confluence pages); `
        + `its end inside the window after ${shown.moved} scroll(s), the tool call ${shown.chipInside ? "inside it too" : "above it"}`);
  } else {
    // sale-01: the whole answer may be logged: sale-01 cannot read Confluence.
    const named = await page.getByText(CONFLUENCE_TOOL).first().isVisible().catch(() => false);
    log(`answer of ${persona} to the ${rows.confluence} question (${answer.length} chars): ${answer.replace(/\s+/g, " ").slice(0, 400)}`);
    log(`a Confluence tool name on screen after ${persona}'s answer: ${named ? "YES, check the take" : "no"}`);
  }
  await mark("q2-done");
  await page.waitForTimeout(800);
  await mark("end");
}

// What a take will meet, for the price of a sign-in: Open WebUI's home page (no earlier chat on screen) and whether the
// 1:30 suggestion card is there. Nothing is typed, no prompt is sent, no chat exists afterwards. The tool-call chip
// cannot be scouted: it needs a sent prompt.
export async function scout({ page, step, state, persona }) {
  if (!state.scout) throw new Error("scout() runs only in scout mode");
  const before = (await owuiChats(page)).length;
  await step("home", async () => ({ url: page.url().replace(/[?#].*/, ""), chat_link_on_screen: await onScreen(page, owui.CHAT_LINK),
                                    words: await wordsOnScreen(page, [/Zuno picks the model/, /Find our onboarding pages in Confluence/]) }));
  await step("closed", async () => {
    if (owui.CHAT_ID.test(page.url())) throw new Error("a chat is open after the scout");
    const typed = (await page.locator("#chat-input").innerText().catch(() => "")).trim();
    if (typed) throw new Error("the chat input is not empty after the scout");
    const after = (await owuiChats(page)).length;
    if (after !== before) throw new Error(`${persona} owns ${after} chats after the scout, ${before} before it`);
    return { chats: after };
  });
}

// Delete the chats this take created, by id, each one tried even when another failed.
export async function cleanup({ page, log, state, persona }) {
  const chats = state.chats || [];
  if (!chats.length) return null;
  const failures = [];
  for (const chat of chats) {
    try {
      await owuiDeleteChat(page, { sent: chat.sent, chatId: chat.chatId, created: state.created }, persona, chat.prompt, log);
    } catch (e) {
      failures.push(String(e && e.message ? e.message : e));
    }
  }
  if (failures.length) throw new Error(failures.join("; "));
  return true;
}
