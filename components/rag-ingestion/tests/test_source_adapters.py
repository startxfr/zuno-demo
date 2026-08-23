"""WP-22 (ADR-0204 part 2): source-adapter interface and the three new
adapters, fixture-driven - no live source, S3 or database is ever
contacted (CI-safe).

Run:
    cd components/rag-ingestion && .venv/bin/python tests/test_source_adapters.py
"""
import os
import re
import sys
import unittest.mock as mock
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import rag_ingestion  # noqa: E402
from rag_ingestion import (  # noqa: E402
    SOURCE_ADAPTERS,
    STAGES,
    IngestionConfig,
    _parse_duration_spec,
    _parse_http_last_modified,
    _run_source_adapter,
    stage_normalize,
    stage_validate,
)


class FakeStore:
    """In-memory CorpusStore double - same four methods the stages use."""

    def __init__(self):
        self.json = {}
        self.raw = {}

    def put_json(self, key, obj):
        self.json[key] = obj

    def get_json(self, key):
        return self.json.get(key)

    def list_keys(self, prefix):
        return sorted(k for k in {**self.json, **self.raw} if k.startswith(prefix))

    def get_bytes(self, key):
        return self.raw.get(key)


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
    def __init__(self, payload=None, text="", headers=None):
        self._payload = payload
        self.text = text
        self.headers = headers or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


# --- registry shape ---------------------------------------------------------


def test_every_fetch_stage_has_an_adapter_bound_to_one_domain():
    expected = {
        "fetch-redhat": "knowledge.tech",
        "fetch-confluence": "knowledge.tech",
        "fetch-salesforce": "knowledge.sales",
        "fetch-aramis": "knowledge.adv",
        "load-sxa-dump": "knowledge.sxa-legacy",
        "fetch-sxa": "knowledge.sxa",
    }
    assert {s: a.domain for s, a in SOURCE_ADAPTERS.items()} == expected
    for stage in expected:
        assert stage in STAGES


def test_fetch_stage_for_the_wrong_domain_fails_closed_before_any_write():
    config = _config(INGESTION_DOMAIN="knowledge.tech")
    store = FakeStore()
    adapter = SOURCE_ADAPTERS["fetch-salesforce"]
    try:
        _run_source_adapter(adapter, config, store)
        raise AssertionError("expected SystemExit")
    except SystemExit as exc:
        assert "refusing to fetch" in str(exc)
    assert store.json == {}


# --- fetch-redhat / fetch-confluence (refactored, knowledge.tech) -----------


_REDHAT_HTML = "<html><body><h1>Satellite Guide</h1><main><p>Install steps.</p></main></body></html>"


def test_fetch_redhat_stamps_domain_and_canonical_technology():
    sources = (
        '[{"product": "Satellite", "productSlug": "red-hat-satellite", '
        '"version": "6.15", "documentationUrl": "https://docs.test/sat"},'
        '{"product": "Quay", "productSlug": "red-hat-quay", '
        '"version": "3.10", "documentationUrl": "https://docs.test/quay"}]'
    )
    config = _config(REDHAT_SOURCES_JSON=sources, INGESTION_DOMAIN="knowledge.tech")
    store = FakeStore()
    with mock.patch.object(rag_ingestion, "_http_get", return_value=_FakeResponse(text=_REDHAT_HTML)):
        _run_source_adapter(SOURCE_ADAPTERS["fetch-redhat"], config, store)
    records = list(store.json.values())
    assert len(records) == 2
    by_slug = {r["product"]: r for r in records}
    sat = by_slug["red-hat-satellite"]
    assert sat["domain"] == "knowledge.tech"
    assert sat["technology"] == "satellite"
    # Unmapped slug: technology omitted, never invented (ADR-0202).
    assert "technology" not in by_slug["red-hat-quay"]


def test_fetch_confluence_uses_explicit_per_source_technology():
    page = {
        "title": "Build notes",
        "body": {"storage": {"value": "<p>content</p>"}},
        "ancestors": [],
        "metadata": {"labels": {"results": []}},
        "_links": {"webui": "/spaces/ARCH/pages/1"},
        "history": {"lastUpdated": {"when": "2026-08-01T00:00:00Z"}},
    }
    sources = (
        '[{"name": "satellite-build", "type": "cloud", "technology": "satellite", '
        '"baseUrl": "https://conf.test", "spaces": ["ARCH"], '
        '"requiredGroups": ["confluence-build-satellite"]}]'
    )
    config = _config(CONFLUENCE_SOURCES_JSON=sources, INGESTION_DOMAIN="knowledge.tech")
    store = FakeStore()
    with mock.patch.object(
        rag_ingestion.requests, "get",
        return_value=_FakeResponse(payload={"results": [page]}),
    ):
        _run_source_adapter(SOURCE_ADAPTERS["fetch-confluence"], config, store)
    (record,) = store.json.values()
    assert record["domain"] == "knowledge.tech"
    assert record["technology"] == "satellite"
    assert record["acl_groups"] == ["confluence-build-satellite"]


