// WP-288 / ADR-0618: the walkthrough of "Identity and personas", 5-minute version, for evaluations/browser/record.mjs.
//
// Two takes, one per persona, each in its own browser context and its own video (`takes`): consultant-02 plays the
// rows 0:45 and 2:30, sale-01 the rows 1:30 and 3:30. The two play the SAME screens, which is the point of the page:
// the Keycloak form (login), UnifAI's first screen (unifai), the Team workspace selector open (workspaces), Open
// WebUI's home page (webui), the question about its tools (q-sent, q-done), then end. The prompt is the page's,
// verbatim, the same for both (`node record.mjs --check identity-personas`).
//
// workspaces: the take fails unless the selector lists exactly what the page says for that persona (consultant-02:
// agent-arkos, agent-tekos, consultant; sale-01: agent-comage, sales, and neither agent-tekos nor consultant).
// q-done: the owner's decision of 2026-11-15 shows the tools by a question, not by the tools button. The prompt is
// untested on the page: no check is made on the answer's wording, and the take prints its first 400 characters in
// its log so the page's "You should see" cells can be set from what was seen.
//
// Each take costs one answer on its persona's budget and creates ONE Open WebUI chat, deleted by its id in cleanup().
// In UnifAI nothing is created: "Team" and the open selector are screen state, kept by neither the browser nor the
// server (ViewContext, fork v0.1.72), and no workspace is clicked.
//
// UnifAI's selectors are guesses from the fork's UI source; Open WebUI's were seen live on 2026-11-15 (the shared
// owui* helpers). scout() reports each one, asks nothing and creates nothing.
import { buttons, click, firstVisible, onScreen, owui, owuiAnswered, owuiAsk, owuiChats, owuiDeleteChat, owuiHome, unifai, unifaiSignIn,
         waitUntil, wordsOnScreen } from "./_helpers.mjs";

export const takes = [
  { name: "consultant-02", persona: "consultant-02" },
  { name: "sale-01", persona: "sale-01" },
];
export const page = "docs/demo/scenarios/governance/identity-personas.md";
export const viewport = { width: 1280, height: 800 };
export const markers = ["login", "unifai", "workspaces", "webui", "q-sent", "q-done", "end"];
// The sign-ins (login to unifai) are never shown as motion.
export const motion_from = "unifai";
export const changes = [];
export const prompts = {
  "2:30": "Which tools can you use for me? List their names.",
  "3:30": "Which tools can you use for me? List their names.",
};
export const url = unifai.url;
export const sends = /\/api2\/sessions\/(user\.session\.(create|submit|execute)|session\.(delete|cancel|approval))|\/api\/(chat\/completions|chat\/completed|v1\/chats\/new|v1\/chats\/[^/]+$|v1\/tasks\/)/;

// What the page says each persona sees in UnifAI's workspace selector, and the row its question is.
const EXPECTED = {
  "consultant-02": { workspaces: ["agent-arkos", "agent-tekos", "consultant"], absent: [], row: "2:30" },
  "sale-01": { workspaces: ["agent-comage", "sales"], absent: ["agent-tekos", "consultant"], row: "3:30" },
};
const ALL_WORKSPACES = ["agent-arkos", "agent-tekos", "agent-comage", "consultant", "sales"];
const TEAM = ["button:text-is('Team')"];                                                             // guess (Sidebar.tsx)
// The selector under Personal | Team: a button with a chevron, showing the selected team or "Select team".
const SELECTOR = ["button:has(svg.lucide-chevron-down)", "button:has-text('Select team')"];          // guess (Sidebar.tsx)
const OVERLAY = "div.fixed.inset-0";                                                                 // guess: closes the selector

// Open WebUI's address: the cluster's, or the offline test's stand-in.
const webui = (domain) => process.env.RECORD_BASE_URL_OWUI || owui.url(domain);

// Which workspace names are on screen as a whole text of their own (never "consultant" inside "consultant-02").
async function listed(page) {
  const found = {};
  for (const name of ALL_WORKSPACES) found[name] = await page.getByText(name, { exact: true }).first().isVisible().catch(() => false);
  return found;
}

// UnifAI: switch to Team and open the workspace selector. Nothing in the list is clicked. Returns what matched.
async function openSelector(page) {
  const team = await firstVisible(page, TEAM);
  if (!team) throw new Error(`the Team switch was not found (${TEAM.join(" | ")})`);
  await click(team, { changes });
  const selector = await waitUntil(page, { what: "the workspace selector", timeoutMs: 20000, done: async () => (await firstVisible(page, SELECTOR)) || undefined });
  await page.waitForTimeout(1200);   // the teams load, the first one is shown on the button
  await click(selector, { changes });
  await page.waitForTimeout(1000);
  return { team: team.matched, selector: selector.matched };
}

async function closeSelector(page) {
  const overlay = page.locator(OVERLAY).last();
  if (await overlay.isVisible().catch(() => false)) await overlay.click({ position: { x: 900, y: 600 } }).catch(() => {});
  else await page.keyboard.press("Escape");
  await page.waitForTimeout(500);
}

// Open WebUI with the same Keycloak session: no form is expected; if Keycloak asks again, the same persona signs in
// (nothing is marked on that form).
async function toWebui({ page, domain, keycloak, persona }) {
  const base = webui(domain);
  await page.goto(`${base}/oauth/oidc/login`);
  const first = await waitUntil(page, { what: "Open WebUI after the single sign-on", timeoutMs: 60000,
                                        done: async () => (await firstVisible(page, ["#chat-input", "#username"])) || undefined });
  if (first.matched === "#username") await keycloak(persona);
  await owuiHome(page, base, { changes });
}

