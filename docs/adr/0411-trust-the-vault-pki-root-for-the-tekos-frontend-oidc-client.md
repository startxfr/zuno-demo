# ADR-0411: Trust the Vault PKI root in every agent frontend's OIDC client

- **Status:** Implemented
- **Target:** v0.4
- **Date:** 2026-08-18
- **Decision owners:** Zuno Demo architecture team

## Context

`https://tekos.apps.demo222.startx.fr/login` returned HTTP 502 "identity provider unreachable", even though Keycloak itself was healthy and reachable from a browser hitting the same route directly.

Live diagnosis (pod status, logs, `oc get oauth cluster`, NetworkPolicies, istio policy objects) ruled out Keycloak, the network path, and mesh mTLS - none are involved. The actual cause: `components/agent-frontend/internal/oidc/oidc.go`'s `NewClient` built a plain `http.Client` with no custom `Transport`/`TLSClientConfig`. Every outbound call this client makes to Keycloak - `discover()`, `Exchange()`, `Refresh()`, `getJWKS()` - dials `https://keycloak.<cluster-domain>`, whose Route certificate is issued by cert-manager's `vault-issuer` and chains to Vault's internal PKI root (`CN=zuno-demo.internal`, the same root [ADR-0347](0347-trust-the-vault-pki-root-for-the-oauth-openid-idp.md) already trusts for the cluster's own OAuth server). The frontend pod's UBI9-minimal trust store doesn't include that root, so every call failed `x509: certificate signed by unknown authority`. `loginHandler` calls `oidcClient.AuthURL()` -> `discover()`, and on any error returns exactly `http.Error(w, "identity provider unreachable", http.StatusBadGateway)` - the precise symptom reported. The browser doesn't see this because it's a separate TLS client hitting the same route directly, not going through this pod's Go HTTP client.

**Why ADR-0347 and the existing BFF/gateway fix don't already cover this.** `agent-bff`, `ai-gateway`, and `mcp-gateway` (VERIFIED live 2026-08-16) already solved this exact class of TLS bug by adding a `KeycloakJWKSURL` that points at Keycloak's *internal* Service instead of the external Route, keeping `KeycloakIssuerURL` only as the `iss`-claim comparison string. That trick works only because those services exclusively fetch the JWKS server-to-server. `agent-frontend` is different: it is the OIDC Relying Party running the Authorization Code flow. `AuthURL()` and `EndSessionURL()` produce URLs the **browser** redirects to, which must stay the external Route. And per [ADR-0347](0347-trust-the-vault-pki-root-for-the-oauth-openid-idp.md)'s own finding, Keycloak's `hostname.strict: true` means its `.well-known/openid-configuration` document always advertises the external hostname regardless of which route served the discovery request - so pointing discovery at an internal URL would not even yield internal endpoint URLs. The correct fix here is CA trust, not URL substitution - the same conclusion ADR-0347 reached for the cluster's own OAuth server, now extended to this new consumer.

**Scope.** `components/agent-frontend`/`components/agent-bff` are one shared codebase deployed once per agent ([ADR-0008](0008-use-one-frontend-and-one-bff-deployment-per-agent.md)). Six agents currently deploy it: `tekos`, `advantage`, `comage`, `finage` (raw Helm-rendered Deployments, `gitops/charts/<agent>/templates/deployment.yaml`) and `arkos`, `naveo` (rendered by `aiagent-operator` from an `AIAgent` CR, [ADR-0327](0327-define-the-aiagent-crd-reconciliation-contract-before-implementing-the-operator.md)/[ADR-0308](0308-expand-agent-lifecycle-management-through-the-aiagent-operator.md)). All six frontends share the identical root cause, so this decision and its fix cover all six, not just the one reported.

## Decision

Two complementary parts, mirroring ADR-0347's own two-part shape.

**1. Go-level: explicit CA trust in the OIDC client.** `oidc.NewClient` gained an optional `caCertPath` parameter. Empty (the default) leaves TLS verification exactly as it was - zero behavior change for any deployment that doesn't set it. When set, `NewClient` reads the PEM file, appends it to the system cert pool, and installs that pool as the `http.Client`'s `TLSClientConfig.RootCAs` - so `discover()`, `Exchange()`, `Refresh()`, and `getJWKS()` all pick up the trust change from one construction site. `internal/config.Config` gained `KeycloakCACertPath`, sourced from `KEYCLOAK_CA_CERT_PATH`.

