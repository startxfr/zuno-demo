// WP-288 / ADR-0618: the walkthrough of "Dify", 5-minute version, for evaluations/browser/record.mjs.
//
// The rows of docs/demo/scenarios/experiences/dify.md, as consultant-02 at the front door and Dify's single
// administrator behind it: the Keycloak form (login), Studio with its three applications (studio, row 0:00), Zuno
// Agent opened (agent) and asked the page's question (q-sent, q-done, row 0:45), Zuno Confluence Search opened
// (workflow), its run form filled with the page's topic (run-form) and run (run-done, row 2:30), then end. Rows 3:45
// and 4:15 are words. The prompts are the page's, verbatim (`node record.mjs --check dify`).
//
// TWO credentials (the owner's decision of 2026-11-16): the persona password at the front door, and the password of
// dify-admin@zuno.local on Dify's own form, held by the recorder (`secrets`), typed by it into that one field, never
// marked, described, logged or written.
//
// What it costs and leaves: one Agent turn and one workflow run, model and tool calls made as consultant-02 through
// the token proxy (its budget). The Agent's conversation is deleted by its id when Dify's API lists it. The
// workflow's run stays in the application's run log: Dify has no way to delete one. The applications themselves are
// never changed: the editor's own saves are refused before they leave the browser (_dify.mjs).
//
// The answer shows real Confluence page titles of the space SXSI: the owner accepts them on a public picture
// (2026-11-16). NOTHING was seen live when this was written: every selector is a guess; scout() reports what is there,
// sends nothing and creates nothing.
import { click, describe, firstVisible, newText, waitUntil, wordsOnScreen } from "./_helpers.mjs";
import { dify, difyApi, difyApps, difyAsk, difyConversations, difyGuard, difyOpen, difyRuns, difySignIn } from "./_dify.mjs";

export const persona = "consultant-02";
export const secrets = ["DIFY_ADMIN_PASSWORD"];
export const page = "docs/demo/scenarios/experiences/dify.md";
export const viewport = { width: 1280, height: 800 };
export const markers = ["login", "studio", "agent", "q-sent", "q-done", "workflow", "run-form", "run-done", "end"];
export const motion_from = "studio";   // the two sign-in forms are never shown as motion
export const changes = [];
export const prompts = { "0:45": "Find our onboarding pages in Confluence", "2:30": "onboarding" };
export const url = dify.url;
export const sends = dify.sends;

const APPS = { agent: "Zuno Agent", docs: "Zuno Technical Documentation", workflow: "Zuno Confluence Search" };
const TOOL = "confluence.page.search";   // the page: the tool both applications call
const RUN_TIMEOUT_MS = 120000;           // the page: about 3 s; D1 is a stall of the first run

export async function enter(ctx) {
  ctx.state.refused = await difyGuard(ctx.page);
  await difySignIn(ctx, persona);
  const apps = await difyApps(ctx.page);
  if (!apps) throw new Error("Dify's application list could not be read (GET /console/api/apps): the take could not tell what it creates");
  const absent = Object.values(APPS).filter((name) => !apps[name]);
  if (absent.length) throw new Error(`Studio does not hold ${absent.join(", ")}: the page's three applications are imported at every install`);
  ctx.state.apps = apps;
}

// What the take could leave and can delete: the conversations of Zuno Agent. The workflow's runs cannot be deleted:
// they are counted in the log, not compared.
export async function owned({ page, state }) {
  const ids = await difyConversations(page, state.apps[APPS.agent].id);
  if (!ids) throw new Error("the conversations of Zuno Agent could not be read");
  if (!state.before) state.before = ids;   // the first call, before anything is sent
  return ids.map((id) => ({ kind: "conversation", id }));
}

