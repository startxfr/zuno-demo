// Package runtime is an HTTP client for the shared Agent Runtime's chat
// contract, owned by a parallel track. Documented contract this client
// implements exactly:
//
//	POST /v1/agents/{agent}/chat
//	  headers: Authorization: Bearer <end-user token>
//	  body:  {"session_id": string, "user_sub": string, "message": string, "project_id": string (optional, ADR-0209)}
//	  reply: {"reply": string, "citations": [{"source": string, "title": string}]}
//
// The Authorization header carries the same validated bearer token the BFF
// itself received from the frontend (ADR-0032: identity must propagate
// Frontend -> BFF -> Agent Runtime, not stop at the BFF) - the Agent
// Runtime requires it (app/auth.py:validate_token) and rejects calls
// without one. `user_sub` in the body is correlation/display metadata only
// (ADR-0033): the Runtime derives the authoritative identity from the
// token, not from this field.
//
// This package makes no assumption about the Agent Runtime's internals
// (task graph, RAG, MCP) - it only speaks this HTTP contract.
package runtime

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"

	"github.com/startxfr/zuno-demo/components/agent-bff/internal/reqid"
)

// UpstreamError reports a non-200 response from Agent Runtime, preserving
// the status code so callers (main.go's chatHandler) can decide how to map
// it - e.g. relay a 4xx as-is - instead of treating every non-200 as an
// opaque connectivity failure.
type UpstreamError struct {
	StatusCode int
	Body       string
}

func (e *UpstreamError) Error() string {
	return fmt.Sprintf("agent runtime returned %d: %s", e.StatusCode, e.Body)
}

// Citation mirrors one entry of the Agent Runtime's citations array.
type Citation struct {
	Source string `json:"source"`
	Title  string `json:"title"`
}

// ChatRequest is the Agent Runtime's documented request body.
type ChatRequest struct {
	SessionID string `json:"session_id"`
	UserSub   string `json:"user_sub"`
	Message   string `json:"message"`
	// ADR-0209: optional - see components/agent-runtime/app/schemas.py's
	// ChatRequest.project_id. Empty means no project memory is read or
	// written for this turn.
	ProjectID string `json:"project_id,omitempty"`
	// ADR-0212: optional - omit to start a new conversation (the Agent
	// Runtime mints a fresh run_id and returns it in the SSE "start"
	// event); supply a prior run_id to resume that conversation from its
	// last checkpoint. Resuming under a run_id owned by a different
	// subject is refused server-side (main.go's chatHandler never
	// enforces this itself, same identity-propagation pattern as
	// UserSub/ProjectID above).
	RunID string `json:"run_id,omitempty"`
}

// Conversation mirrors one entry of the Agent Runtime's conversation list
// (ADR-0212, GET /v1/agents/{agent}/conversations).
type Conversation struct {
	RunID     string `json:"run_id"`
	Title     string `json:"title"`
	UpdatedAt string `json:"updated_at"`
	Starred   bool   `json:"starred"`
}

// TranscriptTurn mirrors one entry of the Agent Runtime's structured
// transcript (ADR-0212, GET /v1/agents/{agent}/runs/{run_id}/transcript).
type TranscriptTurn struct {
	Role    string `json:"role"`
	Content string `json:"content"`
	Ts      string `json:"ts"`
}

// RenameConversationRequest is the Agent Runtime's documented request body
// for PATCH /v1/agents/{agent}/runs/{run_id} (ADR-0212).
type RenameConversationRequest struct {
	Title string `json:"title"`
}

// RenameConversationResponse is that endpoint's documented response body.
type RenameConversationResponse struct {
	RunID string `json:"run_id"`
	Title string `json:"title"`
}

// StarResponse is the documented response body for both PUT and DELETE
// .../runs/{run_id}/star (ADR-0212).
type StarResponse struct {
	Starred bool `json:"starred"`
}

// ChatResponse is the Agent Runtime's documented response body.
type ChatResponse struct {
	Reply     string     `json:"reply"`
	Citations []Citation `json:"citations"`
}

// Client calls one agent's chat endpoint on the shared Agent Runtime.
type Client struct {
	baseURL    string
	agentName  string
	httpClient *http.Client
	// streamClient has no fixed Timeout (unlike httpClient) because
	// http.Client.Timeout bounds the *entire* request including reading
	// the response body - fatal for a long SSE stream. Cancellation for a
	// streaming call is instead purely context-driven (ADR-0045 "client
	// cancellation"): main.go's chatHandler derives a bounded context from
	// the inbound request for the overall call, and an early client
	// disconnect cancels r.Context() directly.
	streamClient *http.Client
}

// NewClient builds a Client for the given Agent Runtime base URL and agent.
func NewClient(baseURL, agentName string) *Client {
	return &Client{
		baseURL:   baseURL,
		agentName: agentName,
		httpClient: &http.Client{
			Timeout: 55 * time.Second,
		},
		streamClient: &http.Client{},
	}
}

