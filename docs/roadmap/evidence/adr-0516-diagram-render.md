# ADR-0516 diagram-render implementation evidence

Records the implementing artifacts and live state behind
[ADR-0516](../../adr/0516-generate-diagrams-with-self-hosted-mermaid-rendering.md)
(generate diagrams with self-hosted Mermaid rendering, alongside SDXL image
generation). Unlike most closeouts in this directory, **ADR-0516 had no work
package** - it landed whole in a single commit and was never surfaced as
tracked work, which is why its status stayed `Proposed` for three days after
the decision was fully in effect.

## Basis for closure

Closure rests on **merged code plus the live, healthy deployment** - not on a
fresh end-to-end `generate_diagram` call captured here as a transcript. That
was a deliberate call at closeout time (2026-08-26). The strongest behavioral
evidence on record is indirect but real: commit `93b070d` fixed a defect that
could only have been found by driving the path for real.

## Outcome summary

All eight decision items are in effect as written; nothing was descoped.
Agents write Mermaid directly, an in-cluster Node.js/headless-Chromium service
renders it, and the result comes back as `image/svg+xml` through the existing
`generated_images` artifact shape - no external API, no credential, and no
diagram content leaving the cluster. Tekos received the deliberate carve-out:
it can render diagrams but still never declares `image.generation.create`.

## Per-item evidence against the ADR's decision items

| ADR item | Outcome | Evidence / notes |
|---|---|---|
| 1. `generate_diagram` alongside `generate_image` | Done | Tool schema and description in `components/agent-runtime/app/graph/nodes.py` (~L196-240); both descriptions point at each other. |
| 2. LLM writes `mermaid_source` directly | Done | Single tool argument, no second internal LLM translation call. `"Write the complete diagram definition, not a description of one."` |
| 3. Self-hosted in-cluster rendering | Done | `components/diagram-render/server.js` (`@mermaid-js/mermaid-cli` ^11.4.2 + distro Chromium), reached by `components/mcp-gateway/app/handlers/diagram_gen.py` mirroring `image_gen.py`. Default endpoint `http://diagram-render.zuno-ai-run.svc:8080`. |
| 4. `min_classification: C1` | Done | `policies/tools/tool-policy.yaml` (`diagram.generation.create`, `mcp_server: diagram-gen`) - C1, not `generate_image`'s C2, exactly as argued. |
| 5. `image/svg+xml`, not PNG | Done | `server.js` renders with `outputFormat: "svg"` and returns `{"data_base64", "mime_type": "image/svg+xml"}`. |
| 6. Reuses the `generated_images` shape | Done | Same `data_base64`/`mime_type`/`alt` artifact; zero `components/agent-frontend` changes in either commit. |
| 7. Scope Arkos + Comage + Tekos, Tekos diagrams only | Done | `diagram.generation.create` granted in `agents/{arkos,comage,tekos}/agent.okf.md` and the corresponding `tasks/*.md`. The three Tekos boundary checks now assert the narrower guarantee: `evaluations/tekos/stress_test.py` (`image_generation_boundary`, `"no image/png ever" (not "images == []")`), `security_checks.py` (svg-allowed / png-never), `gate_checks.py` (`tekos_declares_no_dat_or_image_generation_capability`). Tekos still never declares `image.generation.create`. |
| 8. Gateway token + ingress NetworkPolicy | Done for ingress | `X-Zuno-Gateway-Token` validated in `server.js` (ADR-0037 pattern); `gitops/charts/diagram-render/templates/networkpolicy.yaml` restricts ingress to `mcp-gateway`. Egress is **not** restricted - see Open items. |

## The render-failure defect (`93b070d`)

**Mermaid never throws on invalid syntax.** It draws an error placeholder into
the SVG and exits successfully. Before the fix, an LLM-authored diagram with a
syntax error produced a clean HTTP 200 carrying a picture of an error message,
which the model then presented to the user as a finished diagram.

`findRenderIssue()` in `components/diagram-render/server.js` now inspects the
rendered SVG's content and fails the request instead. It is the only place in
the whole chain that looks at render *output* rather than exit status, and it
is what makes the one-shot self-correction retry in
`components/agent-runtime/app/graph/nodes.py` reachable at all. The companion
`_summarize_rendered_svg()` parses `aria-roledescription` and `<text>`/`<tspan>`
labels back out of the SVG so the model's follow-up prose is grounded in what
was actually drawn.

## Live state (2026-08-26, `demo222.startx.fr`)

```
$ oc get deploy,pod -n zuno-ai-run -l app.kubernetes.io/name=diagram-render
deployment.apps/diagram-render   1/1   1   1   35h
pod/diagram-render-54989c4dc4-x2w98   2/2   Running   0   4h28m

$ oc get applications.argoproj.io -A | grep diagram
openshift-gitops   zuno-diagram-render-d0   Synced   Healthy
openshift-gitops   zuno-diagram-render-d1   Synced   Healthy
```

The `2/2` pod confirms the istio sidecar is injected, and the restricted-SCC
Chromium friction flagged as an accepted risk in the ADR did not materialize:
the `--no-sandbox --disable-setuid-sandbox --disable-dev-shm-usage` flags plus
the writable `/tmp` `emptyDir` are sufficient, with zero restarts.

Build/deploy wiring is complete on both paths: `.github/workflows/
build-publish.yml` (matrix entry `diagram-render`) and the in-cluster
BuildConfig via `ansible/roles/mcp_build/tasks/build.yml`, installed by
`ansible/roles/mcp/tasks/install.yml` under `make day2 install mcp`.

## Open items

- **Egress `NetworkPolicy` for `diagram-render` is still not written.** Only
  ingress is restricted. Mermaid can reference external image URLs, so a real
  browser engine rendering unvalidated LLM-authored text is an SSRF vector.
  The ADR accepted this explicitly as non-blocking - the service holds no
  credential and the blast radius is its own pod - and that assessment is
  unchanged at closeout. This remains the one genuine follow-up.
- **No fresh end-to-end live run** was captured for this closeout (see Basis
  for closure above).

## Related closeout changes

The `components/mcp-servers/lucidchart` placeholder README - the diagram
integration this decision supersedes - was deleted in this closeout, together
with the "Lucidchart integration planned" claims it had left behind in
`MEMORY.md`, `agents/arkos/README.md`,
`agents/arkos/tasks/draft-architecture-testimonial.md`,
`docs/architecture/logical-architecture.md`,
`components/mcp-servers/README.md` and `components/mcp-gateway/README.md`.
