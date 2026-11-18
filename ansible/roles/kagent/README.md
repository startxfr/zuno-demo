# kagent

Day 2 component `kagent`: kagent, the Kubernetes-native agent operator, admitted as a thin operations
experience client over the governed chain (ADR-0600, under ADR-0587's admission contract, reaching the
gateways through the token proxy of ADR-0601).

- `make d2 install kagent` seeds Vault (`keycloak/kagent`, `kagent/app`; `kagent/postgresql-app` comes from
  the vault role), gives the `kagent` Keycloak service account the groups listed in `kagent_groups` (default `ocp-ai-ops` only,
  S5 hardening; they must be groups of its persona `ai-ops-01`, and any other group is removed; realm users are create-only), applies three Applications (`zuno-kagent-d0` CRDs, `zuno-token-proxy-kagent-d1`,
  `zuno-kagent-d1`) and waits for the Deployments.
- `make d2 check kagent` compares the running images with the pinned digests, checks that the controller
  discovered the governed tools and accepted the declarative agent `zuno-sre`, and that the Route answers
  only through the front door.
- The chart (`gitops/charts/kagent`) switches off every bundled provider, tool server, sample agent and the
  bundled PostgreSQL; the controller has namespaced Roles only (`watchNamespaces`). Its one ModelConfig and one
  RemoteMCPServer point at the token proxy.
- Prerequisite order: `make d0 install vault` (seeds `kagent/postgresql-app`) and `make d0 install postgresql`
  (creates the role and database and replays the grants) before the first install.
- Uninstall removes the Applications; the Keycloak client, the Vault paths and the database are kept.
