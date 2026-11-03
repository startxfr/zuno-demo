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

## The live question to comage (2026-11-03, agents release v0.9.2, GPU nodes and embedding back)

One question as `sale-01` (copied as its evaluation twin), team `agent-comage`, from a probe pod that was deleted afterwards:
"Peux-tu comparer cette opportunité avec nos affaires historiques d'avant 2021 ? Donne-moi les montants et les durées des affaires comparables."

| Field | Value |
|---|---|
| HTTP status, duration | 200, 3.3 s |
| Routing | `local-wesh-maas`, model `qwen3.5-9b-wesh`, local, classification C2, no fallback |
| Reply | "Ce type de recherche demande une lecture de Salesforce, pas un corpus indexé. J'ai pas le historique d'avant 2021 dans le contexte fourni." |

Reading: the agent no longer falls back to unrelated pages. It says the pre-2021 history is not in its context and points to Salesforce. (The probe's own flag
`MENTIONS_SXA_OR_HISTORY_AS_AVAILABLE` matched the word "historique" inside this refusal; it is a false positive of the keyword test, not a claim that the record is available.)
The reply is not a formal "domain unavailable" message, only the model's own wording: the task is removed, so no task text states it.

advantage, cognos and finage are placeholders that no bundle serves, so no live question can be asked to them. They were `Pending` again after the v0.9.2 roll (the same placeholders).
