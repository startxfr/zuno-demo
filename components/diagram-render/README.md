# diagram-render (ADR-0516)

In-cluster Mermaid-to-SVG rendering service, backing `generate_diagram`
(`components/mcp-gateway/app/handlers/diagram_gen.py`) the same way
`components/ai-gateway` backs `generate_image` (ADR-0415) — except this
never leaves the cluster: no external API, no credential, just headless
Chromium rendering Mermaid source into an SVG.

- `POST /render` — body `{"mermaid_source": "..."}`, returns
  `{"data_base64": "...", "mime_type": "image/svg+xml"}` on success, or a
  422 with `{"error": "...", "request_id": "..."}` for invalid Mermaid
  syntax (the real error/stack trace only goes to this pod's own logs).
- `GET /healthz` / `GET /readyz` — standard liveness/readiness, never
  triggers a real render (a headless-Chromium launch on every probe would
  be needless load).

No `NetworkPolicy`-exposed external Route — reached only by `mcp-gateway`
in-cluster (see `gitops/charts/diagram-render`'s `NetworkPolicy`, ingress
restricted to `mcp-gateway` only — the exact NetworkPolicy gap that broke
`generate_image` for a full session before being caught and fixed
(2026-08-23) is deliberately not repeated here).

Run locally:

```
cd components/diagram-render
npm install
npm start
curl -X POST localhost:8080/render -H 'content-type: application/json' \
  -d '{"mermaid_source": "graph TD; A-->B;"}'
```
