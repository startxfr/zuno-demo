// WP-284 / ADR-0617: record one demo's walkthrough in the browser, for the GIF of its 5-minute version.
//
// Plays evaluations/browser/walkthroughs/<id>.mjs in one Playwright context with recordVideo. The walkthrough calls
// mark(name) at each key moment: the recorder notes the time since t0 (taken right after newPage(), the video's time
// base) and saves a screenshot <name>.png. After the walkthrough, pass or fail, it runs the walkthrough's cleanup()
// (the chat the take created is deleted, by its id), closes the context and leaves in OUT:
//
//   recording.webm   the whole take, never published
//   markers.json     {demo, kind "browser"|"terminal", persona, viewport, started, motion_from, markers: [{name, t,
//                    png, private_addresses}], private_addresses: {flagged, count, at}, created, cleaned, owned, notes?, status, detail}
//                    notes: what the walkthrough put in ctx.state.notes (short scalars only), when it put any
//                    writes: {sent, refused, tolerated, through}, when the walkthrough declares `allows` (the write guard):
//                    method, path and status of every write, never a body
//                    private_addresses: node names and RFC 1918 addresses COUNTED in the page's text at each marker (never
//                    kept); a take that showed one fails, after its clean-up
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
        else if (t.markers !== undefined && (!Array.isArray(t.markers) || !t.markers.length || t.markers.some((m) => !MARKER_NAME.test(m)) || new Set(t.markers).size !== t.markers.length
                                             || !t.markers.includes(t.motion_from))) problems.push(`take ${t.name}: its own \`markers\` need unique names and a \`motion_from\` among them`);
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
  if (walk.secrets !== undefined && (!Array.isArray(walk.secrets) || walk.secrets.some((n) => typeof n !== "string" || !/^[A-Z][A-Z0-9_]{2,}$/.test(n) || n === "PERSONA_PASSWORD"))) {
    problems.push("`secrets` must list the names of the environment variables that hold the other credentials the take types (e.g. DIFY_ADMIN_PASSWORD)");
  }
  const rule = (x) => x && typeof x === "object" && /^(POST|PUT|PATCH|DELETE)$/.test(x.method || "") && x.path instanceof RegExp && typeof x.what === "string" && x.what.length > 0;
  for (const list of ["allows", "tolerates"]) {
    if (walk[list] !== undefined && (!Array.isArray(walk[list]) || !walk[list].every(rule))) problems.push(`\`${list}\` must be a list of {method, path: RegExp, what: "a word saying what it is"}`);
  }
  if (walk.tolerates !== undefined && walk.allows === undefined) problems.push("`tolerates` needs `allows`: the write guard is on only for a walkthrough that declares what it sends");
  if (walk.guards !== undefined && typeof walk.guards !== "function") problems.push("`guards(domain)` must return the addresses of the applications the write guard covers");
  if (walk.creates !== undefined && (!Array.isArray(walk.creates) || walk.creates.some((n) => typeof n !== "string" || !/^[A-Z][A-Z0-9_]{2,}$/.test(n) || (walk.secrets || []).includes(n)))) {
    problems.push("`creates` must list the names of the secrets the take creates and the recorder holds (e.g. MAAS_API_KEY)");
  }
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
// A second credential (the owner's decision of 2026-11-16, for Dify's own administrator): a walkthrough names the
// environment variables it needs in `secrets`; the same rules as the persona password hold. The value is read here
// and nowhere else, a walkthrough never receives it (it asks `ctx.typeSecret(locator, name)` to type it into ONE
// field), and it is struck out of every line printed and every file written, should a page ever echo it.
const secrets = new Map((walk.secrets || []).map((name) => [name, process.env[name] || ""]));
for (const [name, value] of secrets) if (!value) usage(`${name} is required by this walkthrough (its \`secrets\`) and is empty`);
const scrub = (text) => [password, ...secrets.values()].filter((v) => v.length >= 4).reduce((t, v) => t.split(v).join("***"), String(text));
const print = console.log.bind(console);
console.log = (...args) => print(...args.map((a) => (typeof a === "string" ? scrub(a) : a)));
const writeJson = (file, value) => fs.writeFileSync(file, scrub(JSON.stringify(value, null, 2)) + "\n");
async function typeSecret(page, target, name) {
  if (!secrets.has(name)) throw new Error(`the walkthrough does not declare the secret ${name}`);
  const field = typeof target === "string" ? page.locator(target).first() : target;
  // Typed only where it is not drawn. A password field hides it. Any other field (OpenClaw's Control UI asks its
  // password in a plain one) is masked first, by the browser's own text masking, and checked before and after.
  const hidden = async () => (await field.getAttribute("type")) === "password"
    || await field.evaluate((el) => getComputedStyle(el).webkitTextSecurity === "disc").catch(() => false);
  if (!(await hidden())) {
    await field.evaluate((el) => el.style.setProperty("-webkit-text-security", "disc", "important"));
    if (!(await hidden())) throw new Error(`${name} is typed only into a field that hides it: this one is not a password field and could not be masked`);
  }
  await field.fill(secrets.get(name));
  if (!(await hidden())) {
    await field.fill("").catch(() => {});
    throw new Error(`the field ${name} was typed into did not stay masked: it was emptied, the take stops`);
  }
}
// A secret CREATED during the take (an API key shown once): the walkthrough names it in `creates`. The recorder takes
// it out of the creating call's RESPONSE before the page receives it: the page is given the same body with every
// match of `pattern` replaced by `mask`, so the value is never in the page, hence in no frame, picture or video,
// whatever the page does with it. The value joins the recorder's secrets (struck out of every line and file) and
// the walkthrough never receives it: it gets {status, found, body} with the masked body. Install it BEFORE the click
// that creates; it resolves when the call has answered.
function interceptSecret(page, name, { url, method = "POST", pattern, mask }) {
  if (!(walk.creates || []).includes(name)) throw new Error(`the walkthrough does not declare the created secret ${name} (\`creates\`)`);
  if (!(url instanceof RegExp) || !(pattern instanceof RegExp) || typeof mask !== "string" || !mask) throw new Error("interceptSecret needs {url: RegExp, pattern: RegExp, mask: string}");
  const every = new RegExp(pattern.source, "g");
  if (every.test(mask)) throw new Error("the mask must not itself look like the secret");
  let answered;
  const result = new Promise((resolve) => { answered = resolve; });
  const handler = async (route) => {
    if (route.request().method() !== method) return route.continue();
    const response = await route.fetch();
    const text = await response.text();
    const found = [...new Set(text.match(every) || [])];
    found.forEach((value, i) => secrets.set(i ? `${name}#${i + 1}` : name, value));
    const masked = text.replace(every, mask);
    await route.fulfill({ response, body: masked });
    let body = null;
    try { body = JSON.parse(masked); } catch { /* not JSON */ }
    answered({ status: response.status(), found: found.length, body });
    return undefined;
  };
  page.route(url, handler);
  return result;
}
// A call made BY THE RECORDER with a held secret (never by the page, never by the walkthrough): "{secret}" in a
// header's value is replaced by it. Returns {status, text}: the answer's text, the secret struck out, 20,000
// characters at most.
async function fetchWithSecret(page, name, { url, method = "GET", headers = {}, body }) {
  if (!secrets.get(name)) throw new Error(`no ${name} is held: nothing was created, or it is not declared`);
  const filled = Object.fromEntries(Object.entries(headers).map(([key, value]) => [key, String(value).split("{secret}").join(secrets.get(name))]));
  const response = await page.request.fetch(url, { method, headers: filled, data: body, timeout: 120000, failOnStatusCode: false });
  return { status: response.status(), text: scrub(await response.text().catch(() => "")).slice(0, 20000) };
}
fs.mkdirSync(out, { recursive: true });

