// Covers metricsMiddleware and statusRecorder (ADR-0102/roadmap ADR-0111):
// the status code actually recorded per response, and that wrapping the
// ResponseWriter doesn't break proxySSE's flush-per-chunk streaming, since
// that regression would be silent (no test failure, just buffered SSE in
// production).
package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/startxfr/zuno-demo/components/agent-bff/internal/runtime"
	"github.com/startxfr/zuno-demo/components/agent-bff/internal/telemetry"
	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
	"go.opentelemetry.io/otel/sdk/metric/metricdata"
)

func withTestCounter(t *testing.T) *sdkmetric.ManualReader {
	t.Helper()
	reader := sdkmetric.NewManualReader()
	provider := sdkmetric.NewMeterProvider(sdkmetric.WithReader(reader))
	counter, err := provider.Meter("agent-bff-test").Int64Counter("zuno.bff.requests")
	if err != nil {
		t.Fatalf("creating test counter: %v", err)
	}
	telemetry.SetCounterForTest(counter)
	t.Cleanup(func() { telemetry.SetCounterForTest(nil) })
	return reader
}

func recordedCode(t *testing.T, rm metricdata.ResourceMetrics, agent string) (string, bool) {
	t.Helper()
	for _, sm := range rm.ScopeMetrics {
		for _, m := range sm.Metrics {
			sum, ok := m.Data.(metricdata.Sum[int64])
			if !ok {
				continue
			}
			for _, dp := range sum.DataPoints {
				a, _ := dp.Attributes.Value("agent")
				if a.AsString() != agent {
					continue
				}
				code, _ := dp.Attributes.Value("code")
				return code.AsString(), true
			}
		}
	}
	return "", false
}

func TestMetricsMiddlewareRecordsExplicitStatus(t *testing.T) {
	reader := withTestCounter(t)
	handler := metricsMiddleware("tekos", http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusForbidden)
	}))

	handler.ServeHTTP(httptest.NewRecorder(), httptest.NewRequest(http.MethodGet, "/api/chat", nil))

	var rm metricdata.ResourceMetrics
	if err := reader.Collect(context.Background(), &rm); err != nil {
		t.Fatalf("collect: %v", err)
	}
	code, ok := recordedCode(t, rm, "tekos")
	if !ok || code != "403" {
		t.Errorf("recorded code = %q, ok=%v, want 403", code, ok)
	}
}

func TestMetricsMiddlewareDefaultsToOKWithoutExplicitWriteHeader(t *testing.T) {
	reader := withTestCounter(t)
	handler := metricsMiddleware("arkos", http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte("ok")) // never calls WriteHeader - implicit 200
	}))

	handler.ServeHTTP(httptest.NewRecorder(), httptest.NewRequest(http.MethodGet, "/healthz", nil))

	var rm metricdata.ResourceMetrics
	if err := reader.Collect(context.Background(), &rm); err != nil {
		t.Fatalf("collect: %v", err)
	}
	code, ok := recordedCode(t, rm, "arkos")
	if !ok || code != "200" {
		t.Errorf("recorded code = %q, ok=%v, want 200", code, ok)
	}
}

// fakeFlushWriter proves statusRecorder.Flush() delegates to an
// underlying http.Flusher - the exact capability proxySSE type-asserts
// for on every streamed chunk.
type fakeFlushWriter struct {
	http.ResponseWriter
	flushed int
}

func (f *fakeFlushWriter) Flush() { f.flushed++ }

func TestStatusRecorderDelegatesFlush(t *testing.T) {
	underlying := &fakeFlushWriter{ResponseWriter: httptest.NewRecorder()}
	rec := &statusRecorder{ResponseWriter: underlying, status: http.StatusOK}

	var _ http.Flusher = rec // compile-time proof proxySSE's type assertion succeeds
	rec.Flush()
	if underlying.flushed != 1 {
		t.Errorf("underlying.flushed = %d, want 1", underlying.flushed)
	}
}

