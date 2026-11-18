# WP-249 row 8: UnifAI v0.1.69 pinned, its stack images rolled back to v0.1.68 and forward (2026-11-12)

The test ran live on demo333 with the user's go, by session zuno-avancement. The window ran from 16:44 to 17:07 UTC and
was announced to unifai-main, zuno-main and zuno-demo.

## The release

unifai-main cut v0.1.69 early, at the user's request in that session:
- the tag is on `b9d8dedad`, channel alpha, with the release.json of the GitHub release;
- cosign verified 8 of 8;
- unifai-main's e2e and canary were green on these application images.

It contains three changes:
- R-536: a revoked or retired agent keeps its group team, which is the fix ADR-0584 waited for;
- R-551: an optional `source_merge` in the docs_rag retriever config;
- upstream #279: rework of resource deletion.

The dry runs of `pin_operator_catalog.py` and `pin_unifai_images.py` gave the digests unifai-main announced:
- catalog `cae636ce`, operator `9b962ffa`, bundle `4a122fb1`;
- backend `accc1561`, identity `0ee33573`, multiagent `d31e160d`, rag `e310b780`, ui `0be43d74`.

## Steps

| UTC | Step | Result |
|---|---|---|
| 16:44 | baseline; `make d3 backup unifai` | operator 0.1.68; 7 Deployments on the v0.1.68 digests; backup exit 0 |
| 16:46 | f93a111d (catalog pin), 305bedf1 (image pin) pushed; `make d2 install unifai` | exit 0 at 16:48, before OLM finished |
| 16:48-16:51 | OLM and the roll | CSV 0.1.69 `Succeeded` at 16:49 (0.1.68 `Replacing`, then gone); the 7 Deployments on the five 0.1.69 digests at 16:51 |
| 16:51-16:52 | golden path | RESULT PASS, 14 moments (world model as roadmap); `unifai-tekos` deleted its test session |
| 16:53 | known-good `unifai-operator 0.1.69` (7c98ece0); `source_merge` check in MongoDB (`UnifAI.resources`, `blueprints`, `builtin_resource_descriptors`) | 0 documents mention `source_merge`, so the 0.1.68 images reject no retriever |
| 16:54 | **rollback**: 76d2ffa1, the stack images pinned back to v0.1.68 (`pin_unifai_images.py v0.1.68`); `make d2 install unifai` | exit 0; the operator stays 0.1.69 (OLM never downgrades) |
| 16:57-16:58 | the roll | the 7 Deployments on the v0.1.68 digests (`2d628513`, `b77cc554`, `87657395`, `919982f7`, `f214c180`), all ready |
| 16:59-17:00 | golden path | RESULT PASS, 14 moments |
| 17:00 | **forward**: f33adf55, `git revert` of 76d2ffa1; `make d2 install unifai` | exit 0 |
| 17:05 | the roll | back on the five 0.1.69 digests, all ready |
| 17:05-17:07 | golden path | RESULT PASS, 14 moments; CSV `unifai-operator.v0.1.69` |

## Findings

- **The written rollback works both ways** under the newer operator:
  - pin the previous release's stack images, commit, `make d2 install unifai`;
  - each roll takes 3 to 4 minutes after `make` returns, so watch the Deployments' images, not the exit code.
- **The data stayed compatible**: 0.1.68 to 0.1.69 changes no stored shape. The one risk unifai-main named, a
  `source_merge` field that 0.1.68 would refuse, was checked absent before the rollback. No docs_rag retriever was
  edited during the window.
- **Not covered:** the #279 cascade-deletion paths beyond a session delete, and the R-536 revocation path. A
  revocation retest on demo333 is optional (own go).
