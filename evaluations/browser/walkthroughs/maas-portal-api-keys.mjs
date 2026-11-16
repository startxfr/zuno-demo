// WP-290 / ADR-0618: the walkthrough of "MaaS portal and API keys", 5-minute version, for
// evaluations/browser/record.mjs.
//
// The rows of docs/demo/scenarios/rhoai/maas-portal-api-keys.md, as ai-dev-01: the Keycloak form (login), the portal
// (portal, row 0:00), its API keys page (keys), the create dialog filled (create-form), the key created (created,
// row 1:00), then the calls of rows 2:15 (calls) and 3:00 (answer), then end. Row 4:15 is words.
//
// THE KEY IS NEVER SHOWN, and never held by this file (the owner's decision of 2026-11-16). The recorder takes it
// out of the create call's answer before the portal receives it and gives the portal a masked value instead
// (`ctx.interceptSecret`, `creates`): the portal's shown-once dialog therefore displays `sk-oai-` and bullets. The
// calls of rows 2:15 and 3:00 are made BY THE RECORDER with the key it holds (`ctx.fetchWithSecret`), and their real
// results are drawn on a plain page this file writes in the browser, headed as such: the page's commands verbatim,
// `$MAAS_API_KEY` unexpanded, each followed by what the gateway really answered. It is not a terminal and does not
// look like one.
//
// What it costs and leaves: ONE key created on the subscription gpt-oss-20b-ocp-ai-dev and revoked by its id in
// cleanup(), pass or fail; the revoke is then PROVED (the same call with the key must be refused) and the take fails,
// naming the key's id and name, if it is not. One chat completion on ai-dev-01's subscription. A revoked key may stay
// listed as revoked: owned() counts the keys that are not.
//
// NOTHING of the portal was seen live when this was written: its menu, its dialog and its API are guesses, marked
// `guess`. scout() signs in, opens the API keys page, opens the create dialog and CANCELS it, and reports the
// controls and the list's shape (field names only); it creates nothing. The dialog's result (the key shown once)
// cannot be scouted: the first take is its scout.
import { click, describe, firstVisible, newText, waitUntil, wordsOnScreen } from "./_helpers.mjs";

export const persona = "ai-dev-01";
export const creates = ["MAAS_API_KEY"];
export const page = "docs/demo/scenarios/rhoai/maas-portal-api-keys.md";
export const viewport = { width: 1280, height: 800 };
export const markers = ["login", "portal", "keys", "create-form", "created", "calls", "answer", "end"];
export const motion_from = "portal";
export const changes = [];
// The page's commands, verbatim (`node record.mjs --check maas-portal-api-keys`): drawn as text, run by the recorder.
export const prompts = {
  "2:15": "curl -s -o /dev/null -w '%{http_code}\\n' $MAAS/v1/models",
  "3:00": "curl -s $MAAS/v1/chat/completions -H \"Authorization: Bearer $MAAS_API_KEY\" -H 'Content-Type: application/json' -d '{\"model\":\"gpt-oss-20b\",\"messages\":[{\"role\":\"user\",\"content\":\"In one short sentence, say what you can help me with.\"}],\"max_tokens\":64}'",
};
export const url = (domain) => `https://rh-ai.${domain}/maas-consumer-portal`;
// The requests a scout refuses: a key created, revoked or changed.
// (The portal READS its key list by a POST, .../api-keys/search, scout of 2026-11-16: that one is a read and passes.)
export const sends = /api-?keys(?!\/search(\/|\?|$))/i;