def test_fetch_confluence_scopes_via_ancestor_cql_when_directories_set():
    """VERIFIED live 2026-08-19: an unscoped `space="..." and type=page`
    search against a 500+-page space (expanding body.storage for every
    page) sat for 99 minutes before being killed. `directories` should
    resolve to a page id and search `ancestor=<id>` instead - server-side
    narrowing, not a client-side filter over the whole space.
    """
    page = {
        "title": "S0 : Satellite",
        "body": {"storage": {"value": "<p>content</p>"}},
        "ancestors": [
            {"title": "SXS Internal"},
            {"title": "Procédures"},
            {"title": "Technologie : Satellite"},
        ],
        "metadata": {"labels": {"results": []}},
        "_links": {"webui": "/spaces/SXSI/pages/123"},
        "history": {"lastUpdated": {"when": "2026-08-01T00:00:00Z"}},
    }
    sources = (
        '[{"name": "satellite-archi", "type": "cloud", "technology": "satellite", '
        '"baseUrl": "https://conf.test", "spaces": ["SXSI"], '
        '"directories": ["Proc\\u00e9dures/Technologie : Satellite"], '
        '"requiredGroups": ["confluence-archi-satellite"]}]'
    )
    config = _config(CONFLUENCE_SOURCES_JSON=sources, INGESTION_DOMAIN="knowledge.tech")
    store = FakeStore()
    cqls = []

    def fake_get(url, params=None, **_kwargs):
        cqls.append(params["cql"])
        if "title=" in params["cql"]:
            return _FakeResponse(payload={"results": [{"id": "999"}]})
        return _FakeResponse(payload={"results": [page]})

    with mock.patch.object(rag_ingestion.requests, "get", side_effect=fake_get):
        _run_source_adapter(SOURCE_ADAPTERS["fetch-confluence"], config, store)

    assert any('title="Technologie : Satellite"' in c for c in cqls), cqls
    assert any(c.startswith("ancestor=999") for c in cqls), cqls
    # The old unscoped fallback - no title/ancestor clause at all - must
    # not fire when a directory scope resolved successfully.
    assert 'space="SXSI" and type=page' not in cqls, cqls
    (record,) = store.json.values()
    assert record["technology"] == "satellite"


def test_fetch_confluence_resolves_a_shared_directory_scope_only_once():
    """The three tier entries for one tech (archi/build/run) share the
    same space+directories - the scope-id lookup should be cached across
    them, not repeated per source. They also share the matched pages
    themselves: the resulting record should merge every matching source's
    acl_groups, not have the last source silently overwrite the rest
    (VERIFIED live 2026-08-19 as a real bug: only 1/3 tiers' acl_groups
    ever survived)."""
    page = {
        "title": "S0 : Satellite",
        "body": {"storage": {"value": "<p>content</p>"}},
        "ancestors": [{"title": "Procédures"}, {"title": "Technologie : Satellite"}],
        "metadata": {"labels": {"results": []}},
        "_links": {"webui": "/spaces/SXSI/pages/123"},
        "history": {"lastUpdated": {"when": "2026-08-01T00:00:00Z"}},
    }
    directory = '"Proc\\u00e9dures/Technologie : Satellite"'
    sources = (
        "["
        '{"name": "satellite-archi", "technology": "satellite", "baseUrl": "https://conf.test", '
        f'"spaces": ["SXSI"], "directories": [{directory}], "requiredGroups": ["confluence-archi-satellite"]}},'
        '{"name": "satellite-build", "technology": "satellite", "baseUrl": "https://conf.test", '
        f'"spaces": ["SXSI"], "directories": [{directory}], "requiredGroups": ["confluence-build-satellite"]}}'
        "]"
    )
    config = _config(CONFLUENCE_SOURCES_JSON=sources, INGESTION_DOMAIN="knowledge.tech")
    store = FakeStore()
    title_lookups = []
    page_searches = []

    def fake_get(url, params=None, **_kwargs):
        if "title=" in params["cql"]:
            title_lookups.append(params["cql"])
            return _FakeResponse(payload={"results": [{"id": "999"}]})
        page_searches.append(params["cql"])
        return _FakeResponse(payload={"results": [page]})

    with mock.patch.object(rag_ingestion.requests, "get", side_effect=fake_get):
        _run_source_adapter(SOURCE_ADAPTERS["fetch-confluence"], config, store)

    # The scope id is resolved once and reused - only the resolution is
    # cached, not the per-source fetch itself (each source still searches).
    assert len(title_lookups) == 1, title_lookups
    assert len(page_searches) == 2, page_searches
    # Both sources match the same page - one merged record, not two
    # colliding writes with only the last source's acl_groups surviving.
    (record,) = store.json.values()
    assert record["acl_groups"] == [
        "confluence-archi-satellite",
        "confluence-build-satellite",
    ], record["acl_groups"]


# --- fetch-salesforce (knowledge.sales) -------------------------------------


