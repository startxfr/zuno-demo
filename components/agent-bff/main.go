// Command agent-bff is the reusable per-agent BFF (ADR-0008). It validates
// the caller's bearer JWT against Keycloak's JWKS (ADR-0013 identity
// propagation), then calls the shared Agent Runtime's documented chat
// contract - forwarding that same validated token (ADR-0032) - and relays
// the reply back to the frontend. See README.md for this service's own
// small API surface.
package main

import (
	"context"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/startxfr/zuno-demo/components/agent-bff/internal/config"
	"github.com/startxfr/zuno-demo/components/agent-bff/internal/jwks"
	"github.com/startxfr/zuno-demo/components/agent-bff/internal/reqid"
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
	mux.HandleFunc("/api/chat", chatHandler(verifier, runtimeClient, cfg.AgentName))

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

// chatHandler validates and authorizes the caller, then either proxies a
// synchronous JSON reply (default) or, when the caller sent
// Accept: text/event-stream, opens an SSE stream to the Agent Runtime and
// relays it chunk-by-chunk (ADR-0045) - see proxySSE. Every early-return
// error path (auth/authorization/body validation) responds with plain
// JSON regardless of the request's Accept header, since those failures
// happen before any stream would have started.
func chatHandler(verifier *jwks.Verifier, runtimeClient *runtime.Client, agentName string) http.HandlerFunc {
	entitlementGroup := "agent_" + agentName
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			w.Header().Set("Content-Type", "application/json")
			writeError(w, http.StatusMethodNotAllowed, "method not allowed")
			return
		}

		token := bearerToken(r)
		if token == "" {
			w.Header().Set("Content-Type", "application/json")
			writeError(w, http.StatusUnauthorized, "missing bearer token")
			return
		}
		claims, err := verifier.Verify(token)
		if err != nil {
			log.Printf("agent-bff: token verification failed: %v", err)
			w.Header().Set("Content-Type", "application/json")
			writeError(w, http.StatusUnauthorized, "invalid or expired token")
			return
		}

		// ADR-0040: agent entitlement (agent_<name>) is a distinct,
		// server-enforced dimension from the business-role groups that
		// gate individual tools downstream (MCP Gateway policy). Frontend
		// tile visibility is not authorization - this is the actual gate.
		if !hasGroup(claims.Groups, entitlementGroup) {
			log.Printf("agent-bff: subject %q lacks entitlement group %q", claims.Subject, entitlementGroup)
			w.Header().Set("Content-Type", "application/json")
			writeError(w, http.StatusForbidden, "not entitled to this agent")
			return
		}

		var req apiChatRequest
		if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20)).Decode(&req); err != nil {
			w.Header().Set("Content-Type", "application/json")
			writeError(w, http.StatusBadRequest, "invalid request body")
			return
		}
		if strings.TrimSpace(req.Message) == "" {
			w.Header().Set("Content-Type", "application/json")
			writeError(w, http.StatusBadRequest, "message is required")
			return
		}

		requestID := reqid.FromHeaderOrNew(r.Header)
		runtimeReq := runtime.ChatRequest{
			SessionID: req.SessionID,
			UserSub:   claims.Subject, // informational only (ADR-0033); the Runtime derives identity from the forwarded token, not this field
			Message:   req.Message,
		}

		if strings.Contains(r.Header.Get("Accept"), "text/event-stream") {
			// A full streamed reply can legitimately take longer than a
			// single non-streaming call - bounded generously rather than
			// left unbounded, but well past the synchronous path's 55s.
			ctx, cancel := context.WithTimeout(r.Context(), 120*time.Second)
			defer cancel()

			resp, err := runtimeClient.ChatStream(ctx, token, requestID, runtimeReq)
			if err != nil {
				log.Printf("agent-bff: agent runtime stream call failed: %v", err)
				w.Header().Set("Content-Type", "application/json")
				writeError(w, http.StatusBadGateway, "agent runtime unreachable")
				return
			}
			defer resp.Body.Close()

			if resp.StatusCode == http.StatusOK && strings.Contains(resp.Header.Get("Content-Type"), "text/event-stream") {
				proxySSE(w, resp)
				return
			}
			// The Agent Runtime rejected the request before streaming
			// anything (e.g. 401 if this BFF's own forwarded token somehow
			// expired mid-flight) - relay its status/body as-is.
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(resp.StatusCode)
			_, _ = io.Copy(w, resp.Body)
			return
		}

		ctx, cancel := context.WithTimeout(r.Context(), 55*time.Second)
		defer cancel()

		resp, err := runtimeClient.Chat(ctx, token, runtimeReq)
		if err != nil {
			log.Printf("agent-bff: agent runtime call failed: %v", err)
			w.Header().Set("Content-Type", "application/json")
			writeError(w, http.StatusBadGateway, "agent runtime unreachable")
			return
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(apiChatResponse{
			Reply:     resp.Reply,
			Citations: resp.Citations,
		})
	}
}

// proxySSE relays an already-200-OK SSE response body to w chunk by chunk,
// flushing after every read so token deltas reach the caller as they
// arrive rather than being buffered - see
// components/agent-frontend/internal/chat/chat.go's identically-named
// function for the next hop down and the same client-cancellation
// reasoning.
func proxySSE(w http.ResponseWriter, resp *http.Response) {
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("X-Accel-Buffering", "no")
	w.WriteHeader(http.StatusOK)

	flusher, canFlush := w.(http.Flusher)
	buf := make([]byte, 4096)
	for {
		n, readErr := resp.Body.Read(buf)
		if n > 0 {
			if _, writeErr := w.Write(buf[:n]); writeErr != nil {
				return
			}
			if canFlush {
				flusher.Flush()
			}
		}
		if readErr != nil {
			return
		}
	}
}

// hasGroup reports whether want (a bare group name) is among groups (the
// JWT's "groups" claim entries, e.g. "/agent_tekos" - full paths with a
// leading "/", per platform/identity/README.md).
func hasGroup(groups []string, want string) bool {
	for _, g := range groups {
		if strings.TrimPrefix(g, "/") == want {
			return true
		}
	}
	return false
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
