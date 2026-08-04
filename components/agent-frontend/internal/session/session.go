// Package session implements a minimal signed-cookie session so
// agent-frontend stays stateless (no server-side session store to run or
// secure). The cookie carries exactly what the portal and chat proxy need:
// the authenticated subject, group memberships (for tile gating) and the
// raw OIDC access token (forwarded to the BFF as a Bearer credential, per
// ADR-0013 identity propagation). The cookie is HMAC-signed with a secret
// sourced from Vault (ADR-0024) so it cannot be forged or tampered with
// client-side; it is not encrypted, so it must never carry anything beyond
// what the browser is already trusted to see (no client secret, ever).
package session

import (
	"crypto/hmac"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/json"
	"errors"
	"net/http"
	"time"
)

const cookieName = "zuno_session"

// Session is the authenticated state carried in the cookie.
type Session struct {
	Subject     string    `json:"sub"`
	Email       string    `json:"email,omitempty"`
	Groups      []string  `json:"groups"`
	AccessToken string    `json:"access_token"`
	IDToken     string    `json:"id_token"`
	ExpiresAt   time.Time `json:"expires_at"`
}

// Expired reports whether the session's access token has already expired.
func (s Session) Expired() bool {
	return time.Now().After(s.ExpiresAt)
}

// Manager signs and verifies session cookies with an HMAC secret.
type Manager struct {
	secret []byte
	secure bool
}

// NewManager builds a Manager. secure controls the cookie's Secure flag —
// true in every real deployment (frontend is only ever served over TLS
// behind an OpenShift Route), false only for local plain-HTTP development.
func NewManager(secret []byte, secure bool) *Manager {
	return &Manager{secret: secret, secure: secure}
}

// Save writes a signed session cookie.
func (m *Manager) Save(w http.ResponseWriter, s Session) error {
	payload, err := json.Marshal(s)
	if err != nil {
		return err
	}
	encoded := base64.RawURLEncoding.EncodeToString(payload)
	sig := m.sign(encoded)
	value := encoded + "." + sig

	http.SetCookie(w, &http.Cookie{
		Name:     cookieName,
		Value:    value,
		Path:     "/",
		HttpOnly: true,
		Secure:   m.secure,
		SameSite: http.SameSiteLaxMode,
		Expires:  s.ExpiresAt,
	})
	return nil
}

// Load reads and verifies the session cookie, if present and valid.
func (m *Manager) Load(r *http.Request) (*Session, error) {
	c, err := r.Cookie(cookieName)
	if err != nil {
		return nil, errors.New("no session cookie")
	}

	encoded, sig, ok := splitOnce(c.Value, '.')
	if !ok {
		return nil, errors.New("malformed session cookie")
	}
	expected := m.sign(encoded)
	if subtle.ConstantTimeCompare([]byte(sig), []byte(expected)) != 1 {
		return nil, errors.New("session signature mismatch")
	}

	payload, err := base64.RawURLEncoding.DecodeString(encoded)
	if err != nil {
		return nil, err
	}
	var s Session
	if err := json.Unmarshal(payload, &s); err != nil {
		return nil, err
	}
	if s.Expired() {
		return nil, errors.New("session expired")
	}
	return &s, nil
}

// Clear removes the session cookie (logout).
func (m *Manager) Clear(w http.ResponseWriter) {
	http.SetCookie(w, &http.Cookie{
		Name:     cookieName,
		Value:    "",
		Path:     "/",
		HttpOnly: true,
		Secure:   m.secure,
		SameSite: http.SameSiteLaxMode,
		MaxAge:   -1,
	})
}

// SaveValue signs and stores an arbitrary JSON-serializable value in a
// short-lived named cookie. Used for the transient OIDC authorization
// request (state/nonce/PKCE verifier) between /login and /callback, which
// has nothing to do with the authenticated Session type above but needs
// the same tamper-evidence guarantee.
func (m *Manager) SaveValue(w http.ResponseWriter, name string, v interface{}, maxAge time.Duration) error {
	payload, err := json.Marshal(v)
	if err != nil {
		return err
	}
	encoded := base64.RawURLEncoding.EncodeToString(payload)
	sig := m.sign(encoded)

	http.SetCookie(w, &http.Cookie{
		Name:     name,
		Value:    encoded + "." + sig,
		Path:     "/",
		HttpOnly: true,
		Secure:   m.secure,
		SameSite: http.SameSiteLaxMode,
		MaxAge:   int(maxAge.Seconds()),
	})
	return nil
}

// LoadValue verifies and decodes a cookie previously written by SaveValue.
func (m *Manager) LoadValue(r *http.Request, name string, v interface{}) error {
	c, err := r.Cookie(name)
	if err != nil {
		return errors.New("no cookie: " + name)
	}
	encoded, sig, ok := splitOnce(c.Value, '.')
	if !ok {
		return errors.New("malformed cookie: " + name)
	}
	if subtle.ConstantTimeCompare([]byte(sig), []byte(m.sign(encoded))) != 1 {
		return errors.New("signature mismatch: " + name)
	}
	payload, err := base64.RawURLEncoding.DecodeString(encoded)
	if err != nil {
		return err
	}
	return json.Unmarshal(payload, v)
}

// ClearValue removes a cookie previously written by SaveValue.
func (m *Manager) ClearValue(w http.ResponseWriter, name string) {
	http.SetCookie(w, &http.Cookie{
		Name:     name,
		Value:    "",
		Path:     "/",
		HttpOnly: true,
		Secure:   m.secure,
		SameSite: http.SameSiteLaxMode,
		MaxAge:   -1,
	})
}

func (m *Manager) sign(data string) string {
	mac := hmac.New(sha256.New, m.secret)
	mac.Write([]byte(data))
	return base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
}

func splitOnce(s string, sep byte) (string, string, bool) {
	for i := 0; i < len(s); i++ {
		if s[i] == sep {
			return s[:i], s[i+1:], true
		}
	}
	return "", "", false
}
