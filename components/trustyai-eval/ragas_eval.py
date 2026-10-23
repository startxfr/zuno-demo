#!/usr/bin/env python3
"""ADR-0534/WP-109: RAGAS evaluation against the REAL retrieval path.

WP-156: that path is UnifAI's RAG server, the corpus the UnifAI agents
answer from. Retrieval goes through its bearer endpoint as a real demo
persona: the Job signs in through the `zuno-evaluations` Keycloak client
(password grant) and UnifAI applies the persona's own group ACL.

For each configured question this script:
  1. calls UnifAI's GET /api/sources/query.bearer over the knowledge.tech
     sources, keeping the actually-retrieved contexts;
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
  UNIFAI_RAG_URL    default http://unifai-rag-server.zuno-unifai.svc:13456
  UNIFAI_RAG_TAG    default knowledge.tech
  KEYCLOAK_TOKEN_URL
                    default the in-cluster Keycloak Service's zuno realm
                    token endpoint (the issuer stays the public https one,
                    see persona_token())
  EVAL_CLIENT_ID    default zuno-evaluations
  EVAL_CLIENT_SECRET  required, the client's secret
  EVAL_PERSONA      default consultant-01 - retrieval quality must be
                    measured as a realistic caller, not an entitlement-less
                    one that only ever sees ACL-unrestricted documents
  DEMO_PERSONA_PASSWORD  required, the demo personas' shared password
  JUDGE_BASE_URL    default http://qwen36-27b-instruct-kserve-workload-svc.zuno-ai-run.svc:8000/v1
  JUDGE_MODEL       default qwen3.6-27b-instruct
  QUESTIONS         "||"-separated override of the built-in question set
  TOP_K             default 4
  REPORT_PATH       default /tmp/ragas-report.json
  OTEL_EXPORTER_OTLP_ENDPOINT
                    default the shared zuno-monitoring collector; scores
                    are pushed as one-shot OTLP gauges (WP-113) so the
                    zuno-trustyai Grafana dashboard can render them -
                    best-effort, a push failure never fails the run
"""
from __future__ import annotations

import json
import os
import sys
import time

import httpx

UNIFAI_RAG_URL = os.getenv("UNIFAI_RAG_URL", "http://unifai-rag-server.zuno-unifai.svc:13456")
UNIFAI_RAG_TAG = os.getenv("UNIFAI_RAG_TAG", "knowledge.tech")
KEYCLOAK_TOKEN_URL = os.getenv(
    "KEYCLOAK_TOKEN_URL",
    "http://zuno-service.zuno-auth.svc:8080/realms/zuno/protocol/openid-connect/token",
)
EVAL_CLIENT_ID = os.getenv("EVAL_CLIENT_ID", "zuno-evaluations")
EVAL_CLIENT_SECRET = os.getenv("EVAL_CLIENT_SECRET", "")
EVAL_PERSONA = os.getenv("EVAL_PERSONA", "consultant-01")
DEMO_PERSONA_PASSWORD = os.getenv("DEMO_PERSONA_PASSWORD", "")
JUDGE_BASE_URL = os.getenv(
    "JUDGE_BASE_URL",
    "http://qwen36-27b-instruct-kserve-workload-svc.zuno-ai-run.svc:8000/v1",
)
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "qwen3.6-27b-instruct")
TOP_K = int(os.getenv("TOP_K", "4"))
REPORT_PATH = os.getenv("REPORT_PATH", "/tmp/ragas-report.json")

# Real questions against the real corpus (French Confluence/tech content -
# see the real-confluence-content-for-tests note: queries must match the
# actual indexed material, not invented topics). WP-156: UnifAI's
# knowledge.tech sources are the OpenShift and Satellite spaces, so the
# questions follow them; the PostgreSQL one only ever retrieved off-topic
# pages there.
DEFAULT_QUESTIONS = [
    "Comment configurer un cluster OpenShift ?",
    "Comment planifier les évolutions d'un Satellite ?",
    "Comment simuler la charge d'une mise à jour mineure Satellite ?",
]
QUESTIONS = [q for q in os.getenv("QUESTIONS", "").split("||") if q.strip()] or DEFAULT_QUESTIONS

