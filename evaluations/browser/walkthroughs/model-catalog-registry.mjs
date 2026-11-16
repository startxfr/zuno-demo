// WP-289 / ADR-0618: the walkthrough of "Model catalog and registry", 5-minute version, for
// evaluations/browser/record.mjs.
//
// The rows of docs/demo/scenarios/rhoai/model-catalog-registry.md, as ai-dev-01 on the OpenShift AI dashboard: the
// Keycloak form (login), the dashboard's first screen (dashboard, row 0:00), the model catalog opened from the left
// menu (catalog, row 0:45), the catalog narrowed to Red Hat AI validated (validated) and one card opened (card, row
// 2:00), then end. Rows 3:15 and 4:15 are words.
//
// It signs in through the OpenShift sign-in (the provider chooser `openshift`, then Keycloak), the flow the lightspeed
// scout proved on 2026-11-16, with the persona password and nothing else. Read only: it sends no prompt, calls no
// model, deploys nothing, registers nothing; owned() is empty and cleanup() has nothing to delete. It changes no
// setting: when a dialog covers the dashboard (a welcome or a tour), or OpenShift asks to authorize access, the take
// stops and says so; when the source filter is a checkbox, click() refuses it (declare it in `changes` after a scout).
//
// Scouted on demo333 (2026-11-16, 3.6.0-ea.2): the sign-in, the dashboard with no dialog, the left menu (group "AI hub",
// collapsed, holding ONE link "Models"), the Models page opening on its Catalog tab, the catalog cards, the source
// buttons (a toggle group "Source label selection": All models | Red Hat AI - validated models | Red Hat AI models |
// Other models) and a card's page, which loads behind a spinner. The first take (100433) failed on the source label,
// "Red Hat AI - validated models", which the first guess did not match. Selectors marked `guess` are still guesses.
import { buttons, click, describe, firstVisible, newText, waitUntil, wordsOnScreen } from "./_helpers.mjs";

export const persona = "ai-dev-01";
export const page = "docs/demo/scenarios/rhoai/model-catalog-registry.md";
export const viewport = { width: 1280, height: 800 };
export const markers = ["login", "dashboard", "catalog", "validated", "card", "end"];
// The provider chooser and the sign-in (up to dashboard) are never shown as motion.
export const motion_from = "dashboard";
export const changes = [];
export const url = (domain) => `https://rh-ai.${domain}`;
// The requests a scout refuses: a deployment or a registration started from a card (Deploy, Register).
export const sends = /\/(inferenceservices|llminferenceservices|servingruntimes|registered_models|model_versions)(\/|\?|$)/;   // guess

const PROVIDER = "openshift";   // the page: the OpenShift sign-in, Keycloak behind it
const PROVIDER_LINK = [`a[title='Log in with ${PROVIDER}']`, `a.idp:text-is('${PROVIDER}')`, `a:text-is('${PROVIDER}')`];   // seen live in the console, 2026-11-16
const APPROVE = /\/oauth\/authorize\/approve|Authorize Access|Allow selected permissions/i;                               // guess: an OAuth grant page
const NAV = ["#page-sidebar", "nav[aria-label*='Global' i]", "nav"];                                                       // guess
const NAV_GROUP = ["nav button:has-text('AI hub')"];                                                                      // seen collapsed, 2026-11-16
// "Models" is the only link of AI hub (scout of 2026-11-16); the others are kept in case a later version names it.
const NAV_CATALOG = ["nav a:text-is('Catalog')", "nav a:text-is('Model catalog')", "nav a[href*='catalog' i]", "nav a:text-is('Models')"];
const CATALOG_TAB = ["main [role='tab']:has-text('Catalog')", "main a:text-is('Catalog')", "main button:text-is('Catalog')"];   // guess: a tab of the Models page
const SOURCES = /Red Hat AI\s*-\s*validated|Other models/;                                                              // seen, 2026-11-16
// The source button, inside its toggle group: the banner's "Explore Red Hat AI - validated models" and the link "Show
// all Red Hat AI - validated models" carry the same words and are not the filter (seen, 2026-11-16).
const VALIDATED = ["[aria-label='Source label selection'] button:has-text('validated')", "button[id='label-Red Hat AI validated']"];
// guess. The home page's project cards are `.pf-v6-c-card` too (scout of 2026-11-16): a card is looked for only once
// the catalog's sources are on screen.
const CARD = ["main [data-testid*='catalog-card' i] a", "main [data-testid*='model-card' i] a", "main .pf-v6-c-card a", "main .pf-v5-c-card a", "main article a"];
const DETAIL = ["[data-testid='app-page-title']", "main h1", "h1"];                                                         // "main h1" matched, 2026-11-16
// A card's page draws a spinner first ("Loading...", seen in the scout of 2026-11-16): the card is marked once it is gone.
const LOADING = "main [role='progressbar']";
const DIALOG = "[role='dialog'][aria-modal='true'], .pf-v5-c-backdrop, .pf-v6-c-backdrop";                                  // guess: a welcome or a tour
const DWELL_MS = 2000;   // a presenter's pause on each screen, so that every motion moment has frames to cut