// The write guard (record.mjs): the only writes the take may send to the portal. (Its revoke is sent by the
// recorder's own client in cleanup(), like the calls with the key: neither goes through the page.)
export const allows = [
  { method: "POST", path: /api-?keys\/search\/?$/i, what: "the key list (a read)" },
  { method: "POST", path: /api-?keys\/?$/i, what: "create the take's key" },
];
const SUBSCRIPTION = "gpt-oss-20b-ocp-ai-dev";   // the page's row 1:00
const KEY = /sk-oai-[A-Za-z0-9_-]{8,}/;          // the page: a key starting with sk-oai-
const MASK = "sk-oai-••••••••••••••••••••••••";
const KEYS_API = /api-?keys/i;                   // seen live: /maas-consumer-portal/maas/api/v1/api-keys/search (the list, a POST)
const SEARCH = /api-?keys\/search\/?$/i;         // the list: a read made by POST
const CREATE_API = /api-?keys\/?(\?.*)?$/i;      // guess: the create is a POST to the collection itself
const PROVIDER_LINK = ["a[title='Log in with openshift']", "a.idp:text-is('openshift')", "a:text-is('openshift')"];   // seen live for rh-ai, 2026-11-16
const APPROVE = /\/oauth\/authorize\/approve|Authorize Access/i;
const SHELL = [/AI asset endpoints/, /API keys/, /Playground/];   // the page's row 0:00
const NAV_KEYS = ["nav a[href*='/maas/keys']", "nav a:has-text('API keys')", "a:has-text('API keys')", "[role='tab']:has-text('API keys')", "button:has-text('API keys')"];   // guess
const CREATE = ["button:has-text('Create API key')", "button:has-text('Create key')", "button:has-text('Create')", "button:has-text('Generate')"];   // guess
const DIALOG = "[role='dialog']";
// The dialog as the scout of 2026-11-16 saw it: Name*, Description, Subscription* ("Select a subscription"),
// Expiration* (30 days by default, left as it is), "Create API key" (disabled until filled) and Cancel.
const NAME = ["[role='dialog'] input[type='text']", "[role='dialog'] input:not([type])"];   // the key's name: the dialog's first text input
const SUBMIT = ["[role='dialog'] button:has-text('Create API key')", "[role='dialog'] button[type='submit']", "[role='dialog'] button:has-text('Create')"];   // the first seen live

const maas = (domain) => process.env.RECORD_BASE_URL_MAAS || `https://maas.${domain}/zuno-ai-run/gpt-oss-20b`;
const CHAT_BODY = prompts["3:00"].match(/-d '(.*)'$/)[1];
const esc = (text) => String(text).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

// The rows of a key list, whatever its envelope, and the ids of those that are not revoked.
// (the search answers {data: ...} whose value is not itself the list, rescout of 2026-11-16: the list is looked for
// one level deeper too; an envelope that holds nothing, null or {}, is an empty list.)
const NAMES = ["data", "items", "api_keys", "apiKeys", "keys", "results", "object_list"];
function rows(body, depth = 0) {
  if (Array.isArray(body)) return body;
  if (body === null || body === undefined) return depth ? [] : null;
  if (typeof body !== "object") return null;
  for (const name of NAMES) if (Array.isArray(body[name])) return body[name];
  if (depth < 2) for (const name of NAMES) if (name in body) { const inner = rows(body[name], depth + 1); if (inner) return inner; }
  return depth && !Object.keys(body).length ? [] : null;
}
// The shape of an answer, two levels of key names and the kind of each value: never a value.
const shape = (body, depth = 0) => (Array.isArray(body) ? `list(${body.length})` : body === null ? "null" : typeof body !== "object" ? typeof body
  : depth >= 2 ? "object" : Object.fromEntries(Object.keys(body).slice(0, 12).map((key) => [key, shape(body[key], depth + 1)])));
const strictId = (row) => String(row.id || row.key_id || row.keyId || row.jti || "");
const idOf = (row) => strictId(row) || String(row.name || "");
// Is this text on screen as a whole text of its own, anywhere (an <option> of a closed select is not)?
async function shows(scope, text) {
  const hits = scope.getByText(text, { exact: true });
  for (let i = 0; i < Math.min(await hits.count(), 10); i += 1) if (await hits.nth(i).isVisible().catch(() => false)) return hits.nth(i);
  return null;
}
const live = (row) => !/revok|expired|inactive|deleted/i.test(String(row.status || row.state || ""));

