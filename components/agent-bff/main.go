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
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/startxfr/zuno-demo/components/agent-bff/internal/config"
	"github.com/startxfr/zuno-demo/components/agent-bff/internal/jwks"
	"github.com/startxfr/zuno-demo/components/agent-bff/internal/keycloak"
	"github.com/startxfr/zuno-demo/components/agent-bff/internal/reqid"
	"github.com/startxfr/zuno-demo/components/agent-bff/internal/runtime"
	"github.com/startxfr/zuno-demo/components/agent-bff/internal/telemetry"
)

// zunoRealm is the single Keycloak realm this whole platform uses
// (ADR-0012) - never per-agent, unlike AgentName.
const zunoRealm = "zuno"

func main() {
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("agent-bff: configuration error: %v", err)
	}

	// ADR-0029/ADR-0102: metrics are additive observability, never a
	// startup dependency - a Collector outage degrades to "no metrics",
	// same posture the Python services' init_telemetry takes.
	if _, err := telemetry.Init(context.Background(), "agent-bff"); err != nil {
		log.Printf("agent-bff: telemetry init failed, continuing without metrics: %v", err)
	}

	verifier := jwks.NewVerifier(cfg.KeycloakIssuerURL, cfg.KeycloakJWKSURL, cfg.OIDCAudience)
	runtimeClient := runtime.NewClient(cfg.AgentRuntimeBaseURL, cfg.AgentName)
	// ADR-0213: nil (colleague search fails closed, 503) until an
	// operator provisions the zuno-admin-api trust boundary - see
	// config.Config's own doc comment.
	adminClient := keycloak.NewAdminClient(cfg.KeycloakAdminBaseURL, zunoRealm, cfg.KeycloakAdminClientID, cfg.KeycloakAdminClientSecret)
	if adminClient == nil {
		log.Printf("agent-bff: KEYCLOAK_ADMIN_* not fully configured - GET /api/colleagues will fail closed (503)")
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", healthzHandler)
	mux.HandleFunc("/api/chat", chatHandler(verifier, runtimeClient, cfg.AgentName))
	// ADR-0212: thin proxy routes for persistent conversations, each
	// following chatHandler's own verify -> entitlement-check -> forward
	// shape via the shared authorize() helper. None needs the SSE branch.
	mux.HandleFunc("GET /api/conversations", listConversationsHandler(verifier, runtimeClient, cfg.AgentName))
	mux.HandleFunc("GET /api/conversations/{run_id}/transcript", transcriptHandler(verifier, runtimeClient, cfg.AgentName))
	mux.HandleFunc("PATCH /api/conversations/{run_id}", renameConversationHandler(verifier, runtimeClient, cfg.AgentName))
	mux.HandleFunc("PUT /api/conversations/{run_id}/star", starConversationHandler(verifier, runtimeClient, cfg.AgentName, true))
	mux.HandleFunc("DELETE /api/conversations/{run_id}/star", starConversationHandler(verifier, runtimeClient, cfg.AgentName, false))
	mux.HandleFunc("DELETE /api/conversations/{run_id}", archiveConversationHandler(verifier, runtimeClient, cfg.AgentName))
	// ADR-0515: manual drag-reorder and irreversible hard-delete.
	mux.HandleFunc("PUT /api/conversations/reorder", reorderConversationsHandler(verifier, runtimeClient, cfg.AgentName))
	mux.HandleFunc("DELETE /api/conversations/{run_id}/hard-delete", hardDeleteConversationHandler(verifier, runtimeClient, cfg.AgentName))
	// ADR-0527: cloning survives ADR-0213's removal, with new semantics -
	// the copy stays in the source's project and the cloner owns it.
	mux.HandleFunc("POST /api/conversations/{run_id}/clone", cloneConversationHandler(verifier, runtimeClient, cfg.AgentName))
	// ADR-0527: projects are the sharing and context boundary. No {agent}
	// segment - a project is cross-agent; only its conversations are not.
	mux.HandleFunc("GET /api/projects", listProjectsHandler(verifier, runtimeClient, cfg.AgentName))
	mux.HandleFunc("POST /api/projects", createProjectHandler(verifier, runtimeClient, cfg.AgentName))
	mux.HandleFunc("GET /api/projects/{project_id}", getProjectHandler(verifier, runtimeClient, cfg.AgentName))
	mux.HandleFunc("PUT /api/projects/{project_id}", saveProjectHandler(verifier, runtimeClient, cfg.AgentName))
	mux.HandleFunc("GET /api/projects/{project_id}/delete-preview", deleteProjectPreviewHandler(verifier, runtimeClient, cfg.AgentName))
	mux.HandleFunc("DELETE /api/projects/{project_id}", deleteProjectHandler(verifier, runtimeClient, cfg.AgentName))
	mux.HandleFunc("PUT /api/projects/{project_id}/star", starProjectHandler(verifier, runtimeClient, cfg.AgentName, true))
	mux.HandleFunc("DELETE /api/projects/{project_id}/star", starProjectHandler(verifier, runtimeClient, cfg.AgentName, false))
	// ADR-0213/ADR-0527: BFF-only, never forwards to agent-runtime. Both
	// ride the same zuno-admin-api Keycloak trust boundary and both fail
	// closed (503) until an operator provisions it.
	mux.HandleFunc("GET /api/colleagues", listColleaguesHandler(verifier, adminClient, cfg.AgentName))
	mux.HandleFunc("GET /api/groups", listGroupsHandler(verifier, adminClient, cfg.AgentName))

	server := &http.Server{
		Addr:              cfg.ListenAddr,
		Handler:           metricsMiddleware(cfg.AgentName, mux),
		ReadHeaderTimeout: 10 * time.Second,
	}

	log.Printf("agent-bff: serving agent %q, listening on %s, Agent Runtime at %s", cfg.AgentName, cfg.ListenAddr, cfg.AgentRuntimeBaseURL)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("agent-bff: server error: %v", err)
	}
}

// requestIdentity is a mutable box threaded through the request context so
// chatHandler (which decodes the caller's JWT) and metricsMiddleware
// (which records the metric, one layer further out) can share the
// caller's identity without either one calling the other directly -
// preserves metricsMiddleware's single-choke-point recording (see its own
// comment below) while still giving RecordRequest ADR-0029's "by user"
// dimension. Left zero-valued for requests that never reach a
// successfully-verified token (e.g. /healthz, a bad/missing bearer token).
type requestIdentity struct {
	sub    string
	groups []string
	// runID (ADR-0517): the chat turn's run_id, once chatHandler/proxySSE
	// learns it - empty for non-chat endpoints or a chat call that never
	// resolved one (rejected/failed before a run_id was known). Read back
	// by metricsMiddleware after the handler returns, to tag the
	// bff_request span for the per-run resource dashboard.
	runID string
}

