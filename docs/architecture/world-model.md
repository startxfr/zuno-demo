# World model

The interactive generative world-model experience of ADR-0604: a browser demo in which a visitor describes a place, walks into it
and changes it while inside, on one RTX PRO 6000 Blackwell that exists only while the demo is on. This page is the one-screen map;
the decisions, their reasons and the gates are in
[ADR-0604](../adr/0604-introduce-an-interactive-generative-world-model-experience.md), the presenter's steps in
[the demo script](../demo/world-model.md).

```mermaid
flowchart TB
  Browser[Browser: React + PatternFly<br/>WebCodecs H.264 decoder]
  FD[oauth2-proxy front door<br/>Route, Keycloak groups, token refresh]
  Web[world-model-web<br/>identity, GPU lease, prompt screening, relay]
  GW[ai-gateway<br/>prompt enhancement, C1 local only]
  subgraph GPU[world-model-runtime, one pod, node zuno-gpu-world-model-a]
    Flux[FLUX.2 klein 4B<br/>first image, world edits]
    Wp[Waypoint-1.5-1B<br/>4 frames per step]
    Enc[H.264 encoder<br/>NVENC or x264]
  end
  S3[(S3 mirror<br/>pinned weights)]
  Browser -->|HTTPS 443, WebSocket| FD --> Web
  Web -->|user token| GW
  Web -->|REST + WebSocket, internal token| GPU
  S3 -->|init container| GPU
  Flux --> Wp --> Enc -->|binary video + control sequence| Web
```

## What is where

| Piece | Where | Lifetime |
|---|---|---|
| GPU node (`g7e.4xlarge`, no MIG, taint `zuno.io/gpu-world-model`) | `gitops/apps/machines-world-model`, role `world_model_gpu` | only while `zuno_world_model_enabled` is true |
| Runtime, web tier, front door | `gitops/charts/world-model`, role `world_model` | same switch |
| Namespace, GPU quota, SecretStore | `gitops/charts/namespaces`, `gitops/charts/external-secrets` | always (empty while off) |
| Keycloak client `world-model` and its group | realm import, created live by the role | always |
| Model weights, pinned | S3 `zuno-demo-sources/models/world-model`, `platform/world-model/models.lock.yaml` | always |
| Dashboard, cost alert | `gitops/charts/grafana`, `gitops/charts/observability` | always (empty while off) |

## Rules worth knowing

- **One switch** (`zuno_world_model_enabled`, in `ansible/clusters/<cluster>.yml`) drives both the node (Day 0, run locally: the
  AAP credential has no Machine API rights) and the application (Day 2). Install converges to it; off removes what is left.
- **One world per GPU.** The lease is taken before the slow image generation; a second visitor is told busy. A tab left open
  frees the GPU after 60 seconds, a quiet session after 3 minutes, any session after 30.
- **Waypoint-1.5 takes no text.** A prompt is a FLUX edit of the current frame spliced into the world (`append_frame`).
- **Identity is the validated token.** The front door forwards and refreshes it (the access token lives 15 minutes); the API
  checks signature, issuer, audience, expiry and group again, and a header never grants anything.
- **Governed prompts.** Local rules always; the ai-gateway rewrites and screens when it can, with C1 and local-only, and the demo
  degrades to the filtered text when it cannot. There is no path to an external model provider.
- **Honest measurements.** Frames carry the last control sequence they reflect, so the browser measures real input-to-display
  latency; the engine step, VRAM and displayed frames come from this GPU, never from a vendor figure.

## Not in v1

WebRTC (the video runs over the HTTPS Route), the ai-gateway image provider for FLUX, MIG, several concurrent worlds, a persistent
world, and a Perses copy of the dashboard (ADR-0604 §13).
