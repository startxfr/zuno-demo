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
// a user comes through this proxy, OpenShift's "Authorize Access" page. The chain up to that page was seen live on
// 2026-11-16 (the scouts of evaluation-trustyai-evalhub and ai-gateway-routing stopped on it); Grafana's own
// selectors are still guesses, marked `guess`; scout() of the walkthrough reports the chain as it really is.
//
// What a sign-in may create, none of it by a click of the take: the OpenShift User and its group memberships (the
// first sign-in of that persona to OpenShift), the Grafana user (auto_sign_up, the first time).
// "Authorize Access": approving it stores one OAuth authorization for the persona on the cluster. The owner's decision
// of 2026-11-16: a scout or a take may approve it for ai-ops-01, as a DECLARED change. So it is approved only when the
// walkthrough lists `grafana.AUTHORIZE_CHANGE` in its `changes`, the persona is ai-ops-01, and the page is exactly the
// one seen live: the service account grafana-oauth-proxy of zuno-monitoring, for that persona, asking for user:info
// and user:check-access and nothing more. Anything else (another client, another scope, another persona, the change
// not declared) stops the take there, as before. What a take NEVER does: save a dashboard or a time range, star,
// change a preference. The time range is given in the address only.
import { click, firstVisible, read, waitUntil } from "./_helpers.mjs";

export const grafana = {
  url: (domain) => `https://grafana-route-zuno-monitoring.${domain}`,
  PROXY_BUTTON: ["button:has-text('Log in with OpenShift')", "form[action*='/oauth/start'] button", "a[href*='/oauth/start']"],   // guess (oauth-proxy)
  PROVIDER: "openshift",   // the Keycloak provider of the cluster; never startx-htpasswd_auth
  AUTHORIZE: /Authorize Access/i,                                                                                             // seen live 2026-11-16
  // The declared change a walkthrough lists in `changes` to let the sign-in approve that page (the owner's decision).
  AUTHORIZE_CHANGE: "approves OpenShift's Authorize Access page for Grafana's proxy as ai-ops-01 (user:info and user:check-access), which stores one OAuth authorization for ai-ops-01 on the cluster",
  // The second declared change (the owner's decision of 2026-11-16, 11:25): Grafana's product announcement is closed by
  // its cross, which may store a per-user "seen" flag. Declared by the walkthroughs; grafanaNews() still refuses any
  // other write to Grafana while it closes. The scout of 2026-11-16 showed the one request of the close: a POST to
  // Grafana's user storage (NEWS_WRITE); the owner then confirmed it. It is let through only when the walkthrough
  // declares the change; its body is reported by its size and the names of its keys, never its values.
  NEWS_CHANGE: "closes Grafana's product announcement by its cross, which stores in Grafana's user storage of ai-ops-01 that the notice was seen",
  NEWS_WRITE: { method: "POST", path: /^\/apis\/userstorage\.grafana\.app\/[^/]+\/namespaces\/[^/]+\/user-storage\/?$/ },
  AUTHORIZE_PERSONA: "ai-ops-01",
  AUTHORIZE_CLIENT: ["grafana-oauth-proxy", "zuno-monitoring"],
  AUTHORIZE_SCOPES: ["user:info", "user:check-access"],
  ALLOW: ["input[name='approve']", "input[type='submit'][value='Allow selected permissions']", "button:has-text('Allow selected permissions')"],   // guess
  READY: ["[data-testid*='Panel header']", "[data-testid='data-testid dashboard controls']", ".react-grid-layout", "main"],   // guess (Grafana 10+)
  LOADING: "[aria-label='Panel loading bar']",                                                                                // guess
  // The requests that would CHANGE something in Grafana. Its queries are POSTs too (/api/ds/query) and are reads:
  // they are not here. A scout refuses these (the walkthrough's `sends`); a take fails if one was sent.
  writes: /\/api\/(dashboards\/(db|uid|import)|user\/(stars|preferences|password|using)|org\/preferences|preferences|annotations|snapshots|folders|playlists|short-urls|alert|ruler|v1\/provisioning)|\/apis\/[^?]*\/(dashboards|folders|preferences)/,
};