async function keycloak(page, username) {
  // Stock Keycloak theme: #username, #password, #kc-login. The recorder's own copy (run.mjs is not shared).
  await page.fill("#username", username);
  await page.fill("#password", password);
  await Promise.all([page.waitForLoadState("domcontentloaded"), page.click("#kc-login")]);
}

const { chromium } = await import("playwright");

// One scout, of one take (the only one, or one persona of a walkthrough with `takes`), into `out`.
// What a public picture must never show (the repository is public): a node's name (ip-10-18-..., *.compute.internal)
// or a private IPv4 address (RFC 1918). A model's answer is not the same twice, so no walkthrough can promise it: the
// text of the page, every frame of it, is read at each marker and once more after the last one, and the matches are
// COUNTED. Never kept: neither markers.json, scout.json nor the log holds what matched.
const PRIVATE = [/\bip-\d+-\d+-\d+-\d+\b/g, /compute\.internal/g,
                 /(?<![\d.])(?:10\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])|192\.168)\.\d{1,3}\.\d{1,3}(?![\d.]|\.\d)/g];
async function privateAddresses(page) {
  let count = 0;
  for (const frame of page.frames()) {
    const text = await frame.evaluate(() => (document.body ? document.body.innerText : "")).catch(() => "");
    for (const pattern of PRIVATE) count += (text.match(pattern) || []).length;
  }
  return count;
}
// The summary kept in markers.json and scout.json: {flagged, count (the most seen at once), at: [marker or step]}.
const addressSummary = (seen) => ({ flagged: seen.some(([, n]) => n > 0), count: Math.max(0, ...seen.map(([, n]) => n)), at: seen.filter(([, n]) => n > 0).map(([name]) => name) });

