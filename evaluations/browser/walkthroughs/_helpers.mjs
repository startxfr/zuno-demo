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