// Sign in to UnifAI (the Keycloak form is the `login` marker), then to Open WebUI with the same session, so that
// what the persona owns there (its chats) can be listed before anything is sent.
export async function enter(ctx) {
  const { page, domain, persona } = ctx;
  if (!EXPECTED[persona]) throw new Error(`no expectation for the persona ${persona}`);
  // Open WebUI's sidebar is closed before its first screen is drawn, on its own origin only.
  await page.addInitScript((host) => { if (location.host === host) { try { localStorage.setItem("sidebar", "false"); } catch { /* storage refused */ } } },
                           new URL(webui(domain)).host);
  await unifaiSignIn(ctx, persona);
  await toWebui(ctx);
}

export async function owned({ page, domain }) {
  // The chats are Open WebUI's: asked from its own origin.
  if (!page.url().startsWith(webui(domain))) await page.goto(`${webui(domain)}/`).then(() => page.waitForSelector("#chat-input", { timeout: 60000 }));
  return owuiChats(page);
}

export async function run(ctx) {
  const { page, base, domain, mark, log, state, persona } = ctx;
  const want = EXPECTED[persona];
  await page.goto(`${base}/`);
  await waitUntil(page, { what: "UnifAI's first screen", timeoutMs: 60000, done: async () => (await firstVisible(page, TEAM)) || undefined });
  await page.waitForTimeout(1000);
  await mark("unifai");

  await openSelector(page);
  await page.getByText(want.workspaces[0], { exact: true }).first().waitFor({ timeout: 20000 }).catch(() => {});
  const seen = await listed(page);
  const missing = want.workspaces.filter((name) => !seen[name]);
  const unexpected = ALL_WORKSPACES.filter((name) => seen[name] && !want.workspaces.includes(name));
  if (missing.length || unexpected.length) {
    throw new Error(`the workspace selector of ${persona} is not the page's: ${missing.length ? "missing " + missing.join(", ") : ""}`
      + `${missing.length && unexpected.length ? "; " : ""}${unexpected.length ? "not expected " + unexpected.join(", ") : ""}`);
  }
  await mark("workspaces");
  await closeSelector(page);

  await page.goto(`${webui(domain)}/`);
  await owuiHome(page, webui(domain), { changes });
  await mark("webui");

  const prompt = prompts[want.row];
  state.sent = true;   // from here a chat may exist, even if its id is never read: cleanup() must not stay silent
  state.prompt = prompt;
  await owuiAsk(page, prompt, state);
  await mark("q-sent");
  await page.waitForURL(owui.CHAT_ID, { timeout: 60000 });
  state.chatId = page.url().match(owui.CHAT_ID)[1];
  state.created.push({ kind: "chat", id: state.chatId });
  log(`chat ${state.chatId} created`);
  const answer = await owuiAnswered(page, state.chatId, 1);
  await page.waitForTimeout(1500);
  log(`answer of ${persona} to the ${want.row} question (${answer.length} chars): ${answer.replace(/\s+/g, " ").slice(0, 400)}`);
  await mark("q-done");

  await page.waitForTimeout(800);
  await mark("end");
}

// What a take will meet, for the price of the two sign-ins: UnifAI's Team switch and workspace selector with the
// names it lists, and Open WebUI's home page. No workspace is clicked, nothing is typed, no chat exists afterwards.
export async function scout(ctx) {
  const { page, base, domain, step, state, persona } = ctx;
  if (!state.scout) throw new Error("scout() runs only in scout mode");
  const before = (await owuiChats(page).catch(() => [])).length;
  // What "Accept" on the AI Disclosure notice did at the sign-in: no write expected, a sessionStorage key added.
  await step("disclosure", async () => {
    if (state.disclosure.writes.length) throw new Error(`"Accept" sent ${state.disclosure.writes.join(", ")}`);
    return { ...state.disclosure };
  });
  await step("unifai", async () => {
    await page.goto(`${base}/`);
    await waitUntil(page, { what: "UnifAI's first screen", timeoutMs: 60000, done: async () => (await firstVisible(page, [...TEAM, ...unifai.NAV.chats])) || undefined });
    await page.waitForTimeout(1000);
    return { url: page.url().replace(/[?#].*/, ""), team_selector: ((await firstVisible(page, TEAM)) || {}).matched || "",
             words: await wordsOnScreen(page, [/Personal/, /Team/, new RegExp(persona)]) };
  });
  await step("workspaces", async () => {
    const matched = await openSelector(page);
    await page.getByText(EXPECTED[persona].workspaces[0], { exact: true }).first().waitFor({ timeout: 20000 }).catch(() => {});
    const seen = await listed(page);
    const want = EXPECTED[persona].workspaces;
    const found = { ...matched, listed: seen, as_the_page_says: ALL_WORKSPACES.every((name) => seen[name] === want.includes(name)),
                    overlay_on_screen: await page.locator(OVERLAY).last().isVisible().catch(() => false),
                    buttons_near_selector: (await buttons(page, matched.selector)).near.slice(0, 20) };
    await closeSelector(page);
    return found;
  });
  await step("webui", async () => {
    await toWebui(ctx);
    return { url: page.url().replace(/[?#].*/, ""), chat_link_on_screen: await onScreen(page, owui.CHAT_LINK), chat_open: owui.CHAT_ID.test(page.url()) };
  });
  await step("closed", async () => {
    const typed = (await page.locator("#chat-input").innerText().catch(() => "")).trim();
    if (typed) throw new Error("the chat input is not empty after the scout");
    const after = (await owuiChats(page)).length;
    if (after !== before) throw new Error(`${persona} owns ${after} chats after the scout, ${before} before it`);
    return { chats: after };
  });
}

export async function cleanup({ page, log, state, persona }) {
  return owuiDeleteChat(page, state, persona, state.prompt || prompts["2:30"], log);
}
