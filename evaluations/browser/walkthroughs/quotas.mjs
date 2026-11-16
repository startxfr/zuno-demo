// WP-289 / ADR-0618: the walkthrough of "Quotas: one budget per person", 5-minute version, for
// evaluations/browser/record.mjs.
//
// The rows of docs/demo/scenarios/governance/quotas.md, as ai-ops-01, in ONE browser (the chain films one kind per
// GIF: gif.py refuses a terminal take beside a browser take): the Keycloak form of Grafana's sign-in (login), the
// page's class table read on its public GitHub address (classes, row 0:00), the dashboard "Zuno Platform / Five
// experiences" over the last 24 hours, client All (dashboard), the panel "One group across the experiences: tokens
// (over range)" alone over the page (panel, row 1:00), the page's evidence of 2026-11-03 back on GitHub (evidence,
// row 2:30), then end. Row 4:00 is words. The owner's choice of 2026-11-16 (option A, relayed by zuno-demo-reorg).
//
// GitHub: the page is read at its address on the branch devel, as anyone reads it: no sign-in, nothing typed or
// clicked there, only scrolled. When github.com cannot be reached from the recorder, or its layout keeps the table
// or the evidence out of the window, the take fails and says so: the cut then falls back to Grafana only (option B).
//
// Read only in Grafana too. It types no prompt, calls no model and creates nothing: owned() is empty and cleanup()
// has nothing to delete. The panel needs token spend in the last 24 hours, which the page's Start makes (a changing
// unit, run by demo333 with the owner's go): a panel that shows "No data" fails the take. A request that would change
// something in Grafana fails the take. The sign-in's two declared changes are _grafana.mjs's (the OAuth authorization
// of ai-ops-01, the close of Grafana's announcement), as for evaluation-trustyai-evalhub.
//
// NOT yet scouted for this page: GitHub's selectors below are guesses, and panel 7 of the dashboard has not been
// opened alone by any take. The panel lists Keycloak groups and client names (`sales`, `openclaw-sale-01`), no person.
import { describe, read, waitUntil, firstVisible, wordsOnScreen } from "./_helpers.mjs";
import { grafana, grafanaDashboard, grafanaInWindow, grafanaNewsSeen, grafanaSignIn, grafanaViewPanel, grafanaWrites } from "./_grafana.mjs";

export const persona = "ai-ops-01";
export const page = "docs/demo/scenarios/governance/quotas.md";
export const viewport = { width: 1280, height: 800 };
export const markers = ["login", "classes", "dashboard", "panel", "evidence", "end"];
// The sign-in chain (up to classes) is never shown as motion.
export const motion_from = "classes";
export const changes = [grafana.AUTHORIZE_CHANGE, grafana.NEWS_CHANGE];
export const prompts = {};
export const url = grafana.url;
export const sends = grafana.writes;

// gitops/charts/grafana/templates/dashboard-three-experiences.yaml: uid, panel id 7, and the variable client (All).
const DASHBOARD = { uid: "zuno-three-experiences", title: "Five experiences", from: "now-24h", vars: { client: "$__all" } };
const PANEL = { id: 7, title: "One group across the experiences: tokens (over range)", shows: ["group", "client"] };
// The page on GitHub, branch devel (RECORD_BASE_URL_GITHUB replaces github.com in the offline test).
const PAGE_PATH = "/startxfr/zuno-demo/blob/devel/docs/demo/scenarios/governance/quotas.md";
const github = () => `${process.env.RECORD_BASE_URL_GITHUB || "https://github.com"}${PAGE_PATH}`;
const ARTICLE = ["article.markdown-body", ".markdown-body"];   // guess: GitHub's rendered Markdown
// Where the lead paragraph is brought: just under GitHub's sticky file toolbar once the page is scrolled (the scout of
// 2026-11-16: header, repo bar and tabs take 0-167 px at the top of the page and scroll away; the article starts at
// x 337, right of a 320 px file tree). Moved down by steps while the paragraph is covered.
const TOP = 100;
// What each GitHub screen must hold inside the window: the paragraph that leads it (scrolled under the header) and
// the block itself, wholly visible.
const SHOW = {
  classes: { lead: "The classes come from the signed agents release", block: "table", has: "stresstest", words: ["fail_mode", "stresstest"] },
  evidence: { lead: "Evidence of the shared budget", block: "ul", has: "quota_exceeded", words: [] },
};