type ctxKeyIdentity struct{}

// metricsMiddleware wraps every response in a statusRecorder and records
// one zuno.bff.requests count per completed request, labeled by this
// instance's agent, the final status code (ADR-0102's SLO indicator), and
// (ADR-0029) the caller's user/groups once chatHandler has decoded them.
// Wraps the whole mux rather than threading a counter call through every
// error/success path inside chatHandler - chatHandler has too many exit
// points (auth failures, body validation, streaming vs. synchronous) to
// do that without missing one.
func metricsMiddleware(agent string, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		identity := &requestIdentity{}
		ctx := context.WithValue(r.Context(), ctxKeyIdentity{}, identity)
		r = r.WithContext(ctx)

		// ADR-0517: opened before the handler runs and closed after it
		// returns, so it covers the whole request regardless of which
		// exit path the handler took - identity.runID is populated (when
		// known at all) by chatHandler or proxySSE during ServeHTTP, and
		// read back here since both already run to completion
		// synchronously within this call.
		span := telemetry.StartBFFRequestSpan(ctx, agent)
		start := time.Now()

		rec := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(rec, r)

		code := strconv.Itoa(rec.status)
		telemetry.RecordRequest(r.Context(), agent, code, identity.sub, identity.groups)
		telemetry.RecordDuration(r.Context(), agent, code, float64(time.Since(start).Milliseconds()))
		telemetry.EndBFFRequestSpan(span, code, identity.runID, start)
	})
}

// statusRecorder captures the status code a handler ultimately writes.
// Implements http.Flusher (delegating) so proxySSE's flush-per-chunk
// streaming behavior is unaffected by this wrapper sitting in front of it.
type statusRecorder struct {
	http.ResponseWriter
	status      int
	wroteHeader bool
}

func (r *statusRecorder) WriteHeader(status int) {
	if !r.wroteHeader {
		r.status = status
		r.wroteHeader = true
	}
	r.ResponseWriter.WriteHeader(status)
}

func (r *statusRecorder) Write(b []byte) (int, error) {
	// Mirrors net/http's own ResponseWriter contract: an implicit 200 if
	// the handler writes a body without ever calling WriteHeader.
	r.wroteHeader = true
	return r.ResponseWriter.Write(b)
}

