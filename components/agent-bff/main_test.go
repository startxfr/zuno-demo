// Covers metricsMiddleware and statusRecorder (ADR-0102/roadmap ADR-0111):
// the status code actually recorded per response, and that wrapping the
// ResponseWriter doesn't break proxySSE's flush-per-chunk streaming, since
// that regression would be silent (no test failure, just buffered SSE in
// production).
package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

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
