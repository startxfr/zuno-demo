package telemetry

import (
	"context"
	"strings"
	"testing"
	"time"

	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
	"go.opentelemetry.io/otel/sdk/metric/metricdata"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"
)

// newTestCounter builds a real Int64Counter backed by a ManualReader, so
// RecordRequest's actual Add() call path is exercised end to end without
// Init's network-facing OTLP exporter.
func newTestCounter(t *testing.T) (*sdkmetric.ManualReader, func()) {
	t.Helper()
	reader := sdkmetric.NewManualReader()
	provider := sdkmetric.NewMeterProvider(sdkmetric.WithReader(reader))
	meter := provider.Meter("agent-bff-test")
	counter, err := meter.Int64Counter("zuno.bff.requests")
	if err != nil {
		t.Fatalf("creating test counter: %v", err)
	}
	identity, err := meter.Int64Counter("zuno.bff.requests_by_identity")
	if err != nil {
		t.Fatalf("creating test identity counter: %v", err)
	}
	SetCounterForTest(counter)
	SetIdentityCounterForTest(identity)
	return reader, func() { SetCounterForTest(nil); SetIdentityCounterForTest(nil) }
}

// collect returns, per metric name, the summed points keyed by the
// attributes that metric actually carries.
func collect(t *testing.T, reader *sdkmetric.ManualReader) map[string]map[string]int64 {
	t.Helper()
	var got metricdata.ResourceMetrics
	if err := reader.Collect(context.Background(), &got); err != nil {
		t.Fatalf("collecting metrics: %v", err)
	}
	out := map[string]map[string]int64{}
	for _, sm := range got.ScopeMetrics {
		for _, m := range sm.Metrics {
			sum, ok := m.Data.(metricdata.Sum[int64])
			if !ok {
				continue
			}
			byKey := map[string]int64{}
			for _, dp := range sum.DataPoints {
				agent, _ := dp.Attributes.Value("agent")
				code, _ := dp.Attributes.Value("code")
				user, _ := dp.Attributes.Value("user")
				group, _ := dp.Attributes.Value("group")
				key := agent.AsString() + "/" + code.AsString()
				if user.AsString() != "" || group.AsString() != "" {
					key += "/" + user.AsString() + "/" + group.AsString()
				}
				byKey[key] += dp.Value
			}
			out[m.Name] = byKey
		}
	}
	return out
}

func TestRecordRequestCountsOnePointPerResponse(t *testing.T) {
	// The 2026-09-03 split. This counter used to fan out to one point per
	// Keycloak group, which made zuno_bff_requests_total not a request
	// count: alice, in two groups, counted twice per response. Live that
	// read 6541 against 6180 real responses, and it biased the SLO ratios
	// too - a 5xx from a one-group caller weighed less than one from a
	// twelve-group caller in the same 5xx/total.
	reader, cleanup := newTestCounter(t)
	defer cleanup()
	ctx := context.Background()

	RecordRequest(ctx, "tekos", "200", "alice", []string{"agent_tekos", "sales"})
	RecordRequest(ctx, "tekos", "200", "alice", []string{"agent_tekos", "sales"})
	RecordRequest(ctx, "tekos", "403", "bob", nil)
	RecordRequest(ctx, "arkos", "200", "alice", []string{"agent_arkos"})

	got := collect(t, reader)
	requests := got["zuno.bff.requests"]

	// Four calls, four responses - alice's two groups buy her nothing here.
	want := map[string]int64{"tekos/200": 2, "tekos/403": 1, "arkos/200": 1}
	for k, v := range want {
		if requests[k] != v {
			t.Errorf("zuno.bff.requests[%q] = %d, want %d (all: %v)", k, requests[k], v, requests)
		}
	}
	var total int64
	for _, v := range requests {
		total += v
	}
	if total != 4 {
		t.Errorf("zuno.bff.requests total = %d, want 4 (one per RecordRequest call): %v", total, requests)
	}
	// No identity dimension may leak back onto this metric - that leak is
	// the whole defect, and it is invisible until someone sums the series.
	for k := range requests {
		if strings.Count(k, "/") != 1 {
			t.Errorf("zuno.bff.requests carries identity attributes in key %q; it must be agent/code only", k)
		}
	}
}

