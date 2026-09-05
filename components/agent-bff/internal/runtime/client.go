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

// Image mirrors one entry of the Agent Runtime's images array (ADR-0415,
// components/agent-runtime/app/schemas.py's ImageArtifact) - a
// generate_image tool result for this turn, passed through unchanged, the
// same sidecar-field shape as Citation above.
type Image struct {
	DataBase64 string `json:"data_base64"`
	MimeType   string `json:"mime_type"`
	Alt        string `json:"alt"`
}

// ChatRequest is the Agent Runtime's documented request body.
type ChatRequest struct {
	SessionID string `json:"session_id"`
	UserSub   string `json:"user_sub"`
	Message   string `json:"message"`
	// ADR-0209: optional - see components/agent-runtime/app/schemas.py's
	// ChatRequest.project_id. Empty means no project memory is read or
	// written for this turn. ADR-0512 (WP-55): for a project_required
	// task the Agent Runtime treats this as an unverified CANDIDATE,
	// verified server-side against Salesforce before use (or the request
	// is blocked) - this client's contract is unchanged, it always just
	// forwards whatever value it was given.
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
	// ADR-0527: the project this conversation belongs to, empty for a
	// project-less private one, and the caller's effective role on it
	// (read/clone/write/admin). Both are returned per row so the sidebar
	// can group the list and decide read-only mode without a second call.
	ProjectID string `json:"project_id"`
	Role      string `json:"role"`
}

