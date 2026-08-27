# ADR-0527: Introduce the project as the sharing and context boundary

- **Status:** Proposed
- **Target:** v0.4
- **Date:** 2026-08-27
- **Decision owners:** Zuno Demo architecture team
- **Supersedes:** [ADR-0213](0213-introduce-role-based-conversation-sharing.md) in full — conversation-level sharing (`conversation_memberships`, the reader/actor/cloner vocabulary, the five per-conversation membership endpoints, `ShareDialog.tsx`) is replaced by project-level sharing, not merely re-scoped. ADR-0213's single-active-writer lease is the one clause that survives, restated below. Extends [ADR-0209](0209-introduce-project-scoped-agent-memory.md) (its `project_id` stops being client-asserted) and [ADR-0212](0212-introduce-persistent-navigable-chat-conversations.md) (its conversation list stops being filtered on `owner_sub` alone).

## Context

Three unrelated notions of "project" exist in this repository today and none of
them is an object a user can create.

ADR-0209 introduced `project_id` as a *mandatory metadata key* on the
`knowledge.project` domain, guarded by a deliberately binary
`project_memberships` table (`data/rag/schema/005_project_memory.sql`) in the
`rag-project` database. That table is data, not identity infrastructure, for a
reason the present decision inherits verbatim: the Keycloak realm
(`gitops/charts/keycloak/files/realm-zuno.json`) is static and GitOps-provisioned
while engagements are created ad hoc. But nothing ever *creates* a project - the
id enters the system only because a caller asserted it in a chat request
(`components/agent-bff/main.go`'s `project_id` passthrough, forwarded as-is with
an explicit "this BFF does not validate project membership" comment).

ADR-0212 made conversations persistent, listable and single-owner. ADR-0213 then
attached sharing to that object: `conversation_memberships` with three additive
roles, a subject-only ACL with no group dimension, a Keycloak Admin API
colleague lookup, and a per-conversation share dialog. Its repo work merged
(WP-066) but it was never provisioned - `GET /api/colleagues` is a hard 503
until an operator creates the `zuno-admin-api` confidential client, so no
sharing row has ever existed in service. Its own Decision text names
`project_memberships` as the structural precedent it adapted, and notes that
precedent is binary where it needed a role column.

ADR-0512 added a third meaning: for a task marked `zuno.project_required`, a
**Salesforce opportunity id** is verified at conversation start and becomes
`conversations.project_id`, which then flows to the ADR-0511 quota ledger as
`X-Zuno-Project-Id`. The engagement's identity and its Salesforce record are
thereby conflated, and only Salesforce-backed work can carry a project at all.

The result is that the platform's most natural unit of collaboration - "this
client engagement, its briefing, its people and its conversations" - has no
representation. Sharing is per-conversation and cannot address a team. Durable
project memory is gated by a membership table nobody can populate through an
API. And a piece of work that is not a Salesforce opportunity cannot be a
project at all.

## Decision

Introduce a **project**: a first-class, server-created object that is
simultaneously the authorization boundary for sharing, the scope of durable
memory, and the carrier of an engagement's standing context.

### 1. The project is the source of truth for `project_id`

A new `projects` table in the existing `agent-conversations` database (ADR-0212's
dedicated database, whose schema `components/agent-runtime/app/conversations.py`
already applies idempotently at startup) mints and owns every `project_id`.
`conversations.project_id` gains a real foreign key to it and stops being a
client-asserted string: on a brand-new conversation the runtime resolves the
requested project against the caller's own grants before recording it, and on
resume the field is ignored entirely, logged on mismatch.

```sql
CREATE TABLE IF NOT EXISTS projects (
    project_id                text        PRIMARY KEY,
    title                     text        NOT NULL,
    context                   text        NOT NULL DEFAULT '',
    classification            text        NOT NULL DEFAULT 'C2'
                                          CHECK (classification IN ('C1','C2','C3')),
    salesforce_opportunity_id text,
    salesforce_verified_at    timestamptz,
    grants_revision           bigint      NOT NULL DEFAULT 1,
    created_by                text        NOT NULL,
    created_at                timestamptz NOT NULL DEFAULT now(),
    updated_at                timestamptz NOT NULL DEFAULT now(),
    archived_at               timestamptz,
    CONSTRAINT ck_projects_context_length CHECK (char_length(context) <= 54000),
    CONSTRAINT ck_projects_salesforce_pair
        CHECK ((salesforce_opportunity_id IS NULL) = (salesforce_verified_at IS NULL))
);
```