func (r *statusRecorder) Flush() {
	if f, ok := r.ResponseWriter.(http.Flusher); ok {
		f.Flush()
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
	// ADR-0209: optional - forwarded to the Agent Runtime as-is, same
	// identity-propagation pattern as ADR-0032/0033. This BFF never
	// validates project membership itself. ADR-0512 (WP-55): for a
	// project_required task the Agent Runtime treats this as an
	// unverified CANDIDATE and verifies it against Salesforce before
	// trusting it (or blocks the request) - this BFF's own handling is
	// unchanged either way, it always just forwards the field as-is.
	ProjectID string `json:"project_id,omitempty"`
	// ADR-0212: optional - omit to start a new conversation, or supply a
	// prior response's run_id (captured from the SSE "start" event) to
	// resume it. Forwarded to the Agent Runtime as-is; this BFF does not
	// itself enforce run_id ownership, same identity-propagation pattern
	// as ProjectID above.
	RunID string `json:"run_id,omitempty"`
}

// apiChatResponse is the frontend-facing response body (see README.md).
//
// ADR-0215: RunID/SourceMode added - the synchronous JSON path had no way
// to resume a conversation at all before this (only the SSE `start` event
// exposed run_id), which meant a synchronous caller (e.g. the Tekos
// evaluation harness's scenario 7 follow-up turn, evaluations/tekos/
// run_scenarios.py) could never actually exercise multi-turn history -
// its own run_id-dependent branch silently never ran. Additive-only: an
// existing consumer that ignores unknown JSON fields is unaffected.
type apiChatResponse struct {
	Reply      string             `json:"reply"`
	Citations  []runtime.Citation `json:"citations"`
	Images     []runtime.Image    `json:"images"`
	RunID      string             `json:"run_id"`
	SourceMode string             `json:"source_mode"`
	// ADR-0528: the server-resolved project this turn belonged to, so this
	// BFF can set zuno.project_id on its own span for the non-streaming
	// path. Never the Salesforce opportunity id.
	ProjectID string `json:"project_id"`
}

type apiErrorResponse struct {
	Error string `json:"error"`
}

// apiConversation is the frontend-facing shape of one conversation-list
// entry (ADR-0212, see README.md).
type apiConversation struct {
	RunID     string `json:"run_id"`
	Title     string `json:"title"`
	UpdatedAt string `json:"updated_at"`
	Starred   bool   `json:"starred"`
	// ADR-0527: the project this conversation belongs to (empty for a
	// project-less private one) and the caller's effective role on it, so
	// the sidebar can group the list and decide read-only mode without a
	// second call.
	ProjectID string `json:"project_id"`
	Role      string `json:"role"`
}

// apiTranscriptTurn is the frontend-facing shape of one structured
// transcript entry (ADR-0212).
type apiTranscriptTurn struct {
	Role    string          `json:"role"`
	Content string          `json:"content"`
	Ts      string          `json:"ts"`
	Images  []runtime.Image `json:"images,omitempty"`
}

// apiRenameRequest is the frontend-facing request body for
// PATCH /api/conversations/{run_id} (ADR-0212).
type apiRenameRequest struct {
	Title string `json:"title"`
}

// apiRenameResponse is that endpoint's frontend-facing response body.
type apiRenameResponse struct {
	RunID string `json:"run_id"`
	Title string `json:"title"`
}

// apiStarResponse is the frontend-facing response body for both
// PUT and DELETE /api/conversations/{run_id}/star (ADR-0212).
type apiStarResponse struct {
	Starred bool `json:"starred"`
}

// apiArchiveResponse is the frontend-facing response body for
// DELETE /api/conversations/{run_id} (ADR-0212 follow-up: soft-delete).
type apiArchiveResponse struct {
	Archived bool `json:"archived"`
}

// apiReorderRequest is the frontend-facing request body for
// PUT /api/conversations/reorder (ADR-0515) - the caller's full desired
// run_id order for this agent.
type apiReorderRequest struct {
	RunIDs []string `json:"run_ids"`
}

// apiReorderResponse is that endpoint's frontend-facing response body.
type apiReorderResponse struct {
	Updated int `json:"updated"`
}

// apiHardDeleteResponse is the frontend-facing response body for
// DELETE /api/conversations/{run_id}/hard-delete (ADR-0515) -
// irreversible, unlike apiArchiveResponse's soft-delete.
type apiHardDeleteResponse struct {
	Deleted bool `json:"deleted"`
}

// projectContextMaxChars mirrors app/projects.py's PROJECT_CONTEXT_MAX_CHARS,
// app/schemas.py's, and the projects DDL's ck_projects_context_length
// (ADR-0527 clause 5). Checked here too so an oversized body is refused at
// the edge rather than after travelling the whole chain.
const projectContextMaxChars = 54000

// apiProject is the frontend-facing shape of one entry of GET /api/projects
// (ADR-0527). Carries no Salesforce identifier by design - ADR-0528 keeps it
// off every surface that does not strictly need it, so the list says only
// WHETHER this is a customer project.
type apiProject struct {
	ProjectID         string `json:"project_id"`
	Title             string `json:"title"`
	Classification    string `json:"classification"`
	IsCustomer        bool   `json:"is_customer"`
	Starred           bool   `json:"starred"`
	Role              string `json:"role"`
	ConversationCount int    `json:"conversation_count"`
	UpdatedAt         string `json:"updated_at"`
}

// apiProjectGrant is one entry of a project's ACL (ADR-0527). Exactly one of
// Subject/GroupName is set.
type apiProjectGrant struct {
	Subject   string `json:"subject"`
	GroupName string `json:"group_name"`
	Role      string `json:"role"`
	// Response-only; ignored on the way in.
	GrantedBy string `json:"granted_by"`
	CreatedAt string `json:"created_at"`
}

// apiProjectDetail is the frontend-facing shape of GET /api/projects/{id}.
// Grants and the Salesforce fields arrive populated only for an admin -
// agent-runtime decides that, this BFF only relays what it was given.
type apiProjectDetail struct {
	ProjectID               string            `json:"project_id"`
	Title                   string            `json:"title"`
	Context                 string            `json:"context"`
	Classification          string            `json:"classification"`
	IsCustomer              bool              `json:"is_customer"`
	Role                    string            `json:"role"`
	CreatedBy               string            `json:"created_by"`
	CreatedAt               string            `json:"created_at"`
	UpdatedAt               string            `json:"updated_at"`
	Grants                  []apiProjectGrant `json:"grants"`
	SalesforceOpportunityID string            `json:"salesforce_opportunity_id"`
	SalesforceVerifiedAt    string            `json:"salesforce_verified_at"`
}

// apiCreateProjectRequest is the frontend-facing request body for
// POST /api/projects (ADR-0527).
type apiCreateProjectRequest struct {
	Title                   string            `json:"title"`
	Context                 string            `json:"context"`
	Classification          string            `json:"classification"`
	SalesforceOpportunityID string            `json:"salesforce_opportunity_id"`
	Grants                  []apiProjectGrant `json:"grants"`
}

// apiSaveProjectRequest is the frontend-facing request body for
// PUT /api/projects/{project_id} - the WHOLE desired state, committed by the
// dialog's single Save. A null `grants` means "not editing grants" and
// leaves them untouched; a non-null one is the full desired set.
type apiSaveProjectRequest struct {
	Title                   string            `json:"title"`
	Context                 string            `json:"context"`
	Classification          string            `json:"classification"`
	SalesforceOpportunityID string            `json:"salesforce_opportunity_id"`
	Grants                  []apiProjectGrant `json:"grants"`
}

// apiCreateProjectResponse is the response body for both POST /api/projects
// and PUT /api/projects/{project_id}.
type apiCreateProjectResponse struct {
	ProjectID string `json:"project_id"`
}

// apiDeletePreview is the response body for
// GET /api/projects/{project_id}/delete-preview (ADR-0527 clause 7).
type apiDeletePreview struct {
	ConversationsTotal       int `json:"conversations_total"`
	ConversationsOtherOwners int `json:"conversations_other_owners"`
	MembersUsers             int `json:"members_users"`
	MembersGroups            int `json:"members_groups"`
}

// apiDeleteProjectResponse is the response body for
// DELETE /api/projects/{project_id} - a cascade SOFT-delete.
type apiDeleteProjectResponse struct {
	ConversationsArchived int `json:"conversations_archived"`
}

// apiProjectStarResponse is the response body for
// PUT/DELETE /api/projects/{project_id}/star.
type apiProjectStarResponse struct {
	Starred bool `json:"starred"`
}

// apiRealmGroup is one GET /api/groups entry (ADR-0527): a business-role
// group that may be a project grant target. Agent entitlement groups
// (agent_*) are filtered out server-side and never appear here.
type apiRealmGroup struct {
	Name string `json:"name"`
	Path string `json:"path"`
}

// apiCloneConversationResponse is the frontend-facing response body for
// POST /api/conversations/{run_id}/clone (ADR-0213).
type apiCloneConversationResponse struct {
	RunID       string `json:"run_id"`
	SourceRunID string `json:"source_run_id"`
	// ADR-0527: the clone keeps the source's project and takes a derived
	// title, so the frontend can name and place the new tab directly.
	Title     string `json:"title"`
	ProjectID string `json:"project_id"`
}

// apiColleague is one GET /api/colleagues search result. Ineligible
// candidates are still included (Eligible: false) so the frontend can
// grey them out rather than hide them, per the ADR's explicit product
// requirement.
type apiColleague struct {
	Sub         string `json:"sub"`
	DisplayName string `json:"displayName"`
	Eligible    bool   `json:"eligible"`
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
		// ADR-0517: kept in this outer scope (rather than the if-block's
		// own shadowed variable) so the run_id/streaming branches below
		// can also set identity.runID once they learn it.
		identity, _ := r.Context().Value(ctxKeyIdentity{}).(*requestIdentity)
		if identity != nil {
			identity.sub = claims.Subject
			identity.groups = claims.Groups
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
		if strings.TrimSpace(req.SessionID) == "" {
			w.Header().Set("Content-Type", "application/json")
			writeError(w, http.StatusBadRequest, "session_id is required")
			return
		}

		requestID := reqid.FromHeaderOrNew(r.Header)
		runtimeReq := runtime.ChatRequest{
			SessionID: req.SessionID,
			UserSub:   claims.Subject, // informational only (ADR-0033); the Runtime derives identity from the forwarded token, not this field
			Message:   req.Message,
			ProjectID: req.ProjectID, // ADR-0209: forwarded as-is, this BFF does not validate project membership
			RunID:     req.RunID,     // ADR-0212: forwarded as-is, the Agent Runtime enforces ownership
		}
		// ADR-0517: a resumed conversation already knows its run_id
		// upfront - a brand-new one doesn't until agent-runtime's first
		// SSE "start" event (streaming) or its JSON response (non-
		// streaming), handled at each of those points below.
		if identity != nil && req.RunID != "" {
			identity.runID = req.RunID
		}

		if strings.Contains(r.Header.Get("Accept"), "text/event-stream") {
			// A full streamed reply can legitimately take longer than a
			// single non-streaming call - bounded generously rather than
			// left unbounded, but well past the synchronous path's 110s
			// (raised 2026-08-21 from 55s/120s: long-form DAT/workshop
			// drafting plus a reflect pass was routinely running past 55s
			// even before accounting for the local-gpt-oss/image-gen
			// issues fixed the same day).
			ctx, cancel := context.WithTimeout(r.Context(), 180*time.Second)
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
				proxySSE(w, resp, identity)
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

		// 2026-08-21: raised from 55s - long-form DAT/workshop drafting
		// plus a reflect pass was routinely running past it, independent
		// of the local-gpt-oss/image-gen issues fixed the same day.
		ctx, cancel := context.WithTimeout(r.Context(), 110*time.Second)
		defer cancel()

		resp, err := runtimeClient.Chat(ctx, token, runtimeReq)
		if identity != nil && resp != nil {
			// ADR-0517: always populated by the time a non-streaming call
			// returns successfully, whether this was a brand-new or
			// resumed conversation.
			identity.runID = resp.RunID
		}
		if err != nil {
			log.Printf("agent-bff: agent runtime call failed: %v", err)
			w.Header().Set("Content-Type", "application/json")
			// A 4xx from Agent Runtime means it rejected this specific
			// request (bad body, auth) - relay that as our own 4xx instead
			// of collapsing it into a generic 502, which would otherwise
			// hide a real client-side problem behind a false "upstream is
			// down" signal. A connection failure or a 5xx has no such
			// status to relay and stays 502.
			var upstream *runtime.UpstreamError
			if errors.As(err, &upstream) && upstream.StatusCode >= 400 && upstream.StatusCode < 500 {
				writeError(w, upstream.StatusCode, "agent runtime rejected the request")
			} else {
				writeError(w, http.StatusBadGateway, "agent runtime unreachable")
			}
			return
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(apiChatResponse{
			Reply:      resp.Reply,
			Citations:  resp.Citations,
			Images:     resp.Images,
			RunID:      resp.RunID,
			SourceMode: resp.SourceMode,
			ProjectID:  resp.ProjectID,
		})
	}
}

// runIDFromSSE extracts run_id from agent-runtime's very first SSE event
// ("start", always emitted before any token - see
// components/agent-runtime/app/main.go's `_stream_chat`). Deliberately a
// simple substring scan rather than parsing SSE framing/JSON properly:
// this is a best-effort peek (ADR-0517), not a protocol implementation -
// see proxySSE's own comment on why a miss here is never fatal.
var runIDFromSSE = regexp.MustCompile(`"run_id"\s*:\s*"([^"]+)"`)

// proxySSE relays an already-200-OK SSE response body to w chunk by chunk,
// flushing after every read so token deltas reach the caller as they
// arrive rather than being buffered - see
// components/agent-frontend/internal/chat/chat.go's identically-named
// function for the next hop down and the same client-cancellation
// reasoning.
//
// ADR-0517: also peeks the first few reads for run_id, when identity
// doesn't already have one (a brand-new, not resumed, conversation) - so
// metricsMiddleware's bff_request span still gets tagged with run_id even
// on this path, where chatHandler itself never sees the value (it's inside
// the streamed body, not the initial response headers). Best-effort: if
// the "start" event never shows up intact within the first few reads (a
// fragmented write, or a future protocol change), the span is simply left
// untagged rather than blocking/buffering the stream indefinitely.
func proxySSE(w http.ResponseWriter, resp *http.Response, identity *requestIdentity) {
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("X-Accel-Buffering", "no")
	w.WriteHeader(http.StatusOK)

	flusher, canFlush := w.(http.Flusher)
	buf := make([]byte, 4096)

	needRunID := identity != nil && identity.runID == ""
	var pending []byte
	attemptsLeft := 4

	for {
		n, readErr := resp.Body.Read(buf)
		if n > 0 {
			if needRunID {
				pending = append(pending, buf[:n]...)
				if m := runIDFromSSE.FindSubmatch(pending); m != nil {
					identity.runID = string(m[1])
					needRunID = false
					pending = nil
				} else {
					attemptsLeft--
					if attemptsLeft <= 0 || len(pending) > 8192 {
						needRunID = false // give up looking, stop buffering
						pending = nil
					}
				}
			}
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

// authorize validates the caller's bearer token and agent_<agentName>
// entitlement (ADR-0040) - the same check chatHandler performs inline,
// factored out here since every conversation-management handler below
// (ADR-0212) needs the identical check. Sets the response's Content-Type
// unconditionally (every response from these handlers, success or
// failure, is JSON) and writes an error body itself on failure - the
// caller only needs to check ok and return immediately.
func authorize(
	w http.ResponseWriter, r *http.Request, verifier *jwks.Verifier, entitlementGroup string, identity *requestIdentity,
) (token string, ok bool) {
	w.Header().Set("Content-Type", "application/json")

	token = bearerToken(r)
	if token == "" {
		writeError(w, http.StatusUnauthorized, "missing bearer token")
		return "", false
	}
	claims, err := verifier.Verify(token)
	if err != nil {
		log.Printf("agent-bff: token verification failed: %v", err)
		writeError(w, http.StatusUnauthorized, "invalid or expired token")
		return "", false
	}
	if identity != nil {
		identity.sub = claims.Subject
		identity.groups = claims.Groups
	}
	if !hasGroup(claims.Groups, entitlementGroup) {
		log.Printf("agent-bff: subject %q lacks entitlement group %q", claims.Subject, entitlementGroup)
		writeError(w, http.StatusForbidden, "not entitled to this agent")
		return "", false
	}
	return token, true
}

// writeUpstreamError maps an Agent Runtime call error the same way
// chatHandler's synchronous path does: a genuine 4xx from the Runtime
// means it rejected this specific request (e.g. an unknown/not-owned
// run_id) and is relayed as that same status; a connectivity failure or
// 5xx has no such status to relay and falls back to 502.
func writeUpstreamError(w http.ResponseWriter, err error, fallback string) {
	var upstream *runtime.UpstreamError
	if errors.As(err, &upstream) && upstream.StatusCode >= 400 && upstream.StatusCode < 500 {
		writeError(w, upstream.StatusCode, "agent runtime rejected the request")
		return
	}
	writeError(w, http.StatusBadGateway, fallback)
}

// listConversationsHandler handles GET /api/conversations (ADR-0212): the
// caller's own conversations for this agent, `?starred=true` to filter to
// starred only.
func listConversationsHandler(verifier *jwks.Verifier, runtimeClient *runtime.Client, agentName string) http.HandlerFunc {
	entitlementGroup := "agent_" + agentName
	return func(w http.ResponseWriter, r *http.Request) {
		identity, _ := r.Context().Value(ctxKeyIdentity{}).(*requestIdentity)
		token, ok := authorize(w, r, verifier, entitlementGroup, identity)
		if !ok {
			return
		}

		ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
		defer cancel()
		items, err := runtimeClient.ListConversations(ctx, token, r.URL.Query().Get("starred") == "true")
		if err != nil {
			log.Printf("agent-bff: agent runtime list-conversations call failed: %v", err)
			writeUpstreamError(w, err, "agent runtime unreachable")
			return
		}

		out := make([]apiConversation, len(items))
		for i, c := range items {
			out[i] = apiConversation{
				RunID: c.RunID, Title: c.Title, UpdatedAt: c.UpdatedAt, Starred: c.Starred,
				ProjectID: c.ProjectID, Role: c.Role,
			}
		}
		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(out)
	}
}

// transcriptHandler handles GET /api/conversations/{run_id}/transcript
// (ADR-0212): the structured message history for reopening a conversation
// from the left-nav.
func transcriptHandler(verifier *jwks.Verifier, runtimeClient *runtime.Client, agentName string) http.HandlerFunc {
	entitlementGroup := "agent_" + agentName
	return func(w http.ResponseWriter, r *http.Request) {
		identity, _ := r.Context().Value(ctxKeyIdentity{}).(*requestIdentity)
		token, ok := authorize(w, r, verifier, entitlementGroup, identity)
		if !ok {
			return
		}

		ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
		defer cancel()
		turns, err := runtimeClient.GetTranscript(ctx, token, r.PathValue("run_id"))
		if err != nil {
			log.Printf("agent-bff: agent runtime transcript call failed: %v", err)
			writeUpstreamError(w, err, "agent runtime unreachable")
			return
		}

		out := make([]apiTranscriptTurn, len(turns))
		for i, t := range turns {
			out[i] = apiTranscriptTurn{Role: t.Role, Content: t.Content, Ts: t.Ts, Images: t.Images}
		}
		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(out)
	}
}

// renameConversationHandler handles PATCH /api/conversations/{run_id}
// (ADR-0212).
func renameConversationHandler(verifier *jwks.Verifier, runtimeClient *runtime.Client, agentName string) http.HandlerFunc {
	entitlementGroup := "agent_" + agentName
	return func(w http.ResponseWriter, r *http.Request) {
		identity, _ := r.Context().Value(ctxKeyIdentity{}).(*requestIdentity)
		token, ok := authorize(w, r, verifier, entitlementGroup, identity)
		if !ok {
			return
		}

		var req apiRenameRequest
		if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20)).Decode(&req); err != nil {
			writeError(w, http.StatusBadRequest, "invalid request body")
			return
		}
		if strings.TrimSpace(req.Title) == "" {
			writeError(w, http.StatusBadRequest, "title is required")
			return
		}

		ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
		defer cancel()
		renamed, err := runtimeClient.RenameConversation(ctx, token, r.PathValue("run_id"), req.Title)
		if err != nil {
			log.Printf("agent-bff: agent runtime rename call failed: %v", err)
			writeUpstreamError(w, err, "agent runtime unreachable")
			return
		}

		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(apiRenameResponse{RunID: renamed.RunID, Title: renamed.Title})
	}
}

// starConversationHandler handles both PUT (starred=true) and DELETE
// (starred=false) /api/conversations/{run_id}/star (ADR-0212) - registered
// twice in main() under the two methods, each with its own fixed starred
// value, since a bare toggle would need to read current state first.
func starConversationHandler(verifier *jwks.Verifier, runtimeClient *runtime.Client, agentName string, starred bool) http.HandlerFunc {
	entitlementGroup := "agent_" + agentName
	return func(w http.ResponseWriter, r *http.Request) {
		identity, _ := r.Context().Value(ctxKeyIdentity{}).(*requestIdentity)
		token, ok := authorize(w, r, verifier, entitlementGroup, identity)
		if !ok {
			return
		}

		ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
		defer cancel()
		result, err := runtimeClient.SetStar(ctx, token, r.PathValue("run_id"), starred)
		if err != nil {
			log.Printf("agent-bff: agent runtime set-star call failed: %v", err)
			writeUpstreamError(w, err, "agent runtime unreachable")
			return
		}

		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(apiStarResponse{Starred: result.Starred})
	}
}

// archiveConversationHandler handles DELETE /api/conversations/{run_id}
// (ADR-0212 follow-up: soft-delete).
func archiveConversationHandler(verifier *jwks.Verifier, runtimeClient *runtime.Client, agentName string) http.HandlerFunc {
	entitlementGroup := "agent_" + agentName
	return func(w http.ResponseWriter, r *http.Request) {
		identity, _ := r.Context().Value(ctxKeyIdentity{}).(*requestIdentity)
		token, ok := authorize(w, r, verifier, entitlementGroup, identity)
		if !ok {
			return
		}

		ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
		defer cancel()
		result, err := runtimeClient.ArchiveConversation(ctx, token, r.PathValue("run_id"))
		if err != nil {
			log.Printf("agent-bff: agent runtime archive-conversation call failed: %v", err)
			writeUpstreamError(w, err, "agent runtime unreachable")
			return
		}

		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(apiArchiveResponse{Archived: result.Archived})
	}
}

// reorderConversationsHandler handles PUT /api/conversations/reorder
// (ADR-0515): persists a drag-drop reorder of the caller's own
// conversation list for this agent.
func reorderConversationsHandler(verifier *jwks.Verifier, runtimeClient *runtime.Client, agentName string) http.HandlerFunc {
	entitlementGroup := "agent_" + agentName
	return func(w http.ResponseWriter, r *http.Request) {
		identity, _ := r.Context().Value(ctxKeyIdentity{}).(*requestIdentity)
		token, ok := authorize(w, r, verifier, entitlementGroup, identity)
		if !ok {
			return
		}

		var req apiReorderRequest
		if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20)).Decode(&req); err != nil {
			writeError(w, http.StatusBadRequest, "invalid request body")
			return
		}
		if len(req.RunIDs) == 0 {
			writeError(w, http.StatusBadRequest, "run_ids is required")
			return
		}

		ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
		defer cancel()
		result, err := runtimeClient.ReorderConversations(ctx, token, req.RunIDs)
		if err != nil {
			log.Printf("agent-bff: agent runtime reorder-conversations call failed: %v", err)
			writeUpstreamError(w, err, "agent runtime unreachable")
			return
		}

		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(apiReorderResponse{Updated: result.Updated})
	}
}

// hardDeleteConversationHandler handles
// DELETE /api/conversations/{run_id}/hard-delete (ADR-0515): irreversibly
// purges the conversation, unlike archiveConversationHandler's
// soft-delete above.
func hardDeleteConversationHandler(verifier *jwks.Verifier, runtimeClient *runtime.Client, agentName string) http.HandlerFunc {
	entitlementGroup := "agent_" + agentName
	return func(w http.ResponseWriter, r *http.Request) {
		identity, _ := r.Context().Value(ctxKeyIdentity{}).(*requestIdentity)
		token, ok := authorize(w, r, verifier, entitlementGroup, identity)
		if !ok {
			return
		}

		ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
		defer cancel()
		result, err := runtimeClient.HardDeleteConversation(ctx, token, r.PathValue("run_id"))
		if err != nil {
			log.Printf("agent-bff: agent runtime hard-delete-conversation call failed: %v", err)
			writeUpstreamError(w, err, "agent runtime unreachable")
			return
		}

		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(apiHardDeleteResponse{Deleted: result.Deleted})
	}
}

// --------------------------------------------------------------------------
// ADR-0527: projects. Thin proxies in the same shape as every conversation
// handler above - authorize() enforces ADR-0040's agent entitlement (the
// first RBAC dimension), and the project role (the second) is resolved by
// agent-runtime against project_grants, never here.
// --------------------------------------------------------------------------

// listProjectsHandler handles GET /api/projects.
func listProjectsHandler(verifier *jwks.Verifier, runtimeClient *runtime.Client, agentName string) http.HandlerFunc {
	entitlementGroup := "agent_" + agentName
	return func(w http.ResponseWriter, r *http.Request) {
		identity, _ := r.Context().Value(ctxKeyIdentity{}).(*requestIdentity)
		token, ok := authorize(w, r, verifier, entitlementGroup, identity)
		if !ok {
			return
		}

		ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
		defer cancel()
		items, err := runtimeClient.ListProjects(ctx, token)
		if err != nil {
			log.Printf("agent-bff: agent runtime list-projects call failed: %v", err)
			writeUpstreamError(w, err, "agent runtime unreachable")
			return
		}

		out := make([]apiProject, len(items))
		for i, p := range items {
			out[i] = apiProject{
				ProjectID: p.ProjectID, Title: p.Title, Classification: p.Classification,
				IsCustomer: p.IsCustomer, Starred: p.Starred, Role: p.Role,
				ConversationCount: p.ConversationCount, UpdatedAt: p.UpdatedAt,
			}
		}
		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(out)
	}
}

// validateGrants applies the two grant rules this BFF can check without a
// database: exactly one target per grant, and a known role. The last-admin
// guard and the duplicate check need the whole set in context and stay in
// agent-runtime's assert_grants_are_valid, which is the authority - this is
// a fast 400 for an obviously malformed body, not the authorization.
func validateGrants(grants []apiProjectGrant) error {
	for _, g := range grants {
		if (g.Subject == "") == (g.GroupName == "") {
			return fmt.Errorf("each grant must name exactly one of subject or group_name")
		}
		switch g.Role {
		case "read", "clone", "write", "admin":
		default:
			return fmt.Errorf("role must be one of read, clone, write, admin")
		}
		// ADR-0040: agent_<name> entitlement groups are not business-role
		// groups and can never be a grant target. Refused here AND in
		// agent-runtime, on both the write and the resolution side, so
		// neither a bad write nor a stale row can widen access.
		if g.GroupName != "" && strings.HasPrefix(g.GroupName, "agent_") {
			return fmt.Errorf("%q is an agent entitlement group, not a business-role group - it cannot be a project grant target", g.GroupName)
		}
	}
	return nil
}

func toRuntimeGrants(grants []apiProjectGrant) []runtime.ProjectGrant {
	out := make([]runtime.ProjectGrant, len(grants))
	for i, g := range grants {
		out[i] = runtime.ProjectGrant{Subject: g.Subject, GroupName: g.GroupName, Role: g.Role}
	}
	return out
}

// createProjectHandler handles POST /api/projects.
func createProjectHandler(verifier *jwks.Verifier, runtimeClient *runtime.Client, agentName string) http.HandlerFunc {
	entitlementGroup := "agent_" + agentName
	return func(w http.ResponseWriter, r *http.Request) {
		identity, _ := r.Context().Value(ctxKeyIdentity{}).(*requestIdentity)
		token, ok := authorize(w, r, verifier, entitlementGroup, identity)
		if !ok {
			return
		}

		var req apiCreateProjectRequest
		if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20)).Decode(&req); err != nil {
			writeError(w, http.StatusBadRequest, "invalid JSON body")
			return
		}
		if strings.TrimSpace(req.Title) == "" {
			writeError(w, http.StatusBadRequest, "title is required")
			return
		}
		// ADR-0527 clause 5: the same 54000 ceiling the request schema and
		// the SQL CHECK enforce - rejected here too so an oversized body
		// never travels the whole chain to be refused at the end.
		if len(req.Context) > projectContextMaxChars {
			writeError(w, http.StatusBadRequest, fmt.Sprintf("context must be at most %d characters", projectContextMaxChars))
			return
		}
		if err := validateGrants(req.Grants); err != nil {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}

		ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
		defer cancel()
		result, err := runtimeClient.CreateProject(ctx, token, runtime.CreateProjectRequest{
			Title:                   req.Title,
			Context:                 req.Context,
			Classification:          req.Classification,
			SalesforceOpportunityID: req.SalesforceOpportunityID,
			Grants:                  toRuntimeGrants(req.Grants),
		})
		if err != nil {
			log.Printf("agent-bff: agent runtime create-project call failed: %v", err)
			writeUpstreamError(w, err, "agent runtime unreachable")
			return
		}

		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(apiCreateProjectResponse{ProjectID: result.ProjectID})
	}
}

