# WP-185 step 1: the live bundles no longer declare knowledge.sxa-legacy

Read on demo333 on 2026-11-02, after the agents release v0.9.0 was promoted (`0dbbb190`) and repinned by zuno-demo-59. Read-only: `oc get unifaiagentbundle`, nothing changed.

| Bundle | Phase | Release | Tasks served | Knowledge domains (ceiling) | Mentions `sxa-legacy` |
|---|---|---|---|---|---|
| comage | Ready | v0.9.0 | check-deal-status, update-opportunity-status, check-my-drive-and-mail | knowledge.project, knowledge.sales | no |
| tekos | Ready | v0.8.1 | answer-technical-question, find-relevant-docs, check-my-drive-docs, write-code | knowledge.project, knowledge.tech | no |
| arkos | Ready | v0.8.1 | draft-architecture-testimonial, workshop-presentation, structure-demo, write-code | knowledge.project, knowledge.tech | no |
| advantage | Pending (placeholder) | v0.9.0 | none served | knowledge.adv, knowledge.project | no |
| finage | Pending (placeholder) | v0.9.0 | none served | knowledge.project | no |
| cognos | Pending (placeholder) | v0.9.0 | none served | none | no |
| naveo | Pending (placeholder) | v0.8.1 | none served | knowledge.project, knowledge.tech | no |
| soursage | Pending (placeholder) | v0.6.2 | none served | none | no |

Before the repin, comage's bundle (v0.6.2) listed `compare-historical-deals` (workflow `comage-compare-historical-deals`) and its ceiling held `knowledge.sxa-legacy`: the one live bundle where a question could fall back
silently to unrelated pages. That task and that domain are gone from it. No live bundle names the domain.

Not done: a real question to comage on demo333 (the historical-deals question of the brief). It needs the local models and the embedding model, down since 2026-11-02 09:38Z when both GPU nodes
stopped reporting (`node.cloudprovider.kubernetes.io/shutdown`). advantage, cognos and finage are placeholders that no bundle serves, so no live question can be asked to them.