// Open the API keys page and read the list the portal itself fetched: {path, rows}. The path is kept: the revoke
// uses it. The list is read from the portal's own request, so no endpoint is guessed.
async function openKeys(page, state) {
  const isList = (r) => { const path = new URL(r.url()).pathname; return r.status() === 200 && ((r.request().method() === "GET" && KEYS_API.test(path)) || (r.request().method() === "POST" && SEARCH.test(path))); };
  const listed = page.waitForResponse(isList, { timeout: 60000 }).catch(() => null);
  const link = await firstVisible(page, NAV_KEYS);
  if (!link) throw new Error(`the API keys entry was not found (${NAV_KEYS.join(" | ")})`);
  await click(link, { changes });
  const response = await listed;
  if (!response) throw new Error("the portal fetched no key list (no GET whose path holds api-keys, no POST to api-keys/search): the take could not tell what it creates");
  const body = await response.json().catch(() => null);
  const list = rows(body);
  if (!list) throw new Error(`the portal's key list is not a list (its answer's shape: ${JSON.stringify(shape(body)).slice(0, 200)})`);
  // The same request is made again later to read the list: its address, its method, its body and its own headers
  // (never logged; the session's cookies are the browser's).
  const request = response.request();
  const headers = Object.fromEntries(Object.entries(await request.allHeaders()).filter(([name]) => /^(content-type|accept|authorization|x-)/i.test(name)));
  state.list = { url: response.url(), method: request.method(), data: request.postData() || undefined, headers };
  state.keysPath = new URL(response.url()).pathname.replace(/\/search\/?$/i, "");
  state.listShape = { method: request.method(), path: new URL(response.url()).pathname, envelope: shape(body),
                      search_body_keys: (() => { try { return Object.keys(JSON.parse(request.postData() || "{}")); } catch { return []; } })() };
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
  return list;
}

// The key list again, by the same request the portal made (the persona's session, the page's own headers).
async function keys(page, state) {
  const got = await page.request.fetch(state.list.url, { method: state.list.method, data: state.list.data, headers: state.list.headers, failOnStatusCode: false, timeout: 30000 });
  const list = got.status() === 200 ? rows(await got.json().catch(() => null)) : null;
  if (!list) throw new Error(`ai-dev-01's key list could not be read (HTTP ${got.status()})`);
  return list;
}

export async function enter({ page, base, mark, keycloak, state }) {
  await page.goto(`${base}/`);
  const provider = await waitUntil(page, { what: "the OpenShift sign-in page", timeoutMs: 60000, done: async () => (await firstVisible(page, [...PROVIDER_LINK, "#username"])) || undefined });
  if (provider.matched !== "#username") await click(provider, { changes });
  await page.waitForSelector("#username", { timeout: 30000 });
  await mark("login");   // the EMPTY Keycloak form: nothing is marked once the password is typed
  await keycloak(persona);
  await waitUntil(page, { what: "the portal", timeoutMs: 90000, done: async () => {
    if (APPROVE.test(page.url()) || APPROVE.test(await page.locator("body").innerText().catch(() => ""))) {
      throw new Error(`OpenShift asks ${persona} to authorize the portal's access: a take grants nothing; sign in once by hand, then take again`);
    }
    return (page.url().startsWith(base) && (await firstVisible(page, NAV_KEYS))) || undefined;
  } });
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
  if (await page.locator(DIALOG).first().isVisible().catch(() => false)) throw new Error("a dialog covers the portal: the take stops, it dismisses nothing it does not know");
  state.shell = await wordsOnScreen(page, SHELL);
  if (!state.scout) await mark("portal");   // before the key list is opened: owned() needs the list
  state.listed = await openKeys(page, state);
}

export async function owned({ page, state }) {
  return (await keys(page, state)).filter(live).map((row) => ({ kind: "api-key", id: idOf(row) }));
}