func TestIdentityCounterKeepsTheGroupBreakdown(t *testing.T) {
	// ADR-0029's "by user" bullet is preserved, just moved somewhere its
	// fan-out cannot reach a volume or SLO query.
	reader, cleanup := newTestCounter(t)
	defer cleanup()
	ctx := context.Background()

	RecordRequest(ctx, "tekos", "200", "alice", []string{"agent_tekos", "sales"})
	RecordRequest(ctx, "tekos", "200", "alice", []string{"agent_tekos", "sales"})
	RecordRequest(ctx, "tekos", "403", "bob", nil)

	identity := collect(t, reader)["zuno.bff.requests_by_identity"]
	want := map[string]int64{
		"tekos/200/alice/agent_tekos": 2,
		"tekos/200/alice/sales":       2,
		"tekos/403/bob/":              1, // bob had no groups: one point, empty group
	}
	for k, v := range want {
		if identity[k] != v {
			t.Errorf("identity[%q] = %d, want %d (all: %v)", k, identity[k], v, identity)
		}
	}
}

func TestRecordRequestNoopsWithoutInit(t *testing.T) {
	SetCounterForTest(nil)
	// Must not panic when Init was never called (e.g. a handler test that
	// doesn't set up telemetry at all).
	RecordRequest(context.Background(), "tekos", "200", "", nil)
}

// newTestTracer builds a real Tracer backed by an in-memory span recorder, so
// StartBFFRequestSpan/EndBFFRequestSpan's actual attribute-setting path is
// exercised end to end without Init's network-facing OTLP exporter.
func newTestTracer(t *testing.T) (*tracetest.SpanRecorder, func()) {
	t.Helper()
	recorder := tracetest.NewSpanRecorder()
	provider := sdktrace.NewTracerProvider(sdktrace.WithSpanProcessor(recorder))
	SetTracerForTest(provider.Tracer("agent-bff-test"))
	return recorder, func() { SetTracerForTest(nil) }
}

// TestBFFRequestSpanCarriesProjectIdWhenPresent is ADR-0528 (WP-090)
// regression coverage: zuno.project_id was confirmed live against
// production Tempo on 2026-08-29 but had no automated assertion anywhere -
// a refactor of EndBFFRequestSpan's `if projectID != ""` branch would drop
// it silently.
func TestBFFRequestSpanCarriesProjectIdWhenPresent(t *testing.T) {
	recorder, cleanup := newTestTracer(t)
	defer cleanup()

	span := StartBFFRequestSpan(context.Background(), "tekos")
	EndBFFRequestSpan(span, "200", "run-1", "proj-uuid-1", time.Now())

	spans := recorder.Ended()
	if len(spans) != 1 {
		t.Fatalf("got %d ended spans, want 1", len(spans))
	}
	attrs := spans[0].Attributes()
	got := map[string]string{}
	for _, a := range attrs {
		got[string(a.Key)] = a.Value.AsString()
	}
	if got["zuno.project_id"] != "proj-uuid-1" {
		t.Errorf("zuno.project_id = %q, want %q (all: %v)", got["zuno.project_id"], "proj-uuid-1", got)
	}
	if got["zuno.run_id"] != "run-1" {
		t.Errorf("zuno.run_id = %q, want %q (all: %v)", got["zuno.run_id"], "run-1", got)
	}
}

func TestBFFRequestSpanOmitsProjectIdWhenAbsent(t *testing.T) {
	recorder, cleanup := newTestTracer(t)
	defer cleanup()

	span := StartBFFRequestSpan(context.Background(), "tekos")
	EndBFFRequestSpan(span, "200", "run-1", "", time.Now())

	spans := recorder.Ended()
	if len(spans) != 1 {
		t.Fatalf("got %d ended spans, want 1", len(spans))
	}
	for _, a := range spans[0].Attributes() {
		if string(a.Key) == "zuno.project_id" {
			t.Errorf("zuno.project_id present with value %q, want absent", a.Value.AsString())
		}
	}
}
