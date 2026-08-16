package oidc

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
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
	return NewClient(srv.URL, "tekos-frontend", "secret", "https://tekos.example.com/callback")
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
