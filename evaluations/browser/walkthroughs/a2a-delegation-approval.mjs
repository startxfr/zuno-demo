// WP-290 / ADR-0618: the walkthrough of "A2A delegation and approval", 5-minute version, for
// evaluations/browser/record.mjs.
//
// The rows of docs/demo/scenarios/governance/a2a-delegation-approval.md, as consultant-02 in the team workspace
// agent-arkos: the Keycloak form (login), its own new session on the workflow arkos in the Collaboration Hub (hub,
// row 0:00), the page's question (q-sent, row 0:45), the approval card of aap.cluster.audit (card, row 1:30),
// Approve clicked (approved, row 2:30), Arkos's answer with the job (q-done), then end. A second card, if one comes,
// is rejected (row 3:30). Row 4:15 is words. The prompt is the page's, verbatim
// (`node record.mjs --check a2a-delegation-approval`).
//
// THE TAKE CLICKS APPROVE (the owner's decision of 2026-11-16, and a go for EACH take): that launches the AAP job
// zuno-day0-check, a read-only audit that runs about six minutes and that nobody can delete from AAP. It is the one
// declared change (`changes`). The card is approved only if it is the card of aap.cluster.audit; any other card
// stops the take without a click. AAP accepts 2 launches per caller in 15 minutes: two takes in a row use them up.
//
// It costs one delegating turn on consultant-02's budget (about 65,000 tokens on 2026-11-03) and creates ONE session
// in the team workspace, deleted by its id at the end (the rules of unifai-agents). Arkos answers without delegating
// on some turns (the page: one in four): then no card comes, the take fails and says so, and the turn was spent.
//
// Team mode is _unifai_team.mjs's (seen by the scouts of 2026-11-16). The approval card was never seen by a scout
// (a scout sends nothing): its selectors are guesses from the page's words, marked `guess`.
import { click, firstVisible, pageApi, read, unifai, unifaiAsk, unifaiDeleteSession, unifaiSignIn, waitUntil, wordsOnScreen } from "./_helpers.mjs";
import { ADD, START, newSession, openHub, openSelector, teamAllows, teamSessions, warm, toBottom } from "./_unifai_team.mjs";

export const persona = "consultant-02";
export const page = "docs/demo/scenarios/governance/a2a-delegation-approval.md";
export const viewport = { width: 1280, height: 800 };
export const markers = ["login", "hub", "q-sent", "card", "approved", "q-done", "end"];
export const motion_from = "hub";
export const changes = ["clicks Approve on the approval card of aap.cluster.audit, which launches the AAP job zuno-day0-check (one job per take, about six minutes, read only; an AAP job cannot be deleted), and Reject on a second card if one comes"];
export const prompts = {
  "0:45": "Call the Tekos delegation tool right now and ask it to launch a fresh cluster audit with its audit tool (aap.cluster.audit), then tell me the job link it returns. Do not answer from memory.",
};
export const url = unifai.url;
export const sends = unifai.sends;
// The write guard: a team take's writes, and the decision on an approval card (Approve, the declared change; Reject).
export const allows = [...teamAllows, { method: "POST", path: /^\/api2\/sessions\/session\.approval\/?$/, what: "the decision on an approval card" }];

