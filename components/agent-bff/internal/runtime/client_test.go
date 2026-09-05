package runtime

import (
	"encoding/json"
	"testing"
)

// TestChatResponseUnmarshalsRoutingMetadata is a regression test for the
// exact ADR-0215 trap ChatResponse's own doc comment warns about:
// encoding/json silently drops any JSON field with no matching Go struct
// field, so ADR-0550's new "routing" field needed an explicit
// RoutingMetadata type/tag here to ever reach main.go's apiChatResponse,
// not just an OpenAPI schema annotation (see contract_test.go for that
// separate check).
func TestChatResponseUnmarshalsRoutingMetadata(t *testing.T) {
	raw := `{
		"reply": "hi", "citations": [], "images": [], "run_id": "r1", "source_mode": "indexed",
		"project_id": "proj-1",
		"routing": {
			"agent": "arkos", "task": "draft-architecture-testimonial", "project_id": "proj-1",
			"project_classification": "C2", "effective_classification": "C2",
			"selected_model": "gpt-oss-20b", "selected_provider": "local-gpt-oss",
			"execution_location": "local", "fallback_used": false, "fallback_from": null,
			"local_only_required": true, "routing_reason": "This request at classification C2 is routed to a local model."
		}
	}`

	var resp ChatResponse
	if err := json.Unmarshal([]byte(raw), &resp); err != nil {
		t.Fatalf("unmarshal failed: %v", err)
	}

	if resp.Routing.Agent != "arkos" || resp.Routing.Task != "draft-architecture-testimonial" {
		t.Fatalf("routing.agent/task not decoded: %+v", resp.Routing)
	}
	if resp.Routing.SelectedProvider != "local-gpt-oss" || resp.Routing.SelectedModel != "gpt-oss-20b" {
		t.Fatalf("routing.selected_provider/selected_model not decoded: %+v", resp.Routing)
	}
	if resp.Routing.ExecutionLocation != "local" {
		t.Fatalf("routing.execution_location not decoded: %+v", resp.Routing)
	}
	if !resp.Routing.LocalOnlyRequired {
		t.Fatalf("routing.local_only_required not decoded: %+v", resp.Routing)
	}
	if resp.Routing.FallbackFrom != "" {
		t.Fatalf("expected empty fallback_from for a JSON null, got %q", resp.Routing.FallbackFrom)
	}
}

// TestChatResponseRoutingDefaultsToZeroValueWhenAbsent guards the other
// direction: an older agent-runtime response with no "routing" key at all
// must not fail to decode - it should simply leave RoutingMetadata at its
// Go zero value, not panic or error.
func TestChatResponseRoutingDefaultsToZeroValueWhenAbsent(t *testing.T) {
	raw := `{"reply": "hi", "citations": [], "images": [], "run_id": "r1", "source_mode": "indexed", "project_id": ""}`

	var resp ChatResponse
	if err := json.Unmarshal([]byte(raw), &resp); err != nil {
		t.Fatalf("unmarshal failed: %v", err)
	}
	if resp.Routing != (RoutingMetadata{}) {
		t.Fatalf("expected zero-value RoutingMetadata when absent, got %+v", resp.Routing)
	}
}
