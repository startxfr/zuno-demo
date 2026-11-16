// WP-288 / ADR-0618: what the walkthroughs that film Dify share (dify first; guardrails' row 0:45 asks the same Zuno
// Agent). Imported ONLY by those walkthroughs; like _grafana.mjs it is in no walkthrough hash: after editing this
// file, scout again by hand.
//
// Dify on Zuno (docs/demo/scenarios/experiences/dify.md): a front door (Keycloak, group `consultant`), then Dify's own
// sign-in form, as its single local administrator dify-admin@zuno.local. That second password is the take's second
// credential (the owner's decision of 2026-11-16): the recorder holds it, this file only asks it to type it into the
// one password field of Dify's form (`ctx.typeSecret`), and nothing is marked or described while that form is open.
//
// Seen live by the first scout (2026-11-16): the two sign-in forms work as guessed, and Dify then opens on its Home
// page. Everything after Studio is still a guess from Dify 1.x, marked `guess`: the cards, the chat pane, the run
// form and every API path; scout() of the walkthrough reports what is really there.
//
// What a take may write in Dify, and nothing else: one message to the Zuno Agent's chat (a conversation, deleted by
// its id at the end when Dify's API lists it), one run of the workflow (its run log CANNOT be deleted: said in the
// record notice). What it must never write: the applications themselves. Dify's editor saves by itself; every
// request to its console API that is not a read and not on a short list is refused before it leaves the browser, in
// a take as in a scout (`difyGuard`, default deny).
import { click, firstVisible, read, waitUntil } from "./_helpers.mjs";

export const dify = {
  url: (domain) => `https://dify.${domain}`,
  // The declared effect of an Agent turn (measured on three takes of 2026-11-16, the owner's decision of that day):
  // the card of Zuno Agent reads "Edited at" the minute of the turn, although the browser sent no configuration (the
  // take of 21:50 sent login, chat-messages, the workflow run and the conversation's delete, nothing else).
  TURN_CHANGE: "an Agent turn in Dify's Debug & Preview moves the Zuno Agent's edited date (Dify's server does it; no configuration is sent by the browser)",
  ADMIN: "dify-admin@zuno.local",   // the page: Dify's single local administrator; not a secret
  SECRET: "DIFY_ADMIN_PASSWORD",    // the environment variable the recorder reads (walkthrough `secrets`)
  EMAIL: ["input#email", "input[type='email']", "input[name='email']"],                                   // guess
  PASSWORD: ["input#password", "input[type='password']"],                                                // guess
  SUBMIT: ["form button[type='submit']", "button:has-text('Sign in')", "button:has-text('Login')"],      // guess
  // Dify opens on its Home page, not on Studio (scout of 2026-11-16: "Welcome back", a left menu Home / Studio /
  // Knowledge / Skills / Integrations): Studio is reached by its entry of that menu.
  STUDIO: ["a[href='/apps']", "a:text-is('Studio')", "nav a:has-text('Studio')", "a:has-text('Studio')"],
  HOME: /Welcome back/,
  CHAT_INPUT: ["textarea[placeholder*='Talk' i]", "textarea[placeholder*='message' i]", "textarea"],     // guess
  RUN: ["button:has-text('Test Run')", "button:has-text('Run')"],                                        // 'Test Run' seen live, 2026-11-16
  START_RUN: ["button:has-text('Start Run')", "button:has-text('Start run')", "form button[type='submit']"],   // 'Start Run' seen live, 2026-11-16
  TOPIC: ["[placeholder='Topic' i]", "input[type='text']", "textarea"],   // the run form's one field: placeholder "Topic", seen live
  // The ONLY requests to Dify's console API that are not reads and may leave the browser (difyGuard): the two
  // sign-in calls, one read that Dify makes by POST, the Agent's chat message, the workflow's run, and the delete of
  // the take's own conversation. Anything else is refused: an application is never written.
  allowed: [
    ["POST", /^\/console\/api\/(login|refresh-token)\/?$/],
    ["POST", /^\/console\/api\/workspaces\/current\/?$/],                                   // a read made by POST (guess)
    ["POST", /^\/console\/api\/apps\/[^/]+\/chat-messages\/?$/],
    ["POST", /^\/console\/api\/apps\/[^/]+\/workflows\/draft\/run\/?$/],
    ["DELETE", /^\/console\/api\/apps\/[^/]+\/chat-conversations\/[^/]+\/?$/],
  ],
  // What a scout refuses besides: a chat message, a workflow run, a conversation deleted.
  sends: /\/console\/api\/apps\/[^/]+\/(chat-messages|completion-messages|workflows\/draft\/run|advanced-chat\/workflows\/draft\/run|chat-conversations\/[^/]+)\/?$/,
  ANSWER_TIMEOUT_MS: 240000,   // the Agent turn took 82 s on 2026-11-06
};

