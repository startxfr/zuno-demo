// WP-288 / ADR-0618: the walkthrough of "Observability trace", 5-minute version, for evaluations/browser/record.mjs.
//
// Two takes of two screens, each in its own browser and its own video (`takes`, each with its own markers):
//   chat   row 0:45: consultant-02 on UnifAI, team workspace agent-tekos: the Keycloak form (login), the
//          Collaboration Hub (hub), its own new session on the workflow tekos and the page's question (q-sent,
//          q-done), end.
//   trace  rows 1:45 and 3:00: ai-ops-01 on the Tempo search UI: the Keycloak form (login), the search of the page
//          (service ai-gateway, operation model_call, tag zuno.persona=consultant-02, last 15 minutes) with its
//          results (search), the newest trace opened (trace), a model_call span opened on its tags (tags), end.
// Rows 0:00 and 4:15 are words. The prompt is the page's, verbatim (`node record.mjs --check observability-trace`).
//
// chat costs one Tekos answer on consultant-02's budget and creates ONE session in the team workspace, deleted by
// its id (the rules of unifai-agents). The trace it leaves is the demo's proof and stays, as for any use. trace is
// read only: a search and two clicks, nothing created, nothing saved. It is played after chat and searches again, up
// to three minutes, until a trace shows: spans are exported in batches (the page: up to a minute).
//
// The search is given in the address (/search?service=...&operation=...&tags=...&lookback=15m), which is what the
// form's "Find Traces" produces: the form shows the same fields filled. NOT seen live (the page says the search was
// never rehearsed): the Tempo search UI is the Jaeger UI, and its selectors below are that UI's, marked `guess`.
//
// Two things the first scout must tell before any take:
//  - the Tempo UI's own OpenShift proxy asks "Authorize Access" for ai-ops-01 (the scout of 2026-11-16 stopped on
//    it): approved as a declared change since the owner's decision of that day, see `changes`.
//  - an opened span shows a "Process" line (the pod's address, its host): the recorder counts node names and private
//    addresses on the page at each step; if it finds some at `tags`, a take would fail there. scout() opens the newest
//    existing trace (read only) so that this is known for the price of a sign-in.
import { click, firstVisible, unifai, unifaiAnswered, unifaiAsk, unifaiDeleteSession, unifaiSignIn, waitUntil, wordsOnScreen } from "./_helpers.mjs";
import { ADD, newSession, openHub, openSelector, teamSessions, toBottom } from "./_unifai_team.mjs";
import { grafanaInWindow, proxySignIn } from "./_grafana.mjs";

export const takes = [
  { name: "chat", persona: "consultant-02", markers: ["login", "hub", "q-sent", "q-done", "end"], motion_from: "hub" },
  { name: "trace", persona: "ai-ops-01", markers: ["login", "search", "trace", "tags", "end"], motion_from: "search" },
];
export const page = "docs/demo/scenarios/governance/observability-trace.md";
export const viewport = { width: 1280, height: 800 };
export const markers = takes[0].markers;
export const motion_from = takes[0].motion_from;
// OpenShift's "Authorize Access" page of the Tempo UI's own proxy, as the scout of 2026-11-16 met it: service account
// tempo-tempo of zuno-monitoring, for ai-ops-01, user:info and user:check-access. The owner's decision of 2026-11-16
// (in demo333's session): approve it, as a DECLARED change, for exactly that client and those two scopes. Any other
// page still stops the take (proxySignIn, _grafana.mjs).
const TEMPO_AUTHORIZE = { persona: "ai-ops-01", client: ["tempo-tempo", "zuno-monitoring"],
  change: "approves OpenShift's Authorize Access page for the Tempo search UI's proxy as ai-ops-01 (user:info and user:check-access), which stores one OAuth authorization for ai-ops-01 on the cluster" };
export const changes = [TEMPO_AUTHORIZE.change];
export const prompts = { "0:45": "In one short sentence, say what you can help me with." };
export const url = unifai.url;
export const sends = unifai.sends;

const WORKSPACE = "agent-tekos";
const WORKFLOW = "tekos";
const TEAMS = ["agent-arkos", "agent-tekos", "consultant"];   // consultant-02's workspaces (the unifai-agents page)
const SEARCH = { service: "ai-gateway", operation: "model_call", tags: { "zuno.persona": "consultant-02" }, lookback: "15m" };   // the page's row 1:45
const SPAN = "model_call";
// The tags the page's row 3:00 names; the first three must be drawn inside the window at the `tags` marker.
const TAGS = ["zuno.persona", "zuno.client", "zuno.agent", "zuno.task", "zuno.classification", "zuno.model_kind", "zuno.provider", "zuno.model",
              "zuno.latency_ms", "zuno.estimated_cost_usd", "zuno.outcome", "zuno.run_id"];
