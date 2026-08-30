package telemetry

import (
	"context"
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
	counter, err := provider.Meter("agent-bff-test").Int64Counter("zuno.bff.requests")
	if err != nil {
		t.Fatalf("creating test counter: %v", err)
	}
	SetCounterForTest(counter)
	return reader, func() { SetCounterForTest(nil) }
}

func TestRecordRequestIncrementsByAgentAndCode(t *testing.T) {
	reader, cleanup := newTestCounter(t)
	defer cleanup()
	ctx := context.Background()

	RecordRequest(ctx, "tekos", "200", "alice", []string{"agent_tekos", "sales"})
	RecordRequest(ctx, "tekos", "200", "alice", []string{"agent_tekos", "sales"})
	RecordRequest(ctx, "tekos", "403", "bob", nil)
	RecordRequest(ctx, "arkos", "200", "alice", []string{"agent_arkos"})

	var got metricdata.ResourceMetrics
	if err := reader.Collect(ctx, &got); err != nil {
		t.Fatalf("collecting metrics: %v", err)
	}

	counts := map[string]int64{}
	for _, sm := range got.ScopeMetrics {
		for _, m := range sm.Metrics {
			sum, ok := m.Data.(metricdata.Sum[int64])
			if !ok {
				continue
			}
			for _, dp := range sum.DataPoints {
				agent, _ := dp.Attributes.Value("agent")
				code, _ := dp.Attributes.Value("code")
				user, _ := dp.Attributes.Value("user")
				group, _ := dp.Attributes.Value("group")
				key := agent.AsString() + "/" + code.AsString() + "/" + user.AsString() + "/" + group.AsString()
				counts[key] = dp.Value
			}
		}
	}

	// One point per (agent, code, user, group) - a multi-group user
	// (alice) is intentionally double-counted across her two groups.
	want := map[string]int64{
		"tekos/200/alice/agent_tekos": 2,
		"tekos/200/alice/sales":       2,
		"tekos/403/bob/":              1,
		"arkos/200/alice/agent_arkos": 1,
	}
	for k, v := range want {
		if counts[k] != v {
			t.Errorf("counts[%q] = %d, want %d (all: %v)", k, counts[k], v, counts)
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
