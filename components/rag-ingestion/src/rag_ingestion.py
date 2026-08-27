#!/usr/bin/env python3
"""Runtime entrypoint for the RAG ingestion pipeline.

The command contract is intentionally stable so the KFP pipeline can use a single
image for all stages (see files/pipeline.py.tpl in the Helm chart). Every stage
round-trips its state through S3 - KFP runs each stage in its own pod, so there is
no shared local disk between them:

    fetch-* / load-sxa-dump        -> <rawPrefix>/<doc_id>.json   (source adapters)
    detect-changes                 -> <manifestPrefix>/changeset.json (manifest.json is read, not written, here)
    normalize                      -> <normalizedPrefix>/<doc_id>.json
    chunk                          -> <normalizedPrefix>/<doc_id>.chunks.json
    embed                          -> (same file, chunks gain an "embedding" key)
    index-pgvector                 -> document_embeddings rows (data/rag/schema/004_rag_chunking.sql)
    validate                       -> exits non-zero if anything index-pgvector touched is incomplete;
                                       only on success does it write <manifestPrefix>/manifest.json,
                                       since that's the first point a document is confirmed durably
                                       indexed (see the WP-067 live-verification note on
                                       stage_detect_changes below for why this isn't done earlier)

ADR-0204 (WP-22): the fetch stages are implementations of one source-adapter
interface (SOURCE_ADAPTERS below), each bound to exactly one logical knowledge
domain: fetch-redhat + fetch-confluence -> knowledge.tech, fetch-salesforce ->
knowledge.sales, load-sxa-dump -> knowledge.sxa-legacy (ADR-0219: the
company's pre-2021 commercial record, parsed straight from S3 - no database
engine, no MCP tools). A pipeline run targets one domain (--domain /
INGESTION_DOMAIN): running a fetch stage against the wrong domain aborts
before writing anything (fail closed - the per-domain databases of ADR-0204
must never receive another domain's records), and every raw record is stamped
with the domain so normalize can carry it into chunk metadata (ADR-0202).
"""
import argparse
import fnmatch
import hashlib
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Dict, Optional
from urllib.parse import urljoin, urlparse

import boto3
import psycopg
import requests
import sqlparse
from bs4 import BeautifulSoup, NavigableString
from botocore.exceptions import ClientError
from pgvector.psycopg import register_vector

logger = logging.getLogger("rag_ingestion")

STAGES = (
    "fetch-redhat",
    "fetch-confluence",
    "fetch-salesforce",
    "load-sxa-dump",
    "detect-changes",
    "normalize",
    "chunk",
    "embed",
    "index-pgvector",
    "validate",
    "reconcile-acls",
)

DEFAULT_DOMAIN = "knowledge.tech"

# ADR-0202's canonical cross-source `technology` vocabulary
# (knowledge/tech/domain.yaml technology_vocabulary) keyed by
# docs.redhat.com productSlug. Deliberately partial: an unmapped slug gets
# NO technology key (omit, never invent) - extending the vocabulary means
# editing knowledge/tech/domain.yaml and this map together. Confluence
# sources carry an explicit per-source `technology` value in
# gitops/charts/rag-ingestion/values.yaml instead of a mapping here.
TECHNOLOGY_BY_PRODUCT_SLUG = {
    "red-hat-satellite": "satellite",
    "openshift-container-platform": "openshift",
    "red-hat-openshift-ai-self-managed": "openshift-ai",
    "red-hat-build-of-keycloak": "keycloak",
}

# ADR-0205/WP-24: the domains an operational-source freshness enforcement
# applies to are every domain EXCEPT these - a mirror of
# components/rag-service/app/search.py's own _IMMUTABLE_LEGACY_DOMAINS
# constant. The two are intentionally maintained separately: ingestion and
# rag-service are independently built/deployed images with no shared
# Python package between them (the same reason the technology map above
# and knowledge/tech/domain.yaml's vocabulary are a documented, manually
# kept-in-sync pair rather than one shared source file).
_IMMUTABLE_LEGACY_DOMAINS = {"knowledge.sxa-legacy"}
_REQUIRED_FRESHNESS_FIELDS = ("source_modified_at", "indexed_at", "stale_after")

_DURATION_RE = re.compile(r"^(\d+)([dhm])$")


def _parse_duration_spec(spec: Optional[str]) -> Optional[timedelta]:
    """Parses a knowledge/<domain>/domain.yaml-mirroring duration spec
    ("7d", "4h", "5m") from the STALE_AFTER chart value into a timedelta;
    "none"/absent (knowledge.sxa-legacy's on-demand objective, and any
    domain that simply hasn't set one) means "never compute stale_after
    for this run's chunks" - not "compute it as zero", which would mark
    everything stale immediately."""
    if not spec or spec.strip().lower() == "none":
        return None
    match = _DURATION_RE.match(spec.strip())
    if not match:
        raise SystemExit(
            f"STALE_AFTER={spec!r} is not a valid duration spec - expected "
            "'<int>d', '<int>h', '<int>m', or 'none'"
        )
    amount, unit = int(match.group(1)), match.group(2)
    if unit == "d":
        return timedelta(days=amount)
    if unit == "h":
        return timedelta(hours=amount)
    return timedelta(minutes=amount)


DOC_LINK_PATTERN = re.compile(r"/(html|html-single)/")
MAX_DISCOVERED_LINKS = 50
HTTP_TIMEOUT_SECONDS = 30
HTTP_USER_AGENT = "zuno-rag-ingestion/1.0 (+https://github.com/startxfr/zuno-demo)"


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


@dataclass
class IngestionConfig:
    # ADR-0204 (WP-22): the one logical knowledge domain this pipeline run
    # targets. Selects which source adapters may run and is stamped into
    # every record's metadata; the per-domain database identity arrives
    # through the same PG* env vars as before, wired per domain by the
    # chart (the deploy-side counterpart of
    # platform/bindings/knowledge/bindings.yaml).
    domain: str

    redhat_sources: list
    confluence_sources: list
    salesforce_sources: list

    salesforce_instance_url: Optional[str]
    salesforce_token: Optional[str]

    # load-sxa-dump reads the operator-supplied, approved snapshot from the
    # SXA corpus bucket (ADR-0025: no dump ever lives in git; a separate
    # bucket from s3_bucket above, which holds unrelated corpus content).
    # It ships as a schema.sql/data.sql key pair, both named below.
    sxa_dump_schema_s3_key: Optional[str]
    sxa_dump_data_s3_key: Optional[str]
    sxa_snapshot_id: Optional[str]
    sxa_s3_endpoint: str
    sxa_s3_bucket: str
    sxa_s3_region: str
    sxa_s3_path_style: bool
    sxa_aws_access_key_id: Optional[str]
    sxa_aws_secret_access_key: Optional[str]

    # ADR-0216: the MariaDB database the dump imports natively into - the
    # live query target for real SXA content (sales-db in mariadb mode);
    # separate from pg_host/pg_database above, which stays the
    # local-dev/CI fixture path (ADR-0016, superseded for the live target
    # only).


    # ADR-0205/WP-24: this run's domain's freshness objective, realized as
    # a duration spec ("7d"/"4h"/"5m"/"none") - see _parse_duration_spec.
    # Mirrors knowledge/<domain>/domain.yaml's freshness.operation_classes.
    # semantic-read.max_staleness (a human-maintained mirror, the same
    # pattern WP-22 established for schedule.cron / freshness.objective).
    stale_after_spec: Optional[str]

    s3_endpoint: str
    s3_bucket: str
    s3_region: str
    s3_path_style: bool
    raw_prefix: str
    normalized_prefix: str
    manifest_prefix: str
    failed_prefix: str
    aws_access_key_id: Optional[str]
    aws_secret_access_key: Optional[str]

    pg_host: str
    pg_port: int
    pg_database: str
    pg_schema: str
    pg_sslmode: str
    pg_user: Optional[str]
    pg_password: Optional[str]

    embedding_endpoint: str
    embedding_model: str
    embedding_dimensions: int
    embedding_batch_size: int
    embedding_api_token: Optional[str]

    confluence_token: Optional[str]
    confluence_username: Optional[str]

    chunk_strategy: str
    chunk_max_tokens: int
    chunk_overlap_tokens: int
    chunk_preserve_code_blocks: bool
    chunk_preserve_tables: bool

    corpus_incremental: bool
    corpus_hash_algorithm: str
    corpus_delete_orphans: bool

    # WP-57: both concurrency knobs default to a conservative worker count
    # (network/S3-latency-bound work, not CPU-bound - higher than the CPU
    # count is fine and expected). Configurable rather than hardcoded so an
    # operator can tune per-cluster network conditions without a code
    # change. fetch_redhat_concurrency bounds the per-source page-fetch
    # pool in _fetch_redhat; fetch_sxa_write_concurrency bounds the
    # per-row S3-write pool in _load_sxa_dump.
    fetch_redhat_concurrency: int
    fetch_sxa_write_concurrency: int
    # ADR-0219 (2026-08-26): the same treatment for the four stages that
    # were still strictly serial. The SXA dump renders one document per
    # table row - 314,428 of them, measured live - and at one-to-two S3
    # round-trips per document each of these stages took hours, so no full
    # run ever survived long enough to index anything. Same rationale as the two knobs above:
    # S3-latency-bound, not CPU-bound, so worker counts above the CPU count
    # are expected. embed_concurrency bounds in-flight embedding REQUESTS
    # (each already carrying embedding_batch_size chunks), so it multiplies
    # against the predictor's own capacity - keep it modest.
    normalize_concurrency: int
    chunk_concurrency: int
    embed_concurrency: int
    index_read_concurrency: int

    # WP-58: bounds the per-document S3 GET pool that rebuilds
    # detect-changes' "current" state (network/S3-latency-bound work,
    # same rationale as the two fields above - a live SXA run's
    # raw prefix held 314,428 objects, exposing the previously
    # sequential read loop as the pipeline's next bottleneck).
    detect_changes_read_concurrency: int


