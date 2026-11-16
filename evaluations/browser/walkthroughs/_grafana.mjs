// WP-288 / ADR-0618: what the walkthroughs that show a Grafana panel share (evaluation-trustyai-evalhub first; quotas,
// ai-gateway-routing, observability-trace and guardrails' row 2:00 sit behind the same sign-in). Imported ONLY by
// those walkthroughs. It is deliberately not in _helpers.mjs: the walkthrough hash covers _helpers.mjs and the
// walkthrough's own file, so adding this there would have made every scout of the night stale. The price: a change
// HERE does not change a walkthrough's hash, so after editing this file, scout again by hand.
//
// Grafana on Zuno (gitops/charts/grafana, read 2026-11-16) sits behind an OpenShift oauth-proxy sidecar
// (--provider=openshift, a SubjectAccessReview on pods of zuno-monitoring) and trusts its X-Forwarded-User header
// (auth.proxy, auto_sign_up, no login form of its own). So the sign-in chain is: the proxy's own page with one
// button, OpenShift's provider chooser (`openshift` is the Keycloak provider), the Keycloak form, and, the first time
// a user comes through this proxy, OpenShift's "Authorize Access" page. NOT yet seen live: every selector below is a
// guess, marked `guess`; scout() of the walkthrough reports the chain as it really is.
//
// What a sign-in may create, none of it by a click of the take: the OpenShift User and its group memberships (the
// first sign-in of that persona to OpenShift), the Grafana user (auto_sign_up, the first time). What a take NEVER
// does: approve "Authorize Access" (it would store an OAuth authorization for the persona on the cluster: the take
// stops there and says so), save a dashboard or a time range, star, change a preference. The time range is given in
// the address only.
import { click, firstVisible, read, waitUntil } from "./_helpers.mjs";

export const grafana = {
  url: (domain) => `https://grafana-route-zuno-monitoring.${domain}`,
  PROXY_BUTTON: ["button:has-text('Log in with OpenShift')", "form[action*='/oauth/start'] button", "a[href*='/oauth/start']"],   // guess (oauth-proxy)
  PROVIDER: "openshift",   // the Keycloak provider of the cluster; never startx-htpasswd_auth
  AUTHORIZE: /Authorize Access/i,                                                                                             // guess (OpenShift)
  READY: ["[data-testid*='Panel header']", "[data-testid='data-testid dashboard controls']", ".react-grid-layout", "main"],   // guess (Grafana 10+)
  LOADING: "[aria-label='Panel loading bar']",                                                                                // guess
  // The requests that would CHANGE something in Grafana. Its queries are POSTs too (/api/ds/query) and are reads:
  // they are not here. A scout refuses these (the walkthrough's `sends`); a take fails if one was sent.
  writes: /\/api\/(dashboards\/(db|uid|import)|user\/(stars|preferences|password|using)|org\/preferences|preferences|annotations|snapshots|folders|playlists|short-urls|alert|ruler|v1\/provisioning)|\/apis\/[^?]*\/(dashboards|folders|preferences)/,
};

const provider = (name) => [`a[title='Log in with ${name}']`, `a.idp:text-is('${name}')`, `a:text-is('${name}')`];   // guess (OpenShift login page)