// DEFAULT DENY (2026-11-16). After the first take the card of Zuno Agent read "Edited at" the minute of that take:
// something had written to the application although the saves this file had guessed were refused. So nothing is
// guessed any more: every request to Dify's console API that is not a read (GET, HEAD, OPTIONS) is refused before it
// leaves the browser, in a take as in a scout, unless it is one of the few a take must send (`dify.allowed`). The
// refused ones are listed by method and path; and any write that is NOT on the list and was answered all the same
// (it escaped the filter: a request sent while a page unloads can) is listed apart, and a take that has one fails.
// Returns a function giving the refused list; its `.through()` gives the writes that got through, its `.sent()` every
// allowed write the take made and how it was answered (method, path, status: never a body).
const READ = ["GET", "HEAD", "OPTIONS"];
const anonymous = (path) => path.replace(/[0-9a-f]{8}-[0-9a-f-]{27}/g, "<id>");
const isAllowed = (method, path) => dify.allowed.some(([m, p]) => m === method && p.test(path));
export async function difyGuard(page) {
  const refused = [];
  const through = [];
  const answered = [];
  const allowed = [];   // every request that is not a read and was let through, in order: what the take really sent
  await page.context().route((url) => url.pathname.startsWith("/console/api/"), (route) => {
    const r = route.request();
    const path = new URL(r.url()).pathname;
    if (READ.includes(r.method())) return route.fallback();
    if (isAllowed(r.method(), path)) { allowed.push(`${r.method()} ${anonymous(path)}`); return route.fallback(); }   // a scout's own filter still applies
    refused.push(`${r.method()} ${anonymous(path)}`);
    return route.abort();
  });
  page.context().on("response", (response) => {
    const r = response.request();
    const path = new URL(r.url()).pathname;
    if (!path.startsWith("/console/api/") || READ.includes(r.method())) return;
    if (isAllowed(r.method(), path)) { answered.push(`${r.method()} ${anonymous(path)} -> ${response.status()}`); return; }
    through.push(`${r.method()} ${anonymous(path)} (HTTP ${response.status()})`);
  });
  const list = () => [...new Set(refused)];
  list.through = () => [...new Set(through)];
  list.sent = () => ({ sent: [...allowed], answered: [...answered] });   // not de-duplicated: the order and the count matter
  return list;
}

