// Package chat serves the Tekos chat UI and proxies chat requests from the
// browser to the agent's BFF. The BFF has no public Route (ADR-0023
// isolation — one fewer public ingress per agent); the frontend forwards
// POST /api/chat to the BFF's in-cluster Service, attaching the caller's
// OIDC access token as a Bearer credential so the BFF can independently
// revalidate identity (ADR-0013) before calling the Agent Runtime.
package chat

import (
	"bytes"
	"encoding/json"
	"html/template"
	"io"
	"net/http"
	"time"

	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/okf"
	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/session"
)

const pageTemplate = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{.DisplayName}} — Zuno</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body class="pf-body">
  <header class="zuno-header">
    <div class="zuno-header-title"><a class="zuno-home-link" href="/">Zuno</a> / {{.DisplayName}}</div>
    <div class="zuno-header-user">
      <span class="zuno-user-sub">{{.Subject}}</span>
      <a class="pf-button pf-button-link" href="/logout">Sign out</a>
    </div>
  </header>
  <main class="zuno-chat-shell">
    <div id="zuno-chat-log" class="zuno-chat-log" aria-live="polite"></div>
    <form id="zuno-chat-form" class="zuno-chat-form">
      <input id="zuno-chat-input" class="pf-form-control" type="text"
             placeholder="Ask a technical question…" autocomplete="off" required>
      <button class="pf-button pf-button-primary" type="submit">Send</button>
    </form>
  </main>
  <script src="/static/chat.js"></script>
</body>
</html>`

var tmpl = template.Must(template.New("chat").Parse(pageTemplate))

type pageView struct {
	DisplayName string
	Subject     string
}

// PageHandler serves the chat UI for one active agent, gated on the caller
// being signed in and authorized (their groups intersect access.groups).
func PageHandler(agent okf.Agent, sessions *session.Manager) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		sess, err := sessions.Load(r)
		if err != nil || sess == nil {
			http.Redirect(w, r, "/login", http.StatusFound)
			return
		}
		if !agent.AllowsAnyGroup(sess.Groups) {
			http.Error(w, "not authorized for this agent", http.StatusForbidden)
			return
		}

		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		_ = tmpl.Execute(w, pageView{
			DisplayName: agent.Spec.UI.DisplayName,
			Subject:     sess.Subject,
		})
	}
}

// chatRequest is what the browser JS POSTs to this frontend's /api/chat.
type chatRequest struct {
	SessionID string `json:"session_id"`
	Message   string `json:"message"`
}

// bffChatRequest is forwarded to the BFF's POST /api/chat (see
// components/agent-bff/README.md for the BFF's own small API surface).
type bffChatRequest struct {
	SessionID string `json:"session_id"`
	Message   string `json:"message"`
}

// APIHandler proxies a validated, authorized chat turn to the BFF.
func APIHandler(agent okf.Agent, bffBaseURL string, sessions *session.Manager) http.HandlerFunc {
	client := &http.Client{Timeout: 60 * time.Second}

	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}

		sess, err := sessions.Load(r)
		if err != nil || sess == nil {
			http.Error(w, "not authenticated", http.StatusUnauthorized)
			return
		}
		if !agent.AllowsAnyGroup(sess.Groups) {
			http.Error(w, "not authorized for this agent", http.StatusForbidden)
			return
		}

		var req chatRequest
		if err := json.NewDecoder(io.LimitReader(r.Body, 1<<20)).Decode(&req); err != nil {
			http.Error(w, "invalid request body", http.StatusBadRequest)
			return
		}
		if req.Message == "" {
			http.Error(w, "message is required", http.StatusBadRequest)
			return
		}

		body, err := json.Marshal(bffChatRequest{
			SessionID: req.SessionID,
			Message:   req.Message,
		})
		if err != nil {
			http.Error(w, "internal error", http.StatusInternalServerError)
			return
		}

		bffReq, err := http.NewRequestWithContext(r.Context(), http.MethodPost,
			bffBaseURL+"/api/chat", bytes.NewReader(body))
		if err != nil {
			http.Error(w, "internal error", http.StatusInternalServerError)
			return
		}
		bffReq.Header.Set("Content-Type", "application/json")
		bffReq.Header.Set("Authorization", "Bearer "+sess.AccessToken)

		resp, err := client.Do(bffReq)
		if err != nil {
			http.Error(w, "agent backend unreachable", http.StatusBadGateway)
			return
		}
		defer resp.Body.Close()

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(resp.StatusCode)
		_, _ = io.Copy(w, resp.Body)
	}
}
