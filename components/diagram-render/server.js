/**
 * diagram-render (ADR-0516): renders Mermaid source into an SVG, entirely
 * in-cluster. Never calls out to any external service (unlike ai-gateway's
 * SDXL path, ADR-0415) - this was a deliberate choice over a free public
 * rendering API (mermaid.ink) specifically to keep diagram *content*
 * (which can describe internal system topology, deal-specific details,
 * etc.) inside the cluster, consistent with the C1/C2/C3 data-
 * classification discipline every other external-facing call in this
 * repo already follows.
 *
 * Reached only by mcp-gateway's diagram_gen.py handler, in-process style
 * mirror of image_gen.py's call to ai-gateway - this service has no
 * externally-routed OpenShift Route, only a NetworkPolicy-gated ClusterIP
 * Service (see gitops/charts/diagram-render's own NetworkPolicy, ingress
 * restricted to mcp-gateway only).
 *
 * Not the real MCP protocol (unlike components/mcp-servers/*) - this is a
 * single-purpose, stateless rendering operation with no tool catalog of
 * its own, so it's a plain internal REST endpoint, same shape as
 * ai-gateway's role relative to image_gen.py.
 */
const express = require("express");
const os = require("os");
const path = require("path");
const fs = require("fs/promises");
const crypto = require("crypto");
const { run } = require("@mermaid-js/mermaid-cli");

const PORT = process.env.PORT || 8080;
// Generous but bounded - a real technical diagram is a few KB of text;
// anything past this is either abuse or a runaway LLM generation, and
// puppeteer rendering time scales with diagram complexity, so this also
// caps worst-case render latency.
const MAX_SOURCE_BYTES = parseInt(process.env.MAX_SOURCE_BYTES || "65536", 10);
const RENDER_TIMEOUT_MS = parseInt(process.env.RENDER_TIMEOUT_MS || "30000", 10);

const app = express();
app.use(express.json({ limit: "256kb" }));

let ready = false;

// ADR-0037's second layer, same posture as components/mcp-servers/
// confluence/server.py: NetworkPolicy (ingress from mcp-gateway only) is
// the first layer; this shared secret proves a call actually came from
// the gateway, not merely from a network-adjacent pod. Rendering
// arbitrary Mermaid-derived content through a real headless-Chromium
// process is a more interesting attack surface than a plain API
// pass-through, so this stays on even though diagram-render (unlike
// confluence-mcp) holds no credential of its own to protect - the
// resource being protected here is the render process itself. Not
// enforced as a hard startup requirement (same as diagram_gen.py's own
// MCP_GATEWAY_WORKLOAD_TOKEN reasoning) so this still starts and serves
// health checks if the secret hasn't landed yet.
const GATEWAY_TOKEN = process.env.MCP_GATEWAY_WORKLOAD_TOKEN || "";
app.use("/render", (req, res, next) => {
  if (GATEWAY_TOKEN && req.get("X-Zuno-Gateway-Token") !== GATEWAY_TOKEN) {
    return res.status(403).json({ error: "missing or invalid gateway token" });
  }
  next();
});

async function renderMermaidToSvg(mermaidSource) {
  // mermaid-cli's run() operates on files, not strings in memory - a
  // unique per-request temp dir avoids any cross-request collision under
  // concurrent load, and is fully cleaned up in the finally block below
  // regardless of success/failure.
  const workDir = await fs.mkdtemp(path.join(os.tmpdir(), "diagram-"));
  const inputPath = path.join(workDir, "input.mmd");
  const outputPath = path.join(workDir, "output.svg");
  try {
    await fs.writeFile(inputPath, mermaidSource, "utf8");
    await run(inputPath, outputPath, {
      outputFormat: "svg",
      puppeteerConfig: {
        // Restricted SCC (random non-root UID, no HOME) - the default
        // Chromium sandbox needs privileges this environment never
        // grants, and /dev/shm is small under the pod's default memory
        // limits; both flags are the standard, documented workaround
        // for exactly this containerized-non-root shape (same "restricted
        // SCC -> random UID" class of issue this repo already works
        // around elsewhere, e.g. every Python Job's HOME=/tmp fix).
        args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
      },
    });
    return await fs.readFile(outputPath, "utf8");
  } finally {
    await fs.rm(workDir, { recursive: true, force: true }).catch(() => {});
  }
}

app.post("/render", async (req, res) => {
  const mermaidSource = req.body && req.body.mermaid_source;
  if (typeof mermaidSource !== "string" || mermaidSource.trim() === "") {
    return res.status(400).json({ error: "mermaid_source is required and must be a non-empty string" });
  }
  if (Buffer.byteLength(mermaidSource, "utf8") > MAX_SOURCE_BYTES) {
    return res.status(400).json({ error: `mermaid_source exceeds ${MAX_SOURCE_BYTES} bytes` });
  }

  const requestId = crypto.randomUUID();
  const timeout = new Promise((_, reject) =>
    setTimeout(() => reject(new Error("render timed out")), RENDER_TIMEOUT_MS)
  );

  try {
    const svg = await Promise.race([renderMermaidToSvg(mermaidSource), timeout]);
    return res.json({
      data_base64: Buffer.from(svg, "utf8").toString("base64"),
      mime_type: "image/svg+xml",
    });
  } catch (err) {
    // Full detail server-side only - mirrors agent-runtime's own
    // "log the real exception, never leak it to the caller verbatim"
    // posture adopted this session (components/agent-runtime/app/main.py's
    // _CLIENT_FACING_STREAM_ERROR). Invalid Mermaid syntax is the
    // overwhelmingly common failure mode here (an LLM's own generation
    // mistake, not a system fault), so the caller-facing message says so
    // plainly rather than echoing a raw puppeteer/parser stack trace.
    console.error(`[${requestId}] render failed:`, err);
    return res.status(422).json({ error: "invalid or unrenderable Mermaid source", request_id: requestId });
  }
});

// Deliberately does NOT do a real render on every probe (same reasoning
// as components/mcp-servers/confluence/server.py's healthz: a liveness/
// readiness probe firing every ~10-15s must never carry the cost of a
// full headless-Chromium launch) - readiness instead confirms the
// mermaid-cli module loaded correctly at startup (see bottom of file).
app.get("/healthz", (_req, res) => res.status(200).json({ status: "ok" }));
app.get("/readyz", (_req, res) => (ready ? res.status(200).json({ status: "ready" }) : res.status(503).json({ status: "not-ready" })));

app.listen(PORT, () => {
  // require() above already proves the module resolved; readiness only
  // needs to wait for the HTTP listener itself to be up.
  ready = true;
  console.log(`diagram-render listening on :${PORT}`);
});
