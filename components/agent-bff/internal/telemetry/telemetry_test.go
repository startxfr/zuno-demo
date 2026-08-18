package telemetry

import (
	"context"
	"testing"

	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
	"go.opentelemetry.io/otel/sdk/metric/metricdata"
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
