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
	"time"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlpmetric/otlpmetrichttp"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/metric"
	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/trace"
)

const defaultOTELEndpoint = "http://zuno-otel-collector-collector.zuno-monitoring.svc:4318"

var (
	requestCounter    metric.Int64Counter
	identityCounter   metric.Int64Counter
	durationHistogram metric.Float64Histogram
	tracer            trace.Tracer
)

// Init sets up the OTLP metrics AND trace pipelines and registers the
// request counter/duration histogram/tracer. Returns a shutdown func the
// caller should invoke on exit to flush any buffered metrics/spans
// (best-effort - a missed final flush loses at most one export interval's
// worth of data, never previously-exported data).
//
// ADR-0543: agent-bff previously had metrics only (no OTel tracer at all) -
// added here so its `bff_request` span can join the per-run resource
// dashboard alongside every other service's spans (agent-runtime,
// mcp-gateway, rag-service, ai-gateway all already had a tracer).
func Init(ctx context.Context, serviceName string) (func(context.Context) error, error) {
	endpoint := os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
	if endpoint == "" {
		endpoint = defaultOTELEndpoint
	}

	metricExporter, err := otlpmetrichttp.New(ctx, otlpmetrichttp.WithEndpointURL(endpoint+"/v1/metrics"))
	if err != nil {
		return nil, fmt.Errorf("telemetry: creating OTLP metric exporter: %w", err)
	}

	res, err := resource.New(ctx, resource.WithAttributes(
		attribute.String("service.name", serviceName),
	))
	if err != nil {
		return nil, fmt.Errorf("telemetry: building resource: %w", err)
	}

	meterProvider := sdkmetric.NewMeterProvider(
		sdkmetric.WithResource(res),
		sdkmetric.WithReader(sdkmetric.NewPeriodicReader(metricExporter)),
	)

	meter := meterProvider.Meter(serviceName)
	requestCounter, err = meter.Int64Counter(
		"zuno.bff.requests",
		metric.WithDescription("agent-bff HTTP responses by agent and status code - exactly one point per response"),
	)
	if err != nil {
		return nil, fmt.Errorf("telemetry: creating request counter: %w", err)
	}
	// Identity breakdown, split off from zuno.bff.requests on 2026-09-03.
	// Fans out to one point PER KEYCLOAK GROUP, so it counts group-request
	// pairs, not requests - the name says so, and its description says so,
	// because that is the whole reason it is a separate series. Never a
	// source of volume, rate or SLO.
	identityCounter, err = meter.Int64Counter(
		"zuno.bff.requests_by_identity",
		metric.WithDescription("agent-bff responses fanned out per Keycloak group - group-request pairs, NOT a request count; use zuno.bff.requests for volume and SLO"),
	)
	if err != nil {
		return nil, fmt.Errorf("telemetry: creating identity counter: %w", err)
	}
	durationHistogram, err = meter.Float64Histogram(
		"zuno.bff.request_duration_ms",
		metric.WithDescription("agent-bff HTTP response latency by agent and status code"),
		metric.WithUnit("ms"),
	)
	if err != nil {
		return nil, fmt.Errorf("telemetry: creating request duration histogram: %w", err)
	}

	traceExporter, err := otlptracehttp.New(ctx, otlptracehttp.WithEndpointURL(endpoint+"/v1/traces"))
	if err != nil {
		return nil, fmt.Errorf("telemetry: creating OTLP trace exporter: %w", err)
	}
	tracerProvider := sdktrace.NewTracerProvider(
		sdktrace.WithResource(res),
		sdktrace.WithBatcher(traceExporter),
	)
	tracer = tracerProvider.Tracer(serviceName)

	return func(shutdownCtx context.Context) error {
		metricErr := meterProvider.Shutdown(shutdownCtx)
		traceErr := tracerProvider.Shutdown(shutdownCtx)
		if metricErr != nil {
			return metricErr
		}
		return traceErr
	}, nil
}