def _env(name: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    val = os.environ.get(name, default)
    if required and not val:
        raise SystemExit(f"Missing required environment variable: {name}")
    return val


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None or val == "":
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    val = os.environ.get(name)
    if not val:
        return default
    return int(val)


def _env_json(name: str, default: Any) -> Any:
    val = os.environ.get(name)
    if not val:
        return default
    try:
        return json.loads(val)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in environment variable {name}: {exc}") from exc


def load_config() -> IngestionConfig:
    return IngestionConfig(
        domain=os.environ.get("INGESTION_DOMAIN") or DEFAULT_DOMAIN,
        redhat_sources=_env_json("REDHAT_SOURCES_JSON", []),
        confluence_sources=_env_json("CONFLUENCE_SOURCES_JSON", []),
        salesforce_sources=_env_json("SALESFORCE_SOURCES_JSON", []),
        salesforce_instance_url=os.environ.get("SALESFORCE_INSTANCE_URL"),
        salesforce_token=os.environ.get("SALESFORCE_TOKEN"),
        sxa_dump_schema_s3_key=os.environ.get("SXA_DUMP_SCHEMA_S3_KEY"),
        sxa_dump_data_s3_key=os.environ.get("SXA_DUMP_DATA_S3_KEY"),
        sxa_snapshot_id=os.environ.get("SXA_SNAPSHOT_ID"),
        sxa_s3_endpoint=os.environ.get("SXA_S3_ENDPOINT", ""),
        sxa_s3_bucket=os.environ.get("SXA_S3_BUCKET", ""),
        sxa_s3_region=os.environ.get("SXA_S3_REGION", ""),
        sxa_s3_path_style=_env_bool("SXA_S3_PATH_STYLE", False),
        sxa_aws_access_key_id=os.environ.get("SXA_AWS_ACCESS_KEY_ID"),
        sxa_aws_secret_access_key=os.environ.get("SXA_AWS_SECRET_ACCESS_KEY"),
        stale_after_spec=os.environ.get("STALE_AFTER"),
        s3_endpoint=os.environ.get("S3_ENDPOINT", ""),
        s3_bucket=_env("S3_BUCKET", required=True),
        s3_region=os.environ.get("S3_REGION", ""),
        s3_path_style=_env_bool("S3_PATH_STYLE", False),
        raw_prefix=os.environ.get("S3_RAW_PREFIX", "raw"),
        normalized_prefix=os.environ.get("S3_NORMALIZED_PREFIX", "normalized"),
        manifest_prefix=os.environ.get("S3_MANIFEST_PREFIX", "manifests"),
        failed_prefix=os.environ.get("S3_FAILED_PREFIX", "failed"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        pg_host=_env("PGHOST", required=True),
        pg_port=_env_int("PGPORT", 5432),
        pg_database=_env("PGDATABASE", required=True),
        pg_schema=os.environ.get("PGSCHEMA", "public"),
        pg_sslmode=os.environ.get("PGSSLMODE", "require"),
        pg_user=os.environ.get("PGUSER"),
        pg_password=os.environ.get("PGPASSWORD"),
        embedding_endpoint=_env("EMBEDDING_ENDPOINT", required=True),
        embedding_model=_env("EMBEDDING_MODEL", required=True),
        embedding_dimensions=_env_int("EMBEDDING_DIMENSIONS", 1024),
        embedding_batch_size=_env_int("EMBEDDING_BATCH_SIZE", 16),
        embedding_api_token=os.environ.get("EMBEDDING_API_TOKEN"),
        confluence_token=os.environ.get("CONFLUENCE_TOKEN"),
        confluence_username=os.environ.get("CONFLUENCE_USERNAME"),
        chunk_strategy=os.environ.get("CHUNKING_STRATEGY", "structural"),
        chunk_max_tokens=_env_int("CHUNK_MAX_TOKENS", 700),
        chunk_overlap_tokens=_env_int("CHUNK_OVERLAP_TOKENS", 100),
        chunk_preserve_code_blocks=_env_bool("CHUNK_PRESERVE_CODE_BLOCKS", True),
        chunk_preserve_tables=_env_bool("CHUNK_PRESERVE_TABLES", True),
        corpus_incremental=_env_bool("CORPUS_INCREMENTAL", True),
        corpus_hash_algorithm=os.environ.get("CORPUS_HASH_ALGORITHM", "sha256"),
        corpus_delete_orphans=_env_bool("CORPUS_DELETE_ORPHANS", True),
        fetch_redhat_concurrency=_env_int("FETCH_REDHAT_CONCURRENCY", 8),
        fetch_sxa_write_concurrency=_env_int("FETCH_SXA_WRITE_CONCURRENCY", 8),
        detect_changes_read_concurrency=_env_int("DETECT_CHANGES_READ_CONCURRENCY", 16),
        normalize_concurrency=_env_int("NORMALIZE_CONCURRENCY", 16),
        chunk_concurrency=_env_int("CHUNK_CONCURRENCY", 16),
        embed_concurrency=_env_int("EMBED_CONCURRENCY", 4),
        index_read_concurrency=_env_int("INDEX_READ_CONCURRENCY", 16),
    )


# --------------------------------------------------------------------------
# S3-backed corpus store
# --------------------------------------------------------------------------


class CorpusStore:
    """Thin S3 wrapper - every stage's state lives here, not on local disk."""

    def __init__(self, config: IngestionConfig):
        self._bucket = config.s3_bucket
        from botocore.config import Config as BotoClientConfig

        client_kwargs: dict = {
            "region_name": config.s3_region or None,
            "aws_access_key_id": config.aws_access_key_id,
            "aws_secret_access_key": config.aws_secret_access_key,
            # Bounded timeouts + retries: in-cluster S3 transfers on this
            # platform hang intermittently (an index run can sit
            # idle-in-transaction for minutes inside a get_json).
            # botocore's legacy defaults can stall a stage for a long time;
            # fail the call fast and let the retry mode handle transients.
            "config": BotoClientConfig(
                s3={"addressing_style": "path" if config.s3_path_style else "auto"},
                connect_timeout=10,
                read_timeout=60,
                retries={"max_attempts": 4, "mode": "standard"},
                # WP-58: botocore's default (10) is below
                # detect_changes_read_concurrency's default (16) - without
                # this, excess threads would queue for a free pooled
                # connection instead of actually running in parallel,
                # silently capping the gain this store's callers pay for.
                max_pool_connections=32,
            ),
        }
        if config.s3_endpoint:
            client_kwargs["endpoint_url"] = config.s3_endpoint
        self._client = boto3.client("s3", **client_kwargs)

    def put_json(self, key: str, obj: Any) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=json.dumps(obj, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )

    def get_json(self, key: str) -> Any:
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in ("NoSuchKey", "404"):
                return None
            raise
        return json.loads(resp["Body"].read())

    def list_keys(self, prefix: str) -> list:
        paginator = self._client.get_paginator("list_objects_v2")
        keys = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys

    def get_bytes(self, key: str) -> Optional[bytes]:
        """Raw object read - load-sxa-dump's snapshot file is a SQL dump,
        not JSON."""
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in ("NoSuchKey", "404"):
                return None
            raise
        return resp["Body"].read()


def doc_id_for(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_http_last_modified(value: Optional[str]) -> Optional[str]:
    """ADR-0205/WP-24: best-effort source_modified_at signal for product
    docs - docs.redhat.com pages carry no other last-modified field this
    pipeline can read. Many pages omit this header entirely (returns None
    then, same as if it were never attempted) - stage_normalize's fallback
    to fetched_at covers that case, documented there."""
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_language(code: Optional[str]) -> str:
    return (code or "en").split("-")[0].lower()


# --------------------------------------------------------------------------
# HTTP helpers
# --------------------------------------------------------------------------


def _http_get(url: str, **kwargs) -> requests.Response:
    headers = kwargs.pop("headers", {})
    headers.setdefault("User-Agent", HTTP_USER_AGENT)
    resp = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT_SECONDS, **kwargs)
    resp.raise_for_status()
    return resp


def _matches_filters(url: str, include: list, exclude: list) -> bool:
    if exclude and any(fnmatch.fnmatch(url, pattern) for pattern in exclude):
        return False
    if include:
        return any(fnmatch.fnmatch(url, pattern) for pattern in include)
    return True


def _discover_doc_links(base_url: str, soup: BeautifulSoup, limit: int = MAX_DISCOVERED_LINKS) -> list:
    """Finds same-book links from a docs.redhat.com landing/TOC page.

    html-single pages already contain the whole book, so this typically finds
    little/nothing extra for them; multi-page/landing pages yield their real
    chapter links here instead.
    """
    parsed_base = urlparse(base_url)
    found: list = []
    seen = {base_url}
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"]).split("#", 1)[0]
        parsed = urlparse(href)
        if parsed.netloc != parsed_base.netloc or not DOC_LINK_PATTERN.search(parsed.path):
            continue
        if href in seen:
            continue
        seen.add(href)
        found.append(href)
        if len(found) >= limit:
            logger.warning("Capped documentation link discovery at %d links for %s", limit, base_url)
            break
    return found


def _extract_title_and_text(html: str) -> tuple:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    title_tag = soup.find("h1") or soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""
    main = soup.find("main") or soup.find(attrs={"role": "main"}) or soup.body or soup
    text = main.get_text("\n", strip=True) if main is not None else soup.get_text("\n", strip=True)
    return title, text


# --------------------------------------------------------------------------
# Source adapters (ADR-0204, WP-22)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceAdapter:
    """One entry per source system: the stage name the KFP DAG invokes, the
    single knowledge domain whose corpus the adapter feeds, and the fetch
    callable. Every adapter shares the same contract - read its own slice
    of IngestionConfig, write one raw record per document to
    <rawPrefix>/<doc_id>.json through the same CorpusStore round-trip,
    stamp `domain` (and `technology` where the canonical vocabulary
    applies) on each record, and return how many records it wrote."""

    stage: str
    domain: str
    fetch: Callable[[IngestionConfig, CorpusStore], int]


def _run_source_adapter(adapter: SourceAdapter, config: IngestionConfig, store: CorpusStore) -> None:
    if config.domain != adapter.domain:
        # Fail closed BEFORE any write: a run targeting one domain must
        # never produce raw records for another (they would be indexed
        # into that run's database with the wrong domain metadata).
        raise SystemExit(
            f"{adapter.stage}: adapter feeds {adapter.domain} but this run targets "
            f"{config.domain} (INGESTION_DOMAIN/--domain) - refusing to fetch"
        )
    written = adapter.fetch(config, store)
    logger.info("%s: wrote %d raw documents", adapter.stage, written)


# --------------------------------------------------------------------------
# fetch-redhat (knowledge.tech)
# --------------------------------------------------------------------------


def _build_redhat_record(source: dict, url: str, page) -> Optional[dict]:
    """Builds one fetch-redhat record from an already-fetched response, or
    None if the page has no extractable text (skip - unchanged from the
    pre-WP-57 behavior)."""
    title, text = _extract_title_and_text(page.text)
    if not text.strip():
        return None
    doc_id = doc_id_for(url)
    record = {
        "doc_id": doc_id,
        "url": url,
        "title": title or url,
        "raw_html": page.text,
        "domain": "knowledge.tech",
        "product": source["productSlug"],
        "version": source["version"],
        "language": _normalize_language((source.get("languages") or ["en-US"])[0]),
        "source_type": "product-doc",
        "classification": "C1",
        "acl_groups": [],
        "fetched_at": _utcnow_iso(),
        "sha256": hashlib.sha256(page.text.encode("utf-8")).hexdigest(),
        "provenance": url,
        "last_modified": _parse_http_last_modified(page.headers.get("Last-Modified")),
        # WP-57: enables a conditional GET (If-None-Match) against this
        # same URL on the next run.
        "etag": page.headers.get("ETag"),
    }
    technology = TECHNOLOGY_BY_PRODUCT_SLUG.get(source["productSlug"])
    if technology:
        record["technology"] = technology
    return record


def _fetch_redhat_one(config: IngestionConfig, store: CorpusStore, source: dict, url: str) -> bool:
    """Fetches and stores one page, run concurrently across a source's
    discovered URLs (WP-57 - sequential per-page fetching was the
    dominant cost of fetch-redhat). Uses a conditional GET against any
    ETag/Last-Modified this URL's raw record carries from a previous run:
    a 304 leaves that record untouched rather than re-fetching/re-parsing
    it - safe because nothing ever purges raw/<domain>/ between runs, so
    detect-changes still finds the existing file. Returns True if a
    record was (re)written."""
    doc_id = doc_id_for(url)
    raw_key = f"{config.raw_prefix}/{doc_id}.json"
    previous = store.get_json(raw_key)
    headers: Dict[str, str] = {}
    if previous:
        if previous.get("etag"):
            headers["If-None-Match"] = previous["etag"]
        if previous.get("last_modified"):
            headers["If-Modified-Since"] = previous["last_modified"]
    try:
        page = _http_get(url, headers=headers)
    except requests.RequestException as exc:
        logger.error("fetch-redhat: failed to fetch %s: %s", url, exc)
        return False
    if page.status_code == 304:
        return False
    record = _build_redhat_record(source, url, page)
    if record is None:
        return False
    store.put_json(raw_key, record)
    return True


def _fetch_redhat(config: IngestionConfig, store: CorpusStore) -> int:
    fetched = 0
    for source in config.redhat_sources:
        if not source.get("enabled", True):
            continue
        if source.get("fetchMode") == "pdf":
            logger.warning(
                "fetchMode=pdf is not implemented yet for %s %s - skipping",
                source.get("product"), source.get("version"),
            )
            continue
        base_url = source["documentationUrl"]
        try:
            base_resp = _http_get(base_url)
        except requests.RequestException as exc:
            logger.error("fetch-redhat: failed to fetch %s: %s", base_url, exc)
            continue
        soup = BeautifulSoup(base_resp.text, "lxml")
        urls = [base_url] + _discover_doc_links(base_url, soup)
        include = source.get("include") or []
        exclude = source.get("exclude") or []
        urls = [u for u in dict.fromkeys(urls) if _matches_filters(u, include, exclude)]

        # base_url's response is already in hand (fetched unconditionally
        # above to discover links) - store it directly rather than
        # re-fetching it conditionally. WP-57: every OTHER discovered URL
        # runs through the concurrent conditional-GET path below.
        base_record = _build_redhat_record(source, base_url, base_resp)
        if base_record is not None:
            store.put_json(f"{config.raw_prefix}/{base_record['doc_id']}.json", base_record)
            fetched += 1

        remaining = [u for u in urls if u != base_url]
        if remaining:
            with ThreadPoolExecutor(max_workers=max(1, config.fetch_redhat_concurrency)) as pool:
                results = pool.map(lambda u: _fetch_redhat_one(config, store, source, u), remaining)
                fetched += sum(1 for written in results if written)
    return fetched


# --------------------------------------------------------------------------
# fetch-confluence (knowledge.tech)
# --------------------------------------------------------------------------


def _confluence_auth(config: IngestionConfig):
    if config.confluence_username and config.confluence_token:
        return (config.confluence_username, config.confluence_token)
    if config.confluence_token:
        token = config.confluence_token

        def _bearer(req):
            req.headers["Authorization"] = f"Bearer {token}"
            return req

        return _bearer
    return None


def _ancestor_path_matches(ancestor_titles: list, directory: str) -> bool:
    """Best-effort: Confluence has no literal filesystem directories, only a
    page hierarchy by title. A directory entry like "Satellite/Build" matches
    when every named segment appears, in order, among the page's ancestors.
    """
    wanted = [p for p in directory.split("/") if p]
    if not wanted:
        return True
    idx = 0
    for title in ancestor_titles:
        if title == wanted[idx]:
            idx += 1
            if idx == len(wanted):
                return True
    return False


def _resolve_confluence_scope_id(base_url: str, auth, space: str, title: str) -> Optional[str]:
    """Resolve a directory segment's title to its Confluence page id within
    one space, so the fetch loop below can scope its search with CQL's
    `ancestor=<id>` instead of paging through the entire space. Confluence
    enforces unique page titles within a space, so this is unambiguous.
    """
    try:
        resp = requests.get(
            f"{base_url}/wiki/rest/api/content/search",
            params={
                "cql": f'space="{space}" and type=page and title="{title}"',
                "limit": 5,
            },
            auth=auth,
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error(
            "fetch-confluence: could not resolve directory scope '%s' in space %s: %s",
            title, space, exc,
        )
        return None
    results = resp.json().get("results", [])
    return results[0]["id"] if results else None


def _fetch_confluence(config: IngestionConfig, store: CorpusStore) -> int:
    if not config.confluence_sources:
        logger.info("fetch-confluence: no confluence sources configured")
        return 0
    auth = _confluence_auth(config)
    # A space like SXSI can hold 500+ pages, and every enabled source used
    # to run an unscoped `space="..." and type=page` search - fetching+
    # expanding body.storage for EVERY page in the space, filtering by
    # directories client-side only afterward - once per confluence[] entry,
    # each independently re-scanning the same space. That can leave a
    # pipeline run sitting on this stage for an hour or more with zero log
    # output. CQL's `ancestor=<page id>` clause does this filtering
    # server-side instead: resolving a directory's last title segment to a
    # page id (cached per space+title, so sources sharing the same
    # directories only resolve once) turns a full-space scan into a single
    # ~1s scoped request. `_ancestor_path_matches` is still applied to each
    # result below - unchanged semantics, just against a pre-narrowed set.
    scope_id_cache: Dict[tuple, Optional[str]] = {}
    # The three tier entries per tech (archi/build/run) intentionally
    # target the same directory tree, differentiated only by
    # requiredGroups (ADR-0330) - doc_id is purely URL-derived, so writing
    # immediately per source let whichever source processed a shared page
    # LAST silently overwrite the earlier sources' acl_groups, dropping
    # most records. A real access-control bug: architects could lose
    # visibility a page should have granted them, or a lower tier could
    # inherit access it shouldn't have. Records are now accumulated in
    # memory across every source, merging acl_groups (union,
    # order-preserving) into one entry per doc_id instead of overwriting,
    # with a single deduplicated write per page at the end.
    records_by_doc_id: Dict[str, dict] = {}
    for source in config.confluence_sources:
        if not source.get("enabled", True):
            continue
        base_url = source["baseUrl"].rstrip("/")
        directories = source.get("directories") or []
        exclude_labels = set(source.get("excludeLabels") or [])
        required_groups = source.get("requiredGroups") or []

        for space in source.get("spaces") or []:
            # One search per resolvable directory scope, or a single
            # unscoped space-wide search when no directories are set
            # (operator intent: ingest the whole space) or a scope
            # couldn't be resolved (falls back rather than silently
            # fetching nothing).
            search_cqls = []
            for directory in directories:
                last_segment = directory.rsplit("/", 1)[-1]
                cache_key = (base_url, space, last_segment)
                if cache_key not in scope_id_cache:
                    scope_id_cache[cache_key] = _resolve_confluence_scope_id(
                        base_url, auth, space, last_segment
                    )
                scope_id = scope_id_cache[cache_key]
                if scope_id:
                    search_cqls.append(f'ancestor={scope_id} and type=page')
            if not search_cqls:
                search_cqls = [f'space="{space}" and type=page']

            for search_cql in search_cqls:
                # `start=`/`limit=` offset paging silently does NOT advance
                # for `ancestor=`-filtered CQL searches - every request
                # returns the identical first page regardless of `start`,
                # even though the response echoes back the requested
                # `start` value. That turns the old `while ... start +=
                # limit` loop into a genuine infinite loop whenever a scope
                # has more than one page of results - worse than the plain
                # space-wide scan it replaced. `_links.next` cursor-based
                # pagination advances correctly for both this and the
                # unscoped fallback query below, so it's used universally.
                next_url = f"{base_url}/wiki/rest/api/content/search"
                next_params = {
                    "cql": search_cql,
                    "limit": 25,
                    "expand": "body.storage,ancestors,history.lastUpdated,metadata.labels",
                }
                while next_url:
                    try:
                        resp = requests.get(
                            next_url,
                            params=next_params,
                            auth=auth,
                            timeout=HTTP_TIMEOUT_SECONDS,
                        )
                        resp.raise_for_status()
                    except requests.RequestException as exc:
                        logger.error("fetch-confluence: search failed for space %s: %s", space, exc)
                        break
                    payload = resp.json()
                    results = payload.get("results", [])
                    for page in results:
                        labels = {
                            label["name"]
                            for label in page.get("metadata", {}).get("labels", {}).get("results", [])
                        }
                        if labels & exclude_labels:
                            continue
                        ancestor_titles = [a["title"] for a in page.get("ancestors", [])]
                        if directories and not any(
                            _ancestor_path_matches(ancestor_titles, directory) for directory in directories
                        ):
                            continue
                        html = page.get("body", {}).get("storage", {}).get("value", "")
                        if not html.strip():
                            continue
                        web_ui = page.get("_links", {}).get("webui", "")
                        page_url = f"{base_url}/wiki{web_ui}"
                        doc_id = doc_id_for(page_url)
                        existing = records_by_doc_id.get(doc_id)
                        if existing:
                            # Same page already matched by an earlier
                            # source (typically a sibling tier sharing the
                            # same directory tree) - merge, don't overwrite.
                            existing["acl_groups"] = list(
                                dict.fromkeys(existing["acl_groups"] + required_groups)
                            )
                            continue
                        record = {
                            "doc_id": doc_id,
                            "url": page_url,
                            "title": page.get("title", page_url),
                            "raw_html": html,
                            "domain": "knowledge.tech",
                            "product": source.get("name", space),
                            "version": None,
                            "language": "en",
                            "source_type": "confluence",
                            "classification": "C2",
                            "acl_groups": list(required_groups),
                            "fetched_at": _utcnow_iso(),
                            "sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
                            "provenance": page_url,
                            "last_modified": page.get("history", {}).get("lastUpdated", {}).get("when"),
                        }
                        # Explicit per-source canonical value (values.yaml
                        # confluence[].technology) - never derived from the
                        # source name (omit rather than invent, ADR-0202).
                        if source.get("technology"):
                            record["technology"] = source["technology"]
                        records_by_doc_id[doc_id] = record
                    next_link = payload.get("_links", {}).get("next")
                    if next_link:
                        next_url = f"{base_url}/wiki{next_link}"
                        next_params = None  # the cursor URL already carries the full query string
                    else:
                        next_url = None
    for doc_id, record in records_by_doc_id.items():
        store.put_json(f"{config.raw_prefix}/{doc_id}.json", record)
    return len(records_by_doc_id)


# --------------------------------------------------------------------------
# fetch-salesforce (knowledge.sales)
# --------------------------------------------------------------------------


def _render_record_text(fields: dict) -> str:
    """Stable "Field: value" rendering - the semantic text a structured
    record contributes to the corpus. Keys render in the configured field
    order, never dict order, so the sha256 change detection stays
    deterministic."""
    lines = []
    for name, value in fields.items():
        if value is None or value == "":
            continue
        lines.append(f"{name}: {value}")
    return "\n".join(lines)


def _fetch_salesforce(config: IngestionConfig, store: CorpusStore) -> int:
    """REST (SOQL) query of the configured objects -> one raw record per
    Salesforce record, carrying ADR-0202's sales metadata extensions. The
    instance URL and token arrive via env/ESO (operator-supplied - no live
    call ever happens in CI; tests drive this with fixtures)."""
    if not config.salesforce_sources:
        logger.info("fetch-salesforce: no salesforce sources configured")
        return 0
    if not config.salesforce_instance_url or not config.salesforce_token:
        raise SystemExit(
            "fetch-salesforce: SALESFORCE_INSTANCE_URL/SALESFORCE_TOKEN not set - "
            "supply them via the chart's ExternalSecret before enabling this domain"
        )
    base = config.salesforce_instance_url.rstrip("/")
    headers = {"Authorization": f"Bearer {config.salesforce_token}"}
    fetched = 0
    for source in config.salesforce_sources:
        if not source.get("enabled", True):
            continue
        object_name = source["object"]
        fields = source.get("fields") or ["Id", "Name"]
        soql = source.get("soql") or f"SELECT {', '.join(fields)} FROM {object_name}"
        url = f"{base}/services/data/v59.0/query"
        try:
            resp = requests.get(
                url, params={"q": soql}, headers=headers, timeout=HTTP_TIMEOUT_SECONDS
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("fetch-salesforce: query failed for %s: %s", object_name, exc)
            continue
        for sf_record in resp.json().get("records", []):
            record_id = sf_record.get("Id")
            if not record_id:
                continue
            ordered = {name: sf_record.get(name) for name in fields}
            text = _render_record_text(ordered)
            if not text.strip():
                continue
            record_url = f"{base}/{record_id}"
            doc_id = doc_id_for(record_url)
            record = {
                "doc_id": doc_id,
                "url": record_url,
                "title": sf_record.get("Name") or f"{object_name} {record_id}",
                "text": text,
                "domain": "knowledge.sales",
                "product": None,
                "version": None,
                "language": "en",
                "source_type": "salesforce-object",
                # sales-data -> C2 (policies/data-classification/classification.yaml)
                "classification": source.get("classification", "C2"),
                "acl_groups": source.get("requiredGroups") or [],
                "fetched_at": _utcnow_iso(),
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "provenance": record_url,
                "last_modified": sf_record.get("LastModifiedDate"),
                # ADR-0202 sales extensions - straight from the record where
                # the source config names the field, absent otherwise.
                "sales": {
                    "object": object_name,
                    "deal_type": source.get("dealType"),
                    "status": sf_record.get(source.get("statusField") or "StageName"),
                },
            }
            store.put_json(f"{config.raw_prefix}/{doc_id}.json", record)
            fetched += 1
    return fetched


# --------------------------------------------------------------------------
# load-sxa-dump (knowledge.sxa-legacy)
# --------------------------------------------------------------------------


def _fetch_sxa_dump_bytes(config: IngestionConfig, key: str) -> Optional[bytes]:
    """Fetches one object of the SXA dump from its S3 bucket - a separate
    client from CorpusStore, which is bound to the shared corpus bucket and
    unrelated content. The dump ships as a schema.sql + data.sql pair, and
    ADR-0219's parse needs them separately (column order comes from the
    schema, rows from the data), so this fetches one key per call rather
    than concatenating."""
    from botocore.config import Config as BotoClientConfig

    client_kwargs: dict = {
        "region_name": config.sxa_s3_region or None,
        "aws_access_key_id": config.sxa_aws_access_key_id,
        "aws_secret_access_key": config.sxa_aws_secret_access_key,
        "config": BotoClientConfig(
            s3={"addressing_style": "path" if config.sxa_s3_path_style else "auto"},
            connect_timeout=10,
            read_timeout=60,
            retries={"max_attempts": 4, "mode": "standard"},
        ),
    }
    if config.sxa_s3_endpoint:
        client_kwargs["endpoint_url"] = config.sxa_s3_endpoint
    client = boto3.client("s3", **client_kwargs)
    try:
        resp = client.get_object(Bucket=config.sxa_s3_bucket, Key=key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in ("NoSuchKey", "404"):
            return None
        raise
    return resp["Body"].read()


def _split_sql_statements(dump_text: str) -> list:
    """Splits a SQL script into individual statements on unquoted,
    top-level semicolons - quote-aware (single/double/backtick) so a `;`
    inside a VARCHAR value or a backtick-quoted identifier never splits a
    statement early. Deliberately not a full SQL parser: mysqldump output
    is machine-generated and well-formed, this only needs to handle
    normal escaping, not adversarial input.

    Comment lines (`-- ...`) are stripped per-line *before* splitting, not
    by checking whether a whole (possibly multi-line) statement starts
    with `--` - a comment line immediately followed by a real statement on
    the next line is not itself a comment once joined.

    WP-57: delegates the actual splitting to sqlparse.split() (a compiled
    tokenizer) instead of a pure-Python char-by-char state machine, which
    was the dominant cost of load-sxa-dump on large dumps. sqlparse.split()
    KEEPS the trailing `;` on each statement (verified empirically) -
    _INSERT_RE's `values` group (`(?P<values>.+)$`, re.DOTALL) would
    otherwise absorb it into the last value, so stripping it here is a
    correctness requirement, not cosmetic."""
    lines = [line for line in dump_text.splitlines() if not line.strip().startswith("--")]
    stripped_text = "\n".join(lines)
    statements = [s.strip().rstrip(";").strip() for s in sqlparse.split(stripped_text)]
    return [s for s in statements if s]




def _load_sxa_dump(config: IngestionConfig, store: CorpusStore) -> int:
    """ADR-0219: the company's pre-2021 commercial record, parsed straight
    out of S3 into one raw record per dumped table row.

    No database engine is involved, ephemeral or persistent. ADR-0216
    originally imported this dump into a live MariaDB `sxa` database so a
    deterministic MCP tool surface could query it; ADR-0219 retired that
    whole path (SXA is a closed historical record, not a live system, so
    there was nothing for an exact-figure tool to be authoritative about)
    and adopted ADR-0217's reasoning instead: mysqldump output is
    machine-generated and well-formed, so `_parse_create_table_columns` +
    `_parse_insert_rows` are sufficient without a database round-trip.

    Content is emitted exactly as it arrives from S3 - no transform, no
    scanning. `min_classification: C3` plus `knowledge.sxa-legacy`'s
    `allowed_groups` are the safeguard.

    Idempotent per snapshot: a re-run against a byte-identical dump
    produces byte-identical records, so detect-changes sees unchanged
    sha256s, and the checksum short-circuit below skips the parse entirely.
    """
    if not config.sxa_dump_schema_s3_key or not config.sxa_dump_data_s3_key:
        raise SystemExit(
            "load-sxa-dump: SXA_DUMP_SCHEMA_S3_KEY/SXA_DUMP_DATA_S3_KEY not set - "
            "upload the approved snapshot to the SXA bucket and point this at it"
        )
    schema_bytes = _fetch_sxa_dump_bytes(config, config.sxa_dump_schema_s3_key)
    if schema_bytes is None:
        raise SystemExit(
            f"load-sxa-dump: no object at s3://{config.sxa_s3_bucket}/"
            f"{config.sxa_dump_schema_s3_key}"
        )
    data_bytes = _fetch_sxa_dump_bytes(config, config.sxa_dump_data_s3_key)
    if data_bytes is None:
        raise SystemExit(
            f"load-sxa-dump: no object at s3://{config.sxa_s3_bucket}/"
            f"{config.sxa_dump_data_s3_key}"
        )
    checksum = hashlib.sha256(schema_bytes + b"\n" + data_bytes).hexdigest()

    # WP-57's short-circuit: skip the parse (thousands of rows) when this
    # exact dump byte-for-byte matches the last run's. Safe because nothing
    # purges raw/<domain>/ between runs, so the prior run's records stay in
    # place and detect-changes still finds them.
    checksum_key = f"{config.manifest_prefix}/sxa-dump-checksum.json"
    previous = store.get_json(checksum_key)
    if previous and previous.get("checksum") == checksum:
        logger.info(
            "load-sxa-dump: dump unchanged since last run (checksum %s) - skipping re-parse",
            checksum[:16],
        )
        return 0

    schema_text = schema_bytes.decode("utf-8", errors="replace")
    data_text = data_bytes.decode("utf-8", errors="replace")
    snapshot_id = config.sxa_snapshot_id or f"sha256-{checksum[:16]}"
    imported_at = _utcnow_iso()

    if "CREATE TABLE" not in schema_text.upper():
        raise SystemExit(
            "load-sxa-dump: no CREATE TABLE statement found in the schema export - "
            "not a mysqldump-style schema, refusing to parse an unvalidated shape"
        )

    columns_by_table = _parse_create_table_columns(schema_text)
    records = []
    for table, row in _parse_insert_rows(data_text, columns_by_table):
        text = _render_record_text(row)
        if not text.strip():
            continue
        row_id = row.get("id", hashlib.sha256(repr(sorted(row.items())).encode()).hexdigest()[:12])
        # sxa-dump:// matches knowledge/sxa-legacy/domain.yaml's declared
        # source class. ADR-0216's implementation emitted sxa-mariadb://,
        # which never matched the descriptor - corrected here (ADR-0219).
        record_url = f"sxa-dump://{table}/{row_id}"
        doc_id = doc_id_for(record_url)
        records.append({
            "doc_id": doc_id,
            "url": record_url,
            "title": f"SXA {table} #{row_id}",
            "text": text,
            "domain": "knowledge.sxa-legacy",
            "product": None,
            "version": None,
            "language": "fr",
            "source_type": "sxa-dump",
            # Historical commercial data: C3 by default (ADR-0206) until the
            # field-level review WP-23 records says otherwise.
            "classification": "C3",
            "acl_groups": [],
            "fetched_at": imported_at,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "provenance": f"sxa dump snapshot {snapshot_id}",
            # ADR-0206 snapshot discipline + ADR-0202 sxa-legacy extensions.
            "sxa": {
                "snapshot_id": snapshot_id,
                "imported_at": imported_at,
                "snapshot_checksum": checksum,
                "table": table,
            },
        })

    # WP-57: one synchronous put_object per row is thousands of sequential
    # round-trips; this stage is S3-latency-bound, not CPU-bound.
    if records:
        with ThreadPoolExecutor(max_workers=max(1, config.fetch_sxa_write_concurrency)) as pool:
            list(pool.map(
                lambda r: store.put_json(f"{config.raw_prefix}/{r['doc_id']}.json", r),
                records,
            ))
    store.put_json(checksum_key, {"checksum": checksum, "fetched_at": imported_at})
    return len(records)


# --------------------------------------------------------------------------
# SQL-dump parsing helpers (shared by load-sxa-dump)
# --------------------------------------------------------------------------

_CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+`?(?P<table>\w+)`?\s*\((?P<body>.*)\)\s*ENGINE",
    re.IGNORECASE | re.DOTALL,
)
_INSERT_RE = re.compile(
    r"^INSERT\s+INTO\s+`?(?P<table>\w+)`?\s*"
    r"(?:\((?P<columns>[^)]*)\)\s*)?"
    r"VALUES\s*(?P<values>.+)$",
    re.IGNORECASE | re.DOTALL,
)
_TABLE_CONSTRAINT_KEYWORDS = (
    "PRIMARY KEY", "UNIQUE KEY", "UNIQUE", "KEY", "INDEX", "CONSTRAINT",
    "FOREIGN KEY", "FULLTEXT", "SPATIAL", "CHECK",
)


def _split_top_level(text: str, sep: str) -> list:
    """Splits `text` on `sep` at paren-depth 0, quote-aware (single/double/
    backtick) - the same escaping rules as _split_sql_statements, generalized
    to any separator/depth rather than only top-level semicolons. Used for
    both a CREATE TABLE body's column/constraint definitions and a VALUES
    clause's row tuples (sep=",", called with the text already stripped to
    one row's parenthesized contents) - mysqldump output is machine-generated
    and well-formed, so this doesn't need to handle adversarial input, only
    normal escaping and nested parens (column type precision, e.g.
    DECIMAL(10,2))."""
    parts = []
    current: list = []
    depth = 0
    in_string: Optional[str] = None
    escaped = False
    for ch in text:
        if escaped:
            current.append(ch)
            escaped = False
            continue
        if ch == "\\" and in_string in ("'", '"'):
            current.append(ch)
            escaped = True
            continue
        if in_string:
            current.append(ch)
            if ch == in_string:
                in_string = None
            continue
        if ch in ("'", '"', "`"):
            in_string = ch
            current.append(ch)
            continue
        if ch == "(":
            depth += 1
            current.append(ch)
            continue
        if ch == ")":
            depth -= 1
            current.append(ch)
            continue
        if ch == sep and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(ch)
    tail = "".join(current)
    if tail.strip():
        parts.append(tail)
    return [p.strip() for p in parts]


def _split_row_tuples(values_clause: str) -> list:
    """Splits a VALUES clause ("(1,'a'),(2,'b')") into each row's raw inner
    text ("1,'a'" / "2,'b'"), quote-aware so a literal containing `),(`
    never splits mid-row. Trailing `;`/whitespace already stripped by the
    caller (_split_sql_statements)."""
    rows = []
    depth = 0
    in_string: Optional[str] = None
    escaped = False
    current: list = []
    for ch in values_clause:
        if escaped:
            if depth > 0:
                current.append(ch)
            escaped = False
            continue
        if ch == "\\" and in_string in ("'", '"'):
            escaped = True
            if depth > 0:
                current.append(ch)
            continue
        if in_string:
            if depth > 0:
                current.append(ch)
            if ch == in_string:
                in_string = None
            continue
        if ch in ("'", '"'):
            in_string = ch
            if depth > 0:
                current.append(ch)
            continue
        if ch == "(":
            depth += 1
            if depth > 1:
                current.append(ch)
            continue
        if ch == ")":
            depth -= 1
            if depth == 0:
                rows.append("".join(current))
                current = []
            else:
                current.append(ch)
            continue
        if depth > 0:
            current.append(ch)
    return rows


def _convert_sql_literal(token: str) -> Any:
    """Converts one raw VALUES-tuple token into a Python value: quoted
    strings are unescaped, NULL/numeric literals convert, anything else
    (hex blobs, date/function literals mysqldump rarely emits per-row) is
    kept as the raw token - good enough for _render_record_text's "Field:
    value" rendering, which only needs a str() anyway."""
    token = token.strip()
    if token.upper() == "NULL":
        return None
    if len(token) >= 2 and token[0] == "'" and token[-1] == "'":
        inner = token[1:-1]
        return inner.replace("\\'", "'").replace('\\"', '"').replace("\\\\", "\\")
    try:
        if re.match(r"^-?\d+$", token):
            return int(token)
        return float(token)
    except ValueError:
        return token


def _parse_create_table_columns(schema_text: str) -> Dict[str, list]:
    """Extracts {table: [column, ...]} in declared order from a
    mysqldump-style schema file, skipping table-level constraint
    definitions (PRIMARY KEY/KEY/CONSTRAINT/...) that share the same
    top-level comma-separated body as real column definitions."""
    columns_by_table: Dict[str, list] = {}
    for statement in _split_sql_statements(schema_text):
        match = _CREATE_TABLE_RE.search(statement)
        if not match:
            continue
        table = match.group("table")
        columns = []
        for fragment in _split_top_level(match.group("body"), ","):
            fragment = fragment.strip()
            if not fragment.startswith("`"):
                upper = fragment.upper()
                if any(upper.startswith(kw) for kw in _TABLE_CONSTRAINT_KEYWORDS):
                    continue
            col_match = re.match(r"`(?P<name>[^`]+)`", fragment)
            if col_match:
                columns.append(col_match.group("name"))
        if columns:
            columns_by_table[table] = columns
    return columns_by_table


def _parse_insert_rows(data_text: str, columns_by_table: Dict[str, list]):
    """Yields (table, row_dict) for every row in every INSERT statement in
    a mysqldump-style data file - no SQL engine involved (ADR-0217): the
    column order comes from the INSERT's own explicit column list when
    present, otherwise from columns_by_table (the CREATE TABLE-declared
    order mysqldump's own default `INSERT INTO t VALUES (...)` form
    relies on implicitly)."""
    for statement in _split_sql_statements(data_text):
        match = _INSERT_RE.match(statement.strip())
        if not match:
            continue
        table = match.group("table")
        if match.group("columns"):
            columns = [c.strip().strip("`") for c in match.group("columns").split(",")]
        else:
            columns = columns_by_table.get(table)
        if not columns:
            logger.warning(
                "load-sxa-dump: no column order known for table %s (missing from "
                "schema and INSERT has no explicit column list) - skipping its rows",
                table,
            )
            continue
        for row_text in _split_row_tuples(match.group("values")):
            tokens = _split_top_level(row_text, ",")
            if len(tokens) != len(columns):
                logger.warning(
                    "load-sxa-dump: row in table %s has %d values but %d known columns - skipping",
                    table, len(tokens), len(columns),
                )
                continue
            yield table, {col: _convert_sql_literal(tok) for col, tok in zip(columns, tokens)}


# --------------------------------------------------------------------------
# Adapter registry
# --------------------------------------------------------------------------

SOURCE_ADAPTERS = {
    adapter.stage: adapter
    for adapter in (
        SourceAdapter("fetch-redhat", "knowledge.tech", _fetch_redhat),
        SourceAdapter("fetch-confluence", "knowledge.tech", _fetch_confluence),
        SourceAdapter("fetch-salesforce", "knowledge.sales", _fetch_salesforce),
        SourceAdapter("load-sxa-dump", "knowledge.sxa-legacy", _load_sxa_dump),
    )
}


# --------------------------------------------------------------------------
# detect-changes
# --------------------------------------------------------------------------


def stage_detect_changes(config: IngestionConfig, store: CorpusStore) -> None:
    manifest_key = f"{config.manifest_prefix}/manifest.json"
    manifest = store.get_json(manifest_key) or {}

    raw_keys = [k for k in store.list_keys(f"{config.raw_prefix}/") if k.endswith(".json")]
    current: dict = {}
    # WP-58: one GET per raw/<domain>/ object - network/S3-latency-bound,
    # not CPU-bound. pool.map preserves order and results are folded into
    # `current` back on this thread, so there is no concurrent dict
    # mutation to guard against.
    with ThreadPoolExecutor(max_workers=max(1, config.detect_changes_read_concurrency)) as pool:
        for record in pool.map(store.get_json, raw_keys):
            if not record:
                continue
            current[record["doc_id"]] = {"sha256": record["sha256"], "url": record["url"]}

    if not config.corpus_incremental:
        new_ids = list(current.keys())
        changed_ids: list = []
    else:
        new_ids = [doc_id for doc_id in current if doc_id not in manifest]
        changed_ids = [
            doc_id
            for doc_id, info in current.items()
            if doc_id in manifest and manifest[doc_id].get("sha256") != info["sha256"]
        ]

    if config.corpus_delete_orphans:
        deleted_ids = [doc_id for doc_id in manifest if doc_id not in current]
        deleted_urls = [manifest[doc_id]["url"] for doc_id in deleted_ids if "url" in manifest[doc_id]]
    else:
        deleted_ids, deleted_urls = [], []

    new_and_changed_ids = set(new_ids) | set(changed_ids)
    unchanged_ids = [doc_id for doc_id in current if doc_id not in new_and_changed_ids]

    # WP-067 live verification (2026-08-26) caught a real bug here: this
    # stage used to write manifest.json unconditionally, right after
    # hashing the raw docs and BEFORE normalize/chunk/embed/index-pgvector
    # (each a separate KFP pod) ever ran. When one of those later stages
    # failed mid-pipeline, the manifest was already overwritten to mark
    # those documents "seen" - every subsequent run then saw 0 new/changed
    # and silently skipped them forever, even though nothing had actually
    # been indexed (the domain sat at 0 rows in document_embeddings
    # despite several prior runs reporting an overall SUCCEEDED state).
    # manifest.json is now only written by stage_validate, once it has
    # confirmed each touched document actually has indexed rows - see the
    # "current_new_changed" carry-through below.
    changeset = {
        "new": new_ids,
        "changed": changed_ids,
        "deleted": deleted_ids,
        "deleted_urls": deleted_urls,
        "unchanged": unchanged_ids,
        "current_new_changed": {doc_id: current[doc_id] for doc_id in new_ids + changed_ids},
        "generated_at": _utcnow_iso(),
    }
    store.put_json(f"{config.manifest_prefix}/changeset.json", changeset)
    logger.info(
        "detect-changes: %d new, %d changed, %d deleted, %d unchanged",
        len(new_ids), len(changed_ids), len(deleted_ids), len(unchanged_ids),
    )


def _load_changeset(config: IngestionConfig, store: CorpusStore, stage_name: str) -> Optional[dict]:
    changeset = store.get_json(f"{config.manifest_prefix}/changeset.json")
    if not changeset:
        logger.warning("%s: no changeset found, run detect-changes first", stage_name)
    return changeset


# --------------------------------------------------------------------------
# normalize
# --------------------------------------------------------------------------


def _table_to_text(table) -> str:
    rows = []
    for tr in table.find_all("tr"):
        cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
        if cells:
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def _normalize_html(html: str, *, preserve_code_blocks: bool, preserve_tables: bool) -> tuple:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    if preserve_code_blocks:
        for pre in soup.find_all("pre"):
            code_text = pre.get_text("\n")
            pre.replace_with(NavigableString(f"\n```\n{code_text}\n```\n"))

    if preserve_tables:
        for table in soup.find_all("table"):
            table.replace_with(NavigableString("\n" + _table_to_text(table) + "\n"))

    title_tag = soup.find("h1") or soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""
    main = soup.find("main") or soup.find(attrs={"role": "main"}) or soup.body or soup
    text = main.get_text("\n", strip=True) if main is not None else soup.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return title, text


def _normalize_one(doc_id: str, config: IngestionConfig, store: CorpusStore) -> bool:
    """Normalize a single raw document and write it to <normalized_prefix>/.

    ADR-0219: split out of stage_normalize so the per-document work (one S3
    GET, pure-Python cleanup, one S3 PUT) can run on a worker thread. Every
    value it touches is either read-only shared config or local to this
    call, so there is no cross-document state to guard. Returns True when a
    normalized document was written.
    """
    raw = store.get_json(f"{config.raw_prefix}/{doc_id}.json")
    if not raw:
        logger.warning("normalize: raw document %s missing, skipping", doc_id)
        return False
    if raw.get("raw_html") is not None:
        title, text = _normalize_html(
            raw["raw_html"],
            preserve_code_blocks=config.chunk_preserve_code_blocks,
            preserve_tables=config.chunk_preserve_tables,
        )
    else:
        # Structured-source adapters (salesforce/sxa-dump) emit
        # ready text, not HTML - nothing to clean up.
        title, text = raw.get("title") or "", raw.get("text") or ""
    if not text.strip():
        logger.warning("normalize: %s produced no text after cleanup, skipping", raw["url"])
        return False
    domain = raw.get("domain") or config.domain
    # ADR-0205/WP-24: distinct fields, not the old conflated
    # `last_modified` - source_modified_at is the SOURCE's own
    # modification signal when the adapter captured one (Confluence's
    # history.lastUpdated.when, Salesforce's LastModifiedDate, or a
    # best-effort HTTP Last-Modified header for product docs - see
    # _fetch_redhat); when a source genuinely exposes none,
    # `fetched_at` is the best available lower bound,
    # not an invented value. indexed_at is always this pipeline's own
    # clock at normalize time, independent of whatever the source
    # reported - the two are only ever equal by coincidence now.
    indexed_at_dt = datetime.now(timezone.utc)
    indexed_at = indexed_at_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    metadata = {
        # ADR-0202/ADR-0204: records written before the domain field
        # existed are knowledge.tech by construction - the only domain
        # this pipeline ever served (same default rag-service applies).
        "domain": domain,
        "product": raw.get("product"),
        "version": raw.get("version"),
        "language": _normalize_language(raw.get("language")),
        "source_type": raw.get("source_type"),
        "classification": raw.get("classification", "C1"),
        "acl_groups": raw.get("acl_groups") or [],
        "source_modified_at": raw.get("last_modified") or raw.get("fetched_at"),
        "indexed_at": indexed_at,
        "provenance": raw.get("provenance") or raw.get("url"),
    }
    # ADR-0205/WP-24: derived from this run's domain freshness
    # objective (STALE_AFTER, mirroring knowledge/<domain>/domain.yaml)
    # - omitted entirely (never set to a fake value) when the domain
    # has no configured window, e.g. knowledge.sxa-legacy's on-demand
    # objective (_IMMUTABLE_LEGACY_DOMAINS).
    stale_duration = _parse_duration_spec(config.stale_after_spec)
    if domain not in _IMMUTABLE_LEGACY_DOMAINS and stale_duration is not None:
        metadata["stale_after"] = (indexed_at_dt + stale_duration).strftime("%Y-%m-%dT%H:%M:%SZ")
    if raw.get("technology"):
        metadata["technology"] = raw["technology"]
    # Per-domain metadata extensions (ADR-0202's metadata-schema.yaml)
    # ride through under their domain's own key.
    for extension_key in ("sales", "adv", "sxa"):
        if raw.get(extension_key):
            metadata[extension_key] = raw[extension_key]
    record = {
        "doc_id": doc_id,
        "url": raw["url"],
        "title": raw.get("title") or title,
        "text": text,
        "metadata": metadata,
    }
    store.put_json(f"{config.normalized_prefix}/{doc_id}.json", record)
    return True


def stage_normalize(config: IngestionConfig, store: CorpusStore) -> None:
    changeset = _load_changeset(config, store, "normalize")
    if not changeset:
        return
    doc_ids = changeset["new"] + changeset["changed"]
    normalized = 0
    # ADR-0219: one GET + one PUT per document, S3-latency-bound exactly like
    # stage_detect_changes' read pool. pool.map preserves order and the
    # counter is folded back on this thread, so nothing is shared mutably.
    with ThreadPoolExecutor(max_workers=max(1, config.normalize_concurrency)) as pool:
        for position, written in enumerate(
            pool.map(lambda doc_id: _normalize_one(doc_id, config, store), doc_ids), start=1
        ):
            if written:
                normalized += 1
            if position % 10000 == 0:
                logger.info("normalize: %d/%d documents processed", position, len(doc_ids))
    logger.info("normalize: wrote %d normalized documents", normalized)


# --------------------------------------------------------------------------
# chunk
# --------------------------------------------------------------------------


def _get_token_encoder():
    try:
        import tiktoken

        return tiktoken.get_encoding("cl100k_base")
    except Exception as exc:  # pragma: no cover - network/environment dependent
        logger.warning(
            "tiktoken encoding unavailable (%s); falling back to a whitespace-based token approximation",
            exc,
        )
        return None


def _count_tokens(text: str, encoder) -> int:
    if encoder is not None:
        return len(encoder.encode(text))
    return max(1, int(len(text.split()) * 1.3))


def _split_into_units(text: str) -> list:
    """Paragraph-level units. Fenced code blocks (```...```, see
    _normalize_html) are kept atomic and never split mid-block."""
    units: list = []
    buf: list = []
    in_code = False
    for line in text.splitlines():
        if line.strip() == "```":
            in_code = not in_code
            buf.append(line)
            if not in_code:
                units.append("\n".join(buf))
                buf = []
            continue
        if in_code:
            buf.append(line)
            continue
        if line.strip() == "" and buf:
            units.append("\n".join(buf))
            buf = []
        else:
            buf.append(line)
    if buf:
        units.append("\n".join(buf))
    return [u for u in units if u.strip()]


def _split_oversized_unit(unit: str, max_tokens: int, encoder) -> list:
    """Word-boundary fallback for a single paragraph that alone exceeds
    max_tokens (_split_into_units only breaks on blank lines/code fences,
    so an unusually long paragraph would otherwise become one oversized
    chunk). Table text can hit this same path since it carries no fence
    marker to protect it - it splits by word boundary too, not by row;
    acceptable for the rare oversized table, not worth a second marker."""
    words = unit.split()
    if not words:
        return [unit]
    pieces: list = []
    current: list = []
    for word in words:
        current.append(word)
        if _count_tokens(" ".join(current), encoder) >= max_tokens:
            pieces.append(" ".join(current))
            current = []
    if current:
        pieces.append(" ".join(current))
    return pieces or [unit]


def _chunk_text(text: str, *, max_tokens: int, overlap_tokens: int, encoder) -> list:
    units: list = []
    for unit in _split_into_units(text):
        is_code_block = unit.strip().startswith("```") and unit.strip().endswith("```")
        if not is_code_block and _count_tokens(unit, encoder) > max_tokens:
            units.extend(_split_oversized_unit(unit, max_tokens, encoder))
        else:
            units.append(unit)
    chunks: list = []
    current_units: list = []
    current_tokens = 0
    for unit in units:
        unit_tokens = _count_tokens(unit, encoder)
        if current_units and current_tokens + unit_tokens > max_tokens:
            chunks.append("\n\n".join(current_units))
            if overlap_tokens > 0:
                overlap_units: list = []
                overlap_count = 0
                for u in reversed(current_units):
                    t = _count_tokens(u, encoder)
                    if overlap_count + t > overlap_tokens:
                        break
                    overlap_units.insert(0, u)
                    overlap_count += t
                current_units, current_tokens = overlap_units, overlap_count
            else:
                current_units, current_tokens = [], 0
        current_units.append(unit)
        current_tokens += unit_tokens
    if current_units:
        chunks.append("\n\n".join(current_units))
    return chunks or [text]


def _chunk_one(doc_id: str, config: IngestionConfig, store: CorpusStore, encoder) -> int:
    """Chunk a single normalized document. Returns the chunk count written.

    ADR-0219: split out of stage_chunk for the same reason as _normalize_one.
    `encoder` is a tiktoken Encoding, whose encode() is safe to call from
    several threads, so one encoder is shared across the pool rather than
    rebuilt (and re-downloaded) per document.
    """
    doc = store.get_json(f"{config.normalized_prefix}/{doc_id}.json")
    if not doc:
        logger.warning("chunk: normalized document %s missing, skipping", doc_id)
        return 0
    pieces = _chunk_text(
        doc["text"],
        max_tokens=config.chunk_max_tokens,
        overlap_tokens=config.chunk_overlap_tokens,
        encoder=encoder,
    )
    record = {
        "doc_id": doc_id,
        "url": doc["url"],
        "title": doc["title"],
        "metadata": doc["metadata"],
        "chunks": [{"chunk_index": i, "text": piece} for i, piece in enumerate(pieces)],
    }
    store.put_json(f"{config.normalized_prefix}/{doc_id}.chunks.json", record)
    return len(record["chunks"])


def stage_chunk(config: IngestionConfig, store: CorpusStore) -> None:
    changeset = _load_changeset(config, store, "chunk")
    if not changeset:
        return
    encoder = _get_token_encoder()
    doc_ids = changeset["new"] + changeset["changed"]
    total_chunks = 0
    with ThreadPoolExecutor(max_workers=max(1, config.chunk_concurrency)) as pool:
        for position, count in enumerate(
            pool.map(lambda doc_id: _chunk_one(doc_id, config, store, encoder), doc_ids), start=1
        ):
            total_chunks += count
            if position % 10000 == 0:
                logger.info("chunk: %d/%d documents processed", position, len(doc_ids))
    logger.info("chunk: split %d documents into %d chunks", len(doc_ids), total_chunks)


# --------------------------------------------------------------------------
# embed
# --------------------------------------------------------------------------


def _embed_batch(texts: list, config: IngestionConfig) -> list:
    """Same request/response contract as components/rag-service/app/embeddings.py
    (OpenAI-compatible /v1/embeddings) - both sides must agree on this shape."""
    url = config.embedding_endpoint.rstrip("/") + "/embeddings"
    headers = {"Content-Type": "application/json"}
    if config.embedding_api_token:
        headers["Authorization"] = f"Bearer {config.embedding_api_token}"
    # truncate_prompt_tokens is a vLLM extension (ignored by rag-service's
    # query path, which never nears the limit): without it one chunk over the
    # model's max sequence length 400-fails its ENTIRE batch. Chunk budgets
    # can't fully prevent that - the chunker counts cl100k tokens (~1.4-1.7x
    # fewer than bge WordPiece) and preserved code blocks bypass the budget
    # altogether - in practice this has cost a run nearly all of its chunks
    # to shared-batch 400s.
    payload = {
        "model": config.embedding_model,
        "input": texts,
        "truncate_prompt_tokens": -1,
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    body = resp.json()
    return [item["embedding"] for item in body["data"]]


def stage_embed(config: IngestionConfig, store: CorpusStore) -> None:
    """Embed every chunk of this run's changeset.

    ADR-0219 (2026-08-26): batching used to happen strictly WITHIN one
    document - `for start in range(0, len(chunks), embedding_batch_size)`
    over a single record. That is fine for knowledge.tech, whose documents
    are long product pages that chunk many times over, but the SXA dump
    renders one document per table row averaging ~1.2 KB against a
    320-token budget, so virtually every document is a SINGLE chunk. The
    effect was that EMBEDDING_BATCH_SIZE=64 sent 314,428 requests of one
    chunk each, and the stage could never finish. Chunks are now pooled ACROSS
    documents into genuinely full batches, and several batches are in
    flight at once, while the per-document write-back and the failure
    semantics (a failed batch logs and leaves its chunks unembedded for
    stage_validate to catch) are unchanged.
    """
    changeset = _load_changeset(config, store, "embed")
    if not changeset:
        return
    doc_ids = changeset["new"] + changeset["changed"]
    batch_size = max(1, config.embedding_batch_size)
    workers = max(1, config.embed_concurrency)
    # Documents are read, embedded and written back one window at a time so
    # peak memory stays bounded: a full window of embedded chunks is held at
    # once, and a 1024-dimension vector costs ~32 KB as Python floats.
    window_size = max(batch_size * workers * 4, 128)
    embedded_docs = 0
    embedded_chunks = 0

    def _embed_one_batch(batch):
        """batch is a list of (record, chunk). Returns (batch, vectors|None)."""
        try:
            return batch, _embed_batch([chunk["text"] for _, chunk in batch], config)
        except requests.RequestException as exc:
            logger.error(
                "embed: request failed for %d chunk(s) starting at %s chunk %d: %s",
                len(batch), batch[0][0]["url"], batch[0][1]["chunk_index"], exc,
            )
            return batch, None

    with ThreadPoolExecutor(max_workers=max(1, config.index_read_concurrency)) as io_pool, \
            ThreadPoolExecutor(max_workers=workers) as embed_pool:
        for offset in range(0, len(doc_ids), window_size):
            window = doc_ids[offset:offset + window_size]
            records = []
            for doc_id, record in zip(
                window,
                io_pool.map(
                    lambda d: store.get_json(f"{config.normalized_prefix}/{d}.chunks.json"), window
                ),
            ):
                if not record:
                    logger.warning("embed: chunk document %s missing, skipping", doc_id)
                    continue
                records.append(record)

            pending = [(record, chunk) for record in records for chunk in record["chunks"]]
            batches = [pending[i:i + batch_size] for i in range(0, len(pending), batch_size)]
            for batch, vectors in embed_pool.map(_embed_one_batch, batches):
                if vectors is None:
                    continue
                for (record, chunk), vector in zip(batch, vectors):
                    if len(vector) != config.embedding_dimensions:
                        logger.error(
                            "embed: dimension mismatch for %s chunk %d (got %d, expected %d)",
                            record["url"], chunk["chunk_index"],
                            len(vector), config.embedding_dimensions,
                        )
                        continue
                    chunk["embedding"] = vector
                    embedded_chunks += 1

            # Write back only after every batch in this window has been
            # applied, so a record is never persisted half-embedded.
            list(
                io_pool.map(
                    lambda r: store.put_json(
                        f"{config.normalized_prefix}/{r['doc_id']}.chunks.json", r
                    ),
                    records,
                )
            )
            embedded_docs += len(records)
            logger.info(
                "embed: %d/%d documents processed, %d chunks embedded so far",
                min(offset + window_size, len(doc_ids)), len(doc_ids), embedded_chunks,
            )
    logger.info("embed: embedded %d chunks across %d documents", embedded_chunks, embedded_docs)


# --------------------------------------------------------------------------
# index-pgvector
# --------------------------------------------------------------------------


def _pg_connect(config: IngestionConfig):
    conninfo = (
        f"host={config.pg_host} port={config.pg_port} dbname={config.pg_database} "
        f"user={config.pg_user} password={config.pg_password} sslmode={config.pg_sslmode}"
    )
    conn = psycopg.connect(conninfo, autocommit=False)
    register_vector(conn)
    with conn.cursor() as cur:
        cur.execute(f"SET search_path TO {config.pg_schema}, public")
    return conn


# ADR-0525: one round-trip per chunk row made this the pipeline's slowest
# stage. The ingestion pod reaches PostgreSQL through pgbouncer with
# sslmode=require from a mesh-injected pod, so every execute() pays
# app -> istio sidecar -> pgbouncer -> Postgres. Measured at ~35ms/row
# (~113k rows in ~66 min on the SXA corpus) - that is latency, not
# server-side insert cost. psycopg3's executemany() pipelines a whole batch
# into one flight, so the per-row latency term collapses.
_INDEX_WRITE_BATCH_ROWS = 1000

_VECTOR_INDEX_NAME = "ix_document_embeddings_embedding_cosine"

# Rebuilding a 310k-row index to add a handful of documents would cost far
# more than it saves, so the drop/recreate below only runs when the load is
# large relative to what is already indexed.
_VECTOR_INDEX_REBUILD_RATIO = 0.2

_INDEX_UPSERT_SQL = """
    INSERT INTO document_embeddings (source, chunk_index, title, content, embedding, metadata)
    VALUES (%s, %s, %s, %s, %s, %s::jsonb)
    ON CONFLICT (source, chunk_index) DO UPDATE SET
        title = EXCLUDED.title,
        content = EXCLUDED.content,
        embedding = EXCLUDED.embedding,
        metadata = EXCLUDED.metadata,
        updated_at = now()
"""


def _ivfflat_lists_for(rows: int) -> int:
    """pgvector sizes ivfflat at roughly rows/1000 below 1M rows. Floored at
    10 - the value 006_embedding_1024.sql ships, which is all a schema Job
    running against an empty table can know - and capped at 1000."""
    return max(10, min(1000, rows // 1000))


def _vector_index_should_be_rebuilt(cur, incoming_docs: int) -> bool:
    cur.execute("SELECT count(*) FROM document_embeddings")
    existing = (cur.fetchone() or [0])[0]
    if existing == 0:
        return True
    return incoming_docs >= existing * _VECTOR_INDEX_REBUILD_RATIO


def _rebuild_vector_index(conn, cur) -> None:
    """Recreates the ivfflat index sized from the row count that is now
    actually present. This is the only point in the system that knows it:
    the schema Job builds the index when the table is still empty."""
    cur.execute("SELECT count(*) FROM document_embeddings")
    rows = (cur.fetchone() or [0])[0]
    lists = _ivfflat_lists_for(rows)
    cur.execute(
        f"CREATE INDEX IF NOT EXISTS {_VECTOR_INDEX_NAME} "
        f"ON document_embeddings USING ivfflat (embedding vector_cosine_ops) "
        f"WITH (lists = {lists})"
    )
    conn.commit()
    logger.info("index-pgvector: rebuilt %s with lists=%d for %d rows", _VECTOR_INDEX_NAME, lists, rows)


def stage_index_pgvector(config: IngestionConfig, store: CorpusStore) -> None:
    changeset = _load_changeset(config, store, "index-pgvector")
    if not changeset:
        return
    conn = _pg_connect(config)
    indexed = 0
    deleted = 0
    # ADR-0219: the S3 GET below used to sit INSIDE the per-document database
    # loop, so every document cost a serial round-trip to S3 before a single
    # row could be written. Each window's records are now prefetched
    # concurrently and the database loop consumes them from memory - which
    # also means the open transaction no longer interleaves with S3 latency
    # at all.
    window_size = max(1, config.index_read_concurrency) * 64
    doc_ids = changeset["new"] + changeset["changed"]

    # ADR-0525: on a bulk load, maintaining ivfflat per row costs more than
    # rebuilding it once at the end - and the rebuild is also the only moment
    # the real row count is known, so it is where `lists` gets sized properly.
    dropped_vector_index = False
    try:
        with conn.cursor() as probe:
            dropped_vector_index = _vector_index_should_be_rebuilt(probe, len(doc_ids))
            if dropped_vector_index:
                probe.execute(f"DROP INDEX IF EXISTS {_VECTOR_INDEX_NAME}")
                conn.commit()
                logger.info("index-pgvector: dropped %s for the bulk load", _VECTOR_INDEX_NAME)
    except Exception:
        conn.rollback()
        dropped_vector_index = False
        logger.warning("index-pgvector: could not drop %s, indexing with it in place", _VECTOR_INDEX_NAME)

    try:
        with conn.cursor() as cur, ThreadPoolExecutor(
            max_workers=max(1, config.index_read_concurrency)
        ) as io_pool:
            position = 0
            for offset in range(0, len(doc_ids), window_size):
                window = doc_ids[offset:offset + window_size]
                fetched = io_pool.map(
                    lambda d: store.get_json(f"{config.normalized_prefix}/{d}.chunks.json"), window
                )
                pending: list = []
                for doc_id, record in zip(window, fetched):
                    position += 1
                    if not record:
                        logger.warning("index-pgvector: chunk document %s missing, skipping", doc_id)
                        continue
                    for chunk in record["chunks"]:
                        if "embedding" not in chunk:
                            logger.warning(
                                "index-pgvector: %s chunk %d has no embedding, skipping",
                                record["url"], chunk["chunk_index"],
                            )
                            continue
                        metadata = dict(record["metadata"])
                        metadata["chunk_index"] = chunk["chunk_index"]
                        pending.append(
                            (
                                record["url"],
                                chunk["chunk_index"],
                                record["title"],
                                chunk["text"],
                                chunk["embedding"],
                                json.dumps(metadata),
                            )
                        )
                        # Flush inside the window so a single window cannot
                        # build an unbounded list of 1024-dimension vectors.
                        if len(pending) >= _INDEX_WRITE_BATCH_ROWS:
                            cur.executemany(_INDEX_UPSERT_SQL, pending)
                            indexed += len(pending)
                            pending.clear()
                if pending:
                    cur.executemany(_INDEX_UPSERT_SQL, pending)
                    indexed += len(pending)
                    pending.clear()
                # Commit per window, not per run and no longer per document.
                # Per-run was never safe (a Patroni failover mid-run lost
                # every upserted row); per-document cost one commit
                # round-trip per row, which on a 314,428-document domain
                # dominated the stage. A window bounds what a failover can
                # lose to the documents prefetched above, and the upsert
                # keeps partial progress safe to re-run either way.
                # ADR-0525 batches the writes WITHIN a window; this commit
                # boundary deliberately did not move.
                conn.commit()
                logger.info(
                    "index-pgvector: %d/%d documents processed, %d chunk rows so far",
                    position, len(doc_ids), indexed,
                )

            for url in changeset.get("deleted_urls", []):
                cur.execute("DELETE FROM document_embeddings WHERE source = %s", (url,))
                deleted += cur.rowcount
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        # Must survive the exception path: leaving the index dropped would
        # degrade this domain's retrieval to a sequential scan until the next
        # successful run.
        if dropped_vector_index:
            try:
                with conn.cursor() as cur:
                    _rebuild_vector_index(conn, cur)
            except Exception:
                logger.error(
                    "index-pgvector: FAILED to recreate %s - retrieval for this domain "
                    "will sequential-scan until it is rebuilt manually",
                    _VECTOR_INDEX_NAME,
                )
        conn.close()
    logger.info("index-pgvector: upserted %d chunk rows, deleted %d orphaned rows", indexed, deleted)


# --------------------------------------------------------------------------
# validate
# --------------------------------------------------------------------------


def stage_validate(config: IngestionConfig, store: CorpusStore) -> None:
    changeset = _load_changeset(config, store, "validate")
    if not changeset:
        return

    touched_urls = set()
    freshness_failures = []
    for doc_id in changeset["new"] + changeset["changed"]:
        record = store.get_json(f"{config.normalized_prefix}/{doc_id}.chunks.json")
        if not record:
            continue
        touched_urls.add(record["url"])

        # ADR-0205/WP-24: operational-source chunks must carry the full
        # freshness trio - checked against THIS run's own normalized state
        # (the source of truth for what stage_normalize just computed),
        # not re-derived from the database. knowledge.sxa-legacy is exempt
        # (an immutable point-in-time snapshot, WP-22/ADR-0206) - every
        # other domain fails closed on a missing field rather than
        # silently indexing untrusted-forever content.
        metadata = record.get("metadata") or {}
        domain = metadata.get("domain", "knowledge.tech")
        if domain not in _IMMUTABLE_LEGACY_DOMAINS:
            missing = [f for f in _REQUIRED_FRESHNESS_FIELDS if not metadata.get(f)]
            if missing:
                freshness_failures.append(
                    f"{record['url']}: domain '{domain}' chunk missing required freshness "
                    f"metadata: {', '.join(missing)}"
                )

    conn = _pg_connect(config)
    failures = list(freshness_failures)
    try:
        with conn.cursor() as cur:
            for url in touched_urls:
                cur.execute(
                    "SELECT count(*), count(*) FILTER (WHERE embedding IS NULL) "
                    "FROM document_embeddings WHERE source = %s",
                    (url,),
                )
                total, missing_embedding = cur.fetchone()
                if total == 0:
                    failures.append(f"{url}: no rows indexed")
                elif missing_embedding:
                    failures.append(f"{url}: {missing_embedding}/{total} chunk(s) missing an embedding")
    finally:
        conn.close()

    logger.info(
        "validate: checked %d documents (%d new, %d changed, %d deleted, %d unchanged)",
        len(touched_urls), len(changeset["new"]), len(changeset["changed"]),
        len(changeset.get("deleted", [])), len(changeset.get("unchanged", [])),
    )
    if failures:
        for failure in failures:
            logger.error("validate: %s", failure)
        raise SystemExit(f"validate: {len(failures)} document(s) failed validation")
    logger.info("validate: all touched documents indexed successfully")

    # Only now - after every new/changed document has been confirmed to
    # actually have indexed rows above - is it safe to advance manifest.json
    # (the state stage_detect_changes diffs future runs against). Writing it
    # any earlier let a downstream failure (chunk/embed/index-pgvector, each
    # a separate pod) silently and permanently mark unindexed documents as
    # "already seen".
    manifest_key = f"{config.manifest_prefix}/manifest.json"
    manifest = store.get_json(manifest_key) or {}
    for doc_id in changeset.get("deleted", []):
        manifest.pop(doc_id, None)
    manifest.update(changeset.get("current_new_changed", {}))
    store.put_json(manifest_key, manifest)


# --------------------------------------------------------------------------
# reconcile-acls (ADR-0110, WP-25)
# --------------------------------------------------------------------------


def _iter_live_confluence_pages(config: IngestionConfig, auth) -> Dict[str, Optional[list]]:
    """Re-lists every page CURRENTLY visible and in-scope for each enabled
    Confluence source, the same CQL/directory/label selection
    stage_fetch_confluence uses (minus the body.storage expansion - this
    only needs to know a page exists and what governs its ACLs, not its
    content). Returns {page_url: required_groups | None} - None means
    "page exists (participates in the liveness/deletion check below) but
    this source's preserveAcl: false says never let reconciliation
    overwrite its acl_groups" (gitops/charts/rag-ingestion/values.yaml's
    per-source preserveAcl field, previously read by no code).

    ADR-0110's authoritative source of "current source authorization" is
    the declared platform config (source.requiredGroups,
    gitops/charts/rag-ingestion/values.yaml) - NOT a live Confluence
    restrictions API call (no such integration exists in this repo; see
    the ADR's own Context for why that per-document generalization is
    deferred to v0.4/ADR-0408). What IS live here is page *existence/
    visibility*: a page absent from this listing has either been deleted
    or the technical identity fetch-confluence authenticates as can no
    longer see it - both cases must fail closed the same way.

    Raises SystemExit on any source-listing failure, before any caller
    can act on a partial result - a transient Confluence outage must
    never be mistaken for "every page was deleted".

    Config commonly declares several sources against the SAME space (a
    real knowledge.tech config observed live 2026-08-21, WP-25: six
    sources - satellite-archi/build/run, openshift-archi/build/run - all
    pointing at one space, "SXSI", differing only in which directories/
    excludeLabels/requiredGroups they apply afterward). The CQL query
    itself (`space=X and type=page`) is identical across every source
    sharing a space; only the post-listing filtering below differs per
    source. `_raw_pages` caches each unique (base_url, space) listing so
    it is fetched over the network once no matter how many sources
    reference it, instead of once per source - a real 6x redundant
    network cost this reconcile pass was paying before this cache
    existed, plausibly most of why a single run took over 2 hours
    against this space.
    """
    live: Dict[str, Optional[list]] = {}
    raw_pages_by_space: Dict[tuple, list] = {}

    def _raw_pages(base_url: str, space: str) -> list:
        key = (base_url, space)
        if key not in raw_pages_by_space:
            raw_pages_by_space[key] = _list_confluence_space_pages(base_url, space, auth)
        return raw_pages_by_space[key]

    for source in config.confluence_sources:
        if not source.get("enabled", True):
            continue
        base_url = source["baseUrl"].rstrip("/")
        directories = source.get("directories") or []
        exclude_labels = set(source.get("excludeLabels") or [])
        required_groups = source.get("requiredGroups") or []
        preserve_acl = source.get("preserveAcl", True)

        for space in source.get("spaces") or []:
            for page in _raw_pages(base_url, space):
                if page["labels"] & exclude_labels:
                    continue
                if directories and not any(
                    _ancestor_path_matches(page["ancestor_titles"], directory) for directory in directories
                ):
                    continue
                live[page["page_url"]] = required_groups if preserve_acl else None
    return live


def _list_confluence_space_pages(base_url: str, space: str, auth) -> list:
    """Raw CQL page listing for one (base_url, space) pair - every field a
    caller might need to apply its own directory/label filtering
    afterward (labels, ancestor_titles, page_url), with no per-source
    filtering applied here. Cached by _iter_live_confluence_pages so each
    unique space is only ever listed once per reconcile-acls run,
    regardless of how many sources reference it.
    """
    pages: list = []
    # `start=`/`limit=` offset paging does not reliably terminate against
    # this endpoint - live-cluster-confirmed 2026-08-23: a real run against
    # this exact space paginated past start=294425 before Confluence itself
    # 504'd, 58 minutes in, having never seen a short page. This is the
    # same "content/search" endpoint stage_fetch_confluence's own loop
    # already moved off offset paging for (see that function's own comment
    # on `_links.next` cursor-based pagination) - this function was added
    # later for WP-25 and reintroduced the old approach instead of reusing
    # the fix. `_links.next`'s presence/absence is this endpoint's actual
    # documented end-of-results signal, unlike inferring it from a short
    # page.
    next_url = f"{base_url}/wiki/rest/api/content/search"
    next_params = {
        "cql": f'space="{space}" and type=page',
        "limit": 25,
        "expand": "ancestors,metadata.labels",
    }
    while next_url:
        try:
            resp = requests.get(
                next_url,
                params=next_params,
                auth=auth,
                timeout=HTTP_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise SystemExit(
                f"reconcile-acls: listing failed for space '{space}' ({exc}) - "
                "aborting with zero deletions rather than treating a transient "
                "outage as 'every page was deleted'"
            ) from exc
        payload = resp.json()
        results = payload.get("results", [])
        for page in results:
            labels = {
                label["name"]
                for label in page.get("metadata", {}).get("labels", {}).get("results", [])
            }
            ancestor_titles = [a["title"] for a in page.get("ancestors", [])]
            web_ui = page.get("_links", {}).get("webui", "")
            page_url = f"{base_url}/wiki{web_ui}"
            pages.append({"labels": labels, "ancestor_titles": ancestor_titles, "page_url": page_url})
        if pages and len(pages) % 200 == 0:
            # WP-25 2026-08-21: this listing call is the only work
            # stage_reconcile_acls does before its own next log line -
            # against a large real space, a live diagnostic run sat
            # completely silent for over an hour with no way to tell
            # "still working" from "stuck" short of exec'ing in to check
            # CPU/network activity directly. A line every 200 pages (8
            # batches of `limit`) costs nothing for a small space and
            # gives real mid-flight visibility for a large one.
            logger.info("reconcile-acls: listed %d page(s) so far in space '%s'", len(pages), space)
        next_link = payload.get("_links", {}).get("next")
        if next_link:
            next_url = f"{base_url}/wiki{next_link}"
            next_params = None  # the cursor URL already carries the full query string
        else:
            next_url = None
    return pages


def stage_reconcile_acls(config: IngestionConfig, store: CorpusStore) -> None:
    """ADR-0110: keeps indexed acl_groups aligned with current source
    authorization and removes chunks whose source is no longer visible or
    no longer under any declared source's scope. Runs over EVERY indexed
    confluence chunk (unlike the other stages, not just this run's
    changeset - an unchanged document's ACL can still change), fail
    closed: undeterminable authorization (page absent from the live
    listing) means removal, never "leave it as-is and hope". A no-op
    when this domain has no Confluence sources configured (every domain
    but knowledge.tech, and knowledge.tech before an operator configures
    any real space)."""
    if not config.confluence_sources:
        logger.info("reconcile-acls: no confluence sources configured, nothing to reconcile")
        return

    auth = _confluence_auth(config)
    live_pages = _iter_live_confluence_pages(config, auth)
    run_snapshot = _utcnow_iso()

    conn = _pg_connect(config)
    updated = 0
    deleted = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT source, metadata -> 'acl_groups' FROM document_embeddings "
                "WHERE metadata ->> 'source_type' = 'confluence'"
            )
            indexed = cur.fetchall()

            for source_url, current_acl in indexed:
                if isinstance(current_acl, str):  # defensive: some psycopg
                    current_acl = json.loads(current_acl)  # configs return jsonb as text
                current_acl = current_acl or []

                if source_url not in live_pages:
                    cur.execute("DELETE FROM document_embeddings WHERE source = %s", (source_url,))
                    deleted += cur.rowcount
                    # Audit: source + reason + this run's snapshot marker -
                    # never chunk content (ADR-0110 task 3).
                    logger.info(
                        "reconcile-acls: removed source=%s reason=no-longer-visible-or-in-scope snapshot=%s",
                        source_url, run_snapshot,
                    )
                    continue

                new_acl = live_pages[source_url]
                if new_acl is None:
                    # preserveAcl: false - existence confirmed (so this
                    # chunk is NOT deleted), acl_groups deliberately left
                    # untouched.
                    continue
                if sorted(current_acl) != sorted(new_acl):
                    cur.execute(
                        "UPDATE document_embeddings SET metadata = jsonb_set(metadata, '{acl_groups}', %s::jsonb), "
                        "updated_at = now() WHERE source = %s",
                        (json.dumps(new_acl), source_url),
                    )
                    updated += cur.rowcount
                    logger.info(
                        "reconcile-acls: updated acl_groups source=%s snapshot=%s", source_url, run_snapshot
                    )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    logger.info(
        "reconcile-acls: %d document(s) had acl_groups updated, %d document(s) removed "
        "(checked against %d live page(s))",
        updated, deleted, len(live_pages),
    )


# --------------------------------------------------------------------------
# CLI dispatch
# --------------------------------------------------------------------------

STAGE_FUNCTIONS = {
    "detect-changes": stage_detect_changes,
    "normalize": stage_normalize,
    "chunk": stage_chunk,
    "embed": stage_embed,
    "index-pgvector": stage_index_pgvector,
    "validate": stage_validate,
    "reconcile-acls": stage_reconcile_acls,
}


def main() -> int:
    parser = argparse.ArgumentParser(prog="rag-ingestion")
    parser.add_argument("stage", choices=STAGES)
    parser.add_argument(
        "--domain",
        help=(
            "logical knowledge domain this run targets (default: "
            "INGESTION_DOMAIN env or knowledge.tech). Fetch stages refuse "
            "to run for a domain they don't feed (ADR-0204)."
        ),
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.domain:
        os.environ["INGESTION_DOMAIN"] = args.domain
    config = load_config()
    logger.info("Starting RAG ingestion stage: %s (domain %s)", args.stage, config.domain)

    store = CorpusStore(config)
    adapter = SOURCE_ADAPTERS.get(args.stage)
    if adapter is not None:
        _run_source_adapter(adapter, config, store)
    else:
        STAGE_FUNCTIONS[args.stage](config, store)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
