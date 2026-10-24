"""ADR-0114 MaaS adapter prototype.

Zuno keeps every business/context decision it already makes - C1/C2/C3
eligibility, sovereignty, `X-Zuno-Local-Only` (ADR-0035) - entirely in
app/routing.py, unchanged. This module changes nothing about *whether* a
request is allowed to reach a candidate; it only changes *how* an
already-eligible candidate is reached, for providers that opt in.

Today every candidate is invoked directly: the "local" candidate hits its
KServe/vLLM predictor Service, each SaaS candidate hits its vendor API.
This module adds a second transport - the same OpenAI-compatible
`ChatOpenAI` client app/providers.py already uses for every candidate,
pointed at OpenShift AI MaaS's own OpenAI-compatible model-access endpoint
instead. It is:

- **additive**: no existing provider's behavior changes unless it opts in;
- **opt-in per provider**: a provider-routing.yaml entry must set
  `via_maas: true` (see platform/ai-gateway/provider-routing.yaml's schema
  comment - no shipped entry sets it yet, so out of the box nothing routes
  through it);
- **globally gated**: even an opted-in provider only actually uses this
  path when `MAAS_ADAPTER_ENABLED=true` (chart value
  `maasAdapter.enabled`, default `false`) - the operational "prototype
  ... before removing current gateway capabilities" step ADR-0114 requires.

See docs/roadmap/evidence/adr-0114-maas-coverage.md for the feature
comparison this prototype exists to inform.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote

from langchain_core.language_models.chat_models import BaseChatModel

MAAS_ADAPTER_ENABLED = os.getenv("MAAS_ADAPTER_ENABLED", "false").strip().lower() == "true"
MAAS_GATEWAY_ENDPOINT = os.getenv("MAAS_GATEWAY_ENDPOINT", "")
# Names the environment variable the MaaS API key is read from (populated
# by an ExternalSecret, same convention as every provider's *_API_KEY_ENV
# in provider-routing.yaml - never a literal value here, ADR-0024).
# ADR-0521 (WP-076) step 3: kept as the documented fallback - MaaS's own
# API-key issuance flow was never discovered live (only
# /internal/v1/api-keys/validate has been observed working), so this stays
# wired for the day it is, but is no longer the primary path (see
# MAAS_SA_TOKEN_PATH below).
MAAS_GATEWAY_API_KEY_ENV = os.getenv("MAAS_GATEWAY_API_KEY_ENV", "MAAS_GATEWAY_API_KEY")
# ADR-0521 (WP-076) step 3: this pod's own audience-scoped ServiceAccount
# token (gitops/charts/ai-gateway's deployment.yaml - a purpose-built
# projected volume, not the pod's default SA mount, which stays off per
# ADR-0052's hardening). Authenticates as
# system:serviceaccount:zuno-ai-run:ai-gateway via maas-gateway-auth's
# kubernetesTokenReview rule (live-confirmed audience:
# https://kubernetes.default.svc, `oc get authpolicy maas-gateway-auth -n
# openshift-ingress`) - no external issuance flow needed for ai-gateway's
# own local-model traffic. gitops/charts/models's maas.yaml grants this
# identity a MaaSSubscription/MaaSAuthPolicy entry per model
# (owner.users/subjects.users, not a persona group).
MAAS_SA_TOKEN_PATH = os.getenv("MAAS_SA_TOKEN_PATH", "")

# ADR-0201 (WP-27): a THIRD gate, on top of the two above, specific to
# candidates that leave the cluster (candidate.kind != "local") - external-
# model egress through MaaS is a distinct lifecycle/policy decision from
# "route the local model's own traffic through MaaS" (which never leaves
# the cluster network, no egress concern). Default off: enabling
# MAAS_ADAPTER_ENABLED alone must never open external egress by itself.
MAAS_EXTERNAL_EGRESS_ENABLED = os.getenv("MAAS_EXTERNAL_EGRESS_ENABLED", "false").strip().lower() == "true"


class MaasAdapterError(RuntimeError):
    pass


def enabled() -> bool:
    return MAAS_ADAPTER_ENABLED


def _env_flag(name: str) -> bool:
    # Read per call (not at import like the switches above), so a test can
    # flip it with mock.patch.dict(os.environ) and nothing is cached.
    return os.getenv(name, "false").strip().lower() == "true"


# ---------------------------------------------------------------------------
# WP-157 decision D5 (ADR-0570 amendment of 2026-10-24): the gateway's own
# identity towards MaaS. Off by default (chart value
# maasAdapter.gatewayIdentity.enabled renders MAAS_GATEWAY_IDENTITY=true).
#
# Off: today's behaviour - the caller's Keycloak token is forwarded
# (_maas_bearer_token below) and no quota context leaves the gateway.
# On: the pod's ServiceAccount token authenticates every MaaS call, and the
# gateway attaches what it has itself validated (app/auth.py) or been told
# by its platform caller, as the headers below. MaaS trusts them only
# because only this pod holds that token: the generated TokenRateLimitPolicy
# (gitops/charts/connectivity-link/templates/quota-tokenratelimitpolicies.yaml)
# applies its limits only when the authenticated identity is this
# ServiceAccount, and counts on these headers.
#
# THE ONE PLACE these names are defined. platform/okf/generate_quota_enforcement.py
# repeats them (lower-cased, ATTESTED_HEADERS) for the policy it generates;
# tests/test_maas_gateway_identity.py fails if the two sets drift.
ATTESTED_HEADERS: Dict[str, str] = {
    # The caller's validated JWT `sub` (CallerIdentity.sub).
    "user": "X-Zuno-User-Sub",
    # The caller's groups claim, sorted and joined with "|", "(none)" when
    # empty - the same key app/quota.py's group dimension uses, so the
    # Kuadrant counter has the ledger's granularity.
    "groups": "X-Zuno-Groups",
    # The quota class the request runs under (X-Zuno-Quota-Class from the
    # platform caller, default `standard`).
    "quota_class": "X-Zuno-Quota-Class",
    # The verified zuno project id (ADR-0528), only when the request has one.
    "project": "X-Zuno-Project-Id",
}
# Characters kept as-is in an attested value; anything else (a non-ASCII
# group name, a header-breaking control character) is percent-encoded, which
# keeps the value a valid HTTP header and the counter key stable.
_HEADER_SAFE = "/|()-_.:@+= "


def gateway_identity_enabled() -> bool:
    return _env_flag("MAAS_GATEWAY_IDENTITY")


@dataclass(frozen=True)
class MaasCallContext:
    """What the gateway attests to MaaS about one request (D5)."""

    sub: str
    groups: Tuple[str, ...] = ()
    quota_class: str = "standard"
    project_id: Optional[str] = None


def groups_key(groups) -> str:
    return "|".join(sorted(groups or ())) or "(none)"


def attested_headers(context: MaasCallContext) -> Dict[str, str]:
    headers = {
        ATTESTED_HEADERS["user"]: context.sub,
        ATTESTED_HEADERS["groups"]: groups_key(context.groups),
        ATTESTED_HEADERS["quota_class"]: context.quota_class or "standard",
    }
    if context.project_id:
        headers[ATTESTED_HEADERS["project"]] = context.project_id
    return {name: quote(str(value), safe=_HEADER_SAFE) for name, value in headers.items()}


def _service_account_token() -> str:
    if MAAS_SA_TOKEN_PATH and os.path.exists(MAAS_SA_TOKEN_PATH):
        with open(MAAS_SA_TOKEN_PATH, "r", encoding="utf-8") as fh:
            token = fh.read().strip()
        if token:
            return token
    raise MaasAdapterError(
        "MAAS_GATEWAY_IDENTITY is on but no ServiceAccount token is readable at "
        f"MAAS_SA_TOKEN_PATH={MAAS_SA_TOKEN_PATH!r} - refusing to fall back to "
        "the caller's token, which would carry no attested quota context"
    )


# ---------------------------------------------------------------------------
# WP-157 step 4 (inventory finding 4): a MaaS 429 is a quota denial, not an
# outage. Off by default (maasAdapter.quota429Passthrough.enabled renders
# MAAS_QUOTA_429_PASSTHROUGH=true): today a 429 from MaaS falls through to the
# direct sibling and then to SaaS like any provider error.
def quota_429_passthrough_enabled() -> bool:
    return _env_flag("MAAS_QUOTA_429_PASSTHROUGH")


class MaasQuotaExceeded(Exception):
    """A via_maas candidate answered 429. Carries what app/main.py needs to
    return the gateway's own 429 contract (WP-148: status 429, Retry-After,
    `quota_exceeded` body) instead of trying the next candidate."""

    def __init__(self, provider: str, retry_after: Optional[int] = None, upstream_message: str = ""):
        super().__init__(f"MaaS quota exceeded on {provider}")
        self.provider = provider
        self.retry_after = retry_after
        self.upstream_message = upstream_message

    def detail(self, quota_class: str) -> Dict[str, Any]:
        # Same keys as app/quota.py's QuotaDenial.detail() where MaaS gives
        # an equivalent; MaaS's own 429 does not name the dimension or the
        # budget (to capture live, inventory V12), so neither is invented.
        return {
            "error": "quota_exceeded",
            "quota_class": quota_class,
            "dimension": "maas",
            "provider": self.provider,
        }


def _status_and_headers(exc: BaseException):
    status = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if status is None and response is not None:
        status = getattr(response, "status_code", None)
    headers = getattr(response, "headers", None) or {}
    return status, headers


def quota_exceeded_from(exc: BaseException, provider: str) -> Optional[MaasQuotaExceeded]:
    """A MaasQuotaExceeded when `exc` is an HTTP 429 (the openai SDK's
    RateLimitError, or anything carrying status_code 429), else None."""
    status, headers = _status_and_headers(exc)
    if status != 429:
        return None
    retry_after: Optional[int] = None
    raw = headers.get("retry-after") if hasattr(headers, "get") else None
    if raw is not None:
        try:
            retry_after = max(1, int(float(str(raw).strip())))
        except ValueError:
            retry_after = None  # an HTTP-date form; not forwarded
    return MaasQuotaExceeded(provider, retry_after, str(exc)[:200])


def _maas_bearer_token(caller_bearer_token: Optional[str] = None) -> str:
    """2026-09-01 (identity-per-caller): prefers the real caller's own
    Keycloak bearer token (the one this gateway already validated for its
    own AuthN - app/auth.py's CallerIdentity.token) over the pod's fixed
    ServiceAccount/API-key identity, so the MaaS Gateway's Authorino
    AuthConfig (once ModelsAsService.spec.externalOIDC is set -
    gitops/charts/models/templates/maas.yaml) resolves the REAL user's
    sub/groups instead of always landing in the single shared "ai-gateway"
    MaaSSubscription. Every real Zuno request has a caller identity by the
    time chat_model_for() runs (app/main.py's `identity` dependency is
    required, never optional) - the None branch here only covers a
    standalone/test caller of this module that never threads one through.

    Falls back to the SA-token/API-key path below only when no caller
    token was passed in at all - this does NOT retry with the SA token if
    the MaaS Gateway itself rejects the forwarded caller token at request
    time (e.g. the still-open clientId/audience question, see
    templates/maas.yaml's comment); that would surface as a normal
    provider failure and this candidate's own existing fallback-to-next-
    provider handling (app/main.py) takes over, same as any other
    transient provider error.

    WP-157 D5: with MAAS_GATEWAY_IDENTITY on, the pod's ServiceAccount token
    always wins and the caller's token is never sent to MaaS.
    """
    if gateway_identity_enabled():
        return _service_account_token()
    if caller_bearer_token:
        return caller_bearer_token
    if MAAS_SA_TOKEN_PATH and os.path.exists(MAAS_SA_TOKEN_PATH):
        with open(MAAS_SA_TOKEN_PATH, "r", encoding="utf-8") as fh:
            token = fh.read().strip()
        if token:
            return token
    return os.getenv(MAAS_GATEWAY_API_KEY_ENV, "not-required")


def should_use_maas(cfg: Dict[str, Any], candidate_kind: str = "local") -> bool:
    """True only when the global switch is on AND this specific provider's
    config opted in - the two-key gate that keeps this default-off and
    additive. For a non-local candidate (an external SaaS provider routed
    through MaaS, `candidate_kind != "local"`), a THIRD gate applies:
    MAAS_EXTERNAL_EGRESS_ENABLED must also be on (ADR-0201's "external-
    model egress, if enabled, is explicitly marked optional"). This never
    changes WHETHER a candidate was eligible in the first place -
    app/routing.py's classification/local-only filtering already ran
    before chat_model_for() (and this function) are ever consulted; this
    only gates the TRANSPORT for an already-eligible external candidate.
    """
    if not MAAS_ADAPTER_ENABLED or not cfg.get("via_maas", False):
        return False
    if candidate_kind != "local" and not MAAS_EXTERNAL_EGRESS_ENABLED:
        return False
    return True


def chat_model_via_maas(
    cfg: Dict[str, Any],
    request_id: Optional[str] = None,
    caller_bearer_token: Optional[str] = None,
    max_tokens: Optional[int] = None,
    context: Optional[MaasCallContext] = None,
) -> BaseChatModel:
    """The exact same `ChatOpenAI` class every direct candidate in
    app/providers.py already uses, pointed at the MaaS gateway's
    OpenAI-compatible endpoint. `maas_model_ref` lets a provider-routing.yaml
    entry override the model identifier MaaS publishes it under, when that
    differs from the serving runtime's own internal model name
    (ADR-0114/ADR-0201 - MaaS model publication naming is not guaranteed to
    match `model`).

    ADR-0201 (WP-27) usage correlation: `request_id`, when the caller has
    one (app/main.py forwards the same X-Zuno-Request-Id
    app/telemetry.py:model_call_span stamps on this call's own span), rides
    along as a request header to MaaS itself - so MaaS-side usage/token
    metrics can be joined to this same Zuno request trace, not just
    ai-gateway's own span.

    ADR-0521 (WP-076) step 4: `cfg.get("endpoint")` takes priority over the
    module-level MAAS_GATEWAY_ENDPOINT default. Live-verified against the
    real cluster (2026-08-26): the only proven-working MaaS route for a
    local model is the PATH-PREFIXED form -
    "<maas-gateway>/<namespace>/<model>/v1" (KServe's auto-generated
    HTTPRoute, `ipp-pre`'s ext_proc filter copies the request body's
    `model` field into the X-Gateway-Model-Name header the AuthPolicy's
    OPA rules key on) - which is necessarily per-model, not a single
    shared endpoint every via_maas provider could point at. The header-
    gated form documented in earlier ADR-0201 notes 403s on authorization
    even though it routes correctly - see gitops/charts/models/values.yaml
    maas.models[].endpointOverride's comment for the full identity-
    mismatch history this sidesteps.
    """
    endpoint = cfg.get("endpoint") or MAAS_GATEWAY_ENDPOINT
    if not endpoint:
        raise MaasAdapterError(
            "MAAS_ADAPTER_ENABLED is true but neither this provider's own "
            "endpoint nor MAAS_GATEWAY_ENDPOINT is set - the MaaS adapter "
            "has nothing to point at"
        )

    from langchain_openai import ChatOpenAI

    default_headers = {"X-Zuno-Request-Id": request_id} if request_id else None
    # WP-157 D5: attested quota context, only with the gateway's own identity
    # (a forwarded caller token must never carry headers MaaS would trust).
    if gateway_identity_enabled():
        if context is None:
            raise MaasAdapterError(
                "MAAS_GATEWAY_IDENTITY is on but no request context reached the "
                "MaaS adapter - refusing an unattested call"
            )
        default_headers = {**(default_headers or {}), **attested_headers(context)}
    extra: Dict[str, Any] = {}
    if quota_429_passthrough_enabled():
        # A 429 is answered to the caller at once (app/main.py), so the SDK
        # must not retry it first; this also drops the SDK's retries of
        # 5xx/connection errors on MaaS calls, which the candidate loop's own
        # fallback already covers.
        extra["max_retries"] = 0

    # ADR-0521 (WP-076) step 4, live incident 2026-08-26: maas-default-
    # gateway's TLS cert is issued by the same cluster
    # openshift-service-serving-signer CA every local LLMInferenceService
    # endpoint already uses (confirmed live: `oc get secret
    # maas-gateway-service-tls -n openshift-ingress` and
    # gpt-oss-20b-kserve-workload-svc's cert share the same issuer) - not
    # in this pod's default trust store, so without this the openai SDK's
    # own httpx client fails TLS verification and every via_maas call
    # surfaces as a generic "Connection error" (silently falling back to
    # the direct candidate rather than actually reaching MaaS). Same
    # LOCAL_GPT_OSS_CA_BUNDLE env var/mounted file app/providers.py's
    # local branch already trusts - despite the name, it's the cluster
    # CA, not something gpt-oss-specific.
    http_async_client = None
    ca_bundle = os.getenv("LOCAL_GPT_OSS_CA_BUNDLE")
    if ca_bundle:
        import httpx

        http_async_client = httpx.AsyncClient(verify=ca_bundle)

    from app.reasoning import with_reasoning

    return with_reasoning(ChatOpenAI)(
        base_url=endpoint,
        api_key=_maas_bearer_token(caller_bearer_token),
        model=cfg.get("maas_model_ref", cfg.get("model")),
        temperature=cfg.get("temperature", 0.2),
        timeout=cfg.get("timeout_seconds", 60),
        default_headers=default_headers,
        http_async_client=http_async_client,
        # Same reasoning as app/providers.py's local/openai branches - keeps
        # this dormant adapter from becoming a landmine once it's wired up.
        stream_usage=True,
        # ADR-0544: forwarded, not optional - structure-demo's own
        # preferred candidate (local-maas) is via_maas: true, so this is
        # the branch its declared max_tokens actually reaches.
        max_tokens=max_tokens,
        **extra,
    )
