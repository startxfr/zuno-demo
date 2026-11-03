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

## Still to prove

A question through the mcp-gateway search tool shows C2 for Confluence and C1 for Red Hat documentation (audit label and marker level):
owned by the session that built the mcp-gateway change. Result to be added here.
