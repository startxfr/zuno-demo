# WP-280: Compose the workshops from scenario steps

- **State:** Operator pending
- **ADRs:** [ADR-0616](../../adr/0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md)
- **Depends on:** [WP-275](wp-275-move-the-experience-demos-to-the-lifecycle.md), [WP-276](wp-276-move-the-governance-demos-to-the-lifecycle.md), [WP-277](wp-277-move-the-rhoai-demos-to-the-lifecycle.md), [WP-278](wp-278-move-the-foundation-demos-to-the-lifecycle.md), [WP-279](wp-279-move-the-blender-and-world-model-demos-to-the-lifecycle.md)
- **Related:** [WP-271](wp-271-scaffold-every-demo-directory-and-the-catalogue-check.md), [WP-281](wp-281-rehearse-every-demo-and-workshop-end-to-end.md)
- **Target:** v0.16
- **Estimated files touched:** ~40: six workshop pages, their directories, `docs/demo/_template-workshop.md`, the catalogue test

> Why: ADR-0616 clause 10. A workshop is a sequence of scenario steps plus a few rows of its own; composing it from the
> scenario files keeps one source per step.

## Goal

`make demo use <workshop-id>` and the same verbs play each of the six workshops, with their actions chained from their
scenarios and their steps flattened in agenda order.

## Steps

1. For each workshop (`three-experiences`, `five-experiences`, `sovereign-governed-ai`, `agentic-ai`,
   `rhoai-end-to-end`, `trusted-platform-ops`), write the `agenda:` of `ansible/demos/<id>/demo.yml` from the page's
   Agenda table: `{at, own: true}` for the opening, the transitions and the close; `{at, scenario, version}` for a linked
   scenario, with `only: [<times>]` when the page plays named rows (`sovereign-governed-ai` plays rows 10:30 and 12:30 of
   the sovereignty 15-minute version); `{at, inline: <slug>}` for a section of the workshop page holding its own
   `Time | Do | Say` table (`## One platform behind the three`, `## Same rules, one dashboard`).
2. Own and inline rows get their step files under the workshop directory (`steps/agenda-H-MM.yml`,
   `steps/agenda-H-MM--MM-SS.yml`).
3. Chain the actions in the engine: status, check, install and start over the distinct scenarios in agenda order, stop
   and uninstall in reverse, then the workshop's own action file; one merged golden-path run and one merged browser run;
   one guard for the workshop (`DEMO_CONFIRM=<workshop-id>`).
4. Replace each workshop's `## Before you start` by `## Presenter lifecycle`, which names what its scenarios' sections
   already cover and adds only what is the workshop's own; add the section to `_template-workshop.md`.
5. Extend the catalogue test: every agenda entry matches the Agenda row with the same time (link stem and
   `#5-minute-version` / `#15-minute-version` anchor), every `only` time exists in the scenario, every `inline` slug is a
   section with a timed table.
6. Rehearse each workshop: `make demo rehearse <workshop-id>`, with the owner's named go when one of its scenarios has a
   changing unit. The 90-minute variant of `rhoai-end-to-end` is out of scope; its page says so.

## Acceptance

- The catalogue test passes for the six agendas.
- Each workshop has a rehearsal report ending with `RESULT: PASS`, or failures its page explains.