// A take or a scout that never ends, ends: its phases are given a deadline (RECORD_DEADLINE_S, or the walkthrough's
// `deadline_s`; 20 minutes for a take, 10 for a scout), then the clean-up three minutes. On the workstation of
// 2026-11-16 seven recorders of timed-out offline suites ran for hours. The phase left behind is abandoned: closing
// the browser ends whatever it was waiting for.
const deadlineMs = (fallbackS) => 1000 * (Number(process.env.RECORD_DEADLINE_S) || Number(walk.deadline_s) || fallbackS);
function within(work, ms, what) {
  let timer;
  const late = new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(`${what} did not end within ${Math.round(ms / 1000)} s: stopped by the recorder's deadline`)), ms); });
  work.catch(() => {});   // if the deadline wins, what the phase throws later is nobody's
  return Promise.race([work, late]).finally(() => clearTimeout(timer));
}

// THE WRITE GUARD (default deny, 2026-11-16). A walkthrough that exports `allows` gets it, in a take AND in a scout:
// every request to its application(s) that is not a read (GET, HEAD, OPTIONS) is refused before it leaves the
// browser unless the walkthrough declares it: `allows: [{method, path, what}]`, `path` a RegExp on the address's
// path, `what` a word saying what it is ("chat send", "search (a read)", "delete own chat"). A write it does not
// declare is aborted and listed, and FAILS a take, unless it is in `tolerates` (same shape: a write the application
// tries by itself and the take means to refuse, an editor's autosave): then it is aborted, listed, and that is all.
// A write that is not declared and was answered all the same fails a take and a scout. The applications are
// `guards(domain)` (addresses; by default the walkthrough's own): the sign-in pages (Keycloak, OpenShift) are other
// origins and are not covered. Before this guard only a scout was protected, by `sends`; a take sent whatever the
// page sent (the Dify finding of 2026-11-16). Only method, path and status are ever kept: never a body.
const READS = ["GET", "HEAD", "OPTIONS"];
const anonymous = (pathname) => pathname.replace(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f-]{22}|[0-9a-f]{16,}|\d{4,}/gi, "<id>");
async function guardWrites(context) {
  if (!walk.allows) return null;
  const origins = (walk.guards ? walk.guards(domain) : [process.env.RECORD_BASE_URL || walk.url(domain)]).map((address) => new URL(address).origin);
  const found = (list, request) => (list || []).find((x) => x.method === request.method() && x.path.test(new URL(request.url()).pathname));
  const seen = { sent: [], refused: [], tolerated: [], through: [] };
  await context.route((address) => origins.includes(address.origin), (route) => {
    const request = route.request();
    if (READS.includes(request.method())) return route.fallback();
    const line = `${request.method()} ${anonymous(new URL(request.url()).pathname)}`;
    const allowed = found(walk.allows, request);
    if (allowed) return route.fallback();   // a scout's own filter (`sends`) still has its say
    (found(walk.tolerates, request) ? seen.tolerated : seen.refused).push(line);
    return route.abort();
  });
  context.on("response", (response) => {
    const request = response.request();
    if (READS.includes(request.method()) || !origins.includes(new URL(request.url()).origin)) return;
    const line = `${request.method()} ${anonymous(new URL(request.url()).pathname)}`;
    const allowed = found(walk.allows, request);
    if (allowed) seen.sent.push(`${line} -> ${response.status()} (${allowed.what})`);
    else seen.through.push(`${line} -> ${response.status()}`);
  });
  return seen;
}
// What markers.json and scout.json keep of it, and what it makes fail: [problems].
function writesReport(seen, record, { scout }) {
  if (!seen) return [];
  const once = (list) => [...new Set(list)];
  record.writes = { sent: seen.sent, refused: once(seen.refused), tolerated: once(seen.tolerated), through: once(seen.through) };
  const problems = [];
  if (seen.through.length) problems.push(`a write the walkthrough does not declare was answered all the same: ${once(seen.through).join(", ")}`);
  if (seen.refused.length && !scout) problems.push(`the page was about to send ${once(seen.refused).length} write(s) the walkthrough does not declare (aborted): ${once(seen.refused).join(", ")}`);
  return problems;
}