const WAIT_FOR_TRACE_MS = 180000;
const READY = [".SearchForm", ".SearchTracePage", "[data-testid='SearchForm']", "#jaeger-ui-root", "main"];       // guess (Jaeger UI)
const RESULT = [".ResultItem a.ResultItemTitle--item", ".ResultItem a", "a[href*='/trace/']"];                             // guess
const SPAN_NAME = [".span-row .span-name", ".span-name", "[data-testid='span-name']"];                                      // guess
const DETAIL = [".detail-row", ".SpanDetail", "[data-testid='span-detail']"];                                              // guess
const TAGS_HEADER = [".AccordianKeyValues--header:has-text('Tags')", "a:has-text('Tags')", "[role='switch']:has-text('Tags')"];   // guess

const tempo = (domain) => process.env.RECORD_BASE_URL_TEMPO || `https://tempo-jaegerui-zuno-monitoring.${domain}`;
const searchAddress = (base) => `${base}/search?service=${SEARCH.service}&operation=${SEARCH.operation}`
  + `&tags=${encodeURIComponent(JSON.stringify(SEARCH.tags))}&lookback=${SEARCH.lookback}&limit=20`;

export async function enter(ctx) {
  const { page, domain, take, state } = ctx;
  if (take.name === "trace") {
    state.writes = [];
    // Read only: any request to the Tempo UI that is not a GET is kept, and fails the take.
    page.on("request", (r) => { if (r.url().startsWith(tempo(domain)) && !["GET", "HEAD", "OPTIONS"].includes(r.method())) state.writes.push(`${r.method()} ${new URL(r.url()).pathname}`); });
    await proxySignIn({ ...ctx, base: tempo(domain) }, take.persona, { changes, what: "the Tempo search UI", ready: READY, authorize: TEMPO_AUTHORIZE });
    return;
  }
  await unifaiSignIn(ctx, take.persona);
  const seen = await openSelector(page, TEAMS, { changes, state });
  if (!seen.listed[WORKSPACE]) throw new Error(`the workspace selector of ${take.persona} does not list ${WORKSPACE}`);
  state.selector = seen;
  if (state.scout) return;
  await openHub(page, state, WORKSPACE, { changes });
}

export async function owned({ page, state, take }) {
  if (take.name === "trace" || !state.teamId) return [];
  return (await teamSessions(page, state.teamId)).map((id) => ({ kind: "session", id }));
}

async function runChat({ page, mark, log, state }) {
  // The hub opens the workspace's most recent session by itself: the take's own is created first, then shown.
  const id = await newSession(page, state, WORKFLOW, { changes });
  log(`session ${id} created (${WORKFLOW}, workspace ${WORKSPACE})`);
  await page.waitForTimeout(1000);
  await mark("hub");
  await unifaiAsk(page, prompts["0:45"], state);
  const shown = await waitUntil(page, { what: "the question in the thread", timeoutMs: 20000, done: async () => (await page.getByText(prompts["0:45"], { exact: true }).count()) > 0 || undefined }).catch(() => false);
  if (!shown) throw new Error("the question was typed but does not show in the thread: it was not sent");
  await mark("q-sent");
  const answer = await unifaiAnswered(page, id, 1);
  if (!answer.trim()) throw new Error("the answer is empty");
  await page.waitForTimeout(2500);   // the last tokens drawn
  await toBottom(page, prompts["0:45"]);
  await page.waitForTimeout(1200);
  await mark("q-done");
  await page.waitForTimeout(800);
  await mark("end");
}

// Load the search and return its results (locators' count), waiting for the page to settle.
async function search(page, base) {
  await page.goto(searchAddress(base));
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(1500);
  const first = await firstVisible(page, RESULT);
  return first ? { matched: first.matched, count: await page.locator(first.matched).count() } : { matched: "", count: 0 };
}

// Open the newest trace of the results, then a model_call span, then its tags: what is on screen at each step.
async function openTrace(page, found) {
  await click(page.locator(found.matched).first(), { changes });
  await page.waitForURL(/\/trace\/[0-9a-f]{8,}/, { timeout: 30000 });
  await waitUntil(page, { what: "the trace's spans", timeoutMs: 30000, done: async () => (await firstVisible(page, SPAN_NAME)) || undefined });
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(1000);
}

async function openSpan(page) {
  const name = await firstVisible(page, SPAN_NAME);
  const spans = page.locator(name.matched).filter({ hasText: SPAN });
  if (!(await spans.count())) throw new Error(`the trace holds no ${SPAN} span on screen (${name.matched})`);
  await click(spans.first(), { changes });
  const detail = await waitUntil(page, { what: "the span's detail", timeoutMs: 15000, done: async () => (await firstVisible(page, DETAIL)) || undefined });
  const header = await firstVisible(page, TAGS_HEADER);
  if (header) { await click(header, { changes }); await page.waitForTimeout(800); }   // an accordion of the page: nothing is saved
  await page.mouse.move(640, 790);
  const text = await page.locator(detail.matched).first().innerText().catch(() => "");
  return { detail: detail.matched, tags_header: header ? header.matched : "", tags: TAGS.filter((tag) => text.includes(tag)) };
}

