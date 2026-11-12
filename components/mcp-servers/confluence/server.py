"""confluence MCP server (ADR-0117, protocol per ADR-0043).

Zuno's first real external MCP integration: a real, standards-compliant
MCP server (the `mcp` SDK's `MCPServer`, streamable-HTTP transport,
mounted at /mcp - same shape as `components/mcp-servers/salesforce`)
fronting the real Confluence Cloud REST API, replacing
`components/mcp-gateway/app/handlers/confluence.py`'s demo-mode handler.

Exposes exactly the four capabilities ADR-0116 already named for
Confluence: `confluence.page.search`, `confluence.page.read`,
`confluence.page.create`, `confluence.page.update` (tool functions below:
`search_pages`, `read_page`, `create_page`, `update_page` - the MCP
Gateway's binding registry maps the logical capability ID to whichever
`provider_tool` name this server actually exposes, per ADR-0116).

Authentication mode is `service-identity` (ADR-0208): every call uses the
same technical Confluence identity (email + API token, HTTP Basic Auth -
the standard Atlassian Cloud REST API convention, matching
UnifAI's Confluence source for consistency), sourced from an `ExternalSecret` resolving
`zuno/confluence/technical` (seeded by
`ansible/roles/vault/tasks/install.yml`, keys `url`/`email`/`token`) -
never hardcoded, per ADR-0024. The MCP Gateway's `policy.evaluate()`
authorizes the caller's agent/task/role/classification *before* this
shared service identity is ever used, satisfying ADR-0208's requirement
that a service-identity binding enforce Zuno subject/role scope itself
rather than relying on the downstream credential to do so - this server
has no per-user identity to check, by design.

ADR-0037: the gateway is still the trust boundary. This server does not
re-validate the caller's end-user JWT; every /mcp call must carry the
gateway's Vault-Transit-signed call assertion (WP-250: the shared workload token is retired).

    POST /mcp    - real MCP streamable-HTTP transport (initialize,
                   tools/list, tools/call)
    GET /healthz -> 200 once CONFLUENCE_BASE_URL/EMAIL/API_TOKEN are
                   configured. Deliberately does NOT make a live
                   Confluence call on every probe (unlike confluence's
                   healthz, which does a free local DB round-trip) - a
                   Kubernetes liveness/readiness probe firing every
                   ~10-15s against a real external SaaS API would be a
                   needless, avoidable load/quota cost.
"""
from __future__ import annotations

import base64
import fnmatch
import hashlib
import hmac
import json
import logging
import math
import os
import re
import string
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Mapping, Optional, Tuple

import httpx
from fastapi import FastAPI
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

CONFLUENCE_BASE_URL = os.getenv("CONFLUENCE_BASE_URL", "")
CONFLUENCE_EMAIL = os.getenv("CONFLUENCE_EMAIL", "")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN", "")
HTTP_TIMEOUT_SECONDS = float(os.getenv("CONFLUENCE_HTTP_TIMEOUT_SECONDS", "20"))

logger = logging.getLogger("confluence_mcp")


# --------------------------------------------------------------------------
# ADR-0603 M12 (WP-225 lot B): the signed caller context.
#
# The gateway signs who a call is for (sub, groups, email, username, the tool,
# a timestamp, this server's name) from the token it has validated, and sends it as
# X-Zuno-Caller-Context / X-Zuno-Caller-Signature (components/mcp-gateway/app/
# caller_context.py), only to backends whose binding declares caller_context.
# The key is derived per backend from the workload token this server already holds. Duplicated in each server: an image is built from its own
# directory only (ADR-0119). A missing, forged, stale or other-tool context
# verifies as None; a server that needs it then refuses (fail closed).
# --------------------------------------------------------------------------

# The audience of the caller context: this server's backend name in
# platform/bindings/tools/tool-bindings.yaml.
CALLER_CONTEXT_AUDIENCE = "confluence"


def _verified_caller(headers: Optional[Mapping[str, str]], tool: str) -> Optional[Dict[str, Any]]:
    # WP-250: the caller is read from the verified call assertion only (`ctx`, see the
    # call-assertion verifier block). No shared secret is involved any more.
    return _assertion_caller(headers, tool)


