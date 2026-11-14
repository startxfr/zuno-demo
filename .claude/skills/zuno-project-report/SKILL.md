---
name: zuno-project-report
description: Generate "Zuno Atlas", the private HTML project report for zuno-demo (release timeline with ADR/WP per band, progress charts, platform HLD, per-component datasheets with live CPU/RAM/PVC/GPU from the cluster). Use when the user asks for the project report, atlas, roadmap overview, platform HLD page, or to refresh it.
---

# zuno-project-report

Builds one self-contained HTML page (French, light/dark themes, no external data) and publishes it as a **private Artifact**.
Never commit the output: the repos are public and the page carries cluster consumption figures.

## Run

1. `oc whoami` must answer (read-only cluster access is enough). Do not touch the cluster otherwise.
2. `bash .claude/skills/zuno-project-report/scripts/generate.sh "$(git rev-parse --show-toplevel)" <scratchpad>/zuno-atlas.html`
   It prints component rows (id, pods, cpuReq, cpuUse, memReq, memUse, pvcGi, gpu) and, before them, any running pod that matches no component.
3. Publish with the Artifact tool, file path `<scratchpad>/zuno-atlas.html`, icon `map`. Re-use the same path in the same conversation to keep the URL; from a new conversation pass the existing URL (use `action: "list"` to find "Zuno Atlas").
4. Tell the user: data date, any new unmatched pods, and that component texts are hand-written (see below).

## Pipeline (scripts/)

| Step | File | Source | Output |
|---|---|---|---|
| ADR + WP | `parse_roadmap.py` | `docs/adr/README.md` (status, band, Retired table), ADR `**Date:**`, `docs/roadmap/implementation-roadmap.md` tracker, WP briefs (`**State:**`, done date) | `raw.json` |
| Cluster | `collect_cluster.sh` | thanos-querier (requests, 6 h CPU rate, working set, PVC) + `oc get pods/pvc -A -o json` | `m_*.json`, `p_*.json`, `pods.json`, `pvc.json` |
| Components | `build_comps.py` | pods grouped by `assets/components.py` selectors | `comps.json` |
| Assemble | `build_data.py` | adds git tags, commits per day, band goals, node capacity, MIG slices | `data.json` |
| HTML | `generate.sh` | injects `data.json` into `assets/template.html` at `/*DATA*/null` | final HTML |

## What to maintain by hand

- **`assets/components.py`** is the single source for the component list. Each entry: `id, name, layer, sel` (namespace regex + pod-owner-name regex, first match wins, so order matters), `pvc` selectors, `sum`, `feat[]`, `use`, `uses[]` (ids this component depends on, drives the HLD arrows), `ext[]`.
  - When `build_comps.py` lists unmatched pods in a zuno-owned namespace, add or extend a component.
  - Descriptions are written from the ADRs and ops notes, not generated. Check a claim in the repo before adding one.
  - Layers: fnd, sec, data, obs, ai, gw, exp, ops (colours fixed in the template, one per layer).
- **`goals` and `order` in `build_data.py`**: one French sentence per version band. Add a line when a new band appears in `docs/adr/README.md`.
- **`isPlanned` in `assets/template.html`**: currently `b==='v0.17'`. Update when a band starts or closes.
- **Request-flow steps** (`FLOW` in the template) mirror the governed chain Keycloak → UnifAI → AI Gateway → Kuadrant → MaaS → models → MCP gateway → MCP servers → tracing.

## Known limits

- WP → band assignment uses the first non-retired ADR cited by the WP; WPs with no ADR go to "Hors bande".
- ADR "created" curve uses the ADR `**Date:**`; WP "done" curve needs a date in the WP State line (about 220 of 261 have one).
- Used CPU is a 6 h average, memory is instantaneous. Both change from run to run.
- Fonts come from Google Fonts (the only host the Artifact CSP allows).