// Grafana's own announcement ("NEW  Grafana Assistant is now available to OSS users", 1/4, seen live on 2026-11-16
// over the home page AND over the dashboard): a take would film it over the panels. It is closed by its own close
// button (or Escape), and the close is MEASURED the way the other first-screen notices are: while it is closed, every
// request to Grafana that is not a GET and not a query (and not the one declared write, grafana.NEWS_WRITE) is
// refused before it leaves the browser and kept by its path,
// and the browser-storage keys it adds are kept by name. A close that only writes to the browser is fine (nothing on
// the server, nothing of the persona's settings). A close that wants to write to Grafana stops the take: nothing was
// written, and whether a take may save that for the persona is the owner's decision. Any OTHER dialog stops the take.
const seenNews = new WeakMap();   // page -> {shown, closed_by, refused: [], storage_added: []}
export const grafanaNewsSeen = (page) => seenNews.get(page) || { shown: 0, closed_by: "", refused: [], allowed: [], storage_added: [], declared: false };
const NEWS = { DIALOG: "[role='dialog']", IS: /Grafana Assistant|is now available to|What's new in Grafana/i, // seen live: "NEW", "Grafana Assistant is now available to OSS users"
               CLOSE: ["[role='dialog'] button[aria-label='Close']", "[role='dialog'] button[aria-label*='close' i]", "[role='dialog'] button[data-testid*='close' i]"] };   // guess
const QUIET = /\/api\/(ds\/query|frontend-metrics|live\/)|\/log-grafana-javascript-agent|\/api\/frontend\/assets/;   // reads and telemetry: let through, not state

export async function grafanaNews(page, { watchMs = 3000 } = {}) {
  const seen = grafanaNewsSeen(page);
  seenNews.set(page, seen);
  const origin = new URL(page.url()).origin;
  const deadline = Date.now() + watchMs;   // the announcement comes a moment after the page
  while (Date.now() < deadline) {
    const dialog = page.locator(NEWS.DIALOG).first();
    if (!(await dialog.isVisible().catch(() => false))) { await page.waitForTimeout(300); continue; }
    const text = (await dialog.innerText().catch(() => "")).replace(/\s+/g, " ").trim();
    if (!NEWS.IS.test(text)) throw new Error(`a dialog covers Grafana and it is not its product announcement ("${text.slice(0, 80)}"): the take stops, it dismisses nothing it does not know`);
    seen.shown += 1;
    const refused = [];
    const guard = (route) => {
      const r = route.request();
      const path = new URL(r.url()).pathname;
      if (r.method() === "GET" || QUIET.test(path)) return route.continue();
      if (seen.declared && r.method() === grafana.NEWS_WRITE.method && grafana.NEWS_WRITE.path.test(path)) {
        let body = null;
        try { body = r.postDataJSON(); } catch { /* not JSON */ }
        const keys = body && typeof body === "object" ? Object.keys(body).flatMap((k) => [k, ...(body[k] && typeof body[k] === "object" && !Array.isArray(body[k]) ? Object.keys(body[k]).map((inner) => `${k}.${inner}`) : [])]) : [];
        seen.allowed.push({ request: `${r.method()} ${path}`, bytes: (r.postData() || "").length, keys: keys.filter((k) => !/^metadata\./.test(k)).slice(0, 20) });
        return route.continue();
      }
      refused.push(`${r.method()} ${new URL(r.url()).pathname}`);
      return route.abort();
    };
    const keys = () => read(page, () => [...Object.keys(localStorage).map((k) => "local:" + k), ...Object.keys(sessionStorage).map((k) => "session:" + k)]);
    const before = await keys();
    await page.route(`${origin}/**`, guard);
    try {
      const close = await firstVisible(page, NEWS.CLOSE);
      if (close) { await click(close); seen.closed_by = close.matched; } else { await page.keyboard.press("Escape"); seen.closed_by = "Escape"; }
      await dialog.waitFor({ state: "hidden", timeout: 10000 }).catch(() => {});
      await page.waitForTimeout(1200);   // what the close sends, it sends now
    } finally {
      await page.unroute(`${origin}/**`, guard);
    }
    seen.storage_added = [...new Set([...seen.storage_added, ...(await keys()).filter((k) => !before.includes(k))])];
    seen.refused.push(...refused);
    if (refused.length) {
      throw new Error(`closing Grafana's announcement wanted to send ${refused.join(", ")} to Grafana: refused before it left the browser, nothing was written; `
        + "whether a take may save that for the persona is the owner's decision");
    }
    if (await dialog.isVisible().catch(() => false)) throw new Error(`Grafana's announcement is still on screen after ${seen.closed_by}`);
    return seen;
  }
  return seen;
}

