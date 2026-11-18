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
import { click, firstVisible, read, unifai, unifaiAnswered, unifaiAsk, unifaiDeleteSession, unifaiSignIn, waitUntil, wordsOnScreen } from "./_helpers.mjs";
import { ADD, newSession, openHub, openSelector, teamAllows, teamSessions, warm, toBottom } from "./_unifai_team.mjs";
import { proxySignIn } from "./_grafana.mjs";

const tempo = (domain) => process.env.RECORD_BASE_URL_TEMPO || `https://tempo-jaegerui-zuno-monitoring.${domain}`;
export const takes = [
  { name: "chat", persona: "consultant-02", markers: ["login", "hub", "q-sent", "q-done", "end"], motion_from: "hub" },
  { name: "trace", persona: "ai-ops-01", markers: ["login", "search", "trace", "tags", "tags-run", "end"], motion_from: "search" },
];
export const page = "docs/demo/scenarios/foundation/observability-trace.md";
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
// The write guard covers both applications: UnifAI gets a team take's writes; the Tempo search UI gets none at all.
export const allows = teamAllows;
export const guards = (domain) => [process.env.RECORD_BASE_URL || unifai.url(domain), tempo(domain)];

const WORKSPACE = "agent-tekos";
const WORKFLOW = "tekos";
const TEAMS = ["agent-arkos", "agent-tekos", "consultant"];   // consultant-02's workspaces (the unifai-agents page)
// The page's row 1:45, plus the agent: on 2026-11-16 the newest model_call of consultant-02 in 15 minutes was a FAILED
// call of its OpenClaw assistant, not the Tekos answer. The search names the agent too, so the trace is the turn the
// first take asked (the page's own recovery row narrows the search the same way, by tags).
const SEARCH = { service: "ai-gateway", operation: "model_call", tags: { "zuno.persona": "consultant-02", "zuno.agent": "tekos" }, lookback: "15m" };
const SPAN = "model_call";
// The tags the page's row 3:00 names. The span lists its zuno.* rows in alphabetical order (seen 2026-11-17: agent,
// classification, client, estimated_cost_usd, a list of the persona's groups on several lines, latency_ms, model,
// model_kind, outcome, persona, prompt_tokens, provider, request_id, run_id, task, user_sub): more than the window
// holds under the Jaeger UI's fixed header, so the take makes TWO pictures, by framing only (no row is hidden or
// changed):
//  - `tags`: zuno.model with the one row after it as the last of the window; FIRST_NAMED must be drawn in the window
//    (which app, which agent, which model, what cost).
//  - `tags-run`: zuno.run_id with the one row after it (zuno.task) as the last of the window; LAST_NAMED must be drawn
//    (who asked, and the run, which is the chat take's own session id).
// Both are framed from the BOTTOM: once zuno.groups is folded the seventeen zuno.* rows are about 460 px high and fit
// under the header, so zuno.agent as the first row would bring zuno.user_sub into the window (the stand-in showed
// it; on the live picture of 05:44 the rows are 27 px and the visible area about 480).
// Before them the take folds zuno.groups, a JSON list the UI draws open on about ten lines, with the UI's own arrow
// beside it, as a reader would (a fold of the page, kept nowhere; said in the notes: groups_collapsed).
// DRAWN means the WHOLE row, label and value, at its full height inside the visible area: a row cut by an edge of the
// window or under the fixed header is not drawn (the rescout of 05:44 counted a row whose top alone showed).
// zuno.user_sub (the persona's Keycloak subject, the list's last row) must be in NEITHER picture: any part of it in
// the window at a marker fails the take. A named tag the span shows and that is outside the window at its marker
// fails the take too. A tag of the page's row the span does not carry at all is logged (a matter for the page).
const TAGS = ["zuno.persona", "zuno.client", "zuno.agent", "zuno.task", "zuno.classification", "zuno.model_kind", "zuno.provider", "zuno.model",
              "zuno.latency_ms", "zuno.estimated_cost_usd", "zuno.outcome", "zuno.run_id"];