def test_fetch_salesforce_writes_sales_metadata_from_fixture_records():
    sources = (
        '[{"object": "Opportunity", "fields": ["Id", "Name", "StageName", "Amount"], '
        '"dealType": "new-business", "requiredGroups": ["sales"]}]'
    )
    config = _config(
        INGESTION_DOMAIN="knowledge.sales",
        SALESFORCE_SOURCES_JSON=sources,
        SALESFORCE_INSTANCE_URL="https://sf.test",
        SALESFORCE_TOKEN="fixture-token",
    )
    store = FakeStore()
    payload = {
        "records": [
            {"Id": "006A1", "Name": "Big deal", "StageName": "Negotiation", "Amount": 10000},
            {"Id": "006A2", "Name": "Small deal", "StageName": "Closed Won", "Amount": 500},
        ]
    }
    with mock.patch.object(
        rag_ingestion.requests, "get", return_value=_FakeResponse(payload=payload)
    ) as fake_get:
        _run_source_adapter(SOURCE_ADAPTERS["fetch-salesforce"], config, store)
    assert fake_get.call_args.kwargs["headers"]["Authorization"] == "Bearer fixture-token"
    records = sorted(store.json.values(), key=lambda r: r["url"])
    assert len(records) == 2
    first = records[0]
    assert first["domain"] == "knowledge.sales"
    assert first["source_type"] == "salesforce-object"
    assert first["classification"] == "C2"
    assert first["acl_groups"] == ["sales"]
    assert first["sales"]["object"] == "Opportunity"
    assert first["sales"]["deal_type"] == "new-business"
    assert first["sales"]["status"] == "Negotiation"
    assert "Name: Big deal" in first["text"]


def test_fetch_salesforce_without_credentials_fails_closed():
    config = _config(
        INGESTION_DOMAIN="knowledge.sales",
        SALESFORCE_SOURCES_JSON='[{"object": "Opportunity"}]',
    )
    try:
        _run_source_adapter(SOURCE_ADAPTERS["fetch-salesforce"], config, FakeStore())
        raise AssertionError("expected SystemExit")
    except SystemExit as exc:
        assert "SALESFORCE_INSTANCE_URL" in str(exc)


# --- fetch-aramis (knowledge.adv) -------------------------------------------


def test_fetch_aramis_writes_adv_metadata_from_fixture_export():
    sources = '[{"name": "projects", "endpoint": "/api/projects", "projectType": "delivery"}]'
    config = _config(
        INGESTION_DOMAIN="knowledge.adv",
        ARAMIS_SOURCES_JSON=sources,
        ARAMIS_BASE_URL="https://aramis.test",
        ARAMIS_TOKEN="fixture-token",
    )
    store = FakeStore()
    payload = [
        {"id": 41, "name": "Refonte SI", "status": "active", "customer": "ACME", "budget": 120000},
    ]
    with mock.patch.object(
        rag_ingestion.requests, "get", return_value=_FakeResponse(payload=payload)
    ):
        _run_source_adapter(SOURCE_ADAPTERS["fetch-aramis"], config, store)
    (record,) = store.json.values()
    assert record["domain"] == "knowledge.adv"
    assert record["source_type"] == "aramis-export"
    assert record["url"] == "aramis://projects/41"
    assert record["adv"]["project_type"] == "delivery"
    assert record["adv"]["status"] == "active"
    assert record["adv"]["customer"] == "ACME"


# --- load-sxa-dump (knowledge.sxa-legacy, ADR-0216/WP-065) ------------------


_SXA_DUMP = """-- MySQL dump 10.11
-- Host: localhost    Database: sxa

-- Table structure for table `affaire`
CREATE TABLE `affaire` (
  `id` int(11) NOT NULL,
  `titre` varchar(255)
);
INSERT INTO `affaire` VALUES (1,'Contrat A'),(2,'Contrat B');

-- Table structure for table `devis`
CREATE TABLE `devis` (
  `id` int(11) NOT NULL
);
INSERT INTO `devis` VALUES (10),(11);
"""


class FakeMariaDBCursor:
    """Test double for pymysql's DictCursor - real enough to prove
    _load_sxa_dump's import/extraction flow without a live MariaDB.
    SHOW TABLES / SELECT * FROM <table> are served from the connection's
    pre-seeded fixture rows rather than actually interpreting the
    executed SQL - _import_sxa_dump_native's own statement-splitting is
    exercised separately (test_split_sql_statements_*)."""

    def __init__(self, conn):
        self._conn = conn
        self._result: list = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql):
        self._conn.executed.append(sql)
        stripped = sql.strip()
        if stripped.upper() == "SHOW TABLES":
            self._result = [{"Tables_in_sxa": t} for t in self._conn.tables]
        elif stripped.upper().startswith("SELECT * FROM"):
            table = stripped.split("`")[1]
            self._result = self._conn.rows.get(table, [])
        else:
            self._result = []

    def fetchall(self):
        return self._result


class FakeMariaDBConnection:
    def __init__(self, tables, rows):
        self.tables = tables  # SHOW TABLES order
        self.rows = rows  # table -> list of dict rows
        self.executed: list = []
        self.committed = False
        self.closed = False

    def cursor(self):
        return FakeMariaDBCursor(self)

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


