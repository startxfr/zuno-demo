# ADR-0575: Upstream generic UnifAI changes and isolate zuno-specific code

- **Status:** Accepted
- **Target:** v0.11
- **Date:** 2026-10-17
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0561](0561-adopt-unifai-as-the-agent-platform.md), [ADR-0562](0562-authenticate-unifai-against-the-zuno-keycloak-realm.md), [ADR-0563](0563-forward-caller-identity-and-zuno-context-headers-from-unifai.md), [ADR-0564](0564-deliver-okf-bundles-to-unifai-operator-as-signed-oci-artifacts.md), [ADR-0566](0566-instrument-unifai-with-opentelemetry.md), [ADR-0568](0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md), [ADR-0569](0569-close-unifai-parity-gaps-generically.md), [ADR-0574](0574-deploy-unifai-through-argocd-from-a-pinned-olm-catalog.md)

## Context

ADR-0561 adopts UnifAI from the fork `startxfr/UnifAI` (local checkout
`startx-unifai`, branch `devel`), whose upstream is
`redhat-community-ai-tools/UnifAI` (Apache License 2.0). The UnifAI ADRs of
this release add a large amount of code to it: identity forwarding and
context headers (ADR-0563), an OIDC-claims directory provider (ADR-0562),
OpenTelemetry in three services (ADR-0566), hybrid search, ACL filtering,
four source connectors and backup (ADR-0568), project memory and routing
metadata in the UI (ADR-0569), and OKF bundle handling in the operator
(ADR-0564).

The fork already has a branch model and guard rails (`fork/README.md`,
`MEMORY.md`):

- `main` mirrors `upstream/main`, fast-forward only, with no own commits;
- `devel` is `main` plus the fork delta, receives `main` by merge, and is
  what is built, tagged and deployed;
- features start from `main` (`make feature-start`), are merged into
  `devel` to test (`make feature-to-devel`), and may go upstream
  (`make contrib-*`);
- fork-only paths (`fork/fork-only-paths`: `Makefile`, `fork.mk`,
  `fork.mk.example`, `MEMORY.md`, `fork/`, `.fork/`) are refused on every
  branch but `devel` by the `guard-fork-only` hook, and `fork/contrib-check.sh`
  rejects them in a contribution and reproduces upstream's review rules
  (ruff, gitleaks, no added `TODO`/bare `except`, Conventional Commits);
- pushes to `origin` and `upstream` are disabled until explicitly decided.

Today the delta outside `fork/` is small: `git diff --name-only main devel`
lists `MEMORY.md`, `Makefile`, `fork.mk.example` and one upstream file,
`multi-agent/Dockerfile` (the optional corporate CA fix, branch
`fix/multiagent-optional-corp-ca`, the first upstream candidate). The
operator, about 41,000 added lines, lives entirely under
`fork/unifai-operator`. Upstream was last merged into `main` on
2026-10-15 and moves actively.

Upstream has no CONTRIBUTING file, takes PRs from in-repo branches, and gates
them with a CodeRabbit and Cursor review pipeline that needs secrets a fork
does not get (`MEMORY.md`). The fork's open TODO list states twice that the
maintainers (`.github/CODEOWNERS`) must be contacted before the first PR.

Every line of delta in an upstream path is a potential conflict on each
`main` merge into `devel`. The work above, kept as fork delta, would turn
each upstream sync into a manual merge across services.

## Decision

**Every change is classified before it is written: generic or
zuno-specific.** A change is generic when it has a use for any UnifAI user
and names no zuno concept. Identity forwarding, templated headers, OTel,
hybrid search, ACL filtering, the Confluence/git/web/SQL-dump connectors,
the OIDC-claims directory provider, project memory and response-metadata
display are generic. OKF parsing, the `X-Zuno-*` header names as defaults,
the `zuno.*` attribute names, classification semantics and any adapter to a
zuno service are zuno-specific.

**Generic changes are built for upstream from the start.** Each is a
feature branch from `main`, one concern per branch, passing
`make contrib-check`, with tests, type hints and Conventional Commits, merged
into `devel` for use and proposed upstream when ready. Names, configuration
keys and defaults are neutral: a header template is configuration whose
zuno values live in zuno's charts, and an attribute is `unifai.run_id`, not
`zuno.run_id` (ADR-0566 maps it in the collector).

**Upstream is contacted before the first PR**, through the CODEOWNERS, with
the first, smallest candidate (`fix/multiagent-optional-corp-ca`). The
larger items (OTel, identity forwarding, hybrid search) are announced as
design proposals before code is submitted, so that their shape can follow
the maintainers' preferences rather than be rewritten after review.
Opening a PR, and enabling the push URL it needs, remains an explicit user
decision each time, as the fork's guard rails already require.

**Zuno-specific code never enters an upstream path.** It lives under
`fork/` (the operator, and OKF handling in `fork/unifai-operator/internal/okf/`
per ADR-0564), or in zuno's own repository (charts, values, collector
processors, binding data). Where a zuno need cannot be met by configuration
of a generic feature, the generic feature gains an extension point rather
than a zuno branch inside it.

**The operator stays fork-only.** Upstream deploys with helmfile, and the
operator embeds those charts unchanged (`internal/stack/assets`, refreshed by
`make charts`, never edited). Offering it upstream is a separate
conversation with the maintainers, not a prerequisite of any work package.

**The branch model is unchanged and binding:** `main` mirrors upstream,
`devel` is `main` plus delta, releases are tagged on `devel`, and zuno
deploys only tagged `devel` releases (ADR-0574).

## Consequences

If upstream accepts the generic changes, the fork's long-term delta shrinks
to `fork/` and a rebase or merge of `main` stays mechanical. If it accepts
none, the cost is the same code carried as delta, but split into
single-concern branches that can each be re-applied, which is still cheaper
than one fused patch set.

Writing for upstream costs more per change: neutral naming, configuration
surfaces, tests and review cycles on a schedule zuno does not control.
Zuno's work packages therefore never wait on an upstream merge; they use the
change from `devel` as soon as it is merged there.

The classification rule moves some logic out of UnifAI and into zuno's
deployment (header values, attribute mapping), which is where cluster
policy belongs anyway.

## Security considerations

`contrib-check.sh` runs gitleaks on every contribution and refuses fork-only
paths, so secrets, `fork.mk` and `.fork/secrets.env` content cannot leave
through a PR. Nothing internal to zuno (realm names, hostnames, Confluence
space keys, classification policy) belongs in an upstream change; review of
each branch checks for it before the push URL is enabled.

Security-relevant generic features (identity forwarding, ACL filtering)
receive more upstream scrutiny than fork-only code would, which is a benefit.
Until merged upstream, their review is zuno's own.

## Operational considerations

Each `main` sync into `devel` is followed by the operator's `make charts`
and `make test`, so a chart change upstream is caught by the operator's
render tests before a release is tagged.

The fork records each generic branch's upstream state (proposed, open PR,
merged, declined) in its `MEMORY.md`, so a declined change is known to be
permanent delta.

No step of this decision touches a cluster.
