"""ADR-0602 clause 10 / ADR-0603 M14 (WP-225 lot C): the per-call assertion.

Until lot C the gateway forwarded the caller's own Keycloak bearer to every
streamable-HTTP backend. None of them uses it (each acts with its own technical
credential, after the gateway's ADR-0011 decision), so the user's token was only
exposure: a backend, or anything that reads its traffic, could replay it against
every other service that accepts the `zuno-admin-api` audience.

With `MCP_OUTBOUND_IDENTITY=assertion` the gateway sends, instead of that bearer,
a short-lived JWT it signs itself, one per tool call:

    Authorization: Bearer <compact JWS, EdDSA (Ed25519), typ zuno-call+jwt>

    {"iss": "mcp-gateway", "aud": "<the binding's backend>", "sub": "<caller sub>",
     "act": {"sub": "mcp-gateway"}, "tool": "<the backend's own tool name>",
     "args": "<sha256 of the canonical JSON of the tool arguments>",
     "iat": ..., "exp": <iat + at most 60 s>, "jti": "<uuid>"}

Only the gateway holds the private key (MCP_CALL_ASSERTION_KEY_FILE); each Zuno
server holds the public key and verifies it (`CallAssertionMiddleware`, the same
block in confluence, git-forge, salesforce and aap). Unlike the workload token and
the lot B caller context, a backend cannot mint one. A backend refuses an
assertion that is forged, expired, longer-lived than 60 s, addressed to another
backend, minted for another tool or other arguments, or replayed (its `jti` is consumed by the one
`tools/call` it was minted for).

Per binding (platform/bindings/tools/tool-bindings.yaml), in assertion mode:
- `user_token: true`: the backend needs the caller's own token (a
  provider-delegated backend); the bearer is forwarded, as before;
- `gateway_token: true` (a Zuno server): the assertion;
- otherwise (a third-party backend, kubernetes-mcp-server): no Authorization at all.

`MCP_OUTBOUND_IDENTITY=bearer` (the default) keeps today's forwarding. In
assertion mode a missing or unreadable key fails the call (502): the gateway never
falls back to the user's bearer.

WP-247 (Vault Transit): with `MCP_CALL_ASSERTION_SIGNER=transit` the private key is
not in the pod at all. The gateway builds the same compact JWS and asks Vault
(`transit/sign/<key>`, an ed25519 key that cannot be exported) to sign the
`header.payload` bytes, authenticating with its own ServiceAccount token
(`auth/kubernetes/login`, a role bound to the gateway ServiceAccount only). A Vault
that cannot be reached, refuses the login or answers something that is not a
signature fails the call exactly like an unreadable key: the caller gets the 502 of
`AssertionUnavailable`, never a fallback to the bearer or to a local key. The default
(`file`) is unchanged.

RFC 8693 token exchange was the other option of clause 10. It was not chosen:
it needs a Keycloak round trip per tool call, one client (or audience) per
backend in a realm whose import is create-only, and Keycloak JWKS reachability
and CA trust in every backend; the assertion needs none of these and is verified
offline.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import ssl
import threading
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, Optional, Tuple

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

logger = logging.getLogger("mcp_gateway.call_assertion")

TYPE = "zuno-call+jwt"
ISSUER = "mcp-gateway"
ALGORITHM = "EdDSA"
MAX_TTL_SECONDS = 60
# The `sub` of an assertion the gateway mints for itself (a tools/list schema read),
# never a caller: it carries no `tool`, so no tools/call verifies with it.
SELF_SUBJECT = "system:mcp-gateway"

MODES = ("bearer", "assertion")
SIGNERS = ("file", "transit")

_SA_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
# Seconds before a Vault client token expires at which it is renewed by logging in again.
_TOKEN_MARGIN_SECONDS = 30
_VAULT_TIMEOUT_SECONDS = 2.0

_KEY_CACHE: Dict[str, Tuple[float, Ed25519PrivateKey]] = {}


class AssertionUnavailable(RuntimeError):
    """Assertion mode is on but the signing key cannot be used."""


def mode() -> str:
    """MCP_OUTBOUND_IDENTITY, read per call: `bearer` (default) or `assertion`."""
    raw = (os.getenv("MCP_OUTBOUND_IDENTITY") or "bearer").strip().lower()
    if raw not in MODES:
        logger.error("MCP_OUTBOUND_IDENTITY=%r is not one of %s; using bearer", raw, MODES)
        return "bearer"
    return raw


def ttl_seconds() -> int:
    raw = (os.getenv("MCP_CALL_ASSERTION_TTL_SECONDS") or "").strip()
    try:
        value = int(raw) if raw else MAX_TTL_SECONDS
    except ValueError:
        value = MAX_TTL_SECONDS
    return max(5, min(value, MAX_TTL_SECONDS))


def signer() -> str:
    """Where the signature comes from: `file` (the key mounted in the pod, the
    default) or `transit` (Vault signs, WP-247). An unknown value fails closed."""
    raw = (os.getenv("MCP_CALL_ASSERTION_SIGNER") or "file").strip().lower()
    if raw not in SIGNERS:
        raise AssertionUnavailable(f"MCP_CALL_ASSERTION_SIGNER must be one of {SIGNERS}, not {raw!r}")
    return raw


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


class _VaultTransit:
    """The two Vault calls the gateway needs: a Kubernetes login, then `transit/sign`.
    Standard library only (no new dependency in the pinned image); every call has a
    short timeout, so a dead Vault costs one bounded wait, not a hung gateway."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._token = ""
        self._expires = 0.0

    @staticmethod
    def _config() -> Dict[str, str]:
        cfg = {
            "addr": (os.getenv("VAULT_ADDR") or "").strip().rstrip("/"),
            "role": (os.getenv("VAULT_AUTH_ROLE") or "").strip(),
            "key": (os.getenv("VAULT_TRANSIT_KEY") or "").strip(),
            "mount": (os.getenv("VAULT_TRANSIT_MOUNT") or "transit").strip().strip("/"),
            "auth_mount": (os.getenv("VAULT_AUTH_MOUNT") or "kubernetes").strip().strip("/"),
            "ca": (os.getenv("VAULT_CACERT") or "").strip(),
            "sa_token": (os.getenv("VAULT_SA_TOKEN_FILE") or _SA_TOKEN_PATH).strip(),
        }
        missing = [name for name in ("addr", "role", "key") if not cfg[name]]
        if missing:
            raise AssertionUnavailable(
                "transit signing needs VAULT_ADDR, VAULT_AUTH_ROLE and VAULT_TRANSIT_KEY (missing: "
                + ", ".join(missing) + ")"
            )
        return cfg

    @staticmethod
    def _post(cfg: Dict[str, str], path: str, body: Dict[str, Any], token: str = "") -> Dict[str, Any]:
        request = urllib.request.Request(
            f"{cfg['addr']}/v1/{path}",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", **({"X-Vault-Token": token} if token else {})},
            method="POST",
        )
        context = None
        if cfg["addr"].startswith("https://"):
            context = ssl.create_default_context(cafile=cfg["ca"] or None)
        with urllib.request.urlopen(request, timeout=_VAULT_TIMEOUT_SECONDS, context=context) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))

    def _login(self, cfg: Dict[str, str]) -> None:
        try:
            with open(cfg["sa_token"], "r", encoding="utf-8") as handle:
                jwt_value = handle.read().strip()
        except OSError as exc:
            raise AssertionUnavailable(f"the ServiceAccount token {cfg['sa_token']} is unreadable: {exc}") from exc
        answer = self._post(cfg, f"auth/{cfg['auth_mount']}/login", {"role": cfg["role"], "jwt": jwt_value})
        auth = answer.get("auth") or {}
        token = auth.get("client_token")
        if not token:
            raise AssertionUnavailable("Vault answered the login without a client token")
        self._token = str(token)
        self._expires = time.time() + float(auth.get("lease_duration") or 0) - _TOKEN_MARGIN_SECONDS

    def sign(self, data: bytes) -> bytes:
        cfg = self._config()
        payload = {"input": base64.b64encode(data).decode("ascii")}
        path = f"{cfg['mount']}/sign/{cfg['key']}"
        try:
            for attempt in (1, 2):
                with self._lock:
                    if not self._token or time.time() >= self._expires:
                        self._login(cfg)
                    token = self._token
                try:
                    answer = self._post(cfg, path, payload, token)
                    break
                except urllib.error.HTTPError as exc:
                    if exc.code == 403 and attempt == 1:  # the token was revoked or expired early: log in once more
                        with self._lock:
                            self._token = ""
                        continue
                    raise
        except AssertionUnavailable:
            raise
        except (OSError, ValueError) as exc:  # URLError, HTTPError, timeouts, bad JSON
            with self._lock:
                self._token = ""
            raise AssertionUnavailable(f"Vault transit signing is unavailable: {exc}") from exc
        signature = str((answer.get("data") or {}).get("signature") or "")
        prefix, _, encoded = signature.rpartition(":")
        try:
            raw = base64.b64decode(encoded, validate=True) if prefix.startswith("vault:v") else b""
        except ValueError:
            raw = b""
        if len(raw) != 64:  # an ed25519 signature is exactly 64 bytes
            raise AssertionUnavailable("Vault returned something that is not an ed25519 signature")
        return raw


