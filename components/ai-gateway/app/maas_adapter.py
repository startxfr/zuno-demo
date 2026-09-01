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
from typing import Any, Dict, Optional

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
    """
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

    return ChatOpenAI(
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
    )