// getProjectHandler handles GET /api/projects/{project_id}.
func getProjectHandler(verifier *jwks.Verifier, runtimeClient *runtime.Client, agentName string) http.HandlerFunc {
	entitlementGroup := "agent_" + agentName
	return func(w http.ResponseWriter, r *http.Request) {
		identity, _ := r.Context().Value(ctxKeyIdentity{}).(*requestIdentity)
		token, ok := authorize(w, r, verifier, entitlementGroup, identity)
		if !ok {
			return
		}

		ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
		defer cancel()
		detail, err := runtimeClient.GetProject(ctx, token, r.PathValue("project_id"))
		if err != nil {
			log.Printf("agent-bff: agent runtime get-project call failed: %v", err)
			writeUpstreamError(w, err, "agent runtime unreachable")
			return
		}

		grants := make([]apiProjectGrant, len(detail.Grants))
		for i, g := range detail.Grants {
			grants[i] = apiProjectGrant{
				Subject: g.Subject, GroupName: g.GroupName, Role: g.Role,
				GrantedBy: g.GrantedBy, CreatedAt: g.CreatedAt,
			}
		}
		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(apiProjectDetail{
			ProjectID: detail.ProjectID, Title: detail.Title, Context: detail.Context,
			Classification: detail.Classification, IsCustomer: detail.IsCustomer, Role: detail.Role,
			CreatedBy: detail.CreatedBy, CreatedAt: detail.CreatedAt, UpdatedAt: detail.UpdatedAt,
			Grants:                  grants,
			SalesforceOpportunityID: detail.SalesforceOpportunityID,
			SalesforceVerifiedAt:    detail.SalesforceVerifiedAt,
		})
	}
}

