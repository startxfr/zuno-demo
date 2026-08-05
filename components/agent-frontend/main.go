// Command agent-frontend serves the Zuno agent portal (one tile per agent,
// gated on OIDC group membership) and, for the one active agent this
// deployment is configured for, a PatternFly-styled chat UI that proxies to
// that agent's BFF. See components/agent-frontend/README.md for the full
// design, and ADR-0008 for why this single codebase is deployed once per
// agent rather than forked.
package main

import (
	"log"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/assets"
	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/chat"
	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/config"
	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/oidc"
	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/okf"
	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/portal"
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

	oidcClient := oidc.NewClient(cfg.KeycloakIssuerURL, cfg.OIDCClientID, cfg.OIDCClientSecret, cfg.OIDCRedirectURL)
	sessions := session.NewManager(cfg.SessionHMACSecret, isSecureBaseURL(cfg.SelfBaseURL))

	mux := http.NewServeMux()

	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})

	mux.Handle(staticBase, http.StripPrefix(staticBase, http.FileServer(http.Dir(cfg.WebDistDir))))

	mux.HandleFunc("/", portal.Handler(agents, sessions, portalAsset))

	mux.HandleFunc("/login", loginHandler(oidcClient, sessions))
	mux.HandleFunc("/callback", callbackHandler(oidcClient, sessions))
	mux.HandleFunc("/logout", logoutHandler(oidcClient, sessions, cfg.SelfBaseURL))

	mux.HandleFunc("/"+activeAgent.Zuno.Name, chat.PageHandler(activeAgent, sessions, chatAsset))
	mux.HandleFunc("/api/chat", chat.APIHandler(activeAgent, cfg.BFFBaseURL, sessions))

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
			Subject:     claims.Subject,
			Email:       claims.Email,
			Groups:      claims.Groups,
			AccessToken: tokens.AccessToken,
			IDToken:     tokens.IDToken,
			ExpiresAt:   expiresAt,
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
		sess, _ := sessions.Load(r)
		sessions.Clear(w)

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
