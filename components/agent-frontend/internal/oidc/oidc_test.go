package oidc

import (
	"encoding/json"
	"encoding/pem"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"testing"
)

func newDiscoveryTestClient(t *testing.T, endSessionEndpoint string) *Client {
	t.Helper()
	mux := http.NewServeMux()
	mux.HandleFunc("/.well-known/openid-configuration", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(Discovery{
			Issuer:                "http://issuer.example",
			AuthorizationEndpoint: "http://issuer.example/auth",
			TokenEndpoint:         "http://issuer.example/token",
			JWKSURI:               "http://issuer.example/jwks",
			EndSessionEndpoint:    endSessionEndpoint,
		})
	})
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	c, err := NewClient(srv.URL, "tekos-frontend", "secret", "https://tekos.example.com/callback", "")
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	return c
}

// EndSessionURL must always give Keycloak enough to identify the RP and
// terminate the session: either id_token_hint, or (when no ID token is
// available - e.g. the session already expired server-side) client_id as
// the documented fallback. Sending id_token_hint as an empty string is what
// produces Keycloak's "Missing parameters: id_token_hint" error.
func TestEndSessionURLWithIDTokenHint(t *testing.T) {
	c := newDiscoveryTestClient(t, "http://issuer.example/logout")

	got, err := c.EndSessionURL("the-id-token", "https://tekos.example.com")
	if err != nil {
		t.Fatalf("EndSessionURL: %v", err)
	}
	u, err := url.Parse(got)
	if err != nil {
		t.Fatalf("parsing result: %v", err)
	}
	q := u.Query()
	if q.Get("id_token_hint") != "the-id-token" {
		t.Errorf("id_token_hint = %q, want %q", q.Get("id_token_hint"), "the-id-token")
	}
	if q.Has("client_id") {
		t.Errorf("client_id should be omitted when id_token_hint is present, got %q", q.Get("client_id"))
	}
	if q.Get("post_logout_redirect_uri") != "https://tekos.example.com" {
		t.Errorf("post_logout_redirect_uri = %q", q.Get("post_logout_redirect_uri"))
	}
}

func TestEndSessionURLFallsBackToClientIDWithoutIDToken(t *testing.T) {
	c := newDiscoveryTestClient(t, "http://issuer.example/logout")

	got, err := c.EndSessionURL("", "https://tekos.example.com")
	if err != nil {
		t.Fatalf("EndSessionURL: %v", err)
	}
	u, err := url.Parse(got)
	if err != nil {
		t.Fatalf("parsing result: %v", err)
	}
	q := u.Query()
	if q.Has("id_token_hint") {
		t.Errorf("id_token_hint should be omitted when empty (not sent as a blank param), got %q", q.Get("id_token_hint"))
	}
	if q.Get("client_id") != "tekos-frontend" {
		t.Errorf("client_id = %q, want %q", q.Get("client_id"), "tekos-frontend")
	}
	if q.Get("post_logout_redirect_uri") != "https://tekos.example.com" {
		t.Errorf("post_logout_redirect_uri = %q", q.Get("post_logout_redirect_uri"))
	}
}

// writeCACertPEM PEM-encodes srv's leaf certificate into a fresh file under
// t.TempDir() and returns its path, for exercising NewClient's caCertPath.
func writeCACertPEM(t *testing.T, srv *httptest.Server) string {
	t.Helper()
	block := &pem.Block{Type: "CERTIFICATE", Bytes: srv.Certificate().Raw}
	path := filepath.Join(t.TempDir(), "ca.crt")
	if err := os.WriteFile(path, pem.EncodeToMemory(block), 0o600); err != nil {
		t.Fatalf("writing CA cert file: %v", err)
	}
	return path
}

// ADR-0411: Keycloak's Route certificate chains to a private CA no stock
// container trust store carries - NewClient's caCertPath parameter must let
// the client trust it explicitly.
func TestNewClientTrustsCustomCACert(t *testing.T) {
	var srv *httptest.Server
	srv = httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(Discovery{
			Issuer:                srv.URL,
			AuthorizationEndpoint: srv.URL + "/auth",
			TokenEndpoint:         srv.URL + "/token",
			JWKSURI:               srv.URL + "/jwks",
		})
	}))
	defer srv.Close()
	caPath := writeCACertPEM(t, srv)

	c, err := NewClient(srv.URL, "tekos-frontend", "secret", "https://tekos.example.com/callback", caPath)
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	if _, err := c.discover(); err != nil {
		t.Fatalf("discover() with trusted custom CA: %v", err)
	}
}

// Proves the fix doesn't quietly disable verification: without caCertPath,
// a server presenting a certificate the system pool doesn't trust must still
// fail - this is the exact failure mode that produced "identity provider
// unreachable" before ADR-0411, and it must still fail with no CA path set.
func TestNewClientRejectsUntrustedServerByDefault(t *testing.T) {
	var srv *httptest.Server
	srv = httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(Discovery{Issuer: srv.URL})
	}))
	defer srv.Close()

	c, err := NewClient(srv.URL, "tekos-frontend", "secret", "https://tekos.example.com/callback", "")
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	if _, err := c.discover(); err == nil {
		t.Fatal("discover() succeeded against an untrusted server with no caCertPath set, want a TLS verification error")
	}
}

func TestNewClientRejectsUnreadableCACertPath(t *testing.T) {
	missing := filepath.Join(t.TempDir(), "does-not-exist.crt")
	if _, err := NewClient("https://issuer.example", "tekos-frontend", "secret", "https://tekos.example.com/callback", missing); err == nil {
		t.Fatal("NewClient succeeded with an unreadable caCertPath, want an error")
	}
}

func TestNewClientRejectsInvalidPEM(t *testing.T) {
	path := filepath.Join(t.TempDir(), "garbage.crt")
	if err := os.WriteFile(path, []byte("not a certificate"), 0o600); err != nil {
		t.Fatalf("writing garbage CA file: %v", err)
	}
	if _, err := NewClient("https://issuer.example", "tekos-frontend", "secret", "https://tekos.example.com/callback", path); err == nil {
		t.Fatal("NewClient succeeded with invalid PEM content, want an error")
	}
}
