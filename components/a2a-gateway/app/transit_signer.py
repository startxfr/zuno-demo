"""WP-247 lot 2 (ADR-0602 option A): the agent-chain signature made by Vault Transit.

The a2a-gateway signs `X-Zuno-Agent-Chain` (app/signed_chain.py). With AGENT_CHAIN_SIGNER=transit
the Ed25519 key never reaches the pod: this module logs in to Vault with the pod's ServiceAccount
token (Kubernetes auth, role VAULT_AUTH_ROLE) and asks `transit/sign/<VAULT_TRANSIT_KEY>` for the
signature of the JWS signing input. Standard library only; every Vault call has a 2 s timeout.

A failure raises TransitUnavailable; the caller (app/clients.py) then sends NO chain, exactly as it
does today for an unreadable key file: the verifiers keep the unverified headers and every floor that
applies to them. There is no fallback to a local key.

Same client as components/mcp-gateway/app/call_assertion.py (each image is built from its own
directory, ADR-0119, so it is duplicated, not shared)."""

from __future__ import annotations

import base64
import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict

SIGNERS = ("file", "transit")

_SA_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
# Seconds before a Vault client token expires at which it is renewed by logging in again.
_TOKEN_MARGIN_SECONDS = 30
_VAULT_TIMEOUT_SECONDS = 2.0


class TransitUnavailable(RuntimeError):
    """Transit signing is selected but Vault cannot sign."""


def signer() -> str:
    """AGENT_CHAIN_SIGNER: `file` (the default, the key mounted in the pod) or `transit`.
    An unknown value is an error, never a silent `file`."""
    raw = (os.getenv("AGENT_CHAIN_SIGNER") or "file").strip().lower()
    if raw not in SIGNERS:
        raise TransitUnavailable(f"AGENT_CHAIN_SIGNER must be one of {SIGNERS}, not {raw!r}")
    return raw


class VaultTransit:
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
            raise TransitUnavailable(
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
            raise TransitUnavailable(f"the ServiceAccount token {cfg['sa_token']} is unreadable: {exc}") from exc
        answer = self._post(cfg, f"auth/{cfg['auth_mount']}/login", {"role": cfg["role"], "jwt": jwt_value})
        auth = answer.get("auth") or {}
        token = auth.get("client_token")
        if not token:
            raise TransitUnavailable("Vault answered the login without a client token")
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
        except TransitUnavailable:
            raise
        except (OSError, ValueError) as exc:  # URLError, HTTPError, timeouts, bad JSON
            with self._lock:
                self._token = ""
            raise TransitUnavailable(f"Vault transit signing is unavailable: {exc}") from exc
        signature = str((answer.get("data") or {}).get("signature") or "")
        prefix, _, encoded = signature.rpartition(":")
        try:
            raw = base64.b64decode(encoded, validate=True) if prefix.startswith("vault:v") else b""
        except ValueError:
            raw = b""
        if len(raw) != 64:  # an ed25519 signature is exactly 64 bytes
            raise TransitUnavailable("Vault returned something that is not an ed25519 signature")
        return raw


_TRANSIT = VaultTransit()


def sign(data: bytes) -> bytes:
    """The Ed25519 signature of `data` made by Vault (the process-wide client)."""
    return _TRANSIT.sign(data)
