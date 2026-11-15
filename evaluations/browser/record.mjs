// WP-284 / ADR-0617: record one demo's walkthrough in the browser, for the GIF of its 5-minute version.
//
// Plays evaluations/browser/walkthroughs/<id>.mjs in one Playwright context with recordVideo. The walkthrough calls
// mark(name) at each key moment: the recorder notes the time since t0 (taken right after newPage(), the video's time
// base) and saves a screenshot <name>.png. After the walkthrough, pass or fail, it runs the walkthrough's cleanup()
// (the chat the take created is deleted, by its id), closes the context and leaves in OUT:
//
//   recording.webm   the whole take, never published
//   markers.json     {demo, persona, viewport, started, motion_from, markers: [{name, t, png}], chat_deleted, status,
//                    detail}; motion_from: the first marker a motion segment of the cut may start at
//   <marker>.png     one per marker reached (and failed.png when the walkthrough stopped)
//
// This is not the browser check (run.mjs, WP-243, untouched): it carries its own copy of the Keycloak helper.
//
// Run through evaluations/browser/record.sh (podman, the Playwright image whose browsers match playwright@1.48.0).
// Environment: DEMO (the walkthrough id), APPS_DOMAIN, PERSONA_PASSWORD, OUT; RECORD_BASE_URL replaces the demo's
// route (the offline test). `node record.mjs --check <id>` only loads the walkthrough and checks its shape and that its
// prompts are the page's own: no browser, no cluster, no password.
//
// RECORD_SCOUT=1 (record.sh <id> [OUT] --scout) plays the walkthrough's scout(ctx) instead: it signs in, reaches the
// first screen and opens the menus the walkthrough will use, WITHOUT sending a prompt, so a selector is checked for
// the price of a sign-in. No video, no chat, no model call: every request that would send a chat message is refused
// and fails the scout. It leaves scout.json ({demo, persona, started, steps: [{step, ok, selector, png, text, ...}],
// status, detail}) and one scout-<step>.png per step; last line `SCOUT: done` (exit 0) or `SCOUT: failed <steps>`
// (exit 1).
// Exit code: 0 every marker reached and the cleanup done, 1 the walkthrough or the cleanup failed, 2 usage/environment.
// The last line printed is `RESULT: PASS` or `RESULT: FAIL <detail>`.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const MARKER_NAME = /^[a-z0-9][a-z0-9-]*$/;

function usage(message) {
  console.error(message);
  process.exit(2);
}

async function load(id) {
  if (!id || !MARKER_NAME.test(id)) usage("DEMO must be a walkthrough id, e.g. open-webui");
  const file = path.join(here, "walkthroughs", `${id}.mjs`);
  if (!fs.existsSync(file)) usage(`no walkthrough for ${id}: ${path.relative(process.cwd(), file)} is missing`);
  const walk = await import(file);
  const problems = shapeProblems(walk);
  if (problems.length) usage(`walkthrough ${id}: ${problems.join("; ")}`);
  return walk;
}

// What every walkthrough exports: persona, viewport {width, height}, markers (the names it marks, in order),
// motion_from (one of them: no motion segment of the cut starts before it, so a sign-in is never shown as motion),
// url(domain) (the page it starts from), run(ctx); optionally prompts {time: text}, page (the demo page, from the
// repository root) and cleanup(ctx) -> {chat_deleted}.
export function shapeProblems(walk) {
  const problems = [];
  if (typeof walk.persona !== "string" || !walk.persona) problems.push("`persona` must be a persona name");
  const v = walk.viewport;
  if (!v || !Number.isInteger(v.width) || !Number.isInteger(v.height)) problems.push("`viewport` needs width and height");
  if (!Array.isArray(walk.markers) || !walk.markers.length) problems.push("`markers` must list the marker names");
  else {
    for (const name of walk.markers) if (!MARKER_NAME.test(name)) problems.push(`marker name ${JSON.stringify(name)}`);
    if (new Set(walk.markers).size !== walk.markers.length) problems.push("marker names must be unique");
  }
  if (!Array.isArray(walk.markers) || !walk.markers.includes(walk.motion_from)) problems.push("`motion_from` must be one of the markers");
  if (typeof walk.url !== "function") problems.push("`url(domain)` is missing");
  if (typeof walk.run !== "function") problems.push("`run(ctx)` is missing");
  if (walk.cleanup !== undefined && typeof walk.cleanup !== "function") problems.push("`cleanup` must be a function");
  if (walk.scout !== undefined && typeof walk.scout !== "function") problems.push("`scout` must be a function");
  return problems;
}

