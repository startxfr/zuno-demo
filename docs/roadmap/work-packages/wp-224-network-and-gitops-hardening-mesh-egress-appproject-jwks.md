# WP-224: Network and GitOps hardening: mesh, egress, AppProject, JWKS (delivers ADR-0602, ADR-0603)

- **State:** Repo work in review (2026-11-07): reviewed read-only, fixes applied; push pending the user's go. The code is complete in the worktree `zuno-demo-wp224` (branch
  `wp-224-network-gitops`). A live rehearsal on demo333 is under way: the mesh and egress objects are applied by hand,
  outside ArgoCD, one step at a time, each with the user's go. Nothing is pushed.
- **ADRs:** ADR-0602, ADR-0603
- **Depends on:** WP-222, WP-223 (the AppProjects whitelist no `ClusterSecretStore`, so WP-223 must be rolled out
  first)
- **Blocks:** WP-227
- **Estimated files touched:** ~150 (106 Application `project:` lines)

> Execute this brief as a standalone task from the repository root. Every cluster action needs the user's go.

## Goal

Reduce real risk at a reasonable cost:
- Stop plaintext calls to the namespaces that hold secrets and identities (C3).
- Close the internet egress of the namespaces that run agent content (exfiltration by a prompt-injected agent).
- Bound what an ArgoCD Application may declare (C4).
- Validate tokens against Keycloak over HTTPS only (C6).

## ADR references

ADR-0602 clauses 4 to 6; ADR-0603 M1, M4.

## Decisions taken with the user (2026-11-06)

| Point | Decision | Not adopted (why) |
|---|---|---|
| mTLS | Targeted STRICT per namespace on zuno-data, zuno-auth and zuno-ai-run, with justified port exceptions | Mesh-wide STRICT: the router, webhooks, vLLM TLS, monitoring and the unmeshed callers would break. Fine `AuthorizationPolicy`: cost of mapping every flow. Meshing UnifAI and the experiences: large effort. |
| Egress | EgressFirewall deny-all plus allowlist in zuno-ai-run and zuno-unifai | Istio egress gateway and in-cluster egress NetworkPolicy: nice-to-have. |
| ArgoCD | Three projects: `zuno-platform`, `zuno-apps` and `zuno-bootstrap` | A `zuno-rbac` project: a ClusterRoleBinding stays an escalation path anyway. Removing the controller's cluster-admin: too much breakage risk for now. |
| JWKS | The public HTTPS Route (Let's Encrypt) for Authorino and the RAGAS token; the gateways keep the in-cluster Service, mTLS under STRICT (revised 2026-11-07) | Keycloak on internal 8443: too much operator and client work. |
| ExternalSecret creation by ocp-ai-dev/ops | Accepted: since WP-223, the blast radius is the namespace's own keys | |
| Validation | Hand-applied rehearsal on demo333 (PERMISSIVE, observe, STRICT per namespace, then the firewalls) | A push now would also roll out WP-222/223 (Vault migration not done). |

## Repo changes

1. **Mesh.**
   - `gitops/charts/namespaces/templates/peerauthentication-namespace.yaml` renders a namespace-wide `default` policy,
     whose mode is one value per namespace. It also renders one workload-scoped PERMISSIVE policy per exception,
     annotated with `zuno.io/permissive-reason`.
   - The 11 exceptions:

     | Namespace | Workload | Port(s) | Unmeshed caller |
     |---|---|---|---|
     | zuno-auth | Keycloak | 8080 | router (edge Route) and zuno-aap |
     | zuno-auth | Redis | 9121 | monitoring |
     | zuno-data | Postgres instances | 9187 | the PodMonitor exporter |
     | zuno-data | Postgres instances | 8008 | Patroni members over the headless Service |
     | zuno-ai-run | ai-, mcp- and a2a-gateway | 8080 | UnifAI, the experiences, playground, Lightspeed |
     | zuno-ai-run | vLLM | 8000 | its own TLS |
     | zuno-ai-run | EPP | 9090 | monitoring |
     | zuno-ai-run | embeddings | 8080 | UnifAI and monitoring |
     | zuno-ai-run | guardrails | 8000 | router |
     | zuno-ai-run | guardrails-smoke | 8080 | router and monitoring |
     | zuno-ai-run | evalhub | 8443 / 8081 | router and monitoring |
2. **Egress.**
   - `namespaces/templates/egressfirewall-namespace.yaml` covers zuno-ai-run: the five LLM providers, Confluence,
     GitHub/GitLab, S3, the API server on 6443, and the Keycloak and UnifAI Routes. Salesforce is added only when it is
     enabled.
   - `unifai/templates/egressfirewall.yaml` covers zuno-unifai: Confluence, docs.redhat.com and the other RAG sources,
     S3, Keycloak, the identity Route and the API server.
   - Both end with `Deny 0.0.0.0/0`, and the render fails on an empty list.
   - Residuals: the Keycloak dnsName resolves to the shared load balancer, so it opens every `*.apps` Route; DNS
     tunnelling; CDNs with shared IPs.
3. **ArgoCD.**
   - New AppProjects under `ansible/roles/argocd/kustomize/appproject/`:
     - `zuno-platform`: 61 Applications, 30 cluster kinds, no `*`.
     - `zuno-apps`: 45 Applications, no cluster kind, `operators.coreos.com` and `argoproj.io` blacklisted.
     - `zuno-bootstrap`: the root app-of-apps only.
   - 22 Applications were retargeted off `openshift-gitops`.
   - The repo secret is now global (`project: ""`).
   - RBAC for `role:zuno-paas-dev` covers both projects.
   - The legacy `zuno` project is deleted by the role once no live Application names it.
4. **Keycloak over HTTPS.**
   - The connectivity-link AuthPolicy uses `issuerUrl https://keycloak.<domain>/realms/zuno` and requires `aud` to
     include `zuno-admin-api`. It renders only when `keycloakAcmeWildcardTLS` is true.
   - The gateways' `keycloakJwksUrl` stays the in-cluster Service, now mTLS under STRICT (user decision after the
     review); empty means the issuer's `/protocol/openid-connect/certs` for an external Keycloak.
   - The RAGAS Job mints its token at the HTTPS endpoint. This removes the `iss=http` trap.
