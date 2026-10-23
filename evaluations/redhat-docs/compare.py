#!/usr/bin/env python3
"""Compare the Red Hat documentation search of rag-service and UnifAI on a fixed question set (WP-168).

For each question of questions.yaml, query both engines as a persona and report whether the expected
books are among the top-k sources, with the best score and the first source of each. The two engines'
scores are not on one scale (rag-service: similarity; UnifAI hybrid: reciprocal-rank fusion), so the
comparison is on hits, not scores.

    RAG_SERVICE_URL=http://localhost:18080 UNIFAI_RAG_URL=http://localhost:13456 \
    KEYCLOAK_URL=https://keycloak.apps.<domain> EVAL_CLIENT_SECRET=... DEMO_PERSONA_PASSWORD=... \
    python3 compare.py [--persona consultant-02] [--top-k 5] [--engines rag-service,unifai]

rag-service and UnifAI are usually reached through `oc port-forward` from the workstation.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx
import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
from unifai_target import login_name  # noqa: E402

KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "")
REALM = os.environ.get("KEYCLOAK_REALM", "zuno")
RAG_SERVICE_URL = os.environ.get("RAG_SERVICE_URL", "http://localhost:18080")
UNIFAI_RAG_URL = os.environ.get("UNIFAI_RAG_URL", "http://localhost:13456")
SOURCE_TYPES = [t for t in os.environ.get("UNIFAI_SOURCE_TYPES", "WEB").split(",") if t]


def token(persona: str) -> str:
    resp = httpx.post(
        f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token",
        data={"grant_type": "password", "client_id": os.environ.get("EVAL_CLIENT_ID", "zuno-evaluations"),
              "client_secret": os.environ["EVAL_CLIENT_SECRET"], "username": login_name(persona),
              "password": os.environ["DEMO_PERSONA_PASSWORD"], "scope": "openid"}, timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]


def search_rag_service(query: str, top_k: int) -> list[dict]:
    resp = httpx.post(f"{RAG_SERVICE_URL}/v1/search", timeout=60,
                      json={"query": query, "top_k": top_k, "domains": ["knowledge.tech"], "caller_groups": []})
    resp.raise_for_status()
    return [{"source": r.get("source", ""), "score": float(r.get("score") or 0)} for r in resp.json().get("results", [])]


def search_unifai(query: str, top_k: int, bearer: str) -> list[dict]:
    rows: list[dict] = []
    for source_type in SOURCE_TYPES:
        resp = httpx.get(f"{UNIFAI_RAG_URL}/api/sources/query.bearer", timeout=60,
                         params={"query": query, "sourceType": source_type, "tags": "knowledge.tech",
                                 "top_k_results": top_k},
                         headers={"Authorization": f"Bearer {bearer}"})
        resp.raise_for_status()
        for m in resp.json().get("matches", []):
            meta = m.get("metadata") or {}
            rows.append({"source": meta.get("url") or meta.get("path") or "", "score": float(m.get("score") or 0)})
    return sorted(rows, key=lambda r: -r["score"])[:top_k]


def hit(rows: list[dict], expect: list[str]) -> int | None:
    """1-based rank of the first expected source, else None."""
    for rank, row in enumerate(rows, 1):
        if any(fragment in row["source"] for fragment in expect):
            return rank
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--persona", default="consultant-02")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--engines", default="rag-service,unifai")
    parser.add_argument("--json", action="store_true", help="print the raw results as JSON")
    args = parser.parse_args()
    engines = args.engines.split(",")
    questions = yaml.safe_load((HERE / "questions.yaml").read_text())
    bearer = token(args.persona) if "unifai" in engines else ""
    report = []
    for q in questions:
        row = {"id": q["id"], "query": q["query"]}
        for engine in engines:
            rows = (search_rag_service(q["query"], args.top_k) if engine == "rag-service"
                    else search_unifai(q["query"], args.top_k, bearer))
            row[engine] = {"rank": hit(rows, q["expect"]), "top": rows[0]["source"] if rows else None,
                           "best_score": rows[0]["score"] if rows else None, "results": len(rows)}
        report.append(row)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{'id':>3}  " + "  ".join(f"{e:>12}" for e in engines) + "  query")
        for r in report:
            print(f"{r['id']:>3}  " + "  ".join(f"{('rank ' + str(r[e]['rank'])) if r[e]['rank'] else 'MISS':>12}" for e in engines)
                  + f"  {r['query'][:70]}")
        for e in engines:
            hits = sum(1 for r in report if r[e]["rank"])
            print(f"{e}: {hits}/{len(report)} questions with an expected book in the top {args.top_k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
