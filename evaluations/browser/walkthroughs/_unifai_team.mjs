// WP-288 / ADR-0618: UnifAI's Team mode, shared by the walkthroughs that work in a team workspace (unifai-agents,
// observability-trace). Imported ONLY by those walkthroughs; like _grafana.mjs it is in no walkthrough hash (adding
// it to _helpers.mjs would have made every scout stale): after editing this file, scout again by hand.
//
// Read in the fork's source (Sidebar.tsx, CollaborationHubView.tsx, collaborationHubPanels.tsx, v0.1.72), not yet
// seen live: "Team" and the chosen workspace are screen state only (the clicks send nothing, nothing is kept; a page
// reload returns to Personal, so a take never reloads), the hub is the route of Agentic Chats, its "+" is titled
// "New session from workflow" and its dialog confirms with "Start Session". Selectors marked `guess` are from that
// reading. Seen live by the scouts of 2026-11-16: the Team switch, the selector and its entries, the hub's "+" and
// its dialog match; the hub OPENS BY ITSELF the workspace's most recent session (anybody's: on that day one whose
// workflow no longer validated, with an error toast), and the dialog's rows do carry a Human-in-the-Loop switch (never
// clicked: the click guard refuses it). So a take creates its own session FIRST and shows the hub only then.
import { click, firstVisible, pageApi, read, unifai, unifaiDisclosure, waitUntil } from "./_helpers.mjs";

// A click of this module, named: a click that times out says which one it was. Under load (the scout of 2026-11-16,
// load 6 to 10) UnifAI's "AI Disclosure" notice can come after the sign-in helper stopped waiting for it, and then
// covers the page: when a click fails and the notice is on screen, it is accepted as usual and the click made again.
async function press(page, target, what, { changes = [], state = {} } = {}) {
  for (let attempt = 1; ; attempt += 1) {
    try {
      return await click(target, { changes, timeout: 8000 });
    } catch (error) {
      const notice = await page.locator(unifai.DIALOG).filter({ hasText: unifai.DISCLOSURE }).first().isVisible().catch(() => false);
      if (attempt >= 3 || !notice) throw new Error(`the click on ${what} failed (${String(error.message || error).split("\n")[0].slice(0, 120)})${notice ? ", the AI Disclosure notice is still on screen" : ""}`);
      await unifaiDisclosure(page, state);
    }
  }
}

// The write guard (record.mjs): what a take in a team workspace may send to UnifAI, and nothing else. From the
// fork's source (use-session-hub.ts, api/collaboration.ts, api/sessions.ts): its own session created, its questions,
// its session cancelled and deleted, and what the hub sends by itself while a session is open (presence, the locks'
// states). A scout shows what else UnifAI sends (scout.json `writes.refused`).
export const teamAllows = [
  { method: "POST", path: /^\/api2\/sessions\/user\.session\.create\/?$/, what: "create own session" },
  { method: "POST", path: /^\/api2\/sessions\/user\.session\.submit\/?$/, what: "chat send" },
  { method: "POST", path: /^\/api2\/sessions\/session\.cancel\/?$/, what: "cancel own session" },
  { method: "DELETE", path: /^\/api2\/sessions\/session\.delete\/?$/, what: "delete own session" },
  { method: "POST", path: /^\/api2\/collaboration\/session\.(join|leave|heartbeat|typing)\/?$/, what: "presence in the hub" },
  { method: "POST", path: /^\/api2\/collaboration\/edit_lock\.statuses\/?$/, what: "the locks' states (a read)" },
  // Sent by the hub for the workflow of the session it shows (scouts of 2026-11-16, refused by the first guard). Read
  // in the fork (endpoints/blueprints.py, validate_blueprint): it checks a saved workflow and answers the result,
  // it stores nothing. Refused, the hub says "Workflow Unavailable" and disables the message box.
  { method: "POST", path: /^\/api2\/blueprints\/blueprint\.validate\/?$/, what: "the workflow's validation (a read)" },
];
// UnifAI's first load can outlast every wait of the sign-in helper (rescouts of 2026-11-16: a goto past 30 s, and
// once a black page with a spinner that never left). The entry page is opened HERE first, given 90 s to show its
// sign-in button, and loaded once more if it is still on its loading screen; the sign-in helper then finds it warm.
// Nothing is signed in to, nothing is sent.
export async function warm(page, base) {
  for (let attempt = 1; attempt <= 2; attempt += 1) {
    await page.goto(`${base}/`, { timeout: 90000, waitUntil: "domcontentloaded" }).catch(() => {});
    const ready = await waitUntil(page, { what: "UnifAI's entry page", timeoutMs: 90000, done: async () => (await firstVisible(page, [...unifai.SSO, ...unifai.NAV.chats])) || undefined }).catch(() => null);
    if (ready) return attempt;
  }
  throw new Error("UnifAI's entry page was still on its loading screen after two loads of 90 s");
}
export const TEAM = ["button:text-is('Team')"];                                                             // guess (Sidebar.tsx)
export const SELECTOR = ["button:has(svg.lucide-chevron-down)", "button:has-text('Select team')"];          // guess (Sidebar.tsx)
export const HUB = ["a[href='/agentic-chats']"];                                                            // the same route as Agentic Chats
export const ADD = ["button[title='New session from workflow']"];                                           // guess (collaborationHubPanels.tsx)
export const START = "Start Session";                                                                       // guess (CollaborationHubView.tsx)

