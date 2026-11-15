// WP-286 / ADR-0617: what the walkthroughs of evaluations/browser/record.mjs share. Recorder side only: run.mjs
// (WP-243, the browser check) never imports this file.
//
// Rules every walkthrough follows:
// - Selectors are candidate lists, the first one being what the application showed live, with the date it was seen;
//   scout() reports which candidate matched, so a UI upgrade fails in a scout and not in a take.
// - "On screen" is decided by geometry and a hit test, not by Playwright's `visible`: an application may keep a
//   closed panel in the page, slid away or covered.
// - A take reads the persona's settings and never changes them: no switch, no checkbox, no settings form is clicked.
// - Whatever a take creates, it deletes by id, and says so.

// The first of these selectors that is on screen, or null; the locator carries the selector that matched.
export async function firstVisible(page, selectors) {
  for (const selector of selectors) {
    const found = page.locator(selector).first();
    if (await found.isVisible().catch(() => false)) return Object.assign(found, { matched: selector });
  }
  return null;
}

// True when an element matching the selector can really be seen: inside the viewport and not covered or slid away.
export async function onScreen(page, selector) {
  return page.evaluate((selector) => [...document.querySelectorAll(selector)].some((el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2 || r.right <= 0 || r.bottom <= 0 || r.left >= innerWidth || r.top >= innerHeight) return false;
    const x = Math.min(Math.max(r.left + r.width / 2, 0), innerWidth - 1);
    const y = Math.min(Math.max(r.top + r.height / 2, 0), innerHeight - 1);
    const top = document.elementFromPoint(x, y);
    return Boolean(top) && (el.contains(top) || top.contains(el));
  }), selector);
}

// One call to the application's own API from the page, with the signed-in session: {status, body}. The session token
// (read from localStorage under `tokenKey` when the application keeps one there) never leaves the browser.
export async function pageApi(page, method, path, tokenKey = "token") {
  return page.evaluate(async ([method, path, tokenKey]) => {
    const token = (tokenKey && localStorage.getItem(tokenKey)) || "";
    const r = await fetch(path, { method, credentials: "include", headers: token ? { Authorization: `Bearer ${token}` } : {} });
    let body = null;
    try { body = await r.json(); } catch { /* not JSON */ }
    return { status: r.status, body };
  }, [method, path, tokenKey]);
}

// The lines of text on screen now that were not there before: what a menu just showed.
export async function newText(page, before) {
  const seen = new Set(before.split("\n").map((l) => l.trim()));
  const after = await page.locator("body").innerText();
  return [...new Set(after.split("\n").map((l) => l.trim()).filter((l) => l && !seen.has(l)))].slice(0, 60);
}

// The buttons around an anchor (its nearest ancestor that holds at least three), then every other labelled button on
// screen: what a selector can be built from.
export async function buttons(page, anchor) {
  return page.evaluate((anchor) => {
    const describe = (b) => {
      const r = b.getBoundingClientRect();
      return { id: b.id || "", aria: b.getAttribute("aria-label") || "", title: b.getAttribute("title") || "",
               text: (b.innerText || "").trim().slice(0, 60), x: Math.round(r.left), y: Math.round(r.top),
               on_screen: r.width > 1 && r.height > 1 && r.right > 0 && r.bottom > 0 && r.left < innerWidth && r.top < innerHeight };
    };
    let box = document.querySelector(anchor);
    for (let i = 0; box && i < 10 && box.querySelectorAll("button").length < 3; i += 1) box = box.parentElement;
    const near = box ? [...box.querySelectorAll("button")] : [];
    const others = [...document.querySelectorAll("button")].filter((b) => !near.includes(b) && (b.id || b.getAttribute("aria-label")));
    return { near: near.map(describe), elsewhere: others.map(describe).filter((b) => b.on_screen).slice(0, 60) };
  }, anchor);
}

// The switches on screen ([role=switch]) with their state and the text beside them: [{label, on}]. Read, never clicked.
export async function switches(page) {
  return page.evaluate(() => [...document.querySelectorAll("[role='switch']")].filter((sw) => {
    const r = sw.getBoundingClientRect();
    return r.width > 1 && r.height > 1;
  }).map((sw) => {
    let box = sw.parentElement;
    for (let i = 0; box && i < 4 && !(box.innerText || "").trim(); i += 1) box = box.parentElement;
    return { label: ((box && box.innerText) || "").trim().split("\n")[0].slice(0, 60),
             on: sw.getAttribute("aria-checked") === "true" || sw.getAttribute("data-state") === "checked" };
  }));
}

// Close every open menu ([role=menu]) with Escape; throws when one stays open.
export async function closeMenus(page) {
  for (let i = 0; i < 3 && await page.locator("[role='menu']").first().isVisible().catch(() => false); i += 1) {
    await page.keyboard.press("Escape");
    await page.waitForTimeout(400);
  }
  if (await page.locator("[role='menu']").first().isVisible().catch(() => false)) throw new Error("a menu did not close");
}