// TranscriptTurn mirrors one entry of the Agent Runtime's structured
// transcript (ADR-0212, GET /v1/agents/{agent}/runs/{run_id}/transcript).
type TranscriptTurn struct {
	Role    string `json:"role"`
	Content string `json:"content"`
	Ts      string `json:"ts"`
	// ADR-0415: present only on an assistant turn that generated at least
	// one image (components/agent-runtime/app/main.py's
	// _build_transcript_structured).
	Images []Image `json:"images,omitempty"`
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

// ArchiveResponse is the documented response body for
// DELETE .../runs/{run_id} (ADR-0212 follow-up: soft-delete).
type ArchiveResponse struct {
	Archived bool `json:"archived"`
}

// ReorderConversationsRequest is the Agent Runtime's documented request
// body for PUT /v1/agents/{agent}/conversations/reorder (ADR-0515) - the
// caller's full desired run_id order for this agent.
type ReorderConversationsRequest struct {
	RunIDs []string `json:"run_ids"`
}

// ReorderConversationsResponse is that endpoint's documented response
// body: the count of conversations actually reordered (run_ids the
// caller doesn't own are silently skipped server-side).
type ReorderConversationsResponse struct {
	Updated int `json:"updated"`
}

// HardDeleteResponse is the documented response body for
// DELETE .../runs/{run_id}/hard-delete (ADR-0515) - irreversible, unlike
// ArchiveResponse's soft-delete.
type HardDeleteResponse struct {
	Deleted bool `json:"deleted"`
}

// ProjectGrant mirrors one entry of a project's ACL (ADR-0527). Exactly
// one of Subject/GroupName is set - the XOR the runtime enforces both in
// Pydantic and in project_grants' own CHECK constraint.
type ProjectGrant struct {
	// omitempty on all four is load-bearing on the OUTBOUND path, not
	// cosmetic. agent-runtime types subject/group_name as
	// `Optional[str] = Field(default=None, min_length=1)` and enforces the
	// XOR between them, so a Go zero value serialized as "" is not "absent"
	// to Pydantic - it is a present string of length 0, and the request is
	// rejected 422 with `string_too_short`. Live-verified 2026-08-28: every
	// group-less grant (i.e. every grant naming a user) failed this way, so
	// no project could be created at all.
	//
	// Safe for responses: this struct is only ever marshaled on the way OUT
	// to agent-runtime; what the frontend receives is re-encoded as
	// main.apiProjectGrant, whose shape is unchanged. omitempty has no
	// effect on unmarshaling.
	Subject   string `json:"subject,omitempty"`
	GroupName string `json:"group_name,omitempty"`
	Role      string `json:"role"`
	// Response-only, and agent-runtime's request model has no such fields.
	GrantedBy string `json:"granted_by,omitempty"`
	CreatedAt string `json:"created_at,omitempty"`
}

// Project mirrors one entry of GET /v1/projects (ADR-0527). Deliberately
// carries no Salesforce field: ADR-0528 keeps the opportunity identifier
// off every surface that does not strictly need it, so the list exposes
// only whether the project IS a customer project.
type Project struct {
	ProjectID         string `json:"project_id"`
	Title             string `json:"title"`
	Classification    string `json:"classification"`
	IsCustomer        bool   `json:"is_customer"`
	Starred           bool   `json:"starred"`
	Role              string `json:"role"`
	ConversationCount int    `json:"conversation_count"`
	UpdatedAt         string `json:"updated_at"`
}

// ProjectDetail mirrors GET /v1/projects/{project_id} (ADR-0527). Grants
// and the Salesforce fields are populated by the runtime only when the
// caller is an admin - the grant list names colleagues, and ADR-0528 keeps
// the opportunity id admin-only.
type ProjectDetail struct {
	ProjectID               string         `json:"project_id"`
	Title                   string         `json:"title"`
	Context                 string         `json:"context"`
	Classification          string         `json:"classification"`
	IsCustomer              bool           `json:"is_customer"`
	Role                    string         `json:"role"`
	CreatedBy               string         `json:"created_by"`
	CreatedAt               string         `json:"created_at"`
	UpdatedAt               string         `json:"updated_at"`
	Grants                  []ProjectGrant `json:"grants"`
	SalesforceOpportunityID string         `json:"salesforce_opportunity_id"`
	SalesforceVerifiedAt    string         `json:"salesforce_verified_at"`
}

// CreateProjectRequest is the Agent Runtime's documented request body for
// POST /v1/projects (ADR-0527).
type CreateProjectRequest struct {
	Title   string `json:"title"`
	Context string `json:"context"`
	// Same trap as ProjectGrant above: agent-runtime types this as
	// `Literal["C1","C2","C3"] = "C2"`, so omitting it takes the default but
	// sending "" is a literal_error. The Salesforce id beside it already had
	// omitempty; this one did not.
	Classification          string         `json:"classification,omitempty"`
	SalesforceOpportunityID string         `json:"salesforce_opportunity_id,omitempty"`
	Grants                  []ProjectGrant `json:"grants"`
}

// SaveProjectRequest is the request body for PUT /v1/projects/{project_id}
// (ADR-0527) - the WHOLE desired state at once, which is why this ADR needs
// one endpoint where ADR-0213 needed five. A nil Grants means "the caller
// may not edit grants" and leaves them untouched; a non-nil value is the
// full desired set, so anything absent from it is revoked.
type SaveProjectRequest struct {
	Title   string `json:"title"`
	Context string `json:"context"`
	// Same trap as ProjectGrant above: agent-runtime types this as
	// `Literal["C1","C2","C3"] = "C2"`, so omitting it takes the default but
	// sending "" is a literal_error. The Salesforce id beside it already had
	// omitempty; this one did not.
	Classification          string         `json:"classification,omitempty"`
	SalesforceOpportunityID string         `json:"salesforce_opportunity_id,omitempty"`
	Grants                  []ProjectGrant `json:"grants"`
}

// CreateProjectResponse is the documented response body for POST /v1/projects.
type CreateProjectResponse struct {
	ProjectID string `json:"project_id"`
}

// DeletePreview is the documented response body for
// GET /v1/projects/{project_id}/delete-preview (ADR-0527 clause 7) - the
// counts the confirmation must name before an admin archives colleagues'
// visible work.
type DeletePreview struct {
	ConversationsTotal       int `json:"conversations_total"`
	ConversationsOtherOwners int `json:"conversations_other_owners"`
	MembersUsers             int `json:"members_users"`
	MembersGroups            int `json:"members_groups"`
}

// DeleteProjectResponse is the documented response body for
// DELETE /v1/projects/{project_id} (a cascade SOFT-delete).
type DeleteProjectResponse struct {
	ConversationsArchived int `json:"conversations_archived"`
}

// ProjectStarResponse is the documented response body for
// PUT/DELETE /v1/projects/{project_id}/star.
type ProjectStarResponse struct {
	Starred bool `json:"starred"`
}

// CloneConversationResponse is the documented response body for
// POST /v1/agents/{agent}/runs/{run_id}/clone (ADR-0213).
type CloneConversationResponse struct {
	RunID       string `json:"run_id"`
	SourceRunID string `json:"source_run_id"`
	// ADR-0527: the clone stays in the SOURCE's project and takes a derived
	// title, so the frontend can name and place the new tab without
	// re-fetching the list.
	Title     string `json:"title"`
	ProjectID string `json:"project_id"`
}

// RoutingMetadata mirrors components/agent-runtime/app/schemas.py's
// RoutingMetadata (ADR-0550, WP-135) - the real per-request model-routing
// decision. Declared as its own Go struct rather than a raw map, for the
// exact ADR-0215 reason ChatResponse's own docstring below documents:
// encoding/json silently drops any JSON field this BFF's Go structs don't
// declare, so this field needed an explicit type here to reach
// apiChatResponse at all, not just the SSE streaming path (proxySSE is a
// raw byte relay and already forwards it with zero code change).
type RoutingMetadata struct {
	Agent                   string `json:"agent"`
	Task                    string `json:"task"`
	ProjectID               string `json:"project_id"`
	ProjectClassification   string `json:"project_classification"`
	EffectiveClassification string `json:"effective_classification"`
	SelectedModel           string `json:"selected_model"`
	SelectedProvider        string `json:"selected_provider"`
	ExecutionLocation       string `json:"execution_location"`
	FallbackUsed            bool   `json:"fallback_used"`
	FallbackFrom            string `json:"fallback_from,omitempty"`
	LocalOnlyRequired       bool   `json:"local_only_required"`
	RoutingReason           string `json:"routing_reason"`
}

// ChatResponse is the Agent Runtime's documented response body.
//
// ADR-0215: RunID/SourceMode were silently dropped here until this fix -
// encoding/json ignores unknown response fields by default, so the Agent
// Runtime's actual `run_id`/`source_mode` JSON keys (see components/
// agent-runtime/app/main.py's agent_chat) were present on the wire but
// never reached apiChatResponse below. That made this BFF's synchronous
// JSON path unable to resume a conversation at all - only the SSE `start`
// event (ChatStream, proxySSE) ever exposed run_id - discovered live
// while verifying ADR-0215's multi-turn history on demo222.
type ChatResponse struct {
	Reply      string     `json:"reply"`
	Citations  []Citation `json:"citations"`
	Images     []Image    `json:"images"`
	RunID      string     `json:"run_id"`
	SourceMode string     `json:"source_mode"`
	// ADR-0528: the server-resolved project this turn belonged to, so
	// agent-bff can tag its own span with zuno.project_id on the
	// non-streaming path (the streaming path reads it from the SSE start
	// event instead).
	ProjectID string `json:"project_id"`
	// ADR-0550 (WP-135): see RoutingMetadata's own comment above.
	Routing RoutingMetadata `json:"routing"`
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
		// MEMORY.md's own architecture constraint: "long document workflows
		// may take up to 10 minutes." main.go's chatHandler already derives
		// a 600s context for the non-streaming /api/chat call (see its own
		// comment), but this fixed http.Client.Timeout raced it and always
		// won at 55s regardless - confirmed live (2026-08-31): a genuine
		// DAT-drafting call surfaced as agent-bff's own 502 "agent runtime
		// unreachable" with "Client.Timeout exceeded while awaiting
		// headers" in the log, the literal net/http wording for this field
		// firing, not context cancellation. Shared with doJSON's four
		// conversation-management methods below, all of which pass their
		// own much shorter (15-30s) context - unaffected, since whichever
		// of {ctx deadline, Client.Timeout} is sooner wins.
		httpClient: &http.Client{
			Timeout: 600 * time.Second,
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

// ArchiveConversation calls DELETE /v1/agents/{agent}/runs/{run_id}
// (ADR-0212 follow-up) - soft-deletes the conversation, never touching
// its underlying LangGraph checkpoint.
func (c *Client) ArchiveConversation(ctx context.Context, bearerToken, runID string) (*ArchiveResponse, error) {
	path := fmt.Sprintf("/v1/agents/%s/runs/%s", c.agentName, url.PathEscape(runID))
	var out ArchiveResponse
	if err := c.doJSON(ctx, http.MethodDelete, bearerToken, path, nil, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// ReorderConversations calls PUT /v1/agents/{agent}/conversations/reorder
// (ADR-0515) - persists a drag-drop reorder of the caller's own
// conversation list for this agent.
func (c *Client) ReorderConversations(ctx context.Context, bearerToken string, runIDs []string) (*ReorderConversationsResponse, error) {
	path := fmt.Sprintf("/v1/agents/%s/conversations/reorder", c.agentName)
	var out ReorderConversationsResponse
	body := ReorderConversationsRequest{RunIDs: runIDs}
	if err := c.doJSON(ctx, http.MethodPut, bearerToken, path, body, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// HardDeleteConversation calls DELETE
// /v1/agents/{agent}/runs/{run_id}/hard-delete (ADR-0515) - irreversibly
// purges the conversation's metadata row and its LangGraph checkpoint,
// unlike ArchiveConversation's soft-delete above.
func (c *Client) HardDeleteConversation(ctx context.Context, bearerToken, runID string) (*HardDeleteResponse, error) {
	path := fmt.Sprintf("/v1/agents/%s/runs/%s/hard-delete", c.agentName, url.PathEscape(runID))
	var out HardDeleteResponse
	if err := c.doJSON(ctx, http.MethodDelete, bearerToken, path, nil, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// ListMembers calls GET /v1/agents/{agent}/runs/{run_id}/members
// (ADR-0213) - owner-only.
// ListProjects fetches GET /v1/projects (ADR-0527). No {agent} segment:
// a project is cross-agent, and only its conversations are agent-scoped.
func (c *Client) ListProjects(ctx context.Context, bearerToken string) ([]Project, error) {
	var out []Project
	if err := c.doJSON(ctx, http.MethodGet, bearerToken, "/v1/projects", nil, &out); err != nil {
		return nil, err
	}
	return out, nil
}

// CreateProject posts POST /v1/projects (ADR-0527). The runtime merges the
// caller's own admin grant into the submitted set, so a project can never
// be created unadministrable.
func (c *Client) CreateProject(ctx context.Context, bearerToken string, req CreateProjectRequest) (*CreateProjectResponse, error) {
	var out CreateProjectResponse
	if err := c.doJSON(ctx, http.MethodPost, bearerToken, "/v1/projects", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// GetProject fetches GET /v1/projects/{project_id} (ADR-0527).
func (c *Client) GetProject(ctx context.Context, bearerToken, projectID string) (*ProjectDetail, error) {
	var out ProjectDetail
	if err := c.doJSON(ctx, http.MethodGet, bearerToken, "/v1/projects/"+url.PathEscape(projectID), nil, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// SaveProject puts PUT /v1/projects/{project_id} (ADR-0527) - the single
// full-state commit behind the dialog's one Save.
func (c *Client) SaveProject(ctx context.Context, bearerToken, projectID string, req SaveProjectRequest) (*CreateProjectResponse, error) {
	var out CreateProjectResponse
	if err := c.doJSON(ctx, http.MethodPut, bearerToken, "/v1/projects/"+url.PathEscape(projectID), req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// DeleteProjectPreview fetches GET /v1/projects/{project_id}/delete-preview.
func (c *Client) DeleteProjectPreview(ctx context.Context, bearerToken, projectID string) (*DeletePreview, error) {
	var out DeletePreview
	if err := c.doJSON(ctx, http.MethodGet, bearerToken, "/v1/projects/"+url.PathEscape(projectID)+"/delete-preview", nil, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// DeleteProject calls DELETE /v1/projects/{project_id} - a cascade
// SOFT-delete (ADR-0527 clause 7), never a purge.
func (c *Client) DeleteProject(ctx context.Context, bearerToken, projectID string) (*DeleteProjectResponse, error) {
	var out DeleteProjectResponse
	if err := c.doJSON(ctx, http.MethodDelete, bearerToken, "/v1/projects/"+url.PathEscape(projectID), nil, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// SetProjectStar toggles the caller's personal star on a project.
func (c *Client) SetProjectStar(ctx context.Context, bearerToken, projectID string, starred bool) (*ProjectStarResponse, error) {
	method := http.MethodDelete
	if starred {
		method = http.MethodPut
	}
	var out ProjectStarResponse
	if err := c.doJSON(ctx, method, bearerToken, "/v1/projects/"+url.PathEscape(projectID)+"/star", nil, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) CloneConversation(ctx context.Context, bearerToken, runID string) (*CloneConversationResponse, error) {
	path := fmt.Sprintf("/v1/agents/%s/runs/%s/clone", c.agentName, url.PathEscape(runID))
	var out CloneConversationResponse
	if err := c.doJSON(ctx, http.MethodPost, bearerToken, path, nil, &out); err != nil {
		return nil, err
	}
	return &out, nil
}
