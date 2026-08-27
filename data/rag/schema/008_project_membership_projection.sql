-- Zuno Demo - project_memberships becomes a projection (ADR-0527, WP-088)
--
-- Applied only to the knowledge.project domain's database (rag-project),
-- by gitops/charts/rag-service's per-domain schema-apply Job, immediately
-- after 005_project_memory.sql created the table this file alters.
--
-- ADR-0209 made project_memberships the ACL of record for
-- knowledge.project, deliberately as data rather than as a Keycloak group
-- per project. ADR-0527 keeps that table and keeps app/search.py's
-- fail-closed check against it byte-identical - what changes is where the
-- rows come from. The authority is now project_grants in the
-- agent-conversations database, which agent-runtime owns; this table is a
-- read-model of it, replaced wholesale per project through
-- PUT /v1/projects/{project_id}/memberships.
--
-- Two reasons it is a projection rather than a cross-database read: this
-- service must keep deciding for itself (app/search.py's check is defence
-- in depth precisely because it does not trust its caller's membership
-- claim), and agent-runtime deliberately holds no credential on this
-- database (see components/agent-runtime/app/clients/project_memory_client.py).

-- Monotone per project, carried from projects.grants_revision. Without it
-- a push delayed behind a newer one would resurrect an already-revoked
-- grant set on retry. Pre-existing WP-28 rows default to 0, so the first
-- projection push (revision >= 1) always supersedes them.
ALTER TABLE project_memberships ADD COLUMN IF NOT EXISTS revision bigint NOT NULL DEFAULT 0;

-- Replace-all writes make duplicates impossible in practice; these make
-- them impossible in principle, and they are partial for the same reason
-- the table's own CHECK is an XOR-in-spirit: exactly one of the two
-- columns is ever set on a row.
CREATE UNIQUE INDEX IF NOT EXISTS uq_project_memberships_subject
    ON project_memberships (project_id, subject) WHERE subject IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_project_memberships_group
    ON project_memberships (project_id, group_name) WHERE group_name IS NOT NULL;

COMMENT ON TABLE project_memberships IS
    'ADR-0527: PROJECTION of agent-conversations.project_grants, replaced per project via PUT /v1/projects/{id}/memberships. Still the fail-closed deny gate app/search.py enforces (ADR-0209) - never edited directly.';
