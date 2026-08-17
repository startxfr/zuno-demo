package main

import (
	"crypto"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"math/big"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"testing"
	"time"

	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/oidc"
	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/session"
)

type testJWK struct {
	Kty string `json:"kty"`
	Kid string `json:"kid"`
	N   string `json:"n"`
	E   string `json:"e"`
	Alg string `json:"alg"`
}

type testJWKS struct {
	Keys []testJWK `json:"keys"`
}

// signRS256 hand-builds a JWT the same way internal/oidc.verifySignatureAndGetClaims
// verifies one, so this test exercises the real callback/session code path
// against a token that looks exactly like what Keycloak would issue.
func signRS256(t *testing.T, key *rsa.PrivateKey, kid string, claims map[string]interface{}) string {
	t.Helper()
	headerJSON, err := json.Marshal(map[string]string{"alg": "RS256", "kid": kid})
	if err != nil {
		t.Fatalf("marshal header: %v", err)
	}
	claimsJSON, err := json.Marshal(claims)
	if err != nil {
		t.Fatalf("marshal claims: %v", err)
	}
	signingInput := base64.RawURLEncoding.EncodeToString(headerJSON) + "." + base64.RawURLEncoding.EncodeToString(claimsJSON)
	hashed := sha256.Sum256([]byte(signingInput))
	sig, err := rsa.SignPKCS1v15(rand.Reader, key, crypto.SHA256, hashed[:])
	if err != nil {
		t.Fatalf("sign: %v", err)
	}
	return signingInput + "." + base64.RawURLEncoding.EncodeToString(sig)
}

func testSessionManager(t *testing.T) *session.Manager {
	t.Helper()
	addr := os.Getenv("TEST_REDIS_ADDR")
	if addr == "" {
		addr = "localhost:6379"
	}
	key := make([]byte, 32)
	for i := range key {
		key[i] = byte(i)
	}
	store, err := session.NewStore(addr, "", 0, key)
	if err != nil {
		t.Fatalf("NewStore: %v", err)
	}
	return session.NewManager([]byte("test-hmac-secret"), true, store, time.Hour, nil)
}