`project_id` is a server-minted UUID, never the Salesforce id: the project id is
emitted in `X-Zuno-Project-Id` and in traces (ADR-0528), and no Salesforce
identifier may leave the database that way.

The database choice is deliberate. Every hot-path read - the conversation list,
the per-request access check, the cascade archive - is a join of `conversations`
against the project and its grants, which PostgreSQL can only do inside one
database; and agent-runtime holds exactly one conversations credential and
deliberately no `rag-project` credential (see
`components/agent-runtime/app/clients/project_memory_client.py`'s module
docstring, which records that rag-service, not this runtime, holds the
`knowledge.project` credential).

### 2. Four roles, granted to a subject or to a business-role group

```sql
CREATE TABLE IF NOT EXISTS project_grants (
    id          bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id  text        NOT NULL REFERENCES projects(project_id),
    subject     text,
    group_name  text,
    role        text        NOT NULL CHECK (role IN ('read','clone','write','admin')),
    granted_by  text        NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_project_grants_subject_xor_group
        CHECK ((subject IS NULL) <> (group_name IS NULL))
);
```

- **read** - view the project and read its conversations; cannot send messages.
- **clone** - read, plus copy a conversation into a new one the cloner owns.
- **write** - read and clone, plus send messages and edit the project's title
  and context.
- **admin** - write, plus manage grants, edit the Salesforce link, and delete
  the project.

The four roles form a **total order**, `read < clone < write < admin`: cloning
exposes nothing a reader cannot already see (the cloner has the whole
transcript by definition), so making it a rung rather than a sibling capability
keeps "the caller's effective role is the strongest grant that matches them"
well-defined when a direct grant and a group grant disagree. Effective role is
resolved in a single indexed query matching `subject` or any of the caller's
groups; **no match is a denial**, never a default.

Grants target either a Keycloak subject or a **business-role group** (`sales`,
`sales_admin`, `consultant`, `adv`, `finance`, `board`). Agent-entitlement
groups (`agent_*`) are rejected on both the grant and the resolution side:
ADR-0040 makes them the answer to "which agent may this person open at all",
and admitting them here would turn "shared with the consultants" into "shared
with everyone who can open Tekos", collapsing the two dimensions that ADR keeps
apart.

The XOR constraint differs deliberately from ADR-0209's inclusive OR on
`project_memberships`: the RBAC tab renders one row per grant under either a
Users or a Groups subsection, and a row carrying both would have no unambiguous
home nor revoke semantics.

### 3. No owner column; the last admin cannot be removed

A project has **no owner**. Its creator simply receives an `admin` grant, and
`created_by` is audit metadata that is never an authorization input. This is a
considered departure from ADR-0212's `conversations.owner_sub` and ADR-0213's
single-owner rule: an engagement outlives the person who opened it, and a
transferable-owner model makes "the owner left the company" an operational
incident. The invariant that made a single owner attractive - a project can
never become unadministrable - is preserved instead by a guard: any grant change
whose resulting set contains no subject-scoped `admin` grant is rejected. The
guard covers demotion and revocation alike, and is enforced server-side
regardless of what the UI allows.

`conversations.owner_sub` is **kept** and keeps its meaning: the person who
started a conversation may always write to it, even when their project role is
only `clone`. That is what makes the `clone` role useful rather than merely
archival - fork and continue, without the right to disturb the original.

### 4. Conversations inherit; a conversation without a project is private

The effective right on a conversation is: the caller's project role if the
conversation belongs to a project they hold a grant on; `write` (or `admin`,
when their project role is `admin`) if they are its `owner_sub`; otherwise
denial. A conversation with no project is visible to its `owner_sub` and to
nobody else - there is no longer any way to share a single conversation, by
design.

