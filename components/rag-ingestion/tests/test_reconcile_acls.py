"""WP-25 (ADR-0110): the reconcile-acls stage - keeps indexed acl_groups
aligned with current Confluence source authorization and removes chunks
whose source is no longer visible/in-scope. Fixture-driven, no live
Confluence or database is ever contacted (CI-safe).

Run:
    cd components/rag-ingestion && .venv/bin/python tests/test_reconcile_acls.py
"""
import json
import os
import sys
import unittest.mock as mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import rag_ingestion  # noqa: E402
from rag_ingestion import stage_reconcile_acls  # noqa: E402

_REQUIRED_ENV = {
    "S3_BUCKET": "test-bucket",
    "PGHOST": "localhost",
    "PGDATABASE": "rag-tech",
    "EMBEDDING_ENDPOINT": "http://embeddings.test/v1",
    "EMBEDDING_MODEL": "test-model",
}


def _config(**env):
    merged = {**_REQUIRED_ENV, **env}
    with mock.patch.dict(os.environ, merged, clear=True):
        return rag_ingestion.load_config()


class _FakeResponse:
    def __init__(self, payload=None):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _confluence_page(page_id: str, ancestors=None, labels=None) -> dict:
    return {
        "_links": {"webui": f"/spaces/ARCH/pages/{page_id}"},
        "ancestors": [{"title": t} for t in (ancestors or [])],
        "metadata": {"labels": {"results": [{"name": n} for n in (labels or [])]}},
    }


class _FakeCursor:
    """Backs a fake `document_embeddings` table (source -> acl_groups
    list) with just enough SQL-shape sniffing to serve
    stage_reconcile_acls's three query shapes."""

    def __init__(self, table: dict):
        self._table = table
        self._pending = []
        self.rowcount = 0

    def execute(self, sql, params=None):
        if "SELECT DISTINCT" in sql:
            self._pending = [(source, acl) for source, acl in self._table.items()]
        elif "DELETE FROM document_embeddings" in sql:
            source = params[0]
            self.rowcount = 1 if source in self._table else 0
            self._table.pop(source, None)
        elif "UPDATE document_embeddings" in sql:
            new_acl_json, source = params
            self.rowcount = 1 if source in self._table else 0
            if source in self._table:
                self._table[source] = json.loads(new_acl_json)
        else:
            raise AssertionError(f"unexpected SQL in fake cursor: {sql!r}")

    def fetchall(self):
        return self._pending

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _FakeConn:
    def __init__(self, table: dict):
        self._table = table
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return _FakeCursor(self._table)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def _confluence_config(sources, table):
    config = _config(
        INGESTION_DOMAIN="knowledge.tech",
        CONFLUENCE_SOURCES_JSON=json.dumps(sources),
    )
    conn = _FakeConn(table)
    return config, conn


_DEFAULT_SOURCE = [{
    "name": "satellite-archi", "type": "cloud", "baseUrl": "https://conf.test",
    "spaces": ["ARCH"], "requiredGroups": ["confluence-archi-satellite"],
}]


def test_reconcile_acls_updates_a_changed_acl_groups_value():
    table = {"https://conf.test/wiki/spaces/ARCH/pages/1": ["old-group"]}
    config, conn = _confluence_config(_DEFAULT_SOURCE, table)
    listing = {"results": [_confluence_page("1")]}
    with mock.patch.object(rag_ingestion, "_pg_connect", return_value=conn), \
         mock.patch.object(rag_ingestion.requests, "get", return_value=_FakeResponse(listing)):
        stage_reconcile_acls(config, store=None)
    assert table["https://conf.test/wiki/spaces/ARCH/pages/1"] == ["confluence-archi-satellite"]
    assert conn.committed


def test_reconcile_acls_deletes_a_document_no_longer_visible():
    table = {
        "https://conf.test/wiki/spaces/ARCH/pages/1": ["confluence-archi-satellite"],
        "https://conf.test/wiki/spaces/ARCH/pages/GONE": ["confluence-archi-satellite"],
    }
    config, conn = _confluence_config(_DEFAULT_SOURCE, table)
    listing = {"results": [_confluence_page("1")]}  # page "GONE" no longer in the live listing
    with mock.patch.object(rag_ingestion, "_pg_connect", return_value=conn), \
         mock.patch.object(rag_ingestion.requests, "get", return_value=_FakeResponse(listing)):
        stage_reconcile_acls(config, store=None)
    assert "https://conf.test/wiki/spaces/ARCH/pages/GONE" not in table
    assert "https://conf.test/wiki/spaces/ARCH/pages/1" in table


