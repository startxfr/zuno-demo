// Local end-to-end run of the world-model browser experience (ADR-0604 WP-234), no GPU:
// real Chrome (it has the H.264 decoder the bundled Chromium lacks) -> world-model-web (dev auth)
// -> world-model-runtime (mock engine, x264). Started by run.sh; run it with Node >= 18.
//   BASE_URL=http://127.0.0.1:18081 CHROME=/usr/bin/google-chrome node e2e.mjs
import { chromium } from "playwright-core";

const base = process.env.BASE_URL ?? "http://127.0.0.1:18081";
const shots = process.env.SHOTS_DIR;
const steps = [];
const problems = [];
const ok = (name) => { steps.push(name); console.log(`ok   ${name}`); };
const must = (cond, message) => { if (!cond) throw new Error(message); };

const browser = await chromium.launch({
  executablePath: process.env.CHROME ?? "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox", "--autoplay-policy=no-user-gesture-required"],
});
const page = await (await browser.newContext({ viewport: { width: 1500, height: 1000 } })).newPage();
page.setDefaultTimeout(20000);
page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
const failed = [];
page.on("response", async (r) => {
  if (r.status() >= 400) failed.push(`${r.request().method()} ${new URL(r.url()).pathname} -> ${r.status()} ${(await r.text().catch(() => "")).slice(0, 120)}`);
});
// The browser logs every failed fetch as a console error: those are judged from `failed`, below.
page.on("console", (m) => { if (m.type() === "error" && !m.text().startsWith("Failed to load resource")) problems.push(`console: ${m.text()}`); });

// a fingerprint of what is on the canvas right now
const fingerprint = () => page.evaluate(() => {
  const c = document.querySelector("canvas");
  const d = c.getContext("2d").getImageData(0, 0, c.width, c.height).data;
  let h = 0;
  for (let i = 0; i < d.length; i += 4099) h = (h * 31 + d[i] + d[i + 1] * 3 + d[i + 2] * 7) | 0;
  return { h, w: c.width, hgt: c.height, lit: d.slice(0, 4000).some((v) => v > 8) };
});
const shot = async (n) => { if (shots) await page.screenshot({ path: `${shots}/${n}.png` }); };

try {
  await page.goto(base);
  await page.getByText("Zuno World Model").first().waitFor();
  await page.getByText("Generative AI, not a 3D simulation").waitFor();
  ok("the page loads with the disclosure");

  await page.getByRole("button", { name: "Enter this world" }).click();
  await page.getByText("Creating the world").waitFor();
  ok("a preset starts a world");

  // frames must reach the canvas through WebSocket -> WebCodecs
  await page.waitForFunction(() => {
    const c = document.querySelector("canvas");
    return c && c.width === 1280 && c.getContext("2d").getImageData(0, 0, 40, 40).data.some((v, i) => i % 4 !== 3 && v > 8);
  }, null, { timeout: 30000 });
  const a = await fingerprint();
  await page.waitForTimeout(700);
  const b = await fingerprint();
  must(a.lit && b.lit, "the canvas is blank");
  must(a.h !== b.h, "the picture does not change over time: frames are not being decoded");
  ok(`video decodes and animates (${a.w}x${a.hgt})`);
  await shot("1-live");

  // keyboard control: focus the canvas, hold W, expect a latency sample and a different picture
  await page.locator("canvas").click({ position: { x: 600, y: 300 } });
  const before = await fingerprint();
  await page.keyboard.down("KeyW");
  await page.waitForTimeout(1500);
  await page.keyboard.up("KeyW");
  const after = await fingerprint();
  // Clicking the canvas locks the pointer (by design); Esc releases it, and until then every click goes to the canvas.
  const locked = await page.evaluate(() => document.pointerLockElement === document.querySelector("canvas"));
  console.log(`     pointer lock ${locked ? "engaged by the click" : "not granted in this browser (keyboard control still works)"}`);
  await page.evaluate(() => document.exitPointerLock());
  must(before.h !== after.h, "holding W changed nothing on screen");
  await page.getByText("Technical view").click();
  await page.getByText(/median \d+ ms, p95 \d+ ms/).waitFor({ timeout: 10000 });
  const latency = await page.getByText(/median \d+ ms, p95 \d+ ms/).innerText();
  const fpsText = await page.getByText(/^\d+ frames\/s$/).first().innerText();
  must(Number(fpsText.split(" ")[0]) > 5, `displayed fps too low: ${fpsText}`);
  ok(`keyboard control works; input to display: ${latency}; displayed: ${fpsText}`);
  await shot("2-technical");

  // a world edit goes through the screening and comes back applied
  await page.getByRole("textbox", { name: "Describe a change" }).fill("the sky turns red");
  await page.getByRole("button", { name: "Apply to the world" }).click();
  await page.getByText(/Change 1: applied in/).waitFor({ timeout: 15000 });
  ok("a prompt change is applied to the running world");
  await page.getByRole("button", { name: /The sky turns red/ }).click();
  await page.getByText(/Change 2: applied in/).waitFor({ timeout: 15000 });
  ok("the preset event applies as change 2");
  await shot("3-edited");

  // a refused prompt is explained and the world keeps running
  await page.getByRole("textbox", { name: "Describe a change" }).fill("a naked crowd");
  await page.getByRole("button", { name: "Apply to the world" }).click();
  await page.getByText("outside the content rules").waitFor();
  const still = await fingerprint();
  await page.waitForTimeout(400);
  must((await fingerprint()).h !== still.h, "the world froze after a refused prompt");
  ok("a refused prompt is explained and the world keeps running");

  // reset rebuilds the world from its first image
  await page.getByRole("button", { name: "Reset to the first image" }).click();
  await page.waitForFunction(() => document.body.innerText.includes("Change the world") && !document.body.innerText.includes("Creating the world"), null, { timeout: 20000 });
  await page.waitForTimeout(1500);
  const afterReset = await fingerprint();
  await page.waitForTimeout(500);
  must((await fingerprint()).h !== afterReset.h, "no video after reset");
  ok("reset rebuilds the world and the video resumes");

  await page.getByRole("button", { name: "End session" }).click();
  await page.getByText("Start a world").waitFor();
  ok("ending the session returns to the start");
  // The one refusal this run provokes on purpose is the only failed request allowed.
  const unexpected = failed.filter((f) => !/POST \/api\/sessions\/\w+\/prompts -> 422 .*prompt_refused/.test(f));
  must(unexpected.length === 0, `unexpected failed requests: ${unexpected.join(" | ")}`);
  must(failed.length === 1, `expected exactly one refused prompt, saw: ${failed.join(" | ")}`);
  must(problems.length === 0, `browser errors: ${problems.join(" | ")}`);
  ok("no console or page errors, and the only failed request is the refused prompt");
  console.log(`\nPASS ${steps.length} steps`);
} catch (e) {
  await shot("failure").catch(() => {});
  console.error(`\nFAIL after ${steps.length} steps: ${e.message}`);
  if (problems.length) console.error(problems.join("\n"));
  process.exitCode = 1;
} finally {
  await browser.close();
}
