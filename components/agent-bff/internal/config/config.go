// Package config loads agent-bff's runtime configuration from the
// environment. Per ADR-0008 this codebase is shared across every agent;
// AGENT_NAME plus the Agent Runtime base URL are what turn this one image
// into "the Tekos BFF" for a given Deployment.
package config

import (
	"fmt"
	"os"
)

// Config holds every environment-derived setting agent-bff needs.
type Config struct {
	// ListenAddr is the address the HTTP server binds, e.g. ":8080".
	ListenAddr string

	// AgentName is this BFF instance's agent, used to build the Agent
	// Runtime path POST /v1/agents/{AgentName}/chat.
	AgentName string

	// KeycloakIssuerURL is the OIDC issuer whose JWKS validates incoming
	// bearer tokens, e.g. https://keycloak.apps.<cluster-domain>/realms/zuno -
	// matches the Keycloak CR's actual Route hostname, see
	// gitops/charts/keycloak/templates/keycloak.yaml. Standard JWKS
	// validation against <issuer>/protocol/openid-connect/certs.
	KeycloakIssuerURL string

	// KeycloakJWKSURL optionally overrides where the JWKS is actually
	// fetched from, while KeycloakIssuerURL stays the iss-claim comparison
	// string. VERIFIED live (2026-08-16): the external Route's certificate
	// chains to Vault's internal root CA, absent from the container's
	// trust store, so fetching JWKS via the issuer URL fails TLS
	// verification and every token is rejected as invalid - the in-cluster
	// Keycloak Service (plain HTTP by Keycloak's own edge-termination
	// design, inside the mesh/NetworkPolicy boundary) is the reliable
	// path. Same two-variable seam as the Python services' auth.py.
	KeycloakJWKSURL string

	// OIDCAudience is the expected `aud`/`azp` claim on incoming access
	// tokens - the frontend's client ID, since the frontend is the token's
	// original requesting party (contract: <agent>-frontend).
	OIDCAudience string

	// AgentRuntimeBaseURL is the shared Agent Runtime's in-cluster base
	// URL, e.g. http://agent-runtime.zuno-ai-run.svc.cluster.local:8080
	// (zuno-ai-run: Agent Runtime is a shared platform component per
	// ADR-0007, not per-agent - reconciled with gitops/charts/agent-runtime
	// during integration). Owned by a parallel track; this BFF only calls
	// its documented HTTP contract (POST /v1/agents/{agent}/chat).
	AgentRuntimeBaseURL string
}

// Load reads configuration from the environment.
func Load() (*Config, error) {
	cfg := &Config{
		ListenAddr:          getenv("LISTEN_ADDR", ":8080"),
		AgentName:           getenv("AGENT_NAME", "tekos"),
		KeycloakIssuerURL:   getenv("KEYCLOAK_ISSUER_URL", ""),
		KeycloakJWKSURL:     getenv("KEYCLOAK_JWKS_URL", ""),
		OIDCAudience:        getenv("OIDC_AUDIENCE", "tekos-frontend"),
		AgentRuntimeBaseURL: getenv("AGENT_RUNTIME_BASE_URL", "http://agent-runtime.zuno-ai-run.svc.cluster.local:8080"),
	}

	if cfg.KeycloakIssuerURL == "" {
		return nil, fmt.Errorf("KEYCLOAK_ISSUER_URL is required")
	}

	return cfg, nil
}

func getenv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