// Sign in to Grafana through its proxy, OpenShift's chooser and Keycloak. The `login` marker is the EMPTY Keycloak
// form. Returns the chain as it was met, for the scout: [{step, url (no query), matched}]. state.grafana keeps it.
export async function grafanaSignIn({ page, base, mark, keycloak, state }, persona, { changes = [] } = {}) {
  const chain = [];
  state.grafana = { chain, authorize_shown: false };
  const here = () => page.url().replace(/[?#].*/, "");
  await page.goto(`${base}/`);
  const wanted = [...grafana.PROXY_BUTTON, ...provider(grafana.PROVIDER), "#username"];
  for (let hop = 0; hop < 4; hop += 1) {
    const found = await waitUntil(page, { what: "Grafana's sign-in chain", timeoutMs: 60000, done: async () => (await firstVisible(page, wanted)) || undefined });
    if (found.matched === "#username") break;
    chain.push({ step: grafana.PROXY_BUTTON.includes(found.matched) ? "proxy" : "chooser", url: here(), matched: found.matched });
    await click(found, { changes });
    await page.waitForLoadState("domcontentloaded", { timeout: 30000 }).catch(() => {});
    await page.waitForTimeout(500);
  }
  await page.waitForSelector("#username", { timeout: 30000 });
  chain.push({ step: "keycloak", url: here(), matched: "#username" });
  await mark("login");   // nothing is marked once the password is typed
  await keycloak(persona);
  // Back on Grafana, or stopped on OpenShift's "Authorize Access" page: never approved by a take or a scout.
  const landed = await waitUntil(page, { what: "Grafana after the sign-in", timeoutMs: 90000, done: async () => {
    if (await page.getByText(grafana.AUTHORIZE).first().isVisible().catch(() => false)) return "authorize";
    if (page.url().startsWith(base) && !/\/oauth\//.test(page.url()) && await firstVisible(page, grafana.READY)) return "grafana";
    return undefined;
  } });
  chain.push({ step: landed, url: here(), matched: "" });
  if (landed === "authorize") {
    state.grafana.authorize_shown = true;
    throw new Error(`OpenShift asks ${persona} to authorize Grafana's proxy ("Authorize Access"): approving it stores an authorization for ${persona} `
      + "on the cluster, which a take or a scout never does; it is the owner's to approve once by hand, signed in as that persona");
  }
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
  return chain;
}

// Open a dashboard by its uid, the time range and its variables in the address only (nothing is saved): the address
// reached.
export async function grafanaDashboard(page, base, uid, { from = "now-6h", to = "now", vars = {} } = {}) {
  const chosen = Object.entries(vars).map(([name, value]) => `&var-${encodeURIComponent(name)}=${encodeURIComponent(value)}`).join("");
  await page.goto(`${base}/d/${uid}/?orgId=1&from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}${chosen}`);
  await waitUntil(page, { what: `the dashboard ${uid}`, timeoutMs: 60000, done: async () => (await firstVisible(page, grafana.READY.slice(0, 3))) || undefined });
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(1000);
  return page.url().replace(/[#].*/, "");
}

const panelSelectors = (title) => [`[data-testid='data-testid Panel header ${title}']`, `section:has(h2:text-is("${title}"))`,
                                   `[aria-label="${title} panel"]`, `div:has(> header h2:text-is("${title}"))`];   // guess (Grafana 10+)

// Bring a panel to the middle of the screen (Grafana draws a panel only once it is near the screen: the page is
// wheeled down until its title shows), wait until its queries have settled, and read it: {selector, no_data, lines}.
// `lines` is the panel's text as shown, at most 40 lines of 120 characters, for the review of what a picture holds.
export async function grafanaPanel(page, title, { timeoutMs = 60000 } = {}) {
  let panel = null;
  for (let wheel = 0; wheel < 30 && !panel; wheel += 1) {
    panel = await firstVisible(page, panelSelectors(title));
    if (!panel) {
      const heading = page.getByText(title, { exact: true }).first();
      if (await heading.isVisible().catch(() => false)) break;
      await page.mouse.move(640, 500);
      await page.mouse.wheel(0, 400);
      await page.waitForTimeout(400);
    }
  }
  const target = panel || page.getByText(title, { exact: true }).first();
  if (!(await target.isVisible().catch(() => false))) throw new Error(`the panel "${title}" was not found on the dashboard (${panelSelectors(title)[0]}, or its title as text)`);
  await read(target, (el) => el.scrollIntoView({ block: "center" }));   // a scroll of the view: nothing is changed
  const box = panel ? page.locator(panel.matched).first() : null;
  let last = null;
  let stableSince = Date.now();
  const text = await waitUntil(page, { what: `the queries of "${title}"`, timeoutMs, everyMs: 300, done: async () => {
    const now = box ? await box.innerText().catch(() => "") : await page.locator("body").innerText();
    const loading = box ? await box.locator(grafana.LOADING).first().isVisible().catch(() => false) : await page.locator(grafana.LOADING).first().isVisible().catch(() => false);
    if (now !== last || loading) { last = now; stableSince = Date.now(); return undefined; }
    return Date.now() - stableSince >= 2000 ? now : undefined;
  } });
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  return { selector: panel ? panel.matched : `text=${title}`, whole_panel: Boolean(panel), no_data: lines.some((l) => /^No data$/i.test(l)),
           lines: lines.slice(0, 40).map((l) => l.slice(0, 120)) };
}

// Watch for a request that would change something in Grafana: returns a function giving the list so far.
export function grafanaWrites(page) {
  const seen = [];
  page.on("request", (r) => {
    if (!["GET", "HEAD", "OPTIONS"].includes(r.method()) && grafana.writes.test(new URL(r.url()).pathname)) seen.push(`${r.method()} ${new URL(r.url()).pathname}`);
  });
  return () => [...seen];
}
