// WP-288 / ADR-0618: what the walkthroughs that film Dify share (dify first; guardrails' row 0:45 asks the same Zuno
// Agent). Imported ONLY by those walkthroughs; like _grafana.mjs it is in no walkthrough hash: after editing this
// file, scout again by hand.
//
// Dify on Zuno (docs/demo/scenarios/experiences/dify.md): a front door (Keycloak, group `consultant`), then Dify's own
// sign-in form, as its single local administrator dify-admin@zuno.local. That second password is the take's second
// credential (the owner's decision of 2026-11-16): the recorder holds it, this file only asks it to type it into the
// one password field of Dify's form (`ctx.typeSecret`), and nothing is marked or described while that form is open.
//
// NOTHING below was seen live when this was written (2026-11-16): the browser check stops at the front door. Every
// selector and every API path is a guess from Dify 1.x, marked `guess`; scout() of the walkthrough reports what is
// really there.
//
// What a take may write in Dify, and nothing else: one message to the Zuno Agent's chat (a conversation, deleted by
// its id at the end when Dify's API lists it), one run of the workflow (its run log CANNOT be deleted: said in the
// record notice). What it must never write: the applications themselves. Dify's editor saves an application's draft
// and its model configuration by itself when a page is opened; those requests are refused before they leave the
// browser, in a take as in a scout, and counted (`difyGuard`).
import { click, firstVisible, read, waitUntil } from "./_helpers.mjs";

export const dify = {
  url: (domain) => `https://dify.${domain}`,
  ADMIN: "dify-admin@zuno.local",   // the page: Dify's single local administrator; not a secret
  SECRET: "DIFY_ADMIN_PASSWORD",    // the environment variable the recorder reads (walkthrough `secrets`)
  EMAIL: ["input#email", "input[type='email']", "input[name='email']"],                                   // guess
  PASSWORD: ["input#password", "input[type='password']"],                                                // guess
  SUBMIT: ["form button[type='submit']", "button:has-text('Sign in')", "button:has-text('Login')"],      // guess
  STUDIO: ["a[href='/apps']", "nav a:has-text('Studio')"],                                               // guess
  CHAT_INPUT: ["textarea[placeholder*='Talk' i]", "textarea[placeholder*='message' i]", "textarea"],     // guess
  RUN: ["button:has-text('Test Run')", "button:has-text('Run')"],                                        // guess: the workflow's run button
  START_RUN: ["button:has-text('Start Run')", "button:has-text('Start run')", "form button[type='submit']"],   // guess
  // The application's own definition: never written by a take or a scout (the editor's autosave included).
  definition: /\/console\/api\/apps\/[^/]+(\/(model-config|workflows\/draft|workflows\/publish|site|api-enable|site-enable|name|icon|copy|export|convert-to-workflow))?\/?$/,
  // What a scout refuses besides: a chat message, a workflow run, a conversation deleted.
  sends: /\/console\/api\/apps\/[^/]+\/(chat-messages|completion-messages|workflows\/draft\/run|advanced-chat\/workflows\/draft\/run|chat-conversations\/[^/]+)\/?$/,
  ANSWER_TIMEOUT_MS: 240000,   // the Agent turn took 82 s on 2026-11-06
};

// Refuse every write to an application's definition before it leaves the browser: returns a function giving the
// list of what was refused so far ("METHOD path", ids replaced). GETs pass.
export async function difyGuard(page) {
  const refused = [];
  await page.route(dify.definition, (route) => {
    const r = route.request();
    if (r.method() === "GET") return route.continue();
    refused.push(`${r.method()} ${new URL(r.url()).pathname.replace(/[0-9a-f]{8}-[0-9a-f-]{27}/g, "<id>")}`);
    return route.abort();
  });
  return () => [...new Set(refused)];
}

// Sign in: the front door (Keycloak, the `login` marker on its EMPTY form), then Dify's own form as its single
// administrator. Nothing is marked, described or logged between the two forms and Studio.
export async function difySignIn({ page, base, mark, keycloak, typeSecret, state }, persona) {
  state.dify = { second_form: false, studio: "" };
  await page.goto(`${base}/`);
  await page.waitForSelector("#username", { timeout: 30000 });
  await mark("login");   // the EMPTY Keycloak form: nothing is marked once a password is typed
  await keycloak(persona);
  const found = await waitUntil(page, { what: "Dify behind its front door", timeoutMs: 90000, done: async () => {
    if (!page.url().startsWith(base)) return undefined;
    if (await firstVisible(page, dify.PASSWORD)) return "form";
    if (/\/apps(\/|\?|$)/.test(page.url()) && !(await firstVisible(page, dify.PASSWORD))) return "studio";
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
  await waitUntil(page, { what: "Dify's Studio after its sign-in", timeoutMs: 90000, done: async () => {
    if (await firstVisible(page, dify.PASSWORD)) {
      const wrong = await page.getByText(/invalid|incorrect|wrong|failed/i).first().isVisible().catch(() => false);
      if (wrong) throw new Error("Dify refused its administrator's sign-in (the form shows an error)");
      return undefined;
    }
    return /\/apps(\/|\?|$)/.test(page.url()) || undefined;
  } });
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
export async function difyOpen(page, base, name, { changes = [] } = {}) {
  if (!/\/apps(\/|\?|$)/.test(page.url())) await page.goto(`${base}/apps`);
  const card = page.getByText(name, { exact: true }).first();
  await card.waitFor({ timeout: 30000 });
  await click(card, { changes });
  await page.waitForURL(/\/app\/[0-9a-f-]{8,}\//, { timeout: 30000 });
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
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
