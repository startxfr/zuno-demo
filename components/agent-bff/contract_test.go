// ADR-0054's mandatory operational consideration: "contract tests between
// frontend, BFF and Runtime adapters". This is the BFF-side half: it
// parses openapi.json (this component's zero-dependency reason it's JSON,
// not YAML - see that file's own description) with the standard library
// alone and asserts the wire structs in main.go serialize to exactly the
// same field names openapi.json declares, so a change to one without the
// other fails `go test` instead of silently drifting (the exact failure
// mode ADR-0054's Context names: "This has already allowed identity and
// streaming expectations to diverge between components").
package main

import (
	"encoding/json"
	"os"
	"reflect"
	"sort"
	"testing"

	"github.com/startxfr/zuno-demo/components/agent-bff/internal/runtime"
)

type openapiSchema struct {
	Required   []string                   `json:"required"`
	Properties map[string]json.RawMessage `json:"properties"`
}

type openapiDoc struct {
	Paths      map[string]json.RawMessage `json:"paths"`
	Components struct {
		Schemas map[string]openapiSchema `json:"schemas"`
	} `json:"components"`
}

func loadOpenAPISpec(t *testing.T) openapiDoc {
	t.Helper()
	data, err := os.ReadFile("openapi.json")
	if err != nil {
		t.Fatalf("reading openapi.json: %v", err)
	}
	var doc openapiDoc
	if err := json.Unmarshal(data, &doc); err != nil {
		t.Fatalf("parsing openapi.json: %v", err)
	}
	return doc
}

// jsonFieldNames returns the sorted set of JSON field names a Go value
// serializes to, read from its `json:"..."` struct tags rather than an
// actual Marshal round-trip, so it works the same for zero-valued structs.
func jsonFieldNames(v any) []string {
	rt := reflect.TypeOf(v)
	var names []string
	for i := 0; i < rt.NumField(); i++ {
		tag := rt.Field(i).Tag.Get("json")
		if tag == "" || tag == "-" {
			continue
		}
		name := tag
		for i, c := range tag {
			if c == ',' {
				name = tag[:i]
				break
			}
		}
		names = append(names, name)
	}
	sort.Strings(names)
	return names
}

func schemaPropertyNames(t *testing.T, doc openapiDoc, schemaName string) []string {
	t.Helper()
	schema, ok := doc.Components.Schemas[schemaName]
	if !ok {
		t.Fatalf("openapi.json has no components.schemas.%s", schemaName)
	}
	names := make([]string, 0, len(schema.Properties))
	for name := range schema.Properties {
		names = append(names, name)
	}
	sort.Strings(names)
	return names
}

func assertMatchesSchema(t *testing.T, doc openapiDoc, goValue any, schemaName string) {
	t.Helper()
	got := jsonFieldNames(goValue)
	want := schemaPropertyNames(t, doc, schemaName)
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("%T's JSON fields %v do not match openapi.json's %s properties %v - update whichever one is stale", goValue, got, schemaName, want)
	}
}

func TestOpenAPISpecIsWellFormed(t *testing.T) {
	doc := loadOpenAPISpec(t)
	paths := []string{
		"/healthz",
		"/api/chat",
		"/api/conversations",
		"/api/conversations/{run_id}/transcript",
		"/api/conversations/{run_id}",
		"/api/conversations/{run_id}/star",
		"/api/conversations/reorder",
		"/api/conversations/{run_id}/hard-delete",
		"/api/conversations/{run_id}/members",
		"/api/conversations/{run_id}/members/{subject}",
		"/api/conversations/{run_id}/owner",
		"/api/conversations/{run_id}/clone",
		"/api/colleagues",
	}
	for _, path := range paths {
		if _, ok := doc.Paths[path]; !ok {
			t.Errorf("openapi.json is missing path %q, which main.go registers", path)
		}
	}
}

func TestChatRequestMatchesOpenAPISpec(t *testing.T) {
	assertMatchesSchema(t, loadOpenAPISpec(t), apiChatRequest{}, "ChatRequest")
}

func TestChatResponseMatchesOpenAPISpec(t *testing.T) {
	assertMatchesSchema(t, loadOpenAPISpec(t), apiChatResponse{}, "ChatResponse")
}

