# ADR-0408: a user who loses a source group stops retrieving its content (live proof, 2026-11-11)

The one open item of the [ADR-0408 stub](../adr-decisions-v0.4.md#adr-0408-automate-removal-of-inaccessible-private-rag-content):
remove a persona from a group that gates a RAG source, query as that persona, get nothing. Run on demo333 with the
user's go, by session zuno-avancement.

## Setup

- **Persona:** `stress-consultant-01`. It is not used by the golden path or the demonstration, and it belongs to the three
  groups that gate the `tekos-satellite` Confluence source (`aclGroups` in `ansible/clusters/demo333.yml`):
  `consultant/confluence-archi-satellite`, `-build-satellite` and `-run-satellite`.
- **Query path:** UnifAI RAG `GET /api/sources/query.bearer` (the path the agents' retrieval uses), with the persona's own
  token from the `zuno-evaluations` client, `sourceType=CONFLUENCE`, `tags=knowledge.tech`, `top_k_results=10`. The service
  was reached through `oc port-forward svc/unifai-rag-server`.
- **Questions:** "Satellite capsule installation and content synchronisation" (Satellite content), and a control,
  "OpenShift cluster installation and day 2 operations" (the `tekos-openshift` source, whose groups were not touched).
- A match is counted as Satellite when its `metadata.source_id` is the `tekos-satellite` source (`f3a799df177ed7a46ab04bd7`).

## Result

| Step (UTC) | Satellite groups in the token | Satellite question: Satellite chunks | Control: Satellite chunks / others |
|---|---|---|---|
| 14:30:00, baseline | 3 | 10 of 10 | 0 / 10 |
| 14:30:31, persona removed from the three groups (kcadm) | | | |
| 14:30:53, new token | 0 | **0 of 10** (the 10 matches come from other sources) | 0 / 10 |
| 14:30:55, persona added back to the three groups | | | |
| 14:31:18, new token | 3 | 10 of 10 | 0 / 10 |

Every query answered HTTP 200. The filter applies at query time, from the groups of the caller's token: the content
stopped being returned on the first query after the change, without removing any embedding, and came back once the
groups were restored. The persona ends with the same groups it started with.

## Limits

- The proof uses a new token after each change. A token issued before the removal keeps its groups until it expires
  (Keycloak access-token lifetime), which is the expected behaviour of a token-based filter.
- Pages deleted at their source are removed at the next incremental sync (WP-149); that path was not exercised here.
