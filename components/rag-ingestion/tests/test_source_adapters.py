"""WP-22 (ADR-0204 part 2): source-adapter interface and the three new
adapters, fixture-driven - no live source, S3 or database is ever
contacted (CI-safe).

Run:
    cd components/rag-ingestion && .venv/bin/python tests/test_source_adapters.py
"""
import os
import sys
import unittest.mock as mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import rag_ingestion  # noqa: E402
from rag_ingestion import (  # noqa: E402
    SOURCE_ADAPTERS,
    STAGES,
    IngestionConfig,
    _run_source_adapter,
    stage_normalize,
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
    def __init__(self, payload=None, text=""):
        self._payload = payload
        self.text = text

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


# --- load-sxa-dump (knowledge.sxa-legacy) -----------------------------------


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


def test_load_sxa_dump_writes_one_record_per_table_with_snapshot_discipline():
    config = _config(
        INGESTION_DOMAIN="knowledge.sxa-legacy",
        SXA_DUMP_S3_KEY="dumps/sxa-2026-08.sql",
        SXA_SNAPSHOT_ID="2026-08",
    )
    store = FakeStore()
    store.raw["dumps/sxa-2026-08.sql"] = _SXA_DUMP.encode("utf-8")
    _run_source_adapter(SOURCE_ADAPTERS["load-sxa-dump"], config, store)
    records = {r["url"]: r for r in store.json.values()}
    assert set(records) == {"sxa-dump://affaire", "sxa-dump://devis"}
    affaire = records["sxa-dump://affaire"]
    assert affaire["domain"] == "knowledge.sxa-legacy"
    assert affaire["classification"] == "C3"
    assert affaire["sxa"]["snapshot_id"] == "2026-08"
    assert affaire["sxa"]["table"] == "affaire"
    assert len(affaire["sxa"]["snapshot_checksum"]) == 64
    assert affaire["sxa"]["imported_at"]
    assert "CREATE TABLE `affaire`" in affaire["text"]


def test_load_sxa_dump_reimport_of_same_snapshot_is_idempotent():
    config = _config(
        INGESTION_DOMAIN="knowledge.sxa-legacy",
        SXA_DUMP_S3_KEY="dumps/sxa-2026-08.sql",
    )
    store = FakeStore()
    store.raw["dumps/sxa-2026-08.sql"] = _SXA_DUMP.encode("utf-8")
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
        SXA_DUMP_S3_KEY="dumps/not-a-dump.sql",
    )
    store = FakeStore()
    store.raw["dumps/not-a-dump.sql"] = b"SELECT 1; -- no table sections"
    try:
        _run_source_adapter(SOURCE_ADAPTERS["load-sxa-dump"], config, store)
        raise AssertionError("expected SystemExit for non-dump content")
    except SystemExit as exc:
        assert "refusing to index" in str(exc)
    config2 = _config(INGESTION_DOMAIN="knowledge.sxa-legacy")
    try:
        _run_source_adapter(SOURCE_ADAPTERS["load-sxa-dump"], config2, FakeStore())
        raise AssertionError("expected SystemExit for missing key")
    except SystemExit as exc:
        assert "SXA_DUMP_S3_KEY" in str(exc)


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


TESTS = [
    test_every_fetch_stage_has_an_adapter_bound_to_one_domain,
    test_fetch_stage_for_the_wrong_domain_fails_closed_before_any_write,
    test_fetch_redhat_stamps_domain_and_canonical_technology,
    test_fetch_confluence_uses_explicit_per_source_technology,
    test_fetch_salesforce_writes_sales_metadata_from_fixture_records,
    test_fetch_salesforce_without_credentials_fails_closed,
    test_fetch_aramis_writes_adv_metadata_from_fixture_export,
    test_load_sxa_dump_writes_one_record_per_table_with_snapshot_discipline,
    test_load_sxa_dump_reimport_of_same_snapshot_is_idempotent,
    test_load_sxa_dump_refuses_non_dump_content_and_missing_key,
    test_normalize_carries_domain_technology_and_extensions_into_metadata,
    test_normalize_defaults_missing_domain_to_the_run_domain,
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
