// ADR-0628 / WP-331: the browser part of "Vault and PKI", 5-minute version, for evaluations/browser/record.mjs.
//
// The UI rows of docs/demo/scenarios/foundation/vault-pki.md, in Vault's own web UI on the chart's Route
// (vault.<apps domain>), signed in with the read-only token of platform/vault/demo_token.sh (role demo-reader,
// 30 minutes): the token form with the token masked (login, row 0:45), the KV engine zuno/ with secret names only
// (secrets, row 0:45), the Kubernetes auth roles (access, row 1:45), the policy of zuno-ai-run (policy, row 2:45), the
// Transit keys (transit, row 3:30) and the PKI roles (pki, row 3:30), then end. Row 0:00 is the terminal (the GIF's
// terminal still, an assembled take: ansible/demos/vault-pki/gif.yml); row 4:15 is words.
//
// The token is the secret VAULT_DEMO_TOKEN, minted just before the take:
//   VAULT_DEMO_TOKEN="$(platform/vault/demo_token.sh --print)" bash evaluations/browser/record.sh vault-pki <dir>
// typed by the recorder into the masked token field (ctx.typeSecret), struck out of every log line and file. The
// persona is required by the recorder; Vault never sees it.
//
// Read only. The token's policy cannot read a secret value or write anything (vault-demo-reader.hcl); the write guard
// adds a second fence: every request to Vault that is not a read is refused, except the UI's capability check
// (POST sys/capabilities-self, a read of what the token may do). The take never opens a secret: it shows the list
// of names. owned() is empty and cleanup() has nothing to delete.
//
// Scouted on demo333 on 2026-11-23 (13:13Z): sign-in and the five pages OK, no "permission denied", the only write
// the UI's capability check. scout() reports, for each page, its address, whether it shows "permission denied" and
// whether the expected words are on screen, so that a missing policy path is found before the take.
import { wordsOnScreen } from "./_helpers.mjs";

export const persona = "paas-ops-01";
export const secrets = ["VAULT_DEMO_TOKEN"];
export const page = "docs/demo/scenarios/foundation/vault-pki.md";
export const viewport = { width: 1280, height: 800 };
export const markers = ["login", "secrets", "access", "policy", "transit", "pki", "end"];
// The token form is a still; motion starts once signed in.
export const motion_from = "secrets";
export const changes = [];
export const prompts = {};
export const url = (domain) => `https://vault.${domain}/ui/`;
export const allows = [{ method: "POST", path: /^\/v1\/sys\/capabilities-self$/, what: "the UI's capability check (a read)" }];
// No chat in this application: nothing for a scout's message filter to stop.
export const sends = /^$/;

const DENIED = /permission denied|not authorized|403/i;
const PAGES = [
  { marker: "secrets", row: "0:45", path: "vault/secrets/zuno/kv/list", shows: [/zuno/] },
  { marker: "access", row: "1:45", path: "vault/access/kubernetes/item/role", shows: [/ns-zuno-ai-run/, /demo-reader/] },
  { marker: "policy", row: "2:45", path: "vault/policy/acl/ns-zuno-ai-run", shows: [/zuno\/data\//] },
  { marker: "transit", row: "3:30", path: "vault/secrets/transit/list", shows: [/agent-chain/, /mcp-call-assertion/] },
  { marker: "pki", row: "3:30", path: "vault/secrets/pki/pki/roles", shows: [/istio/, /cert-manager/] },
];

async function open(page, base, entry) {
  await page.goto(`${base}${entry.path}`, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
  const text = await page.locator("body").innerText().catch(() => "");
  return { url: page.url().replace(/[?#].*/, ""), denied: DENIED.test(text), missing: entry.shows.filter((re) => !re.test(text)).map(String) };
}

async function signIn(ctx) {
  const { page, base } = ctx;
  await page.goto(`${base}vault/auth?with=token`, { waitUntil: "domcontentloaded" });
  const field = page.locator("input[name='token'], [data-test-token]").first();
  await field.waitFor({ timeout: 30000 });
  await ctx.typeSecret(field, "VAULT_DEMO_TOKEN");
  return page.locator("[data-test-auth-submit], button[type='submit']").first();
}

export async function enter(ctx) {
  ctx.state.submit = await signIn(ctx);
}

// Nothing is created, so nothing is owned: the before/after comparison is of two empty lists.
export async function owned() {
  return [];
}

export async function run({ page, base, mark, log, state }) {
  await page.waitForTimeout(800);
  await mark("login");
  await state.submit.click();
  await page.waitForURL(/\/ui\/vault\/(dashboard|secrets)/, { timeout: 30000 });
  for (const entry of PAGES) {
    const shown = await open(page, base, entry);
    if (shown.denied) throw new Error(`row ${entry.row}: ${entry.path} says permission denied: the demo-reader policy lacks a path`);
    if (shown.missing.length) throw new Error(`row ${entry.row}: ${entry.path} does not show ${shown.missing.join(", ")}`);
    log(`row ${entry.row}: ${shown.url}`);
    await page.waitForTimeout(1200);
    await mark(entry.marker);
  }
  await page.waitForTimeout(800);
  await mark("end");
}

// What a take will meet, for the price of a sign-in: each page of the tour, whether the token may see it, and the words
// it shows. Nothing is opened beyond the lists and the one policy.
export async function scout(ctx) {
  const { page, base, step, state } = ctx;
  if (!state.scout) throw new Error("scout() runs only in scout mode");
  await step("signed-in", async () => {
    await state.submit.click();
    await page.waitForURL((address) => /\/ui\/vault\//.test(address.pathname) && !/\/auth$/.test(address.pathname), { timeout: 30000 });
    return { url: page.url().replace(/[?#].*/, ""), words: await wordsOnScreen(page, [/Secrets Engines/, /zuno/, /transit/, /pki/]) };
  });
  for (const entry of PAGES) {
    await step(`page-${entry.marker}`, async () => ({ row: entry.row, ...(await open(page, base, entry)) }));
  }
}

export async function cleanup() {
  return null;
}