def _caller(ctx: Optional[Context], tool: str) -> Optional[Dict[str, Any]]:
    """The verified caller of this tool call, or None (no context, or not verified)."""
    if ctx is None:
        return None
    try:
        headers = ctx.headers
    except Exception:  # noqa: BLE001 - outside a request (a direct call in a test)
        return None
    return _verified_caller(headers, tool)


def _group_allowlist(env_name: str) -> Dict[str, List[str]]:
    """A JSON object {Keycloak group: [pattern]} from `env_name`.

    Empty or unset: {} (no allowlist, the behaviour before WP-225). Malformed: a
    configured but empty allowlist, which refuses every caller (fail closed)."""
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return {}
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError:
        return {"": []}
    if not isinstance(doc, dict):
        return {"": []}
    if not doc:
        return {}  # "{}" (the chart default rendered as JSON) is no allowlist
    return {
        str(group): [str(p).strip() for p in patterns if isinstance(p, str) and p.strip()]
        for group, patterns in doc.items()
        if isinstance(patterns, list)
    } or {"": []}


def _allowed(target: str, caller: Optional[Dict[str, Any]], allowlist: Dict[str, List[str]]) -> bool:
    """True when one of the caller's groups lists a pattern (fnmatch, case-insensitive)
    matching `target`. No verified caller: False."""
    if caller is None:
        return False
    target = target.lower()
    for group in caller["groups"]:
        for pattern in allowlist.get(group, ()):
            if fnmatch.fnmatchcase(target, pattern.lower()):
                return True
    return False


# ADR-0603 M12: the Confluence spaces each Keycloak group may reach through the
# shared technical identity. CONFLUENCE_SPACE_ALLOWLIST is a JSON object
# {group: [space key pattern]} (chart value spaceAllowlist.groups); "*" is every
# space. Empty: no allowlist, the behaviour before WP-225. Scope "all" checks
# reads and writes, "write" only create_page and update_page.
SPACE_ALLOWLIST_ENV = "CONFLUENCE_SPACE_ALLOWLIST"


def _space_allowlist_scope() -> str:
    value = os.getenv("CONFLUENCE_SPACE_ALLOWLIST_SCOPE", "all").strip().lower()
    return value if value in ("all", "write") else "all"


def _space_policy(ctx: Optional[Context], tool: str, *, write: bool) -> Optional[Tuple[Dict[str, Any], Dict[str, List[str]]]]:
    """None when no allowlist applies to this call; else the verified caller and the
    allowlist. Raises PermissionError when an allowlist applies and the caller is not
    verified (no signed context, or a forged or stale one)."""
    allowlist = _group_allowlist(SPACE_ALLOWLIST_ENV)
    if not allowlist or (not write and _space_allowlist_scope() == "write"):
        return None
    caller = _caller(ctx, tool)
    if caller is None:
        raise PermissionError(
            f"{tool} is refused: a space allowlist is configured and the call carries no verified caller context"
        )
    return caller, allowlist


def _check_space(space_key: str, policy: Optional[Tuple[Dict[str, Any], Dict[str, List[str]]]]) -> None:
    if policy is None:
        return
    caller, allowlist = policy
    if not _allowed(space_key or "", caller, allowlist):
        raise PermissionError(
            f"space {space_key!r} is outside the space allowlist of the caller's groups (ADR-0603 M12)"
        )


def _check_page_space(page_id: str, space_key: str, policy: Optional[Tuple[Dict[str, Any], Dict[str, List[str]]]]) -> None:
    """A page the caller names by id: outside the caller's spaces it answers as a
    missing page, so the refusal tells nothing of where the page lives."""
    try:
        _check_space(space_key, policy)
    except PermissionError:
        raise ValueError(f"no Confluence page with id {page_id}") from None


def _literal_spaces(policy: Tuple[Dict[str, Any], Dict[str, List[str]]]) -> Optional[List[str]]:
    """The caller's allowed space keys when they are all literal keys, for a CQL
    `space in (...)` clause; None when a pattern is a wildcard (post-filter only)."""
    caller, allowlist = policy
    keys: List[str] = []
    for group in caller["groups"]:
        for pattern in allowlist.get(group, ()):
            if not _SPACE_KEY_RE.fullmatch(pattern) or any(c in pattern for c in "*?["):
                return None
            keys.append(pattern)
    return sorted(set(keys))


class ConfluenceConfigError(RuntimeError):
    pass