// Which of these words (regular expressions) can be read on screen now: {source: true|false}.
export async function wordsOnScreen(page, words) {
  const found = {};
  for (const word of words) found[word.source] = await page.getByText(word).first().isVisible().catch(() => false);
  return found;
}

// The elements on screen that carry a role or are a control (button, link, input), inside `scope` (a selector, the
// whole page by default): tag, id, role, aria-* and data-state attributes, the first classes, 60 characters of text.
// What scout() dumps so a selector is written from the real element, not from a screenshot.
export async function describe(page, scope = "body", limit = 80) {
  return page.evaluate(([scope, limit]) => {
    const root = document.querySelector(scope);
    if (!root) return [];
    return [...root.querySelectorAll("[role], button, a[href], input, textarea, select")].filter((el) => {
      const r = el.getBoundingClientRect();
      return r.width > 1 && r.height > 1 && r.right > 0 && r.bottom > 0 && r.left < innerWidth && r.top < innerHeight;
    }).slice(0, limit).map((el) => {
      const attrs = {};
      for (const a of el.attributes) if (a.name.startsWith("aria-") || a.name === "data-state" || a.name === "type") attrs[a.name] = a.value.slice(0, 80);
      return { tag: el.tagName.toLowerCase(), id: el.id || "", role: el.getAttribute("role") || "", attrs,
               classes: [...el.classList].slice(0, 4), text: (el.innerText || el.value || "").trim().split("\n")[0].slice(0, 60) };
    });
  }, [scope, limit]);
}

// Click, unless the target is a control that changes a setting: a switch, a checkbox, a radio button, or anything
// inside one. A walkthrough that must change one lists it in its exported `changes` and passes that name here; the
// take's guard shows the list. Everything a walkthrough clicks goes through this.
export async function click(locator, { change = "", changes = [], timeout = 15000 } = {}) {
  const setting = await locator.evaluate((el) => {
    const hit = el.closest("[role='switch'], [role='checkbox'], [role='radio'], input[type='checkbox'], input[type='radio']")
      || el.querySelector("[role='switch'], [role='checkbox'], [role='radio'], input[type='checkbox'], input[type='radio']");
    return hit ? (hit.getAttribute("role") || hit.getAttribute("type") || "control") : "";
  }, undefined, { timeout });
  if (setting && !(change && changes.includes(change))) {
    throw new Error(`refused to click a ${setting}: a take never changes the persona's settings (not declared in \`changes\`)`);
  }
  await locator.click({ timeout });
}

// The error messages on screen now: error toasts and alerts, as text. A model refusal (HTTP 429, a quota, an error
// bubble) shows here long before any timeout.
export async function errorsOnScreen(page) {
  return page.evaluate(() => {
    const seen = [];
    for (const el of document.querySelectorAll("[data-sonner-toast][data-type='error'], [role='alert'], .toast-error")) {
      const r = el.getBoundingClientRect();
      const text = (el.innerText || "").trim().replace(/\s+/g, " ");
      if (r.width > 1 && r.height > 1 && text && /\b(429|rate.?limit|quota|too many requests|exceeded|denied|refused|unauthori[sz]ed|forbidden|failed|error)\b/i.test(text)) seen.push(text.slice(0, 200));
    }
    return seen;
  });
}

// Poll until done() returns something other than undefined, and fail AT ONCE when failed() returns a message or an
// error is on screen, instead of waiting out the timeout: a refused model call must not cost three minutes.
export async function waitUntil(page, { what, done, failed = async () => "", timeoutMs = 180000, everyMs = 500 }) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = await done();
    if (value !== undefined) return value;
    const why = (await failed()) || (await errorsOnScreen(page))[0] || "";
    if (why) throw new Error(`${what} was refused or failed: ${why}`);
    await page.waitForTimeout(everyMs);
  }
  throw new Error(`${what} did not finish within ${Math.round(timeoutMs / 1000)} s`);
}

// The lines on screen now that were not in `before`, once the screen has changed and then stayed the same for
// `quietMs` with none of the `busy` selectors visible: an answer that has finished, for an application whose API does
// not say so. Lines equal to one of `ignore` (the prompt just typed) do not count as an answer.
export async function settled(page, { what, before, ignore = [], busy = [], quietMs = 6000, timeoutMs = 180000 }) {
  const old = new Set(before.split("\n").map((l) => l.trim()));
  const skip = new Set(ignore.map((l) => l.trim()));
  let last = null;
  let stableSince = Date.now();
  return waitUntil(page, {
    what, timeoutMs,
    done: async () => {
      const text = await page.locator("body").innerText();
      if (text !== last) { last = text; stableSince = Date.now(); return undefined; }
      const fresh = [...new Set(text.split("\n").map((l) => l.trim()).filter((l) => l && !old.has(l) && !skip.has(l)))];
      if (!fresh.length) return undefined;
      for (const selector of busy) {
        if (await page.locator(selector).first().isVisible().catch(() => false)) { stableSince = Date.now(); return undefined; }
      }
      return Date.now() - stableSince >= quietMs ? fresh : undefined;
    },
  });
}
