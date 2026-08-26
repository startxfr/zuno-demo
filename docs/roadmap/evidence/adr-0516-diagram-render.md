# ADR-0516 diagram-render implementation evidence

Records the implementing artifacts and live state behind
[ADR-0516](../../adr/0516-generate-diagrams-with-self-hosted-mermaid-rendering.md)
(generate diagrams with self-hosted Mermaid rendering, alongside SDXL image
generation). Unlike most closeouts in this directory, **ADR-0516 had no work
package** - it landed whole in a single commit and was never surfaced as
tracked work, which is why its status stayed `Proposed` for three days after
the decision was fully in effect.

## Basis for closure

Closure initially rested on merged code plus the live, healthy deployment.
A real end-to-end render was then captured on 2026-08-26 while verifying the
egress work below, so the closure is now behavioral, not inferred.

Executed from inside the `mcp-gateway` pod against
`http://diagram-render.zuno-ai-run.svc:8080/render` - the same URL and the
same `X-Zuno-Gateway-Token` header `diagram_gen.py` itself uses:

| Run | Result |
|---|---|
| `graph TD; A[Baseline]-->B[Render];` | HTTP 200, `mime_type: image/svg+xml`, 14620 base64 bytes, node labels present in the decoded SVG |
| `graph TD; A[PostEgress]-->B[Render];` | identical: HTTP 200, `image/svg+xml`, 14620 bytes, labels present |

Checking that the labels actually appear in the decoded SVG is the part that
matters: it distinguishes a real render from Mermaid's error placeholder,
which is precisely the failure mode `93b070d` fixed.

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
| 8. Gateway token + ingress NetworkPolicy | Done as decided | `X-Zuno-Gateway-Token` validated in `server.js` (ADR-0037 pattern); `gitops/charts/diagram-render/templates/networkpolicy.yaml` restricts ingress to `mcp-gateway`. Egress remains unrestricted, as the ADR accepted - an attempt to close it was reverted, see below. |

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

## Egress NetworkPolicy (attempted, reverted, still open)

ADR-0516 accepted, as non-blocking, that only ingress was restricted:
LLM-authored Mermaid is unvalidated text run through a real browser engine,
and Mermaid can reference external image URLs, so the render was an SSRF
vector able to reach anything the pod network could reach.

Attempted 2026-08-26 (commits `56319f8`, `0368e35`) and **reverted the same
day**. The reasoning still holds - the application needs no egress at all, it
renders a local file to a local file - but an allowlist of cluster DNS plus
the `zuno-mesh` control plane is not sufficient for the **istio sidecar** to
bootstrap, and what else it requires was not determined.

### How it was proven

An A/B pair of pods built from the same `diagram-render` image in the same
namespace, differing only by label:

| Pod | `app.kubernetes.io/name` | Selected by the policy | Result |
|---|---|---|---|
| `netpol-ab-unselected` | `netpol-ab-control` | no | Running, Ready |
| `netpol-ab-selected` | `diagram-render` | yes | hung in `PodInitializing`; istio-proxy startup probe refused on `:15021` |

DNS also stayed blocked from a selected pod even with a port-only UDP/TCP 53
rule carrying no `to` peer at all - the standard pattern, which should have
worked. That part is still unexplained. The cluster is `OVNKubernetes`, so
egress rules are genuinely supported; the allowlist is simply incomplete.

### Two verification traps, both hit

1. **A TCP probe cannot verify egress from a mesh-injected pod.** istio's
   `includeOutboundIPRanges: "*"` terminates outbound TCP at the sidecar, so
   `connect()` succeeds locally whether or not the packet could ever reach the
   real destination. Two probes reported ALLOWED against destinations that
   were not in fact reachable, which pointed the investigation the wrong way.
   UDP is not captured, so only a UDP query - or a real end-to-end call -
   tells the truth.
2. **Pod readiness after `oc apply` proves nothing.** The live pod stayed
   `2/2` Ready throughout, because it had started hours before the policy and
   its sidecar was already bootstrapped. This is a delayed-fuse failure: it
   would have surfaced on the pod's next restart, in whatever unrelated
   context that happened. Only a pod that *starts* under the policy tests
   bootstrap - hence the A/B method above, which tests it without restarting
   the real workload.

### Where it stands

The risk is back to exactly what ADR-0516 accepted: ingress restricted to
`mcp-gateway`, egress unrestricted, no credential on the service, blast radius
contained to its own pod. Anyone resuming this should start from the A/B pod
method rather than from a fresh guess at the allowlist.

## Open items

- **The egress `NetworkPolicy` is still not written** - see the section
  above for what was tried, what it broke, and how to resume.

## Related closeout changes

The `components/mcp-servers/lucidchart` placeholder README - the diagram
integration this decision supersedes - was deleted in this closeout, together
with the "Lucidchart integration planned" claims it had left behind in
`MEMORY.md`, `agents/arkos/README.md`,
`agents/arkos/tasks/draft-architecture-testimonial.md`,
`docs/architecture/logical-architecture.md`,
`components/mcp-servers/README.md` and `components/mcp-gateway/README.md`.
