// WP-284 / ADR-0617: record one demo's walkthrough in the browser, for the GIF of its 5-minute version.
//
// Plays evaluations/browser/walkthroughs/<id>.mjs in one Playwright context with recordVideo. The walkthrough calls
// mark(name) at each key moment: the recorder notes the time since t0 (taken right after newPage(), the video's time
// base) and saves a screenshot <name>.png. After the walkthrough, pass or fail, it runs the walkthrough's cleanup()
// (the chat the take created is deleted, by its id), closes the context and leaves in OUT:
//
//   recording.webm   the whole take, never published
//   markers.json     {demo, kind "browser"|"terminal", persona, viewport, started, motion_from, markers: [{name, t,
//                    png}], created, cleaned, owned, status, detail}
//                    motion_from: the first marker a motion segment of the cut may start at
//                    created: [{kind, id}] what the take created; cleaned: true (all deleted), false (something may
//                    remain), null (nothing was created)
//                    owned: {before, after, same} what the persona owns (ids read in its own session after the
//                    sign-in and after the cleanup); a difference fails the take
//
// A walkthrough plays in phases: enter(ctx) signs in and reaches the first screen; owned(ctx) lists what the persona
// owns; run(ctx) plays the rows; cleanup(ctx) deletes what run created; then owned(ctx) again.
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
// and fails the scout. It leaves scout.json ({demo, persona, started, when, walkthrough_sha256, changes, steps:
// [{step, ok, selector, png, text, ...}], status "done"|"fail", detail}) and one scout-<step>.png per step; last line `SCOUT: done` (exit 0) or `SCOUT: failed <steps>`
// (exit 1).
//
// RECORD_TERMINAL=1 (record.sh <id> <OUT> --terminal) films a terminal demo (ADR-0618 clause 6): OUT already holds
// terminal.cast and terminal-steps.json, a real session captured by terminal/capture.py and passed by the text gate.
// The recorder replays those bytes at their own timing in xterm.js (terminal/replay.html, vendored, loaded from disk)
// and films the page, with the markers `start`, then `<MM-SS>-typed` and `<MM-SS>-done` for each row, then `end`. The
// replay holds still while a marker's image is saved (markers.json: terminal.held_seconds, the only time in the video
// that is not the session's own). No
// walkthrough, no sign-in, no password, no cluster: the container receives the two text files and nothing else.
// Exit code: 0 every marker reached and the cleanup done, 1 the walkthrough or the cleanup failed, 2 usage/environment.
// The last line printed is `RESULT: PASS` or `RESULT: FAIL <detail>`.
import crypto from "node:crypto";
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