// The plain page of the recorder's calls: a heading that says what it is, then each command of the page and its
// real result. Nothing is typed or animated; the key is the text $MAAS_API_KEY.
async function draw(page, sections) {
  await page.setContent(`<!doctype html><title>Calls made by the recorder</title>
<body style="font:17px/1.5 system-ui,sans-serif;margin:32px 48px;color:#151515;background:#fff">
<h1 style="font-size:24px;margin:0 0 4px">Calls made by the recorder with the key just created</h1>
<p style="margin:0 0 20px;color:#555">The key is not shown: the recorder holds it and sends it. Each command is the page's; each result is what the gateway answered.</p>
${sections.map((s) => `<section style="margin:0 0 18px;padding:12px 16px;border:1px solid #c7c7c7;border-radius:6px">
<div style="font:14px/1.4 ui-monospace,monospace;color:#333;white-space:pre-wrap;word-break:break-all">${esc(s.command)}</div>
<div style="margin-top:8px"><strong>${esc(s.label)}</strong> <span style="white-space:pre-wrap">${esc(s.result)}</span></div></section>`).join("")}</body>`);
  await page.waitForTimeout(600);
}

export async function run({ page, domain, mark, log, state, interceptSecret, fetchWithSecret }) {
  await mark("keys");
  const open = await firstVisible(page, CREATE);
  if (!open) throw new Error(`the create button was not found (${CREATE.join(" | ")})`);
  await click(open, { changes });
  const dialog = page.locator(DIALOG).first();
  await dialog.waitFor({ timeout: 15000 });
  state.keyName = `zuno-demo-gif-${new Date().toISOString().replace(/\D/g, "").slice(0, 14)}`;   // this take's key, by a name of its own
  const name = await firstVisible(page, NAME);
  if (name) { await name.click(); await page.keyboard.type(state.keyName, { delay: 20 }); }
  // The subscription: when the dialog does not already show it, its chooser is opened and the entry clicked.
  if (!(await shows(dialog, SUBSCRIPTION))) {
    const chooser = await firstVisible(page, [`${DIALOG} button:has-text('Select a subscription')`, `${DIALOG} [role='combobox']`, `${DIALOG} select`, `${DIALOG} button[aria-haspopup]`]);   // the first seen live, 2026-11-16
    if (chooser) { await click(chooser, { changes }); await page.waitForTimeout(500); }
  }
  // The entry of the open list (its text may carry more than the name), else the name as a text of its own.
  const entry = page.locator("[role='option'], [role='menuitem'], [role='listbox'] li, [role='menu'] li").filter({ hasText: SUBSCRIPTION }).first();
  if (await entry.isVisible().catch(() => false)) await click(entry, { changes });
  else if (!(await shows(page, SUBSCRIPTION))) throw new Error(`the create dialog does not offer the subscription ${SUBSCRIPTION}`);
  await page.waitForTimeout(600);
  if (!(await dialog.getByText(SUBSCRIPTION).first().isVisible().catch(() => false))) throw new Error(`the create dialog does not show ${SUBSCRIPTION} as chosen`);
  await mark("create-form");

  // From here a key may exist. The recorder stands between the portal and the answer of the create call.
  state.creating = true;
  const created = interceptSecret("MAAS_API_KEY", { url: CREATE_API, method: "POST", pattern: KEY, mask: MASK });
  // If the portal ever sends the value it was given back to its server, the mask would break that call: it is seen.
  const sentBack = [];
  page.on("request", (r) => { if ((r.postData() || "").includes(MASK) || decodeURIComponent(r.url()).includes(MASK)) sentBack.push(`${r.method()} ${new URL(r.url()).pathname}`); });
  const submit = await firstVisible(page, SUBMIT);
  if (!submit) throw new Error(`the dialog's create button was not found (${SUBMIT.join(" | ")})`);
  if (await page.locator(submit.matched).first().isDisabled().catch(() => false)) throw new Error("the dialog's create button is still disabled: a required field (Name, Subscription, Expiration) is not filled");
  await click(submit, { changes });
  const answer = await Promise.race([created, page.waitForTimeout(60000).then(() => null)]);
  if (!answer) throw new Error("the create call was not seen within 60 s (no POST to a path ending in api-keys): a key may exist, check the portal by hand");
  if (answer.status >= 300 || !answer.found) throw new Error(`the portal's create call answered HTTP ${answer.status} with ${answer.found ? "a" : "no"} key in it`);
  state.keyId = answer.body ? strictId(answer.body) : "";
  state.created.push({ kind: "api-key", id: state.keyId || state.keyName });
  log(`key created (id ${state.keyId || "not in the answer"}, name ${state.keyName}); the portal received a masked value`);
  await page.waitForTimeout(1500);
  if (!(await page.getByText("sk-oai-", { exact: false }).first().isVisible().catch(() => false))) log("the portal does not show the masked key on screen after the create: check created.png");
  if (sentBack.length) throw new Error(`the portal sent the key it was shown back to its server (${[...new Set(sentBack)].join(", ")}): the mask breaks that follow-up, the take stops (the key is revoked)`);
  await mark("created");

  // Rows 2:15 and 3:00: the recorder's own calls, their real results drawn on a plain page.
  const endpoint = maas(domain);
  const none = await page.request.get(`${endpoint}/v1/models`, { failOnStatusCode: false, timeout: 60000 });
  const withKey = await fetchWithSecret("MAAS_API_KEY", { url: `${endpoint}/v1/models`, headers: { Authorization: "Bearer {secret}" } });
  if (none.status() !== 401 || withKey.status !== 200) throw new Error(`the gateway answered ${none.status()} without a key and ${withKey.status} with it: the page says 401, then 200`);
  const sections = [
    { command: prompts["2:15"], label: "HTTP status:", result: String(none.status()) },
    { command: `${prompts["2:15"]} -H "Authorization: Bearer $MAAS_API_KEY"`, label: "HTTP status:", result: String(withKey.status) },
  ];
  await draw(page, sections);
  await mark("calls");
  const chat = await fetchWithSecret("MAAS_API_KEY", { url: `${endpoint}/v1/chat/completions`, method: "POST",
    headers: { Authorization: "Bearer {secret}", "Content-Type": "application/json" }, body: CHAT_BODY });
  let said = null;
  try { said = JSON.parse(chat.text); } catch { /* not JSON */ }
  const content = said && said.choices && said.choices[0] && said.choices[0].message ? String(said.choices[0].message.content || "") : "";
  if (chat.status !== 200 || !content.trim() || !said.usage) throw new Error(`the chat completion answered HTTP ${chat.status} ${content.trim() ? "" : "with no content "}${said && said.usage ? "" : "and no usage block"}`.trim());
  sections.push({ command: prompts["3:00"], label: "choices[0].message.content:", result: `${content.trim().slice(0, 600)}\nusage: ${JSON.stringify(said.usage)}` });
  await draw(page, sections);
  await mark("answer");
  await page.waitForTimeout(800);
  await mark("end");
}

