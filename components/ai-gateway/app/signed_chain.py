"""ADR-0603 M14 (WP-225 lot C): the signed agent chain.

The agent a call is made for (`X-Zuno-Agent` / `X-Zuno-Task`) and its delegators
(`X-Zuno-Delegated-By`) are headers the caller writes. The a2a-gateway is the one
service that knows them for a fact: each of its A2A endpoints IS one admitted agent,
and it checks an inbound delegation chain against the signed OKF declarations
before it runs the turn (ADR-0401, ADR-0403, ADR-0406). From WP-225 lot C it says
so in a header the ai-gateway and the mcp-gateway can verify:

    X-Zuno-Agent-Chain: <compact JWS, EdDSA (Ed25519), typ zuno-agent-chain+jwt>

    {"iss": "a2a-gateway", "aud": "<ai-gateway|mcp-gateway>",
     "agent": "<executing agent>", "task": "<its task>",
     "hops": [["<outermost delegator>", "<task>"], ...],
     "ath": "<base64url SHA-256 of the bearer token sent with it>",
     "iat": ..., "exp": <iat + at most 60 s>, "jti": "<uuid>"}

- One key pair. Only the a2a-gateway holds the private key
  (AGENT_CHAIN_SIGNING_KEY_FILE); the verifiers hold the public key
  (AGENT_CHAIN_PUBLIC_KEY, PEM). A verifier cannot mint a chain.
- Bound to the token: `ath` is the hash of the exact bearer the call carries, so a
  chain copied onto another caller's request does not verify. Addressed: `aud` names
  the verifying service.
- Short: `exp - iat` is at most 60 s and a chain dated in the future is refused. A
  replay within that window needs the same bearer token and yields the same agent
  identity the a2a-gateway attested for that token, so `jti` is not tracked.

`resolve()` is the verifiers' entry point. With verification on and a valid chain,
the verified agent and task replace the headers, and an `X-Zuno-Agent` that
disagrees is ignored and logged. A missing, forged, expired or misaddressed chain
is ignored (logged when present): the call keeps today's behaviour, the unverified
headers, and every floor that applies to them.

This file is byte-identical in components/a2a-gateway, components/ai-gateway and
components/mcp-gateway (each image is built from its own directory, ADR-0119); the
lot C tests compare the copies.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Sequence, Tuple

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

logger = logging.getLogger("zuno.signed_chain")

HEADER = "X-Zuno-Agent-Chain"
TYPE = "zuno-agent-chain+jwt"
ISSUER = "a2a-gateway"
ALGORITHM = "EdDSA"
MAX_TTL_SECONDS = 60
# Clock skew accepted on `iat` and `exp`, never added to the 60 s lifetime bound.
LEEWAY_SECONDS = 5
MAX_HOPS = 8
_NAME = re.compile(r"^[a-z][a-z0-9-]*$")

Hops = Tuple[Tuple[str, str], ...]


class ChainSignatureError(ValueError):
    """The chain header is malformed, forged, expired, misaddressed or unbound."""


@dataclass(frozen=True)
class VerifiedChain:
    agent: str
    task: str
    hops: Hops  # the delegators, outermost first; empty for a direct call
    jti: str


def _truthy(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def token_hash(token: str) -> str:
    """`ath`: base64url (no padding) of the SHA-256 of the bearer token."""
    digest = hashlib.sha256((token or "").encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def load_private_key(pem: str) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("the agent-chain signing key is not an Ed25519 private key")
    return key


def load_public_key(pem: str) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(pem.encode("utf-8"))
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("the agent-chain public key is not an Ed25519 public key")
    return key


def _valid_name(value: Any) -> bool:
    return isinstance(value, str) and bool(_NAME.match(value))


def parse_hops(delegated_by: Optional[str]) -> Hops:
    """`X-Zuno-Delegated-By` (`agent:task[,agent:task]`) as hops; empty when absent."""
    hops: List[Tuple[str, str]] = []
    for part in (delegated_by or "").split(","):
        agent, sep, task = part.strip().partition(":")
        if sep and _valid_name(agent) and _valid_name(task):
            hops.append((agent, task))
        elif part.strip():
            raise ChainSignatureError(f"malformed delegation entry {part.strip()!r}")
    return tuple(hops)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def sign(
    *,
    private_key: Optional[Ed25519PrivateKey] = None,
    signer: Optional[Callable[[bytes], bytes]] = None,
    audience: str,
    token: str,
    agent: str,
    task: str,
    hops: Sequence[Tuple[str, str]] = (),
    ttl_seconds: int = MAX_TTL_SECONDS,
    now: Optional[float] = None,
) -> str:
    if not (_valid_name(agent) and _valid_name(task)):
        raise ChainSignatureError("the executing agent and task must be plain names")
    hop_list = [[a, t] for a, t in hops]
    if len(hop_list) > MAX_HOPS or not all(_valid_name(a) and _valid_name(t) for a, t in hop_list):
        raise ChainSignatureError("malformed delegation hops")
    issued = int(now if now is not None else time.time())
    ttl = max(1, min(int(ttl_seconds), MAX_TTL_SECONDS))
    claims = {
        "iss": ISSUER,
        "aud": audience,
        "agent": agent,
        "task": task,
        "hops": hop_list,
        "ath": token_hash(token),
        "iat": issued,
        "exp": issued + ttl,
        "jti": uuid.uuid4().hex,
    }
    if signer is not None:
        # WP-247 lot 2: the key lives in Vault Transit. `signer` takes the JWS signing input and
        # returns the 64-byte Ed25519 signature; the header is the one PyJWT writes below.
        header = {"typ": TYPE, "alg": ALGORITHM}
        signing_input = (
            _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8")) + "."
            + _b64url(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
        )
        return signing_input + "." + _b64url(signer(signing_input.encode("ascii")))
    if private_key is None:
        raise ChainSignatureError("sign() needs a private key or a signer")
    return jwt.encode(claims, private_key, algorithm=ALGORITHM, headers={"typ": TYPE})


def verify(
    value: str,
    *,
    public_key: Ed25519PublicKey,
    audience: str,
    token: str,
    now: Optional[float] = None,
) -> VerifiedChain:
    try:
        header = jwt.get_unverified_header(value)
    except jwt.PyJWTError as exc:
        raise ChainSignatureError(f"unreadable chain: {exc}") from exc
    if header.get("typ") != TYPE or header.get("alg") != ALGORITHM:
        raise ChainSignatureError("not an agent chain (typ or alg)")
    current = now if now is not None else time.time()
    try:
        # exp and iat are checked below against `current`, with the lifetime bound.
        claims = jwt.decode(
            value,
            public_key,
            algorithms=[ALGORITHM],
            audience=audience,
            issuer=ISSUER,
            options={"require": ["exp", "iat", "aud", "iss", "jti"], "verify_exp": False, "verify_iat": False},
        )
    except jwt.PyJWTError as exc:
        raise ChainSignatureError(f"invalid chain: {exc}") from exc
    iat, exp = claims.get("iat"), claims.get("exp")
    if not isinstance(iat, int) or not isinstance(exp, int):
        raise ChainSignatureError("iat and exp must be integers")
    if exp - iat > MAX_TTL_SECONDS or exp < iat:
        raise ChainSignatureError(f"lifetime above {MAX_TTL_SECONDS} s")
    if iat > current + LEEWAY_SECONDS:
        raise ChainSignatureError("issued in the future")
    if current > exp + LEEWAY_SECONDS:
        raise ChainSignatureError("expired")
    if claims.get("ath") != token_hash(token):
        raise ChainSignatureError("not bound to this bearer token")
    agent, task, raw_hops = claims.get("agent"), claims.get("task"), claims.get("hops")
    if not (_valid_name(agent) and _valid_name(task)):
        raise ChainSignatureError("malformed agent or task")
    if not isinstance(raw_hops, list) or len(raw_hops) > MAX_HOPS:
        raise ChainSignatureError("malformed hops")
    hops: List[Tuple[str, str]] = []
    for hop in raw_hops:
        if not (isinstance(hop, list) and len(hop) == 2 and _valid_name(hop[0]) and _valid_name(hop[1])):
            raise ChainSignatureError("malformed hop")
        hops.append((hop[0], hop[1]))
    return VerifiedChain(agent=agent, task=task, hops=tuple(hops), jti=str(claims.get("jti")))


# --- configuration (read per call, keys cached by their source) ---------------

_PUBLIC_CACHE: dict = {}
_PRIVATE_CACHE: dict = {}


def verification_enabled() -> bool:
    """AGENT_CHAIN_VERIFY (verifiers). Off by default: the header is then ignored."""
    return _truthy(os.getenv("AGENT_CHAIN_VERIFY"))


def public_key_from_env() -> Optional[Ed25519PublicKey]:
    pem = (os.getenv("AGENT_CHAIN_PUBLIC_KEY") or "").strip()
    if not pem:
        return None
    if pem not in _PUBLIC_CACHE:
        try:
            _PUBLIC_CACHE[pem] = load_public_key(pem)
        except ValueError as exc:
            logger.error("AGENT_CHAIN_PUBLIC_KEY is unusable, no chain verifies: %s", exc)
            _PUBLIC_CACHE[pem] = None
    return _PUBLIC_CACHE[pem]


def private_key_from_env() -> Optional[Ed25519PrivateKey]:
    """AGENT_CHAIN_SIGNING_KEY_FILE (the a2a-gateway only). None when unset or unreadable."""
    path = (os.getenv("AGENT_CHAIN_SIGNING_KEY_FILE") or "").strip()
    if not path:
        return None
    try:
        stamp = os.stat(path).st_mtime
        cached = _PRIVATE_CACHE.get(path)
        if cached and cached[0] == stamp:
            return cached[1]
        with open(path, "r", encoding="utf-8") as handle:
            key = load_private_key(handle.read())
    except (OSError, ValueError) as exc:
        logger.error("agent-chain signing key %s is unusable, no chain is signed: %s", path, exc)
        return None
    _PRIVATE_CACHE[path] = (stamp, key)
    return key


@dataclass(frozen=True)
class Resolved:
    agent: str
    task: str
    hops: Optional[Hops]  # None: no verified chain, keep the caller's delegation headers
    verified: bool


def resolve(
    value: Optional[str],
    declared_agent: str,
    declared_task: str,
    *,
    token: str,
    audience: str,
    log: Optional[logging.Logger] = None,
) -> Resolved:
    """The agent identity a verifier uses for one call (see the module docstring)."""
    log = log or logger
    unverified = Resolved(agent=declared_agent, task=declared_task, hops=None, verified=False)
    value = (value or "").strip()
    if not value or not verification_enabled():
        return unverified
    key = public_key_from_env()
    if key is None:
        log.warning("agent chain present but no public key is configured; using the unverified headers")
        return unverified
    try:
        chain = verify(value, public_key=key, audience=audience, token=token)
    except ChainSignatureError as exc:
        log.warning("agent chain ignored (%s); using the unverified headers agent=%s", exc, declared_agent or "-")
        return unverified
    declared = (declared_agent or "").strip().lower()
    if declared and declared != chain.agent:
        log.warning(
            "X-Zuno-Agent %r disagrees with the verified agent chain (%s); the header is ignored",
            declared_agent, chain.agent,
        )
    elif (declared_task or "").strip() and (declared_task or "").strip().lower() != chain.task:
        log.warning(
            "X-Zuno-Task %r disagrees with the verified agent chain (%s/%s); the header is ignored",
            declared_task, chain.agent, chain.task,
        )
    return Resolved(agent=chain.agent, task=chain.task, hops=chain.hops, verified=True)
