"""ADR-0216 (WP-065): deterministic, schema-aware PII redaction for SXA
content before it enters the RAG vector index. Fixture-driven, no live
MariaDB is ever contacted.

Run:
    cd components/rag-ingestion && .venv/bin/python tests/test_sxa_anonymize.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import sxa_anonymize  # noqa: E402


def test_pii_column_is_redacted() -> None:
    row = {"id": 1, "first_name": "Jean", "last_name": "Dupont", "email": "jean.dupont@example.com"}
    redacted = sxa_anonymize.redact_row("contacts", row)
    assert redacted["first_name"] != "Jean"
    assert redacted["last_name"] != "Dupont"
    assert redacted["email"] != "jean.dupont@example.com"
    assert redacted["email"].endswith("@example.invalid")


def test_non_pii_column_passes_through_unchanged() -> None:
    row = {"id": 42, "reference": "OPP-2026-001", "customer_id": 7}
    redacted = sxa_anonymize.redact_row("opportunities", row)
    assert redacted == row


def test_unknown_table_passes_through_unchanged() -> None:
    """A table with no PII_COLUMNS entry at all - opportunity_statuses,
    order_statuses, etc. - must never be touched."""
    row = {"code": "won", "label": "Won", "is_closed": True}
    redacted = sxa_anonymize.redact_row("opportunity_statuses", row)
    assert redacted == row


def test_redaction_is_deterministic_across_calls() -> None:
    """Same input maps to the same pseudonym every time, so cross-record
    references stay internally consistent."""
    first = sxa_anonymize.redact_value("contacts", "email", "a@b.com")
    second = sxa_anonymize.redact_value("contacts", "email", "a@b.com")
    assert first == second


def test_redaction_differs_for_different_inputs() -> None:
    a = sxa_anonymize.redact_value("contacts", "first_name", "Alice")
    b = sxa_anonymize.redact_value("contacts", "first_name", "Bob")
    assert a != b


def test_none_and_empty_values_pass_through() -> None:
    assert sxa_anonymize.redact_value("contacts", "email", None) is None
    assert sxa_anonymize.redact_value("contacts", "email", "") == ""


def test_freetext_column_redacts_inline_email_and_phone() -> None:
    note = "Called customer at +33 6 12 34 56 78, follow up via jean@example.com next week."
    redacted = sxa_anonymize.redact_value("customers", "notes", note)
    assert "jean@example.com" not in redacted
    assert "+33 6 12 34 56 78" not in redacted
    assert "follow up via" in redacted  # non-PII prose is preserved


def test_freetext_with_no_pii_pattern_is_returned_unchanged() -> None:
    note = "Quarterly review scheduled for next month."
    assert sxa_anonymize.redact_freetext(note) == note


def test_pii_columns_map_covers_every_known_pii_bearing_table() -> None:
    """A minimal completeness guard: the tables ADR-0216 explicitly names
    (customers, contacts, users) must be present in the map. This doesn't
    prove the map is exhaustive against a real schema - that's the named
    operator review WP-065's brief calls out - but it catches an
    accidental removal."""
    for table in ("customers", "contacts", "users"):
        assert table in sxa_anonymize.PII_COLUMNS, f"{table} missing from PII_COLUMNS"


TESTS = [
    test_pii_column_is_redacted,
    test_non_pii_column_passes_through_unchanged,
    test_unknown_table_passes_through_unchanged,
    test_redaction_is_deterministic_across_calls,
    test_redaction_differs_for_different_inputs,
    test_none_and_empty_values_pass_through,
    test_freetext_column_redacts_inline_email_and_phone,
    test_freetext_with_no_pii_pattern_is_returned_unchanged,
    test_pii_columns_map_covers_every_known_pii_bearing_table,
]


def main() -> int:
    failed = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS {test.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
