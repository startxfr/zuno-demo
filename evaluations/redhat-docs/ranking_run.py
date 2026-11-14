#!/usr/bin/env python3
"""Run ranking.yaml against UnifAI's query.bearer and write the hit@1 / hit@5 / MRR figures (WP-186, R-530).

Same method as the README's "Ranking set" section: each entry is queried with its own `sourceType` and `tags`,
`top_k_results` fixed (compare only at the same top_k), as a member of agent_tekos. The result file has the shape of
`results/ranking-fr-2026-11-03.json`, with an extra `en21` block (the 24 English entries minus the 3 `expect_none`).

    oc -n zuno-unifai port-forward svc/unifai-rag-server 13456:13456 &
    KEYCLOAK_URL=https://keycloak.apps.<domain> EVAL_CLIENT_SECRET=... DEMO_PERSONA_PASSWORD=... \
    python3 ranking_run.py --persona eval-consultant-01 --top-k 10 --out results/ranking-<name>-<date>.json

Read only: it sends search queries and writes the result file; the credentials come from the environment.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compare  # noqa: E402  (reuses token(), hit() and the UNIFAI_RAG_URL setting)

import httpx  # noqa: E402


def query(entry: dict, top_k: int, bearer: str) -> list[dict]:
    resp = httpx.get(f"{compare.UNIFAI_RAG_URL}/api/sources/query.bearer", timeout=60,
                     params={"query": entry["query"], "sourceType": entry.get("sourceType", "WEB"),
                             "tags": entry.get("tags", "knowledge.tech"), "top_k_results": top_k},
                     headers={"Authorization": f"Bearer {bearer}"})
    resp.raise_for_status()
    rows = []
    for m in resp.json().get("matches", []):
        meta = m.get("metadata") or {}
        rows.append({"source": meta.get("url") or meta.get("path") or "", "score": float(m.get("score") or 0)})
    return sorted(rows, key=lambda r: -r["score"])[:top_k]


def figures(rows: list[dict]) -> dict:
    ranked = [r for r in rows if r["expected"]]
    n = len(ranked) or 1
    return {
        "entries": len(ranked),
        "hit@1": sum(1 for r in ranked if r["rank"] == 1) / n,
        "hit@5": sum(1 for r in ranked if r["rank"] and r["rank"] <= 5) / n,
        "mrr": sum(1 / r["rank"] for r in ranked if r["rank"]) / n,
        "missed": [r["id"] for r in ranked if not r["rank"]],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", default="eval-consultant-01")
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--set", default=str(HERE / "ranking.yaml"))
    ap.add_argument("--label", default="")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    entries = yaml.safe_load(Path(args.set).read_text())
    bearer = compare.token(args.persona)
    rows = []
    for e in entries:
        res = query(e, args.top_k, bearer)
        expected = bool(e.get("expect")) and not e.get("expect_none")
        rank = compare.hit(res, e["expect"]) if expected else None
        rows.append({"id": e["id"], "rank": rank, "expected": expected, "lang": e.get("lang", "en"),
                     "top_score": res[0]["score"] if res else None,
                     "top_url": res[0]["source"] if res else None, "query": e["query"]})
        print(f"{e['id']:>3}  {('rank ' + str(rank)) if rank else ('MISS' if expected else 'none-expected'):>14}  {e['query'][:70]}",
              flush=True)
    fr = [r for r in rows if r["lang"] == "fr"]
    en = [r for r in rows if r["lang"] != "fr"]
    out = {
        "run": __import__("datetime").date.today().isoformat(),
        "set": f"ranking.yaml ({len(en)} English + {len(fr)} French), top_k {args.top_k}, persona {args.persona}, UnifAI query.bearer"
               + (f", {args.label}" if args.label else ""),
        "en21": figures(en),
        "french_subset": figures(fr),
        "all_34": {**figures(rows), "expect_none_top_scores": [r["top_score"] for r in rows if not r["expected"]]},
        "rows": [{k: v for k, v in r.items() if k != "expected"} for r in rows],
    }
    Path(args.out).write_text(json.dumps(out, indent=2) + "\n")
    for name in ("en21", "french_subset", "all_34"):
        f = out[name]
        print(f"{name}: hit@1 {f['hit@1']:.2f}  hit@5 {f['hit@5']:.2f}  MRR {f['mrr']:.2f}  missed {f['missed']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