// The prompts a walkthrough types must be the page's own, verbatim: each one is a backticked text in the row of its time.
export function promptProblems(walk, pageText) {
  const problems = [];
  for (const [time, prompt] of Object.entries(walk.prompts || {})) {
    const row = pageText.split("\n").find((line) => line.startsWith(`| ${time} |`));
    if (!row) problems.push(`the page has no row ${time}`);
    else if (!row.includes("`" + prompt + "`")) problems.push(`the prompt of ${time} is not the page's: ${prompt}`);
  }
  return problems;
}

if (process.argv[2] === "--check") {
  const walk = await load(process.argv[3]);
  const problems = [];
  if (walk.page) {
    const file = path.join(here, "..", "..", walk.page);
    if (!fs.existsSync(file)) problems.push(`${walk.page} is missing`);
    else problems.push(...promptProblems(walk, fs.readFileSync(file, "utf8")));
  }
  for (const problem of problems) console.error(problem);
  console.log(`${process.argv[3]}: persona ${walk.persona}, ${walk.viewport.width}x${walk.viewport.height}, markers ${walk.markers.join(", ")}; motion from ${walk.motion_from}`);
  process.exit(problems.length ? 1 : 0);
}

const id = process.env.DEMO || "";
const domain = process.env.APPS_DOMAIN || "";
const password = process.env.PERSONA_PASSWORD || "";
const out = process.env.OUT || "/out";
if (!domain || !password) usage("APPS_DOMAIN and PERSONA_PASSWORD are required");
const walk = await load(id);
fs.mkdirSync(out, { recursive: true });

async function keycloak(page, username) {
  // Stock Keycloak theme: #username, #password, #kc-login. The recorder's own copy (run.mjs is not shared).
  await page.fill("#username", username);
  await page.fill("#password", password);
  await Promise.all([page.waitForLoadState("domcontentloaded"), page.click("#kc-login")]);
}

const { chromium } = await import("playwright");

if (process.env.RECORD_SCOUT === "1") {
  if (!walk.scout) usage(`walkthrough ${id} has no scout()`);
  const report = { demo: id, persona: walk.persona, viewport: walk.viewport, started: new Date().toISOString(),
                   steps: [], status: "fail", detail: "" };
  const browser = await chromium.launch();
  const context = await browser.newContext({ ignoreHTTPSErrors: true, locale: "en-US", viewport: walk.viewport });
  const page = await context.newPage();
  const t0 = Date.now();
  const log = (text) => console.log(`${((Date.now() - t0) / 1000).toFixed(1).padStart(6)}s  ${text}`);
  // A scout never sends a chat message: the calls that would are refused before they leave the browser.
  const refused = [];
  await page.route(/\/api\/(chat\/completions|chat\/completed|v1\/chats\/new|v1\/chats\/[^/]+$|v1\/tasks\/)/, (route) => {
    if (route.request().method() === "GET") return route.continue();
    refused.push(`${route.request().method()} ${new URL(route.request().url()).pathname}`);
    return route.abort();
  });
  // step(name, fn): fn returns what it found ({selector, text, ...}); a step that throws is kept as failed and the
  // scout goes on, so one run says everything it can.
  const step = async (name, fn) => {
    const entry = { step: name, ok: true, png: `scout-${name}.png` };
    try {
      Object.assign(entry, (await fn()) || {});
    } catch (e) {
      entry.ok = false;
      entry.error = String(e && e.message ? e.message : e).split("\n")[0].slice(0, 300);
    }
    await page.screenshot({ path: path.join(out, entry.png) }).catch(() => { entry.png = null; });
    report.steps.push(entry);
    log(`scout ${name}: ${entry.ok ? "ok" : "FAILED " + entry.error}`);
    return entry;
  };
  const ctx = { page, domain, log, step, state: { scout: true }, mark: async () => {},
                keycloak: (username) => keycloak(page, username), base: process.env.RECORD_BASE_URL || walk.url(domain) };
  try {
    await walk.scout(ctx);
  } catch (e) {
    report.steps.push({ step: "scout", ok: false, png: null, error: String(e && e.message ? e.message : e).split("\n")[0].slice(0, 300) });
  }
  await context.close();
  await browser.close();
  const bad = report.steps.filter((s) => !s.ok).map((s) => s.step);
  if (refused.length) bad.push(`a chat message was about to be sent (${refused.join(", ")})`);
  report.refused_requests = refused;
  report.status = bad.length ? "fail" : "done";
  report.detail = bad.length ? `failed: ${bad.join(", ")}` : `${report.steps.length} steps`;
  fs.writeFileSync(path.join(out, "scout.json"), JSON.stringify(report, null, 2) + "\n");
  console.log(bad.length ? `SCOUT: failed ${bad.join(", ")}` : "SCOUT: done");
  process.exit(bad.length ? 1 : 0);
}