def test_load_sxa_dump_natively_imports_and_writes_one_record_per_row():
    config = _config(
        INGESTION_DOMAIN="knowledge.sxa-legacy",
        SXA_DUMP_SCHEMA_S3_KEY="sxa.schema.sql",
        SXA_DUMP_DATA_S3_KEY="sxa.data.sql",
        SXA_SNAPSHOT_ID="2026-08",
        SXA_S3_BUCKET="sxa-bucket",
    )
    store = FakeStore()
    fake_conn = FakeMariaDBConnection(
        tables=["customers"],
        rows={"customers": [{"id": 1, "name": "Acme Corp", "phone": "0102030405"}]},
    )
    with mock.patch.object(rag_ingestion, "_fetch_sxa_dump_bytes", return_value=_SXA_DUMP.encode("utf-8")), \
         mock.patch.object(rag_ingestion, "_mariadb_connect", return_value=fake_conn):
        _run_source_adapter(SOURCE_ADAPTERS["load-sxa-dump"], config, store)

    # The dump's own CREATE TABLE/INSERT statements were actually executed
    # against the connection (native import, no schema translation).
    assert any("CREATE TABLE `affaire`" in s for s in fake_conn.executed)
    assert any("INSERT INTO `affaire`" in s for s in fake_conn.executed)
    assert fake_conn.committed
    assert fake_conn.closed

    records = list(store.json.values())
    assert len(records) == 1
    record = records[0]
    assert record["domain"] == "knowledge.sxa-legacy"
    assert record["classification"] == "C3"
    assert record["source_type"] == "sxa-mariadb"
    assert record["acl_groups"] == []
    assert record["sxa"]["snapshot_id"] == "2026-08"
    assert record["sxa"]["table"] == "customers"
    assert len(record["sxa"]["snapshot_checksum"]) == 64
    assert record["sxa"]["imported_at"]
    # 2026-08-23 amendment: no anonymization transform - content reaches
    # the embedded record exactly as imported.
    assert "Acme Corp" in record["text"]
    assert "0102030405" in record["text"]


def test_load_sxa_dump_reimport_of_same_snapshot_is_idempotent():
    config = _config(
        INGESTION_DOMAIN="knowledge.sxa-legacy",
        SXA_DUMP_SCHEMA_S3_KEY="sxa.schema.sql",
        SXA_DUMP_DATA_S3_KEY="sxa.data.sql",
        SXA_S3_BUCKET="sxa-bucket",
    )
    store = FakeStore()
    rows = {"customers": [{"id": 1, "name": "Acme Corp"}]}

    def _new_conn(*_args, **_kwargs):
        return FakeMariaDBConnection(tables=["customers"], rows=rows)

    with mock.patch.object(rag_ingestion, "_fetch_sxa_dump_bytes", return_value=_SXA_DUMP.encode("utf-8")), \
         mock.patch.object(rag_ingestion, "_mariadb_connect", side_effect=_new_conn):
        _run_source_adapter(SOURCE_ADAPTERS["load-sxa-dump"], config, store)
        first = {k: dict(v) for k, v in store.json.items()}
        _run_source_adapter(SOURCE_ADAPTERS["load-sxa-dump"], config, store)
    # Same keys, same content sha256s: detect-changes will see every doc
    # as unchanged, so re-running the same snapshot re-indexes nothing.
    assert set(store.json) == set(first)
    for key, record in store.json.items():
        assert record["sha256"] == first[key]["sha256"]


def test_load_sxa_dump_refuses_non_dump_content_and_missing_key():
    config = _config(
        INGESTION_DOMAIN="knowledge.sxa-legacy",
        SXA_DUMP_SCHEMA_S3_KEY="sxa.schema.sql",
        SXA_DUMP_DATA_S3_KEY="sxa.data.sql",
        SXA_S3_BUCKET="sxa-bucket",
    )
    with mock.patch.object(rag_ingestion, "_fetch_sxa_dump_bytes", return_value=b"SELECT 1; -- no table sections"):
        try:
            _run_source_adapter(SOURCE_ADAPTERS["load-sxa-dump"], config, FakeStore())
            raise AssertionError("expected SystemExit for non-dump content")
        except SystemExit as exc:
            assert "refusing to import" in str(exc)
    config2 = _config(INGESTION_DOMAIN="knowledge.sxa-legacy")
    try:
        _run_source_adapter(SOURCE_ADAPTERS["load-sxa-dump"], config2, FakeStore())
        raise AssertionError("expected SystemExit for missing key")
    except SystemExit as exc:
        assert "SXA_DUMP_SCHEMA_S3_KEY" in str(exc)