const provider = (name) => [`a[title='Log in with ${name}']`, `a.idp:text-is('${name}')`, `a:text-is('${name}')`];   // guess (OpenShift login page)

// Sign in to Grafana through its proxy, OpenShift's chooser and Keycloak. The `login` marker is the EMPTY Keycloak
// form. Returns the chain as it was met, for the scout: [{step, url (no query), matched}]. state.grafana keeps it.
// The sign-in of any application behind an OpenShift oauth-proxy (Grafana, the Tempo search UI): see the header.
// `authorize` ({change, persona, client: [names on the page]}) lets it approve OpenShift's "Authorize Access" page;
// without it, or when the page is not exactly that one, the take stops there.
export async function proxySignIn({ page, base, mark, keycloak, state }, persona, { changes = [], what = "Grafana", ready = grafana.READY, authorize = null } = {}) {
  const chain = [];
  state.grafana = { chain, authorize_shown: false, authorized: false };
  const here = () => page.url().replace(/[?#].*/, "");
  await page.goto(`${base}/`, { timeout: 90000 }).catch(() => page.goto(`${base}/`, { timeout: 90000 }));   // a slow first load: once more
  const wanted = [...grafana.PROXY_BUTTON, ...provider(grafana.PROVIDER), "#username"];
  for (let hop = 0; hop < 4; hop += 1) {
    const found = await waitUntil(page, { what: `the sign-in chain of ${what}`, timeoutMs: 60000, done: async () => (await firstVisible(page, wanted)) || undefined });
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
  // Back on Grafana, or on OpenShift's "Authorize Access" page: approved only as the declared change, see above.
  const land = () => waitUntil(page, { what: `${what} after the sign-in`, timeoutMs: 90000, done: async () => {
    if (await page.getByText(grafana.AUTHORIZE).first().isVisible().catch(() => false)) return "authorize";
    if (page.url().startsWith(base) && !/\/oauth\//.test(page.url()) && await firstVisible(page, ready)) return what === "Grafana" ? "grafana" : "application";
    return undefined;
  } });
  let landed = await land();
  chain.push({ step: landed, url: here(), matched: "" });
  if (landed === "authorize") {
    state.grafana.authorize_shown = true;
    const stop = (why) => new Error(`OpenShift asks ${persona} to authorize ${what}'s proxy ("Authorize Access") and the take stops there: ${why}; `
      + `approving it stores an authorization for ${persona} on the cluster, the owner's to approve by hand, signed in as that persona`);
    if (!authorize || !changes.includes(authorize.change)) throw stop("the walkthrough does not declare that change");
    if (persona !== authorize.persona) throw stop(`the owner's decision covers ${authorize.persona} only`);
    // The page must be the one the owner decided on: the same client, the same persona, the same two scopes.
    const asked = await read(page, () => ({
      text: document.body.innerText,
      scopes: [...document.querySelectorAll("input[type='checkbox']")].map((box) => ({ name: box.value || box.name || "", checked: box.checked })),
    }));
    const absent = [...authorize.client, `(${persona})`, ...grafana.AUTHORIZE_SCOPES].filter((word) => !asked.text.includes(word));
    if (absent.length) throw stop(`the page is not the one the owner approved (not on it: ${absent.join(", ")})`);
    const words = asked.text.match(/\b[a-z]+:[a-z][a-z-]*\b/g) || [];
    const more = [...new Set(words)].filter((word) => /^(user|role):/.test(word) && !grafana.AUTHORIZE_SCOPES.includes(word));
    if (more.length || asked.scopes.length !== grafana.AUTHORIZE_SCOPES.length) {
      throw stop(`it asks for more than ${grafana.AUTHORIZE_SCOPES.join(" and ")} (${more.join(", ") || asked.scopes.length + " permissions listed"})`);
    }
    const allow = await firstVisible(page, grafana.ALLOW);
    if (!allow) throw stop(`its button was not found (${grafana.ALLOW.join(" | ")})`);
    await click(allow, { changes });   // the page's permissions are left as shown: no checkbox is touched
    state.grafana.authorized = true;
    await page.waitForLoadState("domcontentloaded", { timeout: 30000 }).catch(() => {});
    await page.waitForTimeout(500);
    landed = await land();
    chain.push({ step: landed === "authorize" ? "authorize-again" : landed, url: here(), matched: allow.matched });
    if (landed === "authorize") throw stop("the page came back after it was approved once");
  }
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
  return chain;
}

// Grafana's own sign-in: the chain above with Grafana's declared Authorize Access page, then its announcement.
export async function grafanaSignIn(ctx, persona, { changes = [] } = {}) {
  const chain = await proxySignIn(ctx, persona, { changes, what: "Grafana", ready: grafana.READY,
    authorize: { change: grafana.AUTHORIZE_CHANGE, persona: grafana.AUTHORIZE_PERSONA, client: grafana.AUTHORIZE_CLIENT } });
  // Whether the walkthrough declared the close of the announcement decides whether its one write is let through.
  seenNews.set(ctx.page, { ...grafanaNewsSeen(ctx.page), declared: changes.includes(grafana.NEWS_CHANGE) });
  ctx.state.grafana.news = await grafanaNews(ctx.page);
  return chain;
}

// Open a dashboard by its uid, the time range and its variables in the address only (nothing is saved): the address
// reached.
export async function grafanaDashboard(page, base, uid, { from = "now-6h", to = "now", vars = {} } = {}) {
  const chosen = Object.entries(vars).map(([name, value]) => `&var-${encodeURIComponent(name)}=${encodeURIComponent(value)}`).join("");
  await page.goto(`${base}/d/${uid}/?orgId=1&from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}${chosen}`);
  await waitUntil(page, { what: `the dashboard ${uid}`, timeoutMs: 60000, done: async () => (await firstVisible(page, grafana.READY.slice(0, 3))) || undefined });
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
  await grafanaNews(page, { watchMs: 2500 });   // the announcement comes back on every page until it is closed
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
  // A panel behind a dialog is not a picture of the panel (the take of 2026-11-16 passed with the announcement over it).
  if (await page.locator(NEWS.DIALOG).first().isVisible().catch(() => false)) throw new Error(`a dialog covers the dashboard while the panel "${title}" is read: nothing to film`);
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  return { selector: panel ? panel.matched : `text=${title}`, whole_panel: Boolean(panel), no_data: lines.some((l) => /^No data$/i.test(l)),
           lines: lines.slice(0, 40).map((l) => l.slice(0, 120)) };
}

// Is this text drawn INSIDE the window, whole? Some element holding exactly it must have its box in the window, not be
// cut by its own cell (an ellipsis) and be the thing on top at its centre. A panel's text is on the page long before
// it is in the picture: the takes of 2026-11-16 passed with their key column cut off on the right.
export async function grafanaInWindow(page, text) {
  const hits = page.getByText(text, { exact: true });
  const view = page.viewportSize();
  const count = Math.min(await hits.count(), 30);
  for (let i = 0; i < count; i += 1) {
    const hit = hits.nth(i);
    const box = await hit.boundingBox().catch(() => null);
    if (!box || box.width < 1 || box.height < 1 || box.x < 0 || box.y < 0 || box.x + box.width > view.width || box.y + box.height > view.height) continue;
    const whole = await read(hit, (el) => {
      if (el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).overflowX !== "visible") return false;
      const r = el.getBoundingClientRect();
      const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return Boolean(top) && (top === el || el.contains(top) || top.contains(el));
    }).catch(() => false);
    if (whole) return true;
  }
  return false;
}

// Open ONE panel of a dashboard over the whole page (Grafana's "view panel" mode, by the address only: nothing is
// saved), so a table has the page's width, and read it as grafanaPanel() does. `shows`: the texts that must be drawn
// inside the window (column headers, the proof); the panel is refused when one is not, or when "No data" shows.
// Grafana names the panel `panel-<id>` in the address since its "scenes" dashboards and `<id>` before: both are
// tried, and the mode is proved by the page itself (one panel header on screen, at least 60% of the window wide).
export async function grafanaViewPanel(page, base, uid, id, title, { from = "now-6h", to = "now", vars = {}, shows = [] } = {}) {
  const chosen = Object.entries(vars).map(([name, value]) => `&var-${encodeURIComponent(name)}=${encodeURIComponent(value)}`).join("");
  const tried = [];
  for (const name of [`panel-${id}`, `${id}`]) {
    await page.goto(`${base}/d/${uid}/?orgId=1&from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}${chosen}&viewPanel=${name}`);
    await waitUntil(page, { what: `the panel ${name} of ${uid}`, timeoutMs: 60000, done: async () => (await firstVisible(page, grafana.READY.slice(0, 3))) || undefined });
    await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
    await grafanaNews(page, { watchMs: 1500 });
    await page.mouse.move(150, 700);   // away from the panel: no tooltip over it
    const headers = page.locator("[data-testid*='Panel header']");
    const deadline = Date.now() + 8000;
    let alone = false;
    while (Date.now() < deadline && !alone) {
      const visible = [];
      for (let i = 0; i < Math.min(await headers.count(), 40); i += 1) if (await headers.nth(i).isVisible().catch(() => false)) visible.push(headers.nth(i));
      const box = visible.length === 1 ? await visible[0].boundingBox().catch(() => null) : null;
      alone = Boolean(box) && box.width >= 0.6 * page.viewportSize().width && (await visible[0].innerText().catch(() => "")).includes(title);
      if (!alone) await page.waitForTimeout(400);
    }
    tried.push(`viewPanel=${name}: ${alone ? "one wide panel" : "not alone or not wide"}`);
    if (!alone) continue;
    const shown = await grafanaPanel(page, title);
    await page.mouse.move(150, 700);
    await page.waitForTimeout(500);
    const absent = [];
    for (const text of shows) if (!(await grafanaInWindow(page, text))) absent.push(text);
    return { ...shown, view: `viewPanel=${name}`, not_in_window: absent, url: page.url().replace(/[#].*/, "") };
  }
  throw new Error(`the panel "${title}" (id ${id}) did not open alone over the page (${tried.join("; ")})`);
}

// Watch for a request that would change something in Grafana: returns a function giving the list so far.
export function grafanaWrites(page) {
  const seen = [];
  page.on("request", (r) => {
    if (!["GET", "HEAD", "OPTIONS"].includes(r.method()) && grafana.writes.test(new URL(r.url()).pathname)) seen.push(`${r.method()} ${new URL(r.url()).pathname}`);
  });
  return () => [...new Set(seen)];   // each request once: a dashboard is loaded several times
}