// What a take will meet, for the price of a sign-in: the portal's shell, the API keys page with the shape of its
// list (field names only, no value), and the create dialog, opened and CANCELLED. Nothing is created.
export async function scout({ page, step, state }) {
  if (!state.scout) throw new Error("scout() runs only in scout mode");
  const before = state.listed.filter(live).length;
  await step("portal", async () => ({ shell: state.shell }));
  await step("keys", async () => ({ list_path: state.keysPath, list_request: state.listShape, keys: state.listed.length, not_revoked: before,
                                    fields: [...new Set(state.listed.flatMap((row) => Object.keys(row || {})))].sort().slice(0, 30),
                                    create_selector: ((await firstVisible(page, CREATE)) || {}).matched || "" }));
  await step("create-dialog", async () => {
    const open = await firstVisible(page, CREATE);
    if (!open) throw new Error(`no create button among ${CREATE.join(" | ")}`);
    const text = await page.locator("body").innerText();
    await click(open, { changes });
    await page.locator(DIALOG).first().waitFor({ timeout: 15000 });
    await page.waitForTimeout(800);
    return { text: (await newText(page, text)).slice(0, 20).map((l) => l.slice(0, 80)), name_selector: ((await firstVisible(page, NAME)) || {}).matched || "",
             submit_selector: ((await firstVisible(page, SUBMIT)) || {}).matched || "", subscription_offered: await (async () => {
               // The subscription's list is opened, read and closed with Escape: nothing is chosen.
               if (await shows(page, SUBSCRIPTION)) return true;
               const chooser = await firstVisible(page, [`${DIALOG} button:has-text('Select a subscription')`, `${DIALOG} [role='combobox']`]);
               if (!chooser) return false;
               await click(chooser, { changes });
               await page.waitForTimeout(600);
               const offered = await page.locator("[role='option'], [role='menuitem'], [role='listbox'] li, [role='menu'] li").filter({ hasText: SUBSCRIPTION }).first().isVisible().catch(() => false);
               await page.keyboard.press("Escape");
               await page.waitForTimeout(300);
               return offered;
             })(),
             controls: (await describe(page, DIALOG, 40)).slice(0, 25) };
  });
  await step("closed", async () => {
    const dialog = page.locator(DIALOG).first();
    const cancel = dialog.getByRole("button", { name: /^(Cancel|Close)$/ }).first();
    if (await cancel.count()) await click(cancel, { changes }); else await page.keyboard.press("Escape");
    await dialog.waitFor({ state: "hidden", timeout: 15000 });
    const after = (await keys(page, state)).filter(live).length;
    if (after !== before) throw new Error(`ai-dev-01 holds ${after} keys after the scout, ${before} before it`);
    return { not_revoked: after };
  });
}