def test_import_sxa_dump_native_skips_create_view_statements():
    # Confirmed live 2026-08-23: this phpMyAdmin-style dump's views are
    # hardcoded to their original source database name ("PROD_sxa"),
    # which this MariaDB user has no grant on ("CREATE VIEW command
    # denied") - _import_sxa_dump_native must skip them rather than fail
    # the whole import, since _load_sxa_dump only ever reads base tables.
    dump = (
        "CREATE TABLE `commande` (`id` int);\n"
        "CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER "
        "VIEW `PROD_sxa`.`EXTRACT_SALES_202x` AS select `PROD_sxa`.`commande`.`id` "
        "AS `id` from `PROD_sxa`.`commande`;\n"
        "INSERT INTO `commande` VALUES (1);"
    )
    fake_conn = FakeMariaDBConnection(tables=["commande"], rows={"commande": [{"id": 1}]})
    rag_ingestion._import_sxa_dump_native(fake_conn, dump)
    assert not any("VIEW" in s.upper() for s in fake_conn.executed)
    assert any("CREATE TABLE `commande`" in s for s in fake_conn.executed)
    assert any("INSERT INTO `commande`" in s for s in fake_conn.executed)
    assert fake_conn.committed


def test_split_sql_statements_handles_semicolons_inside_quoted_values():
    dump = "INSERT INTO `t` VALUES (1,'a;b'),(2,\"c;d\");\nCREATE TABLE `u` (`id` int);"
    statements = rag_ingestion._split_sql_statements(dump)
    assert statements == [
        "INSERT INTO `t` VALUES (1,'a;b'),(2,\"c;d\")",
        "CREATE TABLE `u` (`id` int)",
    ]


def test_split_sql_statements_skips_comment_only_lines():
    dump = "-- just a comment\nSELECT 1;"
    assert rag_ingestion._split_sql_statements(dump) == ["SELECT 1"]


# --- fetch-sxa (knowledge.sxa, ADR-0217) -------------------------------------

