// WP-286: the click guard of walkthroughs/_helpers.mjs, against tests/fake-open-webui.mjs (run by record-offline.sh in
// the Playwright image). A switch is not clicked unless the walkthrough declared the change.
import { chromium } from "playwright";
import { click } from "../walkthroughs/_helpers.mjs";

const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto("http://127.0.0.1:8099/");
await page.click("#integration-menu-button");
await page.click("#tools-row");
const sw = page.locator("#zuno-switch");
let failed = 0;
const expect = (what, ok) => { console.log(`${ok ? "ok   " : "FAIL "} ${what}`); if (!ok) failed = 1; };

let refused = "";
try { await click(sw, { changes: [] }); } catch (e) { refused = e.message; }
expect("a switch is refused", /refused to click a switch/.test(refused));
expect("and it is still on", (await sw.getAttribute("aria-checked")) === "true");
refused = "";
try { await click(page.getByText("Zuno tools"), { change: "tools", changes: [] }); } catch (e) { refused = e.message; }
expect("naming a change that is not declared does not help (a plain label is clicked, it holds no switch)", refused === "");
refused = "";
try { await click(sw, { change: "zuno-tools-switch", changes: ["zuno-tools-switch"] }); } catch (e) { refused = e.message; }
expect("a declared change is clicked", refused === "" && (await sw.getAttribute("aria-checked")) === "false");
await browser.close();
process.exit(failed);