OTEL_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "http://zuno-otel-collector-collector.zuno-monitoring.svc:4318",
)


def push_gauges_otlp(gauge_name: str, points: list[tuple[float, dict[str, str]]]) -> None:
    """WP-113: one-shot OTLP/HTTP JSON gauge push to the shared collector,
    hand-rolled because this image carries no OTel SDK. Best-effort by
    contract: a push failure logs and returns - it never fails the eval.
    The collector's prometheus exporter re-exposes the gauge (dots become
    underscores: zuno.ragas_score -> zuno_ragas_score) for the scrape
    window; dashboards read it back with last_over_time()."""
    now = str(time.time_ns())
    body = {"resourceMetrics": [{
        "resource": {"attributes": [
            {"key": "service.name", "value": {"stringValue": "trustyai-eval"}},
        ]},
        "scopeMetrics": [{
            "scope": {"name": "trustyai-eval"},
            "metrics": [{
                "name": gauge_name,
                "gauge": {"dataPoints": [
                    {"timeUnixNano": now, "asDouble": float(value),
                     "attributes": [{"key": k, "value": {"stringValue": str(v)}}
                                    for k, v in attrs.items()]}
                    for value, attrs in points
                ]},
            }],
        }],
    }]}
    try:
        resp = httpx.post(f"{OTEL_ENDPOINT}/v1/metrics", json=body, timeout=10)
        resp.raise_for_status()
        print(f"pushed {len(points)} {gauge_name} gauge points to {OTEL_ENDPOINT}")
    except Exception as exc:  # noqa: BLE001 - observe-only, never fail the run
        print(f"WARNING: OTLP metric push failed (run unaffected): {exc}")