async function scoutOne(take, out) {
  const report = { demo: id, ...(take.name ? { take: take.name } : {}), persona: take.persona, viewport: walk.viewport, started: new Date().toISOString(),
                   walkthrough_sha256: walkthroughHash(id), changes: walk.changes, when: "", steps: [], status: "fail", detail: "" };
  const browser = await chromium.launch();
  const context = await browser.newContext({ ignoreHTTPSErrors: true, locale: "en-US", viewport: walk.viewport });
  const guarded = await guardWrites(context);
  const page = await context.newPage();
  // A first load on the cluster can take more than Playwright's 30 s (rescouts of 2026-11-16: four of seven attempts
  // lost on that alone): every navigation is given 90 s.
  page.setDefaultNavigationTimeout(90000);
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
    entry.private_addresses = await privateAddresses(page).catch(() => 0);
    report.steps.push(entry);
    log(`scout ${name}: ${entry.ok ? "ok" : "FAILED " + entry.error}`);
    return entry;
  };
  const ctx = { page, domain, log, step, take, persona: take.persona, state: { scout: true }, mark: async () => {},
                keycloak: (username) => keycloak(page, username), typeSecret: (target, name) => typeSecret(page, target, name),
                interceptSecret: (name, how) => interceptSecret(page, name, how), fetchWithSecret: (name, call) => fetchWithSecret(page, name, call), base: process.env.RECORD_BASE_URL || walk.url(domain) };
  try {
    await within((async () => {
    // The same first two phases as a take: the sign-in, then what the persona owns (its count is all a scout keeps).
    const entered = await step("enter", async () => { await walk.enter(ctx); return {}; });
    if (entered.ok) {
      await step("owned", async () => ({ count: (await walk.owned(ctx)).length }));
      await walk.scout(ctx);
    }
    })(), deadlineMs(600), "the scout");
  } catch (e) {
    report.steps.push({ step: "scout", ok: false, png: null, error: String(e && e.message ? e.message : e).split("\n")[0].slice(0, 300) });
  }
  await context.close();
  await browser.close();
  const bad = report.steps.filter((s) => !s.ok).map((s) => s.step);
  if (refused.length) bad.push(`a request a scout refuses was about to be sent (${refused.join(", ")})`);
  report.refused_requests = refused;
  // The write guard: in a scout the undeclared writes it aborted are REPORTED (that is how an allow-list is learned);
  // only one that got through fails it.
  bad.push(...writesReport(guarded, report, { scout: true }));
  if (guarded && guarded.refused.length) log(`write guard: aborted, not declared: ${[...new Set(guarded.refused)].join(", ")}`);
  // Reported, not a failure: a scout asks nothing, so what it sees is what the page shows before any answer.
  report.private_addresses = addressSummary(report.steps.filter((s) => typeof s.private_addresses === "number").map((s) => [s.step, s.private_addresses]));
  report.when = new Date().toISOString();
  report.status = bad.length ? "fail" : "done";
  report.detail = bad.length ? `failed: ${bad.join(", ")}` : `${report.steps.length} steps`;
  writeJson(path.join(out, "scout.json"), report);
  return { code: bad.length ? 1 : 0, line: bad.length ? `failed ${bad.join(", ")}` : "done" };
}

