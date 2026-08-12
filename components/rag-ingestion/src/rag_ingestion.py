#!/usr/bin/env python3
"""Runtime entrypoint for the RAG ingestion pipeline.

The command contract is intentionally stable so the KFP pipeline can use a single
image for all stages (see files/pipeline.py.tpl in the Helm chart). Every stage
round-trips its state through S3 - KFP runs each stage in its own pod, so there is
no shared local disk between them:

    fetch-redhat/fetch-confluence  -> <rawPrefix>/<doc_id>.json
    detect-changes                 -> <manifestPrefix>/{manifest,changeset}.json
    normalize                      -> <normalizedPrefix>/<doc_id>.json
    chunk                          -> <normalizedPrefix>/<doc_id>.chunks.json
    embed                          -> (same file, chunks gain an "embedding" key)
    index-pgvector                 -> document_embeddings rows (data/rag/schema/004_rag_chunking.sql)
    validate                       -> exits non-zero if anything index-pgvector touched is incomplete
"""
import argparse
import fnmatch
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
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
    "detect-changes",
    "normalize",
    "chunk",
    "embed",
    "index-pgvector",
    "validate",
)

DOC_LINK_PATTERN = re.compile(r"/(html|html-single)/")
MAX_DISCOVERED_LINKS = 50
HTTP_TIMEOUT_SECONDS = 30
HTTP_USER_AGENT = "zuno-rag-ingestion/1.0 (+https://github.com/startxfr/zuno-demo)"


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


@dataclass
class IngestionConfig:
    redhat_sources: list
    confluence_sources: list

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
        redhat_sources=_env_json("REDHAT_SOURCES_JSON", []),
        confluence_sources=_env_json("CONFLUENCE_SOURCES_JSON", []),
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
        embedding_dimensions=_env_int("EMBEDDING_DIMENSIONS", 384),
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
            "config": BotoClientConfig(
                s3={"addressing_style": "path" if config.s3_path_style else "auto"}
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


def doc_id_for(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
# fetch-redhat
# --------------------------------------------------------------------------


def stage_fetch_redhat(config: IngestionConfig, store: CorpusStore) -> None:
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
                "product": source["productSlug"],
                "version": source["version"],
                "language": _normalize_language((source.get("languages") or ["en-US"])[0]),
                "source_type": "product-doc",
                "classification": "C1",
                "acl_groups": [],
                "fetched_at": _utcnow_iso(),
                "sha256": hashlib.sha256(page.text.encode("utf-8")).hexdigest(),
                "provenance": url,
            }
            store.put_json(f"{config.raw_prefix}/{doc_id}.json", record)
            fetched += 1
    logger.info("fetch-redhat: wrote %d raw documents", fetched)


# --------------------------------------------------------------------------
# fetch-confluence
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


def stage_fetch_confluence(config: IngestionConfig, store: CorpusStore) -> None:
    if not config.confluence_sources:
        logger.info("fetch-confluence: no confluence sources configured")
        return
    auth = _confluence_auth(config)
    fetched = 0
    for source in config.confluence_sources:
        if not source.get("enabled", True):
            continue
        base_url = source["baseUrl"].rstrip("/")
        directories = source.get("directories") or []
        exclude_labels = set(source.get("excludeLabels") or [])
        required_groups = source.get("requiredGroups") or []

        for space in source.get("spaces") or []:
            start = 0
            limit = 25
            while True:
                params = {
                    "cql": f'space="{space}" and type=page',
                    "start": start,
                    "limit": limit,
                    "expand": "body.storage,ancestors,history.lastUpdated,metadata.labels",
                }
                try:
                    resp = requests.get(
                        f"{base_url}/wiki/rest/api/content/search",
                        params=params,
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
                    record = {
                        "doc_id": doc_id,
                        "url": page_url,
                        "title": page.get("title", page_url),
                        "raw_html": html,
                        "product": source.get("name", space),
                        "version": None,
                        "language": "en",
                        "source_type": "confluence",
                        "classification": "C2",
                        "acl_groups": required_groups,
                        "fetched_at": _utcnow_iso(),
                        "sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
                        "provenance": page_url,
                        "last_modified": page.get("history", {}).get("lastUpdated", {}).get("when"),
                    }
                    store.put_json(f"{config.raw_prefix}/{doc_id}.json", record)
                    fetched += 1
                if len(results) < limit:
                    break
                start += limit
    logger.info("fetch-confluence: wrote %d raw documents", fetched)


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
        title, text = _normalize_html(
            raw["raw_html"],
            preserve_code_blocks=config.chunk_preserve_code_blocks,
            preserve_tables=config.chunk_preserve_tables,
        )
        if not text.strip():
            logger.warning("normalize: %s produced no text after cleanup, skipping", raw["url"])
            continue
        record = {
            "doc_id": doc_id,
            "url": raw["url"],
            "title": raw.get("title") or title,
            "text": text,
            "metadata": {
                "product": raw.get("product"),
                "version": raw.get("version"),
                "language": _normalize_language(raw.get("language")),
                "source_type": raw.get("source_type"),
                "classification": raw.get("classification", "C1"),
                "acl_groups": raw.get("acl_groups") or [],
                "last_modified": raw.get("last_modified") or raw.get("fetched_at"),
                "provenance": raw.get("provenance") or raw.get("url"),
            },
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
    payload = {"model": config.embedding_model, "input": texts}
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
            for doc_id in changeset["new"] + changeset["changed"]:
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
    for doc_id in changeset["new"] + changeset["changed"]:
        record = store.get_json(f"{config.normalized_prefix}/{doc_id}.chunks.json")
        if record:
            touched_urls.add(record["url"])

    conn = _pg_connect(config)
    failures = []
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
# CLI dispatch
# --------------------------------------------------------------------------

STAGE_FUNCTIONS = {
    "fetch-redhat": stage_fetch_redhat,
    "fetch-confluence": stage_fetch_confluence,
    "detect-changes": stage_detect_changes,
    "normalize": stage_normalize,
    "chunk": stage_chunk,
    "embed": stage_embed,
    "index-pgvector": stage_index_pgvector,
    "validate": stage_validate,
}


def main() -> int:
    parser = argparse.ArgumentParser(prog="rag-ingestion")
    parser.add_argument("stage", choices=STAGES)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger.info("Starting RAG ingestion stage: %s", args.stage)

    config = load_config()
    store = CorpusStore(config)
    STAGE_FUNCTIONS[args.stage](config, store)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
