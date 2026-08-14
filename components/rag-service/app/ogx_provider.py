"""ADR-0322 OGX-backed RAG provider prototype (v0.1 integration scope).

Zuno's stable retrieval contract is app/search.py's hybrid_search():
(query, top_k, product, version, language, caller_groups) in,
{"results": [...], "vector_search_used": bool} out - app/main.py's
POST /v1/search returns that shape as SearchResponse regardless of which
provider served the request. This module implements the same contract
against the Red Hat OpenShift AI OGX Operator's data-plane API instead of
the local pgvector+full-text hybrid search in search.py.

OGX's own documented positioning is "OpenAI-compatible APIs and
vector-store integrations" (ADR-0322 Context), so this adapter targets the
OpenAI Vector Stores search convention
(`POST /v1/vector_stores/{vector_store_id}/search`). VERIFIED live,
2026-08-14: `spec.components.ogx.managementState: Managed` on this
cluster's zuno-dsc only installs the OGX Operator/controller (`oc get svc
-n redhat-ods-applications` shows only
ogx-k8s-operator-controller-manager-metrics-service/-webhook-service, no
API-serving Service) - a separate namespaced `OGXServer` CR
(`ogxservers.ogx.io/v1beta1`, confirmed via `oc explain ogxserver.spec`)
is what stands up the actual data-plane API, and none exists on this
cluster yet (`oc get ogxserver -A` returns no resources). See
gitops/charts/openshift-ai/templates/ogxserver.yaml (disabled by default)
for the CR that would create one. This adapter has therefore never been
exercised against a live OGX endpoint - its HTTP request/response mapping
follows the documented OpenAI Vector Stores API shape, not a verified OGX
wire capture; treat it as a prototype pending a live OGXServer to test
against (ADR-0322 v0.1 scope explicitly calls for a prototype-then-parity-
test step, not a finished integration).

Same additive/opt-in shape as components/ai-gateway/app/maas_adapter.py:
- **additive**: app/search.py and the default /v1/search behavior are
  completely unchanged unless a deployment opts in;
- **globally gated**: RAG_PROVIDER must be explicitly set to "ogx" (chart
  value `ogxProvider.enabled`, default false, renders no such env var) -
  the existing pgvector+full-text provider stays the default, per
  ADR-0322's "preserve the current custom RAG provider... during
  migration";
- **never silently promoted to default**: ADR-0322's acceptance criteria
  require provider-parity tests (tests/test_provider_parity.py) before any
  task switches from the custom provider to OGX by default - this module
  does not decide that switch, callers do.

Filtering strategy (product/version/ACL, ADR-0046/ADR-0322 Security
considerations - "any OGX-backed retrieval path must preserve source ACL
and group filters, data classification"): OGX's vector-store search API
almost certainly supports server-side metadata filter pushdown, but its
exact filter-grammar wire format is not verified against a live endpoint
(no OGXServer exists to confirm it against - see module docstring above).
Rather than encode an unverified query DSL that could silently fail open,
this adapter over-fetches unfiltered results and applies the identical
product/version-exact-match and fail-closed ACL-group-intersection checks
app/search.py's `_filter_clause` enforces in SQL, in Python, on the
`attributes` OGX returns per result. This is strictly conservative: even
if OGX also applies (or ignores) its own filters server-side, this
adapter's own check is the one ACL enforcement actually depends on -
defense in depth, the same posture ADR-0322 requires of OGX's own
OAuth/ABAC relative to Zuno's authorization boundary.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from app.search import _is_stale

logger = logging.getLogger("rag_service.ogx_provider")

RAG_PROVIDER = os.getenv("RAG_PROVIDER", "pgvector").strip().lower()
OGX_BASE_URL = os.getenv("OGX_BASE_URL", "")
OGX_VECTOR_STORE_ID = os.getenv("OGX_VECTOR_STORE_ID", "")
# Names the environment variable the OGX API token is read from (populated
# by an ExternalSecret - never a literal value here, ADR-0024), same
# indirection convention as ai-gateway's MAAS_GATEWAY_API_KEY_ENV.
OGX_API_TOKEN_ENV = os.getenv("OGX_API_TOKEN_ENV", "OGX_API_TOKEN")
OGX_TIMEOUT_SECONDS = float(os.getenv("OGX_TIMEOUT_SECONDS", "10"))

# Over-fetch factor before client-side product/version/ACL filtering -
# mirrors app/search.py's hybrid_search `fetch_n = max(top_k * 4, 20)`.
_OVERFETCH_FACTOR = 4
_OVERFETCH_MIN = 20


class OgxProviderError(Exception):
    pass


def enabled() -> bool:
    return RAG_PROVIDER == "ogx"


def should_use_ogx() -> bool:
    """True only when the deployment opted in (RAG_PROVIDER=ogx). Unlike
    maas_adapter.should_use_maas's two-key gate (a global switch plus a
    per-provider config opt-in), rag-service has no per-model/per-provider
    dimension to gate on a second axis - provider choice here is a
    deployment-time decision, not a per-request one, so one key is enough.
    """
    return enabled()


def _passes_filters(
    attributes: Dict[str, Any],
    product: Optional[str],
    version: Optional[str],
    caller_groups: List[str],
    domains: Optional[List[str]] = None,
    technology: Optional[str] = None,
) -> bool:
    """The exact semantics of app/search.py:_filter_clause, applied to a
    plain dict instead of a SQL WHERE clause - see that function's
    docstring for the ACL fail-closed rationale and the ADR-0202/ADR-0203
    domain/technology additions.
    """
    if product and attributes.get("product") != product:
        return False
    if version and attributes.get("version") != version:
        return False
    if technology and attributes.get("technology") != technology:
        return False
    if domains:
        doc_domain = attributes.get("domain", "knowledge.tech")
        if doc_domain not in domains:
            return False

    acl_groups = attributes.get("acl_groups")
    if acl_groups:
        if not caller_groups or not (set(acl_groups) & set(caller_groups)):
            return False
    return True


def _row_to_result(row: Dict[str, Any]) -> Dict[str, Any]:
    """Maps one OpenAI Vector Store search result item
    (`{"file_id", "score", "content": [{"text": ...}], "attributes": {...}}`)
    to the exact app/schemas.py:SearchResult shape app/search.py's
    _row_to_doc already produces, so main.py can return either provider's
    output through the same SearchResponse model unchanged. `attributes`
    is expected to carry the same metadata keys ADR-0046 already writes
    into document_embeddings.metadata (classification/language/product/
    version/stale/acl_groups) - a parity proof requires both providers to
    expose the same caller-facing fields, not just the same ranking, and
    populating an OGX-indexed corpus with those attributes is this WP's
    documented residual operator action (see the WP-06 brief), not
    something this adapter performs.
    """
    attributes = row.get("attributes") or {}
    content_parts = row.get("content") or []
    text = " ".join(part.get("text", "") for part in content_parts if isinstance(part, dict))
    return {
        "id": str(row.get("file_id", "")),
        "source": attributes.get("source", ""),
        "title": attributes.get("title", ""),
        "snippet": text[:400],
        "score": float(row.get("score", 0.0)),
        # ADR-0046: untagged rows default to C1, same baseline as
        # app/search.py:_row_to_doc - never invent a higher classification.
        "classification": attributes.get("classification", "C1"),
        "language": attributes.get("language"),
        "product": attributes.get("product"),
        "version": attributes.get("version"),
        "stale": _is_stale(attributes),
        # ADR-0202: same untagged-row default as app/search.py:_row_to_doc.
        "domain": attributes.get("domain", "knowledge.tech"),
        "_attributes": attributes,  # internal only, stripped before return
    }


async def ogx_search(
    query: str,
    top_k: int,
    product: Optional[str] = None,
    version: Optional[str] = None,
    language: Optional[str] = None,
    caller_groups: Optional[List[str]] = None,
    domains: Optional[List[str]] = None,
    technology: Optional[str] = None,
) -> Dict[str, Any]:
    """Same signature/return shape as app/search.py:hybrid_search - see
    that function's docstring and this module's docstring for the contract
    and the filtering strategy this mirrors. `language` is intentionally
    not sent to OGX and not used to re-rank here either: app/search.py
    treats it as a soft boost applied after RRF fusion, a Zuno-side ranking
    adjustment with no equivalent in a single ranked list from a single
    provider - out of scope for a parity prototype whose acceptance bar is
    metadata/ACL/classification/citation parity, not ranking-algorithm
    parity (ADR-0322 acceptance criteria).
    """
    if not OGX_BASE_URL or not OGX_VECTOR_STORE_ID:
        raise OgxProviderError(
            "RAG_PROVIDER=ogx but OGX_BASE_URL/OGX_VECTOR_STORE_ID is not set - "
            "the OGX provider has nothing to point at"
        )

    caller_groups = caller_groups or []
    top_k = max(1, top_k)
    fetch_n = max(top_k * _OVERFETCH_FACTOR, _OVERFETCH_MIN)

    headers = {}
    token = os.getenv(OGX_API_TOKEN_ENV, "")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    payload: Dict[str, Any] = {"query": query, "max_num_results": fetch_n}
    url = f"{OGX_BASE_URL.rstrip('/')}/v1/vector_stores/{OGX_VECTOR_STORE_ID}/search"

    try:
        async with httpx.AsyncClient(timeout=OGX_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        body = resp.json()
    except Exception as exc:
        raise OgxProviderError(f"OGX vector-store search failed: {exc}") from exc

    rows = body.get("data", [])
    filtered = []
    for row in rows:
        doc = _row_to_result(row)
        if not _passes_filters(doc.pop("_attributes"), product, version, caller_groups, domains, technology):
            continue
        filtered.append(doc)
        if len(filtered) >= top_k:
            break

    return {"results": filtered, "vector_search_used": True}
