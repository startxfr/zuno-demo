/*
Copyright 2026.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package controller

import "os"

// OperatorConfig carries platform-wide constants the reconciler needs but
// that must never live on an AIAgent CR (ADR-0327: the CR is deployment
// bindings/references for ONE agent, not a place to redeclare shared
// platform config). Every field here matches a value every agent chart's
// own values.yaml/helpers already hardcode or derive the same way -
// gitops/charts/tekos/templates/_helpers.tpl is the reference this
// mirrors.
type OperatorConfig struct {
	// ClusterBaseDomain is the one genuinely per-cluster value; every
	// other field below is either a fixed in-cluster Service DNS name or
	// derived from this one, exactly like the chart helpers.
	ClusterBaseDomain string

	// KeycloakJWKSURL is where the BFFs actually fetch the JWKS, while
	// keycloakIssuerURL() stays the iss-claim comparison string - the
	// external Route's certificate chains to Vault's internal root CA,
	// absent from container trust stores, so the in-cluster Keycloak
	// Service is the reliable fetch path.
	KeycloakJWKSURL string

	// KeycloakCAConfigMapName, if non-empty, names a ConfigMap (key
	// ca.crt) in the agent's own target namespace that the frontend
	// container mounts and trusts via KEYCLOAK_CA_CERT_PATH - ADR-0411.
	// Unlike the BFF's KeycloakJWKSURL workaround, the frontend's OIDC
	// relying-party flow must keep dialing Keycloak's external Route
	// (AuthURL/EndSessionURL redirect the browser there), so it needs
	// actual CA trust rather than an internal-URL substitution. Ansible's
	// agents role syncs this ConfigMap from openshift-config/
	// keycloak-serving-ca (the same source ADR-0347 established) into
	// every agent's target namespace before this operator's first
	// reconcile. Empty disables the volume/mount/env var entirely.
	KeycloakCAConfigMapName string

	// KeycloakAdminBaseURL and KeycloakAdminClientID configure agent-bff's
	// Keycloak Admin API boundary (ADR-0213, extended by ADR-0527's project
	// RBAC tab, provisioned by ADR-0530). The bare host only - the client
	// appends /realms/<realm>/... itself. The matching client secret is not
	// here: it reaches the pod from Vault via desiredBFFExternalSecret, never
	// through operator config.
	//
	// Blanking KeycloakAdminClientID disables the boundary entirely - no
	// ExternalSecret, no env vars - and agent-bff keeps its documented
	// fail-closed 503 on GET /api/colleagues and GET /api/groups.
	KeycloakAdminBaseURL  string
	KeycloakAdminClientID string

	// AgentRuntimeBaseURL, RedisAddr, SessionMaxLifetimeSeconds: fixed
	// in-cluster coordinates for shared platform services, identical
	// across every agent (see gitops/charts/tekos/values.yaml).
	AgentRuntimeBaseURL       string
	RedisAddr                 string
	SessionMaxLifetimeSeconds string

	// AllowedTargetNamespaces is the in-code cross-namespace defense in
	// depth CONTRACT.md calls for. ADR-0329 puts every agent in one
	// shared namespace today; a CR asking for anything else is rejected
	// before any resource is generated, regardless of what the CRD
	// schema alone would permit.
	AllowedTargetNamespaces []string

	// SharedServiceRefs are Service{name,namespace} pairs the shared
	// platform is expected to publish. RuntimeBindingReady only ever
	// reads these (never creates/deletes them) - a pure presence check,
	// not a lifecycle dependency, so it never violates the "operator
	// must not become responsible for shared platform services"
	// boundary.
	SharedServiceRefs []ServiceRef
}

// ServiceRef names a Service the reconciler only ever reads.
type ServiceRef struct {
	Name      string
	Namespace string
}

func getenvDefault(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

// DefaultOperatorConfig mirrors gitops/charts/tekos/values.yaml's own
// defaults field-for-field, overridable per deployment via env vars on
// the manager Deployment (gitops/charts/aiagent-operator sets
// CLUSTER_BASE_DOMAIN from the same Ansible inventory variable every
// agent chart's own Application already substitutes).
func DefaultOperatorConfig() OperatorConfig {
	return OperatorConfig{
		ClusterBaseDomain:         getenvDefault("CLUSTER_BASE_DOMAIN", "apps.mycluster.example.com"),
		KeycloakJWKSURL:           getenvDefault("KEYCLOAK_JWKS_URL", "http://zuno-service.zuno-auth.svc:8080/realms/zuno/protocol/openid-connect/certs"),
		KeycloakCAConfigMapName:   getenvDefault("KEYCLOAK_CA_CONFIGMAP_NAME", "agent-frontend-keycloak-ca"),
		KeycloakAdminBaseURL:      getenvDefault("KEYCLOAK_ADMIN_BASE_URL", "http://zuno-service.zuno-auth.svc:8080"),
		KeycloakAdminClientID:     getenvDefault("KEYCLOAK_ADMIN_CLIENT_ID", "zuno-admin-api"),
		AgentRuntimeBaseURL:       getenvDefault("AGENT_RUNTIME_BASE_URL", "http://agent-runtime.zuno-ai-run.svc.cluster.local:8080"),
		RedisAddr:                 getenvDefault("REDIS_ADDR", "zuno-redis-master.zuno-auth.svc.cluster.local:6379"),
		SessionMaxLifetimeSeconds: getenvDefault("SESSION_MAX_LIFETIME_SECONDS", "43200"),
		AllowedTargetNamespaces:   []string{"zuno-ai-run"},
		SharedServiceRefs: []ServiceRef{
			{Name: "agent-runtime", Namespace: "zuno-ai-run"},
			{Name: "mcp-gateway", Namespace: "zuno-ai-run"},
			{Name: "rag-service", Namespace: "zuno-data"},
		},
	}
}

func (c OperatorConfig) namespaceAllowed(ns string) bool {
	for _, allowed := range c.AllowedTargetNamespaces {
		if allowed == ns {
			return true
		}
	}
	return false
}

func (c OperatorConfig) keycloakIssuerURL() string {
	return "https://keycloak." + c.ClusterBaseDomain + "/realms/zuno"
}
