package session

import (
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"
)

// Requires a real Redis reachable at TEST_REDIS_ADDR (default
// localhost:6379) - ADR-0042's store.go talks to a real redis.Client, not
// a fake, so these tests prove genuine behavior against the real thing.
func testStore(t *testing.T) *Store {
	t.Helper()
	addr := os.Getenv("TEST_REDIS_ADDR")
	if addr == "" {
		addr = "localhost:6379"
	}
	key := make([]byte, 32)
	for i := range key {
		key[i] = byte(i)
	}
	st, err := NewStore(addr, "", 0, key)
	if err != nil {
		t.Fatalf("NewStore: %v", err)
	}
	return st
}

func extractCookie(rec *httptest.ResponseRecorder, name string) *http.Cookie {
	for _, c := range rec.Result().Cookies() {
		if c.Name == name {
			return c
		}
	}
	return nil
}

func TestSaveLoadRoundTrip(t *testing.T) {
	store := testStore(t)
	m := NewManager([]byte("test-hmac-secret"), true, store, time.Hour, nil)

	sess := Session{
		Subject:     "user-1",
		Email:       "user-1@example.com",
		Groups:      []string{"sales", "agent_comage"},
		AccessToken: "access-token-value",
		IDToken:     "id-token-value",
		ExpiresAt:   time.Now().Add(time.Hour),
	}

	rec := httptest.NewRecorder()
	if err := m.Save(rec, sess); err != nil {
		t.Fatalf("Save: %v", err)
	}
	cookie := extractCookie(rec, cookieName)
	if cookie == nil {
		t.Fatal("no zuno_session cookie set by Save")
	}
	if len(cookie.Value) == 0 {
		t.Fatal("cookie value is empty")
	}
	// The cookie must never carry the raw access token in the clear -
	// that's the entire point of ADR-0042.
	if containsSubstring(cookie.Value, "access-token-value") {
		t.Fatal("cookie value leaks the raw access token - opaque session ID expected")
	}

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.AddCookie(cookie)

	loaded, err := m.Load(req)
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if loaded.Subject != sess.Subject || loaded.AccessToken != sess.AccessToken {
		t.Fatalf("loaded session does not match saved session: %+v", loaded)
	}
}

func TestClearRevokesServerSideSession(t *testing.T) {
	store := testStore(t)
	m := NewManager([]byte("test-hmac-secret"), true, store, time.Hour, nil)

	sess := Session{Subject: "user-2", ExpiresAt: time.Now().Add(time.Hour)}
	rec := httptest.NewRecorder()
	if err := m.Save(rec, sess); err != nil {
		t.Fatalf("Save: %v", err)
	}
	cookie := extractCookie(rec, cookieName)

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.AddCookie(cookie)

	clearRec := httptest.NewRecorder()
	m.Clear(clearRec, req)

	// Re-use the ORIGINAL cookie (simulating an attacker who captured it
	// before logout/revocation) against a fresh request - it must no
	// longer resolve, proving Clear revokes server-side, not just clears
	// the caller's own browser cookie.
	req2 := httptest.NewRequest(http.MethodGet, "/", nil)
	req2.AddCookie(cookie)
	if _, err := m.Load(req2); err == nil {
		t.Fatal("Load succeeded after Clear - session was not actually revoked server-side")
	}
}

func TestTamperedCookieRejected(t *testing.T) {
	store := testStore(t)
	m := NewManager([]byte("test-hmac-secret"), true, store, time.Hour, nil)

	sess := Session{Subject: "user-3", ExpiresAt: time.Now().Add(time.Hour)}
	rec := httptest.NewRecorder()
	if err := m.Save(rec, sess); err != nil {
		t.Fatalf("Save: %v", err)
	}
	cookie := extractCookie(rec, cookieName)
	cookie.Value = cookie.Value + "tampered"

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.AddCookie(cookie)
	if _, err := m.Load(req); err == nil {
		t.Fatal("Load succeeded on a tampered cookie signature")
	}
}

func TestLoadRefreshesExpiredAccessTokenTransparently(t *testing.T) {
	store := testStore(t)
	refreshCalls := 0
	refresher := func(refreshToken string) (string, string, string, int64, error) {
		refreshCalls++
		if refreshToken != "the-refresh-token" {
			t.Fatalf("unexpected refresh token passed to Refresher: %q", refreshToken)
		}
		return "new-access-token", "new-id-token", "new-refresh-token", 3600, nil
	}
	m := NewManager([]byte("test-hmac-secret"), true, store, time.Hour, refresher)

	sess := Session{
		Subject:      "user-4",
		AccessToken:  "old-access-token",
		RefreshToken: "the-refresh-token",
		ExpiresAt:    time.Now().Add(-time.Minute), // already expired
	}
	rec := httptest.NewRecorder()
	if err := m.Save(rec, sess); err != nil {
		t.Fatalf("Save: %v", err)
	}
	cookie := extractCookie(rec, cookieName)

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.AddCookie(cookie)
	loaded, err := m.Load(req)
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if refreshCalls != 1 {
		t.Fatalf("expected exactly 1 refresh call, got %d", refreshCalls)
	}
	if loaded.AccessToken != "new-access-token" || loaded.RefreshToken != "new-refresh-token" {
		t.Fatalf("session was not updated with refreshed tokens: %+v", loaded)
	}
	if loaded.Expired() {
		t.Fatal("refreshed session reports as still expired")
	}

	// A second Load must see the already-refreshed, now-valid session
	// persisted in the store, not refresh again.
	req2 := httptest.NewRequest(http.MethodGet, "/", nil)
	req2.AddCookie(cookie)
	if _, err := m.Load(req2); err != nil {
		t.Fatalf("second Load: %v", err)
	}
	if refreshCalls != 1 {
		t.Fatalf("expected refresh to happen only once, got %d calls", refreshCalls)
	}
}

func TestLoadFailsClosedAndRevokesOnRefreshError(t *testing.T) {
	store := testStore(t)
	refresher := func(refreshToken string) (string, string, string, int64, error) {
		return "", "", "", 0, errRefreshRejected
	}
	m := NewManager([]byte("test-hmac-secret"), true, store, time.Hour, refresher)

	sess := Session{
		Subject:      "user-5",
		RefreshToken: "a-refresh-token",
		ExpiresAt:    time.Now().Add(-time.Minute),
	}
	rec := httptest.NewRecorder()
	if err := m.Save(rec, sess); err != nil {
		t.Fatalf("Save: %v", err)
	}
	cookie := extractCookie(rec, cookieName)

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.AddCookie(cookie)
	if _, err := m.Load(req); err == nil {
		t.Fatal("Load succeeded despite a rejected refresh")
	}

	// The record must be gone, not just this one request rejected.
	req2 := httptest.NewRequest(http.MethodGet, "/", nil)
	req2.AddCookie(cookie)
	if _, err := m.Load(req2); err == nil {
		t.Fatal("session still resolvable after a failed refresh - not revoked server-side")
	}
}

var errRefreshRejected = &testError{"refresh token rejected by identity provider"}

type testError struct{ msg string }

func (e *testError) Error() string { return e.msg }

func containsSubstring(haystack, needle string) bool {
	return len(needle) > 0 && len(haystack) >= len(needle) && indexOf(haystack, needle) >= 0
}

func indexOf(haystack, needle string) int {
	for i := 0; i+len(needle) <= len(haystack); i++ {
		if haystack[i:i+len(needle)] == needle {
			return i
		}
	}
	return -1
}