// One take, of one persona, into `out`: its own browser context, video, markers.json and PNGs.
async function takeOne(take, out) {
  const wanted = take.markers || walk.markers;   // a take of several may play other screens: its own markers
  const record = { demo: id, kind: "browser", ...(take.name ? { take: take.name } : {}), persona: take.persona, viewport: walk.viewport, started: new Date().toISOString(),
                   motion_from: take.motion_from || walk.motion_from, markers: [], created: [], cleaned: null,
                   owned: { before: null, after: null, same: null }, status: "fail", detail: "" };
  const browser = await chromium.launch();
  const context = await browser.newContext({
    ignoreHTTPSErrors: true, locale: "en-US", viewport: walk.viewport,
    recordVideo: { dir: out, size: walk.viewport },
  });
  const guarded = await guardWrites(context);
  const page = await context.newPage();
  // A first load on the cluster can take more than Playwright's 30 s (rescouts of 2026-11-16: four of seven attempts
  // lost on that alone): every navigation is given 90 s.
  page.setDefaultNavigationTimeout(90000);
  const t0 = Date.now();
  const log = (text) => console.log(`${((Date.now() - t0) / 1000).toFixed(1).padStart(6)}s  ${text}`);

  async function mark(name) {
    const expected = wanted[record.markers.length];
    if (name !== expected) throw new Error(`marker ${name} out of order: ${expected || "no marker"} was expected`);
    const t = Math.round((Date.now() - t0) / 10) / 100;
    await page.screenshot({ path: path.join(out, `${name}.png`) });
    const addresses = await privateAddresses(page).catch(() => 0);
    record.markers.push({ name, t, png: `${name}.png`, private_addresses: addresses });
    log(`marker ${name}${addresses ? ` (${addresses} node names or private addresses on the page)` : ""}`);
  }

  const state = { created: record.created };   // the walkthrough pushes {kind, id} as soon as it knows an id
  state.notes = {};   // facts of its own a walkthrough wants kept in markers.json (`notes`): short scalars only
  const ownedIds = async () => (await walk.owned(ctx)).map((o) => `${o.kind}:${o.id}`).sort();
  let ownedBefore = null;
  const ctx = { page, domain, mark, log, state, take, persona: take.persona, keycloak: (username) => keycloak(page, username), typeSecret: (target, name) => typeSecret(page, target, name),
                interceptSecret: (name, how) => interceptSecret(page, name, how), fetchWithSecret: (name, call) => fetchWithSecret(page, name, call),
                base: process.env.RECORD_BASE_URL || walk.url(domain) };
  const failures = [];
  try {
    await within((async () => {
      await walk.enter(ctx);
      ownedBefore = await ownedIds();   // before anything is sent: an unreadable list stops the take for the price of a sign-in
      record.owned.before = ownedBefore.length;
      await walk.run(ctx);
    })(), deadlineMs(1200), "the take");
    const missing = wanted.slice(record.markers.length);
    if (missing.length) throw new Error(`markers not reached: ${missing.join(", ")}`);
  } catch (e) {
    failures.push(String(e && e.message ? e.message : e).split("\n")[0].slice(0, 300));
    await page.screenshot({ path: path.join(out, "failed.png") }).catch(() => {});
  }
  // Before the clean-up changes the page: what it shows after the last marker.
  const shown = record.markers.map((m) => [m.name, m.private_addresses]);
  shown.push(["after the last marker", await privateAddresses(page).catch(() => 0)]);
  record.private_addresses = addressSummary(shown);
  // Pass or fail, what the take created is removed: a failed take must not leave its chat behind either.
  try {
    const cleaned = await within(Promise.resolve().then(() => walk.cleanup(ctx)), 180000, "the clean-up");
    record.cleaned = record.created.length || cleaned === true ? cleaned === true : null;
  } catch (e) {
    record.cleaned = false;
    failures.push(String(e && e.message ? e.message : e).split("\n")[0].slice(0, 300));
  }
  // The persona must own after the take exactly what it owned before it: ids only, never a title, and only in the log.
  if (ownedBefore) {
    try {
      const ownedAfter = await within(ownedIds(), 120000, "the read of what the persona owns");
      record.owned.after = ownedAfter.length;
      const added = ownedAfter.filter((o) => !ownedBefore.includes(o));
      const removed = ownedBefore.filter((o) => !ownedAfter.includes(o));
      // (the counts too: two items a walkthrough gives the same id must not hide one more)
      record.owned.same = !added.length && !removed.length && ownedAfter.length === ownedBefore.length;
      if (!record.owned.same) {
        failures.push(`${take.persona} does not own the same items after the take: ${added.length || Math.max(0, ownedAfter.length - ownedBefore.length)} more, ${removed.length || Math.max(0, ownedBefore.length - ownedAfter.length)} fewer (ids in the log)`);
        for (const o of added) log(`owned after, not before: ${o}`);
        for (const o of removed) log(`owned before, not after: ${o}`);
      }
    } catch (e) {
      record.owned.same = false;
      failures.push(`what ${take.persona} owns could not be read after the take: ${String(e.message || e).split("\n")[0].slice(0, 200)}`);
    }
  }
  // The write guard's account, once the clean-up has sent its own writes too.
  if (guarded) {
    await page.waitForTimeout(500);
    failures.push(...writesReport(guarded, record, { scout: false }));
    log(`write guard: sent ${guarded.sent.join("; ") || "nothing"}${guarded.tolerated.length ? `; aborted as declared: ${[...new Set(guarded.tolerated)].join(", ")}` : ""}`);
  }
  // After the clean-up, which it never stops: a take that showed a node name or a private address is not publishable.
  if (record.private_addresses.flagged) {
    failures.push(`the page showed node names or private IP addresses (${record.private_addresses.count} at once, at ${record.private_addresses.at.join(", ")}): `
      + "this take must not be published; record again, or ask a question whose answer cannot hold them");
  }
  const video = page.video();
  await context.close();
  await browser.close();
  try {
    fs.renameSync(await video.path(), path.join(out, "recording.webm"));
  } catch (e) {
    failures.push(`no recording.webm: ${String(e.message || e).slice(0, 200)}`);
  }
  // A walkthrough's own notes: at most 20 of them, numbers, booleans or strings of 200 characters; anything else is
  // dropped, so a title, an answer or an object never lands in markers.json by this door.
  const notes = Object.entries(state.notes && typeof state.notes === "object" ? state.notes : {})
    .filter(([key, value]) => /^[a-z][a-z0-9_]{0,39}$/.test(key) && (["number", "boolean"].includes(typeof value) || (typeof value === "string" && value.length <= 200))).slice(0, 20);
  if (notes.length) record.notes = Object.fromEntries(notes);
  record.status = failures.length ? "fail" : "pass";
  record.detail = failures.length ? failures.join("; ")
    : `${record.markers.length} markers in ${record.markers[record.markers.length - 1].t.toFixed(1)} s`;
  writeJson(path.join(out, "markers.json"), record);
  return { code: failures.length ? 1 : 0, line: record.status === "pass" ? "PASS" : `FAIL ${record.detail}` };
}