def _require_config() -> None:
    if not (CONFLUENCE_BASE_URL and CONFLUENCE_EMAIL and CONFLUENCE_API_TOKEN):
        raise ConfluenceConfigError(
            "CONFLUENCE_BASE_URL/CONFLUENCE_EMAIL/CONFLUENCE_API_TOKEN are required "
            "(sourced from an ExternalSecret against secret/zuno/confluence/technical "
            "- never hardcoded, ADR-0024)"
        )


def _client() -> httpx.AsyncClient:
    _require_config()
    return httpx.AsyncClient(
        base_url=f"{CONFLUENCE_BASE_URL.rstrip('/')}/wiki/rest/api",
        auth=(CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN),
        timeout=HTTP_TIMEOUT_SECONDS,
    )


def _summarize(content: Dict[str, Any]) -> Dict[str, Any]:
    """Common projection of a Confluence `content` object into the shape
    every tool below returns - `id`, `title`, `space`, `url`, `version`,
    plus a `body` excerpt when the response expanded it. Mirrors the demo
    handler's field names (`id`, `title`, `space`, `url`) it replaces, so
    existing callers/tests reading those fields keep working."""
    space_key = (content.get("space") or {}).get("key", "")
    webui = ((content.get("_links") or {}).get("webui")) or ""
    base = (content.get("_links") or {}).get("base", CONFLUENCE_BASE_URL)
    body = ((content.get("body") or {}).get("storage") or {}).get("value")
    return {
        "id": content.get("id"),
        "title": content.get("title"),
        "space": space_key,
        "url": f"{base}{webui}" if webui else None,
        "version": (content.get("version") or {}).get("number"),
        **({"body": body} if body is not None else {}),
    }


# A full natural-language question passed verbatim into CQL's
# text~"<phrase>" operator rarely matches real page content: Confluence's
# fuzzy text search still needs the words to actually co-occur, and
# interrogative/meta words ("what", "does", "the latest internal Confluence
# doc") dilute a query that would otherwise match on its few significant
# words ("RHOAI 3.5 EA2 rollout"). Only applied above _QUERY_WORD_THRESHOLD
# words - a caller already passing a short, targeted query (the common case
# for direct tool use, e.g. "model serving") is left untouched.
_QUERY_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "do", "does", "did",
    "what", "when", "where", "who", "how", "why", "which", "say", "says",
    "said", "about", "please", "can", "could", "would", "tell", "me",
    "of", "for", "to", "in", "on", "at", "and", "or", "that", "this",
    "it", "its", "i", "you", "we", "doc", "docs", "document", "documents",
    "confluence", "internal", "latest",
})
_QUERY_WORD_THRESHOLD = 5
# Live-caught 2026-09-05 (ADR-0550 webinar rehearsal): three deliberately
# unrelated multi-word queries (a container-platform topic, a hospital EHR
# migration, renewable energy) each still came back with non-empty
# `results` from Confluence Cloud's own CQL `text~` ranking - it behaves
# closer to a fuzzy per-word OR match than an AND/phrase match, so any
# query sharing even one common IT word with a real page counts as a
# "hit" upstream. ADR-0034 escalates effective_classification to C2 the
# moment this tool returns ANY result, so an over-permissive match here
# has a real security-classification consequence, not just noisy search
# results - hence the post-filter in `_is_relevant_result` below, not just
# a search-quality nicety.
_MIN_TITLE_RELEVANCE_RATIO = 0.5


def _significant_words(query: str) -> List[str]:
    """Query words surviving stopword-stripping - shared by
    `_cql_query_text` (what CQL actually searches for) and
    `_is_relevant_result` (the post-filter below), so both always agree
    on what "significant" means for a given query."""
    return [
        stripped
        for w in query.split()
        if (stripped := w.strip(string.punctuation)) and stripped.lower() not in _QUERY_STOPWORDS
    ]


# Global keys are letters/digits; personal spaces are "~" + username or
# account id (e.g. ~john.doe, ~557058:3f1c...). No quote or space can pass.
_SPACE_KEY_RE = re.compile(r"~?[A-Za-z0-9][A-Za-z0-9_.:@-]{0,127}")
# Confluence content ids are numeric; checked before they reach a URL path.
_PAGE_ID_RE = re.compile(r"[0-9]{1,20}")
_MAX_SEARCH_LIMIT = 50


