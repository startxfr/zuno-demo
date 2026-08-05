// Package okf loads and represents agent.okf.md OKF v0.2 Markdown bundles
// (ADR-0038, superseding the earlier Kubernetes-style agent.okf.yaml) so the
// portal can render one tile per agent from the same declarative source of
// truth the Agent Runtime (ADR-0039) and MCP Gateway policy engine
// (ADR-0036) consume. See platform/okf/schema/zuno-okf-v0.2.schema.json and
// zuno-okf-task-v0.2.schema.json for the authoritative schemas this struct
// set mirrors.
package okf

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"gopkg.in/yaml.v3"
)

// Agent is the parsed frontmatter of an agents/<name>/agent.okf.md bundle,
// plus its resolved tasks (each a separate linked Markdown document under
// tasks/<task>.md).
type Agent struct {
	OkfVersion  string `yaml:"okf_version"`
	Type        string `yaml:"type"`
	Title       string `yaml:"title"`
	Description string `yaml:"description"`
	Zuno        Zuno   `yaml:"zuno"`

	// Tasks is resolved by LoadAll from Zuno.TaskNames, not part of the
	// index frontmatter itself.
	Tasks []Task `yaml:"-"`
}

// Zuno mirrors the frontmatter's `zuno` extension object (ADR-0006).
type Zuno struct {
	Name      string   `yaml:"name"`
	Status    string   `yaml:"status"` // "active" | "placeholder"
	TaskNames []string `yaml:"tasks"`
	Model     Model    `yaml:"model"`
	Access    Access   `yaml:"access"`
	UI        UI       `yaml:"ui"`
}

// Task is a resolved agents/<name>/tasks/<task>.md bundle.
type Task struct {
	Name         string
	Title        string
	AllowedTools []string
}

// taskFrontmatter mirrors zuno-okf-task-v0.2.schema.json.
type taskFrontmatter struct {
	OkfVersion string `yaml:"okf_version"`
	Type       string `yaml:"type"`
	Title      string `yaml:"title"`
	Zuno       struct {
		AllowedTools []string `yaml:"allowed_tools"`
	} `yaml:"zuno"`
}

// Model is zuno.model.
type Model struct {
	PreferredClassification string `yaml:"preferred_classification"`
	Notes                   string `yaml:"notes"`
}

// Access is zuno.access.
type Access struct {
	Groups []string `yaml:"groups"`
}

// UI is zuno.ui, consumed directly by the portal tile template.
type UI struct {
	DisplayName     string `yaml:"displayName"`
	TileDescription string `yaml:"tileDescription"`
	Color           string `yaml:"color"`
	Icon            string `yaml:"icon"`
}

// IsActive reports whether this agent has a real, deployed FE/BFF (ADR-0007).
func (a Agent) IsActive() bool {
	return a.Zuno.Status == "active"
}

// AllowsAnyGroup reports whether any of the caller's JWT groups intersects
// this agent's zuno.access.groups (ADR-0040: the agent_<name> entitlement
// group, not a business role). Groups are compared without a leading "/" so
// callers can pass either the Keycloak "groups" claim's raw entries (e.g.
// "/agent_tekos") or bare names.
func (a Agent) AllowsAnyGroup(callerGroups []string) bool {
	allowed := make(map[string]struct{}, len(a.Zuno.Access.Groups))
	for _, g := range a.Zuno.Access.Groups {
		allowed[normalizeGroup(g)] = struct{}{}
	}
	for _, g := range callerGroups {
		if _, ok := allowed[normalizeGroup(g)]; ok {
			return true
		}
	}
	return false
}

func normalizeGroup(g string) string {
	for len(g) > 0 && g[0] == '/' {
		g = g[1:]
	}
	return g
}

// splitFrontmatter separates a leading "---\n<yaml>\n---\n" block from the
// rest of a Markdown document. Splitting (rather than a regex) on every
// "---" occurrence and keeping only the first two matters: SplitN(s, "---", 3)
// stops after the second delimiter, so a "---" appearing later in the
// Markdown body (e.g. a horizontal rule) is preserved intact in part [2]
// rather than truncating the body.
func splitFrontmatter(raw []byte) (frontmatter []byte, body []byte, err error) {
	parts := strings.SplitN(string(raw), "---", 3)
	if len(parts) < 3 {
		return nil, nil, fmt.Errorf("expected a leading '---' YAML frontmatter block")
	}
	return []byte(parts[1]), []byte(strings.TrimSpace(parts[2])), nil
}

// LoadAll walks dir for <dir>/<name>/agent.okf.md bundles, one per agent
// subdirectory, resolves each bundle's zuno.tasks into agents/<name>/tasks/<task>.md,
// and returns them sorted by agent name for stable portal rendering order.
func LoadAll(dir string) ([]Agent, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, fmt.Errorf("reading agents directory %q: %w", dir, err)
	}

	var agents []Agent
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		agentDir := filepath.Join(dir, entry.Name())
		path := filepath.Join(agentDir, "agent.okf.md")
		raw, err := os.ReadFile(path)
		if err != nil {
			if os.IsNotExist(err) {
				continue
			}
			return nil, fmt.Errorf("reading %q: %w", path, err)
		}
		frontmatter, _, err := splitFrontmatter(raw)
		if err != nil {
			return nil, fmt.Errorf("%q: %w", path, err)
		}
		var a Agent
		if err := yaml.Unmarshal(frontmatter, &a); err != nil {
			return nil, fmt.Errorf("parsing %q frontmatter: %w", path, err)
		}
		if a.Zuno.Name == "" {
			return nil, fmt.Errorf("%q: zuno.name is required", path)
		}
		tasks, err := loadTasks(agentDir, a.Zuno.TaskNames)
		if err != nil {
			return nil, err
		}
		a.Tasks = tasks
		agents = append(agents, a)
	}

	sort.Slice(agents, func(i, j int) bool {
		return agents[i].Zuno.Name < agents[j].Zuno.Name
	})

	return agents, nil
}

func loadTasks(agentDir string, taskNames []string) ([]Task, error) {
	var tasks []Task
	for _, name := range taskNames {
		path := filepath.Join(agentDir, "tasks", name+".md")
		raw, err := os.ReadFile(path)
		if err != nil {
			return nil, fmt.Errorf("reading task %q: %w", path, err)
		}
		frontmatter, _, err := splitFrontmatter(raw)
		if err != nil {
			return nil, fmt.Errorf("%q: %w", path, err)
		}
		var tf taskFrontmatter
		if err := yaml.Unmarshal(frontmatter, &tf); err != nil {
			return nil, fmt.Errorf("parsing %q frontmatter: %w", path, err)
		}
		tasks = append(tasks, Task{
			Name:         name,
			Title:        tf.Title,
			AllowedTools: tf.Zuno.AllowedTools,
		})
	}
	return tasks, nil
}

// Find returns the agent with the given zuno.name, if loaded.
func Find(agents []Agent, name string) (Agent, bool) {
	for _, a := range agents {
		if a.Zuno.Name == name {
			return a, true
		}
	}
	return Agent{}, false
}
