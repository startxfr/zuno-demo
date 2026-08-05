// Package config loads agent-frontend's runtime configuration from the
// environment. Per ADR-0008 the frontend codebase is shared across every
// agent; ACTIVE_AGENT plus the OIDC_* / BFF_BASE_URL values are what turn
// this one image into "the Tekos frontend" for a given Deployment. No value
// here is a secret - OIDC_CLIENT_SECRET and SESSION_HMAC_SECRET are injected
// as environment variables sourced from an ExternalSecret (ADR-0024), never
// hardcoded or committed.
package config

import (
	"fmt"
	"os"
)

// Config holds every environment-derived setting agent-frontend needs.
type Config struct {
	// ListenAddr is the address the HTTP server binds, e.g. ":8080".
	ListenAddr string

	// AgentsDir is the directory containing one subdirectory per agent, each
	// with an agent.okf.md OKF v0.2 Markdown bundle (ADR-0038, baked into
	// the image at build time from the repository's agents/ directory -
	// see Dockerfile).
	AgentsDir string

	// ActiveAgent is the agent this deployment renders a full chat UI for
	// (its agent.okf.md must have zuno.status: active). All five agents are
	// still listed on the portal tile view regardless of this value.
	ActiveAgent string

	// KeycloakIssuerURL is the OIDC issuer, e.g.
	// https://sso.apps.<cluster-domain>/realms/zuno. ASSUMPTION: the identity
	// track has not yet published a Keycloak route hostname convention
	// (ansible/roles/keycloak is still a scaffold at the time this was
	// written), so "sso.<cluster_base_domain>" is this track's placeholder;
	// see components/agent-frontend/README.md.
	KeycloakIssuerURL string

	// OIDCClientID is the confidential client registered in the zuno realm
	// for this agent, e.g. "tekos-frontend" (contract fixed by Track E's
	// brief: <agent>-frontend).
	OIDCClientID string

	// OIDCClientSecret authenticates this confidential client to Keycloak's
	// token endpoint. Sourced from Vault via ExternalSecret; never a literal
	// default.
	OIDCClientSecret string

	// OIDCRedirectURL is this deployment's own callback URL, e.g.
	// https://tekos.apps.<cluster-domain>/callback - must be pre-registered
	// on the Keycloak client matching the documented redirect URI pattern
	// https://<agent>.apps.<cluster-domain>/*.
	OIDCRedirectURL string

	// SelfBaseURL is this frontend's own externally reachable base URL,
	// e.g. https://tekos.apps.<cluster-domain>. Used to build the
	// post-logout redirect and as a fallback to derive OIDCRedirectURL.
	SelfBaseURL string

	// BFFBaseURL is the in-cluster ClusterIP Service URL for this agent's
	// BFF, e.g. http://tekos-bff.zuno-agent-tekos.svc.cluster.local:8080. The BFF
	// has no OpenShift Route (ADR-0023 isolation + no need for a second
	// public ingress) - the frontend proxies chat calls to it server-side.
	BFFBaseURL string

	// SessionHMACSecret signs the frontend's session cookie (subject,
	// groups, access token, expiry). Sourced from Vault via ExternalSecret.
	SessionHMACSecret []byte
}

// Load reads configuration from the environment, applying safe defaults
// only where a default cannot leak a secret or silently misroute traffic.
func Load() (*Config, error) {
	cfg := &Config{
		ListenAddr:        getenv("LISTEN_ADDR", ":8080"),
		AgentsDir:         getenv("AGENTS_DIR", "/agents"),
		ActiveAgent:       getenv("ACTIVE_AGENT", "tekos"),
		KeycloakIssuerURL: getenv("KEYCLOAK_ISSUER_URL", ""),
		OIDCClientID:      getenv("OIDC_CLIENT_ID", "tekos-frontend"),
		OIDCClientSecret:  os.Getenv("OIDC_CLIENT_SECRET"),
		OIDCRedirectURL:   getenv("OIDC_REDIRECT_URL", ""),
		SelfBaseURL:       getenv("SELF_BASE_URL", ""),
		BFFBaseURL:        getenv("BFF_BASE_URL", "http://tekos-bff.zuno-agent-tekos.svc.cluster.local:8080"),
	}

	if cfg.KeycloakIssuerURL == "" {
		return nil, fmt.Errorf("KEYCLOAK_ISSUER_URL is required")
	}
	if cfg.SelfBaseURL == "" {
		return nil, fmt.Errorf("SELF_BASE_URL is required")
	}
	if cfg.OIDCRedirectURL == "" {
		cfg.OIDCRedirectURL = cfg.SelfBaseURL + "/callback"
	}
	if cfg.OIDCClientSecret == "" {
		return nil, fmt.Errorf("OIDC_CLIENT_SECRET is required (expected from an ExternalSecret-mounted env var)")
	}

	secret := os.Getenv("SESSION_HMAC_SECRET")
	if secret == "" {
		return nil, fmt.Errorf("SESSION_HMAC_SECRET is required (expected from an ExternalSecret-mounted env var)")
	}
	cfg.SessionHMACSecret = []byte(secret)

	return cfg, nil
}

func getenv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
