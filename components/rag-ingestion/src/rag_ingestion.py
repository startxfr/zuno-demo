#!/usr/bin/env python3
"""Runtime entrypoint for the RAG ingestion pipeline.

The command contract is intentionally stable so the KFP pipeline can use a single
image for all stages (see files/pipeline.py.tpl in the Helm chart). Every stage
round-trips its state through S3 - KFP runs each stage in its own pod, so there is
no shared local disk between them:

    fetch-* / load-sxa-dump        -> <rawPrefix>/<doc_id>.json   (source adapters)
    detect-changes                 -> <manifestPrefix>/{manifest,changeset}.json
    normalize                      -> <normalizedPrefix>/<doc_id>.json
    chunk                          -> <normalizedPrefix>/<doc_id>.chunks.json
    embed                          -> (same file, chunks gain an "embedding" key)
    index-pgvector                 -> document_embeddings rows (data/rag/schema/004_rag_chunking.sql)
    validate                       -> exits non-zero if anything index-pgvector touched is incomplete

ADR-0204 (WP-22): the fetch stages are implementations of one source-adapter
interface (SOURCE_ADAPTERS below), each bound to exactly one logical knowledge
domain: fetch-redhat + fetch-confluence -> knowledge.tech, fetch-salesforce ->
knowledge.sales, fetch-aramis -> knowledge.adv, load-sxa-dump ->
knowledge.sxa-legacy, fetch-sxa -> knowledge.sxa (ADR-0217: a distinct,
already-anonymized weekly SXA source - no MariaDB, no MCP tools, unlike
load-sxa-dump). A pipeline run targets one domain (--domain /
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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Dict, Optional
from urllib.parse import urljoin, urlparse

import boto3
import psycopg
import requests
from bs4 import BeautifulSoup, NavigableString
from botocore.exceptions import ClientError
from pgvector.psycopg import register_vector

logger = logging.getLogger("rag_ingestion")

STAGES = (
    "fetch-redhat",
    "fetch-confluence",
    "fetch-salesforce",
    "fetch-aramis",
    "load-sxa-dump",
    "fetch-sxa",
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
    aramis_sources: list

    salesforce_instance_url: Optional[str]
    salesforce_token: Optional[str]
    aramis_base_url: Optional[str]
    aramis_token: Optional[str]

    # load-sxa-dump reads the operator-supplied, approved snapshot from its
    # own dedicated bucket (ADR-0025: no dump ever lives in git; ADR-0216:
    # a separate bucket from s3_bucket above, which holds unrelated corpus
    # content). Split schema/data key pair (2026-08-23 amendment): this
    # domain now reuses ADR-0217's already-anonymized corpus bucket (no
    # separate raw dump exists), which ships as a schema.sql/data.sql pair
    # rather than one combined mysqldump - same shape as sxa_corpus_*
    # below.
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
    sxa_mariadb_host: str
    sxa_mariadb_port: int
    sxa_mariadb_user: Optional[str]
    sxa_mariadb_password: Optional[str]
    sxa_mariadb_database: str

    # ADR-0217 (WP-067): fetch-sxa's own dedicated bucket - a distinct
    # source from sxa_dump_schema_s3_key/sxa_dump_data_s3_key/sxa_mariadb_*
    # above (knowledge.sxa-legacy). No MariaDB fields: this domain is
    # RAG-only, no live query target.
    sxa_corpus_schema_s3_key: Optional[str]
    sxa_corpus_data_s3_key: Optional[str]
    sxa_corpus_snapshot_id: Optional[str]
    sxa_corpus_s3_endpoint: str
    sxa_corpus_s3_bucket: str
    sxa_corpus_s3_region: str
    sxa_corpus_s3_path_style: bool
    sxa_corpus_aws_access_key_id: Optional[str]
    sxa_corpus_aws_secret_access_key: Optional[str]

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
        aramis_sources=_env_json("ARAMIS_SOURCES_JSON", []),
        salesforce_instance_url=os.environ.get("SALESFORCE_INSTANCE_URL"),
        salesforce_token=os.environ.get("SALESFORCE_TOKEN"),
        aramis_base_url=os.environ.get("ARAMIS_BASE_URL"),
        aramis_token=os.environ.get("ARAMIS_TOKEN"),
        sxa_dump_schema_s3_key=os.environ.get("SXA_DUMP_SCHEMA_S3_KEY"),
        sxa_dump_data_s3_key=os.environ.get("SXA_DUMP_DATA_S3_KEY"),
        sxa_snapshot_id=os.environ.get("SXA_SNAPSHOT_ID"),
        sxa_s3_endpoint=os.environ.get("SXA_S3_ENDPOINT", ""),
        sxa_s3_bucket=os.environ.get("SXA_S3_BUCKET", ""),
        sxa_s3_region=os.environ.get("SXA_S3_REGION", ""),
        sxa_s3_path_style=_env_bool("SXA_S3_PATH_STYLE", False),
        sxa_aws_access_key_id=os.environ.get("SXA_AWS_ACCESS_KEY_ID"),
        sxa_aws_secret_access_key=os.environ.get("SXA_AWS_SECRET_ACCESS_KEY"),
        sxa_mariadb_host=os.environ.get("SXA_MARIADB_HOST", ""),
        sxa_mariadb_port=_env_int("SXA_MARIADB_PORT", 3306),
        sxa_mariadb_user=os.environ.get("SXA_MARIADB_USER"),
        sxa_mariadb_password=os.environ.get("SXA_MARIADB_PASSWORD"),
        sxa_mariadb_database=os.environ.get("SXA_MARIADB_DATABASE", ""),
        sxa_corpus_schema_s3_key=os.environ.get("SXA_CORPUS_SCHEMA_S3_KEY"),
        sxa_corpus_data_s3_key=os.environ.get("SXA_CORPUS_DATA_S3_KEY"),
        sxa_corpus_snapshot_id=os.environ.get("SXA_CORPUS_SNAPSHOT_ID"),
        sxa_corpus_s3_endpoint=os.environ.get("SXA_CORPUS_S3_ENDPOINT", ""),
        sxa_corpus_s3_bucket=os.environ.get("SXA_CORPUS_S3_BUCKET", ""),
        sxa_corpus_s3_region=os.environ.get("SXA_CORPUS_S3_REGION", ""),
        sxa_corpus_s3_path_style=_env_bool("SXA_CORPUS_S3_PATH_STYLE", False),
        sxa_corpus_aws_access_key_id=os.environ.get("SXA_CORPUS_AWS_ACCESS_KEY_ID"),
        sxa_corpus_aws_secret_access_key=os.environ.get("SXA_CORPUS_AWS_SECRET_ACCESS_KEY"),
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

        for url in urls:
            try:
                page = base_resp if url == base_url else _http_get(url)
            except requests.RequestException as exc:
                logger.error("fetch-redhat: failed to fetch %s: %s", url, exc)
                continue
            title, text = _extract_title_and_text(page.text)
            if not text.strip():
                continue
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
            }
            technology = TECHNOLOGY_BY_PRODUCT_SLUG.get(source["productSlug"])
            if technology:
                record["technology"] = technology
            store.put_json(f"{config.raw_prefix}/{doc_id}.json", record)
            fetched += 1
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
# fetch-aramis (knowledge.adv)
# --------------------------------------------------------------------------


def _fetch_aramis(config: IngestionConfig, store: CorpusStore) -> int:
    """Aramis API/export ingestion -> one raw record per exported item,
    carrying ADR-0202's adv metadata extensions. Endpoint/token via
    env/ESO (operator-supplied); fixture-driven in tests."""
    if not config.aramis_sources:
        logger.info("fetch-aramis: no aramis sources configured")
        return 0
    if not config.aramis_base_url:
        raise SystemExit(
            "fetch-aramis: ARAMIS_BASE_URL not set - supply it via the chart "
            "before enabling this domain"
        )
    base = config.aramis_base_url.rstrip("/")
    headers = {}
    if config.aramis_token:
        headers["Authorization"] = f"Bearer {config.aramis_token}"
    fetched = 0
    for source in config.aramis_sources:
        if not source.get("enabled", True):
            continue
        endpoint = source["endpoint"]
        try:
            resp = requests.get(f"{base}{endpoint}", headers=headers, timeout=HTTP_TIMEOUT_SECONDS)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("fetch-aramis: export failed for %s: %s", endpoint, exc)
            continue
        payload = resp.json()
        items = payload if isinstance(payload, list) else payload.get("items", [])
        for item in items:
            item_id = str(item.get("id") or item.get("reference") or "")
            if not item_id:
                continue
            fields = {k: v for k, v in item.items() if not isinstance(v, (dict, list))}
            text = _render_record_text(fields)
            if not text.strip():
                continue
            record_url = f"aramis://{source.get('name', endpoint.strip('/'))}/{item_id}"
            doc_id = doc_id_for(record_url)
            record = {
                "doc_id": doc_id,
                "url": record_url,
                "title": item.get("title") or item.get("name") or record_url,
                "text": text,
                "domain": "knowledge.adv",
                "product": None,
                "version": None,
                "language": _normalize_language(source.get("language")),
                "source_type": "aramis-export",
                "classification": source.get("classification", "C2"),
                "acl_groups": source.get("requiredGroups") or [],
                "fetched_at": _utcnow_iso(),
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "provenance": record_url,
                "last_modified": item.get("updated_at") or item.get("modified"),
                # ADR-0202 adv extensions.
                "adv": {
                    "project_type": source.get("projectType"),
                    "status": item.get("status"),
                    "customer": item.get("customer"),
                },
            }
            store.put_json(f"{config.raw_prefix}/{doc_id}.json", record)
            fetched += 1
    return fetched


# --------------------------------------------------------------------------
# load-sxa-dump (knowledge.sxa-legacy)
# --------------------------------------------------------------------------


def _fetch_sxa_dump_bytes(config: IngestionConfig) -> Optional[bytes]:
    """Fetches the real dump from its own dedicated S3 bucket (ADR-0216) -
    a separate client from CorpusStore, which is bound to the shared
    corpus bucket and unrelated content. Split schema/data key pair
    (2026-08-23 amendment): this domain reuses ADR-0217's corpus bucket,
    which ships as schema.sql + data.sql rather than one combined
    mysqldump - fetches both and concatenates (schema first, so its
    CREATE TABLE statements run before data.sql's INSERTs)."""
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
    parts = []
    for key in (config.sxa_dump_schema_s3_key, config.sxa_dump_data_s3_key):
        try:
            resp = client.get_object(Bucket=config.sxa_s3_bucket, Key=key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in ("NoSuchKey", "404"):
                return None
            raise
        parts.append(resp["Body"].read())
    return b"\n".join(parts)


def _mariadb_connect(config: IngestionConfig):
    """ADR-0216: the live import/query target. A thin wrapper so tests can
    mock this one call rather than the whole pymysql API."""
    import pymysql
    import pymysql.cursors

    return pymysql.connect(
        host=config.sxa_mariadb_host,
        port=config.sxa_mariadb_port,
        user=config.sxa_mariadb_user,
        password=config.sxa_mariadb_password,
        database=config.sxa_mariadb_database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
    )


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
    the next line is not itself a comment once joined."""
    lines = [line for line in dump_text.splitlines() if not line.strip().startswith("--")]
    stripped_text = "\n".join(lines)

    statements = []
    current: list = []
    in_string: Optional[str] = None
    escaped = False
    for ch in stripped_text:
        current.append(ch)
        if escaped:
            escaped = False
            continue
        if ch == "\\" and in_string in ("'", '"'):
            escaped = True
            continue
        if in_string:
            if ch == in_string:
                in_string = None
            continue
        if ch in ("'", '"', "`"):
            in_string = ch
            continue
        if ch == ";":
            statements.append("".join(current[:-1]))
            current = []
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return [s.strip() for s in statements if s.strip()]


_CREATE_VIEW_RE = re.compile(
    r"^CREATE\s+(?:ALGORITHM=\S+\s+)?(?:DEFINER=\S+\s+)?(?:SQL\s+SECURITY\s+\S+\s+)?VIEW\b",
    re.IGNORECASE,
)
_CREATE_TABLE_NAME_RE = re.compile(
    r"^CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?(?P<table>\w+)`?",
    re.IGNORECASE,
)


def _import_sxa_dump_native(conn, dump_text: str) -> None:
    """Executes the real mysqldump SQL directly against MariaDB - no
    schema re-derivation (ADR-0216: the dump's own format is already
    MySQL-native, unlike ADR-0016's superseded Postgres-translation
    path). CREATE VIEW statements are skipped: confirmed live 2026-08-23,
    this phpMyAdmin-style export's views are hardcoded to their original
    source database name (`` `PROD_sxa`.`view_name` ``, embedded in every
    column reference too), which our own `sxa` database's user has no
    grant on and which doesn't exist here at all - "CREATE VIEW command
    denied". _load_sxa_dump only ever reads base tables via SHOW
    TABLES/SELECT *, so the views (and their harmless
    CREATE-TABLE-IF-NOT-EXISTS stand-in placeholders, which still import
    fine as empty, always-skipped tables) are simply not needed.

    Every CREATE TABLE statement gets an explicit `DROP TABLE IF EXISTS`
    right before it, regardless of whether the dump itself has one:
    confirmed live 2026-08-23, this phpMyAdmin export uses `CREATE TABLE
    IF NOT EXISTS` throughout (no `DROP TABLE IF EXISTS` anywhere) - a
    re-run (new snapshot, or a retry after a mid-import failure like the
    view-statement one above) would otherwise leave CREATE TABLE as a
    silent no-op against already-populated tables, so the following
    INSERTs collide on primary keys instead of re-importing cleanly. This
    is what _load_sxa_dump's own idempotency claim already assumed the
    dump would provide.

    A duplicate-key IntegrityError on any single statement is logged and
    skipped rather than aborting the whole import: confirmed live
    2026-08-23, this legacy production export has genuine primary-key
    collisions in a few peripheral permission/config tables (e.g.
    user_droits' (login, droit) pair repeated - real production data debt
    a strict constraint here was never enforced against upstream), even
    against a freshly dropped-and-recreated table. Failing the entire
    import over one bad statement would also lose every core business
    table (commande/devis/entreprise/contact/affaire/...) that comes
    after it in the dump, which matters far more than a handful of stale
    permission rows."""
    import pymysql

    with conn.cursor() as cur:
        for statement in _split_sql_statements(dump_text):
            if _CREATE_VIEW_RE.match(statement):
                continue
            create_table_match = _CREATE_TABLE_NAME_RE.match(statement)
            if create_table_match:
                cur.execute(f"DROP TABLE IF EXISTS `{create_table_match.group('table')}`")
            try:
                cur.execute(statement)
            except pymysql.err.IntegrityError as exc:
                logger.warning(
                    "load-sxa-dump: skipping a statement that violated a "
                    "constraint (%s): %s...",
                    exc, statement[:120],
                )
    conn.commit()


def _load_sxa_dump(config: IngestionConfig, store: CorpusStore) -> int:
    """ADR-0216 (WP-065): real per-record content, replacing the previous
    raw-DDL-chunk placeholder (never exercised against a real dump because
    none ever existed). Fetches the dump (schema.sql + data.sql pair) from
    its own dedicated S3 bucket, imports it NATIVELY into MariaDB (no
    schema translation), then extracts real per-record text from every
    imported table and emits one raw record per row - untouched, same as
    what the access-controlled sales-db MCP path serves (2026-08-23
    amendment: the operator-supplied content is trusted as-is, whatever
    its actual anonymization state; no transform happens here). Idempotent
    per snapshot id: re-running the same snapshot re-imports identical
    data, so records come out byte-identical (detect-changes sees
    unchanged sha256s) and a new snapshot version replaces content under
    the same identity with new snapshot metadata - the same discipline
    ADR-0206 already required."""
    if not config.sxa_dump_schema_s3_key or not config.sxa_dump_data_s3_key:
        raise SystemExit(
            "load-sxa-dump: SXA_DUMP_SCHEMA_S3_KEY/SXA_DUMP_DATA_S3_KEY not set - "
            "upload the approved snapshot to the dedicated SXA bucket and point "
            "this at it"
        )
    raw_bytes = _fetch_sxa_dump_bytes(config)
    if raw_bytes is None:
        raise SystemExit(
            f"load-sxa-dump: no object at s3://{config.sxa_s3_bucket}/"
            f"{{{config.sxa_dump_schema_s3_key},{config.sxa_dump_data_s3_key}}}"
        )
    dump_text = raw_bytes.decode("utf-8", errors="replace")
    checksum = hashlib.sha256(raw_bytes).hexdigest()
    snapshot_id = config.sxa_snapshot_id or f"sha256-{checksum[:16]}"
    imported_at = _utcnow_iso()

    if not re.search(r"CREATE TABLE", dump_text, re.IGNORECASE):
        raise SystemExit(
            "load-sxa-dump: no CREATE TABLE statement found - "
            "not a SQL schema export, refusing to import an unvalidated shape"
        )

    conn = _mariadb_connect(config)
    try:
        _import_sxa_dump_native(conn, dump_text)
        written = 0
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            tables = [next(iter(row.values())) for row in cur.fetchall()]
        for table in tables:
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM `{table}`")
                rows = cur.fetchall()
            for row in rows:
                text = _render_record_text(row)
                if not text.strip():
                    continue
                row_id = row.get("id", hashlib.sha256(repr(sorted(row.items())).encode()).hexdigest()[:12])
                record_url = f"sxa-mariadb://{table}/{row_id}"
                doc_id = doc_id_for(record_url)
                record = {
                    "doc_id": doc_id,
                    "url": record_url,
                    "title": f"SXA {table} #{row_id}",
                    "text": text,
                    "domain": "knowledge.sxa-legacy",
                    "product": None,
                    "version": None,
                    "language": "fr",
                    "source_type": "sxa-mariadb",
                    # Historical commercial data: C3 by default (ADR-0206) until the
                    # field-level review WP-23 records says otherwise.
                    "classification": "C3",
                    "acl_groups": [],
                    "fetched_at": imported_at,
                    "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "provenance": f"sxa MariaDB import snapshot {snapshot_id}",
                    # ADR-0206 snapshot discipline + ADR-0202 sxa-legacy extensions.
                    "sxa": {
                        "snapshot_id": snapshot_id,
                        "imported_at": imported_at,
                        "snapshot_checksum": checksum,
                        "table": table,
                    },
                }
                store.put_json(f"{config.raw_prefix}/{doc_id}.json", record)
                written += 1
    finally:
        conn.close()
    return written


# --------------------------------------------------------------------------
# fetch-sxa (knowledge.sxa)
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
                "fetch-sxa: no column order known for table %s (missing from "
                "schema and INSERT has no explicit column list) - skipping its rows",
                table,
            )
            continue
        for row_text in _split_row_tuples(match.group("values")):
            tokens = _split_top_level(row_text, ",")
            if len(tokens) != len(columns):
                logger.warning(
                    "fetch-sxa: row in table %s has %d values but %d known columns - skipping",
                    table, len(tokens), len(columns),
                )
                continue
            yield table, {col: _convert_sql_literal(tok) for col, tok in zip(columns, tokens)}


def _fetch_sxa_corpus_bytes(config: IngestionConfig, key: str) -> Optional[bytes]:
    """Fetches one object from fetch-sxa's own dedicated bucket (ADR-0217) -
    a separate client from CorpusStore, same pattern as
    _fetch_sxa_dump_bytes's separate client for sxa-legacy's own dedicated
    bucket. Distinct buckets: this source's provenance/trust model is not
    shared with sxa-legacy's."""
    from botocore.config import Config as BotoClientConfig

    client_kwargs: dict = {
        "region_name": config.sxa_corpus_s3_region or None,
        "aws_access_key_id": config.sxa_corpus_aws_access_key_id,
        "aws_secret_access_key": config.sxa_corpus_aws_secret_access_key,
        "config": BotoClientConfig(
            s3={"addressing_style": "path" if config.sxa_corpus_s3_path_style else "auto"},
            connect_timeout=10,
            read_timeout=60,
            retries={"max_attempts": 4, "mode": "standard"},
        ),
    }
    if config.sxa_corpus_s3_endpoint:
        client_kwargs["endpoint_url"] = config.sxa_corpus_s3_endpoint
    client = boto3.client("s3", **client_kwargs)
    try:
        resp = client.get_object(Bucket=config.sxa_corpus_s3_bucket, Key=key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in ("NoSuchKey", "404"):
            return None
        raise
    return resp["Body"].read()


def _fetch_sxa(config: IngestionConfig, store: CorpusStore) -> int:
    """ADR-0217 (WP-067): a weekly, already-anonymized SXA corpus export -
    distinct from load-sxa-dump/knowledge.sxa-legacy above. Parses
    schema.sql + data.sql directly in Python (no MariaDB, no SQL engine at
    all: mysqldump output is machine-generated and well-formed, the same
    assumption _split_sql_statements already relies on elsewhere in this
    file) and emits one raw, untouched record per row - the operator's
    content is trusted as-is (2026-08-23 amendment: no PII scanning
    either). Idempotent per snapshot id, same discipline as
    load-sxa-dump: a re-run against byte-identical schema/data produces
    byte-identical records (detect-changes sees unchanged sha256s)."""
    if not config.sxa_corpus_schema_s3_key or not config.sxa_corpus_data_s3_key:
        raise SystemExit(
            "fetch-sxa: SXA_CORPUS_SCHEMA_S3_KEY/SXA_CORPUS_DATA_S3_KEY not set - "
            "upload the approved weekly export to the dedicated SXA corpus "
            "bucket and point this at it"
        )
    schema_bytes = _fetch_sxa_corpus_bytes(config, config.sxa_corpus_schema_s3_key)
    if schema_bytes is None:
        raise SystemExit(
            f"fetch-sxa: no object at s3://{config.sxa_corpus_s3_bucket}/{config.sxa_corpus_schema_s3_key}"
        )
    data_bytes = _fetch_sxa_corpus_bytes(config, config.sxa_corpus_data_s3_key)
    if data_bytes is None:
        raise SystemExit(
            f"fetch-sxa: no object at s3://{config.sxa_corpus_s3_bucket}/{config.sxa_corpus_data_s3_key}"
        )
    schema_text = schema_bytes.decode("utf-8", errors="replace")
    data_text = data_bytes.decode("utf-8", errors="replace")
    checksum = hashlib.sha256(schema_bytes + b"\n" + data_bytes).hexdigest()
    snapshot_id = config.sxa_corpus_snapshot_id or f"sha256-{checksum[:16]}"
    fetched_at = _utcnow_iso()

    if "CREATE TABLE" not in schema_text.upper():
        raise SystemExit(
            "fetch-sxa: no CREATE TABLE statements found in schema.sql - "
            "not a mysqldump-style schema export, refusing to parse an unvalidated shape"
        )

    columns_by_table = _parse_create_table_columns(schema_text)
    written = 0
    for table, row in _parse_insert_rows(data_text, columns_by_table):
        text = _render_record_text(row)
        if not text.strip():
            continue
        row_id = row.get("id", hashlib.sha256(repr(sorted(row.items())).encode()).hexdigest()[:12])
        record_url = f"sxa-corpus://{table}/{row_id}"
        doc_id = doc_id_for(record_url)
        record = {
            "doc_id": doc_id,
            "url": record_url,
            "title": f"SXA {table} #{row_id}",
            "text": text,
            "domain": "knowledge.sxa",
            "product": None,
            "version": None,
            "language": "fr",
            "source_type": "sxa-corpus",
            "classification": "C3",
            "acl_groups": [],
            "fetched_at": fetched_at,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "provenance": f"sxa corpus weekly export snapshot {snapshot_id}",
            "sxa": {
                "snapshot_id": snapshot_id,
                "import_timestamp": fetched_at,
                "checksum": checksum,
                "table": table,
            },
        }
        store.put_json(f"{config.raw_prefix}/{doc_id}.json", record)
        written += 1
    return written


# --------------------------------------------------------------------------
# Adapter registry
# --------------------------------------------------------------------------

SOURCE_ADAPTERS = {
    adapter.stage: adapter
    for adapter in (
        SourceAdapter("fetch-redhat", "knowledge.tech", _fetch_redhat),
        SourceAdapter("fetch-confluence", "knowledge.tech", _fetch_confluence),
        SourceAdapter("fetch-salesforce", "knowledge.sales", _fetch_salesforce),
        SourceAdapter("fetch-aramis", "knowledge.adv", _fetch_aramis),
        SourceAdapter("load-sxa-dump", "knowledge.sxa-legacy", _load_sxa_dump),
        SourceAdapter("fetch-sxa", "knowledge.sxa", _fetch_sxa),
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
    for key in raw_keys:
        record = store.get_json(key)
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

    unchanged_ids = [doc_id for doc_id in current if doc_id not in new_ids and doc_id not in changed_ids]

    changeset = {
        "new": new_ids,
        "changed": changed_ids,
        "deleted": deleted_ids,
        "deleted_urls": deleted_urls,
        "unchanged": unchanged_ids,
        "generated_at": _utcnow_iso(),
    }
    store.put_json(f"{config.manifest_prefix}/changeset.json", changeset)
    store.put_json(manifest_key, current)
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


def stage_normalize(config: IngestionConfig, store: CorpusStore) -> None:
    changeset = _load_changeset(config, store, "normalize")
    if not changeset:
        return
    normalized = 0
    for doc_id in changeset["new"] + changeset["changed"]:
        raw = store.get_json(f"{config.raw_prefix}/{doc_id}.json")
        if not raw:
            logger.warning("normalize: raw document %s missing, skipping", doc_id)
            continue
        if raw.get("raw_html") is not None:
            title, text = _normalize_html(
                raw["raw_html"],
                preserve_code_blocks=config.chunk_preserve_code_blocks,
                preserve_tables=config.chunk_preserve_tables,
            )
        else:
            # Structured-source adapters (salesforce/aramis/sxa-dump) emit
            # ready text, not HTML - nothing to clean up.
            title, text = raw.get("title") or "", raw.get("text") or ""
        if not text.strip():
            logger.warning("normalize: %s produced no text after cleanup, skipping", raw["url"])
            continue
        domain = raw.get("domain") or config.domain
        # ADR-0205/WP-24: distinct fields, not the old conflated
        # `last_modified` - source_modified_at is the SOURCE's own
        # modification signal when the adapter captured one (Confluence's
        # history.lastUpdated.when, Salesforce's LastModifiedDate, Aramis'
        # updated_at/modified, or a best-effort HTTP Last-Modified header
        # for product docs - see _fetch_redhat); when a source genuinely
        # exposes none, `fetched_at` is the best available lower bound,
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
        normalized += 1
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


def stage_chunk(config: IngestionConfig, store: CorpusStore) -> None:
    changeset = _load_changeset(config, store, "chunk")
    if not changeset:
        return
    encoder = _get_token_encoder()
    doc_ids = changeset["new"] + changeset["changed"]
    total_chunks = 0
    for doc_id in doc_ids:
        doc = store.get_json(f"{config.normalized_prefix}/{doc_id}.json")
        if not doc:
            logger.warning("chunk: normalized document %s missing, skipping", doc_id)
            continue
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
        total_chunks += len(record["chunks"])
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
    changeset = _load_changeset(config, store, "embed")
    if not changeset:
        return
    doc_ids = changeset["new"] + changeset["changed"]
    embedded_docs = 0
    embedded_chunks = 0
    for doc_id in doc_ids:
        record = store.get_json(f"{config.normalized_prefix}/{doc_id}.chunks.json")
        if not record:
            logger.warning("embed: chunk document %s missing, skipping", doc_id)
            continue
        chunks = record["chunks"]
        for start in range(0, len(chunks), config.embedding_batch_size):
            batch = chunks[start:start + config.embedding_batch_size]
            texts = [c["text"] for c in batch]
            try:
                vectors = _embed_batch(texts, config)
            except requests.RequestException as exc:
                logger.error(
                    "embed: request failed for %s chunks %d-%d: %s",
                    doc_id, start, start + len(batch), exc,
                )
                continue
            for chunk, vector in zip(batch, vectors):
                if len(vector) != config.embedding_dimensions:
                    logger.error(
                        "embed: dimension mismatch for %s chunk %d (got %d, expected %d)",
                        doc_id, chunk["chunk_index"], len(vector), config.embedding_dimensions,
                    )
                    continue
                chunk["embedding"] = vector
                embedded_chunks += 1
        store.put_json(f"{config.normalized_prefix}/{doc_id}.chunks.json", record)
        embedded_docs += 1
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


def stage_index_pgvector(config: IngestionConfig, store: CorpusStore) -> None:
    changeset = _load_changeset(config, store, "index-pgvector")
    if not changeset:
        return
    conn = _pg_connect(config)
    indexed = 0
    deleted = 0
    try:
        with conn.cursor() as cur:
            doc_ids = changeset["new"] + changeset["changed"]
            for position, doc_id in enumerate(doc_ids, start=1):
                record = store.get_json(f"{config.normalized_prefix}/{doc_id}.chunks.json")
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
                    cur.execute(
                        """
                        INSERT INTO document_embeddings (source, chunk_index, title, content, embedding, metadata)
                        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                        ON CONFLICT (source, chunk_index) DO UPDATE SET
                            title = EXCLUDED.title,
                            content = EXCLUDED.content,
                            embedding = EXCLUDED.embedding,
                            metadata = EXCLUDED.metadata,
                            updated_at = now()
                        """,
                        (
                            record["url"],
                            chunk["chunk_index"],
                            record["title"],
                            chunk["text"],
                            chunk["embedding"],
                            json.dumps(metadata),
                        ),
                    )
                    indexed += 1
                # Commit per document, not per run: the S3 get_json above can
                # stall and a Patroni failover can kill the connection - a
                # single run-wide transaction loses every upserted row each
                # time either happens. The upsert makes partial progress
                # safe to re-run.
                conn.commit()
                if position % 100 == 0:
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