def test_reconcile_acls_removes_a_document_outside_every_configured_scope():
    """Fail closed: a page that's still visible in Confluence but no
    longer falls under ANY currently-configured source's directory scope
    (config narrowed) is undeterminable -> removed, same as a genuinely
    deleted page."""
    source = [{**_DEFAULT_SOURCE[0], "directories": ["Satellite/Architecture"]}]
    table = {"https://conf.test/wiki/spaces/ARCH/pages/1": ["confluence-archi-satellite"]}
    config, conn = _confluence_config(source, table)
    # The page exists but its ancestors don't match the configured directory.
    listing = {"results": [_confluence_page("1", ancestors=["Satellite", "Build"])]}
    with mock.patch.object(rag_ingestion, "_pg_connect", return_value=conn), \
         mock.patch.object(rag_ingestion.requests, "get", return_value=_FakeResponse(listing)):
        stage_reconcile_acls(config, store=None)
    assert table == {}


def test_reconcile_acls_leaves_an_unchanged_document_alone():
    table = {"https://conf.test/wiki/spaces/ARCH/pages/1": ["confluence-archi-satellite"]}
    config, conn = _confluence_config(_DEFAULT_SOURCE, table)
    listing = {"results": [_confluence_page("1")]}
    with mock.patch.object(rag_ingestion, "_pg_connect", return_value=conn), \
         mock.patch.object(rag_ingestion.requests, "get", return_value=_FakeResponse(listing)):
        stage_reconcile_acls(config, store=None)
    # Same value, and stage_reconcile_acls's own UPDATE query only fires
    # when sorted(current) != sorted(new) - the fake table would still
    # show the same list either way, so also assert no reconnection error
    # occurred and the entry survived unmodified.
    assert table["https://conf.test/wiki/spaces/ARCH/pages/1"] == ["confluence-archi-satellite"]


def test_reconcile_acls_aborts_with_zero_deletions_on_a_listing_failure():
    """A transient Confluence outage must never look like 'every page was
    deleted' - the whole stage aborts before any DELETE/UPDATE runs."""
    import requests as requests_module

    table = {"https://conf.test/wiki/spaces/ARCH/pages/1": ["confluence-archi-satellite"]}
    config, conn = _confluence_config(_DEFAULT_SOURCE, table)
    with mock.patch.object(rag_ingestion, "_pg_connect", return_value=conn), \
         mock.patch.object(
             rag_ingestion.requests, "get",
             side_effect=requests_module.RequestException("connection reset"),
         ):
        try:
            stage_reconcile_acls(config, store=None)
            raise AssertionError("expected SystemExit")
        except SystemExit as exc:
            assert "aborting with zero deletions" in str(exc)
    # The fake DB connection was never even opened (the listing failure
    # happens before _pg_connect is called).
    assert table == {"https://conf.test/wiki/spaces/ARCH/pages/1": ["confluence-archi-satellite"]}
    assert not conn.committed


def test_reconcile_acls_preserve_acl_false_confirms_existence_without_touching_acl():
    source = [{**_DEFAULT_SOURCE[0], "preserveAcl": False}]
    table = {"https://conf.test/wiki/spaces/ARCH/pages/1": ["manually-curated-group"]}
    config, conn = _confluence_config(source, table)
    listing = {"results": [_confluence_page("1")]}
    with mock.patch.object(rag_ingestion, "_pg_connect", return_value=conn), \
         mock.patch.object(rag_ingestion.requests, "get", return_value=_FakeResponse(listing)):
        stage_reconcile_acls(config, store=None)
    # Neither deleted (still visible) nor overwritten with requiredGroups.
    assert table["https://conf.test/wiki/spaces/ARCH/pages/1"] == ["manually-curated-group"]


def test_reconcile_acls_is_a_noop_with_no_confluence_sources_configured():
    config = _config(INGESTION_DOMAIN="knowledge.sales")  # no CONFLUENCE_SOURCES_JSON
    with mock.patch.object(rag_ingestion, "_pg_connect") as fake_connect:
        stage_reconcile_acls(config, store=None)
    fake_connect.assert_not_called()


TESTS = [
    test_reconcile_acls_updates_a_changed_acl_groups_value,
    test_reconcile_acls_deletes_a_document_no_longer_visible,
    test_reconcile_acls_removes_a_document_outside_every_configured_scope,
    test_reconcile_acls_leaves_an_unchanged_document_alone,
    test_reconcile_acls_aborts_with_zero_deletions_on_a_listing_failure,
    test_reconcile_acls_preserve_acl_false_confirms_existence_without_touching_acl,
    test_reconcile_acls_is_a_noop_with_no_confluence_sources_configured,
]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
