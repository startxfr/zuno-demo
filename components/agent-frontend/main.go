// Command agent-frontend serves the Zuno agent portal (one tile per agent,
// gated on OIDC group membership) and, for the one active agent this
// deployment is configured for, a PatternFly-styled chat UI that proxies to
// that agent's BFF. See components/agent-frontend/README.md for the full
// design, and ADR-0008 for why this single codebase is deployed once per
// agent rather than forked.
package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/assets"
	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/chat"
	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/config"
	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/oidc"
	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/okf"
	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/portal"
	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/profile"
	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/session"
)

// staticBase must match web/vite.config.ts's build.base.
const staticBase = "/static/"

const oidcTxnCookie = "zuno_oidc_txn"

func main() {
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("agent-frontend: configuration error: %v", err)
	}

	agents, err := okf.LoadAll(cfg.AgentsDir)
	if err != nil {
		log.Fatalf("agent-frontend: loading agent.okf.md bundles from %q: %v", cfg.AgentsDir, err)
	}
	activeAgent, found := okf.Find(agents, cfg.ActiveAgent)
	if !found {
		log.Fatalf("agent-frontend: ACTIVE_AGENT %q not found under %q", cfg.ActiveAgent, cfg.AgentsDir)
	}
	if !activeAgent.IsActive() {
		log.Printf("agent-frontend: warning: ACTIVE_AGENT %q has status %q, not \"active\" - its chat UI will refuse all traffic as unauthorized by design", cfg.ActiveAgent, activeAgent.Zuno.Status)
	}
	log.Printf("agent-frontend: loaded %d agent definitions from %q; serving chat UI for %q", len(agents), cfg.AgentsDir, cfg.ActiveAgent)

	// clusterBaseDomain is the platform-wide Route suffix (e.g.
	// "apps.demo222.startx.fr") shared by every agent-frontend Deployment -
	// derived from this pod's own external URL rather than a new env var,
	// since every agent's hostname follows the same "<name>.<domain>"
	// pattern (ADR-0008). See portal.BuildTiles's doc comment.
	clusterBaseDomain := strings.TrimPrefix(cfg.SelfBaseURL, "https://"+cfg.ActiveAgent+".")

	// ADR-0044: the Vite build (components/agent-frontend/web) must run
	// before this server starts - `npm run build` locally, or the
	// Dockerfile's Node stage in the image. manifest.Entry resolves each
	// page's content-hashed JS/CSS; see internal/assets.
	manifestPath := filepath.Join(cfg.WebDistDir, ".vite", "manifest.json")
	manifest, err := assets.Load(manifestPath, staticBase)
	if err != nil {
		log.Fatalf("agent-frontend: %v", err)
	}
	portalAsset, err := manifest.Entry("src/portal/main.tsx")
	if err != nil {
		log.Fatalf("agent-frontend: %v", err)
	}
	chatAsset, err := manifest.Entry("src/chat/main.tsx")
	if err != nil {
		log.Fatalf("agent-frontend: %v", err)
	}
	profileAsset, err := manifest.Entry("src/profile/main.tsx")
	if err != nil {
		log.Fatalf("agent-frontend: %v", err)
	}

	oidcClient, err := oidc.NewClient(cfg.KeycloakIssuerURL, cfg.OIDCClientID, cfg.OIDCClientSecret, cfg.OIDCRedirectURL, cfg.KeycloakCACertPath)
	if err != nil {
		log.Fatalf("agent-frontend: building OIDC client: %v", err)
	}

	// ADR-0042: server-side session store (Redis, encrypted at rest) -
	// the opaque session-ID cookie resolves through this, never carrying
	// tokens itself.
	store, err := session.NewStore(cfg.RedisAddr, cfg.RedisPassword, 0, cfg.SessionEncryptionKey)
	if err != nil {
		log.Fatalf("agent-frontend: building session store: %v", err)
	}
	pingCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := store.Ping(pingCtx); err != nil {
		log.Fatalf("agent-frontend: Redis session store unreachable at %q: %v", cfg.RedisAddr, err)
	}

	refresher := func(refreshToken string) (accessToken, idToken, refreshTokenOut string, expiresIn int64, err error) {
		t, err := oidcClient.Refresh(refreshToken)
		if err != nil {
			return "", "", "", 0, err
		}
		return t.AccessToken, t.IDToken, t.RefreshToken, t.ExpiresIn, nil
	}
	sessions := session.NewManager(cfg.SessionHMACSecret, isSecureBaseURL(cfg.SelfBaseURL), store, cfg.SessionMaxLifetime, refresher)

	mux := http.NewServeMux()

	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})

	mux.Handle(staticBase, http.StripPrefix(staticBase, http.FileServer(http.Dir(cfg.WebDistDir))))

	mux.HandleFunc("/", portal.Handler(agents, sessions, portalAsset, clusterBaseDomain))
	mux.HandleFunc("/profile", profile.Handler(agents, sessions, profileAsset, clusterBaseDomain))

	mux.HandleFunc("/login", loginHandler(oidcClient, sessions))
	mux.HandleFunc("/callback", callbackHandler(oidcClient, sessions))
	mux.HandleFunc("/logout", logoutHandler(oidcClient, sessions, cfg.SelfBaseURL))

	mux.HandleFunc("/"+activeAgent.Zuno.Name, chat.PageHandler(activeAgent, agents, sessions, chatAsset, clusterBaseDomain))
	mux.HandleFunc("/api/chat", chat.APIHandler(activeAgent, cfg.BFFBaseURL, sessions))

	// ADR-0212: persistent conversations, same session-gated reverse-proxy
	// shape as /api/chat above but via one method/path-agnostic handler.
	conversationsProxy := chat.ConversationsProxyHandler(activeAgent, cfg.BFFBaseURL, sessions)
	mux.HandleFunc("GET /api/conversations", conversationsProxy)
	mux.HandleFunc("GET /api/conversations/{run_id}/transcript", conversationsProxy)
	mux.HandleFunc("PATCH /api/conversations/{run_id}", conversationsProxy)
	mux.HandleFunc("PUT /api/conversations/{run_id}/star", conversationsProxy)
	mux.HandleFunc("DELETE /api/conversations/{run_id}/star", conversationsProxy)
	mux.HandleFunc("DELETE /api/conversations/{run_id}", conversationsProxy)
	// ADR-0515: manual drag-reorder and irreversible hard-delete.
	mux.HandleFunc("PUT /api/conversations/reorder", conversationsProxy)
	mux.HandleFunc("DELETE /api/conversations/{run_id}/hard-delete", conversationsProxy)
	// ADR-0213: role-based conversation sharing - same generic proxy,
	// path/method-driven, no new handler logic needed.
	mux.HandleFunc("GET /api/conversations/{run_id}/members", conversationsProxy)
	mux.HandleFunc("PUT /api/conversations/{run_id}/members/{subject}", conversationsProxy)
	mux.HandleFunc("DELETE /api/conversations/{run_id}/members/{subject}", conversationsProxy)
	mux.HandleFunc("PATCH /api/conversations/{run_id}/owner", conversationsProxy)
	mux.HandleFunc("POST /api/conversations/{run_id}/clone", conversationsProxy)
	mux.HandleFunc("GET /api/colleagues", conversationsProxy)

	server := &http.Server{
		Addr:              cfg.ListenAddr,
		Handler:           mux,
		ReadHeaderTimeout: 10 * time.Second,
	}

	log.Printf("agent-frontend: listening on %s", cfg.ListenAddr)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("agent-frontend: server error: %v", err)
	}
}

