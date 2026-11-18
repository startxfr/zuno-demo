// WP-288 / ADR-0618: the walkthrough of "UnifAI agents", 5-minute version, for evaluations/browser/record.mjs.
//
// Two personas ask the same agent the same question, each in its own browser and its own video (`takes`):
//   consultant-02  rows 0:00 to 1:45: the Keycloak form (login), the Team workspace selector open (workspaces), the
//                  workspace agent-tekos and its Collaboration Hub (hub), a new session on the workflow tekos, the
//                  0:45 question (q1-sent, q1-done), the 1:45 question about the cluster (q2-sent, q2-done), end.
//   ai-ops-01      row 3:00: the Keycloak form (login), agent-tekos and its Collaboration Hub (hub), its OWN new
//                  session on tekos, the same cluster question (q-sent, q-done), end.
// Row 4:15 is words. The prompts are the page's, verbatim (`node record.mjs --check unifai-agents`).
//
// Each take costs its answers on its persona's budget (Tekos chains model and tool calls) and creates ONE session in
// the team workspace agent-tekos, deleted by its id at the end (the id is the answer of UnifAI's own create call).
// Sessions of a team workspace are shared by its members: the take never opens one it did not create, and it fails
// if the workspace does not hold the same sessions after it as before (somebody else's new session would do that
// too: then take again). While its session is open UnifAI sends presence signals (join, heartbeat, typing): they
// end with the session.
//
// The sessions' list of the workspace shows the titles of earlier sessions of its members: the owner accepts them on
// the picture (the decision of 2026-11-16 for unifai-live-rag, same treatment); scout.json never stores a title.
// The cluster answer of ai-ops-01 names real pods and events of zuno-ai-run: object names are fine, a node name or a
// private address fails the take (the recorder's guard). Neither answer is judged here: the first 300 characters of
// each go to the log for the page's "You should see" cells.
//
// Team mode was read in the fork's source (Sidebar.tsx, CollaborationHubView.tsx, v0.1.72), not seen live: "Team"
// and the chosen workspace are screen state only (no request is sent by the clicks, nothing is kept; a page reload
// returns to Personal, so the take never reloads), the hub's "+" is titled "New session from workflow" and its
// dialog confirms with "Start Session". Selectors marked `guess` are from that reading.
import { click, firstVisible, unifai, unifaiAnswered, unifaiAsk, unifaiDeleteSession, unifaiSignIn, waitUntil, wordsOnScreen } from "./_helpers.mjs";
import { ADD, START, newSession, openHub, openSelector, teamAllows, teamSessions, warm, toBottom } from "./_unifai_team.mjs";

export const takes = [
  { name: "consultant-02", persona: "consultant-02", markers: ["login", "workspaces", "hub", "q1-sent", "q1-done", "q2-sent", "q2-done", "end"], motion_from: "workspaces" },
  { name: "ai-ops-01", persona: "ai-ops-01", markers: ["login", "hub", "q-sent", "q-done", "end"], motion_from: "hub" },
];
export const page = "docs/demo/scenarios/experiences/unifai-agents.md";
export const viewport = { width: 1280, height: 800 };
export const markers = takes[0].markers;
export const motion_from = takes[0].motion_from;
export const changes = [];
export const prompts = {
  "0:45": "In one short sentence, say what you can help me with.",
  "1:45": "Why would a pod in the zuno-ai-run namespace fail to start? Check the current state of the namespace and give me what you find.",
};
export const url = unifai.url;
export const sends = unifai.sends;
export const allows = teamAllows;   // the write guard: nothing else is sent to UnifAI

const WORKSPACE = "agent-tekos";
const WORKFLOW = "tekos";
// What the page says each persona's selector lists (row 0:00 for consultant-02; the Personas table for ai-ops-01).
const EXPECTED = { "consultant-02": ["agent-arkos", "agent-tekos", "consultant"], "ai-ops-01": ["agent-tekos", "ops"] };
// Ask, wait for the answer (the session's own state), bring it on screen, and log its beginning for the page.
async function ask(ctx, prompt, count, sentMarker, doneMarker) {
  const { page, mark, log, state } = ctx;
  await unifaiAsk(page, prompt, state);
  const typed = await waitUntil(page, { what: "the question in the thread", timeoutMs: 20000, done: async () => (await page.getByText(prompt, { exact: true }).count()) > 0 || undefined }).catch(() => false);
  if (!typed) throw new Error("the question was typed but does not show in the thread: it was not sent");
  await mark(sentMarker);
  const answer = await unifaiAnswered(page, state.sessionId, count);
  if (!answer.trim()) throw new Error(`the answer to "${prompt.slice(0, 40)}..." is empty`);
  await page.waitForTimeout(2500);   // the last tokens drawn
  await toBottom(page, prompt);
  await page.waitForTimeout(1200);
  log(`answer ${count} (${answer.length} chars): ${answer.replace(/\s+/g, " ").slice(0, 300)}`);
  const tools = await wordsOnScreen(page, [/k8s\.(events|resource|logs)\.[a-z]+/, /knowledge-tekos/]);
  log(`on screen after answer ${count}: a k8s read tool ${Object.values(tools)[0] ? "IS" : "is NOT"} named, the retriever knowledge-tekos ${Object.values(tools)[1] ? "IS" : "is NOT"} named`);
  await mark(doneMarker);
}

