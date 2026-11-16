// WP-288 / ADR-0618: the walkthrough of "Evaluation: TrustyAI and EvalHub", 5-minute version, for
// evaluations/browser/record.mjs.
//
// The Grafana rows of docs/demo/scenarios/rhoai/evaluation-trustyai-evalhub.md, as ai-ops-01, on the dashboard
// "Zuno Platform / TrustyAI evaluation & guardrails" over the last 7 days (the page's Start section): the Keycloak
// form (login), the dashboard (dashboard), the panel "Garak / RAGAS job outcomes" (jobs, row 0:45), "RAGAS scores
// (real UnifAI retrievals)" (ragas, row 1:30), "Garak attack success rate (jailbreak probes)" (garak, row 2:30),
// then end. Rows 0:00 and 4:30 are words; row 3:30 shows two repository files in an editor and is not filmed.
//
// Read only. It types no prompt, calls no model, starts no evaluation and creates nothing: owned() is empty and
// cleanup() has nothing to delete. A panel that shows "No data" fails the take: the picture would say nothing (the
// scores are kept 30 days after a run; the last runs were on 2026-11-09). A request that would change something in
// Grafana (a save, a star, a preference) fails the take. The sign-in itself is the only trace: see _grafana.mjs.
//
// NOT yet scouted: the sign-in chain and the panel selectors are guesses (_grafana.mjs). scout() reports the chain,
// the dashboard's address, and for each panel whether it shows "No data" and the text it shows, so that the review
// can say no real person's name is in a picture (the RAGAS panel lists the evaluation's questions).
import { describe, wordsOnScreen } from "./_helpers.mjs";
import { grafana, grafanaDashboard, grafanaNewsSeen, grafanaPanel, grafanaSignIn, grafanaWrites } from "./_grafana.mjs";

export const persona = "ai-ops-01";
export const page = "docs/demo/scenarios/rhoai/evaluation-trustyai-evalhub.md";
export const viewport = { width: 1280, height: 800 };
export const markers = ["login", "dashboard", "jobs", "ragas", "garak", "end"];
// The sign-in chain (up to dashboard) is never shown as motion.
export const motion_from = "dashboard";
// The one declared change (the owner's decision of 2026-11-16): OpenShift's "Authorize Access" page for Grafana's proxy,
// approved for ai-ops-01 if it shows (the first time that persona comes through the proxy). Nothing else is changed.
// And Grafana's product announcement, closed by its cross (the owner's decision of 2026-11-16, 11:25).
export const changes = [grafana.AUTHORIZE_CHANGE, grafana.NEWS_CHANGE];
export const prompts = {};
export const url = grafana.url;
export const sends = grafana.writes;

const DASHBOARD = { uid: "zuno-trustyai", title: "TrustyAI evaluation & guardrails", from: "now-7d" };   // gitops/charts/grafana
const PANELS = [
  { marker: "jobs", row: "0:45", title: "Garak / RAGAS job outcomes" },
  { marker: "ragas", row: "1:30", title: "RAGAS scores (real UnifAI retrievals)" },
  { marker: "garak", row: "2:30", title: "Garak attack success rate (jailbreak probes)" },
];

export async function enter(ctx) {
  ctx.state.writes = grafanaWrites(ctx.page);
  await grafanaSignIn(ctx, persona, { changes });
}

// Nothing is created, so nothing is owned: the before/after comparison is of two empty lists.
export async function owned() {
  return [];
}

export async function run({ page, base, mark, log, state }) {
  await grafanaDashboard(page, base, DASHBOARD.uid, { from: DASHBOARD.from });
  await page.getByText(DASHBOARD.title).first().waitFor({ timeout: 30000 });
  await mark("dashboard");
  for (const panel of PANELS) {
    const shown = await grafanaPanel(page, panel.title);
    if (shown.no_data) throw new Error(`the panel "${panel.title}" (row ${panel.row}) shows "No data": nothing to film; the scores are kept 30 days after a run`);
    log(`panel "${panel.title}": ${shown.lines.length} lines of text, selector ${shown.selector}`);
    await page.waitForTimeout(800);
    await mark(panel.marker);
  }
  await page.waitForTimeout(800);
  await mark("end");
  const wrote = state.writes();
  if (wrote.length) throw new Error(`the take sent ${wrote.join(", ")} to Grafana: it must change nothing there`);
}

// What a take will meet, for the price of a sign-in: the chain to Grafana, the dashboard, and each panel with what
// it shows. Nothing is saved, starred or changed; the scout fails if a request that would do so was sent.
export async function scout({ page, base, step, state }) {
  if (!state.scout) throw new Error("scout() runs only in scout mode");
  await step("chain", async () => ({ ...state.grafana, url: page.url().replace(/[?#].*/, ""),
                                     words: await wordsOnScreen(page, [/ai-ops-01/, /Zuno Platform/, /Welcome to Grafana/]) }));
  await step("dashboard", async () => {
    const address = await grafanaDashboard(page, base, DASHBOARD.uid, { from: DASHBOARD.from });
    return { url: address, news: grafanaNewsSeen(page), dialog_on_screen: await page.locator("[role='dialog']").first().isVisible().catch(() => false), title_on_screen: await page.getByText(DASHBOARD.title).first().isVisible().catch(() => false),
             words: await wordsOnScreen(page, [/Last 7 days/, /Guardrails \(observe-only\)/, /Evaluation jobs/, /Scores \(latest run\)/]),
             controls: (await describe(page, "body", 40)).filter((el) => el.attrs["aria-label"] || el.text).slice(0, 40) };
  });
  for (const panel of PANELS) {
    await step(`panel-${panel.marker}`, async () => ({ row: panel.row, title: panel.title, ...(await grafanaPanel(page, panel.title)) }));
  }
  await step("closed", async () => {
    const wrote = state.writes();
    if (wrote.length) throw new Error(`the scout sent ${wrote.join(", ")} to Grafana`);
    return { writes: 0, url: page.url().replace(/[#].*/, "") };
  });
}

export async function cleanup() {
  return null;
}