func loginHandler(oidcClient *oidc.Client, sessions *session.Manager) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		req, err := oidc.NewAuthRequest()
		if err != nil {
			http.Error(w, "internal error", http.StatusInternalServerError)
			return
		}
		if err := sessions.SaveValue(w, oidcTxnCookie, req, 10*time.Minute); err != nil {
			http.Error(w, "internal error", http.StatusInternalServerError)
			return
		}
		authURL, err := oidcClient.AuthURL(req)
		if err != nil {
			http.Error(w, "identity provider unreachable", http.StatusBadGateway)
			return
		}
		http.Redirect(w, r, authURL, http.StatusFound)
	}
}

func callbackHandler(oidcClient *oidc.Client, sessions *session.Manager) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var txn oidc.AuthRequest
		if err := sessions.LoadValue(r, oidcTxnCookie, &txn); err != nil {
			http.Error(w, "missing or expired login attempt, please try again", http.StatusBadRequest)
			return
		}
		sessions.ClearValue(w, oidcTxnCookie)

		q := r.URL.Query()
		if errParam := q.Get("error"); errParam != "" {
			http.Error(w, "sign-in failed: "+errParam, http.StatusUnauthorized)
			return
		}
		if q.Get("state") != txn.State {
			http.Error(w, "state mismatch", http.StatusBadRequest)
			return
		}
		code := q.Get("code")
		if code == "" {
			http.Error(w, "missing authorization code", http.StatusBadRequest)
			return
		}

		tokens, err := oidcClient.Exchange(code, txn.CodeVerifier)
		if err != nil {
			log.Printf("agent-frontend: token exchange failed: %v", err)
			http.Error(w, "sign-in failed", http.StatusBadGateway)
			return
		}

		claims, err := oidcClient.VerifyIDToken(tokens.IDToken)
		if err != nil {
			log.Printf("agent-frontend: ID token verification failed: %v", err)
			http.Error(w, "sign-in failed", http.StatusUnauthorized)
			return
		}

		expiresAt := time.Now().Add(time.Duration(tokens.ExpiresIn) * time.Second)
		if tokens.ExpiresIn == 0 {
			expiresAt = time.Now().Add(15 * time.Minute)
		}

		sess := session.Session{
			Subject:           claims.Subject,
			Email:             claims.Email,
			PreferredUsername: claims.PreferredUsername,
			Groups:            claims.Groups,
			AccessToken:       tokens.AccessToken,
			IDToken:           tokens.IDToken,
			RefreshToken:      tokens.RefreshToken,
			ExpiresAt:         expiresAt,
		}
		if err := sessions.Save(w, sess); err != nil {
			http.Error(w, "internal error", http.StatusInternalServerError)
			return
		}

		http.Redirect(w, r, "/", http.StatusFound)
	}
}

func logoutHandler(oidcClient *oidc.Client, sessions *session.Manager, selfBaseURL string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		sess, err := sessions.Load(r)
		if err != nil {
			log.Printf("agent-frontend: no active session at logout: %v", err)
		}
		sessions.Clear(w, r)

		idTokenHint := ""
		if sess != nil {
			idTokenHint = sess.IDToken
		}
		redirectURL, err := oidcClient.EndSessionURL(idTokenHint, selfBaseURL)
		if err != nil {
			redirectURL = selfBaseURL
		}
		http.Redirect(w, r, redirectURL, http.StatusFound)
	}
}

// isSecureBaseURL controls the session cookie's Secure flag: true for any
// real deployment (SelfBaseURL is an https:// Route), false only if
// explicitly running over plain HTTP for local development.
func isSecureBaseURL(base string) bool {
	if os.Getenv("INSECURE_COOKIES") == "true" {
		return false
	}
	return len(base) >= 8 && base[:8] == "https://"
}
