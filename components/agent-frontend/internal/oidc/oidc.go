// Package oidc implements the pieces of the OpenID Connect Authorization
// Code flow (with PKCE) that agent-frontend needs against Keycloak: issuer
// discovery, the authorization redirect, the code-for-token exchange, and
// ID-token signature verification against the issuer's JWKS.
//
// DELIBERATE CHOICE: this is hand-rolled against the Go standard library
// only (net/http, crypto/rsa, encoding/json) rather than using
// golang.org/x/oauth2 + github.com/coreos/go-oidc. This environment has no
// network access to `go mod tidy`/vendor and pin those modules, and the
// OIDC/PKCE surface is small and well-specified enough (RFC 6749 §4.1,
// RFC 7636, OpenID Connect Core §3.1) to implement directly and keep fully
// auditable with zero third-party attack surface in the auth-critical path.
// If/when this module gains real network/toolchain access, adopting
// coreos/go-oidc for discovery caching and stricter claim validation is the
// recommended v1 hardening step - see components/agent-frontend/README.md.
package oidc

import (
	"crypto"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math/big"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"
)

// Discovery is the subset of the OpenID Provider metadata document
// (issuer/.well-known/openid-configuration) this client needs.
type Discovery struct {
	Issuer                string `json:"issuer"`
	AuthorizationEndpoint string `json:"authorization_endpoint"`
	TokenEndpoint         string `json:"token_endpoint"`
	JWKSURI               string `json:"jwks_uri"`
	EndSessionEndpoint    string `json:"end_session_endpoint"`
}

// Client is a minimal OIDC relying-party client for one Keycloak realm.
type Client struct {
	IssuerURL    string
	ClientID     string
	ClientSecret string
	RedirectURL  string

	httpClient *http.Client

	mu        sync.RWMutex
	discovery *Discovery
	jwks      *jwks
	jwksAt    time.Time
}

// NewClient builds an OIDC client. Discovery is fetched lazily on first use
// so a transient startup-time network hiccup against Keycloak doesn't crash
// the frontend pod.
func NewClient(issuerURL, clientID, clientSecret, redirectURL string) *Client {
	return &Client{
		IssuerURL:    strings.TrimRight(issuerURL, "/"),
		ClientID:     clientID,
		ClientSecret: clientSecret,
		RedirectURL:  redirectURL,
		httpClient:   &http.Client{Timeout: 10 * time.Second},
	}
}