// What every walkthrough exports: persona (or takes [{name, persona}], one video per persona: ctx.take and
// ctx.persona say which one is playing), viewport {width, height}, markers (the names it marks, in order),
// motion_from (one of them: no motion segment of the cut starts before it, so a sign-in is never shown as motion),
// changes (the settings the take may change, normally []), url(domain) (the page it starts from), enter(ctx),
// owned(ctx) -> [{kind, id}], run(ctx), cleanup(ctx) -> true | null (throws when something may remain), scout(ctx);
// optionally prompts {time: text}, page (the demo page, from the repository root) and sends (a RegExp: the requests
// that send a message or create something, refused in a scout unless they are a GET).
export function shapeProblems(walk) {
  const problems = [];
  if (walk.takes !== undefined) {
    if (!Array.isArray(walk.takes) || !walk.takes.length) problems.push("`takes` must list {name, persona}");
    else {
      for (const t of walk.takes) {
        if (!t || !MARKER_NAME.test(t.name || "") || typeof t.persona !== "string" || !t.persona) problems.push(`take ${JSON.stringify(t)} needs a name and a persona`);
      }
      if (new Set(walk.takes.map((t) => t && t.name)).size !== walk.takes.length) problems.push("take names must be unique");
    }
  } else if (typeof walk.persona !== "string" || !walk.persona) problems.push("`persona` must be a persona name (or `takes`, one per persona)");
  const v = walk.viewport;
  if (!v || !Number.isInteger(v.width) || !Number.isInteger(v.height)) problems.push("`viewport` needs width and height");
  if (!Array.isArray(walk.markers) || !walk.markers.length) problems.push("`markers` must list the marker names");
  else {
    for (const name of walk.markers) if (!MARKER_NAME.test(name)) problems.push(`marker name ${JSON.stringify(name)}`);
    if (new Set(walk.markers).size !== walk.markers.length) problems.push("marker names must be unique");
  }
  if (!Array.isArray(walk.markers) || !walk.markers.includes(walk.motion_from)) problems.push("`motion_from` must be one of the markers");
  if (typeof walk.url !== "function") problems.push("`url(domain)` is missing");
  for (const phase of ["enter", "owned", "run", "cleanup"]) if (typeof walk[phase] !== "function") problems.push(`\`${phase}(ctx)\` is missing`);
  if (typeof walk.scout !== "function") problems.push("`scout(ctx)` is missing: a walkthrough is scouted before its first take");
  if (walk.sends !== undefined && !(walk.sends instanceof RegExp)) problems.push("`sends` must be a regular expression");
  if (!Array.isArray(walk.changes) || walk.changes.some((c) => typeof c !== "string")) problems.push("`changes` must list the settings the take may change ([] for none)");
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

// The identity of a walkthrough's code, computable without node (platform/demo/presenter.py computes the same): the
// sha256 over, for the shared helpers then the walkthrough, in that order: the repository-relative path as UTF-8, a 0
// byte, the file's bytes, a 0 byte. scout.json carries it, so a take can be refused when the code changed since its
// last good scout.
function walkthroughHash(id) {
  const hash = crypto.createHash("sha256");
  for (const name of ["_helpers.mjs", `${id}.mjs`]) {
    hash.update(Buffer.from(`evaluations/browser/walkthroughs/${name}`, "utf8"));
    hash.update(Buffer.from([0]));
    hash.update(fs.readFileSync(path.join(here, "walkthroughs", name)));
    hash.update(Buffer.from([0]));
  }
  return hash.digest("hex");
}

// Film the replay of a captured terminal session. Returns the exit code.
async function terminalTake(id, out) {
  const castFile = path.join(out, "terminal.cast");
  const stepsFile = path.join(out, "terminal-steps.json");
  if (!fs.existsSync(castFile) || !fs.existsSync(stepsFile)) usage(`${out} needs terminal.cast and terminal-steps.json (terminal/capture.py writes them)`);
  const lines = fs.readFileSync(castFile, "utf8").split("\n").filter(Boolean).map((line) => JSON.parse(line));
  const header = lines[0];
  const events = lines.slice(1).filter((e) => Array.isArray(e) && e[1] === "o");
  const captured = JSON.parse(fs.readFileSync(stepsFile, "utf8"));
  if (captured.demo !== id) usage(`terminal-steps.json is the capture of ${captured.demo}, not of ${id}`);
  if (header.version !== 2 || !events.length) usage("terminal.cast is not a non-empty asciicast v2 file");
  const name = (time) => time.split(":").map((part) => part.padStart(2, "0")).join("-");
  // What is marked, on the session's clock: the first prompt, each row's line typed and prompt back, the end.
  const wanted = [{ name: "start", at: Math.min(events[0][0] + 0.4, captured.steps.length ? captured.steps[0].typed : Infinity) }];
  for (const step of captured.steps) {
    wanted.push({ name: `${name(step.time)}-typed`, at: step.typed + 0.05 });   // the line is complete, Enter not pressed yet
    wanted.push({ name: `${name(step.time)}-done`, at: step.done + 0.05 });     // the prompt is back
  }
  wanted.push({ name: "end", at: events[events.length - 1][0] + 0.6 });
  // The window is the session's own (100x30 unless the demo asked for another, 80-140 x 20-40). The font is the
  // largest whole size that keeps the columns within about 1250 px (Liberation Mono advances 0.6 em): 20 px at 100
  // columns, 15 px at 136. The viewport is then measured on the page itself, before the filmed context exists.
  if (!(header.width >= 80 && header.width <= 140 && header.height >= 20 && header.height <= 40)) usage(`terminal.cast is ${header.width}x${header.height}: the window must be 80-140 columns by 20-40 rows`);
  const fontSize = Math.max(12, Math.min(26, Math.floor(1250 / (0.6 * header.width))));
  const { chromium } = await import("playwright");
  const browser = await chromium.launch();
  const replayUrl = `file://${path.join(here, "terminal", "replay.html")}`;
  const probe = await browser.newPage({ viewport: { width: 1600, height: 1400 } });
  await probe.goto(replayUrl);
  const measured = await probe.evaluate(([header, fontSize]) => window.replay.load(header, [], fontSize), [header, fontSize]);
  await probe.close();
  const viewport = { width: measured.width + 16, height: measured.height + 14 };   // the page's padding on the far sides
  const record = { demo: id, kind: "terminal", persona: "", viewport, started: new Date().toISOString(), motion_from: "start",
                   markers: [], created: [], cleaned: null, owned: null,   // nothing is signed in to, created or read
                   terminal: { cols: header.width, rows: header.height, font_px: fontSize, captured: captured.started,
                               cast_sha256: crypto.createHash("sha256").update(fs.readFileSync(castFile)).digest("hex") },
                   status: "fail", detail: "" };
  const failures = [];
  if (captured.status !== "done") failures.push(`the capture did not pass (${captured.detail})`);
  const context = await browser.newContext({ locale: "en-US", viewport, recordVideo: { dir: out, size: viewport }, offline: true });
  const page = await context.newPage();
  const t0 = Date.now();
  const log = (text) => console.log(`${((Date.now() - t0) / 1000).toFixed(1).padStart(6)}s  ${text}`);
  try {
    await page.goto(replayUrl);
    const size = await page.evaluate(([header, events, fontSize]) => window.replay.load(header, events, fontSize), [header, events, fontSize]);
    if (size.width > viewport.width || size.height > viewport.height) throw new Error(`the ${header.width}x${header.height} terminal is ${size.width}x${size.height} px: it does not fit ${viewport.width}x${viewport.height}`);
    await page.waitForTimeout(300);
    await page.evaluate((stops) => window.replay.play(stops), wanted);
    let before = 0;
    for (const mark of wanted) {
      // The replay holds at each instant to mark, everything before it drawn: the image, the instant in the video
      // and the screen are then the same state. It goes on as soon as the image is saved.
      await page.waitForFunction((name) => window.replay.reached === name, mark.name, { timeout: (mark.at - before + 30) * 1000, polling: 20 });
      before = mark.at;
      const t = Math.round((Date.now() - t0) / 10) / 100;
      await page.screenshot({ path: path.join(out, `${mark.name}.png`) });
      record.markers.push({ name: mark.name, t, png: `${mark.name}.png` });
      log(`marker ${mark.name}`);
      if (process.env.RECORD_TERMINAL_DUMP === "1") {   // the offline test reads the screen as text; a take never does
        fs.writeFileSync(path.join(out, `screen-${mark.name}.txt`), (await page.evaluate(() => window.replay.screen())).join("\n") + "\n");
      }
      await page.evaluate(() => window.replay.resume());
    }
    await page.waitForFunction(() => window.replay.finished && window.replay.written === window.replay.total, null, { timeout: 30000 });
    record.terminal.held_seconds = Math.round((await page.evaluate(() => window.replay.held_ms)) / 10) / 100;
  } catch (e) {
    failures.push(String(e && e.message ? e.message : e).split("\n")[0].slice(0, 300));
    await page.screenshot({ path: path.join(out, "failed.png") }).catch(() => {});
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
  return failures.length ? 1 : 0;
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
  const summary = { demo: process.argv[3], persona: walk.persona || "", ...(walk.takes ? { takes: walk.takes } : {}), viewport: walk.viewport, markers: walk.markers,
                    motion_from: walk.motion_from, changes: walk.changes, walkthrough_sha256: walkthroughHash(process.argv[3]) };
  if (process.argv.includes("--json")) console.log(JSON.stringify(summary));
  else {
    console.log(`${summary.demo}: ${walk.takes ? "takes " + walk.takes.map((t) => `${t.name} (${t.persona})`).join(", ") : "persona " + walk.persona}, ${walk.viewport.width}x${walk.viewport.height}, markers ${walk.markers.join(", ")}; motion from ${walk.motion_from}`);
    console.log(`changes: ${walk.changes.length ? walk.changes.join(", ") : "none"}`);
    console.log(`walkthrough_sha256: ${summary.walkthrough_sha256}`);
  }
  process.exit(problems.length ? 1 : 0);
}

const id = process.env.DEMO || "";
const out = process.env.OUT || "/out";

if (process.env.RECORD_TERMINAL === "1") {
  if (!id || !MARKER_NAME.test(id)) usage("DEMO must be a demo id, e.g. vault-pki");
  process.exit(await terminalTake(id, out));
}

const domain = process.env.APPS_DOMAIN || "";
const password = process.env.PERSONA_PASSWORD || "";
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

// One scout, of one take (the only one, or one persona of a walkthrough with `takes`), into `out`.
async function scoutOne(take, out) {
  const report = { demo: id, ...(take.name ? { take: take.name } : {}), persona: take.persona, viewport: walk.viewport, started: new Date().toISOString(),
                   walkthrough_sha256: walkthroughHash(id), changes: walk.changes, when: "", steps: [], status: "fail", detail: "" };
  const browser = await chromium.launch();
  const context = await browser.newContext({ ignoreHTTPSErrors: true, locale: "en-US", viewport: walk.viewport });
  const page = await context.newPage();
  const t0 = Date.now();
  const log = (text) => console.log(`${((Date.now() - t0) / 1000).toFixed(1).padStart(6)}s  ${text}`);
  // A scout never sends a chat message: the calls that would are refused before they leave the browser.
  const refused = [];
  // Which calls those are is the application's own: a walkthrough names them in `sends` (Open WebUI's by default).
  await page.route(walk.sends || /\/api\/(chat\/completions|chat\/completed|v1\/chats\/new|v1\/chats\/[^/]+$|v1\/tasks\/)/, (route) => {
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
  const ctx = { page, domain, log, step, take, persona: take.persona, state: { scout: true }, mark: async () => {},
                keycloak: (username) => keycloak(page, username), base: process.env.RECORD_BASE_URL || walk.url(domain) };
  try {
    // The same first two phases as a take: the sign-in, then what the persona owns (its count is all a scout keeps).
    const entered = await step("enter", async () => { await walk.enter(ctx); return {}; });
    if (entered.ok) {
      await step("owned", async () => ({ count: (await walk.owned(ctx)).length }));
      await walk.scout(ctx);
    }
  } catch (e) {
    report.steps.push({ step: "scout", ok: false, png: null, error: String(e && e.message ? e.message : e).split("\n")[0].slice(0, 300) });
  }
  await context.close();
  await browser.close();
  const bad = report.steps.filter((s) => !s.ok).map((s) => s.step);
  if (refused.length) bad.push(`a chat message was about to be sent (${refused.join(", ")})`);
  report.refused_requests = refused;
  report.when = new Date().toISOString();
  report.status = bad.length ? "fail" : "done";
  report.detail = bad.length ? `failed: ${bad.join(", ")}` : `${report.steps.length} steps`;
  fs.writeFileSync(path.join(out, "scout.json"), JSON.stringify(report, null, 2) + "\n");
  return { code: bad.length ? 1 : 0, line: bad.length ? `failed ${bad.join(", ")}` : "done" };
}

// One take, of one persona, into `out`: its own browser context, video, markers.json and PNGs.
async function takeOne(take, out) {
  const record = { demo: id, kind: "browser", ...(take.name ? { take: take.name } : {}), persona: take.persona, viewport: walk.viewport, started: new Date().toISOString(),
                   motion_from: walk.motion_from, markers: [], created: [], cleaned: null,
                   owned: { before: null, after: null, same: null }, status: "fail", detail: "" };
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

  const state = { created: record.created };   // the walkthrough pushes {kind, id} as soon as it knows an id
  const ownedIds = async () => (await walk.owned(ctx)).map((o) => `${o.kind}:${o.id}`).sort();
  let ownedBefore = null;
  const ctx = { page, domain, mark, log, state, take, persona: take.persona, keycloak: (username) => keycloak(page, username),
                base: process.env.RECORD_BASE_URL || walk.url(domain) };
  const failures = [];
  try {
    await walk.enter(ctx);
    ownedBefore = await ownedIds();   // before anything is sent: an unreadable list stops the take for the price of a sign-in
    record.owned.before = ownedBefore.length;
    await walk.run(ctx);
    const missing = walk.markers.slice(record.markers.length);
    if (missing.length) throw new Error(`markers not reached: ${missing.join(", ")}`);
  } catch (e) {
    failures.push(String(e && e.message ? e.message : e).split("\n")[0].slice(0, 300));
    await page.screenshot({ path: path.join(out, "failed.png") }).catch(() => {});
  }
  // Pass or fail, what the take created is removed: a failed take must not leave its chat behind either.
  try {
    const cleaned = await walk.cleanup(ctx);
    record.cleaned = record.created.length || cleaned === true ? cleaned === true : null;
  } catch (e) {
    record.cleaned = false;
    failures.push(String(e && e.message ? e.message : e).split("\n")[0].slice(0, 300));
  }
  // The persona must own after the take exactly what it owned before it: ids only, never a title, and only in the log.
  if (ownedBefore) {
    try {
      const ownedAfter = await ownedIds();
      record.owned.after = ownedAfter.length;
      const added = ownedAfter.filter((o) => !ownedBefore.includes(o));
      const removed = ownedBefore.filter((o) => !ownedAfter.includes(o));
      record.owned.same = !added.length && !removed.length;
      if (!record.owned.same) {
        failures.push(`${take.persona} does not own the same items after the take: ${added.length} more, ${removed.length} fewer (ids in the log)`);
        for (const o of added) log(`owned after, not before: ${o}`);
        for (const o of removed) log(`owned before, not after: ${o}`);
      }
    } catch (e) {
      record.owned.same = false;
      failures.push(`what ${take.persona} owns could not be read after the take: ${String(e.message || e).split("\n")[0].slice(0, 200)}`);
    }
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
  return { code: failures.length ? 1 : 0, line: record.status === "pass" ? "PASS" : `FAIL ${record.detail}` };
}

// A walkthrough that films several personas exports `takes: [{name, persona}]` (ADR-0618, identity-personas): the
// same phases are played once per entry, each in its own browser context (nothing of one sign-in reaches the next)
// and its own sub-directory OUT/<name>/, which holds exactly what a single take leaves in OUT. OUT/takes.json lists
// them ({demo, takes: [{name, persona, dir, status, detail}], status}); a later take is still played when an earlier
// one failed, so one run says everything. The last line and the exit code are the whole run's.
const takes = Array.isArray(walk.takes) && walk.takes.length ? walk.takes : [{ name: "", persona: walk.persona }];
const scouting = process.env.RECORD_SCOUT === "1";
const results = [];
for (const take of takes) {
  const dir = take.name ? path.join(out, take.name) : out;
  fs.mkdirSync(dir, { recursive: true });
  if (take.name) console.log(`take ${take.name} (${take.persona}): ${dir}`);
  const result = await (scouting ? scoutOne(take, dir) : takeOne(take, dir));
  results.push({ name: take.name, persona: take.persona, dir: take.name, status: result.code ? "fail" : (scouting ? "done" : "pass"), detail: result.line });
  if (take.name) console.log(`take ${take.name}: ${result.line}`);
}
const bad = results.filter((r) => r.status === "fail");
if (takes.length > 1 || takes[0].name) {
  fs.writeFileSync(path.join(out, "takes.json"), JSON.stringify({ demo: id, takes: results, status: bad.length ? "fail" : results[0].status }, null, 2) + "\n");
}
const word = scouting ? "SCOUT:" : "RESULT:";
if (takes.length === 1 && !takes[0].name) console.log(`${word} ${results[0].detail}`);
else if (bad.length) console.log(`${word} ${scouting ? "failed" : "FAIL"} ${bad.map((r) => `${r.name}: ${r.detail.replace(/^(FAIL|failed) /, "")}`).join("; ")}`);
else console.log(`${word} ${scouting ? "done" : "PASS"}`);
process.exit(bad.length ? 1 : 0);
