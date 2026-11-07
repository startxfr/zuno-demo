// WP-243 / ADR-0606 clause 1: one browser check per experience. Signs in through Keycloak as a persona, waits for the
// screen the demonstration starts from, fails on a JavaScript page error, and saves a screenshot.
//
// Run through evaluations/browser/run.sh (podman, the Playwright image whose browsers match playwright@1.48.0).
// Environment: APPS_DOMAIN, PERSONA_PASSWORD, and optionally OPENCLAW_UI_PASSWORD, ONLY (comma list), OUT (screenshots).
import { chromium } from "playwright";
import fs from "node:fs";

const domain = process.env.APPS_DOMAIN;
const password = process.env.PERSONA_PASSWORD;
const out = process.env.OUT || "/out";
const only = (process.env.ONLY || "").split(",").filter(Boolean);
if (!domain || !password) {
  console.error("APPS_DOMAIN and PERSONA_PASSWORD are required");
  process.exit(2);
}

async function keycloak(page, username) {
  // Stock Keycloak theme: #username, #password, #kc-login.
  await page.waitForSelector("#username", { timeout: 30000 });
  await page.fill("#username", username);
  await page.fill("#password", password);
  await Promise.all([page.waitForLoadState("domcontentloaded"), page.click("#kc-login")]);
}

const checks = {
  "unifai": async (page) => {
    await page.goto(`https://unifai-ui-zuno-unifai.${domain}/`);
    await page.getByText("Login using SSO").click({ timeout: 30000 });
    await keycloak(page, "consultant-02");
    await page.waitForURL(new RegExp(`unifai-ui-zuno-unifai\\.${domain.replace(/\./g, "\\.")}`), { timeout: 60000 });
    await page.waitForLoadState("networkidle", { timeout: 60000 });
    const text = await page.locator("body").innerText();
    if (!text.trim()) throw new Error("UnifAI rendered an empty page");
    return `signed in as consultant-02, ${text.length} chars on screen`;
  },
  "open-webui": async (page) => {
    await page.goto(`https://open-webui.${domain}/oauth/oidc/login`);
    await keycloak(page, "sale-01");
    await page.waitForSelector("#chat-input, textarea", { timeout: 60000 });
    return "signed in as sale-01, the chat input is on screen";
  },
  "kagent": async (page) => {
    await page.goto(`https://kagent.${domain}/`);
    await keycloak(page, "ai-ops-01");
    await page.waitForLoadState("networkidle", { timeout: 60000 });
    // The first screen of a new browser is the onboarding wizard: skip it, as the script says (it would create an agent).
    const skip = page.getByText("Skip wizard");
    if (await skip.count()) await skip.first().click();
    await page.waitForLoadState("networkidle", { timeout: 60000 });
    const text = await page.locator("body").innerText();
    if (!/zuno-sre/i.test(text)) {
      await page.goto(`https://kagent.${domain}/agents`).catch(() => {});
      await page.waitForLoadState("networkidle", { timeout: 60000 });
    }
    const after = await page.locator("body").innerText();
    if (!/zuno-sre/i.test(after)) throw new Error("the agent zuno-sre is not listed");
    return "signed in as ai-ops-01, the agent zuno-sre is listed";
  },
  "dify": async (page) => {
    await page.goto(`https://dify.${domain}/`);
    await keycloak(page, "consultant-02");
    await page.waitForLoadState("networkidle", { timeout: 60000 });
    const text = await page.locator("body").innerText();
    if (!text.trim()) throw new Error("Dify rendered an empty page after the front door");
    return `through the front door as consultant-02, Dify answers (${page.url().replace(/\?.*/, "")})`;
  },
  "openclaw": async (page) => {
    await page.goto(`https://assistant-zuno-claw-sale-01.${domain}/`);
    await keycloak(page, "sale-01");
    await page.waitForLoadState("networkidle", { timeout: 60000 });
    if (!process.env.OPENCLAW_UI_PASSWORD) throw new Error("OPENCLAW_UI_PASSWORD is not set");
    // The Control UI asks for its password (Secret openclaw-ui), then opens its WebSocket to the gateway.
    await page.getByPlaceholder("optional").last().fill(process.env.OPENCLAW_UI_PASSWORD);
    await page.getByRole("button", { name: "Connect" }).click();
    await page.waitForTimeout(8000);
    const text = await page.locator("body").innerText();
    if (/Could not connect/i.test(text)) throw new Error("the Control UI could not connect to its gateway with the password");
    return `through the front door as sale-01, the Control UI connected to its gateway (${text.length} chars)`;
  },
};

const results = [];
const browser = await chromium.launch();
for (const [name, check] of Object.entries(checks)) {
  if (only.length && !only.includes(name)) continue;
  const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e).slice(0, 160)));
  const started = Date.now();
  try {
    const detail = await check(page);
    await page.screenshot({ path: `${out}/${name}.png` });
    results.push({ name, status: errors.length ? "fail" : "pass",
                   detail: errors.length ? `${detail}; page errors: ${errors.join(" | ")}` : detail,
                   seconds: (Date.now() - started) / 1000 });
  } catch (e) {
    await page.screenshot({ path: `${out}/${name}-failed.png` }).catch(() => {});
    results.push({ name, status: "fail", detail: String(e).split("\n")[0].slice(0, 200), seconds: (Date.now() - started) / 1000 });
  } finally {
    await context.close();
  }
}
await browser.close();
for (const r of results) console.log(`${r.status.toUpperCase().padEnd(5)} ${r.name.padEnd(11)} ${r.seconds.toFixed(1).padStart(6)}s  ${r.detail}`);
const failed = results.filter((r) => r.status === "fail").map((r) => r.name);
console.log(`RESULT: ${failed.length ? "FAIL (" + failed.join(", ") + ")" : "PASS"}`);
fs.writeFileSync(`${out}/results.json`, JSON.stringify(results, null, 2));
process.exit(failed.length ? 1 : 0);