// saveProjectHandler handles PUT /api/projects/{project_id} - the single
// full-state commit behind the dialog's one Save.
func saveProjectHandler(verifier *jwks.Verifier, runtimeClient *runtime.Client, agentName string) http.HandlerFunc {
	entitlementGroup := "agent_" + agentName
	return func(w http.ResponseWriter, r *http.Request) {
		identity, _ := r.Context().Value(ctxKeyIdentity{}).(*requestIdentity)
		token, ok := authorize(w, r, verifier, entitlementGroup, identity)
		if !ok {
			return
		}

		var req apiSaveProjectRequest
		if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20)).Decode(&req); err != nil {
			writeError(w, http.StatusBadRequest, "invalid JSON body")
			return
		}
		if strings.TrimSpace(req.Title) == "" {
			writeError(w, http.StatusBadRequest, "title is required")
			return
		}
		if len(req.Context) > projectContextMaxChars {
			writeError(w, http.StatusBadRequest, fmt.Sprintf("context must be at most %d characters", projectContextMaxChars))
			return
		}
		if req.Grants != nil {
			if err := validateGrants(req.Grants); err != nil {
				writeError(w, http.StatusBadRequest, err.Error())
				return
			}
		}

		ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
		defer cancel()
		result, err := runtimeClient.SaveProject(ctx, token, r.PathValue("project_id"), runtime.SaveProjectRequest{
			Title:                   req.Title,
			Context:                 req.Context,
			Classification:          req.Classification,
			SalesforceOpportunityID: req.SalesforceOpportunityID,
			Grants:                  toRuntimeGrants(req.Grants),
		})
		if err != nil {
			log.Printf("agent-bff: agent runtime save-project call failed: %v", err)
			writeUpstreamError(w, err, "agent runtime unreachable")
			return
		}

		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(apiCreateProjectResponse{ProjectID: result.ProjectID})
	}
}

