# api

Thin, single-scope path for `make configure api`: re-applies
`gitops/apps/api` (→ `gitops/charts/tekos`, ADR-0008) without touching the
agent namespaces. Useful for redeploying just the Tekos frontend/BFF after a
change, without a full `make install` pass. The five-namespace Application
(`gitops/apps/agents`) and the full install/check flow live in
`ansible/roles/agents`.