export async function run({ page, base, mark, log, state }) {
  // Studio draws skeleton cards first: its three applications are waited for, right of the left menu (which names
  // the web apps too), a minute.
  const cards = async () => {
    const missing = [];
    for (const name of Object.values(APPS)) {
      const named = page.getByText(name, { exact: true });
      let seen = false;
      for (let i = 0; i < Math.min(await named.count(), 10) && !seen; i += 1) { const box = await named.nth(i).boundingBox().catch(() => null); seen = Boolean(box && box.width > 0 && box.x >= 260); }
      if (!seen) missing.push(name);
    }
    return missing;
  };
  await waitUntil(page, { what: "Studio's cards", timeoutMs: 60000, done: async () => !(await cards()).length || undefined })
    .catch(async () => { throw new Error(`Studio does not show the card of ${(await cards()).join(", ")} within a minute`); });
  await page.waitForTimeout(800);
  await mark("studio");

  await difyOpen(page, base, APPS.agent, { changes, ready: dify.CHAT_INPUT });
  if (!(await firstVisible(page, dify.CHAT_INPUT))) throw new Error(`Zuno Agent's page has no chat input (${dify.CHAT_INPUT.join(" | ")})`);
  await mark("agent");

  const before = await page.locator("body").innerText();
  state.sent = true;   // from here a conversation may exist: cleanup() must not stay silent
  const turn = await difyAsk(page, prompts["0:45"], state, { sent: () => mark("q-sent") });
  const answer = await newText(page, before);
  log(`the Agent's turn took ${turn.seconds} s; the tool ${TOOL} is ${answer.some((line) => line.includes(TOOL)) ? "" : "NOT "}named on screen; ${answer.length} new lines`);
  if (!answer.some((line) => line && !line.includes(prompts["0:45"]))) throw new Error("the Agent's answer shows no text");
  await mark("q-done");

  await difyOpen(page, base, APPS.workflow, { changes, ready: dify.RUN });   // back to Studio by its own link
  const runs = await difyRuns(page, state.apps[APPS.workflow].id);
  await mark("workflow");
  const open = await firstVisible(page, dify.RUN);
  if (!open) throw new Error(`the workflow's Run button was not found (${dify.RUN.join(" | ")})`);
  await click(open, { changes });
  const topic = await waitUntil(page, { what: "the run form's Topic field", timeoutMs: 20000, done: async () => (await firstVisible(page, dify.TOPIC)) || undefined });
  await topic.click();
  await page.keyboard.type(prompts["2:30"], { delay: 40 });
  await page.waitForTimeout(600);
  await mark("run-form");
  const start = await firstVisible(page, dify.START_RUN);
  if (!start) throw new Error(`the run form's start button was not found (${dify.START_RUN.join(" | ")})`);
  state.ran = true;
  await click(start, { changes });
  const done = await waitUntil(page, { what: "the workflow's run", timeoutMs: RUN_TIMEOUT_MS, everyMs: 1000, done: async () => {
    const now = await difyRuns(page, state.apps[APPS.workflow].id);
    const fresh = now && runs ? now.filter((r) => !runs.some((old) => old.id === r.id)) : [];
    if (fresh.some((r) => /failed|stopped/.test(r.status))) throw new Error(`the workflow's run ${fresh[0].status}`);
    return fresh.find((r) => r.status === "succeeded") || undefined;
  } });
  log(`workflow run ${done.id} succeeded; it stays in the application's run log (Dify cannot delete a run)`);
  await page.waitForTimeout(2000);
  await mark("run-done");

  await page.waitForTimeout(800);
  await mark("end");
  const refused = state.refused();
  if (refused.length) log(`saves of the applications refused in the browser: ${refused.join(", ")}`);
  log(`writes the take sent to Dify, in order: ${state.refused.sent().answered.join("; ") || state.refused.sent().sent.join("; ") || "none"}`);
  const through = state.refused.through();
  if (through.length) throw new Error(`a write to Dify that the take does not allow got through: ${through.join(", ")}: an application may have been changed, check it`);
}