// A card's page, once loaded: its title on screen and no spinner left in it.
async function cardShown(page, before) {
  await waitUntil(page, { what: "the model's card", timeoutMs: 60000,
    done: async () => ((await page.locator("body").innerText()) !== before && (await firstVisible(page, DETAIL))
                       && !(await page.locator(LOADING).first().isVisible().catch(() => false))) || undefined });
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
}

async function noDialog(page, where) {
  if (await page.locator(DIALOG).first().isVisible().catch(() => false)) {
    throw new Error(`a dialog covers the ${where}: a take dismisses nothing that is saved in the user's settings; see the scout`);
  }
}

// The left menu's way to the catalog: the group opened first when the link is inside a collapsed one, then the link,
// then the page's Catalog tab when it has one and another tab is selected. Navigation only. {group, link, tab}
async function openMenu(page) {
  let link = await firstVisible(page, NAV_CATALOG);
  let group = "";
  if (!link) {
    const toggle = await firstVisible(page, NAV_GROUP);
    if (!toggle) throw new Error(`neither the catalog link (${NAV_CATALOG.join(" | ")}) nor a menu group holding it (${NAV_GROUP.join(" | ")}) is on screen`);
    group = toggle.matched;
    await click(toggle, { changes });
    link = await waitUntil(page, { what: "the catalog link in the left menu", timeoutMs: 15000, done: async () => (await firstVisible(page, NAV_CATALOG)) || undefined });
  }
  await click(link, { changes });
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
  let tab = "";
  const toTab = await firstVisible(page, CATALOG_TAB);
  if (toTab && (await toTab.getAttribute("aria-selected").catch(() => null)) !== "true") {
    tab = toTab.matched;
    await click(toTab, { changes });
    await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
  }
  return { group, link: link.matched, tab };
}

// The catalog is on screen: its sources named and at least one card.
async function catalogShown(page) {
  await waitUntil(page, { what: "the model catalog and its sources", timeoutMs: 60000,
    done: async () => (SOURCES.test(await page.locator("body").innerText()) && (await firstVisible(page, CARD))) || undefined });
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
}

export async function enter({ page, base, mark, keycloak }) {
  await page.goto(`${base}/`);
  const provider = await waitUntil(page, { what: "the OpenShift sign-in page", timeoutMs: 60000,
    done: async () => (await firstVisible(page, [...PROVIDER_LINK, "#username"])) || undefined });
  if (provider.matched !== "#username") await click(provider, { changes });
  await page.waitForSelector("#username", { timeout: 30000 });
  await mark("login");   // the EMPTY Keycloak form: nothing is marked once the password is typed
  await keycloak(persona);
  await waitUntil(page, { what: "the OpenShift AI dashboard", timeoutMs: 90000, done: async () => {
    if (APPROVE.test(page.url()) || APPROVE.test(await page.locator("body").innerText().catch(() => ""))) {
      throw new Error(`OpenShift asks ${persona} to authorize the dashboard's access: a take grants nothing; sign in once by hand, then take again`);
    }
    return (page.url().startsWith(base) && (await firstVisible(page, NAV))) || undefined;
  } });
  await page.waitForLoadState("networkidle", { timeout: 60000 }).catch(() => {});
  await page.waitForTimeout(1500);
}

// Nothing a persona owns is touched: the take is read only. The recorder compares this list before and after.
export async function owned() {
  return [];
}

