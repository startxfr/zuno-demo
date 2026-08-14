#!/usr/bin/env python3
"""ADR-0330 catalog verification tool (roadmap WP-07).

Iterates every entry in `gitops/charts/rag-ingestion/values.yaml`'s
`redhat[]` array and HTTP-verifies its `documentationUrl`. Every
non-Satellite entry there is WebSearch-sourced, not HTTP-verified
(`docs.redhat.com` returns HTTP 403 to the environment this ADR/tool was
authored in - see ADR-0330's "Follow-up implementation" section), so this
tool exists to let an operator run the real check from a network that can
reach `docs.redhat.com`, then hand the report back.

Output is one line per entry:

    OK        product='...' version='...' url=... detail=200
    REDIRECT  product='...' version='...' url=... detail=<final-url>
    FAIL      product='...' version='...' url=... detail=<reason>

designed to be pasted back verbatim so a follow-up mechanical pass can
update `values.yaml`: OK entries need no change, REDIRECT entries should
have `documentationUrl` updated to the reported final URL, FAIL entries
need investigation (wrong slug/version, page moved, or a real access
problem) before the corresponding `redhat[]` entry can be trusted - see
the WP-07 roadmap brief's "Post-operator repo follow-up" section. This
tool does not modify values.yaml itself.

Run from a network that can reach docs.redhat.com:

    cd components/rag-ingestion/tooling
    pip install -r requirements.txt
    python3 verify_catalog.py
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Any, Dict, List, Tuple

import requests
import yaml

DEFAULT_VALUES_PATH = (
    pathlib.Path(__file__).resolve().parents[3] / "gitops" / "charts" / "rag-ingestion" / "values.yaml"
)
TIMEOUT_SECONDS = 15
USER_AGENT = "zuno-rag-ingestion-catalog-verify/1.0"


def load_redhat_sources(values_path: pathlib.Path) -> List[Dict[str, Any]]:
    with values_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("redhat", [])


def classify_url(url: str, session: Any) -> Tuple[str, str]:
    """Returns (status, detail), status in {"OK", "REDIRECT", "FAIL"}.

    HEAD first (cheap); falls back to GET when the server rejects HEAD
    (405/501 - some docs.redhat.com paths do). `allow_redirects=True`
    means `response.url` is already the final URL after every hop, so a
    mismatch against the requested `url` is exactly "this entry's
    documentationUrl should be updated" - the REDIRECT(final-url) case.
    """
    # Only HEAD's 405/501 triggers the GET fallback; GET's own result (on
    # either the first try or the fallback) always returns directly below -
    # there is no third method to fall back to.
    for method in ("HEAD", "GET"):
        try:
            resp = session.request(
                method, url, timeout=TIMEOUT_SECONDS, allow_redirects=True, headers={"User-Agent": USER_AGENT}
            )
        except requests.RequestException as exc:
            return "FAIL", f"{type(exc).__name__}: {exc}"
        if resp.status_code in (405, 501) and method == "HEAD":
            continue
        if 200 <= resp.status_code < 300:
            if resp.url != url:
                return "REDIRECT", resp.url
            return "OK", str(resp.status_code)
        return "FAIL", f"HTTP {resp.status_code}"
    raise AssertionError("unreachable: the loop above always returns on its GET iteration")


def verify(values_path: pathlib.Path) -> List[Dict[str, str]]:
    sources = load_redhat_sources(values_path)
    session = requests.Session()
    results: List[Dict[str, str]] = []
    for source in sources:
        if not source.get("enabled", True):
            continue
        url = source.get("documentationUrl", "")
        if not url:
            continue
        status, detail = classify_url(url, session)
        results.append(
            {
                "product": source.get("product", ""),
                "version": source.get("version", ""),
                "url": url,
                "status": status,
                "detail": detail,
            }
        )
    return results


def format_report(results: List[Dict[str, str]]) -> str:
    lines = [
        f"{r['status']:<9} product={r['product']!r} version={r['version']!r} url={r['url']} detail={r['detail']}"
        for r in results
    ]
    ok = sum(1 for r in results if r["status"] == "OK")
    redirect = sum(1 for r in results if r["status"] == "REDIRECT")
    fail = sum(1 for r in results if r["status"] == "FAIL")
    lines.append("")
    lines.append(f"Summary: {ok} OK, {redirect} REDIRECT, {fail} FAIL, {len(results)} total")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--values",
        type=pathlib.Path,
        default=DEFAULT_VALUES_PATH,
        help="path to gitops/charts/rag-ingestion/values.yaml (default: repo-relative)",
    )
    args = parser.parse_args()

    if not args.values.exists():
        print(f"values file not found: {args.values}", file=sys.stderr)
        return 2

    results = verify(args.values)
    print(format_report(results))
    return 1 if any(r["status"] == "FAIL" for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
