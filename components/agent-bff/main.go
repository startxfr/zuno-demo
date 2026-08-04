// Command agent-bff is the reusable per-agent BFF (ADR-0008). It validates
// the caller's bearer JWT against Keycloak's JWKS (ADR-0013 identity
// propagation), then calls the shared Agent Runtime's documented chat
// contract and relays the reply back to the frontend. See README.md for
// this service's own small API surface.
package main

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/startxfr/zuno-demo/components/agent-bff/internal/config"
	"github.com/startxfr/zuno-demo/components/agent-bff/internal/jwks"
	"github.com/startxfr/zuno-demo/components/agent-bff/internal/runtime"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("agent-bff: configuration error: %v", err)
	}

	verifier := jwks.NewVerifier(cfg.KeycloakIssuerURL, cfg.OIDCAudience)
	runtimeClient := runtime.NewClient(cfg.AgentRuntimeBaseURL, cfg.AgentName)

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", healthzHandler)
	mux.HandleFunc("/api/chat", chatHandler(verifier, runtimeClient))

	server := &http.Server{
		Addr:              cfg.ListenAddr,
		Handler:           mux,
		ReadHeaderTimeout: 10 * time.Second,
	}

	log.Printf("agent-bff: serving agent %q, listening on %s, Agent Runtime at %s", cfg.AgentName, cfg.ListenAddr, cfg.AgentRuntimeBaseURL)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("agent-bff: server error: %v", err)
	}
}

func healthzHandler(w http.ResponseWriter, r *http.Request) {
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte("ok"))
}

// apiChatRequest is the frontend-facing request body (see README.md).
type apiChatRequest struct {
	SessionID string `json:"session_id"`
	Message   string `json:"message"`
}

// apiChatResponse is the frontend-facing response body (see README.md).
type apiChatResponse struct {
	Reply     string             `json:"reply"`
	Citations []runtime.Citation `json:"citations"`
}

type apiErrorResponse struct {
	Error string `json:"error"`
}

func chatHandler(verifier *jwks.Verifier, runtimeClient *runtime.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")

		if r.Method != http.MethodPost {
			writeError(w, http.StatusMethodNotAllowed, "method not allowed")
			return
		}

		token := bearerToken(r)
		if token == "" {
			writeError(w, http.StatusUnauthorized, "missing bearer token")
			return
		}
		claims, err := verifier.Verify(token)
		if err != nil {
			log.Printf("agent-bff: token verification failed: %v", err)
			writeError(w, http.StatusUnauthorized, "invalid or expired token")
			return
		}

		var req apiChatRequest
		if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20)).Decode(&req); err != nil {
			writeError(w, http.StatusBadRequest, "invalid request body")
			return
		}
		if strings.TrimSpace(req.Message) == "" {
			writeError(w, http.StatusBadRequest, "message is required")
			return
		}

		ctx, cancel := context.WithTimeout(r.Context(), 55*time.Second)
		defer cancel()

		resp, err := runtimeClient.Chat(ctx, runtime.ChatRequest{
			SessionID: req.SessionID,
			UserSub:   claims.Subject,
			Message:   req.Message,
		})
		if err != nil {
			log.Printf("agent-bff: agent runtime call failed: %v", err)
			writeError(w, http.StatusBadGateway, "agent runtime unreachable")
			return
		}

		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(apiChatResponse{
			Reply:     resp.Reply,
			Citations: resp.Citations,
		})
	}
}

func bearerToken(r *http.Request) string {
	h := r.Header.Get("Authorization")
	const prefix = "Bearer "
	if len(h) > len(prefix) && strings.EqualFold(h[:len(prefix)], prefix) {
		return h[len(prefix):]
	}
	return ""
}

func writeError(w http.ResponseWriter, status int, msg string) {
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(apiErrorResponse{Error: msg})
}