// deleteProjectPreviewHandler handles GET /api/projects/{project_id}/delete-preview.
func deleteProjectPreviewHandler(verifier *jwks.Verifier, runtimeClient *runtime.Client, agentName string) http.HandlerFunc {
	entitlementGroup := "agent_" + agentName
	return func(w http.ResponseWriter, r *http.Request) {
		identity, _ := r.Context().Value(ctxKeyIdentity{}).(*requestIdentity)
		token, ok := authorize(w, r, verifier, entitlementGroup, identity)
		if !ok {
			return
		}

		ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
		defer cancel()
		preview, err := runtimeClient.DeleteProjectPreview(ctx, token, r.PathValue("project_id"))
		if err != nil {
			log.Printf("agent-bff: agent runtime delete-preview call failed: %v", err)
			writeUpstreamError(w, err, "agent runtime unreachable")
			return
		}

		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(apiDeletePreview{
			ConversationsTotal:       preview.ConversationsTotal,
			ConversationsOtherOwners: preview.ConversationsOtherOwners,
			MembersUsers:             preview.MembersUsers,
			MembersGroups:            preview.MembersGroups,
		})
	}
}

// deleteProjectHandler handles DELETE /api/projects/{project_id} - a
// cascade SOFT-delete (ADR-0527 clause 7), never a purge.
func deleteProjectHandler(verifier *jwks.Verifier, runtimeClient *runtime.Client, agentName string) http.HandlerFunc {
	entitlementGroup := "agent_" + agentName
	return func(w http.ResponseWriter, r *http.Request) {
		identity, _ := r.Context().Value(ctxKeyIdentity{}).(*requestIdentity)
		token, ok := authorize(w, r, verifier, entitlementGroup, identity)
		if !ok {
			return
		}

		ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
		defer cancel()
		result, err := runtimeClient.DeleteProject(ctx, token, r.PathValue("project_id"))
		if err != nil {
			log.Printf("agent-bff: agent runtime delete-project call failed: %v", err)
			writeUpstreamError(w, err, "agent runtime unreachable")
			return
		}

		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(apiDeleteProjectResponse{ConversationsArchived: result.ConversationsArchived})
	}
}