func (c *Client) discover() (*Discovery, error) {
	c.mu.RLock()
	if c.discovery != nil {
		d := c.discovery
		c.mu.RUnlock()
		return d, nil
	}
	c.mu.RUnlock()

	resp, err := c.httpClient.Get(c.IssuerURL + "/.well-known/openid-configuration")
	if err != nil {
		return nil, fmt.Errorf("fetching OIDC discovery document: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("OIDC discovery returned %d", resp.StatusCode)
	}
	var d Discovery
	if err := json.NewDecoder(resp.Body).Decode(&d); err != nil {
		return nil, fmt.Errorf("decoding OIDC discovery document: %w", err)
	}

	c.mu.Lock()
	c.discovery = &d
	c.mu.Unlock()
	return &d, nil
}

// AuthRequest bundles the values needed to build the authorization redirect
// and later validate its callback.
type AuthRequest struct {
	State         string
	Nonce         string
	CodeVerifier  string
	CodeChallenge string
}

// NewAuthRequest generates a fresh state/nonce/PKCE-verifier triple. The
// caller is responsible for storing State (and CodeVerifier) somewhere it
// can retrieve on /callback - agent-frontend uses a short-lived, signed,
// HttpOnly cookie for this (see internal/session).
func NewAuthRequest() (AuthRequest, error) {
	state, err := randomURLSafeString(32)
	if err != nil {
		return AuthRequest{}, err
	}
	nonce, err := randomURLSafeString(32)
	if err != nil {
		return AuthRequest{}, err
	}
	verifier, err := randomURLSafeString(64)
	if err != nil {
		return AuthRequest{}, err
	}
	sum := sha256.Sum256([]byte(verifier))
	challenge := base64.RawURLEncoding.EncodeToString(sum[:])

	return AuthRequest{
		State:         state,
		Nonce:         nonce,
		CodeVerifier:  verifier,
		CodeChallenge: challenge,
	}, nil
}

// AuthURL builds the Keycloak authorization endpoint redirect URL.
func (c *Client) AuthURL(req AuthRequest) (string, error) {
	d, err := c.discover()
	if err != nil {
		return "", err
	}
	q := url.Values{
		"response_type":         {"code"},
		"client_id":             {c.ClientID},
		"redirect_uri":          {c.RedirectURL},
		"scope":                 {"openid profile email"},
		"state":                 {req.State},
		"nonce":                 {req.Nonce},
		"code_challenge":        {req.CodeChallenge},
		"code_challenge_method": {"S256"},
	}
	return d.AuthorizationEndpoint + "?" + q.Encode(), nil
}

// EndSessionURL builds the Keycloak RP-initiated logout URL.
func (c *Client) EndSessionURL(idTokenHint, postLogoutRedirectURL string) (string, error) {
	d, err := c.discover()
	if err != nil {
		return "", err
	}
	if d.EndSessionEndpoint == "" {
		return postLogoutRedirectURL, nil
	}
	q := url.Values{
		"id_token_hint":            {idTokenHint},
		"post_logout_redirect_uri": {postLogoutRedirectURL},
	}
	return d.EndSessionEndpoint + "?" + q.Encode(), nil
}

// TokenResponse is the subset of the token endpoint response this client uses.
type TokenResponse struct {
	AccessToken  string `json:"access_token"`
	IDToken      string `json:"id_token"`
	RefreshToken string `json:"refresh_token"`
	ExpiresIn    int64  `json:"expires_in"`
	TokenType    string `json:"token_type"`
}

// Exchange trades an authorization code for tokens at the token endpoint.
func (c *Client) Exchange(code, codeVerifier string) (*TokenResponse, error) {
	d, err := c.discover()
	if err != nil {
		return nil, err
	}

	form := url.Values{
		"grant_type":    {"authorization_code"},
		"code":          {code},
		"redirect_uri":  {c.RedirectURL},
		"client_id":     {c.ClientID},
		"client_secret": {c.ClientSecret},
		"code_verifier": {codeVerifier},
	}

	resp, err := c.httpClient.PostForm(d.TokenEndpoint, form)
	if err != nil {
		return nil, fmt.Errorf("calling token endpoint: %w", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("token endpoint returned %d: %s", resp.StatusCode, string(body))
	}

	var t TokenResponse
	if err := json.Unmarshal(body, &t); err != nil {
		return nil, fmt.Errorf("decoding token response: %w", err)
	}
	return &t, nil
}

// Claims is the subset of ID/access token claims this client reads.
type Claims struct {
	Subject           string
	Email             string
	PreferredUsername string
	Groups            []string
	Expiry            time.Time
	Raw               map[string]interface{}
}

// VerifyIDToken validates the ID token's RS256 signature against the
// issuer's JWKS, checks exp/iss/aud, and returns its claims.
func (c *Client) VerifyIDToken(idToken string) (*Claims, error) {
	claimsMap, err := c.verifySignatureAndGetClaims(idToken)
	if err != nil {
		return nil, err
	}

	if iss, _ := claimsMap["iss"].(string); iss != "" {
		d, err := c.discover()
		if err == nil && d.Issuer != "" && iss != d.Issuer {
			return nil, fmt.Errorf("unexpected issuer %q", iss)
		}
	}
	if aud := claimsMap["aud"]; aud != nil {
		if !audienceContains(aud, c.ClientID) {
			return nil, fmt.Errorf("token audience does not include client_id %q", c.ClientID)
		}
	}

	return claimsFromMap(claimsMap), nil
}

func claimsFromMap(m map[string]interface{}) *Claims {
	c := &Claims{Raw: m}
	if v, ok := m["sub"].(string); ok {
		c.Subject = v
	}
	if v, ok := m["email"].(string); ok {
		c.Email = v
	}
	if v, ok := m["preferred_username"].(string); ok {
		c.PreferredUsername = v
	}
	if v, ok := m["exp"].(float64); ok {
		c.Expiry = time.Unix(int64(v), 0)
	}
	if raw, ok := m["groups"].([]interface{}); ok {
		for _, g := range raw {
			if s, ok := g.(string); ok {
				c.Groups = append(c.Groups, s)
			}
		}
	}
	return c
}

func audienceContains(aud interface{}, clientID string) bool {
	switch v := aud.(type) {
	case string:
		return v == clientID
	case []interface{}:
		for _, a := range v {
			if s, ok := a.(string); ok && s == clientID {
				return true
			}
		}
	}
	return false
}

// --- JWKS handling & RS256 verification (stdlib only) ---

type jwk struct {
	Kty string `json:"kty"`
	Kid string `json:"kid"`
	N   string `json:"n"`
	E   string `json:"e"`
	Alg string `json:"alg"`
}

type jwks struct {
	Keys []jwk `json:"keys"`
}

const jwksCacheTTL = 10 * time.Minute

func (c *Client) getJWKS() (*jwks, error) {
	c.mu.RLock()
	if c.jwks != nil && time.Since(c.jwksAt) < jwksCacheTTL {
		k := c.jwks
		c.mu.RUnlock()
		return k, nil
	}
	c.mu.RUnlock()

	d, err := c.discover()
	if err != nil {
		return nil, err
	}
	resp, err := c.httpClient.Get(d.JWKSURI)
	if err != nil {
		return nil, fmt.Errorf("fetching JWKS: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("JWKS endpoint returned %d", resp.StatusCode)
	}
	var k jwks
	if err := json.NewDecoder(resp.Body).Decode(&k); err != nil {
		return nil, fmt.Errorf("decoding JWKS: %w", err)
	}

	c.mu.Lock()
	c.jwks = &k
	c.jwksAt = time.Now()
	c.mu.Unlock()
	return &k, nil
}

func (c *Client) verifySignatureAndGetClaims(token string) (map[string]interface{}, error) {
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return nil, errors.New("malformed JWT")
	}

	headerJSON, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return nil, fmt.Errorf("decoding JWT header: %w", err)
	}
	var header struct {
		Alg string `json:"alg"`
		Kid string `json:"kid"`
	}
	if err := json.Unmarshal(headerJSON, &header); err != nil {
		return nil, fmt.Errorf("parsing JWT header: %w", err)
	}
	if header.Alg != "RS256" {
		return nil, fmt.Errorf("unsupported JWT alg %q (only RS256 is accepted)", header.Alg)
	}

	set, err := c.getJWKS()
	if err != nil {
		return nil, err
	}
	var key *jwk
	for i := range set.Keys {
		if set.Keys[i].Kid == header.Kid {
			key = &set.Keys[i]
			break
		}
	}
	if key == nil {
		return nil, fmt.Errorf("no JWKS key found for kid %q", header.Kid)
	}

	pub, err := rsaPublicKeyFromJWK(*key)
	if err != nil {
		return nil, err
	}

	signingInput := parts[0] + "." + parts[1]
	sig, err := base64.RawURLEncoding.DecodeString(parts[2])
	if err != nil {
		return nil, fmt.Errorf("decoding JWT signature: %w", err)
	}
	hashed := sha256.Sum256([]byte(signingInput))
	if err := rsa.VerifyPKCS1v15(pub, crypto.SHA256, hashed[:], sig); err != nil {
		return nil, fmt.Errorf("JWT signature verification failed: %w", err)
	}

	payloadJSON, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return nil, fmt.Errorf("decoding JWT payload: %w", err)
	}
	var claims map[string]interface{}
	if err := json.Unmarshal(payloadJSON, &claims); err != nil {
		return nil, fmt.Errorf("parsing JWT payload: %w", err)
	}

	if expF, ok := claims["exp"].(float64); ok {
		if time.Now().After(time.Unix(int64(expF), 0)) {
			return nil, errors.New("JWT has expired")
		}
	}

	return claims, nil
}

func rsaPublicKeyFromJWK(k jwk) (*rsa.PublicKey, error) {
	nBytes, err := base64.RawURLEncoding.DecodeString(k.N)
	if err != nil {
		return nil, fmt.Errorf("decoding JWK modulus: %w", err)
	}
	eBytes, err := base64.RawURLEncoding.DecodeString(k.E)
	if err != nil {
		return nil, fmt.Errorf("decoding JWK exponent: %w", err)
	}
	n := new(big.Int).SetBytes(nBytes)
	e := new(big.Int).SetBytes(eBytes)
	return &rsa.PublicKey{N: n, E: int(e.Int64())}, nil
}

func randomURLSafeString(n int) (string, error) {
	buf := make([]byte, n)
	if _, err := rand.Read(buf); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(buf), nil
}