// A workspace's entry in the open selector: a button holding its name and "N member(s)". Never the gear beside it
// (team settings), never "Create a new team".
export const entry = (page, name) => page.locator("button").filter({ hasText: new RegExp(`^\\s*${name}\\s*(\\d+\\s*members?)?\\s*$`) }).first();

// Switch to Team and open the workspace selector: which of the expected workspaces are listed.
export async function openSelector(page, expected, { changes = [], state = {} } = {}) {
  const team = await firstVisible(page, TEAM);
  if (!team) throw new Error(`the Team switch was not found (${TEAM.join(" | ")})`);
  await press(page, team, "the Team switch", { changes, state });
  const selector = await waitUntil(page, { what: "the workspace selector", timeoutMs: 20000, done: async () => (await firstVisible(page, SELECTOR)) || undefined });
  await page.waitForTimeout(1200);   // the teams load, the first one is shown on the button
  await press(page, selector, "the workspace selector", { changes, state });
  await entry(page, expected[0]).waitFor({ timeout: 20000 }).catch(() => {});
  const listed = {};
  for (const name of expected) listed[name] = await entry(page, name).isVisible().catch(() => false);
  return { team: team.matched, selector: selector.matched, listed };
}

// Choose the workspace and open its Collaboration Hub. The team's id is read from the hub's own request for its
// sessions (its `teamId`), so the list read later is that workspace's and no other.
export async function openHub(page, state, workspace, { changes = [] } = {}) {
  await press(page, entry(page, workspace), `the workspace ${workspace}`, { changes, state });   // screen state only: no request, nothing kept
  await page.waitForTimeout(800);
  const hub = await firstVisible(page, HUB);
  if (!hub) throw new Error(`the Collaboration Hub link was not found (${HUB.join(" | ")})`);
  const asked = page.waitForRequest((r) => /\/api2\/sessions\/session\.user\.list/.test(r.url()) && Boolean(new URL(r.url()).searchParams.get("teamId")), { timeout: 120000 });
  await press(page, hub, "the Collaboration Hub link", { changes, state });
  state.teamId = new URL((await asked).url()).searchParams.get("teamId");
  // The hub shows "Loading sessions..." until its list has answered: more than 30 s under load (scout of 2026-11-16,
  // 21 sessions, load 16), so it is given two minutes.
  await waitUntil(page, { what: "the Collaboration Hub and its sessions", timeoutMs: 120000,
    done: async () => (!(await page.getByText("Loading sessions").first().isVisible().catch(() => false)) && (await firstVisible(page, ADD))) || undefined });
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
  await press(page, add, "the new-session button", { changes, state });
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
  await waitUntil(page, { what: "the take's own session in the hub", timeoutMs: 30000,
    done: async () => ((page.url().match(unifai.SESSION_ID) || [])[1] === state.sessionId && (await firstVisible(page, unifai.INPUT))) || undefined });
  // The session the hub had opened by itself may have left an error toast: it must be gone before a picture.
  await page.getByText(/Validation Error|Request failed/).first().waitFor({ state: "hidden", timeout: 12000 }).catch(() => {});
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