// Bring the lead paragraph to `top` pixels from the top of the window with the mouse wheel over the article, as a
// reader scrolls (the first scout's programmatic scroll never moved GitHub's page: both stills showed its top). Each
// round wheels until the paragraph is within 30 px of `top`, then waits and looks again: a page that scrolls itself
// back after it renders gets another round. Returns the rounds and wheel steps used.
async function scrollTo(page, lead, top) {
  const box = await page.locator(ARTICLE[0]).first().boundingBox().catch(() => null);
  await page.mouse.move(box ? Math.min(box.x + box.width / 2, page.viewportSize().width - 20) : 800, 500);
  let steps = 0;
  for (let round = 1; round <= 3; round += 1) {
    for (let i = 0; i < 40; i += 1) {
      const a = await lead.boundingBox().catch(() => null);
      if (!a) break;
      const delta = a.y - top;
      if (Math.abs(delta) <= 30) break;
      await page.mouse.wheel(0, Math.max(-700, Math.min(700, delta)));
      steps += 1;
      await page.waitForTimeout(200);
    }
    await page.waitForTimeout(900);
    const a = await lead.boundingBox().catch(() => null);
    if (a && Math.abs(a.y - top) <= 30) return { rounds: round, steps };
  }
  return { rounds: 3, steps };
}

// Is the element drawn on top at the middle of its first line (not under a sticky header or a banner)?
function uncovered(el) {
  const r = el.getBoundingClientRect();
  const top = document.elementFromPoint(Math.min(r.left + 20, innerWidth - 1), Math.min(r.top + 8, innerHeight - 1));
  return Boolean(top) && (el.contains(top) || top.contains(el));
}

