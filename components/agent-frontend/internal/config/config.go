// Package config loads agent-frontend's runtime configuration from the
// environment. Per ADR-0008 the frontend codebase is shared across every
// agent; ACTIVE_AGENT plus the OIDC_* / BFF_BASE_URL values are what turn
// this one image into "the Tekos frontend" for a given Deployment. No value
// here is a secret - OIDC_CLIENT_SECRET and SESSION_HMAC_SECRET are injected
// as environment variables sourced from an ExternalSecret (ADR-0024), never
// hardcoded or committed.
package config

import (
	"encoding/base64"
	"fmt"
	"os"
	"strconv"
	"time"
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
	// https://keycloak.apps.<cluster-domain>/realms/zuno - matches the
	// Keycloak CR's actual Route hostname, see
	// gitops/charts/keycloak/templates/keycloak.yaml.
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
	// BFF, e.g. http://tekos-bff.zuno-ai-run.svc.cluster.local:8080. The BFF
	// has no OpenShift Route (no need for a second public ingress) - the
	// frontend proxies chat calls to it server-side.
	BFFBaseURL string

	// SessionHMACSecret signs the frontend's opaque session-ID cookie.
	// Sourced from Vault via ExternalSecret.
	SessionHMACSecret []byte

	// SessionEncryptionKey (32 bytes, AES-256) encrypts session records
	// at rest in Redis (ADR-0042). Sourced from Vault via ExternalSecret;
	// distinct from SessionHMACSecret so compromising one doesn't also
	// compromise the other (signing vs. encryption keys stay separate).
	SessionEncryptionKey []byte

	// RedisAddr is the in-cluster Redis Service address, e.g.
	// zuno-redis-master.zuno-auth.svc.cluster.local:6379 (ADR-0042).
	RedisAddr string

	// RedisPassword authenticates to Redis. Sourced from Vault via
	// ExternalSecret; empty only for local development against an
	// unauthenticated Redis.
	RedisPassword string

	// SessionMaxLifetime bounds how long a server-side session record
	// survives in Redis regardless of how many times its access token is
	// refreshed - ADR-0042's "revocable... TTL by default", distinct from
	// the short-lived access token's own expiry.
	SessionMaxLifetime time.Duration

	// WebDistDir is the Vite build output directory (ADR-0044), containing
	// .vite/manifest.json plus the hashed JS/CSS assets - see
	// internal/assets. Set to /app/web/dist in the image (Dockerfile builds
	// it in a Node stage); defaults to web/dist for `go run` from this
	// component's own directory during local development, after running
	// `npm run build` in web/ once.
	WebDistDir string
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
		BFFBaseURL:        getenv("BFF_BASE_URL", "http://tekos-bff.zuno-ai-run.svc.cluster.local:8080"),
		WebDistDir:        getenv("WEB_DIST_DIR", "web/dist"),
		RedisAddr:         getenv("REDIS_ADDR", "zuno-redis-master.zuno-auth.svc.cluster.local:6379"),
		RedisPassword:     os.Getenv("REDIS_PASSWORD"),
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

	encKeyB64 := os.Getenv("SESSION_ENCRYPTION_KEY")
	if encKeyB64 == "" {
		return nil, fmt.Errorf("SESSION_ENCRYPTION_KEY is required (expected from an ExternalSecret-mounted env var, base64-encoded 32 bytes)")
	}
	encKey, err := base64.StdEncoding.DecodeString(encKeyB64)
	if err != nil {
		return nil, fmt.Errorf("SESSION_ENCRYPTION_KEY is not valid base64: %w", err)
	}
	if len(encKey) != 32 {
		return nil, fmt.Errorf("SESSION_ENCRYPTION_KEY must decode to exactly 32 bytes (AES-256), got %d", len(encKey))
	}
	cfg.SessionEncryptionKey = encKey

	maxLifetime := 12 * time.Hour
	if v := os.Getenv("SESSION_MAX_LIFETIME_SECONDS"); v != "" {
		secs, err := strconv.Atoi(v)
		if err != nil {
			return nil, fmt.Errorf("SESSION_MAX_LIFETIME_SECONDS is not a valid integer: %w", err)
		}
		maxLifetime = time.Duration(secs) * time.Second
	}
	cfg.SessionMaxLifetime = maxLifetime

	return cfg, nil
}

func getenv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