// TestCallbackHandlerPersistsRefreshToken is a regression test for the bug
// behind Keycloak's "Missing parameters: id_token_hint" logout error:
// callbackHandler exchanged the authorization code for tokens but never
// carried tokens.RefreshToken into the saved session.Session, so every
// session was created with an empty refresh token. Once the short-lived
// access token expired, session.Manager.Load could no longer refresh it,
// logout saw a nil session, and sent Keycloak an empty id_token_hint.
func TestCallbackHandlerPersistsRefreshToken(t *testing.T) {
	sessions := testSessionManager(t)

	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("GenerateKey: %v", err)
	}

	var issuer string
	var idToken string
	mux := http.NewServeMux()
	mux.HandleFunc("/.well-known/openid-configuration", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(oidc.Discovery{
			Issuer:                issuer,
			AuthorizationEndpoint: issuer + "/auth",
			TokenEndpoint:         issuer + "/token",
			JWKSURI:               issuer + "/jwks",
			EndSessionEndpoint:    issuer + "/logout",
		})
	})
	mux.HandleFunc("/jwks", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(testJWKS{Keys: []testJWK{{
			Kty: "RSA",
			Kid: "test-key",
			Alg: "RS256",
			N:   base64.RawURLEncoding.EncodeToString(priv.PublicKey.N.Bytes()),
			E:   base64.RawURLEncoding.EncodeToString(big.NewInt(int64(priv.PublicKey.E)).Bytes()),
		}}})
	})
	mux.HandleFunc("/token", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(oidc.TokenResponse{
			AccessToken:  "test-access-token",
			IDToken:      idToken,
			RefreshToken: "test-refresh-token",
			ExpiresIn:    300,
			TokenType:    "Bearer",
		})
	})
	server := httptest.NewServer(mux)
	defer server.Close()
	issuer = server.URL

	idToken = signRS256(t, priv, "test-key", map[string]interface{}{
		"sub":   "user-1",
		"email": "user-1@example.com",
		"iss":   issuer,
		"aud":   "tekos-frontend",
		"exp":   time.Now().Add(time.Hour).Unix(),
	})

	oidcClient, err := oidc.NewClient(issuer, "tekos-frontend", "secret", "https://tekos.example.com/callback", "")
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}

	txn := oidc.AuthRequest{State: "test-state", CodeVerifier: "test-verifier"}
	txnRec := httptest.NewRecorder()
	if err := sessions.SaveValue(txnRec, oidcTxnCookie, txn, 10*time.Minute); err != nil {
		t.Fatalf("SaveValue: %v", err)
	}

	req := httptest.NewRequest(http.MethodGet, "/callback?state=test-state&code=test-code", nil)
	for _, c := range txnRec.Result().Cookies() {
		req.AddCookie(c)
	}

	rec := httptest.NewRecorder()
	callbackHandler(oidcClient, sessions)(rec, req)

	if rec.Code != http.StatusFound {
		t.Fatalf("callback returned %d, body: %s", rec.Code, rec.Body.String())
	}

	verifyReq := httptest.NewRequest(http.MethodGet, "/", nil)
	for _, c := range rec.Result().Cookies() {
		verifyReq.AddCookie(c)
	}
	sess, err := sessions.Load(verifyReq)
	if err != nil {
		t.Fatalf("Load after callback: %v", err)
	}
	if sess.RefreshToken != "test-refresh-token" {
		t.Fatalf("session.RefreshToken = %q, want %q - the token exchange's refresh_token was not persisted at login", sess.RefreshToken, "test-refresh-token")
	}
	if sess.IDToken == "" {
		t.Fatal("session.IDToken is empty after callback")
	}
}

// TestLogoutHandlerFallsBackToClientIDWhenSessionIsGone reproduces the
// reported "Missing parameters: id_token_hint" error at the logout handler
// itself: with no session cookie at all (e.g. Redis eviction, expired SSO,
// or a double logout), logoutHandler must still redirect to a valid
// Keycloak end-session URL rather than one with a blank id_token_hint.
func TestLogoutHandlerFallsBackToClientIDWhenSessionIsGone(t *testing.T) {
	sessions := testSessionManager(t)

	var issuer string
	mux := http.NewServeMux()
	mux.HandleFunc("/.well-known/openid-configuration", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(oidc.Discovery{
			Issuer:                issuer,
			AuthorizationEndpoint: issuer + "/auth",
			TokenEndpoint:         issuer + "/token",
			JWKSURI:               issuer + "/jwks",
			EndSessionEndpoint:    issuer + "/logout",
		})
	})
	server := httptest.NewServer(mux)
	defer server.Close()
	issuer = server.URL

	oidcClient, err := oidc.NewClient(issuer, "tekos-frontend", "secret", "https://tekos.example.com/callback", "")
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}

	req := httptest.NewRequest(http.MethodGet, "/logout", nil)
	rec := httptest.NewRecorder()
	logoutHandler(oidcClient, sessions, "https://tekos.example.com")(rec, req)

	if rec.Code != http.StatusFound {
		t.Fatalf("logout returned %d, body: %s", rec.Code, rec.Body.String())
	}
	loc := rec.Header().Get("Location")
	u, err := url.Parse(loc)
	if err != nil {
		t.Fatalf("parsing Location %q: %v", loc, err)
	}
	q := u.Query()
	if q.Has("id_token_hint") && q.Get("id_token_hint") == "" {
		t.Fatal("logout redirect carries a blank id_token_hint - this is what triggers Keycloak's 'Missing parameters' error")
	}
	if q.Get("client_id") != "tekos-frontend" {
		t.Fatalf("client_id = %q, want %q as fallback when no session/id_token is available", q.Get("client_id"), "tekos-frontend")
	}
}