// A walkthrough that films several personas exports `takes: [{name, persona}]` (an entry may carry its own `markers`
// and `motion_from` when its take plays other screens than the first)
//  (ADR-0618, identity-personas): the
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
  writeJson(path.join(out, "takes.json"), { demo: id, takes: results, status: bad.length ? "fail" : results[0].status });
}
// A scout of several takes also leaves ONE scout.json at the top of OUT, shaped like a single scout's: the run's
// status, the walkthrough's hash and `changes`, and every take's steps as `<take>/<step>`, with all a single scout's step holds (what the step read, its count of
// private addresses), the write guard's account of every take (`writes`, each line led by `<take>: `) and the
// private-address summary over all steps.
// What reads "the newest scout of this demo" (make demo record) then needs nothing more.
if (scouting && (takes.length > 1 || takes[0].name)) {
  const parts = results.map((r) => {
    try { return { name: r.name, ...JSON.parse(fs.readFileSync(path.join(out, r.name, "scout.json"), "utf8")) }; } catch { return { name: r.name, steps: [] }; }
  });
  writeJson(path.join(out, "scout.json"), {
    demo: id, takes: results.map((r) => r.name), persona: results.map((r) => r.persona).join(", "), viewport: walk.viewport,
    started: (parts[0] || {}).started || "", when: new Date().toISOString(), walkthrough_sha256: walkthroughHash(id), changes: walk.changes,
    steps: parts.flatMap((part) => (part.steps || []).map((s) => ({ ...s, step: `${part.name}/${s.step}`, ok: s.ok === true, png: s.png ? `${part.name}/${s.png}` : null }))),
    refused_requests: parts.flatMap((part) => part.refused_requests || []),
    ...(parts.some((part) => part.writes) ? { writes: Object.fromEntries(["sent", "refused", "tolerated", "through"].map((kind) =>
      [kind, parts.flatMap((part) => ((part.writes || {})[kind] || []).map((line) => `${part.name}: ${line}`))])) } : {}),
    private_addresses: addressSummary(parts.flatMap((part) => (part.steps || []).filter((s) => typeof s.private_addresses === "number").map((s) => [`${part.name}/${s.step}`, s.private_addresses]))),
    status: bad.length ? "fail" : "done",
    detail: bad.length ? `failed: ${bad.map((r) => r.name).join(", ")}` : `${results.length} takes`,
  });
}
const word = scouting ? "SCOUT:" : "RESULT:";
if (takes.length === 1 && !takes[0].name) console.log(`${word} ${results[0].detail}`);
else if (bad.length) console.log(`${word} ${scouting ? "failed" : "FAIL"} ${bad.map((r) => `${r.name}: ${r.detail.replace(/^(FAIL|failed) /, "")}`).join("; ")}`);
else console.log(`${word} ${scouting ? "done" : "PASS"}`);
process.exit(bad.length ? 1 : 0);
