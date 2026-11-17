"""Settings of world-model-web, read once from the environment (ADR-0604 D1, D4, D8, §8)."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple


def _list(name: str, default: str) -> Tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    return float(raw) if raw else default


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    return default if not raw else raw in {"1", "true", "yes", "on"}


ZUNO_GATEWAY = "zuno"  # the id of the default prompt-enhancement gateway: the Zuno ai-gateway
_GATEWAY_ID = re.compile(r"^[a-z0-9]([a-z0-9-]{0,38}[a-z0-9])?$")


@dataclass(frozen=True)
class AltGateway:
    """WP-303 (ADR-0619 clause 5): an alternative AI gateway the prompt enhancement may use instead of the Zuno one.

    `url` is its OpenAI base URL as the `altGateways` contract writes it (it ends with /v1); the caller's own
    token is sent to it, as to the Zuno ai-gateway."""

    name: str
    url: str
    label: str = ""
    model: str = "auto"  # the entry's first `models` item


def _alt_gateways(raw: str) -> Tuple[AltGateway, ...]:
    """ALT_GATEWAYS: a JSON list of {name, url, label?, models?}. Unset or empty: none."""
    if not raw.strip():
        return ()
    value = json.loads(raw)
    if not isinstance(value, list):
        raise ValueError("ALT_GATEWAYS must be a JSON list")
    found = []
    for entry in value:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str) or not isinstance(entry.get("url"), str):
            raise ValueError("ALT_GATEWAYS: every entry is an object with a name and a url")
        name, url = entry["name"], entry["url"]
        if not _GATEWAY_ID.match(name) or name == ZUNO_GATEWAY:
            raise ValueError(f"ALT_GATEWAYS: {name!r} must be a DNS label of at most 40 characters, and not {ZUNO_GATEWAY!r}")
        if not re.match(r"^https?://[^/\s]+", url):
            raise ValueError(f"ALT_GATEWAYS: {name}: url must be an http(s) URL")
        if any(g.name == name for g in found):
            raise ValueError(f"ALT_GATEWAYS: {name} is listed twice")
        models = entry.get("models") or ["auto"]
        if not isinstance(models, list) or not all(isinstance(m, str) and m for m in models):
            raise ValueError(f"ALT_GATEWAYS: {name}: models must be a list of names")
        found.append(AltGateway(name=name, url=url.rstrip("/"), label=str(entry.get("label") or name), model=models[0]))
    return tuple(found)


@dataclass(frozen=True)
class Settings:
    # --- identity (Keycloak realm zuno, behind the oauth2-proxy front door) -------------------
    auth_mode: str = "oidc"  # "oidc", or "dev" for a local run only (never set by the chart)
    issuer: str = "https://keycloak.apps.mycluster.example.com/realms/zuno"
    jwks_url: str = ""
    audience: str = "zuno-admin-api"  # carried by every experience client (maas-gateway-audience)
    # Sign out (oauth2-proxy cookie, then the Keycloak SSO session): the public https URL of this site and the
    # Keycloak client Keycloak may send the browser back for. Empty public_url = no sign-out link (a local run).
    public_url: str = ""
    logout_client_id: str = "world-model"
    # Groups that may open the demo, and groups that may also release someone else's session.
    allowed_groups: Tuple[str, ...] = ("zuno-world-model-users", "ocp-ai-ops", "ocp-paas-ops")
    ops_groups: Tuple[str, ...] = ("ocp-ai-ops", "ocp-paas-ops")
    # Origins a browser may open the session WebSocket from; empty = same host as the request.
    allowed_origins: Tuple[str, ...] = ()
    # --- the GPU runtime ------------------------------------------------------------------------
    runtime_url: str = "http://world-model-runtime:8080"
    runtime_token: str = ""
    runtime_timeout: float = 120.0  # a FLUX image can take seconds on a cold GPU
    # --- prompt enhancement through the ai-gateway (D8) -----------------------------------------
    gateway_url: str = ""  # empty = enhancement off
    gateway_model: str = "auto"
    gateway_timeout: float = 8.0
    # WP-303: the alternative gateways a visitor may pick for the enhancement, and the one used when none is
    # named (the Zuno ai-gateway unless PROMPT_GATEWAY names an alternative). Empty list = as before.
    alt_gateways: Tuple[AltGateway, ...] = ()
    default_gateway: str = ZUNO_GATEWAY
    max_prompt_chars: int = 300
    deny_terms_file: str = ""
    # --- lease and quotas (one world per GPU) ---------------------------------------------------
    idle_seconds: int = 180
    # A world nobody watches (the tab closed) gives the GPU back after this long.
    detached_seconds: int = 60
    max_session_seconds: int = 1800
    worlds_per_hour: int = 12
    # --- content --------------------------------------------------------------------------------
    presets_file: Path = Path("/app/config/presets.yaml")
    ui_dir: Path = Path("/app/ui/dist")

    @classmethod
    def from_env(cls) -> "Settings":
        issuer = os.getenv("KEYCLOAK_ISSUER", cls.issuer).rstrip("/")
        return cls(
            auth_mode=os.getenv("WORLD_MODEL_AUTH", "oidc").strip(),
            issuer=issuer,
            jwks_url=os.getenv("KEYCLOAK_JWKS_URL", f"{issuer}/protocol/openid-connect/certs"),
            audience=os.getenv("JWT_AUDIENCE", cls.audience),
            public_url=os.getenv("WORLD_MODEL_PUBLIC_URL", "").strip().rstrip("/"),
            logout_client_id=os.getenv("WORLD_MODEL_LOGOUT_CLIENT_ID", cls.logout_client_id).strip(),
            allowed_groups=_list("ALLOWED_GROUPS", ",".join(cls.allowed_groups)),
            ops_groups=_list("OPS_GROUPS", ",".join(cls.ops_groups)),
            allowed_origins=_list("ALLOWED_ORIGINS", ""),
            runtime_url=os.getenv("WORLD_MODEL_RUNTIME_URL", cls.runtime_url).rstrip("/"),
            runtime_token=os.getenv("WORLD_MODEL_INTERNAL_TOKEN", ""),
            runtime_timeout=_float("WORLD_MODEL_RUNTIME_TIMEOUT", 120.0),
            gateway_url=os.getenv("AI_GATEWAY_URL", "").rstrip("/"),
            gateway_model=os.getenv("PROMPT_MODEL", "auto"),
            gateway_timeout=_float("PROMPT_ENHANCE_TIMEOUT", 8.0),
            alt_gateways=_alt_gateways(os.getenv("ALT_GATEWAYS", "")),
            default_gateway=os.getenv("PROMPT_GATEWAY", ZUNO_GATEWAY).strip() or ZUNO_GATEWAY,
            max_prompt_chars=_int("MAX_PROMPT_CHARS", 300),
            deny_terms_file=os.getenv("DENY_TERMS_FILE", ""),
            idle_seconds=_int("SESSION_IDLE_SECONDS", 180),
            detached_seconds=_int("SESSION_DETACHED_SECONDS", 60),
            max_session_seconds=_int("SESSION_MAX_SECONDS", 1800),
            worlds_per_hour=_int("WORLDS_PER_HOUR", 12),
            presets_file=Path(os.getenv("PRESETS_FILE", str(cls.presets_file))),
            ui_dir=Path(os.getenv("UI_DIR", str(cls.ui_dir))),
        )

    def validate(self) -> None:
        if self.auth_mode not in ("oidc", "dev"):
            raise ValueError(f"WORLD_MODEL_AUTH must be oidc or dev, not {self.auth_mode!r}")
        if self.auth_mode == "oidc" and not self.audience:
            raise ValueError("JWT_AUDIENCE must be set in oidc mode: any token of the realm would be accepted")
        if self.default_gateway != ZUNO_GATEWAY and self.default_gateway not in {g.name for g in self.alt_gateways}:
            raise ValueError(f"PROMPT_GATEWAY {self.default_gateway!r} is neither {ZUNO_GATEWAY!r} nor an ALT_GATEWAYS name")
        if self.auth_mode == "oidc" and not self.allowed_groups:
            raise ValueError("ALLOWED_GROUPS must not be empty in oidc mode")