export async function run({ page, mark, log }) {
  await noDialog(page, "dashboard");
  await mark("dashboard");
  await page.waitForTimeout(DWELL_MS);

  const opened = await openMenu(page);
  await catalogShown(page);
  log(`catalog opened from the left menu (${opened.group ? `group ${opened.group}, ` : ""}link ${opened.link}${opened.tab ? `, tab ${opened.tab}` : ""})`);
  await page.waitForTimeout(DWELL_MS);
  await mark("catalog");

  const filter = await firstVisible(page, VALIDATED);
  if (!filter) throw new Error(`the Red Hat AI validated source was not found (${VALIDATED.join(" | ")})`);
  await click(filter, { changes });
  await waitUntil(page, { what: "the validated models", timeoutMs: 30000,
    done: async () => ((await filter.getAttribute("aria-pressed").catch(() => null)) !== "false" && (await firstVisible(page, CARD))) || undefined });
  await page.waitForTimeout(DWELL_MS);
  await mark("validated");

  const card = await firstVisible(page, CARD);
  const name = ((await card.innerText().catch(() => "")) || "").split("\n")[0].trim().slice(0, 80);
  const before = await page.locator("body").innerText();
  await click(card, { changes });
  await cardShown(page, before);
  await page.waitForTimeout(DWELL_MS);
  log(`card opened: ${name || "(no title read)"}`);
  await mark("card");

  await page.waitForTimeout(800);
  await mark("end");
}

// What a take will meet, for the price of a sign-in: the dashboard (a dialog over it?), the left menu and the page it
// opens (dumped even when the catalog is not there), the catalog and its sources, the source filter (a button or a
// checkbox?), and one card, opened only when the catalog was seen. Nothing is deployed or registered: the recorder
// refuses `sends` in a scout, and no Deploy or Register button is clicked.
export async function scout({ page, step, state }) {
  if (!state.scout) throw new Error("scout() runs only in scout mode");
  await step("dashboard", async () => ({ url: page.url().replace(/[?#].*/, ""), dialog_on_screen: await page.locator(DIALOG).first().isVisible().catch(() => false),
                                         nav_selector: ((await firstVisible(page, NAV)) || {}).matched || "",
                                         catalog_link: ((await firstVisible(page, NAV_CATALOG)) || {}).matched || "",
                                         group: ((await firstVisible(page, NAV_GROUP)) || {}).matched || "",
                                         words: await wordsOnScreen(page, [/ai-dev-01/, /OpenShift AI/, /AI hub/, /Catalog/]),
                                         menu: await describe(page, ((await firstVisible(page, NAV)) || {}).matched || "body", 60) }));
  const text = await page.locator("body").innerText();
  await step("menu", async () => {
    const opened = await openMenu(page);
    await page.waitForTimeout(DWELL_MS);
    const heading = await firstVisible(page, DETAIL);
    return { url: page.url().replace(/[?#].*/, ""), ...opened, title: heading ? ((await heading.innerText().catch(() => "")) || "").slice(0, 80) : "",
             tabs: await describe(page, "main [role='tablist']", 20), words: await wordsOnScreen(page, [/Catalog/, /Red Hat AI\s*-\s*validated/, /Other models/, /Registry/, /Deployments/]),
             text: (await newText(page, text)).slice(0, 30), controls: await describe(page, "main", 80) };
  });
  const catalog = await step("catalog", async () => {
    await catalogShown(page);
    const filter = await firstVisible(page, VALIDATED);
    return { url: page.url().replace(/[?#].*/, ""), card_selector: ((await firstVisible(page, CARD)) || {}).matched || "",
             cards: await page.locator(CARD.join(", ")).count(), filter_selector: filter ? filter.matched : "",
             filter_is: filter ? await filter.evaluate((e) => `${e.tagName.toLowerCase()} role=${e.getAttribute("role") || ""} type=${e.getAttribute("type") || ""}`
               + ` checkbox_inside=${!!e.querySelector("input[type=checkbox], input[type=radio], [role=switch]")}`) : "",
             words: await wordsOnScreen(page, [/Red Hat AI\s*-\s*validated/, /Red Hat AI\b/, /Other models/]),
             buttons: await buttons(page, "main"), controls: await describe(page, "main", 80) };
  });
  await step("card", async () => {
    if (!catalog.ok) throw new Error("the catalog was not seen: no card is opened (the home page's project cards look the same)");
    const card = await firstVisible(page, CARD);
    if (!card) throw new Error(`no card on screen (${CARD.join(" | ")})`);
    const before = await page.locator("body").innerText();
    await click(card, { changes });
    await cardShown(page, before);
    return { url: page.url().replace(/[?#].*/, ""), title_selector: ((await firstVisible(page, DETAIL)) || {}).matched || "",
             words: await wordsOnScreen(page, [/Performance/i, /validated/i, /Deploy/, /Register/]), controls: await describe(page, "main", 60) };
  });
  await step("closed", async () => ({ url: page.url().replace(/[?#].*/, ""), dialog_on_screen: await page.locator(DIALOG).first().isVisible().catch(() => false) }));
}

// Nothing was created: there is nothing to delete.
export async function cleanup() {
  return null;
}