func TestErrorResponseMatchesOpenAPISpec(t *testing.T) {
	assertMatchesSchema(t, loadOpenAPISpec(t), apiErrorResponse{}, "ErrorResponse")
}

func TestCitationMatchesOpenAPISpec(t *testing.T) {
	assertMatchesSchema(t, loadOpenAPISpec(t), runtime.Citation{}, "Citation")
}

// ADR-0212 wire structs.

func TestConversationMatchesOpenAPISpec(t *testing.T) {
	assertMatchesSchema(t, loadOpenAPISpec(t), apiConversation{}, "Conversation")
}

func TestTranscriptTurnMatchesOpenAPISpec(t *testing.T) {
	assertMatchesSchema(t, loadOpenAPISpec(t), apiTranscriptTurn{}, "TranscriptTurn")
}

func TestRenameRequestMatchesOpenAPISpec(t *testing.T) {
	assertMatchesSchema(t, loadOpenAPISpec(t), apiRenameRequest{}, "RenameRequest")
}

func TestRenameResponseMatchesOpenAPISpec(t *testing.T) {
	assertMatchesSchema(t, loadOpenAPISpec(t), apiRenameResponse{}, "RenameResponse")
}

func TestStarResponseMatchesOpenAPISpec(t *testing.T) {
	assertMatchesSchema(t, loadOpenAPISpec(t), apiStarResponse{}, "StarResponse")
}

func TestArchiveResponseMatchesOpenAPISpec(t *testing.T) {
	assertMatchesSchema(t, loadOpenAPISpec(t), apiArchiveResponse{}, "ArchiveResponse")
}

// ADR-0515 wire structs.

func TestReorderRequestMatchesOpenAPISpec(t *testing.T) {
	assertMatchesSchema(t, loadOpenAPISpec(t), apiReorderRequest{}, "ReorderRequest")
}

func TestReorderResponseMatchesOpenAPISpec(t *testing.T) {
	assertMatchesSchema(t, loadOpenAPISpec(t), apiReorderResponse{}, "ReorderResponse")
}

func TestHardDeleteResponseMatchesOpenAPISpec(t *testing.T) {
	assertMatchesSchema(t, loadOpenAPISpec(t), apiHardDeleteResponse{}, "HardDeleteResponse")
}

// ADR-0213 wire structs.

func TestMemberMatchesOpenAPISpec(t *testing.T) {
	assertMatchesSchema(t, loadOpenAPISpec(t), apiMember{}, "Member")
}

func TestGrantMembershipRequestMatchesOpenAPISpec(t *testing.T) {
	assertMatchesSchema(t, loadOpenAPISpec(t), apiGrantMembershipRequest{}, "GrantMembershipRequest")
}

func TestGrantMembershipResponseMatchesOpenAPISpec(t *testing.T) {
	assertMatchesSchema(t, loadOpenAPISpec(t), apiGrantMembershipResponse{}, "GrantMembershipResponse")
}

func TestRevokeMembershipResponseMatchesOpenAPISpec(t *testing.T) {
	assertMatchesSchema(t, loadOpenAPISpec(t), apiRevokeMembershipResponse{}, "RevokeMembershipResponse")
}

func TestTransferOwnershipRequestMatchesOpenAPISpec(t *testing.T) {
	assertMatchesSchema(t, loadOpenAPISpec(t), apiTransferOwnershipRequest{}, "TransferOwnershipRequest")
}

func TestTransferOwnershipResponseMatchesOpenAPISpec(t *testing.T) {
	assertMatchesSchema(t, loadOpenAPISpec(t), apiTransferOwnershipResponse{}, "TransferOwnershipResponse")
}

func TestCloneConversationResponseMatchesOpenAPISpec(t *testing.T) {
	assertMatchesSchema(t, loadOpenAPISpec(t), apiCloneConversationResponse{}, "CloneConversationResponse")
}

func TestColleagueMatchesOpenAPISpec(t *testing.T) {
	assertMatchesSchema(t, loadOpenAPISpec(t), apiColleague{}, "Colleague")
}
