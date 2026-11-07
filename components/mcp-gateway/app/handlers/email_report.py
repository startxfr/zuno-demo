"""Demo-mode handler for the ``send_technical_report_email`` MCP tool.

Per MEMORY.md section 5: agents must never send email externally or
impersonate a user's mailbox for outbound mail. Scheduled/triggered
reporting must use a technical SMTP identity and stay restricted to
internal recipients -- this handler enforces that constraint even in demo
mode (it rejects any recipient outside the internal domain allow-list
rather than pretending to send it).

To make this call a real mailbox: replace the "send" step below with an
SMTP call (see ansible/roles/smtp, owned by another track) using the
technical SMTP identity's credentials sourced from
``secret/zuno/smtp/technical`` -- never a user's own mailbox credential.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger("mcp_gateway.email_report")

# Domains considered "internal" for this demo. Override via the
# INTERNAL_EMAIL_DOMAINS env var (comma-separated) once a real internal
# domain is known for the target environment.
_INTERNAL_DOMAINS = tuple(
    d.strip().lower()
    for d in os.getenv("INTERNAL_EMAIL_DOMAINS", "zuno.example.internal").split(",")
    if d.strip()
)


def _is_internal(recipient: str) -> bool:
    recipient = recipient.strip().lower()
    return "@" in recipient and recipient.split("@", 1)[1] in _INTERNAL_DOMAINS


def recipient_allowlist() -> Dict[str, List[str]]:
    """ADR-0603 M12 (WP-225 lot B): EMAIL_RECIPIENT_ALLOWLIST, a JSON object
    {Keycloak group: [recipient pattern]}. A pattern is an address or an fnmatch
    pattern (`*@ops.zuno.example.internal`), matched case-insensitively.

    Empty or unset: no allowlist, the behaviour before WP-225 (the internal-domain
    rule above still applies). Malformed: fails closed, every recipient refused."""
    raw = os.getenv("EMAIL_RECIPIENT_ALLOWLIST", "").strip()
    if not raw:
        return {}
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("EMAIL_RECIPIENT_ALLOWLIST is not valid JSON; every recipient is refused")
        return {"": []}
    if not isinstance(doc, dict):
        logger.error("EMAIL_RECIPIENT_ALLOWLIST is not a JSON object; every recipient is refused")
        return {"": []}
    if not doc:
        return {}  # "{}" (the chart default rendered as JSON) is no allowlist
    return {
        str(group): [str(p).strip().lower() for p in patterns if isinstance(p, str) and p.strip()]
        for group, patterns in doc.items()
        if isinstance(patterns, list)
    } or {"": []}


def _allowed_by_groups(recipient: str, groups: List[str], allowlist: Dict[str, List[str]]) -> bool:
    recipient = recipient.strip().lower()
    for group in groups:
        for pattern in allowlist.get(group, ()):
            if fnmatch.fnmatchcase(recipient, pattern):
                return True
    return False


async def handle(
    arguments: Dict[str, Any],
    caller_sub: str,
    delegated_token: Optional[str] = None,
    bearer_token: str = "",
    caller_groups: Optional[List[str]] = None,
) -> Dict[str, Any]:
    # auth_mode=service-identity (ADR-0208): the technical SMTP identity
    # is a shared credential, never a per-user one - delegated_token is
    # always None here and intentionally unused.
    recipients: List[str] = list(arguments.get("recipients", []) or [])
    subject = str(arguments.get("subject", "")).strip()
    body = str(arguments.get("body", "")).strip()

    rejected = [r for r in recipients if not _is_internal(r)]
    if rejected:
        return {
            "demo_mode": True,
            "sent": False,
            "reason": (
                "recipients outside the internal domain allow-list are rejected "
                f"(agents must not send mail externally): {rejected}"
            ),
        }

    # ADR-0603 M12: the recipients the caller's own groups may reach. The groups
    # come from the validated token (app/main.py), never from the arguments.
    allowlist = recipient_allowlist()
    if allowlist:
        outside = [r for r in recipients if not _allowed_by_groups(r, list(caller_groups or []), allowlist)]
        if outside:
            return {
                "demo_mode": True,
                "sent": False,
                "reason": (
                    "recipients outside the allowlist of the caller's groups are rejected "
                    f"(ADR-0603 M12): {outside}"
                ),
            }

    return {
        "demo_mode": True,
        "sent": True,
        "via": "technical-smtp-identity",
        "recipients": recipients,
        "subject": subject,
        "body_preview": body[:200],
        "caller_sub": caller_sub,
    }
