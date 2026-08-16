// Package session implements ADR-0042's opaque browser session: the
// cookie carries only a random, HMAC-signed session ID (never a token),
// while the authenticated state - subject, group memberships, access
// token, ID token, refresh token, expiry - lives server-side in Redis
// (see store.go), encrypted at rest. Prior to ADR-0042 the cookie itself
// carried a signed-but-unencrypted JSON blob of that state directly;
// moving it server-side lets a session be revoked (Delete), refreshed
// transparently (see Refresher below) without forcing re-login, and grow
// state (delegated provider tokens) without approaching cookie size
// limits.
package session

import (
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/json"
	"errors"
	"net/http"
	"time"
)

const cookieName = "zuno_session"

// Session is the authenticated state stored server-side, keyed by the
// opaque ID the browser holds.
type Session struct {
	Subject           string    `json:"sub"`
	Email             string    `json:"email,omitempty"`
	PreferredUsername string    `json:"preferred_username,omitempty"`
	Groups            []string  `json:"groups"`
	AccessToken       string    `json:"access_token"`
	IDToken           string    `json:"id_token"`
	RefreshToken      string    `json:"refresh_token,omitempty"`
	ExpiresAt         time.Time `json:"expires_at"`
}

// Expired reports whether the session's access token has already expired
// (a signal to refresh, not necessarily that the session itself is dead -
// see Refresher).
func (s Session) Expired() bool {
	return time.Now().After(s.ExpiresAt)
}

// DisplayName returns the best available human-readable name for the
// session: preferred_username, falling back to email, then the raw
// subject (sub) claim if neither is present.
func (s Session) DisplayName() string {
	if s.PreferredUsername != "" {
		return s.PreferredUsername
	}
	if s.Email != "" {
		return s.Email
	}
	return s.Subject
}

// Refresher exchanges a refresh token for a new token set. Implemented by
// oidc.Client.Refresh; kept as a narrow function type here so this
// package doesn't import internal/oidc (session is the lower-level,
// storage-focused package - oidc is wired in at construction by main.go).
// Returning an error is treated as "the refresh token is no longer
// valid" - the caller must fail closed (ADR-0032/0033: never trust a
// cached claim past its validated lifetime).
type Refresher func(refreshToken string) (accessToken, idToken, refreshTokenOut string, expiresIn int64, err error)

// Manager signs/verifies the opaque-session-ID cookie and resolves it
// against a server-side Store, refreshing transparently when possible.
type Manager struct {
	secret      []byte
	secure      bool
	store       *Store
	maxLifetime time.Duration
	refresh     Refresher
}

// NewManager builds a Manager. secure controls the cookie's Secure flag -
// true in every real deployment (frontend is only ever served over TLS
// behind an OpenShift Route), false only for local plain-HTTP
// development. maxLifetime bounds how long a session record survives in
// Redis regardless of how many times its access token gets refreshed -
// ADR-0042's "revocable... TTL", distinct from the short-lived access
// token's own expiry.
func NewManager(secret []byte, secure bool, store *Store, maxLifetime time.Duration, refresh Refresher) *Manager {
	return &Manager{secret: secret, secure: secure, store: store, maxLifetime: maxLifetime, refresh: refresh}
}

// Save creates a new server-side session record and writes the opaque,
// signed session-ID cookie referencing it.
func (m *Manager) Save(w http.ResponseWriter, s Session) error {
	id, err := randomID()
	if err != nil {
		return err
	}
	if err := m.store.Put(context.Background(), id, s, m.maxLifetime); err != nil {
		return err
	}
	m.setCookie(w, id, time.Now().Add(m.maxLifetime))
	return nil
}

// Load resolves the session-ID cookie against the server-side store. If
// the stored access token has expired and a refresh token is present, it
// transparently refreshes and persists the updated token set before
// returning - callers (chat/portal handlers) never see the refresh
// happen, they just always get a currently-valid session or an error.
func (m *Manager) Load(r *http.Request) (*Session, error) {
	id, err := m.sessionID(r)
	if err != nil {
		return nil, err
	}

	s, err := m.store.Get(context.Background(), id)
	if err != nil {
		return nil, err
	}

	if !s.Expired() {
		return s, nil
	}
	if s.RefreshToken == "" || m.refresh == nil {
		return nil, errors.New("session expired and no refresh token is available")
	}

	accessToken, idToken, refreshToken, expiresIn, err := m.refresh(s.RefreshToken)
	if err != nil {
		// Fail closed (ADR-0032/0033): a refresh failure - including the
		// refresh token itself having expired or been revoked at
		// Keycloak - must not leave a stale, still-"valid" session
		// usable. Revoke the server-side record too, not just reject
		// this one request.
		_ = m.store.Delete(context.Background(), id)
		return nil, err
	}

	s.AccessToken = accessToken
	s.IDToken = idToken
	if refreshToken != "" {
		s.RefreshToken = refreshToken
	}
	if expiresIn > 0 {
		s.ExpiresAt = time.Now().Add(time.Duration(expiresIn) * time.Second)
	}
	if err := m.store.Put(context.Background(), id, *s, m.maxLifetime); err != nil {
		return nil, err
	}
	return s, nil
}

// Clear revokes the server-side session record (if any) and removes the
// browser cookie - real revocation, not just "the browser forgot it".
func (m *Manager) Clear(w http.ResponseWriter, r *http.Request) {
	if id, err := m.sessionID(r); err == nil {
		_ = m.store.Delete(context.Background(), id)
	}
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

func (m *Manager) sessionID(r *http.Request) (string, error) {
	c, err := r.Cookie(cookieName)
	if err != nil {
		return "", errors.New("no session cookie")
	}
	id, sig, ok := splitOnce(c.Value, '.')
	if !ok {
		return "", errors.New("malformed session cookie")
	}
	expected := m.sign(id)
	if subtle.ConstantTimeCompare([]byte(sig), []byte(expected)) != 1 {
		return "", errors.New("session signature mismatch")
	}
	return id, nil
}

func (m *Manager) setCookie(w http.ResponseWriter, id string, expires time.Time) {
	value := id + "." + m.sign(id)
	http.SetCookie(w, &http.Cookie{
		Name:     cookieName,
		Value:    value,
		Path:     "/",
		HttpOnly: true,
		Secure:   m.secure,
		SameSite: http.SameSiteLaxMode,
		Expires:  expires,
	})
}

// SaveValue signs and stores an arbitrary JSON-serializable value in a
// short-lived named cookie. Used for the transient OIDC authorization
// request (state/nonce/PKCE verifier) between /login and /callback, which
// has nothing to do with the authenticated Session type above but needs
// the same tamper-evidence guarantee. Unlike Session, this transient,
// small, non-token data still travels directly in a signed cookie -
// ADR-0042 is about token storage, not every cookie this service sets.
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

func randomID() (string, error) {
	buf := make([]byte, 32)
	if _, err := rand.Read(buf); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(buf), nil
}

func splitOnce(s string, sep byte) (string, string, bool) {
	for i := 0; i < len(s); i++ {
		if s[i] == sep {
			return s[:i], s[i+1:], true
		}
	}
	return "", "", false
}