// Revoke the key this take created, by its id, and PROVE it: the same call with the key must now be refused. A
// take whose key still answers fails and names it. The key's value is never needed here: the recorder sends it.
export async function cleanup({ page, domain, log, state, fetchWithSecret }) {
  if (!state.creating) return null;
  const named = `the key ${state.keyId || "(id unknown)"} named ${state.keyName}`;
  let id = state.keyId;
  if (!id) {   // the create answer carried no id: the one key that was not there before, by this take's own name
    const mine = (await keys(page, state).catch(() => [])).filter((row) => String(row.name || row.display_name || row.description || "") === state.keyName);
    if (mine.length === 1) id = idOf(mine[0]);
  }
  if (!id) throw new Error(`${named} could not be found by an id: it was NOT revoked; revoke it by hand in the portal (API keys)`);
  const gone = await page.request.delete(`${new URL(state.list.url).origin}${state.keysPath.replace(/\/$/, "")}/${encodeURIComponent(id)}`, { headers: state.list.headers, failOnStatusCode: false, timeout: 30000 });
  // The proof, when the recorder holds the key: the gateway must refuse it now. When it holds none (the create
  // answer carried no key it could take out), the delete's own answer and the list are all there is.
  const proof = await fetchWithSecret("MAAS_API_KEY", { url: `${maas(domain)}/v1/models`, headers: { Authorization: "Bearer {secret}" } }).catch(() => null);
  if (proof && ![401, 403].includes(proof.status)) {
    throw new Error(`${named} was NOT revoked: its delete answered HTTP ${gone.status()} and the gateway still answers ${proof.status} with it; revoke it by hand in the portal (API keys) NOW`);
  }
  if (!proof) {
    const still = (await keys(page, state).catch(() => null));
    if (gone.status() >= 300 || !still || still.filter(live).some((row) => idOf(row) === id)) {
      throw new Error(`${named} was NOT revoked (delete HTTP ${gone.status()}) and the recorder holds no key to prove it: revoke it by hand in the portal (API keys) NOW`);
    }
    log(`key ${id} revoked (delete HTTP ${gone.status()}); no key was held, so the list is the only proof`);
    return true;
  }
  log(`key ${id} revoked (delete HTTP ${gone.status()}); the gateway now answers ${proof.status} with it`);
  return true;
}
