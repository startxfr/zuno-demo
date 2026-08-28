package chat

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/okf"
)

// The composer's slash menu reads config.tasks[].examples in the browser.
// Chat.tsx calls .length on both levels, and a nil Go slice marshals to JSON
// `null` rather than `[]` - the exact mistake that blanked the page for every
// agent on 2026-08-21 (see okf.PrimaryTaskPromptExamples's comment). These
// tests assert the marshalled shape, not just the Go value, because `null` vs
// `[]` is invisible at the Go level and only bites after serialization.
func TestBuildTaskPromptsAlwaysMarshalsToAnArray(t *testing.T) {
	agent := okf.Agent{Tasks: []okf.Task{
		{Name: "no-examples", Title: "No examples"},
	}}

	got := buildTaskPrompts(agent)
	if got == nil {
		t.Fatal("buildTaskPrompts returned nil; a nil slice marshals to JSON null and crashes Chat.tsx's .length check")
	}
	if len(got) != 0 {
		t.Fatalf("a task declaring no prompt_examples must be skipped, got %#v", got)
	}

	encoded, err := json.Marshal(struct {
		Tasks []taskPrompts `json:"tasks"`
	}{Tasks: got})
	if err != nil {
		t.Fatalf("marshalling: %v", err)
	}
	if string(encoded) != `{"tasks":[]}` {
		t.Fatalf("want {\"tasks\":[]}, got %s", encoded)
	}
}

func TestBuildTaskPromptsKeepsOnlyTasksWithExamples(t *testing.T) {
	agent := okf.Agent{Tasks: []okf.Task{
		{Name: "answer-technical-question", Title: "Answer a technical question", PromptExamples: []string{"first", "second"}},
		{Name: "write-code", Title: "Write code"},
		{Name: "find-relevant-docs", Title: "Find relevant documentation", PromptExamples: []string{"third"}},
	}}

	got := buildTaskPrompts(agent)
	if len(got) != 2 {
		t.Fatalf("want the 2 tasks carrying examples, got %d: %#v", len(got), got)
	}
	if got[0].Name != "answer-technical-question" || got[0].Title != "Answer a technical question" {
		t.Errorf("first entry lost its identity: %#v", got[0])
	}
	if len(got[0].Examples) != 2 || got[0].Examples[0] != "first" {
		t.Errorf("examples not carried through: %#v", got[0].Examples)
	}
	if got[1].Name != "find-relevant-docs" {
		t.Errorf("declaration order must be preserved, got %q second", got[1].Name)
	}
}

// A task document with no `title:` would otherwise render a blank menu row,
// which is unusable with a mouse and unreadable with a screen reader.
func TestBuildTaskPromptsFallsBackToTheTaskNameForATitle(t *testing.T) {
	agent := okf.Agent{Tasks: []okf.Task{
		{Name: "untitled-task", PromptExamples: []string{"example"}},
	}}

	got := buildTaskPrompts(agent)
	if len(got) != 1 || got[0].Title != "untitled-task" {
		t.Fatalf("want the name used as the title, got %#v", got)
	}
}

// buildTaskPrompts copies the examples rather than aliasing the parsed bundle,
// so a later mutation of the response cannot reach back into the process-wide
// agent registry that every request shares.
func TestBuildTaskPromptsDoesNotAliasTheParsedBundle(t *testing.T) {
	original := []string{"as authored"}
	agent := okf.Agent{Tasks: []okf.Task{
		{Name: "task", Title: "Task", PromptExamples: original},
	}}

	got := buildTaskPrompts(agent)
	got[0].Examples[0] = "mutated"

	if original[0] != "as authored" {
		t.Fatalf("mutating the response reached the shared okf.Agent: %q", original[0])
	}
}

// Every active agent's real bundle must produce a usable menu. This is the
// check that would have caught the actual state of the repository before this
// change: the whole prompt_examples path existed and not one task used it.
func TestEveryActiveAgentDeclaresPromptExamples(t *testing.T) {
	agents, err := okf.LoadAll("../../../../agents")
	if err != nil {
		t.Skipf("agent bundles not readable from the test working directory: %v", err)
	}

	active := 0
	for _, a := range agents {
		if !a.IsActive() {
			continue
		}
		active++
		tasks := buildTaskPrompts(a)
		if len(tasks) == 0 {
			t.Errorf("agent %q offers no task prompt examples, so its slash menu would be empty", a.Zuno.Name)
			continue
		}
		for _, task := range tasks {
			for _, ex := range task.Examples {
				if strings.TrimSpace(ex) == "" {
					t.Errorf("agent %q task %q declares a blank prompt example", a.Zuno.Name, task.Name)
				}
			}
		}
	}
	if active == 0 {
		t.Fatal("no active agent found; the fixture path is probably wrong")
	}
}