// starProjectHandler handles PUT/DELETE /api/projects/{project_id}/star.
func starProjectHandler(verifier *jwks.Verifier, runtimeClient *runtime.Client, agentName string, starred bool) http.HandlerFunc {
	entitlementGroup := "agent_" + agentName
	return func(w http.ResponseWriter, r *http.Request) {
		identity, _ := r.Context().Value(ctxKeyIdentity{}).(*requestIdentity)
		token, ok := authorize(w, r, verifier, entitlementGroup, identity)
		if !ok {
			return
		}

		ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
		defer cancel()
		result, err := runtimeClient.SetProjectStar(ctx, token, r.PathValue("project_id"), starred)
		if err != nil {
			log.Printf("agent-bff: agent runtime project-star call failed: %v", err)
			writeUpstreamError(w, err, "agent runtime unreachable")
			return
		}

		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(apiProjectStarResponse{Starred: result.Starred})
	}
}

// cloneConversationHandler handles POST /api/conversations/{run_id}/clone
// (ADR-0527 clause 4): any role from `clone` upward; the copy stays in the
// source's project and the cloner owns it.
func cloneConversationHandler(verifier *jwks.Verifier, runtimeClient *runtime.Client, agentName string) http.HandlerFunc {
	entitlementGroup := "agent_" + agentName
	return func(w http.ResponseWriter, r *http.Request) {
		identity, _ := r.Context().Value(ctxKeyIdentity{}).(*requestIdentity)
		token, ok := authorize(w, r, verifier, entitlementGroup, identity)
		if !ok {
			return
		}

		ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
		defer cancel()
		result, err := runtimeClient.CloneConversation(ctx, token, r.PathValue("run_id"))
		if err != nil {
			log.Printf("agent-bff: agent runtime clone-conversation call failed: %v", err)
			writeUpstreamError(w, err, "agent runtime unreachable")
			return
		}

		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(apiCloneConversationResponse{
			RunID: result.RunID, SourceRunID: result.SourceRunID,
			Title: result.Title, ProjectID: result.ProjectID,
		})
	}
}