const WORKSPACE = "agent-arkos";
const WORKFLOW = "arkos";
const TEAMS = ["agent-arkos", "agent-tekos", "consultant"];   // consultant-02's workspaces
const TOOL = "aap.cluster.audit";
const CARD = "Approval Required";                               // the page's row 1:30
const APPROVE = ["button:text-is('Approve')"];                  // guess
const REJECT = ["button:text-is('Reject')"];                    // guess
const REASON = "textarea[placeholder^='Reason for rejection']"; // the field the first Reject opens (unifai-main, 2026-11-21)
const JOB = /jobs\/playbook\/(\d+)|\bjob(?:\s+id)?\s*[:#]?\s*(\d{2,})/i;
const CARD_TIMEOUT_MS = 180000;      // the page: about 10 s through the API
const ANSWER_TIMEOUT_MS = 300000;    // the approval expires after 300 s

// Reject takes two clicks (ApprovalCard.tsx, read by unifai-main on 2026-11-21): the first only opens a "Reason for
// rejection..." field with Cancel and a second Reject, and only that second one posts the decision. A single click sent
// nothing 99 times on 2026-11-21 08:29Z, and the card expired after 300 s. True once the second Reject is clicked;
// false when the card has no Reject, or was redrawn before the second click (the caller tries again).
async function rejectCard(page, log) {
  const reject = await firstVisible(page, REJECT);
  if (!reject) throw new Error("an approval card is waiting and its Reject button was not found: nothing more is approved");
  await click(reject, { changes });
  const reason = page.locator(REASON).first();
  if (!(await reason.waitFor({ state: "visible", timeout: 5000 }).then(() => true).catch(() => false))) {
    log("the reason field did not open after Reject (the card may have been redrawn): trying again");
    return false;
  }
  const confirm = reason.locator("xpath=ancestor::*[.//button[normalize-space()='Cancel']][1]").locator("button:text-is('Reject')").first();
  if (!(await confirm.isVisible().catch(() => false))) {
    log("the reason field closed before the second Reject (the card was redrawn): trying again");
    return false;
  }
  await click(confirm, { changes });
  return true;
}

export async function enter(ctx) {
  await warm(ctx.page, ctx.base);
  await unifaiSignIn(ctx, persona);
  const seen = await openSelector(ctx.page, TEAMS, { changes, state: ctx.state });
  if (!seen.listed[WORKSPACE]) throw new Error(`the workspace selector of ${persona} does not list ${WORKSPACE}`);
  ctx.state.selector = seen;
  if (ctx.state.scout) return;
  await openHub(ctx.page, ctx.state, WORKSPACE, { changes });
}

export async function owned({ page, state }) {
  if (!state.teamId) return [];
  return (await teamSessions(page, state.teamId)).map((id) => ({ kind: "session", id }));
}

// The session's state, from its own API: {status, answers: [text]}.
async function sessionState(page, id) {
  const got = await pageApi(page, "GET", `/api2/sessions/session.chat.get?sessionId=${encodeURIComponent(id)}`, "").catch(() => null);
  if (!got || got.status !== 200 || !got.body) return { status: "", answers: [] };
  const answers = (Array.isArray(got.body.messages) ? got.body.messages : []).filter((m) => m && m.role === "assistant").map((m) => String(m.content || ""));
  return { status: String(got.body.status || ""), answers };
}

// A card that waits for a decision: its Approve button on screen.
const pending = async (page) => (await page.getByText(CARD).first().isVisible().catch(() => false)) && (await firstVisible(page, APPROVE));

export async function run({ page, mark, log, state }) {
  const id = await newSession(page, state, WORKFLOW, { changes });
  log(`session ${id} created (${WORKFLOW}, workspace ${WORKSPACE})`);
  await page.waitForTimeout(1000);
  await mark("hub");

  await unifaiAsk(page, prompts["0:45"], state);
  const typed = await waitUntil(page, { what: "the question in the thread", timeoutMs: 20000, done: async () => (await page.getByText(prompts["0:45"], { exact: true }).count()) > 0 || undefined }).catch(() => false);
  if (!typed) throw new Error("the question was typed but does not show in the thread: it was not sent");
  await mark("q-sent");

  // The approval card, or the end of the turn without one (Arkos did not delegate).
  const first = await waitUntil(page, { what: "the approval card", timeoutMs: CARD_TIMEOUT_MS, everyMs: 1000, done: async () => {
    if (await pending(page)) return "card";
    const now = await sessionState(page, id);
    if (["FAILED", "CANCELLED"].includes(now.status)) throw new Error(`the session is ${now.status} before any approval card`);
    return now.status === "COMPLETED" && now.answers.length ? "answered" : undefined;
  } });
  if (first !== "card") throw new Error("Arkos answered without delegating (no approval card came): the page says it happens on some turns; the turn was spent, take again later");
  await toBottom(page, prompts["0:45"]);
  await page.waitForTimeout(800);
  // Approved only if it is the card of the audit tool: the words of the card are read, not assumed.
  // (the question itself names the tool, so the card's own text is read: the smallest box around its title that
  // also holds its Approve button.)
  const cardText = await read(page.getByText(CARD).first(), (el) => {
    for (let box = el; box && box !== document.body; box = box.parentElement) {
      if ([...box.querySelectorAll("button")].some((b) => (b.innerText || "").trim() === "Approve")) return box.innerText;
    }
    return "";
  });
  if (!cardText.includes(TOOL)) throw new Error(`the approval card on screen does not name ${TOOL}: nothing is approved`);
  await mark("card");
  await page.waitForTimeout(1500);   // the presenter's sentence

  state.notes.approvals = 0;
  state.notes.rejections = 0;
  const approve = await firstVisible(page, APPROVE);
  await click(approve, { changes });
  state.notes.approvals = 1;
  log(`Approve clicked on the card of ${TOOL}: AAP launches zuno-day0-check`);
  await page.waitForTimeout(1500);
  await mark("approved");

  // The answer; a second card, if the model asks twice, is rejected (the page's row 3:30): one audit is enough.
  const answer = await waitUntil(page, { what: "Arkos's answer after the approval", timeoutMs: ANSWER_TIMEOUT_MS, everyMs: 1000, done: async () => {
    if (await pending(page)) {
      const sent = await rejectCard(page, log);
      if (!sent) return undefined;
      state.notes.rejections += 1;
      log("a second approval card came: rejected (Reject, then Reject next to Cancel)");
      await page.waitForTimeout(1500);
      return undefined;
    }
    const now = await sessionState(page, id);
    if (["FAILED", "CANCELLED"].includes(now.status)) throw new Error(`the session is ${now.status} after the approval`);
    return now.status === "COMPLETED" && now.answers.length ? now.answers[now.answers.length - 1] : undefined;
  } });
  const job = answer.match(JOB);
  state.notes.aap_job = job ? String(job[1] || job[2]) : "";
  log(`answer (${answer.length} chars): ${answer.replace(/\s+/g, " ").slice(0, 300)}`);
  log(job ? `AAP job ${state.notes.aap_job} named in the answer: it stays in AAP` : "the answer names NO job id: check q-done.png and AAP's job list (a job was launched by the approval)");
  await page.waitForTimeout(2500);
  await toBottom(page, prompts["0:45"]);
  await page.waitForTimeout(1200);
  await mark("q-done");
  await page.waitForTimeout(800);
  await mark("end");
}

// What a take will meet, for the price of a sign-in: the selector, the hub of agent-arkos and its new-session dialog
// with the workflow arkos. Nothing is created or sent, so the approval card itself is not seen.
export async function scout({ page, step, state }) {
  if (!state.scout) throw new Error("scout() runs only in scout mode");
  await step("selector", async () => ({ ...state.selector, disclosure: state.disclosure }));
  let before = null;
  await step("hub", async () => {
    await openHub(page, state, WORKSPACE, { changes });
    before = (await teamSessions(page, state.teamId)).length;
    return { team_id_read: Boolean(state.teamId), sessions: before, add_selector: ((await firstVisible(page, ADD)) || {}).matched || "", session_open: unifai.SESSION_ID.test(page.url()),
             words: await wordsOnScreen(page, [/Collaboration Hub/, new RegExp(WORKSPACE), new RegExp(CARD)]) };
  });
  await step("workflows", async () => {
    const add = await firstVisible(page, ADD);
    if (!add) throw new Error(`no new-session button among ${ADD.join(" | ")}`);
    await click(add, { changes });
    const dialog = page.locator(unifai.DIALOG).filter({ hasText: START }).first();
    await dialog.waitFor({ timeout: 15000 });
    const search = await firstVisible(page, unifai.SEARCH);
    if (search) { await search.click(); await page.keyboard.type(WORKFLOW, { delay: 20 }); }
    await page.waitForTimeout(1000);
    return { workflow_exact_matches: await dialog.getByText(WORKFLOW, { exact: true }).count(), start_button: await dialog.getByRole("button", { name: START, exact: true }).count() };
  });
  await step("closed", async () => {
    const dialog = page.locator(unifai.DIALOG).filter({ hasText: START }).first();
    const cancel = dialog.getByRole("button", { name: "Cancel", exact: true });
    if (await cancel.count()) await click(cancel, { changes }); else await page.keyboard.press("Escape");
    await dialog.waitFor({ state: "hidden", timeout: 15000 });
    const after = (await teamSessions(page, state.teamId)).length;
    if (after !== before) throw new Error(`${WORKSPACE} holds ${after} sessions after the scout, ${before} before it`);
    return { sessions: after };
  });
}

// Delete the session this take created, by its id, and nothing else. A card still waiting is rejected first, so no
// approval is left open; the AAP job an approval launched stays in AAP.
export async function cleanup({ page, log, state }) {
  if (state.sessionId && (await pending(page).catch(() => false))) {
    if (await rejectCard(page, log).catch(() => false)) { log("an approval card was still waiting at the end: rejected"); await page.waitForTimeout(1000); }
  }
  const gone = await unifaiDeleteSession(page, state, persona);
  if (gone && state.teamId && (await teamSessions(page, state.teamId)).includes(state.sessionId)) {
    throw new Error(`the session ${state.sessionId} is still listed in ${WORKSPACE} after its delete: delete it by hand`);
  }
  return gone;
}