// RecordRequest increments the request counter for one completed HTTP
// response. A nil counter (Init not called, e.g. in tests that exercise
// handlers directly) is a silent no-op rather than a panic.
//
// zuno.bff.requests gets EXACTLY ONE POINT per response, labeled by agent
// and code. The identity breakdown (ADR-0029's "by user" bullet) goes to
// zuno.bff.requests_by_identity instead.
//
// Until 2026-09-03 both lived on one counter, which fanned out to one
// point per Keycloak group. That made zuno_bff_requests_total not a
// request count: a caller in twelve groups counted twelve times, while a
// request that never reached a verified token (/healthz, a bad bearer)
// counted once. Live, the fleet read 6541 against 6180 real responses.
//
// The damage was not confined to volume panels. docs/platform/slo.md's
// availability rules are 5xx/total ratios, and a ratio only survives a
// UNIFORM fan-out. This one scaled with the caller's group count, so an
// error from a one-group caller and an error from a twelve-group caller
// carried different weight in the same ratio - the SLO measured an error
// rate weighted by group membership rather than by request. Nothing else
// changes: the two metrics keep the same agent/code labels, so every
// existing dashboard and rule reads the corrected series with no edit.
//
// user/groups are empty for requests that never reached a
// successfully-verified token - see main.go's metricsMiddleware/
// chatHandler for how they're threaded through.
func RecordRequest(ctx context.Context, agent, code, user string, groups []string) {
	if requestCounter == nil {
		return
	}
	requestCounter.Add(ctx, 1, metric.WithAttributes(
		attribute.String("agent", agent),
		attribute.String("code", code),
	))

	if identityCounter == nil {
		return
	}
	// A Keycloak group membership is a list and metric labels are scalar,
	// so this one deliberately fans out. It is a separate metric precisely
	// so that fan-out can never reach a volume or SLO query again.
	groupList := groups
	if len(groupList) == 0 {
		groupList = []string{""}
	}
	for _, group := range groupList {
		identityCounter.Add(ctx, 1, metric.WithAttributes(
			attribute.String("agent", agent),
			attribute.String("code", code),
			attribute.String("user", user),
			attribute.String("group", group),
		))
	}
}

// RecordDuration records one completed HTTP response's latency, labeled by
// agent and status code - the aggregate-SLO counterpart to RecordRequest,
// added because agent-bff previously had no latency dimension at all (only
// a count). Unlike RecordRequest, not broken out by user/group - this is
// for other/future dashboards' aggregate latency panels, not per-run
// correlation (see StartBFFRequestSpan/EndBFFRequestSpan below for that).
func RecordDuration(ctx context.Context, agent, code string, durationMs float64) {
	if durationHistogram == nil {
		return
	}
	durationHistogram.Record(ctx, durationMs, metric.WithAttributes(
		attribute.String("agent", agent),
		attribute.String("code", code),
	))
}

// StartBFFRequestSpan opens a `bff_request` span for one HTTP request. A
// nil tracer (Init not called, or its trace exporter failed) yields a nil
// span - EndBFFRequestSpan is a no-op on nil, same "additive observability,
// never a hard dependency" posture as the metrics above.
func StartBFFRequestSpan(ctx context.Context, agent string) trace.Span {
	if tracer == nil {
		return nil
	}
	_, span := tracer.Start(ctx, "bff_request")
	if agent != "" {
		span.SetAttributes(attribute.String("zuno.agent", agent))
	}
	return span
}

// EndBFFRequestSpan closes a span opened by StartBFFRequestSpan, tagging
// it with the final status code and (ADR-0543) run_id once known - runID
// is empty for a request that never resolved one (e.g. a rejected/failed
// chat call, or a non-chat conversation-management endpoint), in which
// case the span is still recorded, just not joinable to a specific run in
// the per-run resource dashboard.
// ADR-0528 adds projectID on the same terms: the engagement dimension, empty
// outside a project, and a SPAN attribute only - never a label on
// requestCounter above, because projects are created ad hoc at runtime and
// their cardinality is unbounded. Never the Salesforce opportunity id.
func EndBFFRequestSpan(span trace.Span, code, runID, projectID string, start time.Time) {
	if span == nil {
		return
	}
	span.SetAttributes(
		attribute.String("zuno.code", code),
		attribute.Float64("zuno.latency_ms", float64(time.Since(start).Microseconds())/1000.0),
	)
	if runID != "" {
		span.SetAttributes(attribute.String("zuno.run_id", runID))
	}
	if projectID != "" {
		span.SetAttributes(attribute.String("zuno.project_id", projectID))
	}
	span.End()
}

// SetCounterForTest points requestCounter at a counter backed by a
// manual reader, so telemetry_test.go can assert on recorded values
// without going through Init's real OTLP exporter/network setup.
func SetCounterForTest(c metric.Int64Counter) { requestCounter = c }

// SetIdentityCounterForTest is the same hook for the identity breakdown,
// so a test can assert that the fan-out lands there and NOT on the request
// counter - which is the entire point of the 2026-09-03 split.
func SetIdentityCounterForTest(c metric.Int64Counter) { identityCounter = c }

// SetTracerForTest points tracer at one backed by a test span recorder, so
// telemetry_test.go can assert on `bff_request`'s exported attributes
// (ADR-0528's zuno.project_id among them) without Init's real OTLP trace
// exporter/network setup.
func SetTracerForTest(tr trace.Tracer) { tracer = tr }