5. **Checks.**
   - `platform/security/check_mesh_mtls.py` (21 tests) and `platform/gitops/check_app_projects.py` (19 tests), both
     wired into `lint.yml`.
   - `platform/gitops/cluster-scoped-kinds.yaml` comes from live API discovery.

## Verification (repo, 2026-11-07)

- These checks all pass: `check_mesh_mtls` (473 checks), `check_app_projects` (106 Applications),
  `check_secret_access`, `check_workload_hardening` and `check_docs`.
- pytest on `platform/security`, `gitops`, `vault` and `keycloak`: 83 passed.
- `helm lint` and `helm template` pass on the touched charts.

## Live rehearsal (demo333)

Manifests and commands are in a bundle outside the repository, rendered from this branch. Results are in
[the evidence file](../evidence/wp-224-live-rehearsal-2026-11-07.md).

## Rollout (after the user's go and the push; WP-222/223 are live since 2026-11-07)

Every live Application tracks `devel` with automated sync, so a push puts the chart changes live at once, under the
old Application specs. That is why the branch renders exactly the live state: zero diff on the 15 PeerAuthentications
(STRICT) and on the zuno-ai-run firewall, except for the 9 Hugging Face hosts that zuno-demo-96 added by hand for the
WP-115 EvalHub run (temporary, deliberately not in git, to be removed by that session). The zuno-unifai firewall stays
off (`egress.enabled: false`, reason recorded) until its own rehearsal.

1. Push to devel. Watch zuno-namespaces-d1, the three gateways and trustyai-config. The RAGAS Job is not rendered
   while the Application still passes the placeholder domain.
2. After the gateways roll: one real token call through ai-, mcp- and a2a-gateway; no "Unable to validate JWT" in the logs.
3. Run the argocd role FIRST: it creates the three projects, makes the repo secret global, moves every live
   Application still in `zuno` to the project and destination its file declares, and keeps the legacy project until
   no Application names it. `role:zuno-paas-dev` keeps `zuno/*` until then.
4. Re-apply the roles one at a time, namespaces and trustyai_config first; check Synced/Healthy and no "not permitted".
5. Re-run the argocd role: it deletes the legacy project. Then drop `appproject.yaml` from the kustomization and fix
   `platform/templates/agent/scaffold_agent.py` in zuno-demo-agents (it still emits `project: zuno`, lines 380 and 416).
6. With the user's go, in a canary window: enable the zuno-unifai firewall and exercise every restart path
   (Deployments, CronJobs, ingestion), including googleapis, the search API and docling model downloads.
7. Set the GitHub settings on `main`: secret scanning with push protection, a ruleset against force-push and
   deletion, and the required checks.

Decision (user, 2026-11-07, after the review): the gateways keep the in-cluster JWKS URL
(`http://zuno-service.zuno-auth.svc:8080/...`). They are meshed and zuno-auth is STRICT, so the hop is mTLS, and gateway
auth does not depend on the public load balancer and the router hairpin. The issuer stays HTTPS (compared with `iss`
only); Authorino and the RAGAS token still use the public HTTPS endpoint.

## Not done here

- The ArgoCD controller keeps its `cluster-admin` binding.
- The plain-HTTP chart repository stays in `sourceRepos`.
- No fine-grained `AuthorizationPolicy`. UnifAI and the experiences are not meshed, so the gateways stay PERMISSIVE
  on 8080.
