# WP-187: the source classification on demo333 (2026-11-03)

Measured on the live Qdrant of the `zuno-unifai` namespace, after operator 0.1.50 and the five application images at
`devel-042c793d1` (rag `sha256:3fc8df7f…`) were rolled and every source was embedded again.

## Roll, in order

| Step | Commit / action | Result |
|---|---|---|
| Operator catalog 0.1.50 | `bd0fd5df` (zuno-demo-da), `make d2 install unifai` | CSV `unifai-operator.v0.1.50` Succeeded |
| Five images to `devel-042c793d1` | `fec63456`, `make d2 install unifai` (local mode) | all UnifAI deployments on the new digests, stack Ready |
| `classification` on the sources | `b1629fc6`, second `make d2 install unifai`, ArgoCD sync of `zuno-unifai-d1` | 24 sources Ready after the re-embed |

The first `make d2 install unifai` went through AAP and failed (job 1284, `status=failed`, detail not read); the same make target run locally
(`zuno_make_aap_mode: local`) succeeded. The old `unifai-devel` namespace holds a stale stack that is not part of this roll.

## Chunks (payload key `metadata.classification`)

| Collection | Chunks | C1 | C2 | No label |
|---|---|---|---|---|
| `confluence_data_hybrid` | 501 | 0 | 501 | 0 |
| `web_data_hybrid` | 15,687 | 15,663 | 0 | 24 |

The 24 chunks without a label are the `sales-demo` source, which is left unclassified; the mcp-gateway returns C2 for them
(`4b7349b6`). The 21 Red Hat documentation sources are C1 and the two Confluence sources (`tekos-satellite` 90 pages,
`tekos-openshift` 411 pages) are C2. The two Red Hat sources that were `Failed` since 2026-11-02 synced again with the change.

## Live check through the mcp-gateway (session zuno-demo 40, about 09:16 to 09:18 UTC)

Run as the OpenClaw persona `consultant-02` through its egress proxy; mcp-gateway with agents v0.10.0 and the marker key, ai-gateway build 38.

| Check | Result |
|---|---|
| `tools/list` | `consultant-02` sees 6 tools (drive, gmail, diagram, `confluence.page.search`, `confluence.page.read`, `knowledge.tech.search`); `sale-01` sees only the 3 C1 tools |
| `confluence.page.search "onboarding"` | real SXSI pages, marker `level=C2 external=0`, signature verified by the ai-gateway |
| ai-gateway on that turn | "classification raised by tool results: C1 -> C2, local_only False -> True (marker C2, marker external=0)", client `openclaw-consultant-02` |
| Forged marker (rewritten to C1, external=1) | signature fails, counted as unmarked: C2, local |
| `knowledge.tech.search` | **401** from the rag-server `query.bearer` endpoint: "Bearer token rejected: Audience doesn't match" |

## Per-chunk label through `knowledge.tech.search` (about 09:50 UTC)

The 401 was an audience mismatch: the OpenClaw clients' tokens lacked the `zuno-admin-api` audience the rag-server `query.bearer` endpoint checks.
Commit `325f9c28` adds the audience mapper to the `openclaw-consultant-02` and `openclaw-sale-01` clients (the Keycloak client reconcile Job
updated both). As `consultant-02` through its proxy, `knowledge.tech.search "How do I configure a MachineSet autoscaler in OpenShift?"` returns five results:

| Result | Source | Classification |
|---|---|---|
| 3 | Confluence SXSI pages O0B45-SUCIN, O0B42-PRCIN, O0B45-EXCIN | C2 |
| 2 | "Machine management \| OpenShift Container Platform 4.22 \| Red Hat Documentation" | C1 |

The mcp-gateway marker on that result is `level=C2 external=0`: the highest chunk level, which the ai-gateway then applies to the turn.
No turn is raised by the RAG itself; the raise happens in the ai-gateway from the signed marker (WP-191, ADR-0594).
