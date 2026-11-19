"""Turn the Zuno tools off for some models in Open WebUI (ADR-0619, WP-296), from inside the Open WebUI pod.

    oc exec -i <pod> -- sh -c 'cd /app/backend && python3 - "$1"' _ '{"no_tools": ["praxis.claude", ...]}' < this file

The chart attaches the Zuno tools to every model (DEFAULT_MODEL_METADATA toolIds). Praxis refuses a SaaS call that
carries tools (owner's decision of 2026-11-18: no tool result reaches a SaaS), so each listed model gets a per-model
entry whose `meta.toolIds` is an empty list: Open WebUI keeps a per-model value over the global default
(open_webui/utils/models.py, "Per-model overrides take precedence"). The entry keeps the model public (a read grant
to everyone: an entry with no grant would hide the model from every user but the administrators), is owned by the
first administrator and keeps any other field it already has. Idempotent; prints one JSON line,
{"<id>": "created" | "updated" | "unchanged"}. Reads and writes nothing else, and no secret.
"""
from __future__ import annotations

import asyncio
import json
import sys

PUBLIC_READ = {"principal_type": "user", "principal_id": "*", "permission": "read"}


def desired(model_id: str, existing: dict | None) -> dict:
    """The entry wanted for model_id: the existing entry's fields with toolIds emptied and the public read grant."""
    existing = existing or {}
    meta = dict(existing.get("meta") or {})
    meta["toolIds"] = []
    grants = [g for g in (existing.get("access_grants") or []) if isinstance(g, dict)]
    if not any(_is_public_read(g) for g in grants):
        grants.append(dict(PUBLIC_READ))
    return {
        "id": model_id,
        "base_model_id": existing.get("base_model_id"),
        "name": existing.get("name") or model_id,
        "meta": meta,
        "params": dict(existing.get("params") or {}),
        "access_grants": [{k: g[k] for k in ("principal_type", "principal_id", "permission")} for g in grants],
        "is_active": existing.get("is_active", True),
    }


def needs_write(existing: dict | None) -> bool:
    """True when the entry is missing, still has tools, or is not public."""
    if not existing:
        return True
    if (existing.get("meta") or {}).get("toolIds") != []:
        return True
    return not any(_is_public_read(g) for g in existing.get("access_grants") or [] if isinstance(g, dict))


def _is_public_read(grant: dict) -> bool:
    return (grant.get("principal_type"), grant.get("principal_id"), grant.get("permission")) == ("user", "*", "read")


async def _apply(model_ids: list[str]) -> dict[str, str]:
    from open_webui.models.models import ModelForm, Models
    from open_webui.models.users import Users

    owner = await Users.get_super_admin_user()
    if owner is None:
        raise SystemExit("no Open WebUI administrator yet: sign in once as a member of openwebui_admin, then rerun")
    result: dict[str, str] = {}
    for model_id in model_ids:
        current = await Models.get_model_by_id(model_id)
        existing = None
        if current is not None:
            existing = current.model_dump()
            existing["access_grants"] = [g.model_dump() if hasattr(g, "model_dump") else g
                                         for g in (current.access_grants or [])]
        if not needs_write(existing):
            result[model_id] = "unchanged"
            continue
        form = ModelForm(**desired(model_id, existing))
        if current is None:
            await Models.insert_new_model(form, owner.id)
            result[model_id] = "created"
        else:
            await Models.update_model_by_id(model_id, form)
            result[model_id] = "updated"
    return result


def main(argv: list[str]) -> int:
    config = json.loads(argv[1]) if len(argv) > 1 else {}
    model_ids = [m for m in config.get("no_tools") or [] if isinstance(m, str) and m]
    print(json.dumps(asyncio.run(_apply(model_ids)) if model_ids else {}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