Metadata rights, which ADR-0213 left silent and WP-066 resolved as owner-only,
are now stated explicitly: star and manual reorder are personal and available to
anyone who may read; rename requires the conversation's owner or project
`write`; archive requires the owner or project `admin`; irreversible purge
remains **owner-only**, because project admins are given cascade archival
(clause 7), not the right to destroy a colleague's history.

**Clone** copies the checkpoint's `channel_values` into a fresh thread **inside
the same project**, with a derived title (`"Foo"` becomes `"Foo (copy)"`), a new
`conversations` row owned by the cloner and `source_run_id` set for provenance.
It does not create a project and does not reset any grant.

**Single active writer.** ADR-0213's `conversation_write_locks` lease is
retained unchanged in shape and TTL: two collaborators must never race on one
LangGraph checkpoint thread, and that hazard is created by project sharing
exactly as it was by conversation sharing. This ADR additionally requires what
ADR-0213 specified but its implementation omitted - the lease must actually be
**renewed while the reply streams**, since the 30-second TTL is well inside the
180-second SSE budget agent-bff allows.

### 5. The project context is background, never instructions

`projects.context` holds up to **54 000 characters** of standing engagement
context, enforced identically in the browser, in the request schema and as a SQL
`CHECK`. It is injected into every conversation of the project at the same point
and under the same framing ADR-0215 already uses for its compaction summary -
a delimited *background information, not instructions* block appended to the
task's own OKF prompt. The OKF bundle remains the sole source of instructions
(ADR-0039): a user-editable field must never be able to rewrite an agent's
behaviour.