def _check_page_id(page_id: str) -> None:
    """ADR-0603 / WP-222: page_id is model-chosen and lands in a URL path."""
    if not _PAGE_ID_RE.fullmatch(str(page_id)):
        raise ValueError("page_id must be a numeric Confluence content id")


def _cql_escape(text: str) -> str:
    """Escapes a value for use inside a double-quoted CQL string literal."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _cql_query_text(query: str) -> str:
    """Reduces a long, question-shaped query to its significant words for
    CQL's text~ operator; returns short queries unchanged."""
    words = query.split()
    if len(words) <= _QUERY_WORD_THRESHOLD:
        return query
    return " ".join(_significant_words(query)) or query


def _is_relevant_result(query: str, title: str) -> bool:
    """Re-checks a CQL hit against the page TITLE only - the sole field
    `search_pages`'s `expand=space,version` actually fetches, not the
    body - requiring at least half of the query's own significant words
    (case-insensitive substring, minimum 1) to appear in it.

    Chosen over an all-words-must-match rule because the one real,
    live-verified match this server already relies on (ADR-0330's
    "version 4.14" -> "Procedure UPGRADE 4.13 vers 4.14 cluster
    data-preprod") only hits 3 of its 5 significant words in the title
    ("OpenShift" and "version" are absent from that real title) - a
    full-AND rule would have broken that known-good scenario. A query
    with no significant words at all (rare - a short query of only
    stopwords) is never filtered, since there is nothing to check
    relevance against."""
    significant = _significant_words(query)
    if not significant:
        return True
    title_lower = (title or "").lower()
    hits = sum(1 for word in significant if word.lower() in title_lower)
    return hits >= max(1, math.ceil(len(significant) * _MIN_TITLE_RELEVANCE_RATIO))