// Sign in: the front door (Keycloak, the `login` marker on its EMPTY form), then Dify's own form as its single
// administrator. Nothing is marked, described or logged between the two forms and Studio.
export async function difySignIn({ page, base, mark, keycloak, typeSecret, state }, persona) {
  state.dify = { second_form: false, landed: "", studio: "" };
  await page.goto(`${base}/`);
  await page.waitForSelector("#username", { timeout: 30000 });
  await mark("login");   // the EMPTY Keycloak form: nothing is marked once a password is typed
  await keycloak(persona);
  const found = await waitUntil(page, { what: "Dify behind its front door", timeoutMs: 90000, done: async () => {
    if (!page.url().startsWith(base)) return undefined;
    if (await firstVisible(page, dify.PASSWORD)) return "form";
    if ((/\/apps(\/|\?|$)/.test(page.url()) || (await firstVisible(page, dify.STUDIO))) && !(await firstVisible(page, dify.PASSWORD))) return "studio";
    return undefined;
  } });
  if (found === "form") {
    state.dify.second_form = true;
    const email = await firstVisible(page, dify.EMAIL);
    if (!email) throw new Error(`Dify's sign-in form has no email field among ${dify.EMAIL.join(" | ")}`);
    await email.fill(dify.ADMIN);
    const field = await firstVisible(page, dify.PASSWORD);
    await typeSecret(page.locator(field.matched).first(), dify.SECRET);
    const submit = await firstVisible(page, dify.SUBMIT);
    if (!submit) throw new Error(`Dify's sign-in form has no button among ${dify.SUBMIT.join(" | ")}`);
    await Promise.all([page.waitForLoadState("domcontentloaded").catch(() => {}), click(submit)]);
  }
  // Signed in: Dify's Home page (or Studio at once, on an older Dify). The sign-in form must be gone.
  const landed = await waitUntil(page, { what: "Dify after its sign-in", timeoutMs: 90000, done: async () => {
    if (await firstVisible(page, dify.PASSWORD)) {
      const wrong = await page.getByText(/invalid|incorrect|wrong|failed/i).first().isVisible().catch(() => false);
      if (wrong) throw new Error("Dify refused its administrator's sign-in (the form shows an error)");
      return undefined;
    }
    if (/\/apps(\/|\?|$)/.test(page.url())) return "studio";
    return (await firstVisible(page, dify.STUDIO)) ? "home" : undefined;
  } });
  state.dify.landed = landed;
  if (landed === "home") {
    await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
    const studio = await firstVisible(page, dify.STUDIO);
    await click(studio);
    await page.waitForURL(/\/apps(\/|\?|$)/, { timeout: 30000 });
  }
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
  state.dify.studio = page.url().replace(/[?#].*/, "");
}

// Call Dify's console API from the page, as the signed-in administrator: {status, body}. Dify keeps its session in
// cookies with a CSRF token, or (older) a bearer token in the browser's storage: both are sent when present; neither
// is ever returned or logged.
export async function difyApi(page, method, path) {
  return read(page, async ({ method, path }) => {
    const headers = {};
    try {
      const token = localStorage.getItem("console_token");
      if (token) headers.Authorization = `Bearer ${token}`;
    } catch { /* storage refused */ }
    const csrf = document.cookie.split("; ").map((c) => c.split("=")).find(([name]) => /csrf_token$/.test(name));
    if (csrf) headers["X-CSRF-Token"] = decodeURIComponent(csrf.slice(1).join("="));
    const r = await fetch(path, { method, credentials: "include", headers });
    let body = null;
    try { body = await r.json(); } catch { /* no JSON body */ }
    return { status: r.status, body };
  }, { method, path });
}

const list = (got) => (got && got.status === 200 && got.body && Array.isArray(got.body.data) ? got.body.data : null);

// The applications of Studio, by name: {name: {id, mode}}; null when the API did not answer a list.
export async function difyApps(page) {
  const apps = list(await difyApi(page, "GET", "/console/api/apps?page=1&limit=100").catch(() => null));
  return apps ? Object.fromEntries(apps.map((a) => [a.name, { id: a.id, mode: a.mode }])) : null;
}

// The ids of an application's conversations (its logs), newest first; null when the API did not answer a list.
export async function difyConversations(page, appId) {
  const rows = list(await difyApi(page, "GET", `/console/api/apps/${appId}/chat-conversations?page=1&limit=100`).catch(() => null));
  return rows ? rows.map((c) => String(c.id)) : null;
}

// The runs of a workflow application: [{id, status}], newest first; null when the API did not answer a list.
export async function difyRuns(page, appId) {
  const rows = list(await difyApi(page, "GET", `/console/api/apps/${appId}/workflow-runs?limit=100`).catch(() => null));
  return rows ? rows.map((r) => ({ id: String(r.id), status: String(r.status || "") })) : null;
}

// Open an application from Studio by its card: the address reached, without its query.
export async function difyOpen(page, base, name, { changes = [], ready = [] } = {}) {
  // Studio is reached by its own link (the left menu's, or the editor's breadcrumb), never by an address typed and
  // never by a card of Home: the first take (2026-11-16) opened the workflow from a place that was not Studio and
  // landed on its web app. Studio is proved by its address before a card is looked for.
  const onStudio = () => new URL(page.url()).pathname.replace(/\/$/, "") === "/apps";
  if (!onStudio()) {
    const studio = await firstVisible(page, dify.STUDIO);
    if (studio) await click(studio, { changes }); else await page.goto(`${base}/apps`);
    await waitUntil(page, { what: "Dify's Studio", timeoutMs: 30000, done: async () => onStudio() || undefined })
      .catch(() => { throw new Error(`Studio was not reached (the address is ${new URL(page.url()).pathname.replace(/[0-9a-f]{8}-[0-9a-f-]{27}/g, "<id>")})`); });
    await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
  }
  // Dify's left menu lists the published web apps by the same names (scout of 2026-11-16): the card is the match in
  // the page's body, right of that menu, not the menu's entry (which opens the web app, not its editor).
  // Studio draws grey skeleton cards first (rescout of 2026-11-16): the card is waited for, a minute.
  const named = page.getByText(name, { exact: true });
  const find = async () => {
    for (let i = 0; i < Math.min(await named.count(), 10); i += 1) {
      const box = await named.nth(i).boundingBox().catch(() => null);
      if (box && box.width > 0 && box.x >= 260) return named.nth(i);   // 260: the menu's width at 1280 px
    }
    return null;
  };
  const card = await waitUntil(page, { what: `the card of ${name} in Studio`, timeoutMs: 60000, done: async () => (await find()) || undefined })
    .catch(() => { throw new Error(`Studio shows no card named ${name} within a minute (only the left menu names it, or the cards never loaded)`); });
  await page.waitForTimeout(800);
  await click(card, { changes });
  await page.waitForURL(/\/app\/[0-9a-f-]{8,}\//, { timeout: 30000 })
    .catch(() => { throw new Error(`the card of ${name} did not open its editor (the address is ${new URL(page.url()).pathname.replace(/[0-9a-f]{8}-[0-9a-f-]{27}/g, "<id>")}): not the application's page in Studio`); });
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
  // The editor draws after its shell (scout of 2026-11-16: a spinner under the breadcrumb when the page was read):
  // when the caller says what it needs (`ready`), it is waited for, 90 s, and the caller checks it afterwards.
  if (ready.length) await waitUntil(page, { what: `the page of ${name}`, timeoutMs: 90000, done: async () => (await firstVisible(page, ready)) || undefined }).catch(() => {});
  await page.waitForTimeout(1000);
  return page.url().replace(/[?#].*/, "");
}

// Type a message in the application's chat pane and send it; resolves when the answer's stream has ended:
// {status, seconds}. The message is marked sent (`sent()`) once it has left the input.
export async function difyAsk(page, prompt, state, { sent = async () => {} } = {}) {
  if (state && state.scout) throw new Error("a scout never types in the chat input");
  const input = await firstVisible(page, dify.CHAT_INPUT);
  if (!input) throw new Error(`the chat input was not found (${dify.CHAT_INPUT.join(" | ")})`);
  const box = page.locator(input.matched).first();
  const t0 = Date.now();
  const answer = page.waitForResponse((r) => /\/chat-messages\/?$/.test(new URL(r.url()).pathname) && r.request().method() === "POST", { timeout: 60000 });
  await input.click();
  await page.keyboard.type(prompt, { delay: 25 });
  await page.keyboard.press("Enter");
  const deadline = Date.now() + 5000;
  while (Date.now() < deadline && (await box.inputValue().catch(() => "")).includes(prompt.slice(0, 20))) await page.waitForTimeout(200);
  if ((await box.inputValue().catch(() => "")).includes(prompt.slice(0, 20))) throw new Error("the message was typed but not sent: it is still in the chat input after Enter");
  await sent();
  const response = await answer;
  if (response.status() >= 400) throw new Error(`Dify answered HTTP ${response.status()} to the message`);
  await Promise.race([response.finished(), page.waitForTimeout(dify.ANSWER_TIMEOUT_MS).then(() => { throw new Error(`the answer's stream did not end within ${dify.ANSWER_TIMEOUT_MS / 1000} s`); })]);
  await page.waitForTimeout(1500);   // the last tokens drawn
  return { status: response.status(), seconds: Math.round((Date.now() - t0) / 100) / 10 };
}