const FIRST_ROW = "zuno.model";
const FIRST_NAMED = ["zuno.agent", "zuno.client", "zuno.estimated_cost_usd", "zuno.model"];
const LAST_ROW = "zuno.run_id";
const LAST_NAMED = ["zuno.persona", "zuno.run_id"];
const NEVER = "zuno.user_sub";
let chatSession = "";   // the chat take's session id, for the trace take of the same run (one process plays both)
const WAIT_FOR_TRACE_MS = 180000;
const READY = [".SearchForm", ".SearchTracePage", "[data-testid='SearchForm']", "#jaeger-ui-root", "main"];       // guess (Jaeger UI)
// A result's title link. Never a bare a[href*='/trace/']: the page's own "Compare" link holds /trace/ too, and the
// rescout of 2026-11-16 followed it before the results were drawn.
const RESULT = [".ResultItem a.ResultItemTitle--item", ".ResultItem a[href*='/trace/']:not([href*='...']):not([href*='compare'])"];   // both seen live, 2026-11-16
const NO_RESULT = /No trace results|No traces? found/i;
const SPAN_NAME = [".span-row .span-name", ".span-name", "[data-testid='span-name']"];                                      // guess
const DETAIL = [".detail-row", ".SpanDetail", "[data-testid='span-detail']"];                                              // guess
const TAGS_HEADER = [".detail-row .AccordianKeyValues--header:has-text('Tags')", ".AccordianKeyValues--header:has-text('Tags')", "[role='switch']:has-text('Tags')"];   // guess

// The 15 minutes are given as two instants too (microseconds, as the form's "Find Traces" writes them): with
// `lookback` alone the search answered traces hours old (the take of 2026-11-16 opened one from 3 h 30 before).
// A scout asks nothing, so it has no turn of its own to find: it looks back six hours instead (read only), which
// lets it open the trace of an earlier Tekos answer and tell what a take's `tags` pictures will hold.
const searchAddress = (base, scout = false) => `${base}/search?service=${SEARCH.service}&operation=${SEARCH.operation}`
  + `&tags=${encodeURIComponent(JSON.stringify(SEARCH.tags))}&lookback=${scout ? "6h" : SEARCH.lookback}&start=${(Date.now() - (scout ? 360 : 15) * 60000) * 1000}&end=${Date.now() * 1000}&limit=20`;

