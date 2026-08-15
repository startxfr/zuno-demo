-- Zuno Demo - project-scoped agent memory (ADR-0209, WP-28)
--
-- Applied only to the knowledge.project domain's database (rag-project,
-- gitops/charts/rag-service's per-domain schema-apply Job -
-- templates/job-schema-apply.yaml). document_embeddings (002_pgvector.sql,
-- ALTERed by 003/004) already exists in this database by the time this
-- file runs - it IS this domain's semantic-memory chunk table
-- (ADR-0202's common metadata contract, `project_id` riding in
-- `metadata->>'project_id'`, WP-28's own extension in
-- knowledge/metadata-schema.yaml). This file adds the two tables that
-- contract doesn't cover: structured project state, and the
-- project-membership ACL PostgreSQL deliberately keeps as data rather
-- than a per-project Keycloak group (ADR-0209 Decision - the realm is
-- static GitOps, projects are created ad hoc at runtime).

-- Structured project state: key facts as rows, not as vector chunks -
-- "OpenShift 4.22, AWS, three clusters" is a lookup, not a similarity
-- search. One row per (project_id, key); the extraction step upserts
-- rather than appending an unbounded history of a fact changing over
-- time (ADR-0209 doesn't ask for fact versioning, only current state).
-- Carries the full record shape ADR-0209's Decision requires for both
-- persistence concerns: project_id, author, agent, source/session,
-- timestamp, classification, acl_groups, content(value), metadata.
CREATE TABLE IF NOT EXISTS project_state (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id      text        NOT NULL,
    key             text        NOT NULL,
    value           jsonb       NOT NULL,
    author_sub      text        NOT NULL,
    agent           text        NOT NULL,
    session_id      text,
    -- C2 default (ADR-0209: memories inherit source classification, never
    -- silently downgraded) - the extraction step always sets this
    -- explicitly from the conversation's own effective_classification;
    -- the default only covers a row written some other way.
    classification  text        NOT NULL DEFAULT 'C2',
    acl_groups      jsonb       NOT NULL DEFAULT '[]'::jsonb,
    metadata        jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_project_state_project_key'
    ) THEN
        ALTER TABLE project_state
            ADD CONSTRAINT uq_project_state_project_key UNIQUE (project_id, key);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_project_state_project_id ON project_state (project_id);

COMMENT ON TABLE project_state IS 'ADR-0209: structured per-engagement facts (key/value), extracted from conversations - never raw turns. One current row per (project_id, key).';

-- Project membership - who may read/write this project's state and
-- semantic memory. Checked at retrieval time with the same fail-closed
-- intersection pattern app/search.py's acl_groups `?|` filter already
-- uses for chunk-level ACLs (ADR-0046): a row's `subject` matches the
-- caller's sub, OR `group_name` matches one of the caller's groups. No
-- matching row for a project_id = deny, whether that means "wrong
-- project_id" or "right project, wrong caller" - both fail closed
-- identically (ADR-0209 Security considerations: "missing membership...
-- must fail closed").
CREATE TABLE IF NOT EXISTS project_memberships (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id  text        NOT NULL,
    -- Exactly one of subject/group_name is set per row - a project can
    -- grant specific users, specific business-role groups, or both
    -- (multiple rows), but never neither (an unconditionally-matching
    -- row would defeat the whole point of this table).
    subject     text,
    group_name  text,
    granted_by  text        NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_project_memberships_subject_or_group
        CHECK (subject IS NOT NULL OR group_name IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS ix_project_memberships_project_id ON project_memberships (project_id);
CREATE INDEX IF NOT EXISTS ix_project_memberships_subject ON project_memberships (subject) WHERE subject IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_project_memberships_group ON project_memberships (group_name) WHERE group_name IS NOT NULL;

COMMENT ON TABLE project_memberships IS 'ADR-0209: project_id -> member subject/group, data not identity infrastructure - checked fail-closed at retrieval, never a Keycloak group per project.';
