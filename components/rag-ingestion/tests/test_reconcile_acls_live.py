"""WP-25 (ADR-0110): read-only live proof that reconcile-acls's page
listing actually reaches real Confluence content, as opposed to
test_reconcile_acls.py's fixture-only coverage (never contacts Confluence
or a database). Calls the exact same read path stage_reconcile_acls uses
(_confluence_auth + _list_confluence_space_pages) against the real "SXSI"
space (gitops/charts/rag-ingestion/values.yaml's six knowledge.tech
sources all point here - the "ARCH" space referenced in ADR-0110's own
note is confirmed empty and deliberately not what this checks). Never
writes anything - no database, no Confluence page create/update/delete.

Requires real credentials (CONFLUENCE_URL, CONFLUENCE_USERNAME,
CONFLUENCE_TOKEN - same names/secret `rag-confluence` production reads)
and network reach to Confluence Cloud; skips (exit 0) rather than fails
when they're absent, so this is safe to leave in a CI image that has
neither.

Run:
    cd components/rag-ingestion && .venv/bin/python tests/test_reconcile_acls_live.py
"""
import os
import sys
import unittest.mock as mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import rag_ingestion  # noqa: E402
from rag_ingestion import _confluence_auth, _list_confluence_space_pages  # noqa: E402

SPACE = "SXSI"
# Real directories this space's sources actually filter by (values.yaml) -
# not asserted individually, just used as a sanity check that real content
# under them is present in the raw listing.
EXPECTED_ANCESTOR_HINTS = ("Openshift", "Satellite", "Gitlab")


def _live_config():
    base_url = os.environ.get("CONFLUENCE_URL")
    username = os.environ.get("CONFLUENCE_USERNAME")
    token = os.environ.get("CONFLUENCE_TOKEN")
    if not (base_url and username and token):
        return None, None
    required_env = {
        "S3_BUCKET": "test-bucket",
        "PGHOST": "localhost",
        "PGDATABASE": "rag-tech",
        "EMBEDDING_ENDPOINT": "http://embeddings.test/v1",
        "EMBEDDING_MODEL": "test-model",
        "CONFLUENCE_USERNAME": username,
        "CONFLUENCE_TOKEN": token,
    }
    with mock.patch.dict(os.environ, required_env, clear=True):
        config = rag_ingestion.load_config()
    return config, base_url


def main() -> int:
    config, base_url = _live_config()
    if config is None:
        print(
            "test_reconcile_acls_live: SKIPPED - CONFLUENCE_URL/CONFLUENCE_USERNAME/"
            "CONFLUENCE_TOKEN not set, no live credentials to verify against"
        )
        return 0

    auth = _confluence_auth(config)
    pages = _list_confluence_space_pages(base_url, SPACE, auth)

    assert pages, f"expected real content in space '{SPACE}', got zero pages"

    seen_ancestors = {title for page in pages for title in page["ancestor_titles"]}
    matched_hints = [h for h in EXPECTED_ANCESTOR_HINTS if any(h in a for a in seen_ancestors)]
    assert matched_hints, (
        f"listed {len(pages)} page(s) in '{SPACE}' but none of their ancestor titles "
        f"matched any of {EXPECTED_ANCESTOR_HINTS} - space may have been restructured"
    )

    print(
        f"test_reconcile_acls_live: PASSED - {len(pages)} real page(s) listed live in "
        f"space '{SPACE}', matched directory hints: {matched_hints}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