const record = { demo: id, persona: walk.persona, viewport: walk.viewport, started: new Date().toISOString(),
                 motion_from: walk.motion_from, markers: [], chat_deleted: false, status: "fail", detail: "" };
const browser = await chromium.launch();
const context = await browser.newContext({
  ignoreHTTPSErrors: true, locale: "en-US", viewport: walk.viewport,
  recordVideo: { dir: out, size: walk.viewport },
});
const page = await context.newPage();
const t0 = Date.now();
const log = (text) => console.log(`${((Date.now() - t0) / 1000).toFixed(1).padStart(6)}s  ${text}`);

async function mark(name) {
  const expected = walk.markers[record.markers.length];
  if (name !== expected) throw new Error(`marker ${name} out of order: ${expected || "no marker"} was expected`);
  const t = Math.round((Date.now() - t0) / 10) / 100;
  await page.screenshot({ path: path.join(out, `${name}.png`) });
  record.markers.push({ name, t, png: `${name}.png` });
  log(`marker ${name}`);
}

const state = {};
const ctx = { page, domain, mark, log, state, keycloak: (username) => keycloak(page, username),
              base: process.env.RECORD_BASE_URL || walk.url(domain) };
const failures = [];
try {
  await walk.run(ctx);
  const missing = walk.markers.slice(record.markers.length);
  if (missing.length) throw new Error(`markers not reached: ${missing.join(", ")}`);
} catch (e) {
  failures.push(String(e && e.message ? e.message : e).split("\n")[0].slice(0, 300));
  await page.screenshot({ path: path.join(out, "failed.png") }).catch(() => {});
}
// Pass or fail, what the take created is removed: a failed take must not leave its chat behind either.
try {
  const cleaned = walk.cleanup ? await walk.cleanup(ctx) : {};
  record.chat_deleted = Boolean(cleaned && cleaned.chat_deleted);
} catch (e) {
  failures.push(String(e && e.message ? e.message : e).split("\n")[0].slice(0, 300));
}
const video = page.video();
await context.close();
await browser.close();
try {
  fs.renameSync(await video.path(), path.join(out, "recording.webm"));
} catch (e) {
  failures.push(`no recording.webm: ${String(e.message || e).slice(0, 200)}`);
}
record.status = failures.length ? "fail" : "pass";
record.detail = failures.length ? failures.join("; ")
  : `${record.markers.length} markers in ${record.markers[record.markers.length - 1].t.toFixed(1)} s`;
fs.writeFileSync(path.join(out, "markers.json"), JSON.stringify(record, null, 2) + "\n");
console.log(record.status === "pass" ? "RESULT: PASS" : `RESULT: FAIL ${record.detail}`);
process.exit(failures.length ? 1 : 0);