// listColleaguesHandler handles GET /api/colleagues (ADR-0213): BFF-only,
// never forwards to agent-runtime. Fails closed (503) when adminClient is
// nil (the zuno-admin-api trust boundary isn't provisioned yet) or when
// the Keycloak Admin API call itself fails - never returns a silent
// empty/wrong list. Eligibility: a candidate must hold this agent's own
// entitlement group AND share at least one business-role group with the
// caller - both computed here from live Keycloak group membership, never
// re-verified by agent-runtime's grant endpoint (that endpoint trusts
// this computation, the ADR's own explicitly-accepted trust boundary).
func listColleaguesHandler(verifier *jwks.Verifier, adminClient *keycloak.AdminClient, agentName string) http.HandlerFunc {
	entitlementGroup := "agent_" + agentName
	return func(w http.ResponseWriter, r *http.Request) {
		identity, _ := r.Context().Value(ctxKeyIdentity{}).(*requestIdentity)
		_, ok := authorize(w, r, verifier, entitlementGroup, identity)
		if !ok {
			return
		}
		if adminClient == nil {
			writeError(w, http.StatusServiceUnavailable, "colleague search is unavailable")
			return
		}

		ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
		defer cancel()
		users, err := adminClient.SearchUsers(ctx, r.URL.Query().Get("q"))
		if err != nil {
			log.Printf("agent-bff: keycloak admin user search failed: %v", err)
			writeError(w, http.StatusServiceUnavailable, "colleague search is unavailable")
			return
		}

		callerGroups := make(map[string]struct{}, len(identity.groups))
		for _, g := range identity.groups {
			callerGroups[strings.TrimPrefix(g, "/")] = struct{}{}
		}

		out := make([]apiColleague, 0, len(users))
		for _, u := range users {
			if u.ID == identity.sub {
				continue // never offer the caller themselves as a share target
			}
			groups, err := adminClient.UserGroups(ctx, u.ID)
			if err != nil {
				log.Printf("agent-bff: keycloak admin group lookup failed for user %q: %v", u.ID, err)
				continue // skip this one candidate rather than fail the whole search
			}
			hasEntitlement := false
			sharesBusinessRole := false
			for _, g := range groups {
				if g == entitlementGroup {
					hasEntitlement = true
				} else if _, shared := callerGroups[g]; shared {
					sharesBusinessRole = true
				}
			}
			out = append(out, apiColleague{
				Sub:         u.ID,
				DisplayName: u.DisplayName(),
				Eligible:    hasEntitlement && sharesBusinessRole,
			})
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(out)
	}
}

// listGroupsHandler handles GET /api/groups (ADR-0527): BFF-only, never
// forwards to agent-runtime, and rides the same zuno-admin-api Keycloak
// Admin API trust boundary ADR-0213 introduced for /api/colleagues.
//
// Returns only BUSINESS-ROLE groups. ADR-0040 keeps agent_<name>
// entitlement ("which agent may this person open at all") apart from
// business role ("what may they reach inside it"), and offering an
// entitlement group as a project grant target would collapse the two -
// "shared with the consultants" would silently become "shared with everyone
// who can open this agent". Filtered here and refused again in
// agent-runtime, so neither layer alone is load-bearing.
//
// Fails closed with 503 in BOTH failure modes: no admin client (the
// zuno-admin-api client isn't provisioned yet) and any Keycloak error -
// including the 403 returned when the service account lacks the
// query-groups role. Never a 200 with an empty list, which would read as
// "this realm has no groups" and quietly prevent every group grant.
func listGroupsHandler(verifier *jwks.Verifier, adminClient *keycloak.AdminClient, agentName string) http.HandlerFunc {
	entitlementGroup := "agent_" + agentName
	return func(w http.ResponseWriter, r *http.Request) {
		identity, _ := r.Context().Value(ctxKeyIdentity{}).(*requestIdentity)
		if _, ok := authorize(w, r, verifier, entitlementGroup, identity); !ok {
			return
		}

		if adminClient == nil {
			log.Printf("agent-bff: GET /api/groups called but KEYCLOAK_ADMIN_* is not configured - failing closed")
			writeError(w, http.StatusServiceUnavailable, "group directory is unavailable")
			return
		}

		ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
		defer cancel()
		groups, err := adminClient.RealmGroups(ctx)
		if err != nil {
			log.Printf("agent-bff: keycloak admin realm-groups lookup failed: %v", err)
			writeError(w, http.StatusServiceUnavailable, "group directory is unavailable")
			return
		}

		out := make([]apiRealmGroup, 0, len(groups))
		for _, g := range groups {
			name := strings.TrimPrefix(g.Path, "/")
			if name == "" || strings.HasPrefix(name, "agent_") {
				continue
			}
			out = append(out, apiRealmGroup{Name: name, Path: g.Path})
		}
		sort.Slice(out, func(i, j int) bool { return out[i].Name < out[j].Name })

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(out)
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