// One screen of the page on GitHub: loaded when it is not the page on screen, then scrolled so its lead paragraph
// shows under the header and its block is wholly inside the window. Read only: nothing is typed or clicked there.
async function onGitHub(page, which) {
  const want = SHOW[which];
  if (page.url().replace(/[?#].*/, "") !== github()) {
    try {
      await page.goto(github(), { waitUntil: "domcontentloaded", timeout: 60000 });
    } catch (e) {
      throw new Error(`the page on GitHub could not be reached (${String(e && e.message ? e.message : e).split("\n")[0].slice(0, 120)}): fall back to option B, Grafana only`);
    }
  }
  const article = await waitUntil(page, { what: "the page rendered on GitHub", timeoutMs: 60000, done: async () => (await firstVisible(page, ARTICLE)) || undefined });
  const body = page.locator(article.matched).first();
  const lead = body.locator("p", { hasText: want.lead }).first();
  const block = body.locator(want.block).filter({ hasText: want.has }).first();
  await lead.waitFor({ timeout: 30000 });
  let scrolled = await scrollTo(page, lead, TOP);
  // Still under a sticky bar at TOP: a little lower, at most four times.
  for (let lower = 1; lower <= 4 && !(await read(lead, uncovered).catch(() => false)); lower += 1) scrolled = await scrollTo(page, lead, TOP + 40 * lower);
  const view = page.viewportSize();
  const a = await lead.boundingBox().catch(() => null);
  const b = await block.boundingBox().catch(() => null);
  const shown = { article: article.matched, url: page.url().replace(/[?#].*/, ""), scrolled, lead_top: a ? Math.round(a.y) : null,
                  block_bottom: b ? Math.round(b.y + b.height) : null, lead_uncovered: await read(lead, uncovered).catch(() => false), absent: [] };
  for (const word of want.words) if (!(await grafanaInWindow(page, word))) shown.absent.push(word);
  if (!a || !b || a.y < 0 || b.y + b.height > view.height || !shown.lead_uncovered || shown.absent.length) {
    throw new Error(`the ${which} of the page is not wholly inside the window on GitHub (lead at ${shown.lead_top}, block ends at `
      + `${shown.block_bottom} of ${view.height}, lead uncovered ${shown.lead_uncovered}, not drawn: ${shown.absent.join(" ") || "-"}, `
      + `${scrolled.rounds} rounds, ${scrolled.steps} wheel steps): the layout fights the scroll, fall back to option B, Grafana only`);
  }
  return shown;
}

export async function enter(ctx) {
  ctx.state.writes = grafanaWrites(ctx.page);
  await grafanaSignIn(ctx, persona, { changes });
}

// Nothing is created, so nothing is owned: the before/after comparison is of two empty lists.
export async function owned() {
  return [];
}

async function panel(page, base) {
  const shown = await grafanaViewPanel(page, base, DASHBOARD.uid, PANEL.id, PANEL.title, { from: DASHBOARD.from, vars: DASHBOARD.vars, shows: PANEL.shows });
  if (shown.no_data) {
    throw new Error(`the panel "${PANEL.title}" shows "No data": no token spend in the last 24 hours; the page's Start spends it (a changing unit, with the owner's go)`);
  }
  if (shown.not_in_window.length) throw new Error(`the panel "${PANEL.title}" does not show ${shown.not_in_window.join(", ")} inside the window`);
  return shown;
}

export async function run({ page, base, mark, log, state }) {
  const classes = await onGitHub(page, "classes");
  log(`classes: ${JSON.stringify(classes)}`);
  await page.waitForTimeout(1500);
  await mark("classes");

  await grafanaDashboard(page, base, DASHBOARD.uid, { from: DASHBOARD.from, vars: DASHBOARD.vars });
  await page.getByText(DASHBOARD.title).first().waitFor({ timeout: 30000 });
  await page.waitForTimeout(1000);
  await mark("dashboard");

  const shown = await panel(page, base);
  log(`panel "${PANEL.title}": ${shown.lines.length} lines of text, alone over the page (${shown.view})`);
  await page.waitForTimeout(1500);
  await mark("panel");

  const evidence = await onGitHub(page, "evidence");
  log(`evidence: ${JSON.stringify(evidence)}`);
  await page.waitForTimeout(1500);
  await mark("evidence");
  await page.waitForTimeout(1000);
  await mark("end");
  const wrote = state.writes();
  if (wrote.length) throw new Error(`the take sent ${wrote.join(", ")} to Grafana: it must change nothing there`);
}

// What a take will meet, for the price of a sign-in: the page on GitHub at both places, the dashboard and the panel
// alone, each with what it shows. Nothing is typed, saved, starred or changed.
export async function scout({ page, base, step, state }) {
  if (!state.scout) throw new Error("scout() runs only in scout mode");
  await step("chain", async () => ({ ...state.grafana, url: page.url().replace(/[?#].*/, "") }));
  await step("classes", async () => onGitHub(page, "classes"));
  await step("classes-shapes", async () => ({ url: page.url().replace(/[?#].*/, ""), header: await describe(page, "header", 30).catch(() => []),
                                              banners: await describe(page, "[role='dialog'], [role='banner'], .flash, .js-notice", 20).catch(() => []) }));
  await step("dashboard", async () => {
    const address = await grafanaDashboard(page, base, DASHBOARD.uid, { from: DASHBOARD.from, vars: DASHBOARD.vars });
    return { url: address, news: grafanaNewsSeen(page), title_on_screen: await page.getByText(DASHBOARD.title).first().isVisible().catch(() => false),
             words: await wordsOnScreen(page, [/Last 24 hours/, /One budget across the experiences/]) };
  });
  await step("panel", async () => ({ title: PANEL.title, ...(await panel(page, base)) }));
  await step("evidence", async () => onGitHub(page, "evidence"));
  await step("closed", async () => {
    const wrote = state.writes();
    if (wrote.length) throw new Error(`the scout sent ${wrote.join(", ")} to Grafana`);
    return { writes: 0, url: page.url().replace(/[#].*/, "") };
  });
}

export async function cleanup() {
  return null;
}