export async function enter(ctx) {
  await warm(ctx.page, ctx.base);
  await unifaiSignIn(ctx, ctx.take.persona);
  // The workspace is chosen here, before owned(): the list a take compares is the team workspace's.
  const seen = await openSelector(ctx.page, EXPECTED[ctx.take.persona], { changes, state: ctx.state });
  const missing = Object.keys(seen.listed).filter((name) => !seen.listed[name]);
  if (missing.length) throw new Error(`the workspace selector of ${ctx.take.persona} does not list ${missing.join(", ")}: not what the page says`);
  ctx.state.selector = seen;
  if (ctx.state.scout) return;
  if (ctx.take.name === "consultant-02") await ctx.mark("workspaces");
  await openHub(ctx.page, ctx.state, WORKSPACE, { changes });
}

export async function owned({ page, state }) {
  if (!state.teamId) return [];   // a scout that has not opened the hub yet
  return (await teamSessions(page, state.teamId)).map((id) => ({ kind: "session", id }));
}

export async function run(ctx) {
  const { page, mark, log, state, take } = ctx;
  // The hub opens the workspace's most recent session by itself (somebody else's, scout of 2026-11-16): nothing is
  // typed there. The take's own session is created first, and the hub is shown with it.
  const id = await newSession(page, state, WORKFLOW, { changes });
  log(`session ${id} created (${WORKFLOW}, workspace ${WORKSPACE})`);
  await page.waitForTimeout(1000);
  await mark("hub");
  if (take.name === "consultant-02") {
    await ask(ctx, prompts["0:45"], 1, "q1-sent", "q1-done");
    await ask(ctx, prompts["1:45"], 2, "q2-sent", "q2-done");
  } else {
    await ask(ctx, prompts["1:45"], 1, "q-sent", "q-done");
  }
  await page.waitForTimeout(800);
  await mark("end");
}

// What a take will meet, for the price of the sign-in: the selector and what it lists, the workspace chosen, its
// hub, the new-session dialog with the workflow in it. Nothing is created, nothing is typed; no title is stored.
export async function scout({ page, step, state, take }) {
  if (!state.scout) throw new Error("scout() runs only in scout mode");
  await step("selector", async () => ({ ...state.selector, disclosure: state.disclosure }));
  let before = null;
  await step("hub", async () => {
    await openHub(page, state, WORKSPACE, { changes });
    before = (await teamSessions(page, state.teamId)).length;
    return { url: page.url().replace(/[?#].*/, "").replace(/\/agentic-chats\/.+$/, "/agentic-chats/<id>"), team_id_read: Boolean(state.teamId), sessions: before,
             add_selector: ((await firstVisible(page, ADD)) || {}).matched || "", session_open: unifai.SESSION_ID.test(page.url()),
             words: await wordsOnScreen(page, [/Collaboration Hub/, new RegExp(WORKSPACE), new RegExp(take.persona)]) };
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
    return { search: search ? search.matched : "", workflow_exact_matches: await dialog.getByText(WORKFLOW, { exact: true }).count(),
             start_button: await dialog.getByRole("button", { name: START, exact: true }).count(), switches: await dialog.locator("[role='switch']").count() };
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

// Delete the session this take created, by its id, and nothing else.
export async function cleanup({ page, state, take }) {
  const gone = await unifaiDeleteSession(page, state, take.persona);
  if (gone && state.teamId && (await teamSessions(page, state.teamId)).includes(state.sessionId)) {
    throw new Error(`the session ${state.sessionId} is still listed in ${WORKSPACE} after its delete: delete it by hand`);
  }
  return gone;
}