**2. Delivery: reuse ADR-0347's CA, sync it into the workload namespace.** `openshift-config/keycloak-serving-ca` (created idempotently by `ansible/roles/openshift_oauth/tasks/install.yml`, self-correcting if `ingress.acmeWildcardTLS` ever flips per [ADR-0211](0211-publicly-trusted-wildcard-tls-via-lets-encrypt-and-route53.md)) is the canonical source - reused verbatim, never re-derived. A new reusable task, `ansible/tasks/sync_keycloak_serving_ca.yml`, copies it into a persistent `zuno-ai-run` ConfigMap (`agent-frontend-keycloak-ca`), generalizing the one-off Job-scoped copy `run_acceptance_gate.yml` already did for its own diagnostic run. Wired once into the `agents` role's `install.yml` (before any agent's GitOps Application applies, avoiding a transient `CreateContainerConfigError`) and checked for existence in `check.yml`.

That ConfigMap is mounted read-only into every frontend container, by two different mechanisms matching each agent's own provisioning model:

- `tekos`, `advantage`, `comage`, `finage`: `gitops/charts/<agent>/templates/deployment.yaml`, guarded by `values.yaml`'s `keycloak.caConfigMapName` (empty disables the volume/mount/env var entirely).
- `arkos`, `naveo`: `aiagent-operator`'s `desiredFrontendDeployment` (`operator/aiagent-operator/internal/controller/resources.go`), guarded by `OperatorConfig.KeycloakCAConfigMapName` - a platform-wide operator setting, not an `AIAgent` CR field, matching the existing pattern for `KeycloakJWKSURL` ([ADR-0327](0327-define-the-aiagent-crd-reconciliation-contract-before-implementing-the-operator.md): the CR is deployment bindings for one agent, not a place to redeclare shared platform config).

In every case, mount path (`/etc/pki/agent-frontend/keycloak-ca`), env var (`KEYCLOAK_CA_CERT_PATH`), ConfigMap name (`agent-frontend-keycloak-ca`), and key (`ca.crt`) are identical, since it's the same container image consuming them regardless of which mechanism rendered the Deployment.

**bff containers are untouched.** They only fetch the JWKS server-to-server via the internal Service (`KEYCLOAK_JWKS_URL`) and never dial the external Route, so they were never affected by this bug.

## Consequences

Every agent frontend's OIDC client now verifies Keycloak's certificate correctly instead of failing every HTTPS call to it. No `readOnlyRootFilesystem` conflict - a ConfigMap volume mount is independent of the container's own root filesystem, and no `update-ca-trust extract`/init container is needed. The CA delivery mechanism (Ansible sync + chart/operator mount) is now a second, reusable consumer of `openshift-config/keycloak-serving-ca` beyond the OAuth server and the acceptance gate - a ConfigMap deletion or accidental edit in `zuno-ai-run` breaks login for all six agents at once, mitigated by the new `check.yml` existence check giving a specific, actionable failure rather than only an indirect `/healthz`-timeout-style symptom (the `/healthz` probe never dials Keycloak, so it stays green even when this ConfigMap is missing).

**Known follow-ups, deliberately not fixed here:**

- `comage` and `finage`'s `bff` containers never received the `KEYCLOAK_JWKS_URL` internal-URL fix that `tekos`/`advantage`'s did - their JWKS fetch still hits the same external-Route TLS gap this ADR fixes for frontends. A separate, pre-existing bug, currently latent because both agents' `status: placeholder` means their BFF calls 404 before reaching JWKS validation in anger.
- An intermittent istio-proxy startup-probe flake on fresh `zuno-ai-run` rollouts (self-heals; mitigated 2026-08-16 per `gitops/charts/service-mesh/values.yaml`, but recurred during this investigation's diagnostics).
- A mesh-wide, so-far-benign istio-proxy SDS error loop about a missing `service-ca.crt` file resource, observed on every sidecar in the mesh during diagnostics, unrelated to this bug.

## Security considerations

No secret material is created or exposed - `keycloak-serving-ca`'s `ca.crt` is public certificate data, identical to what ADR-0347 already publishes for the cluster's own OAuth server. Every mount is read-only, and the Go client change adds trust for exactly one additional CA on top of the system pool - it does not disable verification (proven by `TestNewClientRejectsUntrustedServerByDefault`, which asserts an untrusted server still fails when `caCertPath` is unset).

## Operational considerations

- If the Vault PKI root is ever regenerated, the `zuno-ai-run` ConfigMap goes stale until the next `make d1 install agents`, which re-syncs from the live `openshift-config/keycloak-serving-ca` (itself kept current by `make d0 install/reconcile openshift-oauth`).
- No cleanup-on-uninstall logic was added for the `agent-frontend-keycloak-ca` ConfigMap, matching the existing `acceptance-gate-ca` precedent of leaving Ansible-managed ConfigMaps in `zuno-ai-run` after uninstall.
- `run_acceptance_gate.yml`'s own inline CA copy (`acceptance-gate-ca`) was left as-is rather than refactored onto the new shared task - both now exist and work independently; DRYing them up is an optional future cleanup, not required for correctness.

## Acceptance criteria

- `oc get cm agent-frontend-keycloak-ca -n zuno-ai-run -o jsonpath='{.data.ca\.crt}'` is non-empty and contains a PEM certificate.
- Every agent frontend pod (`tekos`, `advantage`, `comage`, `finage`, `arkos`, `naveo`) has `KEYCLOAK_CA_CERT_PATH` set and the file present at that path.
- `https://tekos.apps.demo222.startx.fr/login` 302s to Keycloak (not 502); a full login completes through `/callback` into the chat UI; `/logout` redirects cleanly through Keycloak's end-session endpoint and back; the refresh path (`Refresh()`) succeeds without a 502.
- `go test ./...` passes in `components/agent-frontend` and `operator/aiagent-operator`, including the new CA-trust regression tests in both.
- `oc get deploy tekos-bff -n zuno-ai-run -o yaml` (and the other five `bff` Deployments) show no new env var/volume/mount - the `bff` scope boundary held.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0347](0347-trust-the-vault-pki-root-for-the-oauth-openid-idp.md) - sibling/precedent: same CA, same "extend trust to a new consumer" shape.
- [ADR-0316](0316-keycloak-route-tls-via-cert-manager.md) - why Keycloak's Route certificate chains to the Vault PKI root in the first place.
- [ADR-0008](0008-use-one-frontend-and-one-bff-deployment-per-agent.md) - the per-agent frontend/BFF split that both scopes this fix to `agent-frontend` only (not `agent-bff`) and requires it applied across all six agent deployments.
- [ADR-0327](0327-define-the-aiagent-crd-reconciliation-contract-before-implementing-the-operator.md) - why `arkos`/`naveo` needed a separate operator-level fix rather than a chart edit.