// Chat calls POST /v1/agents/{agent}/chat and returns its parsed response.
// bearerToken is the same validated end-user token the BFF received on
// /api/chat - it is forwarded as-is (ADR-0032), never replaced by a
// service credential, since the Agent Runtime needs the actual end user's
// identity/groups for classification and MCP tool authorization downstream.
func (c *Client) Chat(ctx context.Context, bearerToken string, req ChatRequest) (*ChatResponse, error) {
	body, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("encoding chat request: %w", err)
	}

	url := fmt.Sprintf("%s/v1/agents/%s/chat", c.baseURL, c.agentName)
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("building chat request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Authorization", "Bearer "+bearerToken)

	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("calling agent runtime at %q: %w", url, err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(io.LimitReader(resp.Body, 4<<20))
	if err != nil {
		return nil, fmt.Errorf("reading agent runtime response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, &UpstreamError{StatusCode: resp.StatusCode, Body: string(respBody)}
	}

	var out ChatResponse
	if err := json.Unmarshal(respBody, &out); err != nil {
		return nil, fmt.Errorf("decoding agent runtime response: %w", err)
	}
	return &out, nil
}

// ChatStream calls the same endpoint as Chat but with
// Accept: text/event-stream (ADR-0045), and returns the raw *http.Response
// for the caller to relay chunk-by-chunk instead of decoding a single JSON
// body - see main.go:chatHandler's proxySSE. The caller must close
// resp.Body. requestID, if non-empty, is forwarded as X-Zuno-Request-Id
// (ADR-0045 request correlation) so this turn's Agent Runtime logs and its
// SSE "start" event carry the same ID agent-frontend minted.
func (c *Client) ChatStream(ctx context.Context, bearerToken, requestID string, req ChatRequest) (*http.Response, error) {
	body, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("encoding chat request: %w", err)
	}

	url := fmt.Sprintf("%s/v1/agents/%s/chat", c.baseURL, c.agentName)
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("building chat request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Authorization", "Bearer "+bearerToken)
	httpReq.Header.Set("Accept", "text/event-stream")
	if requestID != "" {
		httpReq.Header.Set(reqid.Header, requestID)
	}

	resp, err := c.streamClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("calling agent runtime at %q: %w", url, err)
	}
	return resp, nil
}

// doJSON performs a bearer-authenticated JSON request against the Agent
// Runtime and decodes a 200 response into out (out may be nil for a
// response body the caller doesn't need to inspect). Shared by every
// conversation-management method below - the same build/do/read/check/
// decode shape Chat above uses for POST /chat, factored out here since
// four near-identical methods would otherwise repeat it.
func (c *Client) doJSON(ctx context.Context, method, bearerToken, path string, body, out any) error {
	var reader io.Reader
	if body != nil {
		encoded, err := json.Marshal(body)
		if err != nil {
			return fmt.Errorf("encoding request body: %w", err)
		}
		reader = bytes.NewReader(encoded)
	}

	reqURL := c.baseURL + path
	httpReq, err := http.NewRequestWithContext(ctx, method, reqURL, reader)
	if err != nil {
		return fmt.Errorf("building %s %s request: %w", method, reqURL, err)
	}
	if body != nil {
		httpReq.Header.Set("Content-Type", "application/json")
	}
	httpReq.Header.Set("Authorization", "Bearer "+bearerToken)

	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		return fmt.Errorf("calling agent runtime at %q: %w", reqURL, err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(io.LimitReader(resp.Body, 4<<20))
	if err != nil {
		return fmt.Errorf("reading agent runtime response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return &UpstreamError{StatusCode: resp.StatusCode, Body: string(respBody)}
	}
	if out != nil {
		if err := json.Unmarshal(respBody, out); err != nil {
			return fmt.Errorf("decoding agent runtime response: %w", err)
		}
	}
	return nil
}

// ListConversations calls GET /v1/agents/{agent}/conversations (ADR-0212),
// the caller's own conversations for this agent, starred first.
func (c *Client) ListConversations(ctx context.Context, bearerToken string, starredOnly bool) ([]Conversation, error) {
	path := fmt.Sprintf("/v1/agents/%s/conversations", c.agentName)
	if starredOnly {
		path += "?starred=true"
	}
	var out []Conversation
	if err := c.doJSON(ctx, http.MethodGet, bearerToken, path, nil, &out); err != nil {
		return nil, err
	}
	return out, nil
}

// GetTranscript calls GET /v1/agents/{agent}/runs/{run_id}/transcript
// (ADR-0212) - the structured message history for reopening a
// conversation from the left-nav.
func (c *Client) GetTranscript(ctx context.Context, bearerToken, runID string) ([]TranscriptTurn, error) {
	path := fmt.Sprintf("/v1/agents/%s/runs/%s/transcript", c.agentName, url.PathEscape(runID))
	var out []TranscriptTurn
	if err := c.doJSON(ctx, http.MethodGet, bearerToken, path, nil, &out); err != nil {
		return nil, err
	}
	return out, nil
}

// RenameConversation calls PATCH /v1/agents/{agent}/runs/{run_id}
// (ADR-0212).
func (c *Client) RenameConversation(ctx context.Context, bearerToken, runID, title string) (*RenameConversationResponse, error) {
	path := fmt.Sprintf("/v1/agents/%s/runs/%s", c.agentName, url.PathEscape(runID))
	var out RenameConversationResponse
	body := RenameConversationRequest{Title: title}
	if err := c.doJSON(ctx, http.MethodPatch, bearerToken, path, body, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// SetStar calls PUT (starred=true) or DELETE (starred=false)
// /v1/agents/{agent}/runs/{run_id}/star (ADR-0212) - the caller's own
// personal star toggle.
func (c *Client) SetStar(ctx context.Context, bearerToken, runID string, starred bool) (*StarResponse, error) {
	method := http.MethodDelete
	if starred {
		method = http.MethodPut
	}
	path := fmt.Sprintf("/v1/agents/%s/runs/%s/star", c.agentName, url.PathEscape(runID))
	var out StarResponse
	if err := c.doJSON(ctx, method, bearerToken, path, nil, &out); err != nil {
		return nil, err
	}
	return &out, nil
}
