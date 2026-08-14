# Knowledge backend bindings (ADR-0204)

`bindings.yaml` is the platform backend-binding registry for RAG: it
resolves a logical knowledge domain (`knowledge.<name>`, the stable
contract OKF tasks and `policies/knowledge/knowledge-policy.yaml`
reference) to the physical PostgreSQL database that serves it.

Rules (mirroring `platform/bindings/tools/README.md`'s ADR-0116 rules,
applied to knowledge domains instead of tool capabilities):

- Bindings are **platform-controlled configuration** - never supplied by an
  agent, task or caller. OKF bundles and the knowledge policy contain
  logical domain IDs only; database names, schemas and credential
  references live here.
- Agent Runtime authorizes (`app/knowledge.py`'s `evaluate_knowledge()`,
  the full ADR-0203 intersection) **before** rag-service resolves or
  queries a binding.
- Unknown domains and missing bindings **fail closed**: a requested
  domain with no live pool fails the whole query (no silent partial
  results), and is never silently substituted with another domain's
  data.
- Changing the physical database behind a domain is a change to this file
  (plus deployment config) only - agent definitions and policy stay
  untouched (ADR-0204's core property).

The file ships inside the rag-service image (repo-root build context, see
`components/rag-service/Dockerfile`) and is loaded by
`components/rag-service/app/bindings.py`'s `KnowledgeBindingRegistry` at
startup.