// What a take will meet, for the price of the two sign-ins: Studio, each of the two applications' pages with their
// controls, and what Dify's API answers. Nothing is typed in a chat, nothing is run, no conversation exists afterwards.
export async function scout({ page, base, step, state }) {
  if (!state.scout) throw new Error("scout() runs only in scout mode");
  const agent = state.apps[APPS.agent].id;
  const flow = state.apps[APPS.workflow].id;
  const before = state.before.length;
  await step("sign-in", async () => ({ ...state.dify, apps: Object.fromEntries(Object.entries(state.apps).map(([name, a]) => [name, a.mode])) }));
  await step("studio", async () => ({ words: await wordsOnScreen(page, Object.values(APPS).map((name) => new RegExp(name))),
                                      exact_matches: Object.fromEntries(await Promise.all(Object.values(APPS).map(async (name) => [name, await page.getByText(name, { exact: true }).count()]))) }));
  await step("api", async () => {
    const runs = await difyRuns(page, flow);
    const who = await difyApi(page, "GET", "/console/api/account/profile").catch(() => ({ status: 0 }));
    return { conversations: before, workflow_runs: runs ? runs.length : null, profile_status: who.status };
  });
  await step("agent", async () => {
    const address = await difyOpen(page, base, APPS.agent, { changes, ready: [...dify.CHAT_INPUT, "[contenteditable='true']"] });
    const input = await firstVisible(page, dify.CHAT_INPUT);
    return { editable_boxes: await page.locator("[contenteditable='true']").count(), spinner_gone: !(await page.locator("[role='status'], .spin-animation, .animate-spin").first().isVisible().catch(() => false)), url: address.replace(/[0-9a-f]{8}-[0-9a-f-]{27}/g, "<id>"), selector: input ? input.matched : null,
             words: await wordsOnScreen(page, [/confluence\.page\.search/, /Debug|Preview/, /Publish/]),
             controls: (await describe(page, "main, body", 60)).filter((el) => el.attrs.placeholder || el.attrs["aria-label"]).slice(0, 30) };
  });
  await step("workflow", async () => {
    const address = await difyOpen(page, base, APPS.workflow, { changes, ready: dify.RUN });   // back to Studio by its own link, as a take
    const open = await firstVisible(page, dify.RUN);
    return { url: address.replace(/[0-9a-f]{8}-[0-9a-f-]{27}/g, "<id>"), run_selector: open ? open.matched : null,
             words: await wordsOnScreen(page, [/confluence\.page\.search/, /Summarise/, /Start/, /End/, /Test Run/, /Publish/]) };
  });
  await step("run-form", async () => {
    const open = await firstVisible(page, dify.RUN);
    if (!open) throw new Error(`no Run button among ${dify.RUN.join(" | ")}`);
    const text = await page.locator("body").innerText();
    await click(open, { changes });   // opens the form: nothing runs until its own start button
    await page.waitForTimeout(1500);
    const start = await firstVisible(page, dify.START_RUN);
    return { text: (await newText(page, text)).slice(0, 15).map((l) => l.slice(0, 60)), start_selector: start ? start.matched : null,
             topic_selector: ((await firstVisible(page, dify.TOPIC)) || {}).matched || "", fields: await page.locator("input, textarea").count() };
  });
  await step("closed", async () => {
    await page.keyboard.press("Escape");
    const after = await difyConversations(page, agent);
    if (!after || after.length !== before) throw new Error(`Zuno Agent holds ${after ? after.length : "?"} conversations after the scout, ${before} before it`);
    if (state.refused.through().length) throw new Error(`a write to Dify that the scout does not allow got through: ${state.refused.through().join(", ")}`);
    return { conversations: after.length, saves_refused: state.refused(), writes_through: state.refused.through() };
  });
}

// Delete the conversation the Agent's turn created, by its id, and nothing else. It is the ONE conversation that was
// not there before the take; when Dify's API lists none (a debug chat may not be kept as a conversation), nothing is
// deleted and the log says so; when it lists several, nothing is deleted and the take fails.
export async function cleanup({ page, log, state }) {
  if (!state.sent) return null;
  const app = state.apps[APPS.agent].id;
  const now = await difyConversations(page, app);
  if (!now) throw new Error("the conversations of Zuno Agent could not be read after the take: one may remain, check Zuno Agent's logs by hand");
  const fresh = now.filter((id) => !state.before.includes(id));
  if (!fresh.length) { log("Dify lists no new conversation for Zuno Agent: its debug chat left none to delete"); return null; }
  if (fresh.length > 1) throw new Error(`Zuno Agent has ${fresh.length} new conversations: the take's cannot be told from another's, nothing was deleted`);
  state.created.push({ kind: "conversation", id: fresh[0] });
  const gone = await difyApi(page, "DELETE", `/console/api/apps/${app}/chat-conversations/${fresh[0]}`).catch(() => ({ status: 0 }));
  const left = await difyConversations(page, app);
  if (![200, 204].includes(gone.status) || !left || left.includes(fresh[0])) {
    throw new Error(`the conversation ${fresh[0]} of Zuno Agent was NOT deleted: DELETE answered HTTP ${gone.status}; delete it by hand in Zuno Agent's logs`);
  }
  log(`conversation ${fresh[0]} deleted`);
  return true;
}
