// Package jwks validates the bearer JWT the frontend forwards on every
// /api/chat call, against Keycloak's published JWKS. This is the BFF's own
// independent identity check (ADR-0013 identity propagation: the BFF must
// not simply trust that the frontend already checked authorization — it
// revalidates the token's signature, issuer, audience and expiry itself).
//
// ASSUMPTION: at the time this was written, platform/identity/README.md
// (where a parallel identity track would document the exact
// identity-propagation contract) did not yet exist. This package implements
// standard OIDC JWKS validation against
// "<issuer>/protocol/openid-connect/certs" (Keycloak's conventional JWKS
// path) rather than the discovery-document jwks_uri, since the BFF has no
// need for the rest of the discovery document. If platform/identity/README.md
// later documents something different (e.g. a sidecar-validated identity
// header instead of a raw bearer JWT), this package is the one to update.
//
// Implemented against the Go standard library only — see
// components/agent-frontend/internal/oidc's package comment for why this
// track avoided third-party OIDC/JWT libraries in this sandboxed
// environment; the same reasoning applies here, and the two packages
// deliberately duplicate this small amount of RS256/JWKS code rather than
// share a module across two independently deployed services.
package jwks

import (
	"crypto"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"math/big"
	"net/http"
	"strings"
	"sync"
	"time"
)

type key struct {
	Kty string `json:"kty"`
	Kid string `json:"kid"`
	N   string `json:"n"`
	E   string `json:"e"`
	Alg string `json:"alg"`
}

type keySet struct {
	Keys []key `json:"keys"`
}

// Verifier validates RS256-signed JWTs against one issuer's JWKS.
type Verifier struct {
	issuerURL  string
	certsURL   string
	audience   string
	httpClient *http.Client

	mu    sync.RWMutex
	set   *keySet
	setAt time.Time
}

const cacheTTL = 10 * time.Minute

// NewVerifier builds a Verifier for the given issuer. audience is the
// expected `aud`/`azp` claim (the frontend client ID that requested the
// token); pass "" to skip audience checking.
func NewVerifier(issuerURL, audience string) *Verifier {
	issuerURL = strings.TrimRight(issuerURL, "/")
	return &Verifier{
		issuerURL:  issuerURL,
		certsURL:   issuerURL + "/protocol/openid-connect/certs",
		audience:   audience,
		httpClient: &http.Client{Timeout: 10 * time.Second},
	}
}

// Claims is the subset of access-token claims the BFF needs.
type Claims struct {
	Subject string
	Email   string
	Groups  []string
	Expiry  time.Time
}

// Verify validates a bearer token's RS256 signature, issuer, audience and
// expiry, and returns its claims.
func (v *Verifier) Verify(token string) (*Claims, error) {
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

	set, err := v.getKeySet()
	if err != nil {
		return nil, err
	}
	var k *key
	for i := range set.Keys {
		if set.Keys[i].Kid == header.Kid {
			k = &set.Keys[i]
			break
		}
	}
	if k == nil {
		return nil, fmt.Errorf("no JWKS key found for kid %q", header.Kid)
	}

	pub, err := rsaPublicKeyFromJWK(*k)
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
	} else {
		return nil, errors.New("JWT missing exp claim")
	}

	if iss, _ := claims["iss"].(string); iss != "" && iss != v.issuerURL {
		return nil, fmt.Errorf("unexpected issuer %q", iss)
	}

	if v.audience != "" {
		if !audienceMatches(claims, v.audience) {
			return nil, fmt.Errorf("token audience/authorized-party does not include %q", v.audience)
		}
	}

	return claimsFromMap(claims), nil
}

func audienceMatches(claims map[string]interface{}, expected string) bool {
	if azp, ok := claims["azp"].(string); ok && azp == expected {
		return true
	}
	switch aud := claims["aud"].(type) {
	case string:
		return aud == expected
	case []interface{}:
		for _, a := range aud {
			if s, ok := a.(string); ok && s == expected {
				return true
			}
		}
	}
	return false
}

func claimsFromMap(m map[string]interface{}) *Claims {
	c := &Claims{}
	if v, ok := m["sub"].(string); ok {
		c.Subject = v
	}
	if v, ok := m["email"].(string); ok {
		c.Email = v
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

func (v *Verifier) getKeySet() (*keySet, error) {
	v.mu.RLock()
	if v.set != nil && time.Since(v.setAt) < cacheTTL {
		s := v.set
		v.mu.RUnlock()
		return s, nil
	}
	v.mu.RUnlock()

	resp, err := v.httpClient.Get(v.certsURL)
	if err != nil {
		return nil, fmt.Errorf("fetching JWKS from %q: %w", v.certsURL, err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("JWKS endpoint %q returned %d", v.certsURL, resp.StatusCode)
	}
	var s keySet
	if err := json.NewDecoder(resp.Body).Decode(&s); err != nil {
		return nil, fmt.Errorf("decoding JWKS: %w", err)
	}

	v.mu.Lock()
	v.set = &s
	v.setAt = time.Now()
	v.mu.Unlock()
	return &s, nil
}

func rsaPublicKeyFromJWK(k key) (*rsa.PublicKey, error) {
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