_SXA_CORPUS_SCHEMA = """
CREATE TABLE `customers` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `revenue` decimal(10,2) DEFAULT NULL,
  `notes` text,
  PRIMARY KEY (`id`),
  KEY `idx_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

_SXA_CORPUS_DATA = (
    "INSERT INTO `customers` VALUES "
    "(1,'Acme, Inc.',1234.50,'Note with a comma, and a \\'quote\\''),"
    "(2,'Beta Corp',NULL,NULL);"
)


def test_parse_create_table_columns_skips_constraints_keeps_declared_order():
    columns = rag_ingestion._parse_create_table_columns(_SXA_CORPUS_SCHEMA)
    assert columns == {"customers": ["id", "name", "revenue", "notes"]}


def test_parse_insert_rows_handles_quoted_commas_escaped_quotes_and_null():
    columns = rag_ingestion._parse_create_table_columns(_SXA_CORPUS_SCHEMA)
    rows = list(rag_ingestion._parse_insert_rows(_SXA_CORPUS_DATA, columns))
    assert [r for _, r in rows] == [
        {"id": 1, "name": "Acme, Inc.", "revenue": 1234.5, "notes": "Note with a comma, and a 'quote'"},
        {"id": 2, "name": "Beta Corp", "revenue": None, "notes": None},
    ]


def test_fetch_sxa_writes_one_record_per_row_without_any_sql_engine():
    config = _config(
        INGESTION_DOMAIN="knowledge.sxa",
        SXA_CORPUS_SCHEMA_S3_KEY="sxa_data/sxa.schema.sql",
        SXA_CORPUS_DATA_S3_KEY="sxa_data/sxa.data.sql",
        SXA_CORPUS_S3_BUCKET="sxa-corpus-bucket",
    )
    store = FakeStore()

    def fake_fetch(_config, key):
        if key.endswith("schema.sql"):
            return _SXA_CORPUS_SCHEMA.encode("utf-8")
        return _SXA_CORPUS_DATA.encode("utf-8")

    with mock.patch.object(rag_ingestion, "_fetch_sxa_corpus_bytes", side_effect=fake_fetch):
        _run_source_adapter(SOURCE_ADAPTERS["fetch-sxa"], config, store)

    records = list(store.json.values())
    assert len(records) == 2
    (record,) = [r for r in records if "customers/1" in r["url"]]
    assert record["domain"] == "knowledge.sxa"
    assert record["classification"] == "C3"
    assert record["source_type"] == "sxa-corpus"
    assert record["sxa"]["table"] == "customers"
    assert len(record["sxa"]["checksum"]) == 64
    # Not redacted (ADR-0217 trusts the upstream anonymization claim) -
    # unlike load-sxa-dump, real-shaped values pass through as-is.
    assert "Acme" in record["text"]


def test_fetch_sxa_reimport_of_same_export_is_idempotent():
    config = _config(
        INGESTION_DOMAIN="knowledge.sxa",
        SXA_CORPUS_SCHEMA_S3_KEY="sxa_data/sxa.schema.sql",
        SXA_CORPUS_DATA_S3_KEY="sxa_data/sxa.data.sql",
        SXA_CORPUS_S3_BUCKET="sxa-corpus-bucket",
    )
    store = FakeStore()

    def fake_fetch(_config, key):
        if key.endswith("schema.sql"):
            return _SXA_CORPUS_SCHEMA.encode("utf-8")
        return _SXA_CORPUS_DATA.encode("utf-8")

    with mock.patch.object(rag_ingestion, "_fetch_sxa_corpus_bytes", side_effect=fake_fetch):
        _run_source_adapter(SOURCE_ADAPTERS["fetch-sxa"], config, store)
        first = {k: dict(v) for k, v in store.json.items()}
        _run_source_adapter(SOURCE_ADAPTERS["fetch-sxa"], config, store)
    assert set(store.json) == set(first)
    for key, record in store.json.items():
        assert record["sha256"] == first[key]["sha256"]


def test_fetch_sxa_refuses_non_schema_content_and_missing_keys():
    config = _config(INGESTION_DOMAIN="knowledge.sxa", SXA_CORPUS_S3_BUCKET="sxa-corpus-bucket")
    try:
        _run_source_adapter(SOURCE_ADAPTERS["fetch-sxa"], config, FakeStore())
        raise AssertionError("expected SystemExit for missing keys")
    except SystemExit as exc:
        assert "SXA_CORPUS_SCHEMA_S3_KEY" in str(exc)

    config2 = _config(
        INGESTION_DOMAIN="knowledge.sxa",
        SXA_CORPUS_SCHEMA_S3_KEY="sxa_data/sxa.schema.sql",
        SXA_CORPUS_DATA_S3_KEY="sxa_data/sxa.data.sql",
        SXA_CORPUS_S3_BUCKET="sxa-corpus-bucket",
    )
    with mock.patch.object(rag_ingestion, "_fetch_sxa_corpus_bytes", return_value=b"not a schema file"):
        try:
            _run_source_adapter(SOURCE_ADAPTERS["fetch-sxa"], config2, FakeStore())
            raise AssertionError("expected SystemExit for non-schema content")
        except SystemExit as exc:
            assert "refusing to parse" in str(exc)


# --- normalize carries domain/technology/extensions -------------------------


def test_normalize_carries_domain_technology_and_extensions_into_metadata():
    config = _config(INGESTION_DOMAIN="knowledge.sales")
    store = FakeStore()
    store.json["manifests/changeset.json"] = {
        "new": ["html1", "text1"], "changed": [], "deleted": [], "deleted_urls": [], "unchanged": [],
    }
    store.json["raw/html1.json"] = {
        "doc_id": "html1", "url": "https://docs.test/x", "title": "Doc",
        "raw_html": "<html><body><main><p>Hello world content.</p></main></body></html>",
        "domain": "knowledge.tech", "technology": "openshift",
        "product": "openshift-container-platform", "version": "4.20", "language": "en",
        "source_type": "product-doc", "classification": "C1", "acl_groups": [],
        "fetched_at": "2026-08-15T00:00:00Z", "provenance": "https://docs.test/x",
    }
    store.json["raw/text1.json"] = {
        "doc_id": "text1", "url": "https://sf.test/006A1", "title": "Big deal",
        "text": "Name: Big deal\nAmount: 10000",
        "domain": "knowledge.sales", "product": None, "version": None, "language": "en",
        "source_type": "salesforce-object", "classification": "C2", "acl_groups": ["sales"],
        "fetched_at": "2026-08-15T00:00:00Z", "provenance": "https://sf.test/006A1",
        "sales": {"object": "Opportunity", "deal_type": "new-business", "status": "Won"},
    }
    stage_normalize(config, store)
    html_meta = store.json["normalized/html1.json"]["metadata"]
    assert html_meta["domain"] == "knowledge.tech"
    assert html_meta["technology"] == "openshift"
    text_norm = store.json["normalized/text1.json"]
    assert text_norm["text"] == "Name: Big deal\nAmount: 10000"
    assert text_norm["metadata"]["domain"] == "knowledge.sales"
    assert text_norm["metadata"]["sales"]["deal_type"] == "new-business"
    assert "technology" not in text_norm["metadata"]


def test_normalize_defaults_missing_domain_to_the_run_domain():
    config = _config(INGESTION_DOMAIN="knowledge.tech")
    store = FakeStore()
    store.json["manifests/changeset.json"] = {
        "new": ["old1"], "changed": [], "deleted": [], "deleted_urls": [], "unchanged": [],
    }
    # A raw record written before WP-22 existed: no domain key at all.
    store.json["raw/old1.json"] = {
        "doc_id": "old1", "url": "https://docs.test/old", "title": "Old doc",
        "raw_html": "<html><body><main><p>Legacy content.</p></main></body></html>",
        "product": "red-hat-satellite", "version": "6.15", "language": "en",
        "source_type": "product-doc", "classification": "C1", "acl_groups": [],
        "fetched_at": "2026-08-15T00:00:00Z", "provenance": "https://docs.test/old",
    }
    stage_normalize(config, store)
    assert store.json["normalized/old1.json"]["metadata"]["domain"] == "knowledge.tech"


# --- WP-24 (ADR-0205/ADR-0109): freshness metadata --------------------------


def test_parse_duration_spec_supports_days_hours_minutes_and_none():
    assert _parse_duration_spec("7d").days == 7
    assert _parse_duration_spec("4h").total_seconds() == 4 * 3600
    assert _parse_duration_spec("5m").total_seconds() == 5 * 60
    assert _parse_duration_spec("none") is None
    assert _parse_duration_spec(None) is None
    assert _parse_duration_spec("") is None


def test_parse_duration_spec_rejects_a_malformed_value():
    try:
        _parse_duration_spec("banana")
        raise AssertionError("expected SystemExit")
    except SystemExit as exc:
        assert "not a valid duration spec" in str(exc)


def test_parse_http_last_modified_handles_valid_missing_and_malformed():
    assert _parse_http_last_modified("Wed, 21 Oct 2015 07:28:00 GMT") == "2015-10-21T07:28:00Z"
    assert _parse_http_last_modified(None) is None
    assert _parse_http_last_modified("") is None
    assert _parse_http_last_modified("not a valid http-date") is None


def _normalize_one(config, raw_record):
    store = FakeStore()
    store.json["manifests/changeset.json"] = {
        "new": ["doc1"], "changed": [], "deleted": [], "deleted_urls": [], "unchanged": [],
    }
    store.json["raw/doc1.json"] = raw_record
    stage_normalize(config, store)
    return store.json["normalized/doc1.json"]["metadata"]


def test_normalize_computes_indexed_at_and_stale_after_from_the_duration_spec():
    config = _config(INGESTION_DOMAIN="knowledge.sales", STALE_AFTER="4h")
    raw = {
        "doc_id": "doc1", "url": "https://sf.test/1", "title": "Deal", "text": "Name: Deal",
        "domain": "knowledge.sales", "source_type": "salesforce-object", "classification": "C2",
        "acl_groups": [], "provenance": "https://sf.test/1",
        "last_modified": "2026-08-14T10:00:00Z",
    }
    metadata = _normalize_one(config, raw)
    assert metadata["source_modified_at"] == "2026-08-14T10:00:00Z"
    assert metadata["indexed_at"]
    indexed_dt = datetime.strptime(metadata["indexed_at"], "%Y-%m-%dT%H:%M:%SZ")
    stale_dt = datetime.strptime(metadata["stale_after"], "%Y-%m-%dT%H:%M:%SZ")
    assert (stale_dt - indexed_dt) == timedelta(hours=4)


def test_normalize_omits_stale_after_for_sxa_legacy_regardless_of_spec():
    # Even a configured duration must not apply to the exempt domain -
    # the domain check comes first (ADR-0206's on-demand-only objective).
    config = _config(INGESTION_DOMAIN="knowledge.sxa-legacy", STALE_AFTER="7d")
    raw = {
        "doc_id": "doc1", "url": "sxa-dump://affaire", "title": "affaire", "text": "CREATE TABLE...",
        "domain": "knowledge.sxa-legacy", "source_type": "sxa-dump", "classification": "C3",
        "acl_groups": [], "provenance": "sxa-dump snapshot 2026-08",
    }
    metadata = _normalize_one(config, raw)
    assert "stale_after" not in metadata
    assert metadata["source_modified_at"] is None  # no last_modified, no fetched_at either


def test_normalize_omits_stale_after_when_no_duration_is_configured():
    config = _config(INGESTION_DOMAIN="knowledge.tech")  # STALE_AFTER unset
    raw = {
        "doc_id": "doc1", "url": "https://docs.test/x", "title": "Doc",
        "raw_html": "<html><body><main><p>Hello.</p></main></body></html>",
        "domain": "knowledge.tech", "source_type": "product-doc", "classification": "C1", "acl_groups": [],
        "fetched_at": "2026-08-15T00:00:00Z", "provenance": "https://docs.test/x",
    }
    metadata = _normalize_one(config, raw)
    assert "stale_after" not in metadata
    assert metadata["source_modified_at"] == "2026-08-15T00:00:00Z"  # fetched_at fallback


class _FakeValidateCursor:
    def execute(self, *_a, **_kw):
        pass

    def fetchone(self):
        return (1, 0)  # total=1, missing_embedding=0 - the DB-side check always "passes"

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _FakeValidateConn:
    def cursor(self):
        return _FakeValidateCursor()

    def close(self):
        pass


def _validate_store_with(metadata: dict) -> FakeStore:
    store = FakeStore()
    store.json["manifests/changeset.json"] = {
        "new": ["doc1"], "changed": [], "deleted": [], "deleted_urls": [], "unchanged": [],
    }
    store.json["normalized/doc1.chunks.json"] = {
        "doc_id": "doc1", "url": "https://example.test/1", "title": "Doc", "metadata": metadata,
        "chunks": [],
    }
    return store


def test_stage_validate_fails_closed_on_an_operational_chunk_missing_freshness_metadata():
    config = _config(INGESTION_DOMAIN="knowledge.tech")
    store = _validate_store_with({"domain": "knowledge.tech"})  # missing all three fields
    with mock.patch.object(rag_ingestion, "_pg_connect", return_value=_FakeValidateConn()):
        try:
            stage_validate(config, store)
            raise AssertionError("expected SystemExit")
        except SystemExit as exc:
            assert "freshness" in str(exc) or "validation" in str(exc)


def test_stage_validate_passes_a_complete_operational_chunk():
    config = _config(INGESTION_DOMAIN="knowledge.tech")
    store = _validate_store_with({
        "domain": "knowledge.tech",
        "source_modified_at": "2026-08-01T00:00:00Z",
        "indexed_at": "2026-08-15T00:00:00Z",
        "stale_after": "2026-08-22T00:00:00Z",
    })
    with mock.patch.object(rag_ingestion, "_pg_connect", return_value=_FakeValidateConn()):
        stage_validate(config, store)  # must not raise


def test_stage_validate_exempts_sxa_legacy_from_freshness_enforcement():
    config = _config(INGESTION_DOMAIN="knowledge.sxa-legacy")
    store = _validate_store_with({"domain": "knowledge.sxa-legacy"})  # missing all three, exempt
    with mock.patch.object(rag_ingestion, "_pg_connect", return_value=_FakeValidateConn()):
        stage_validate(config, store)  # must not raise


# --- WP-24 write-path invariant ---------------------------------------------


def test_fetch_stage_source_never_issues_a_write_http_verb_against_a_source_system():
    """ADR-0205: "RAG stays write-free - a mutation of a source system
    goes through a live tool capability, never through indexed
    retrieval/ingestion." The fetch stages here only ever read from
    Confluence/Salesforce/Aramis; the sole requests.post in this file is
    _embed_batch's call to the embedding service (a compute call, not a
    source-system mutation) - this test pins that down structurally so a
    future fetch-stage edit can't silently start writing back to a
    source."""
    import inspect

    for adapter in SOURCE_ADAPTERS.values():
        source = inspect.getsource(adapter.fetch)
        assert not re.search(r"requests\.(post|put|patch|delete)\s*\(", source), (
            f"{adapter.stage} contains a write-shaped HTTP call - fetch stages must stay read-only"
        )


# --- embed request contract --------------------------------------------------


def test_embed_batch_asks_the_server_to_truncate_oversized_chunks():
    """One chunk past the embedding model's max sequence length must not be
    able to 400-fail its whole batch (run 3, 2026-08-18: 13307/13324 chunks
    lost that way - preserved code blocks exceed any chunker budget, so a
    client-side budget alone can't prevent it). _embed_batch therefore always
    sends vLLM's truncate_prompt_tokens=-1."""
    config = _config()
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["payload"] = json
        return _FakeResponse({"data": [{"embedding": [0.0]} for _ in json["input"]]})

    with mock.patch.object(rag_ingestion.requests, "post", side_effect=fake_post):
        vectors = rag_ingestion._embed_batch(["a", "b"], config)
    assert captured["url"] == "http://embeddings.test/v1/embeddings"
    assert captured["payload"]["model"] == "test-model"
    assert captured["payload"]["truncate_prompt_tokens"] == -1
    assert len(vectors) == 2


TESTS = [
    test_every_fetch_stage_has_an_adapter_bound_to_one_domain,
    test_fetch_stage_for_the_wrong_domain_fails_closed_before_any_write,
    test_fetch_redhat_stamps_domain_and_canonical_technology,
    test_fetch_confluence_uses_explicit_per_source_technology,
    test_fetch_confluence_scopes_via_ancestor_cql_when_directories_set,
    test_fetch_confluence_resolves_a_shared_directory_scope_only_once,
    test_fetch_salesforce_writes_sales_metadata_from_fixture_records,
    test_fetch_salesforce_without_credentials_fails_closed,
    test_fetch_aramis_writes_adv_metadata_from_fixture_export,
    test_load_sxa_dump_natively_imports_and_writes_one_record_per_row,
    test_load_sxa_dump_reimport_of_same_snapshot_is_idempotent,
    test_load_sxa_dump_refuses_non_dump_content_and_missing_key,
    test_import_sxa_dump_native_skips_create_view_statements,
    test_split_sql_statements_handles_semicolons_inside_quoted_values,
    test_split_sql_statements_skips_comment_only_lines,
    test_parse_create_table_columns_skips_constraints_keeps_declared_order,
    test_parse_insert_rows_handles_quoted_commas_escaped_quotes_and_null,
    test_fetch_sxa_writes_one_record_per_row_without_any_sql_engine,
    test_fetch_sxa_reimport_of_same_export_is_idempotent,
    test_fetch_sxa_refuses_non_schema_content_and_missing_keys,
    test_normalize_carries_domain_technology_and_extensions_into_metadata,
    test_normalize_defaults_missing_domain_to_the_run_domain,
    test_parse_duration_spec_supports_days_hours_minutes_and_none,
    test_parse_duration_spec_rejects_a_malformed_value,
    test_parse_http_last_modified_handles_valid_missing_and_malformed,
    test_normalize_computes_indexed_at_and_stale_after_from_the_duration_spec,
    test_normalize_omits_stale_after_for_sxa_legacy_regardless_of_spec,
    test_normalize_omits_stale_after_when_no_duration_is_configured,
    test_stage_validate_fails_closed_on_an_operational_chunk_missing_freshness_metadata,
    test_stage_validate_passes_a_complete_operational_chunk,
    test_stage_validate_exempts_sxa_legacy_from_freshness_enforcement,
    test_fetch_stage_source_never_issues_a_write_http_verb_against_a_source_system,
    test_embed_batch_asks_the_server_to_truncate_oversized_chunks,
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
