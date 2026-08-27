// Package keycloak is a client-credentials-grant HTTP client against
// Keycloak's Admin REST API (ADR-0213) - a genuinely new outbound trust
// boundary for agent-bff, which otherwise only performs read-only JWKS
// token verification (internal/jwks). Deliberately separate from that
// package: this one authenticates with a *service* credential
// (KEYCLOAK_ADMIN_CLIENT_ID/_SECRET, Vault-seeded, scoped to
// realm-management view-users/query-users only - never manage-users),
// not a caller's own bearer token.
package keycloak

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"sync"
	"time"
)

// AdminClient searches Keycloak users and reads their group membership
// via the zuno realm's Admin REST API.
type AdminClient struct {
	baseURL      string // in-cluster-reachable Keycloak base, e.g. http://keycloak-service.zuno-auth.svc.cluster.local:8080
	realm        string
	clientID     string
	clientSecret string
	httpClient   *http.Client

	mu          sync.Mutex
	accessToken string
	expiresAt   time.Time
}

// NewAdminClient returns nil if baseURL, clientID or clientSecret is
// empty - the zuno-admin-api trust boundary is provisioned as a separate
// operator step (ADR-0213's own Security considerations: needs explicit
// reviewer sign-off), not something a fresh deploy has by default.
// Callers must check for a nil AdminClient and fail closed (503) rather
// than silently skipping colleague search.
func NewAdminClient(baseURL, realm, clientID, clientSecret string) *AdminClient {
	if baseURL == "" || clientID == "" || clientSecret == "" {
		return nil
	}
	return &AdminClient{
		baseURL:      strings.TrimSuffix(baseURL, "/"),
		realm:        realm,
		clientID:     clientID,
		clientSecret: clientSecret,
		httpClient:   &http.Client{Timeout: 10 * time.Second},
	}
}

// User is one Keycloak user search result.
type User struct {
	ID        string `json:"id"`
	Username  string `json:"username"`
	Email     string `json:"email"`
	FirstName string `json:"firstName"`
	LastName  string `json:"lastName"`
}

// DisplayName follows session.Session.DisplayName()'s own precedence
// elsewhere in this codebase: the best human-readable name available,
// never empty for a real Keycloak user (Username is always set).
func (u User) DisplayName() string {
	name := strings.TrimSpace(u.FirstName + " " + u.LastName)
	if name != "" {
		return name
	}
	if u.Username != "" {
		return u.Username
	}
	return u.Email
}

// token performs (or reuses a cached) client-credentials grant against
// this realm's token endpoint. Cached with a 30s early-expiry margin so
// a request never races a token that's about to expire mid-call.
func (c *AdminClient) token(ctx context.Context) (string, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.accessToken != "" && time.Now().Before(c.expiresAt) {
		return c.accessToken, nil
	}

	form := url.Values{
		"grant_type":    {"client_credentials"},
		"client_id":     {c.clientID},
		"client_secret": {c.clientSecret},
	}
	tokenURL := fmt.Sprintf("%s/realms/%s/protocol/openid-connect/token", c.baseURL, c.realm)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, tokenURL, strings.NewReader(form.Encode()))
	if err != nil {
		return "", fmt.Errorf("building admin token request: %w", err)
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return "", fmt.Errorf("requesting admin token: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("admin token request returned %d", resp.StatusCode)
	}

	var body struct {
		AccessToken string `json:"access_token"`
		ExpiresIn   int    `json:"expires_in"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		return "", fmt.Errorf("decoding admin token response: %w", err)
	}
	c.accessToken = body.AccessToken
	margin := body.ExpiresIn - 30
	if margin < 1 {
		margin = 1
	}
	c.expiresAt = time.Now().Add(time.Duration(margin) * time.Second)
	return c.accessToken, nil
}

func (c *AdminClient) adminGet(ctx context.Context, path string, query url.Values, out any) error {
	token, err := c.token(ctx)
	if err != nil {
		return err
	}

	reqURL := fmt.Sprintf("%s/admin/realms/%s%s", c.baseURL, c.realm, path)
	if len(query) > 0 {
		reqURL += "?" + query.Encode()
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return fmt.Errorf("building admin API request: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+token)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("calling Keycloak admin API at %q: %w", reqURL, err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("Keycloak admin API returned %d for %q", resp.StatusCode, reqURL)
	}
	if err := json.NewDecoder(resp.Body).Decode(out); err != nil {
		return fmt.Errorf("decoding Keycloak admin API response: %w", err)
	}
	return nil
}

// SearchUsers calls GET /admin/realms/{realm}/users?search=q, capped at
// 20 results - callers (main.go's colleague-search handler) are
// expected to debounce and this is a "type ahead" search, not a bulk
// export.
func (c *AdminClient) SearchUsers(ctx context.Context, query string) ([]User, error) {
	var out []User
	q := url.Values{"search": {query}, "max": {strconv.Itoa(20)}}
	if err := c.adminGet(ctx, "/users", q, &out); err != nil {
		return nil, err
	}
	return out, nil
}

type groupRef struct {
	Path string `json:"path"`
}

// UserGroups calls GET /admin/realms/{realm}/users/{id}/groups and
// returns each group's bare name (leading "/" stripped, matching the
// caller's own JWT "groups" claim convention this codebase already uses
// elsewhere - see main.go's hasGroup).
func (c *AdminClient) UserGroups(ctx context.Context, userID string) ([]string, error) {
	var refs []groupRef
	if err := c.adminGet(ctx, "/users/"+url.PathEscape(userID)+"/groups", nil, &refs); err != nil {
		return nil, err
	}
	groups := make([]string, len(refs))
	for i, g := range refs {
		groups[i] = strings.TrimPrefix(g.Path, "/")
	}
	return groups, nil
}

// Group is one realm group (ADR-0527's GET /api/groups).
type Group struct {
	ID   string `json:"id"`
	Name string `json:"name"`
	Path string `json:"path"`
}

// RealmGroups calls GET /admin/realms/{realm}/groups and returns every
// top-level realm group.
//
// This needs the realm-management `query-groups` role on the zuno-admin-api
// service account, IN ADDITION to WP-066's view-users/query-users - never
// manage-users, never manage-realm, per ADR-0213's least-privilege
// constraint which ADR-0527 inherits. Without it Keycloak answers 403,
// which adminGet surfaces as an error and the caller must turn into a 503:
// a silently empty group list would read as "this realm has no groups" and
// quietly prevent every group grant.
func (c *AdminClient) RealmGroups(ctx context.Context) ([]Group, error) {
	// briefRepresentation omits sub-groups and attributes - this endpoint
	// only ever offers top-level business-role groups as grant targets.
	query := url.Values{}
	query.Set("briefRepresentation", "true")
	var groups []Group
	if err := c.adminGet(ctx, "/groups", query, &groups); err != nil {
		return nil, err
	}
	return groups, nil
}
