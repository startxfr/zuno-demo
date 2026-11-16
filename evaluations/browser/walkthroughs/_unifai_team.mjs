// WP-288 / ADR-0618: UnifAI's Team mode, shared by the walkthroughs that work in a team workspace (unifai-agents,
// observability-trace). Imported ONLY by those walkthroughs; like _grafana.mjs it is in no walkthrough hash (adding
// it to _helpers.mjs would have made every scout stale): after editing this file, scout again by hand.
//
// Read in the fork's source (Sidebar.tsx, CollaborationHubView.tsx, collaborationHubPanels.tsx, v0.1.72), not yet
// seen live: "Team" and the chosen workspace are screen state only (the clicks send nothing, nothing is kept; a page
// reload returns to Personal, so a take never reloads), the hub is the route of Agentic Chats, its "+" is titled
// "New session from workflow" and its dialog confirms with "Start Session". Selectors marked `guess` are from that
// reading.
import { click, firstVisible, pageApi, read, unifai, waitUntil } from "./_helpers.mjs";

export const TEAM = ["button:text-is('Team')"];                                                             // guess (Sidebar.tsx)
export const SELECTOR = ["button:has(svg.lucide-chevron-down)", "button:has-text('Select team')"];          // guess (Sidebar.tsx)
export const HUB = ["a[href='/agentic-chats']"];                                                            // the same route as Agentic Chats
export const ADD = ["button[title='New session from workflow']"];                                           // guess (collaborationHubPanels.tsx)
export const START = "Start Session";                                                                       // guess (CollaborationHubView.tsx)

// A workspace's entry in the open selector: a button holding its name and "N member(s)". Never the gear beside it
// (team settings), never "Create a new team".
export const entry = (page, name) => page.locator("button").filter({ hasText: new RegExp(`^\\s*${name}\\s*(\\d+\\s*members?)?\\s*$`) }).first();

// Switch to Team and open the workspace selector: which of the expected workspaces are listed.
export async function openSelector(page, expected, { changes = [] } = {}) {
  const team = await firstVisible(page, TEAM);
  if (!team) throw new Error(`the Team switch was not found (${TEAM.join(" | ")})`);
  await click(team, { changes });
  const selector = await waitUntil(page, { what: "the workspace selector", timeoutMs: 20000, done: async () => (await firstVisible(page, SELECTOR)) || undefined });
  await page.waitForTimeout(1200);   // the teams load, the first one is shown on the button
  await click(selector, { changes });
  await entry(page, expected[0]).waitFor({ timeout: 20000 }).catch(() => {});
  const listed = {};
  for (const name of expected) listed[name] = await entry(page, name).isVisible().catch(() => false);
  return { team: team.matched, selector: selector.matched, listed };
}

// Choose the workspace and open its Collaboration Hub. The team's id is read from the hub's own request for its
// sessions (its `teamId`), so the list read later is that workspace's and no other.
export async function openHub(page, state, workspace, { changes = [] } = {}) {
  await click(entry(page, workspace), { changes });   // screen state only: no request, nothing kept
  await page.waitForTimeout(800);
  const hub = await firstVisible(page, HUB);
  if (!hub) throw new Error(`the Collaboration Hub link was not found (${HUB.join(" | ")})`);
  const asked = page.waitForRequest((r) => /\/api2\/sessions\/session\.user\.list/.test(r.url()) && Boolean(new URL(r.url()).searchParams.get("teamId")), { timeout: 30000 });
  await click(hub, { changes });
  state.teamId = new URL((await asked).url()).searchParams.get("teamId");
  await waitUntil(page, { what: "the Collaboration Hub", timeoutMs: 30000, done: async () => (await firstVisible(page, ADD)) || undefined });
  await page.waitForTimeout(1000);
}

// The sessions of the team workspace, by id, every page of the list.
export async function teamSessions(page, teamId) {
  const found = [];
  for (let offset = 0; offset < 5000; offset += 100) {
    const got = await pageApi(page, "GET", `/api2/sessions/session.user.list?userId=${encodeURIComponent(teamId)}&teamId=${encodeURIComponent(teamId)}&limit=100&offset=${offset}`, "");
    const list = got.body && (Array.isArray(got.body) ? got.body : got.body.sessions);
    if (got.status !== 200 || !Array.isArray(list)) throw new Error(`the team workspace's sessions could not be read (offset ${offset}: HTTP ${got.status})`);
    for (const s of list) if (s && s.session_id && !found.includes(String(s.session_id))) found.push(String(s.session_id));
    if (Array.isArray(got.body) || !got.body.pagination || !got.body.pagination.has_more || !list.length) break;
  }
  return found;
}

// Create the take's own session on the workflow: the id is the answer of UnifAI's create call.
export async function newSession(page, state, workflow, { changes = [] } = {}) {
  if (state.scout) throw new Error("a scout never creates a session");
  const add = await firstVisible(page, ADD);
  if (!add) throw new Error(`the new-session button was not found (${ADD.join(" | ")})`);
  await click(add, { changes });
  const dialog = page.locator(unifai.DIALOG).filter({ hasText: START }).first();
  await dialog.waitFor({ timeout: 15000 });
  const search = await firstVisible(page, unifai.SEARCH);
  if (search) { await search.click(); await page.keyboard.type(workflow, { delay: 20 }); }
  const row = dialog.getByText(workflow, { exact: true }).first();
  await row.waitFor({ timeout: 15000 });
  await click(row, { changes });
  state.creating = workflow;   // from here a session may exist even if its id is never read
  const [created] = await Promise.all([
    page.waitForResponse((r) => /\/api2\/sessions\/user\.session\.create/.test(r.url()) && r.request().method() === "POST", { timeout: 60000 }),
    click(dialog.getByRole("button", { name: START, exact: true }), { changes }),
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

// Scroll the thread to its end: every scrolling box around the question's bubble, and no other (the same gesture as
// unifai-live-rag, whose first take had its answer under the fold). A scroll of the view: nothing is changed.
export async function toBottom(page, question) {
  const bubble = page.getByText(question, { exact: true }).last();
  if (!(await bubble.count())) return 0;
  return read(bubble, (el) => {
    let moved = 0;
    for (let box = el.parentElement; box && box !== document.body; box = box.parentElement) {
      if (box.scrollHeight > box.clientHeight + 4 && /auto|scroll/.test(getComputedStyle(box).overflowY)) { box.scrollTop = box.scrollHeight; moved += 1; }
    }
    return moved;
  });
}
