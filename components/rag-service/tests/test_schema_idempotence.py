#!/usr/bin/env python3
"""The RAG schema-apply chain must survive being applied twice.

Nothing else in this repository checks that. `helm lint` renders
configmap-schema.yaml but treats the SQL as an opaque block, and
test_write_path_invariant.py excludes the schema path by name. That gap is
how 004_rag_chunking.sql went stale after ADR-0518 widened the embedding
column to 1024 while 004 kept narrowing it to 384 unconditionally: the Job
could only ever succeed once, and because psql commits each statement
separately, every failed run left the domain's ivfflat index dropped and
never rebuilt. Both symptoms were found in production on 2026-08-27, on
rag-tech (68,931 rows) and rag-sxa-legacy (319,713 rows).

The Job is an ArgoCD Sync hook, so it re-runs on EVERY sync. Idempotence is
not a nicety here, it is the contract.

This test applies the chain exactly as
gitops/charts/rag-service/templates/job-schema-apply.yaml does - same files,
same order, same ON_ERROR_STOP=1, same search_path - against a throwaway
PostgreSQL, then inserts real 1024-dimensional rows and applies it AGAIN.

Run directly:

    cd components/rag-service && python3 tests/test_schema_idempotence.py

Skips cleanly (exit 0, with a reason) when no container runtime or image is
available - the same convention agent-frontend's Go tests use for the Redis
they need. A skip is not a pass: CI that cares must run it somewhere the
image can be pulled.
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import time
import uuid

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_SQL_DIR = _REPO_ROOT / "gitops" / "charts" / "rag-service" / "files" / "sql"
_CANONICAL_SQL_DIR = _REPO_ROOT / "data" / "rag" / "schema"

_IMAGE = "pgvector/pgvector:pg16"
_SCHEMA = "rag"
_PASSWORD = "idempotence-test"

# The exact argument order job-schema-apply.yaml builds for the `project`
# domain - the only domain that applies 005/008, and therefore the widest
# path through the chain. Note 005/008 really do run BEFORE 006/007 there;
# that ordering is reproduced rather than tidied, because reproducing what
# the Job does is the whole point of this test.
_CHAIN = [
    "002_pgvector.sql",
    "003_rag_metadata.sql",
    "004_rag_chunking.sql",
    "005_project_memory.sql",
    "008_project_membership_projection.sql",
    "006_embedding_1024.sql",
    "007_ivfflat_lists.sql",
]


class SkipTest(Exception):
    """Raised when the environment cannot run this test at all."""


def _runtime() -> str:
    for candidate in ("docker", "podman"):
        if shutil.which(candidate) is None:
            continue
        probe = subprocess.run(
            [candidate, "info"], capture_output=True, text=True, timeout=60
        )
        if probe.returncode == 0:
            return candidate
    raise SkipTest("no usable container runtime (tried docker, podman)")


def _start_postgres(runtime: str) -> str:
    name = f"zuno-schema-idempotence-{uuid.uuid4().hex[:8]}"
    # The SQL is BIND-MOUNTED read-only rather than copied in. The image
    # runs as the postgres user, so creating /sql inside it needs root and
    # a copy silently lands nowhere. `:ro,z` keeps SELinux hosts happy
    # (podman) and is harmless elsewhere.
    started = subprocess.run(
        [runtime, "run", "-d", "--rm", "--name", name,
         "-e", f"POSTGRES_PASSWORD={_PASSWORD}", "-e", "POSTGRES_DB=ragtest",
         "-v", f"{_SQL_DIR}:/sql:ro,z",
         _IMAGE],
        capture_output=True, text=True, timeout=300,
    )
    if started.returncode != 0:
        raise SkipTest(f"could not start {_IMAGE}: {started.stderr.strip()[:300]}")

    # pg_isready ALONE is a trap here: the postgres entrypoint boots a
    # temporary server to run initdb and the /docker-entrypoint-initdb.d
    # scripts, answers pg_isready during it, then shuts it down before
    # starting the real one. Connecting in that window fails with "No such
    # file or directory" on the socket - which is exactly how this test
    # failed the first time it was written. Wait for the entrypoint's own
    # "init process complete" marker first, then confirm with pg_isready.
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        logs = subprocess.run(
            [runtime, "logs", name], capture_output=True, text=True, timeout=30,
        )
        combined = (logs.stdout or "") + (logs.stderr or "")
        if "init process complete" in combined:
            ready = subprocess.run(
                [runtime, "exec", name, "pg_isready", "-U", "postgres", "-d", "ragtest"],
                capture_output=True, text=True, timeout=30,
            )
            if ready.returncode == 0:
                return name
        time.sleep(1)
    subprocess.run([runtime, "rm", "-f", name], capture_output=True, timeout=60)
    raise SkipTest("postgres container never became ready within 90s")


def _psql(runtime: str, container: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [runtime, "exec", "-e", f"PGPASSWORD={_PASSWORD}",
         "-e", f"PGOPTIONS=-c search_path={_SCHEMA},public", container,
         "psql", "-U", "postgres", "-d", "ragtest", "-v", "ON_ERROR_STOP=1", *args],
        capture_output=True, text=True, timeout=300,
    )


def _apply_chain(runtime: str, container: str, label: str) -> None:
    """Applies the chain the way the Job does: one psql invocation, every
    file as a -f argument, ON_ERROR_STOP=1 so the first failure aborts."""
    args = ["-c", f"CREATE SCHEMA IF NOT EXISTS {_SCHEMA};"]
    for name in _CHAIN:
        args += ["-f", f"/sql/{name}"]
    result = _psql(runtime, container, *args)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout).strip().splitlines()[-6:]
        raise AssertionError(
            f"{label} of the schema chain failed:\n  " + "\n  ".join(tail)
        )


def _assert_chain_files_exist() -> None:
    """The Job's -f arguments and this directory must agree. A missing file
    is exactly the shape of the ADR-0525 gap where 007 was referenced by the
    Job but never published into the ConfigMap."""
    for name in _CHAIN:
        src = _SQL_DIR / name
        if not src.is_file():
            raise AssertionError(f"the Job references {name} but {src} does not exist")


def _insert_rows(runtime: str, container: str, count: int) -> None:
    """Real 1024-dim rows, the width ADR-0518 settled on. Their presence is
    what turns 004's unguarded cast from a silent no-op into the live
    failure this test exists to prevent - on an empty table the cast has no
    row to evaluate and the bug hides."""
    result = _psql(
        runtime, container, "-c",
        f"INSERT INTO {_SCHEMA}.document_embeddings (source, chunk_index, title, content, embedding) "
        f"SELECT 'idempotence://doc-' || g, g, 'doc ' || g, 'content ' || g, "
        f"(SELECT array_agg(0.01::real)::vector FROM generate_series(1, 1024)) "
        f"FROM generate_series(1, {count}) g "
        f"ON CONFLICT DO NOTHING;",
    )
    if result.returncode != 0:
        raise AssertionError(
            f"could not seed {count} embedded rows: {(result.stderr or '').strip()[:400]}"
        )


def _scalar(runtime: str, container: str, sql: str) -> str:
    result = _psql(runtime, container, "-tAc", sql)
    if result.returncode != 0:
        raise AssertionError(f"query failed: {sql}\n{(result.stderr or '').strip()[:300]}")
    return result.stdout.strip()


def test_the_chain_applies_twice_over_real_1024_dim_rows(runtime: str, container: str) -> None:
    """The regression itself. Pass 1 mirrors a fresh install; the rows then
    make the database look like a live one; pass 2 is what every subsequent
    ArgoCD sync does."""
    _apply_chain(runtime, container, "first application")

    width = _scalar(runtime, container,
                    "SELECT atttypmod FROM pg_attribute "
                    f"WHERE attrelid = '{_SCHEMA}.document_embeddings'::regclass AND attname = 'embedding'")
    assert width == "1024", f"after a fresh apply the column should be vector(1024), got {width}"

    _insert_rows(runtime, container, 25)
    _apply_chain(runtime, container, "second application")

    width = _scalar(runtime, container,
                    "SELECT atttypmod FROM pg_attribute "
                    f"WHERE attrelid = '{_SCHEMA}.document_embeddings'::regclass AND attname = 'embedding'")
    assert width == "1024", f"the second apply changed the column width to {width}"


def test_the_second_apply_preserves_the_rows(runtime: str, container: str) -> None:
    """004 narrows with a USING cast and 006 TRUNCATEs. Both are guarded now,
    but a future edit that removed either guard would destroy a live corpus
    silently rather than fail - so assert the data survives, not merely that
    psql exited 0."""
    rows = _scalar(runtime, container, f"SELECT count(*) FROM {_SCHEMA}.document_embeddings")
    assert rows == "25", f"the second apply should have preserved all 25 rows, found {rows}"


def test_the_ivfflat_index_survives_a_reapply(runtime: str, container: str) -> None:
    """The subtler half of the incident: 004's DROP INDEX committed before
    its ALTER aborted, so a failed run left vector search on a sequential
    scan with nothing to signal it. A green Job that silently dropped the
    index would still be a regression."""
    present = _scalar(
        runtime, container,
        "SELECT count(*) FROM pg_indexes "
        f"WHERE schemaname = '{_SCHEMA}' AND indexname = 'ix_document_embeddings_embedding_cosine'",
    )
    assert present == "1", "the ivfflat index is missing after re-applying the chain"


def test_a_third_apply_is_still_clean(runtime: str, container: str) -> None:
    """Two passes could pass by luck if some statement merely alternated
    state. A third settles it."""
    _apply_chain(runtime, container, "third application")
    rows = _scalar(runtime, container, f"SELECT count(*) FROM {_SCHEMA}.document_embeddings")
    assert rows == "25", f"the third apply lost rows: {rows}"


def test_project_tables_exist_for_the_project_domain(runtime: str, container: str) -> None:
    """005/008 are applied only for `- domain: project`, and ADR-0527's
    membership projection depends on both - project_memberships with the
    revision column 008 adds. Enabling the domain without them means every
    project save fails 503."""
    tables = _scalar(
        runtime, container,
        f"SELECT string_agg(tablename, ',' ORDER BY tablename) FROM pg_tables WHERE schemaname = '{_SCHEMA}'",
    )
    for expected in ("project_memberships", "project_state"):
        assert expected in tables, f"{expected} missing after the chain; got {tables}"

    revision = _scalar(
        runtime, container,
        "SELECT count(*) FROM information_schema.columns "
        f"WHERE table_schema = '{_SCHEMA}' AND table_name = 'project_memberships' AND column_name = 'revision'",
    )
    assert revision == "1", "008 did not add project_memberships.revision"


def test_the_two_sql_copies_have_not_drifted() -> None:
    """configmap-schema.yaml keeps data/rag/schema/ as the canonical
    human-readable source and the chart's files/sql/ as the deployed one,
    synced BY HAND. Only the chart copy is rendered into the ConfigMap, so
    drift means the file people read is not the file that runs. Needs no
    container, so it runs even when the rest of this suite skips."""
    drifted = []
    for name in _CHAIN:
        canonical = _CANONICAL_SQL_DIR / name
        deployed = _SQL_DIR / name
        if not canonical.is_file():
            # 002_pgvector.sql has only ever existed in the chart.
            continue
        if canonical.read_text() != deployed.read_text():
            drifted.append(name)
    assert not drifted, (
        "data/rag/schema/ and gitops/charts/rag-service/files/sql/ have drifted for: "
        + ", ".join(drifted)
    )


CONTAINERLESS_TESTS = [test_the_two_sql_copies_have_not_drifted]

# Order matters: these share one container and build on each other's state,
# deliberately, because that is what re-applying against a live database is.
CONTAINER_TESTS = [
    test_the_chain_applies_twice_over_real_1024_dim_rows,
    test_the_second_apply_preserves_the_rows,
    test_the_ivfflat_index_survives_a_reapply,
    test_a_third_apply_is_still_clean,
    test_project_tables_exist_for_the_project_domain,
]


def main() -> int:
    failures = 0

    for test in CONTAINERLESS_TESTS:
        try:
            test()
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")

    try:
        runtime = _runtime()
        _assert_chain_files_exist()
        container = _start_postgres(runtime)
    except SkipTest as exc:
        print(f"\nSKIP the container-backed tests: {exc}")
        print("A skip is not a pass - run this where pgvector/pgvector:pg16 can be pulled.")
        return 1 if failures else 0

    try:
        for test in CONTAINER_TESTS:
            try:
                test(runtime, container)
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {test.__name__}: {exc}")
            else:
                print(f"PASS {test.__name__}")
    finally:
        subprocess.run([runtime, "rm", "-f", container], capture_output=True, timeout=120)

    total = len(CONTAINERLESS_TESTS) + len(CONTAINER_TESTS)
    print(f"\n{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