export async function enter(ctx) {
  const { page, domain, take, state } = ctx;
  if (take.name === "trace") {
    state.writes = [];
    // Read only: any request to the Tempo UI that is not a GET is kept, and fails the take.
    page.on("request", (r) => { if (r.url().startsWith(tempo(domain)) && !["GET", "HEAD", "OPTIONS"].includes(r.method())) state.writes.push(`${r.method()} ${new URL(r.url()).pathname}`); });
    await proxySignIn({ ...ctx, base: tempo(domain) }, take.persona, { changes, what: "the Tempo search UI", ready: READY, authorize: TEMPO_AUTHORIZE });
    return;
  }
  await warm(page, ctx.base);
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
  chatSession = String(id || "");
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
async function search(page, base, scout = false) {
  // The Tempo UI is slow to load (a goto past 30 s on 2026-11-16): 90 s, and once more if it did not come.
  await page.goto(searchAddress(base, scout), { timeout: 90000 }).catch(() => page.goto(searchAddress(base, scout), { timeout: 90000 }));
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
  // The results are drawn after the page: a result, or the page's own "no result" words, is waited for (20 s).
  await waitUntil(page, { what: "the search's results", timeoutMs: 20000,
    done: async () => (await firstVisible(page, RESULT)) || NO_RESULT.test(await page.locator("body").innerText().catch(() => "")) || undefined }).catch(() => {});
  await page.waitForTimeout(800);
  const first = await firstVisible(page, RESULT);
  return first ? { matched: first.matched, count: await page.locator(first.matched).count() } : { matched: "", count: 0 };
}

// Open the newest trace of the results, then a model_call span, then its tags: what is on screen at each step.
async function openTrace(page, found) {
  await click(page.locator(found.matched).first(), { changes });
  await page.waitForURL((u) => /\/trace\/[0-9a-f]{8,}/.test(u.pathname) && !/compare|\.\.\./.test(u.pathname), { timeout: 30000 });
  await waitUntil(page, { what: "the trace's spans", timeoutMs: 30000, done: async () => (await firstVisible(page, SPAN_NAME)) || undefined });
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(1000);
}

// The ONE exception to the click guard, by name. The Jaeger UI gives its span rows and its accordions the role
// "switch" (scout of 2026-11-16: the guard refused them). They are folds of the trace page, kept nowhere: not a
// setting of the persona. fold() clicks such an element directly, and ONLY such an element: a span's name inside a
// span row, or the header of the accordion "Tags" inside a span's detail. Anything else is refused here too, so the
// guard is not weakened for a real switch.
const FOLDS = {
  span: (el) => Boolean(el.closest(".span-row, [data-testid='span-view']")) && !el.closest(".detail-row"),
  tags: (el) => /^\s*Tags\b/.test(el.innerText || "") && Boolean(el.closest(".AccordianKeyValues, .detail-row, [data-testid='span-detail']")) && !el.matches("input, [type='checkbox']"),
  // the arrow that folds the JSON value of zuno.groups: inside that tag's row of a span's detail, and nowhere else
  groups: (el) => { const row = el.closest("tr"); return Boolean(row && row.closest(".detail-row, .SpanDetail, [data-testid='span-detail']") && ((row.cells[0] || {}).innerText || "").trim() === "zuno.groups") && !el.matches("input, [type='checkbox'], a[href]") && !/copy|json/i.test(el.innerText || ""); },
};
async function fold(target, kind) {
  const allowed = await read(target, FOLDS[kind]);
  if (!allowed) throw new Error(`refused to click: not the ${{ span: "name of a span in its row", tags: "Tags accordion of a span's detail", groups: "fold of zuno.groups in a span's detail" }[kind]} of the Jaeger UI`);
  await target.click({ timeout: 15000 });
}

async function openSpan(page) {
  const name = await firstVisible(page, SPAN_NAME);
  const spans = page.locator(name.matched).filter({ hasText: SPAN });
  if (!(await spans.count())) throw new Error(`the trace holds no ${SPAN} span on screen (${name.matched})`);
  await fold(spans.first(), "span");
  const detail = await waitUntil(page, { what: "the span's detail", timeoutMs: 15000, done: async () => (await firstVisible(page, DETAIL)) || undefined });
  const header = await firstVisible(page, TAGS_HEADER);
  if (header) { await fold(page.locator(header.matched).first(), "tags"); await page.waitForTimeout(800); }
  await page.mouse.move(640, 790);
  const text = await page.locator(detail.matched).first().innerText().catch(() => "");
  const run = (text.replace(/\s+/g, " ").match(/zuno\.run_id\s*=?\s*(\S+)/) || [])[1] || "";
  return { detail: detail.matched, tags_header: header ? header.matched : "", tags: TAGS.filter((tag) => text.includes(tag)), run_id: run,
           error: /\berror\s*=?\s*true\b|otel\.status_code\s*=?\s*ERROR/i.test(text.replace(/\s+/g, " ")) };
}

// Fold the JSON list of zuno.groups with the UI's own arrow (guess: the arrow's element was never seen, only its
// picture, a "▼" before the "["): the candidates of the value's cell are tried one by one until the row gets shorter.
// {collapsed, rows_high_before, rows_high_after}; nothing is thrown when it cannot: the pictures' checks decide.
async function collapseGroups(page, detail) {
  const row = page.locator(detail).first().locator("tr").filter({ has: page.getByText("zuno.groups", { exact: true }) }).first();
  if (!(await row.count())) return { collapsed: false, absent: true };
  const high = async () => Math.round(((await row.boundingBox().catch(() => null)) || { height: 0 }).height);
  const before = await high();
  if (before < 60) return { collapsed: false, already_short: true, high_before: before, high_after: before };
  const cell = row.locator("td").nth(1);
  for (const selector of ["[aria-expanded='true']", "[role='button']", "[class*='collapse' i]", "[class*='expand' i]", "[class*='toggle' i]", "[class*='icon' i]"]) {
    const arrow = cell.locator(selector).first();
    if (!(await arrow.count()) || !(await arrow.isVisible().catch(() => false))) continue;
    const done = await fold(arrow, "groups").then(() => true).catch(() => false);
    await page.waitForTimeout(500);
    const after = await high();
    if (done && after < before - 40) return { collapsed: true, by: selector, high_before: before, high_after: after };
  }
  return { collapsed: false, high_before: before, high_after: await high() };
}

// Frame the span's tag list, by scrolling only: the row AFTER `tag`'s becomes the last of the window, its bottom on
// the window's, so `tag`'s row is whole, one row above the edge. When there is no next row, `tag`'s own row is the
// last, eight pixels above the edge; when the next row is NEVER's, `tag`'s row ends exactly on the edge. Then what is DRAWN, for each of TAGS (see the header),
// and whether ANY part of NEVER is in the window. {drawn: {tag: boolean}, never: boolean}.
async function placeTags(page, detail, tag) {
  const box = page.locator(detail).first();
  const cell = box.getByText(tag, { exact: true }).first();
  if (await cell.count()) {
    await read(cell, (el, never) => {
      const move = (dy) => {
        const before = window.scrollY;
        window.scrollBy(0, dy);
        if (window.scrollY !== before) return;
        for (let up = el.parentElement; up; up = up.parentElement) if (up.scrollHeight > up.clientHeight + 4) { const was = up.scrollTop; up.scrollTop += dy; if (up.scrollTop !== was) return; }
      };
      const row = el.closest("tr") || el;
      let next = row.nextElementSibling;
      const forbidden = Boolean(next && ((next.cells && next.cells[0] ? next.cells[0].innerText : next.innerText) || "").trim().startsWith(never));
      if (forbidden) next = null;
      (next || row).scrollIntoView({ block: "end" });
      move((next || row).getBoundingClientRect().bottom - window.innerHeight + (next ? 2 : forbidden ? 0 : 8));
    }, NEVER);
  }
  await page.mouse.move(640, 60);   // away from the rows: a row under the pointer draws its Copy and JSON buttons over its value
  await page.waitForTimeout(500);
  const drawn = {};
  for (const tag of TAGS) {
    const cell = box.getByText(tag, { exact: true }).first();
    // The WHOLE row: inside the window from its top to its bottom, and at three places of it (the top and the bottom
    // of its label, the middle of its value) the row itself is what is drawn there.
    drawn[tag] = (await cell.count()) > 0 && (await read(cell, (el) => {
      const row = el.closest("tr") || el.parentElement || el;
      const at = row.getBoundingClientRect();
      if (!at.width || at.height < 4 || at.top < 0 || at.bottom > window.innerHeight + 0.5) return false;
      return [[at.left + 12, at.top + 2], [at.left + 12, at.bottom - 2], [at.left + at.width * 0.4, at.top + at.height / 2]]
        .every(([x, y]) => { const seen = document.elementFromPoint(x, y); return Boolean(seen && row.contains(seen)); });
    }).catch(() => false));
  }
  // Any part of the row counts: its key cell and what follows it on the same line, a pixel inside the window is enough.
  const sub = box.getByText(NEVER, { exact: true }).first();
  const never = (await sub.count()) > 0 && (await read(sub, (el) => {
    const line = (el.closest("tr") || el.parentElement || el).getBoundingClientRect();
    if (line.bottom <= 0 || line.top >= window.innerHeight) return false;
    for (let y = Math.max(line.top, 0) + 1; y < Math.min(line.bottom, window.innerHeight); y += 2) {
      const seen = document.elementFromPoint(line.left + 12, y);
      if (seen && ((el.closest("tr") || el).contains(seen) || seen === el)) return true;
    }
    return false;
  }).catch(() => true));
  return { drawn, never };
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
  if (span.error) throw new Error(`the newest ${SPAN} span of the search is a FAILED call (its tags say error): not the picture of a traced answer; take again once a Tekos answer is the newest`);
  const missing = TAGS.filter((tag) => !span.tags.includes(tag));
  if (span.tags.length < 3 || !span.tags.includes("zuno.persona")) throw new Error(`the ${SPAN} span does not show its tags (seen: ${span.tags.join(", ") || "none"})`);
  if (missing.length) log(`tags of the page's row 3:00 NOT in the span's detail: ${missing.join(", ")}`);
  // The run of the span against the session the chat take asked in: the proof that the trace is that turn's.
  state.notes.run_id_is_the_chat_session = Boolean(chatSession && span.run_id === chatSession);
  log(!span.run_id ? "the span shows no zuno.run_id" : !chatSession ? "the span shows a zuno.run_id; the chat take of this run gave no session id to compare it with"
    : state.notes.run_id_is_the_chat_session ? `the span's zuno.run_id is the chat take's session ${chatSession}` : `the span's zuno.run_id (${span.run_id.slice(0, 40)}) is NOT the chat take's session ${chatSession}: check which turn the trace is`);
  log(`the gateway's span ${(await page.locator("body").innerText()).includes(prompts["0:45"]) ? "page SHOWS the question's text somewhere: check tags.png" : "page shows no question text"}`);
  const groups = await collapseGroups(page, span.detail);
  state.notes.groups_collapsed = groups.collapsed;
  log(groups.absent ? "the span carries no zuno.groups" : groups.collapsed ? `zuno.groups folded with the UI's own arrow (${groups.high_before} px high, then ${groups.high_after})`
    : groups.already_short ? "zuno.groups is one line: nothing to fold" : `zuno.groups could NOT be folded (${groups.high_before} px high): the pictures are framed around it`);
  const wrong = [];
  for (const [marker, where, named] of [["tags", FIRST_ROW, FIRST_NAMED], ["tags-run", LAST_ROW, LAST_NAMED]]) {
    const { drawn, never } = await placeTags(page, span.detail, where);
    const shown = TAGS.filter((tag) => drawn[tag]);
    log(`${marker}: tags drawn in the window: ${shown.join(", ") || "none"}; ${NEVER} ${never ? "IS in the window" : "is not in the window"}`);
    state.notes[marker === "tags" ? "tags_in_window" : "tags_run_in_window"] = shown.length;
    wrong.push(...named.filter((tag) => span.tags.includes(tag) && !drawn[tag]).map((tag) => `${tag} is not drawn at ${marker}`));
    // Before the marker: a picture that would hold the persona's subject is not made.
    if (never) throw new Error(`${NEVER} (the persona's Keycloak subject) is in the window at ${marker}: that picture is not made${wrong.length ? `; ${wrong.join(", ")}` : ""}`);
    await page.waitForTimeout(800);
    await mark(marker);
  }
  if (wrong.length) throw new Error(`the span's tags are not all drawn inside the window (${wrong.join(", ")}): the picture would not hold the row's proof`);
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
      found = await search(page, base, true);
      return { url: page.url().replace(/[#].*/, ""), results: found.count, selector: found.matched,
               words: await wordsOnScreen(page, [/ai-gateway/, /model_call/, /zuno\.persona/, /Find Traces/, /Last 15 Minutes|15m/]) };
    });
    await step("trace", async () => {
      if (!found.count) return { skipped: "the search lists no trace of the last six hours: ask Tekos as consultant-02, then scout again" };
      await openTrace(page, found);
      const name = await firstVisible(page, SPAN_NAME);
      return { url: page.url().replace(/\/trace\/.*/, "/trace/<id>"), span_selector: name.matched, spans: await page.locator(name.matched).count(),
               model_call_spans: await page.locator(name.matched).filter({ hasText: SPAN }).count() };
    });
    // The two pictures a take makes of the span's tags, each a step with its own image; nothing is clicked after
    // the span and its Tags are opened.
    let span = null;
    await step("tags", async () => {
      if (!found.count) return { skipped: "no trace" };
      span = await openSpan(page);
      const { run_id, ...seen } = span;   // the run's id is not kept by a scout
      const groups = await collapseGroups(page, span.detail);
      const first = await placeTags(page, span.detail, FIRST_ROW);
      return { ...seen, groups, run_id_shown: Boolean(run_id), span_is_an_error: span.error, in_window: first.drawn,
               caption_in_window: FIRST_NAMED.filter((tag) => span.tags.includes(tag)).every((tag) => first.drawn[tag]), user_sub_in_window: first.never };
    });
    await step("tags-run", async () => {
      if (!span) return { skipped: "no span opened" };
      const last = await placeTags(page, span.detail, LAST_ROW);
      return { in_window: last.drawn, proof_in_window: LAST_NAMED.every((tag) => last.drawn[tag]), user_sub_in_window: last.never,
               process_line_on_screen: await page.getByText(/^Process/).first().isVisible().catch(() => false) };
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