async function runTrace({ page, domain, mark, log, state }) {
  const base = tempo(domain);
  const deadline = Date.now() + WAIT_FOR_TRACE_MS;
  let found = await search(page, base);
  while (!found.count && Date.now() < deadline) {
    log("the search finds no trace yet: searching again in 20 s");
    await page.waitForTimeout(20000);
    found = await search(page, base);
  }
  if (!found.count) throw new Error(`the Tempo search finds no ${SPAN} trace of ${SEARCH.tags["zuno.persona"]} in the last ${SEARCH.lookback} within ${WAIT_FOR_TRACE_MS / 60000} minutes of the question`);
  log(`the search lists ${found.count} trace(s)`);
  state.notes.traces_listed = found.count;
  await mark("search");
  await openTrace(page, found);
  await mark("trace");
  const span = await openSpan(page);
  const missing = TAGS.filter((tag) => !span.tags.includes(tag));
  if (span.tags.length < 3 || !span.tags.includes("zuno.persona")) throw new Error(`the ${SPAN} span does not show its tags (seen: ${span.tags.join(", ") || "none"})`);
  if (missing.length) log(`tags of the page's row 3:00 NOT in the span's detail: ${missing.join(", ")}`);
  const out = [];
  for (const tag of ["zuno.persona", "zuno.client", "zuno.agent"]) if (span.tags.includes(tag) && !(await grafanaInWindow(page, tag))) out.push(tag);
  if (out.length) throw new Error(`the span's tags ${out.join(", ")} are not drawn inside the window: the picture would not hold the row's proof`);
  log(`the gateway's span ${(await page.locator("body").innerText()).includes(prompts["0:45"]) ? "page SHOWS the question's text somewhere: check tags.png" : "page shows no question text"}`);
  await page.waitForTimeout(800);
  await mark("tags");
  await page.waitForTimeout(800);
  await mark("end");
  if (state.writes.length) throw new Error(`the take sent ${[...new Set(state.writes)].join(", ")} to the Tempo search UI: it must change nothing there`);
}

export async function run(ctx) {
  return ctx.take.name === "trace" ? runTrace(ctx) : runChat(ctx);
}

// What the takes will meet, for the price of the sign-ins. chat: the selector, the hub and its new-session button
// (nothing created). trace: the sign-in chain, the search as it answers now and, when it lists a trace, that trace
// and a model_call span opened: read only, and the recorder counts node names and addresses at each step.
export async function scout({ page, domain, step, state, take }) {
  if (!state.scout) throw new Error("scout() runs only in scout mode");
  if (take.name === "trace") {
    const base = tempo(domain);
    await step("chain", async () => ({ ...state.grafana, url: page.url().replace(/[?#].*/, "") }));
    let found = { count: 0 };
    await step("search", async () => {
      found = await search(page, base);
      return { url: page.url().replace(/[#].*/, ""), results: found.count, selector: found.matched,
               words: await wordsOnScreen(page, [/ai-gateway/, /model_call/, /zuno\.persona/, /Find Traces/, /Last 15 Minutes|15m/]) };
    });
    await step("trace", async () => {
      if (!found.count) return { skipped: "the search lists no trace now: ask Tekos as consultant-02, then scout again" };
      await openTrace(page, found);
      const name = await firstVisible(page, SPAN_NAME);
      return { url: page.url().replace(/\/trace\/.*/, "/trace/<id>"), span_selector: name.matched, spans: await page.locator(name.matched).count(),
               model_call_spans: await page.locator(name.matched).filter({ hasText: SPAN }).count() };
    });
    await step("tags", async () => {
      if (!found.count) return { skipped: "no trace" };
      const span = await openSpan(page);
      const inside = {};
      for (const tag of ["zuno.persona", "zuno.client", "zuno.agent"]) inside[tag] = await grafanaInWindow(page, tag);
      return { ...span, in_window: inside, process_line_on_screen: await page.getByText(/^Process/).first().isVisible().catch(() => false) };
    });
    await step("closed", async () => {
      if (state.writes.length) throw new Error(`the scout sent ${[...new Set(state.writes)].join(", ")} to the Tempo search UI`);
      return { writes: 0 };
    });
    return;
  }
  let before = null;
  await step("selector", async () => ({ ...state.selector, disclosure: state.disclosure }));
  await step("hub", async () => {
    await openHub(page, state, WORKSPACE, { changes });
    before = (await teamSessions(page, state.teamId)).length;
    return { team_id_read: Boolean(state.teamId), sessions: before, add_selector: ((await firstVisible(page, ADD)) || {}).matched || "", session_open: unifai.SESSION_ID.test(page.url()) };
  });
  await step("closed", async () => {
    const after = (await teamSessions(page, state.teamId)).length;
    if (after !== before) throw new Error(`${WORKSPACE} holds ${after} sessions after the scout, ${before} before it`);
    return { sessions: after };
  });
}

export async function cleanup({ page, state, take }) {
  if (take.name === "trace") return null;
  const gone = await unifaiDeleteSession(page, state, take.persona);
  if (gone && state.teamId && (await teamSessions(page, state.teamId)).includes(state.sessionId)) {
    throw new Error(`the session ${state.sessionId} is still listed in ${WORKSPACE} after its delete: delete it by hand`);
  }
  return gone;
}
