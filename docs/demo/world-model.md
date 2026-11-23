# Scenario: World model - walk into a generated world on an on-demand GPU

Last reviewed: 2026-11-20

## Introduction

A world model does not draw a scene from a 3D model. It invents the next frame from the last ones, the visitor's key
presses and a description. The visitor types a place, walks into it, and changes it while inside. It is approximate on
purpose: it drifts, it forgets what it showed ten seconds ago, and it sometimes ignores a request. In Zuno it is an
experience client like the others (see [Appendix A](#appendix-a---hld)). The platform adds everything around the
model: the same identity, the same rules on what may be asked, the same observability, and a GPU that exists only
while the demo does. The pods, the GPU node and the prompt path are in [Appendix B](#appendix-b---lld).

**The message:** "Generative AI can build a world you walk into and change. The platform keeps it governed: who may
use it, what may be asked, what it costs, and a GPU that exists only while it is used."

![The 5-minute version of the world model demo, cut from the recorded run of 2026-11-08, not live: a snowy village and a volcano generated frame by frame, a walk into the world, and the prompt that edits the frame to a red sky. The recording carries its own band saying it was recorded and is real output of the demo's GPU runtime.](../assets/img/demo/world-model.gif)

## Personas

The personas are fictional role accounts of the Keycloak realm `zuno`. They share one password,
kept in Vault at `keycloak/demo-personas`. The [catalogue](README.md#personas) lists all of them.

| Persona | Profile | What it can do here | Role in this demo |
|---|---|---|---|
| **ai-ops-01** | AI platform operator, back office. Groups `ocp-ai-ops` (admin on the Zuno namespaces, `zuno-monitoring` included), `agent_tekos`, `openwebui_admin`. | Admitted to the page (`ocp-ai-ops` is one of its three groups) and an operator there: sees who holds the GPU and can release it. 12 worlds per hour. Opens Grafana. | The presenter's browser in both versions. |
| **paas-ops-01** | Platform operator, back office. Group `ocp-paas-ops` (cluster-admin). | Admitted to the page, also as an operator. Reads the GPU node and the pods. | The second visitor and the `oc` terminal of the 15-minute version. |

Other identities:
- the confidential Keycloak client `world-model`, used by the oauth2-proxy front door;
- an internal token between the web tier and the GPU runtime, from Vault through an ExternalSecret;
- the golden-path probe `world-model` creates a world as `GOLDEN_WORLD_PERSONA` (ai-ops-01) from inside the web pod.

## Presenter lifecycle

`make demo use world-model 5|15` selects this page.
Each section below is printed after its action's Ansible file (`ansible/demos/world-model/<action>.yml`) has run, and
says what is left to the presenter. The GPU node is created on demand and bills by the hour. Lead time: about **40
minutes** from the switch to a warm page (15 minutes for the node, 10 for the application, then the checks and a dry
run), when AWS has capacity for the world-model GPU MachineSets. Without capacity there is no node at all: start
earlier and prepare the recording. Credentials are named by their Vault path, never written.

### Status

Nothing to do when it reports the demo is off: that is its normal state today. The file reads, without changing
anything: the flag `zuno_world_model_enabled` in `ansible/inventories/demo333/cluster.yml` (as committed in this checkout, not read from the
cluster), the namespace `zuno-world-model`, the
node labelled `zuno.io/gpu-workload=world-model`, and the world-model Application. While the flag is false there is no
node and no Application, and the page is not show-ready. When the flag is true and a piece is missing, run Install.
By hand, the same reads:

```bash
oc get nodes -l zuno.io/gpu-workload=world-model
oc get pods -n zuno-world-model
```

### Check

Nothing to do when it passes. It runs the golden-path probe `world-model`
(`ONLY=world-model make demo golden-path`, see [golden-path.md](golden-path.md)). It reads that the GrafanaDashboard `world-model` exists in `zuno-monitoring`. It creates a world as
`GOLDEN_WORLD_PERSONA` (**ai-ops-01**) from inside the web pod and must print `PASS`. While the application is not
installed it reports `roadmap`: do not present the demo as live, use the recording (see Start). Run it within the
hour before the session. After Install, `make d2 check world-model` is the deeper preflight: GPU node, runtime engine
waypoint-1.5-1b, image model flux2-klein-4b, encoder `nvenc` (or `x264`), Keycloak 200, ai-gateway reached, no
other egress, Route up. It must be green.

### Install

The file never creates the GPU node. While `zuno_world_model_enabled` is not `true` on `origin/devel`
(`ansible/inventories/demo333/cluster.yml`, as of the last `git fetch`), it fails with `REFUSED` and nothing is installed: use the
recording. When the flag is true, it only reads what exists (the node, the Application, the pods) and prints the owner's
actions below. A GPU node is cluster infrastructure: it needs the platform owner's **double approval**, given
before anything runs, and the owner does the following by hand, never the step. `make demo rehearse` does not run
Install either: it refuses while the demo is off.

1. Set `zuno_world_model_enabled: true` in `ansible/inventories/demo333/cluster.yml`, commit and push. The Day-2 install runs
   through AAP, which reads the repository, not your workstation.
2. `make d0 install world-model-gpu`, run locally (the AAP credential has no Machine API rights). It scales each
   world-model GPU MachineSet named in `zuno_world_model_gpu_sets` to one Machine and waits until one node is Ready
   with a whole GPU: about 15 minutes. When one node has joined, scale the other world-model MachineSets to 0
   (`oc scale machineset <name> -n openshift-machine-api --replicas=0`): the role expects exactly one node. A Machine
   stuck in `Provisioning` with `InsufficientInstanceCapacity` (`oc describe machine -n openshift-machine-api <name>`)
   means AWS has no capacity in that zone for now.
3. The node is ready when exactly one node is labelled `zuno.io/gpu-workload=world-model` with
   `mig.config.state=success` and 1 GPU allocatable.
4. `make d2 build world-model` first, then `make d2 install world-model`. The world-model images were not rebuilt after
   the incident of 2026-11-15 (the internal registry bucket was emptied), so the build comes before the install until
   the images are back in the registry. The install applies the chart. The runtime copies about 20 GB of weights from S3 (about 2.5
   minutes, measured) and loads two models: about 10 more minutes. The Route is
   `https://world-model.apps.demo333.startx.fr`.
5. `make d2 check world-model`: the preflight of Check. It must be green.

`make d0 check world-model-gpu` reports whether the node and the switch agree.

### Start

The file runs nothing. What only a person does, at least **40 minutes** after the Install
began, and earlier when AWS may have no capacity:

- [ ] **Chrome or Edge** (the video is H.264 decoded by WebCodecs). Open `https://world-model.apps.demo333.startx.fr`
  and sign in as **ai-ops-01**, password in Vault at `keycloak/demo-personas`. The persona must be in
  `zuno-world-model-users`, `ocp-ai-ops` or `ocp-paas-ops`.
- [ ] Warm-up: one dry-run world, then **End session**, so the first image in front of the audience is not a cold
  start.
- [ ] Grafana `zuno-monitoring`, dashboard **Zuno Platform / World model**, last 1 hour. It is empty while the demo is
  off. The alert `ZunoWorldModelGpuNodeUpTooLong` fires when a world-model Machine has existed for more than 8 hours. A
  Perses copy of the dashboard is deferred.
- [ ] The recorded fallback `world-model-recorded-2026-11-08.mp4` is on the presenting laptop, open in a video player.
  It is 24 s, 1280x720, a real run of this runtime on 2026-11-08 with the red-sky edit, with the label "RECORDED"
  burnt in. It is not in git (7 MB): it is kept at `/home/cl/demo-fallback/` on the operator's workstation. Show it
  labelled as recorded, never as live. It predates the re-anchor, so it shows no **Stabilizing the world** banner.
- [ ] Known on screen, not a failure: the banner **Stabilizing the world** about every 2 s of walking, with about 0.6 s
  of frozen picture and a small jump of the view. It is the drift fix.
- [ ] 15-minute version: a second browser profile signed in to the page as **paas-ops-01**, and a terminal with `oc`
  as **paas-ops-01**.

### Stop

After the session, in the page, **Sign out** (top right, next to your name). It frees the GPU if you hold it, ends the
oauth2-proxy cookie, then ends your Keycloak single sign-on session and brings you back to the site. The next visit
asks for a login, so another person can sign in on the same browser. Keycloak may show one "Do you want to log out?"
confirmation first (no ID token is passed to it, by design). The client `world-model` must list
`https://world-model.<domain>/*` in its post-logout redirect URIs (set in the realm file, applied to a live realm by
the client-reconcile Job). Close the Grafana profile and the terminal. The GPU node keeps billing until Uninstall.

### Uninstall

The file removes nothing: it shows what is still there (the node and the pods) and prints the owner's actions below. The
owner does them by hand after the session, never the step. The rehearsal covers Uninstall as that no-op:

1. `make d2 uninstall world-model` removes the application.
2. Set `zuno_world_model_enabled: false` in `ansible/inventories/demo333/cluster.yml`, commit and push. Otherwise the next
   `make d0 install` creates the node again.
3. `make d0 uninstall world-model-gpu` terminates the GPU node and removes the world-model MachineSets. It refuses
   while the application exists, and it never touches `zuno-gpu-a`.

`make d0 check world-model-gpu` reports whether the node and the switch agree.

## 5-minute version

The model's context is about ten seconds, so the script resets often. Say so.

| Time | Do | Say | You should see |
|---|---|---|---|
| 0:00 | Read the notice at the top of the page. | "This is generative AI, not a 3D simulation. The picture is invented frame by frame. One GPU, one world, on a node that exists only for the demo." | **Generative AI, not a 3D simulation**. |
| 0:30 | Pick **Snowy village, then a volcano**. | "Nothing is pre-recorded. FLUX.2 klein makes the first image, then the world model generates every frame." | The first image in about a second (measured 0.9 s), then the world runs. |
| 1:15 | Click the picture. Walk in short bursts: W for a few seconds, a turn, stop. Open **Technical view**. | "These numbers are measured on this GPU, not taken from a vendor sheet." | **World engine** `waypoint-1.5-1b` (bf16), **Video encoder** `nvenc`, **Displayed** about 40 frames/s, **Input to display** well under 200 ms (p50 145 ms measured at the server on 2026-11-08). |
| 2:15 | Stop walking with the sky in view. Press **The sky turns red**. | "Waypoint takes no text. A prompt is an image edit: FLUX edits the current frame and the world continues from it." | Banner **Editing the world**. About 1.2 s later the sky is red-pink and the village is still there (measured). |
| 3:15 | Type `a torture chamber under the village` *(untested prompt)* and send it. | "What may be asked is governed too. The request is refused with a reason before it reaches the GPU, and the world keeps running." | "This description is outside the content rules of the demo." The world keeps running. |
| 4:00 | Close. Press **End session** if you stop here. | "You walk into a described place and change it while inside. The platform adds the rest: identity, rules on what may be asked, measurements, and a GPU that exists only while the demo does." | |

**Golden rule:** never walk more than 10 s straight ahead (the model collapses into texture against a snow wall);
press **Reset to the first image** otherwise.

The refusal prompt was never run live. It contains `torture`, a term of the built-in deny list in
[`components/world-model-web/app/prompts.py`](../../components/world-model-web/app/prompts.py), so the local check
refuses it before any call to the ai-gateway.

## 15-minute version

Run the 5-minute version, then:

| Time | Do | Say | You should see |
|---|---|---|---|
| 5:00 | Type your own change: `snow starts falling` *(untested prompt)*. | "My words go through the ai-gateway first: a local model, my own token, public data only. It screens them again and rewrites them for the image model." | The note under the box shows what was really sent. If it says enhancement is off, the filtered text was sent as typed; the demo works either way. |
| 6:15 | Press **Reset to the first image**. | "The model remembers about ten seconds. Reset rebuilds the world from where it started: this is how a long session survives." | The first image again, then the world runs. |
| 7:00 | Walk for about 30 s in short bursts: a few seconds forward, a turn, a pause. | "After our first live show we measured the drift: standing still, the scene holds; walking, it is lost within about ten seconds. Now, every two seconds of walking, FLUX redraws the current frame from the scene text and the world restarts from it. It is a mitigation of a known limit of the model, not a cure." | **Stabilizing the world** about every 2 s, about 0.6 s of frozen picture each time, the view shifts slightly. The village holds. |
| 8:30 | Second browser profile, **paas-ops-01**: open the page. | "One GPU, one world. A second visitor is told, never queued behind the first." | **Another world is running on the GPU**, with the holder's name. As an operator, paas-ops-01 also sees **Release it**: do not click it. |
| 9:30 | Grafana **Zuno Platform / World model**: rows **The GPU node (on demand, billed by the hour)**, **The world, as the GPU sees it**, **What the browser measured (ADR-0604 section 9.1)**, **Who may do what**. | "Everything you saw is measured: GPU, engine step, frames generated against frames displayed, the latency the browser measured, and what happened to each prompt." | **GPU node up for (hours)**; **Input to display, p50 / p95**; the refusal of the 5-minute version under **Prompts, by kind and verdict**. |
| 11:30 | Terminal: `oc get nodes -l zuno.io/gpu-workload=world-model` and `oc get pods -n zuno-world-model` | "The GPU node exists only for the demo. One switch in the repository creates it about 40 minutes before and removes it after. An alert fires if it is forgotten for 8 hours." | One g7e node. Pods `world-model-front-door`, `world-model-web` and `world-model-runtime` Running. |
| 12:30 | Walk through [Appendix B](#appendix-b---lld). | "The front door admits three groups and the web tier checks the token again. Prompts pass a local deny list, then the ai-gateway at C1, local only. Outside the cluster, the namespace may reach only Keycloak and the S3 bucket of the weights. There is no path to an external model." | |
| 14:00 | **End session**, then **Sign out** (top right, next to the name). | "Ending the session frees the GPU at once. Sign out also ends my single sign-on session, so the next person signs in as themselves." | The page asks for a login again. Keycloak may first ask "Do you want to log out?". |
| 14:30 | Close | Repeat the message. | |

## If something goes wrong

| Symptom | Fallback | Say |
|---|---|---|
| The page or the GPU node is down, or the probe fails on the morning | Do not present it as live. Play `world-model-recorded-2026-11-08.mp4` **labelled as recorded, never as live**, or fall back to a roadmap slide. | "This is a recording of a real run on our GPU, made on 2026-11-08. The GPU is not running today." |
| "The GPU runtime is not ready (models loading, or the demo is off)." | Normal for about 10 minutes after `make d2 install world-model`. Watch `oc get pods -n zuno-world-model`. On stage: the recording. | |
| The init container `fetch-models` still copies after 5 minutes | The EgressFirewall's S3 address ranges are stale (`egress.s3CidrsByRegion` in the chart). Refresh them from AWS's published ranges. Not fixable on stage. | |
| "Another world is running on the GPU" and it is nobody's | A tab was closed. The GPU is freed after 60 s (detached) or 3 minutes (idle). As an operator, click **Release it**. | |
| The picture collapses into texture | Press **Reset to the first image**. | "The model remembers about ten seconds. This is its known limit." |
| The red sky does not read well | Say so, and reset. | "The edit is a goal, not a guarantee." |
| The picture is blank, grey or green | Reload the page and start again. If it repeats, the encoder is the suspect (**Technical view** names it): `oc logs -n zuno-world-model deploy/world-model-runtime`. | |
| "This browser cannot decode the video" | Use Chrome or Edge. | |
| A slow first image | The first FLUX call after a cold start compiles kernels. The dry run avoids it. | "The first call warms the GPU up." |
| A refusal for the hourly limit | 12 worlds per user per hour. Continue as **paas-ops-01**. | |
| A forgotten node | The alert `ZunoWorldModelGpuNodeUpTooLong` fires after 8 hours. Run Stop and Uninstall of the [Presenter lifecycle](#presenter-lifecycle). | |

## Limits

- **A persistent or accurate world.** No geometry, no physics, no memory beyond about ten seconds; two visitors never
  share one.
- **Drift is mitigated, not solved** (ADR-0604 D9). Walking makes the model lose its scene within about ten seconds.
  Every two seconds of walking, the runtime redraws the picture from the scene text and restarts from it ("Stabilizing
  the world", about 0.6 s of frozen picture, the view shifts slightly). A long walk still ends somewhere else than it
  started. A world made from an uploaded image alone has no text and is never re-anchored.
- **A prompt is not always obeyed.** The red sky and the volcano are a goal.
- **The measurements date from 2026-11-08**, before the re-anchor. They were not measured again with the re-anchor
  on, which freezes the picture about 0.6 s every 2 s of walking.
- **Chrome and Edge only.** Other browsers get a message, not a picture.
- **No WebRTC.** The video runs over the HTTPS Route (WebSocket, H.264), so it crosses any network. WebRTC is a
  possible phase 2.
- **No image provider in the ai-gateway.** FLUX makes the first image inside the namespace, with no fallback to an
  external provider.
- **One recording only**, with the red-sky edit, made before the re-anchor. WP-237 asked for one per preset (three
  presets: **Logistics warehouse**, **City at night**, **Snowy village, then a volcano**).
- **GPU capacity is not guaranteed.** The node is a g7e instance on demand in eu-central-1. AWS refused it from
  2026-11-10 to 2026-11-11 and again on 2026-11-12.
- **Acceptance is not complete** ([WP-237](../roadmap/work-packages/wp-237-world-model-final-acceptance-and-rehearsal.md)):
  the negative security tests (a user outside the groups gets 403, no other egress, prompts absent from logs and
  metric labels) are still open.

## Appendix A - HLD

Where the world model sits in Zuno. The highlighted box is the subject of this page. Plain arrows carry requests,
dotted arrows carry identity, policy or telemetry.

```mermaid
flowchart TB
  subgraph EXP["Experiences: clients of one governed backend"]
    UNIFAI["UnifAI<br/>agents, RAG"]
    OWUI["Open WebUI"]
    CLAW["OpenClaw<br/>one assistant per persona"]
    DIFY["Dify"]
    KAGENT["kagent"]
    LS["OpenShift Lightspeed"]
    BLENDER["Blender add-on"]
    WM["World model"]
  end
  subgraph GOV["Gateways and governance"]
    TP["token proxy,<br/>egress proxy"]
    RHCL["RHCL Kuadrant<br/>auth, rate limits"]
    AIGW["ai-gateway<br/>classification, routing,<br/>guardrails, quotas"]
    MCPGW["mcp-gateway<br/>tools by group"]
    A2A["a2a-gateway<br/>delegation, approval"]
  end
  subgraph AI["Red Hat OpenShift AI"]
    MAAS["MaaS<br/>gateway, portal, API keys"]
    KSERVE["KServe llm-d<br/>local models on MIG GPUs"]
    EXT["SaaS models<br/>Mistral, Codestral, OVHcloud"]
    PG["GenAI playground"]
    BUILD["Pipelines, MLflow,<br/>Kueue, model registry"]
    EVAL["TrustyAI, EvalHub,<br/>LMEval"]
  end
  subgraph TOOLS["Agents and tools"]
    OKF["OKF agents release<br/>zuno-demo-agents"]
    MCPS["MCP servers<br/>Confluence, Git, AAP,<br/>k8s, Google Workspace"]
  end
  subgraph TRUST["Identity, secrets, supply chain"]
    KC["Keycloak<br/>personas, groups"]
    VAULT["Vault, ESO,<br/>cert-manager"]
    SC["RHTAS, Quay,<br/>image policy"]
  end
  subgraph PLAT["Platform and operations"]
    OCP["OpenShift, Service Mesh,<br/>GPU nodes"]
    GITOPS["Argo CD GitOps,<br/>AAP Day 0-3"]
    OBS["Prometheus, Grafana,<br/>Tempo"]
  end
  SAAS[("SaaS<br/>Confluence, Google,<br/>Salesforce")]

  UNIFAI & OWUI & WM --> AIGW
  CLAW & DIFY & KAGENT --> TP --> AIGW
  BLENDER --> RHCL --> AIGW
  UNIFAI --> A2A
  UNIFAI & OWUI & TP & LS --> MCPGW
  LS & PG --> MAAS
  AIGW --> MAAS
  MAAS --> KSERVE
  AIGW --> EXT
  MAAS -. published .-> EXT
  MCPGW --> MCPS --> SAAS
  BUILD --> KSERVE
  EVAL --> MAAS
  RHCL -. limits .-> MAAS
  OKF -. agents, policies .-> UNIFAI & AIGW & MCPGW
  KC -. tokens .-> AIGW & MCPGW & MAAS
  AIGW & MCPGW -. metrics, traces .-> OBS

  classDef focus fill:#ffd54f,stroke:#d84315,stroke-width:4px,color:#000;
  class WM focus;
```

## Appendix B - LLD

The three pods, the GPU node and the prompt path. Drawn from `gitops/charts/world-model/` (`values.yaml`,
`templates/front-door.yaml`, `web.yaml`, `runtime.yaml`, `egressfirewall.yaml`, `networkpolicy.yaml`),
`gitops/apps/machines-world-model/application-d0.yaml`, `components/world-model-web/app/prompts.py` and
`components/world-model-runtime/app/session.py`. The one-screen map is
[docs/architecture/world-model.md](../architecture/world-model.md).

```mermaid
flowchart LR
  USER["Browser, Chrome or Edge<br/>WebCodecs H.264 decoder"] -->|"HTTPS 443, WebSocket<br/>Route world-model, timeout 30 min"| FD
  subgraph NS["namespace zuno-world-model, experience client, GPU quota 1"]
    FD["world-model-front-door<br/>oauth2-proxy :4180, client world-model<br/>groups zuno-world-model-users,<br/>ocp-ai-ops, ocp-paas-ops"]
    WEB["world-model-web :8080<br/>token checked again: issuer, audience, group<br/>GPU lease: one world, idle 3 min,<br/>detached 60 s, at most 30 min<br/>12 worlds per user per hour"]
    SCR["Prompt screening<br/>1. local: 300 characters, deny list<br/>2. ai-gateway rewrite, degrades if absent"]
    subgraph GPU["world-model-runtime :8080, GPU node g7e, one whole GPU, no MIG"]
      FLUX["FLUX.2 klein 4B<br/>first image, world edits,<br/>re-anchor every 2 s of movement"]
      WPT["Waypoint-1.5-1B<br/>4 frames per step"]
      ENC["H.264 encoder<br/>NVENC or x264"]
    end
    INIT["init container fetch-models<br/>about 20 GB of pinned weights"]
  end
  FD --> WEB --> SCR
  WEB -->|"REST and WebSocket<br/>internal token"| FLUX
  FLUX --> WPT --> ENC
  ENC -->|"video and control sequence"| WEB
  S3[("S3 zuno-demo-sources<br/>models/world-model, eu-west-2")] --> INIT --> FLUX
  SCR -->|"user token, C1,<br/>X-Zuno-Local-Only"| AIGW["ai-gateway, zuno-ai-run<br/>local model"]
  FD -.->|"OIDC"| KC["Keycloak realm zuno"]
  EF["EgressFirewall: Keycloak and S3 only<br/>NetworkPolicy: DNS, namespace, ai-gateway"] -.-> NS
  NODE["MachineSets zuno-gpu-world-model-*<br/>taint zuno.io/gpu-world-model,<br/>switch zuno_world_model_enabled"] -.-> GPU
  WEB & ENC -.->|"ServiceMonitors"| PROM["Prometheus, Grafana<br/>World model dashboard"]
```

## References

The decisions this page rests on:

- [ADR-0604](../adr/0604-introduce-an-interactive-generative-world-model-experience.md): Waypoint-1.5 and FLUX.2 klein
  on one unpartitioned GPU, an on-demand node behind one switch, prompts screened through the ai-gateway, and the
  re-anchor against drift (D9).
- [ADR-0587](../adr/0587-admit-additional-user-experiences-over-the-one-governed-backend.md): experiences are clients
  of the one governed backend.
- [ADR-0605](../adr/0605-gate-every-live-demo-on-a-golden-path-check-and-a-freeze-window.md): no live demo without a
  passing golden path.
- [ADR-0349](../adr/0349-restructure-demo-personas-cluster-access-groups-and-new-agents.md): Restructure demo personas, ocp-* cluster-access groups and two new agents.
- [ADR-0616](../adr/0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md): Prepare and play every catalogue demo through one make demo lifecycle.

## Page status

> **Status:** Rehearsed on 2026-11-15 through `make demo rehearse world-model`: the 5-minute version PASS at 10:50 (12
> units, 22 s), 1 skipped (`install`); the 15-minute version PASS at 10:52 (21 units, 32 s), 1 skipped (`install`).
> Evidence: [WP-279](../roadmap/evidence/wp-279-blender-world-model-rehearsals-2026-11-15.md). This PASS is not
> show-ready: the demo is switched off (`zuno_world_model_enabled` is `false`), there is no GPU node and the application
> is not installed, so `check` passed on the dashboard and on a probe that reports the demo as `roadmap`, not on a
> world. It proves the files and the page play, not the demo. Prerequisites checked read-only on demo333 on 2026-11-12:
> namespace
> `zuno-world-model` present with no pods and no world-model Application installed (quota `requests.nvidia.com/gpu`
> 0/1, SecretStore `vault` Valid); no world-model GPU node. The six world-model MachineSets (g7e.2xlarge, g7e.4xlarge
> and g7e.8xlarge in eu-central-1a and 1b) each had a Machine in `Provisioning` at 22:46 UTC, refused by AWS with
> `InsufficientInstanceCapacity`; after that one-hour search the switch `zuno_world_model_enabled` was set back to
> `false` in git (42172d2e, 2026-11-13 00:05 CET). Grafana
> dashboard `world-model` synced. The golden-path probe `world-model` reports `roadmap` until the application is
> installed. History: shown live on 2026-11-09 (moment 5 of the [demonstration](demo-day-2026-11-09.md)), where it was
> the one part that did not go as planned. The presenter's feedback (the picture blurred and lost the scene while
> walking) led to the re-anchor of [ADR-0604](../adr/0604-introduce-an-interactive-generative-world-model-experience.md)
> D9, deployed the same day. On 2026-11-23 the owner switched the demo on for the demonstration of 2026-11-24 (45108ca4):
> a g7e.8xlarge node in eu-central-1b was ready at 17:21 UTC after a 45-minute capacity search, the runtime image was
> rebuilt at 18:06 UTC (the internal registry no longer held the one of 2026-11-09), the install was green at 18:08 UTC
> and the golden-path probe `world-model` passed (a world created, 460 frames, `waypoint-1.5-1b`, `nvenc`, an edit
> applied in 1.2 s). No rehearsal through `make demo rehearse` is recorded since. The switch goes back to `false` and
> the node is uninstalled after the demonstration; it bills until then.
> **Show-ready ([ADR-0606](../adr/0606-admit-new-experiences-with-a-definition-of-done-and-a-wip-limit.md)):**
> not show-ready: the GPU node is off.
> **Personas:** see [Personas](#personas).
> **Used in workshops:** none while it is not show-ready.
