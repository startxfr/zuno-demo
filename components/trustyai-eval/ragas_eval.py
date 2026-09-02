#!/usr/bin/env python3
"""ADR-0534/WP-109: RAGAS evaluation against the REAL rag-service.

For each configured question this script:
  1. calls rag-service's /v1/search (the live pgvector retrieval path -
     the same endpoint Agent Runtime's retrieve node uses), keeping the
     actually-retrieved contexts;
  2. generates an answer from those contexts with the in-cluster judge
     model (plain http through the mesh - the sidecar originates TLS, see
     the lmevaljob-mesh-double-tls finding);
  3. scores the (question, contexts, answer) triple with RAGAS's
     LLM-judged metrics: faithfulness (is the answer grounded in the
     retrieved contexts?) and context precision (were the retrieved
     contexts relevant to the question?). Both are LLM-only metrics, so
     no separate embeddings endpoint is needed.

Output: a JSON report on stdout and at REPORT_PATH. Observe-only by
design - the report carries scores, not verdicts; thresholds and pass/
fail policy are explicitly deferred by ADR-0534's Non-goals.

Env (all have working in-cluster defaults):
  RAG_SERVICE_URL   default http://rag-service.zuno-data.svc:8080
  JUDGE_BASE_URL    default http://qwen36-27b-instruct-kserve-workload-svc.zuno-ai-run.svc:8000/v1
  JUDGE_MODEL       default qwen3.6-27b-instruct
  CALLER_GROUPS     comma-separated, default "consultant" - rag-service
                    fails closed on empty groups (ADR-0046), so retrieval
                    quality must be measured with a realistic caller
  QUESTIONS         "||"-separated override of the built-in question set
  TOP_K             default 4
  REPORT_PATH       default /tmp/ragas-report.json
"""
from __future__ import annotations

import json
import os
import sys

import httpx

RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://rag-service.zuno-data.svc:8080")
JUDGE_BASE_URL = os.getenv(
    "JUDGE_BASE_URL",
    "http://qwen36-27b-instruct-kserve-workload-svc.zuno-ai-run.svc:8000/v1",
)
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "qwen3.6-27b-instruct")
CALLER_GROUPS = [g for g in os.getenv("CALLER_GROUPS", "consultant").split(",") if g]
TOP_K = int(os.getenv("TOP_K", "4"))
REPORT_PATH = os.getenv("REPORT_PATH", "/tmp/ragas-report.json")

# Real questions against the real corpus (French Confluence/tech content -
# see the real-confluence-content-for-tests note: queries must match the
# actual indexed material, not invented topics).
DEFAULT_QUESTIONS = [
    "Comment configurer un cluster OpenShift ?",
    "Quelles sont les bonnes pratiques de sauvegarde PostgreSQL ?",
    "Comment fonctionne l'authentification Keycloak ?",
]
QUESTIONS = [q for q in os.getenv("QUESTIONS", "").split("||") if q.strip()] or DEFAULT_QUESTIONS


def retrieve(client: httpx.Client, question: str) -> list[str]:
    resp = client.post(
        f"{RAG_SERVICE_URL}/v1/search",
        json={"query": question, "top_k": TOP_K, "caller_groups": CALLER_GROUPS},
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return [r.get("content") or r.get("text") or "" for r in results]


def answer(client: httpx.Client, question: str, contexts: list[str]) -> str:
    prompt = (
        "Réponds à la question en te basant UNIQUEMENT sur le contexte fourni.\n\n"
        "Contexte:\n" + "\n---\n".join(contexts) + f"\n\nQuestion: {question}\nRéponse:"
    )
    resp = client.post(
        f"{JUDGE_BASE_URL}/chat/completions",
        json={"model": JUDGE_MODEL, "max_tokens": 400,
              "messages": [{"role": "user", "content": prompt}]},
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def main() -> int:
    # Imported here so a pure-connectivity failure is reported before the
    # heavyweight ragas import machinery ever loads.
    with httpx.Client(timeout=120) as client:
        samples = []
        for q in QUESTIONS:
            contexts = retrieve(client, q)
            if not contexts:
                print(f"WARNING: no contexts retrieved for {q!r} - skipping")
                continue
            a = answer(client, q, contexts)
            samples.append({"question": q, "contexts": contexts, "answer": a})
            print(f"retrieved {len(contexts)} contexts + answered: {q!r}")

    if not samples:
        print("ERROR: no sample could be built - rag-service returned nothing "
              "for every question; check the corpus and CALLER_GROUPS")
        return 1

    from langchain_openai import ChatOpenAI
    from ragas import EvaluationDataset, SingleTurnSample, evaluate
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness, LLMContextPrecisionWithoutReference

    judge = LangchainLLMWrapper(ChatOpenAI(
        base_url=JUDGE_BASE_URL, api_key="in-cluster-unused",
        model=JUDGE_MODEL, temperature=0.0, timeout=180,
    ))
    dataset = EvaluationDataset(samples=[
        SingleTurnSample(user_input=s["question"],
                         retrieved_contexts=s["contexts"],
                         response=s["answer"])
        for s in samples
    ])
    result = evaluate(dataset=dataset,
                      metrics=[Faithfulness(llm=judge),
                               LLMContextPrecisionWithoutReference(llm=judge)])

    scores = result.to_pandas().to_dict(orient="records")
    report = {
        "framework": "ragas",
        "judge_model": JUDGE_MODEL,
        "caller_groups": CALLER_GROUPS,
        "samples": [
            {"question": s["question"], "n_contexts": len(s["contexts"]),
             "scores": {k: v for k, v in row.items()
                        if isinstance(v, (int, float))}}
            for s, row in zip(samples, scores)
        ],
    }
    out = json.dumps(report, indent=2, ensure_ascii=False)
    print(out)
    with open(REPORT_PATH, "w") as f:
        f.write(out + "\n")
    print(f"ragas report written to {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