def persona_token(client: httpx.Client) -> str:
    """A fresh access token for EVAL_PERSONA. Fetched per question: a run
    outlives Keycloak's short access-token lifespan.

    X-Forwarded-Proto: Keycloak takes the issuer's scheme from the request,
    so a token fetched over the in-cluster http Service carries
    iss=http://<public host>/realms/zuno, which UnifAI rejects (401, live
    2026-10-23). The header makes it the public https issuer."""
    resp = client.post(
        KEYCLOAK_TOKEN_URL,
        headers={"X-Forwarded-Proto": "https"},
        data={
            "grant_type": "password",
            "client_id": EVAL_CLIENT_ID,
            "client_secret": EVAL_CLIENT_SECRET,
            "username": EVAL_PERSONA,
            "password": DEMO_PERSONA_PASSWORD,
        },
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def retrieve(client: httpx.Client, question: str) -> list[str]:
    resp = client.get(
        f"{UNIFAI_RAG_URL}/api/sources/query.bearer",
        params={
            "query": question,
            "sourceType": "CONFLUENCE",
            "tags": UNIFAI_RAG_TAG,
            "top_k_results": TOP_K,
        },
        headers={"Authorization": f"Bearer {persona_token(client)}"},
    )
    resp.raise_for_status()
    matches = resp.json().get("matches", [])
    # The chunk text is `content`, the page title `metadata.title`. Wrong
    # field names here once made every context "" and every ragas score
    # NaN (live-diagnosed 2026-09-02 on the rag-service shape).
    contexts = [
        f"{(m.get('metadata') or {}).get('title', '')}\n{m.get('content', '')}".strip()
        for m in matches
    ]
    return [c for c in contexts if c]


def answer(client: httpx.Client, question: str, contexts: list[str]) -> str:
    prompt = (
        "Réponds à la question en te basant UNIQUEMENT sur le contexte fourni.\n\n"
        "Contexte:\n" + "\n---\n".join(contexts) + f"\n\nQuestion: {question}\nRéponse:"
    )
    resp = client.post(
        f"{JUDGE_BASE_URL}/chat/completions",
        json={"model": JUDGE_MODEL, "max_tokens": 600,
              # qwen3.6 is a thinking model: without this it spends the
              # whole token budget reasoning and returns content=None
              # (2 of 3 questions on the first scored run). vLLM ignores
              # the kwarg harmlessly if a template has no such switch.
              "chat_template_kwargs": {"enable_thinking": False},
              "messages": [{"role": "user", "content": prompt}]},
    )
    resp.raise_for_status()
    msg = resp.json()["choices"][0]["message"]
    # qwen can return content=None (e.g. all budget spent on reasoning) -
    # live-diagnosed 2026-09-02: a None response silently DROPS the
    # 'response' feature from the ragas dataset, and validation then fails
    # with "requires ['response']" - the misleading error the first two
    # runs died on. Fall back to reasoning_content, else empty (the caller
    # skips empty answers).
    return msg.get("content") or msg.get("reasoning_content") or ""


def main() -> int:
    if not EVAL_CLIENT_SECRET or not DEMO_PERSONA_PASSWORD:
        print("ERROR: EVAL_CLIENT_SECRET and DEMO_PERSONA_PASSWORD are required "
              "to sign in as the evaluation persona")
        return 1
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
            if not a.strip():
                print(f"WARNING: judge produced no answer text for {q!r} - skipping")
                continue
            samples.append({"question": q, "contexts": contexts, "answer": a})
            print(f"retrieved {len(contexts)} contexts + answered: {q!r}")

    if not samples:
        print("ERROR: no sample could be built - UnifAI RAG returned nothing "
              f"for every question; check the {UNIFAI_RAG_TAG} sources and "
              f"{EVAL_PERSONA}'s groups")
        return 1

    from langchain_openai import ChatOpenAI
    from ragas import EvaluationDataset, SingleTurnSample, evaluate
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness, LLMContextPrecisionWithoutReference

    from ragas.run_config import RunConfig

    judge = LangchainLLMWrapper(ChatOpenAI(
        base_url=JUDGE_BASE_URL, api_key="in-cluster-unused",
        model=JUDGE_MODEL, temperature=0.0, timeout=300,
        # Same thinking-mode switch as answer(): judged verdicts must be
        # emitted as content within the timeout, not silently spent on
        # reasoning (the TimeoutError -> NaN failure of the first scored
        # run, 2026-09-02).
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    ))
    # Native v2 sample API. An earlier "requires ['response']" validation
    # failure blamed on this path was actually data: a None answer (see
    # answer()'s comment) drops the response feature entirely. With real
    # strings this path validates and runs - proven in-image 2026-09-02.
    dataset = EvaluationDataset(samples=[
        SingleTurnSample(user_input=s["question"],
                         retrieved_contexts=s["contexts"],
                         response=s["answer"])
        for s in samples
    ])
    result = evaluate(dataset=dataset,
                      metrics=[Faithfulness(llm=judge),
                               LLMContextPrecisionWithoutReference(llm=judge)],
                      # Generous per-call budget, low parallelism: one
                      # shared-GPU judge, not an API fleet.
                      run_config=RunConfig(timeout=600, max_workers=2))

    scores = result.to_pandas().to_dict(orient="records")
    report = {
        "framework": "ragas",
        "judge_model": JUDGE_MODEL,
        "persona": EVAL_PERSONA,
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

    # WP-113: surface the same scores on the zuno-trustyai Grafana
    # dashboard. Labels stay bounded: the metric name vocabulary is
    # ragas's own, and questions come from the small configured set.
    points = [
        (score, {"metric": metric_name, "question": s["question"][:80]})
        for s, row in zip(samples, scores)
        for metric_name, score in row.items()
        if isinstance(score, (int, float)) and score == score  # drop NaN
    ]
    if points:
        push_gauges_otlp("zuno.ragas_score", points)
    return 0


if __name__ == "__main__":
    sys.exit(main())