Injection is budgeted, not verbatim. A `zuno.memory.project_context.token_budget`
key (default 1200, same shape as ADR-0215's `zuno.memory.history.token_budget`)
truncates the block on a whitespace boundary, so a maximal context cannot crowd
out history or the user's own question on a 32k-context local model.

The context carries the project's `classification` and feeds ADR-0034's
effective-classification aggregation like any other retrieved content -
monotone escalation only, never a downgrade - so a C3 project's context can
never route a turn to an external model (ADR-0035).

### 6. Projects are global; the sidebar is per-agent

A project is cross-agent, matching ADR-0209's `knowledge.project` contract:
the same engagement is one project whether it is opened from Tekos or from
Arkos, with one set of grants and one context. Only its *conversations* are
agent-scoped, so an agent's sidebar lists that agent's conversations under each
project the caller may see. Project endpoints therefore live at `/v1/projects`,
outside the `/v1/agents/{agent}` family.

Each member may **star** a project independently (`project_stars`, the same
personal-flag pattern ADR-0212 chose for `conversation_stars` and for the same
reason: a star is one user's organizing flag, not a property of the object).

### 7. Deleting a project archives it and its conversations

Deletion is a **cascade soft-delete**: the project and every conversation in it
receive `archived_at`, including conversations owned by other members. Nothing
is erased, and the irreversible per-conversation purge stays where it was. The
confirmation names the counts - total conversations, and how many belong to
other members - because a project admin destroying colleagues' visible work
should be told the size of what they are doing.

### 8. `project_memberships` becomes a projection

rag-service keeps enforcing `knowledge.project` access against
`project_memberships` in the `rag-project` database, fail-closed, with
`app/search.py`'s `_check_project_membership` **unchanged**. That table is
demoted from ACL-of-record to a **read-model projection** of `project_grants`,
pushed by agent-runtime through rag-service's existing write boundary
(`PUT /v1/projects/{project_id}/memberships`, replace-all per project) so this
runtime still never holds a `rag-project` credential.

The push happens **inside** the grant-mutation transaction and before its
commit: a failed push rolls the mutation back and returns 503, so a revocation
is never half-applied. A monotone `grants_revision` accompanies every push and
is stored on the projection, making the endpoint idempotent and non-rewindable
under retry. A best-effort reconciliation at agent-runtime startup re-pushes any
project whose revision the projection does not hold; it is logged and
non-fatal, because a rag-service outage must not prevent agent-runtime from
booting.

Three alternatives were rejected: having rag-service call agent-runtime at
retrieval time (inverts the dependency direction, puts a synchronous hop on the
RAG hot path, and makes an agent-runtime outage a retrieval outage); having
agent-runtime assert membership in the `/v1/search` body (destroys the
defence-in-depth property `hybrid_search`'s own docstring is built on, by making
rag-service trust its caller for authorization); and `postgres_fdw`/`dblink`
(a new cross-database credential grant and a new failure mode inside a query
plan).

### 9. Frontend

`components/agent-frontend/web/src` gains a two-block sidebar in place of
ADR-0212's flat list: a **Projects** block (fold-all control, small-caps
heading, create action; one row per project with a fold caret, the title, a
"new conversation in this project" action and a kebab offering Modify and
Delete) and, below a separator, a **Conversations** block holding the caller's
project-less conversations. Conversation rows keep ADR-0515's exact layout -
drag handle, star, title, kebab - in both blocks, achieved by extracting the
existing row into a shared component rather than reimplementing it.

Clicking a project row opens a **project dialog** with two tabs: Description
(title, context with a live character counter, and the optional Salesforce
field of ADR-0528) and RBAC (Users and Groups subsections, each listing name,
role and a revoke control, with an add control). The dialog stages every change
client-side and commits them in **one** request on validation - which is why the
API offers a single full-state `PUT` rather than ADR-0213's five per-member
endpoints. A caller with `read` or `clone` sees it read-only; `write` may edit
the Description tab; only `admin` sees the RBAC tab and the delete action.

Opening a conversation the caller may only read renders the tab without a
composer, reusing the inline-alert pattern ADR-0213 introduced for lease
contention.

A new BFF-only `GET /api/groups` lists the realm's business-role groups through
the same `zuno-admin-api` Keycloak Admin API client ADR-0213 introduced for
`GET /api/colleagues`, which is retained and reused by the RBAC tab. It requires
one additional least-privilege service-account role, `query-groups`, and never
`manage-users` or `manage-realm`.

## Consequences

The platform gains a real collaboration object, and loses a whole authorization
surface: one boundary (the project) replaces two (the conversation ACL and the
untouchable `project_memberships`). Sharing addresses teams for the first time,
through groups, without any change to Keycloak's static realm - sharing remains
data, exactly as ADR-0209 and ADR-0213 both reasoned. `knowledge.project`
becomes reachable by ordinary users instead of requiring a hand-populated table.
agent-runtime gains a project module, a per-request role resolution on the chat
path, and an outbound projection dependency on rag-service for grant mutations
only - never on the chat path. ADR-0213's merged code is removed rather than
migrated, which is safe precisely because it was never provisioned.

## Security considerations

Every new path fails closed. An absent grant row is a denial, never a default;
every new persistence function refuses on an unreachable pool with 503 rather
than degrading to "no restriction"; the grant mutation rolls back rather than
committing a revocation the projection did not accept; `GET /api/groups` and
`GET /api/colleagues` return 503 rather than an empty list, since a silently
empty group picker reads as "this realm has no groups" and would quietly
prevent every group grant.

The conversation-list query is the single most sensitive change this decision
makes: it moves from a one-predicate `owner_sub` filter to a membership join,
and an error there leaks colleagues' conversations. It requires a
security-negative test covering, at minimum, a private conversation, a project
conversation, a colleague's conversation in a shared project, a colleague's
conversation in an unshared project, and a conversation in an archived project.

`record_turn` retains its documented exception to fail-closed behaviour (it
swallows pool errors so a metadata write never fails a chat reply). It now
writes the server-resolved `project_id`, so a swallowed write leaves a
checkpoint with no `conversations` row - which the access check must treat as a
**denial**, never as "no project restriction".

Revocation stays soft, as under ADR-0213: an open tab keeps working until its
next reload or send, at which point the same fail-closed check denies it. No
per-request caching of effective role may be introduced, as that would widen
exactly the window this posture bounds.

The project context is user-authored free text of substantial size that reaches
the model on every turn. It is classified, escalates the turn monotonically, and
is framed as background rather than instructions; the OKF bundle remains the only
source of agent instructions.

## Operational considerations

Effective-role resolution is one additional indexed lookup, folded into the
existing conversation query as a lateral join rather than a separate round trip.
The grant projection is the only cross-database consistency point in the design
and is observable per push, with the startup reconciliation as its repair path;
a persistent divergence is a symptom of rag-service unavailability, not of the
projection logic. Grant mutations are traceable by `project_id`, `subject` or
`group_name`, and `granted_by`, mirroring ADR-0203's tracing requirement.
Cascade archival reports its counts.

The migration nulls any pre-existing client-asserted `conversations.project_id`
that has no `projects` row - it was never verifiable and nothing consumed it
beyond ADR-0512's now-superseded per-conversation binding - and raises the
affected count as a `NOTICE` before adding the foreign key. The DDL runs
fail-fast inside agent-runtime's startup, so this ordering is load-bearing:
adding the constraint before the cleanup would crash-loop the pod.

## Acceptance criteria

- A user creates a project with a title and a context through the dialog, in one
  save, and it appears in their Projects block; a conversation started from that
  project's action carries its `project_id`, verified server-side.
- A project shared with a colleague as `read` shows that project and its
  conversations in the colleague's sidebar; opening one renders a tab with no
  composer, and a direct chat POST is refused 403.
- A project shared with a business-role **group** grants every member of that
  group the same access without any Keycloak change; an `agent_*` group is
  refused as a grant target.
- A member with `write` sends messages and edits the title and context but
  cannot see the RBAC tab; an `admin` may grant, revoke, and delete.
- Revoking or demoting the last admin is refused, in the UI and at the API.
- A `clone` member clones a conversation into the same project, owns the copy,
  may write to the copy, and cannot write to the original.
- Deleting a project archives it and all its conversations, including a
  colleague's, after a confirmation naming the counts; no message history is
  erased.
- The project context appears in the model's system prompt as a delimited
  background block, truncated to the configured token budget, and a project with
  an empty context produces a prompt byte-identical to today's.
- A user with no grant on a project retrieves none of its `knowledge.project`
  memories, structured state or chunks - the ADR-0209 guarantee, now enforced
  against the projection.
- Automated tests cover effective-role resolution, the last-admin guard, the
  54 000-character limit, fail-closed behaviour on an unreachable pool for every
  new function, rollback when the projection push fails, clone title derivation
  and ownership, and both context-injection points; a security-negative test
  covers the rewritten conversation listing in both directions.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered,
Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0008](0008-use-one-frontend-and-one-bff-deployment-per-agent.md)
- [ADR-0024](0024-use-vault-for-application-secrets.md)
- [ADR-0033](0033-derive-user-identity-only-from-validated-tokens.md)
- [ADR-0034](0034-compute-effective-classification-from-the-complete-context.md)
- [ADR-0035](0035-prevent-restricted-internal-context-from-reaching-external-models.md)
- [ADR-0039](0039-make-agent-runtime-execute-the-okf-agent-contract.md)
- [ADR-0040](0040-separate-agent-entitlement-from-business-role-authorization.md)
- [ADR-0042](0042-use-opaque-browser-sessions-with-server-side-token-storage.md)
- [ADR-0044](0044-use-patternfly-react-for-the-agent-frontend.md)
- [ADR-0054](0054-define-the-bff-contract-openapi-first.md)
- [ADR-0103](0103-persist-resumable-long-running-agent-workflows.md)
- [ADR-0203](0203-enforce-knowledge-authorization-as-policy-intersection.md)
- [ADR-0209](0209-introduce-project-scoped-agent-memory.md)
- [ADR-0212](0212-introduce-persistent-navigable-chat-conversations.md)
- [ADR-0213](0213-introduce-role-based-conversation-sharing.md) (superseded by this ADR)
- [ADR-0215](0215-carry-conversation-history-into-agent-prompts-with-budgeted-compaction.md)
- [ADR-0511](0511-define-okf-quota-policy-enforced-via-kuadrant.md)
- [ADR-0515](0515-per-conversation-tabs-one-browser-tab-per-agent.md)
- [ADR-0528](0528-rekey-project-binding-quota-and-telemetry-onto-the-zuno-project-id.md)
