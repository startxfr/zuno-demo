// Package telemetry sends OTLP metrics to the shared OTel Collector
// (`zuno-otel-collector-collector.zuno-monitoring.svc`), same pattern as
// components/agent-runtime/app/telemetry.py and
// components/mcp-gateway/app/telemetry.py (ADR-0029) - duplicated
// per-service rather than shared, since each service is an independently
// built/deployed image. This is the BFF's own billable/notable operation:
// one HTTP response to the frontend, recorded by agent and status code so
// docs/platform/slo.md's zuno_bff_requests_total query (ADR-0102) has real
// data - OTel's Prometheus naming translates the dotted "zuno.bff.requests"
// counter name into that exact metric name.
package telemetry

import (
	"context"
	"fmt"
	"os"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlpmetric/otlpmetrichttp"
	"go.opentelemetry.io/otel/metric"
	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
	"go.opentelemetry.io/otel/sdk/resource"
)

const defaultOTELEndpoint = "http://zuno-otel-collector-collector.zuno-monitoring.svc:4318"

var requestCounter metric.Int64Counter

// Init sets up the OTLP metrics pipeline and registers the request
// counter. Returns a shutdown func the caller should invoke on exit to
// flush any buffered metrics (best-effort - a missed final flush loses at
// most one export interval's worth of counts, never previously-exported
// data).
func Init(ctx context.Context, serviceName string) (func(context.Context) error, error) {
	endpoint := os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
	if endpoint == "" {
		endpoint = defaultOTELEndpoint
	}

	exporter, err := otlpmetrichttp.New(ctx, otlpmetrichttp.WithEndpointURL(endpoint+"/v1/metrics"))
	if err != nil {
		return nil, fmt.Errorf("telemetry: creating OTLP metric exporter: %w", err)
	}

	res, err := resource.New(ctx, resource.WithAttributes(
		attribute.String("service.name", serviceName),
	))
	if err != nil {
		return nil, fmt.Errorf("telemetry: building resource: %w", err)
	}

	provider := sdkmetric.NewMeterProvider(
		sdkmetric.WithResource(res),
		sdkmetric.WithReader(sdkmetric.NewPeriodicReader(exporter)),
	)

	meter := provider.Meter(serviceName)
	requestCounter, err = meter.Int64Counter(
		"zuno.bff.requests",
		metric.WithDescription("agent-bff HTTP responses by agent and status code"),
	)
	if err != nil {
		return nil, fmt.Errorf("telemetry: creating request counter: %w", err)
	}

	return provider.Shutdown, nil
}

// RecordRequest increments the request counter for one completed HTTP
// response. A nil counter (Init not called, e.g. in tests that exercise
// handlers directly) is a silent no-op rather than a panic.
func RecordRequest(ctx context.Context, agent, code string) {
	if requestCounter == nil {
		return
	}
	requestCounter.Add(ctx, 1, metric.WithAttributes(
		attribute.String("agent", agent),
		attribute.String("code", code),
	))
}

// SetCounterForTest points requestCounter at a counter backed by a
// manual reader, so telemetry_test.go can assert on recorded values
// without going through Init's real OTLP exporter/network setup.
func SetCounterForTest(c metric.Int64Counter) { requestCounter = c }
