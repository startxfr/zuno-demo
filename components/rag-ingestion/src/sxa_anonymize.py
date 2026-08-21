"""ADR-0216: deterministic, schema-aware PII redaction for SXA content
before it enters the RAG vector index.

Real record values keep flowing unredacted through the access-controlled,
audit-logged `sales-db` MCP tools (ADR-0216's Security considerations) -
this module governs only the RAG embedding path, where a leaked value is
effectively permanent and has weaker per-query access control than a live
SQL grant.

Column-map based, not a heuristic/NER scanner: the SXA schema
(data/sxa/schema/001_init.sql) is fully known, so every PII-bearing
column is named explicitly in PII_COLUMNS below. A column not listed
passes through unchanged; a listed column is always redacted, regardless
of its value's shape. This keeps the transform auditable - reviewing
whether PII can leak into the vector index means reviewing this map, not
guessing at a model's recall.

Adding a table/column to the real dump's schema that isn't reflected here
is a silent leak, not a fail-closed error (ADR-0216's Security
considerations calls this out as a named operator review, not an implicit
guarantee) - keep PII_COLUMNS in sync with data/sxa/schema/001_init.sql
whenever either changes.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger("sxa_anonymize")

# table -> {column: redaction kind}. Only columns holding a real person's
# or organization's identifying data are listed - foreign keys, statuses,
# amounts, dates and product/catalog data are never PII and stay out.
PII_COLUMNS: Dict[str, Dict[str, str]] = {
    "customers": {
        "name": "org_name",
        "legal_name": "org_name",
        "phone": "phone",
        "notes": "freetext",
    },
    "contacts": {
        "first_name": "person_name",
        "last_name": "person_name",
        "email": "email",
        "phone": "phone",
    },
    "users": {
        "username": "person_name",
        "email": "email",
        "display_name": "person_name",
        "keycloak_subject": "opaque",
    },
}

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?:\+?\d[\d .-]{6,}\d)")

_PREFIXES = {
    "person_name": "Person",
    "org_name": "Organization",
    "opaque": "id",
}


def _pseudonym(value: str, kind: str) -> str:
    """Deterministic pseudonym: the same input always maps to the same
    output (so cross-record references, e.g. an activity note mentioning
    a contact also named elsewhere, stay internally consistent), but the
    output never reveals the original value - a keyless one-way hash, not
    reversible encryption, since nothing downstream ever needs the real
    value back out of the vector index."""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]
    if kind == "email":
        return f"person-{digest}@example.invalid"
    if kind == "phone":
        return f"+00-000-{digest[:7]}"
    return f"{_PREFIXES.get(kind, 'REDACTED')}-{digest}"


def redact_freetext(text: str) -> str:
    """Best-effort inline redaction for free-text fields (e.g. notes) that
    may embed an email/phone inline rather than being a dedicated PII
    column - regex-based and deliberately conservative: a false-positive
    redaction is safe, a missed real pattern is not. This is not a
    substitute for keeping a genuinely PII-heavy free-text column out of
    the RAG path entirely if it doesn't fit this kind of pattern-based
    coverage."""
    text = _EMAIL_RE.sub(lambda m: _pseudonym(m.group(0), "email"), text)
    text = _PHONE_RE.sub(lambda m: _pseudonym(m.group(0), "phone"), text)
    return text


def redact_value(table: str, column: str, value: Any) -> Any:
    """Redacts one field if (table, column) is PII-bearing; passes
    everything else - including None/empty values - through unchanged."""
    if value is None or value == "":
        return value
    kind = PII_COLUMNS.get(table, {}).get(column)
    if kind is None:
        return value
    if kind == "freetext":
        return redact_freetext(str(value))
    return _pseudonym(str(value), kind)


def redact_row(table: str, row: Dict[str, Any]) -> Dict[str, Any]:
    """Redacts every PII-bearing column in one row. Returns a new dict;
    never mutates the input row."""
    return {column: redact_value(table, column, value) for column, value in row.items()}


def audit_pii_patterns(table: str, row: Dict[str, Any]) -> List[str]:
    """ADR-0217: fetch-sxa's audit-only counterpart to redact_row() above -
    for a source the operator asserts is ALREADY anonymized upstream. Never
    alters a value; only reports which (table, column) pairs in this row
    look PII-shaped, so an upstream anonymization miss is visible in logs
    instead of silently indexed with no signal at all.

    Uses the same PII_COLUMNS map as the enforcing path (one map, two
    behaviors) plus the same email/phone regexes redact_freetext() uses,
    so a listed column with a still-real-looking value, or ANY column
    (listed or not) containing an inline email/phone pattern, gets
    flagged. A false positive here just logs a line; a missed real pattern
    is the risk this function exists to reduce, so it deliberately reuses
    the same conservative-but-real patterns rather than inventing a looser
    set."""
    hits: List[str] = []
    known_columns = PII_COLUMNS.get(table, {})
    for column, value in row.items():
        if value is None or value == "":
            continue
        text = str(value)
        if column in known_columns:
            hits.append(f"{table}.{column}")
            continue
        if _EMAIL_RE.search(text) or _PHONE_RE.search(text):
            hits.append(f"{table}.{column}")
    if hits:
        logger.warning(
            "audit_pii_patterns: PII-shaped value(s) seen in already-anonymized "
            "source, table=%s columns=%s - value(s) passed through unchanged "
            "(ADR-0217 trusts upstream anonymization; this is visibility, not "
            "enforcement)",
            table, hits,
        )
    return hits
