// Package chat serves the Tekos chat UI and proxies chat requests from the
// browser to the agent's BFF. The BFF has no public Route (ADR-0023
// isolation - one fewer public ingress per agent); the frontend forwards
// POST /api/chat to the BFF's in-cluster Service, attaching the caller's
// OIDC access token as a Bearer credential so the BFF can independently
// revalidate identity (ADR-0013) before calling the Agent Runtime.
//
// ADR-0044: the page itself is a thin, per-request HTML shell - the chat
// UI is a PatternFly React component (web/src/chat/Chat.tsx) mounted into
// #root. ADR-0045: when the browser sends Accept: text/event-stream,
// APIHandler streams the BFF's SSE response back byte-for-byte instead of
// buffering a synchronous JSON reply - see proxySSE.
package chat

import (
	"bytes"
	"encoding/json"
	"html/template"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/assets"
	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/okf"
	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/portal"
	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/reqid"
	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/session"
)

const pageTemplate = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{.DisplayName}} - Zuno</title>
  {{range .CSS}}<link rel="stylesheet" href="{{.}}">
  {{end}}
</head>
<body>
  <div id="root"></div>
  <script id="zuno-config" type="application/json">{{.ConfigJSON}}</script>
  <script type="module" src="{{.JS}}"></script>
</body>
</html>`

var tmpl = template.Must(template.New("chat").Parse(pageTemplate))

// chatConfig mirrors web/src/shared/types.ts's ChatConfig field-for-field.
type chatConfig struct {
	DisplayName string `json:"displayName"`
	Subject     string `json:"subject"`
	// UserDisplayName is the signed-in USER's display name (see
	// session.Session.DisplayName) - not to be confused with DisplayName
	// above, which is the AGENT's display name (e.g. "Tekos").
	UserDisplayName string `json:"userDisplayName"`
	HomeURL         string `json:"homeURL"`
	LogoutURL       string `json:"logoutURL"`
	ProfileURL      string `json:"profileURL"`
	// ApiURL is this same-origin page's own chat endpoint (ADR-0044:
	// "keep runtime API endpoint injection from environment into
	// JavaScript context") - always "/api/chat" today, but the React
	// client reads it from injected config rather than hardcoding it so a
	// future deployment split (e.g. serving the API from a different
	// path/host) doesn't require a frontend code change.
	ApiURL string `json:"apiURL"`
	// ConversationsURL is this same-origin page's own conversation-list
	// base (ADR-0212), always "/api/conversations" today - same
	// injected-rather-than-hardcoded rationale as ApiURL above. The
	// client builds the other three conversation endpoints
	// (transcript/rename/star) by appending to this base at request time,
	// since each also needs a run_id it doesn't know until then.
	ConversationsURL string `json:"conversationsURL"`
	// ColleaguesURL is this same-origin page's own colleague-search
	// endpoint (ADR-0213), always "/api/colleagues" today - same
	// injected-rather-than-hardcoded rationale as ApiURL above.
	ColleaguesURL string `json:"colleaguesURL"`
	// AgentNavStrip (ADR-0515) is the cross-agent masthead navigation
	// strip: every OTHER agent this signed-in caller is entitled to and
	// that is actually active/clickable - the same entitlement-filtered
	// set portal.BuildTiles already computes for the portal tile grid,
	// reused here rather than re-deriving it.
	AgentNavStrip []agentNavEntry `json:"agentNavStrip"`
	// PromptExamples (ADR-0515/WP-061) are this agent's primary task's
	// declared zuno.prompt_examples - rendered as clickable starters in
	// the chat empty state when the caller has no conversation history
	// yet. Empty/nil renders no starters.
	PromptExamples []string `json:"promptExamples"`
}

// agentNavEntry is one entry of AgentNavStrip above - mirrors
// web/src/shared/types.ts's AgentNavEntry field-for-field.
type agentNavEntry struct {
	Name        string `json:"name"`
	DisplayName string `json:"displayName"`
	Color       string `json:"color"`
	Href        string `json:"href"`
}

type pageView struct {
	DisplayName string
	JS          string
	CSS         []string
	ConfigJSON  template.JS
}

// PageHandler serves the chat UI for one active agent, gated on the caller
// being signed in and authorized (their groups intersect access.groups).
// agents is the full agent list (ADR-0515: source for the cross-agent
// masthead nav strip, the same list portal.Handler already receives).
// asset is web/src/chat/main.tsx's resolved Vite manifest entry.
// clusterBaseDomain - see portal.BuildTiles's own doc comment.
func PageHandler(agent okf.Agent, agents []okf.Agent, sessions *session.Manager, asset assets.Asset, clusterBaseDomain string) http.HandlerFunc {
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

		cfg := chatConfig{
			DisplayName:      agent.Zuno.UI.DisplayName,
			Subject:          sess.Subject,
			UserDisplayName:  sess.DisplayName(),
			HomeURL:          "/",
			LogoutURL:        "/logout",
			ProfileURL:       "/profile",
			ApiURL:           "/api/chat",
			ConversationsURL: "/api/conversations",
			ColleaguesURL:    "/api/colleagues",
			AgentNavStrip:    buildAgentNavStrip(agents, sess, clusterBaseDomain),
			PromptExamples:   agent.PrimaryTaskPromptExamples(),
		}
		configJSON, err := json.Marshal(cfg) // HTML-escaped by default - see portal.go's comment
		if err != nil {
			http.Error(w, "internal error", http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		view := pageView{
			DisplayName: agent.Zuno.UI.DisplayName,
			JS:          asset.JS,
			CSS:         asset.CSS,
			ConfigJSON:  template.JS(configJSON),
		}
		_ = tmpl.Execute(w, view)
	}
}

// buildAgentNavStrip (ADR-0515) reuses portal.BuildTiles's own
// entitlement computation rather than re-deriving it, then narrows to the
// entries actually worth showing in the masthead: an agent this caller
// can't reach yet (unauthorized) or that has no live chat page to route
// to (placeholder, not yet active) would be a dead link here, unlike on
// the portal grid where those tiles still render disabled for visibility.
func buildAgentNavStrip(agents []okf.Agent, sess *session.Session, clusterBaseDomain string) []agentNavEntry {
	tiles := portal.BuildTiles(agents, sess, clusterBaseDomain)
	strip := make([]agentNavEntry, 0, len(tiles))
	for _, t := range tiles {
		if !t.Clickable {
			continue
		}
		strip = append(strip, agentNavEntry{
			Name:        t.Name,
			DisplayName: t.DisplayName,
			Color:       t.Color,
			Href:        t.Href,
		})
	}
	return strip
}

// chatRequest is what the browser JS POSTs to this frontend's /api/chat.
type chatRequest struct {
	SessionID string `json:"session_id"`
	Message   string `json:"message"`
	// RunID (ADR-0212) is optional - omit to start a new conversation, or
	// send a prior response's run_id (captured from the SSE "start"
	// event) to resume it.
	RunID string `json:"run_id,omitempty"`
}

// bffChatRequest is forwarded to the BFF's POST /api/chat (see
// components/agent-bff/README.md for the BFF's own small API surface).
type bffChatRequest struct {
	SessionID string `json:"session_id"`
	Message   string `json:"message"`
	RunID     string `json:"run_id,omitempty"`
}

// APIHandler proxies a validated, authorized chat turn to the BFF.
// ADR-0045: if the browser sent Accept: text/event-stream, the same call
// is made with that header forwarded, and a 200 SSE response is streamed
// back chunk-by-chunk (proxySSE) instead of read into memory - preserving
// token-by-token latency through this hop. A non-200 or non-SSE response
// (auth/authorization failures, which this handler and the BFF both
// return as plain JSON regardless of the request's Accept header) falls
// back to the synchronous JSON path unchanged.
func APIHandler(agent okf.Agent, bffBaseURL string, sessions *session.Manager) http.HandlerFunc {
	// httpClient bounds the synchronous JSON path only.
	httpClient := &http.Client{Timeout: 60 * time.Second}
	// streamClient has no fixed Timeout (unlike httpClient) - matching
	// agent-bff/internal/runtime/client.go's identical split, since
	// http.Client.Timeout bounds the entire request including reading a
	// streamed body, which would silently truncate a long-but-healthy SSE
	// turn. Cancellation for this path is purely context-driven
	// (ADR-0045 "client cancellation") via r.Context().
	streamClient := &http.Client{}

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
			RunID:     req.RunID,
		})
		if err != nil {
			http.Error(w, "internal error", http.StatusInternalServerError)
			return
		}

		wantsStream := strings.Contains(r.Header.Get("Accept"), "text/event-stream")

		bffReq, err := http.NewRequestWithContext(r.Context(), http.MethodPost,
			bffBaseURL+"/api/chat", bytes.NewReader(body))
		if err != nil {
			http.Error(w, "internal error", http.StatusInternalServerError)
			return
		}
		bffReq.Header.Set("Content-Type", "application/json")
		bffReq.Header.Set("Authorization", "Bearer "+sess.AccessToken)
		// ADR-0045 "preserve request correlation ... across the chain":
		// this frontend is the first hop with an HTTP request at all
		// (browser -> frontend has no ID yet), so it normally mints the ID
		// that agent-bff and agent-runtime then propagate unchanged in
		// their own logs and the "start" SSE event.
		requestID := reqid.FromHeaderOrNew(r.Header)
		bffReq.Header.Set(reqid.Header, requestID)
		client := httpClient
		if wantsStream {
			bffReq.Header.Set("Accept", "text/event-stream")
			client = streamClient
		}

		resp, err := client.Do(bffReq)
		if err != nil {
			http.Error(w, "agent backend unreachable", http.StatusBadGateway)
			return
		}
		defer resp.Body.Close()

		if wantsStream && resp.StatusCode == http.StatusOK &&
			strings.Contains(resp.Header.Get("Content-Type"), "text/event-stream") {
			proxySSE(w, resp)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(resp.StatusCode)
		_, _ = io.Copy(w, resp.Body)
	}
}

// ConversationsProxyHandler forwards any method/path under
// /api/conversations... (ADR-0212: list, transcript, rename, star/unstar)
// to the BFF's identically-shaped route, attaching the caller's session
// access token as a Bearer credential - the same session-gated
// reverse-proxy shape as APIHandler's /api/chat above, minus its SSE-relay
// branch (none of these routes stream). Registered under several
// method+pattern combinations in main.go, since it needs no per-route
// parameter - request method and path alone decide where it forwards.
func ConversationsProxyHandler(agent okf.Agent, bffBaseURL string, sessions *session.Manager) http.HandlerFunc {
	httpClient := &http.Client{Timeout: 30 * time.Second}

	return func(w http.ResponseWriter, r *http.Request) {
		sess, err := sessions.Load(r)
		if err != nil || sess == nil {
			http.Error(w, "not authenticated", http.StatusUnauthorized)
			return
		}
		if !agent.AllowsAnyGroup(sess.Groups) {
			http.Error(w, "not authorized for this agent", http.StatusForbidden)
			return
		}

		target := bffBaseURL + r.URL.Path
		if r.URL.RawQuery != "" {
			target += "?" + r.URL.RawQuery
		}
		bffReq, err := http.NewRequestWithContext(r.Context(), r.Method, target, io.LimitReader(r.Body, 1<<20))
		if err != nil {
			http.Error(w, "internal error", http.StatusInternalServerError)
			return
		}
		bffReq.Header.Set("Content-Type", "application/json")
		bffReq.Header.Set("Authorization", "Bearer "+sess.AccessToken)

		resp, err := httpClient.Do(bffReq)
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

// proxySSE relays an already-200-OK SSE response body to w chunk by chunk,
// flushing after every read so token deltas reach the browser as they
// arrive rather than being buffered - the same reasoning as
// agent-bff/main.go's identically-named function for its own hop, and
// components/agent-runtime/app/main.py:_stream_chat's
// "X-Accel-Buffering: no" header for the first hop. If the client
// disconnects (browser closed the tab, or the React client's "Stop"
// button aborted its fetch), r.Context() -> resp's underlying request
// context is canceled, resp.Body.Read returns an error, and this function
// returns - which in turn cancels the BFF's own request to the Agent
// Runtime (ADR-0045 "client cancellation").
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