// ADR-0527/WP-088: agent-runtime's request models type the optional project
// fields as `Optional[str] = Field(default=None, min_length=1)` and
// `Literal["C1","C2","C3"] = "C2"`. Go's zero value marshals as "", which
// Pydantic reads as PRESENT-and-invalid rather than absent, so a request
// carrying an empty classification or an empty group_name is rejected 422.
//
// Live-verified 2026-08-28 against the running cluster: every grant naming a
// user (and therefore leaving group_name empty) failed, so POST /api/projects
// could not create anything at all. The contract tests did not catch it -
// they compare field NAMES against the OpenAPI spec, and omitempty is not a
// field name. This test covers the serialized bytes instead.
func TestCreateProjectRequest_OmitsEmptyOptionalFields(t *testing.T) {
	body, err := json.Marshal(runtime.CreateProjectRequest{
		Title:   "a project",
		Context: "some context",
		// Classification and SalesforceOpportunityID deliberately unset -
		// the frontend does not always send them.
		Grants: []runtime.ProjectGrant{{Subject: "some-sub", Role: "admin"}},
	})
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var decoded map[string]any
	if err := json.Unmarshal(body, &decoded); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	for _, key := range []string{"classification", "salesforce_opportunity_id"} {
		if _, present := decoded[key]; present {
			t.Errorf("%q must be omitted when empty, not sent as \"\" - agent-runtime rejects the empty string: %s", key, body)
		}
	}

	grants, _ := decoded["grants"].([]any)
	if len(grants) != 1 {
		t.Fatalf("expected 1 grant, got %d", len(grants))
	}
	grant, _ := grants[0].(map[string]any)
	if _, present := grant["group_name"]; present {
		t.Errorf("group_name must be omitted for a subject-scoped grant: %s", body)
	}
	if got := grant["subject"]; got != "some-sub" {
		t.Errorf("subject must survive omitempty when set, got %v", got)
	}
	if got := grant["role"]; got != "admin" {
		t.Errorf("role is required and must always be sent, got %v", got)
	}
}

// The mirror case: a group-scoped grant must omit `subject`, not send "".
func TestProjectGrant_GroupScopedOmitsSubject(t *testing.T) {
	body, _ := json.Marshal(runtime.ProjectGrant{GroupName: "consultant", Role: "read"})
	var decoded map[string]any
	if err := json.Unmarshal(body, &decoded); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if _, present := decoded["subject"]; present {
		t.Errorf("subject must be omitted for a group-scoped grant: %s", body)
	}
	if got := decoded["group_name"]; got != "consultant" {
		t.Errorf("group_name must survive omitempty when set, got %v", got)
	}
}

// ADR-0213's colleague-eligibility rule, made testable by extraction. The
// fourth case is the one that fails on the pre-2026-08-28 inline version: it
// used `else if` over ANY shared group, so a second agent_* entitlement in
// common counted as a shared "business role". ADR-0040 says an entitlement
// group is not a business role, and ADR-0527 clause 2 refuses agent_* as a
// grant target outright - measured on the live realm, that false positive made
// sale-02 and recrut-01 eligible to each other on Soursage with nothing else
// in common.
func TestColleagueIsEligible(t *testing.T) {
	callerGroups := func(names ...string) map[string]struct{} {
		m := make(map[string]struct{}, len(names))
		for _, n := range names {
			m[n] = struct{}{}
		}
		return m
	}

	cases := []struct {
		name       string
		candidate  []string
		caller     map[string]struct{}
		entitle    string
		wantEligib bool
	}{
		{
			name:       "entitlement and a shared business role",
			candidate:  []string{"agent_tekos", "consultant"},
			caller:     callerGroups("agent_tekos", "consultant"),
			entitle:    "agent_tekos",
			wantEligib: true,
		},
		{
			name:       "entitlement but no shared business role",
			candidate:  []string{"agent_tekos", "sales"},
			caller:     callerGroups("agent_tekos", "consultant"),
			entitle:    "agent_tekos",
			wantEligib: false,
		},
		{
			name:       "shared business role but not entitled to this agent",
			candidate:  []string{"agent_arkos", "consultant"},
			caller:     callerGroups("agent_tekos", "consultant"),
			entitle:    "agent_tekos",
			wantEligib: false,
		},
		{
			name:       "a second shared agent_* group is not a business role",
			candidate:  []string{"agent_tekos", "agent_comage"},
			caller:     callerGroups("agent_tekos", "agent_comage", "consultant"),
			entitle:    "agent_tekos",
			wantEligib: false,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := colleagueIsEligible(tc.candidate, tc.caller, tc.entitle); got != tc.wantEligib {
				t.Errorf("colleagueIsEligible(%v) = %v, want %v", tc.candidate, got, tc.wantEligib)
			}
		})
	}
}