mcp_server = MCPServer(
    name="confluence",
    version="0.1.0",
    instructions=(
        "Live Confluence Cloud access: search/read pages for current state, "
        "create/update pages for writes. Indexed knowledge.tech (ADR-0330) "
        "is the normal read path (ADR-0205) - use these tools only for "
        "freshness-sensitive reads or any write."
    ),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Same requirement as salesforce/server.py: the mounted MCP sub-app's
    # session manager needs the parent app's lifespan to run its task group.
    async with mcp_server.session_manager.run():
        yield


app = FastAPI(title="confluence MCP server", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    _require_config()
    return {"status": "ok"}


@mcp_server.tool()
async def search_pages(
    query: str, space: Optional[str] = None, limit: int = 10, ctx: Optional[Context] = None
) -> Dict[str, Any]:
    """Search Confluence pages by text (CQL), optionally scoped to a space key."""
    # ADR-0602 / WP-222: both values are model-chosen and land inside a CQL
    # string literal, so a quote in either would widen the query.
    if space and not _SPACE_KEY_RE.fullmatch(space):
        raise ValueError("space must be a Confluence space key (letters, digits, _ . : @ -, optional leading ~)")
    policy = _space_policy(ctx, "search_pages", write=False)
    if space:
        _check_space(space, policy)
    limit = max(1, min(int(limit), _MAX_SEARCH_LIMIT))
    cql = f'type=page and text~"{_cql_escape(_cql_query_text(query))}"'
    if space:
        cql = f'space="{space}" and {cql}'
    elif policy is not None:
        # ADR-0603 M12: no space named, so the search covers only the caller's
        # spaces - in CQL when they are literal keys, and always by the
        # post-filter below.
        literal = _literal_spaces(policy)
        if literal is not None:
            if not literal:
                raise PermissionError("no Confluence space is allowed to the caller's groups (ADR-0603 M12)")
            spaces = ",".join(f'"{key}"' for key in literal)
            cql = f"space in ({spaces}) and {cql}"
    async with _client() as client:
        resp = await client.get(
            "/content/search",
            params={"cql": cql, "limit": limit, "expand": "space,version"},
        )
        resp.raise_for_status()
        payload = resp.json()

    results = [_summarize(item) for item in payload.get("results", [])]
    # ADR-0034/live-caught 2026-09-05: drop hits CQL's own fuzzy ranking
    # returned but that don't actually look like the query - see
    # _is_relevant_result's own docstring for why this matters beyond
    # search quality.
    results = [r for r in results if _is_relevant_result(query, r.get("title") or "")]
    if policy is not None:
        results = [r for r in results if _allowed(r.get("space") or "", *policy)]
    return {"query": query, "results": results, "count": len(results)}


@mcp_server.tool()
async def read_page(page_id: str, ctx: Optional[Context] = None) -> Dict[str, Any]:
    """Read a Confluence page's current content and metadata by id."""
    _check_page_id(page_id)
    policy = _space_policy(ctx, "read_page", write=False)
    async with _client() as client:
        resp = await client.get(
            f"/content/{page_id}",
            params={"expand": "space,version,body.storage"},
        )
        if resp.status_code == 404:
            raise ValueError(f"no Confluence page with id {page_id}")
        resp.raise_for_status()
        payload = resp.json()

    # ADR-0603 M12: the space is known only once the page is fetched; nothing of
    # a page outside the caller's spaces is returned, not even its space.
    _check_page_space(page_id, (payload.get("space") or {}).get("key", ""), policy)
    return {"page": _summarize(payload)}


@mcp_server.tool()
async def create_page(
    space_key: str, title: str, body_html: str, parent_id: Optional[str] = None, ctx: Optional[Context] = None
) -> Dict[str, Any]:
    """Create a new Confluence page in the given space, optionally under a parent page."""
    policy = _space_policy(ctx, "create_page", write=True)
    _check_space(space_key, policy)
    if parent_id and policy is not None:
        # ADR-0603 M12: the parent must be a page of the same, allowed space; a parent
        # elsewhere answers as a missing page.
        _check_page_id(parent_id)
        async with _client() as client:
            parent_resp = await client.get(f"/content/{parent_id}", params={"expand": "space"})
            if parent_resp.status_code == 404:
                raise ValueError(f"no Confluence page with id {parent_id}")
            parent_resp.raise_for_status()
            parent_space = ((parent_resp.json().get("space") or {}).get("key")) or ""
        _check_page_space(parent_id, parent_space, policy)
        if parent_space.lower() != space_key.lower():
            raise ValueError(f"no Confluence page with id {parent_id} in space {space_key!r}")
    request_body: Dict[str, Any] = {
        "type": "page",
        "title": title,
        "space": {"key": space_key},
        "body": {"storage": {"value": body_html, "representation": "storage"}},
    }
    if parent_id:
        request_body["ancestors"] = [{"id": parent_id}]

    async with _client() as client:
        resp = await client.post("/content", json=request_body)
        if resp.status_code == 400:
            raise ValueError(f"Confluence rejected page creation: {resp.text}")
        resp.raise_for_status()
        payload = resp.json()

    return {"page": _summarize(payload), "created": True}


@mcp_server.tool()
async def update_page(
    page_id: str, body_html: str, title: Optional[str] = None, ctx: Optional[Context] = None
) -> Dict[str, Any]:
    """Update an existing Confluence page's content (and optionally its title) by id."""
    _check_page_id(page_id)
    policy = _space_policy(ctx, "update_page", write=True)
    async with _client() as client:
        current_resp = await client.get(f"/content/{page_id}", params={"expand": "version,space"})
        if current_resp.status_code == 404:
            raise ValueError(f"no Confluence page with id {page_id}")
        current_resp.raise_for_status()
        current = current_resp.json()
        # ADR-0603 M12: the page's own space, read before any write.
        checked_space = (current.get("space") or {}).get("key", "")
        _check_page_space(page_id, checked_space, policy)
        current_version = (current.get("version") or {}).get("number", 0)

        request_body: Dict[str, Any] = {
            "id": page_id,
            "type": "page",
            "title": title or current.get("title"),
            "space": {"key": (current.get("space") or {}).get("key")},
            "body": {"storage": {"value": body_html, "representation": "storage"}},
            "version": {"number": current_version + 1},
        }
        resp = await client.put(f"/content/{page_id}", json=request_body)
        if resp.status_code == 409:
            raise ValueError(
                f"Confluence page {page_id} was modified concurrently (version conflict) - retry"
            )
        resp.raise_for_status()
        payload = resp.json()

    # ADR-0603 M12, accepted race: the space is checked on the GET, and the PUT names
    # that same space and the next version number, so a page moved in between mostly
    # fails as a version conflict. If Confluence still reports another space, the
    # write has happened; it is logged, not hidden.
    written_space = (payload.get("space") or {}).get("key")
    if policy is not None and written_space and written_space != checked_space:
        logger.warning(
            "update_page %s: checked space %r but Confluence reports %r after the write",
            page_id, checked_space, written_space,
        )
    return {"page": _summarize(payload), "updated": True}


# --------------------------------------------------------------------------
# BEGIN call-assertion verifier (WP-225 lot C)
#
# ADR-0602 clause 10 / ADR-0603 M14: the per-call assertion. With
# MCP_OUTBOUND_IDENTITY=assertion the gateway sends, instead of the caller's
# bearer, a JWT it signs with a key only it holds (EdDSA, typ zuno-call+jwt; see
# components/mcp-gateway/app/call_assertion.py): iss mcp-gateway, aud this
# server's backend name, sub the caller, act the gateway, tool the backend tool
# name, exp at most 60 s after iat, jti. This server holds the public key
# (MCP_CALL_ASSERTION_PUBLIC_KEY, PEM) and verifies it here, before any MCP
# handling. A forged, expired, too long-lived or misaddressed assertion is
# refused (401). A tools/call whose name is not the assertion's tool, whose
# arguments do not match its `args` hash, or whose jti was already consumed, is
# refused (403); a body that is not JSON 400, one past the size cap 413. With
# A request without a valid assertion is always refused (WP-250 lot 2: the env switch
# MCP_CALL_ASSERTION_REQUIRED is no longer read).
# WP-250: the assertion may carry `ctx` (groups, email, email_verified, username), the
# caller context signed with the assertion. After verification the middleware hands it to
# the tool code as the header X-Zuno-Assertion-Caller; any such header sent by a client
# is removed first, so only a verified assertion can set it (`_assertion_caller`).
# This block is byte-identical in confluence, git-forge, salesforce and aap
# (each image is built from its own directory, ADR-0119); the lot C tests
# compare the copies.
# --------------------------------------------------------------------------

import logging as _assertion_logging  # noqa: E402 - part of the self-contained block

import jwt as _assertion_jwt  # noqa: E402
from cryptography.hazmat.primitives import serialization as _assertion_serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey as _AssertionPublicKey  # noqa: E402

_ASSERTION_LOG = _assertion_logging.getLogger("zuno.call_assertion")
CALL_ASSERTION_TYPE = "zuno-call+jwt"
CALL_ASSERTION_ISSUER = "mcp-gateway"
CALL_ASSERTION_MAX_TTL_SECONDS = 60
CALL_ASSERTION_LEEWAY_SECONDS = 5
# The largest request body read to check a tools/call (git.file.write carries a whole
# file): MCP_CALL_ASSERTION_MAX_BODY_BYTES, chart callAssertion.maxBodyBytes. A larger
# body is refused with 413.
CALL_ASSERTION_DEFAULT_MAX_BODY_BYTES = 16 * 1024 * 1024
_CALL_ASSERTION_KEYS: Dict[str, Any] = {}
_CALL_ASSERTION_SEEN: Dict[str, float] = {}


class CallAssertionError(ValueError):
    """The assertion is not acceptable; the message is safe to return."""


def _call_assertion_required() -> bool:
    # WP-250 lot 2: always. The assertion is the only way in (the shared workload token is
    # gone); without a configured public key every request is refused (fail closed).
    return True


def _call_assertion_max_body_bytes() -> int:
    raw = os.getenv("MCP_CALL_ASSERTION_MAX_BODY_BYTES", "").strip()
    try:
        value = int(raw) if raw else CALL_ASSERTION_DEFAULT_MAX_BODY_BYTES
    except ValueError:
        value = CALL_ASSERTION_DEFAULT_MAX_BODY_BYTES
    return value if value > 0 else CALL_ASSERTION_DEFAULT_MAX_BODY_BYTES


def _call_assertion_args_hash(arguments: Any) -> str:
    """sha256 of the canonical JSON of tools/call params.arguments (the `args` claim)."""
    canonical = json.dumps(arguments if arguments is not None else {}, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _call_assertion_public_key() -> Any:
    pem = os.getenv("MCP_CALL_ASSERTION_PUBLIC_KEY", "").strip()
    if not pem:
        return None
    if pem not in _CALL_ASSERTION_KEYS:
        try:
            key = _assertion_serialization.load_pem_public_key(pem.encode("utf-8"))
        except ValueError:
            key = None
        if not isinstance(key, _AssertionPublicKey):
            _ASSERTION_LOG.error("MCP_CALL_ASSERTION_PUBLIC_KEY is not an Ed25519 public key; every assertion is refused")
            key = None
        _CALL_ASSERTION_KEYS[pem] = key
    return _CALL_ASSERTION_KEYS[pem]


ASSERTION_CALLER_HEADER = "x-zuno-assertion-caller"


def _strip_assertion_caller(scope: Any) -> Any:
    """The scope without any client-sent X-Zuno-Assertion-Caller header."""
    headers = scope.get("headers") or []
    wanted = ASSERTION_CALLER_HEADER.encode("latin-1")
    if not any(k.lower() == wanted for k, _ in headers):
        return scope
    cleaned = dict(scope)
    cleaned["headers"] = [(k, v) for k, v in headers if k.lower() != wanted]
    return cleaned


def _with_assertion_caller(scope: Any, claims: Dict[str, Any]) -> Any:
    """The scope carrying the caller context of a VERIFIED assertion, if it has one."""
    ctx = claims.get("ctx")
    if not isinstance(ctx, dict):
        return scope
    payload = {
        "sub": claims.get("sub", ""),
        "tool": claims.get("tool", ""),
        "groups": ctx.get("groups", []),
        "email": ctx.get("email", ""),
        "email_verified": ctx.get("email_verified") is True,
        "username": ctx.get("username", ""),
    }
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii").rstrip("=")
    carried = dict(scope)
    carried["headers"] = list(scope.get("headers") or []) + [(ASSERTION_CALLER_HEADER.encode("latin-1"), raw.encode("ascii"))]
    return carried


def _assertion_caller(headers: Optional[Mapping[str, str]], tool: str) -> Optional[Dict[str, Any]]:
    """The caller of a call that arrived with a verified assertion carrying `ctx`, or None."""
    raw = (headers.get(ASSERTION_CALLER_HEADER) if headers else "") or ""
    if not raw:
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict) or payload.get("tool") != tool:
        return None
    groups = payload.get("groups")
    return {
        "sub": str(payload.get("sub") or ""),
        "groups": [str(g) for g in groups] if isinstance(groups, list) else [],
        "email": str(payload.get("email") or "").lower(),
        "email_verified": payload.get("email_verified") is True,
        "username": str(payload.get("username") or ""),
    }


def _call_assertion_type(token: str) -> str:
    try:
        return str(_assertion_jwt.get_unverified_header(token).get("typ") or "")
    except _assertion_jwt.PyJWTError:
        return ""


def _verify_call_assertion(token: str, key: Any, now: Optional[float] = None) -> Dict[str, Any]:
    if key is None:
        raise CallAssertionError("no call-assertion public key is configured")
    try:
        claims = _assertion_jwt.decode(
            token,
            key,
            algorithms=["EdDSA"],
            audience=CALLER_CONTEXT_AUDIENCE,
            issuer=CALL_ASSERTION_ISSUER,
            options={"require": ["exp", "iat", "aud", "iss", "sub", "jti"], "verify_exp": False, "verify_iat": False},
        )
    except _assertion_jwt.PyJWTError as exc:
        raise CallAssertionError(f"invalid call assertion: {exc}") from exc
    current = time.time() if now is None else now
    iat, exp = claims.get("iat"), claims.get("exp")
    if not isinstance(iat, int) or not isinstance(exp, int) or exp < iat or exp - iat > CALL_ASSERTION_MAX_TTL_SECONDS:
        raise CallAssertionError("call assertion lifetime is not within 60 seconds")
    if iat > current + CALL_ASSERTION_LEEWAY_SECONDS or current > exp + CALL_ASSERTION_LEEWAY_SECONDS:
        raise CallAssertionError("call assertion expired or not yet valid")
    act = claims.get("act")
    if not isinstance(act, dict) or act.get("sub") != CALL_ASSERTION_ISSUER:
        raise CallAssertionError("call assertion has no gateway actor")
    if not isinstance(claims.get("tool"), str) or not isinstance(claims.get("jti"), str):
        raise CallAssertionError("call assertion has no tool or jti")
    if "args" in claims and not isinstance(claims["args"], str):
        raise CallAssertionError("call assertion has a malformed args hash")
    ctx = claims.get("ctx")
    if ctx is not None and (
        not isinstance(ctx, dict)
        or not isinstance(ctx.get("groups", []), list)
        or not all(isinstance(g, str) for g in ctx.get("groups", []))
    ):
        raise CallAssertionError("call assertion has a malformed caller context")
    return claims


def _consume_call_assertion(jti: str, exp: int, now: Optional[float] = None) -> bool:
    """True the first time a jti is used for a tools/call; False on a replay."""
    current = time.time() if now is None else now
    for seen, until in list(_CALL_ASSERTION_SEEN.items()):
        if until < current:
            del _CALL_ASSERTION_SEEN[seen]
    if jti in _CALL_ASSERTION_SEEN:
        return False
    _CALL_ASSERTION_SEEN[jti] = exp + CALL_ASSERTION_LEEWAY_SECONDS
    return True


def _called_tools(body: bytes) -> Optional[List[Any]]:
    """The tools/call messages of a body: [(name, arguments)]; None when the body is not JSON."""
    if not body:
        return []
    try:
        message = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None
    messages = message if isinstance(message, list) else [message]
    calls = []
    for item in messages:
        if isinstance(item, dict) and item.get("method") == "tools/call":
            params = item.get("params") if isinstance(item.get("params"), dict) else {}
            calls.append((str(params.get("name") or ""), params.get("arguments")))
    return calls


class CallAssertionMiddleware:
    """Pure ASGI, so the body read for a tools/call is replayed to the MCP app intact."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        scope = _strip_assertion_caller(scope)
        key, required = _call_assertion_public_key(), _call_assertion_required()
        if not required and not os.getenv("MCP_CALL_ASSERTION_PUBLIC_KEY", "").strip():
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
        auth = headers.get("authorization", "")
        token = auth[7:].strip() if auth[:7].lower() == "bearer " else ""
        if not token or _call_assertion_type(token) != CALL_ASSERTION_TYPE:
            if required:
                await JSONResponse({"detail": "a gateway call assertion is required"}, status_code=401)(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return
        try:
            claims = _verify_call_assertion(token, key)
        except CallAssertionError as exc:
            _ASSERTION_LOG.warning("call assertion refused: %s", exc)
            await JSONResponse({"detail": str(exc)}, status_code=401)(scope, receive, send)
            return
        chunks, size, more, limit = [], 0, True, _call_assertion_max_body_bytes()
        while more:
            message = await receive()
            if message.get("type") != "http.request":
                break
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > limit:
                await JSONResponse({"detail": "request body too large"}, status_code=413)(scope, receive, send)
                return
            chunks.append(chunk)
            more = message.get("more_body", False)
        body = b"".join(chunks)
        called = _called_tools(body)
        if called is None:
            await JSONResponse({"detail": "the request body is not JSON"}, status_code=400)(scope, receive, send)
            return
        if called:
            names = [name for name, _ in called]
            if len(called) != 1 or names[0] != claims["tool"]:
                _ASSERTION_LOG.warning("call assertion for tool %r refused for tools/call %s", claims["tool"], names)
                await JSONResponse({"detail": "the call assertion was minted for another tool"}, status_code=403)(scope, receive, send)
                return
            if "args" in claims and claims["args"] != _call_assertion_args_hash(called[0][1]):
                _ASSERTION_LOG.warning("call assertion for tool %r refused: the arguments differ", claims["tool"])
                await JSONResponse({"detail": "the call assertion was minted for other arguments"}, status_code=403)(scope, receive, send)
                return
            if not _consume_call_assertion(claims["jti"], claims["exp"]):
                _ASSERTION_LOG.warning("call assertion replay refused (jti %s)", claims["jti"])
                await JSONResponse({"detail": "the call assertion was already used"}, status_code=403)(scope, receive, send)
                return
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(_with_assertion_caller(scope, claims), replay, send)


# END call-assertion verifier (WP-225 lot C)
# --------------------------------------------------------------------------


mcp_asgi_app: ASGIApp = mcp_server.streamable_http_app(
    streamable_http_path="/mcp",
    transport_security=TransportSecuritySettings(
        allowed_hosts=os.getenv(
            "MCP_ALLOWED_HOSTS",
            "confluence-mcp.zuno-ai-run.svc:8000,"
            "confluence-mcp.zuno-ai-run.svc.cluster.local:8000,"
            "confluence-mcp:8000,localhost:8000,127.0.0.1:8000",
        ).split(","),
    ),
)
mcp_asgi_app.add_middleware(CallAssertionMiddleware)
app.mount("/", mcp_asgi_app)