_TRANSIT = _VaultTransit()


def _transit_encode(claims: Dict[str, Any]) -> str:
    """The compact JWS of `claims`, signed by Vault: same header as PyJWT would write."""
    header = {"typ": TYPE, "alg": ALGORITHM}
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8")) + "."
        + _b64url(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    )
    return signing_input + "." + _b64url(_TRANSIT.sign(signing_input.encode("ascii")))


def signing_key() -> Ed25519PrivateKey:
    path = (os.getenv("MCP_CALL_ASSERTION_KEY_FILE") or "").strip()
    if not path:
        raise AssertionUnavailable("MCP_CALL_ASSERTION_KEY_FILE is not set")
    try:
        stamp = os.stat(path).st_mtime
        cached = _KEY_CACHE.get(path)
        if cached and cached[0] == stamp:
            return cached[1]
        with open(path, "rb") as handle:
            key = serialization.load_pem_private_key(handle.read(), password=None)
    except (OSError, ValueError) as exc:
        raise AssertionUnavailable(f"call-assertion key {path} is unusable: {exc}") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise AssertionUnavailable(f"call-assertion key {path} is not an Ed25519 private key")
    _KEY_CACHE[path] = (stamp, key)
    return key


def args_hash(arguments: Any) -> str:
    """The `args` claim: sha256 of the canonical JSON of the tool arguments. The
    servers compute the same over the tools/call params.arguments they receive."""
    canonical = json.dumps(arguments if arguments is not None else {}, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def mint(
    *,
    audience: str,
    sub: str,
    tool: str,
    arguments: Any = None,
    key: Optional[Ed25519PrivateKey] = None,
    ttl: Optional[int] = None,
    now: Optional[float] = None,
) -> str:
    if not audience:
        raise AssertionUnavailable("an assertion needs the backend name as its audience")
    issued = int(now if now is not None else time.time())
    lifetime = max(1, min(int(ttl if ttl is not None else ttl_seconds()), MAX_TTL_SECONDS))
    claims: Dict[str, Any] = {
        "iss": ISSUER,
        "aud": audience,
        "sub": sub or "",
        "act": {"sub": ISSUER},
        "tool": tool or "",
        "iat": issued,
        "exp": issued + lifetime,
        "jti": uuid.uuid4().hex,
    }
    if tool:
        # A schema-read assertion (no tool) carries no args; it can call nothing.
        claims["args"] = args_hash(arguments)
    if key is None and signer() == "transit":
        return _transit_encode(claims)
    return jwt.encode(claims, key or signing_key(), algorithm=ALGORITHM, headers={"typ": TYPE})


def authorization_for(
    binding: Any, bearer_token: str, *, sub: str, tool: str, arguments: Any = None
) -> Optional[str]:
    """The Authorization header of one streamable-HTTP tool call, or None for none."""
    if mode() == "bearer" or getattr(binding, "user_token", False):
        return f"Bearer {bearer_token}"
    if not getattr(binding, "gateway_token", True):
        return None  # a third-party backend: it receives no identity at all
    return "Bearer " + mint(audience=binding.backend, sub=sub, tool=tool, arguments=arguments)


def schema_authorization_for(backend: str, gateway_token: bool) -> Optional[str]:
    """The Authorization header of a tools/list schema read: none in bearer mode
    (as before), an assertion for the gateway itself in assertion mode."""
    if mode() == "bearer" or not gateway_token or not backend:
        return None
    return "Bearer " + mint(audience=backend, sub=SELF_SUBJECT, tool="")
