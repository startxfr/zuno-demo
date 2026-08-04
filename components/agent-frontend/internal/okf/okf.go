// Package okf loads and represents agent.okf.yaml files (OKF v0.2 + the
// Zuno extension, ADR-0005/ADR-0006) so the portal can render one tile per
// agent from the same declarative source of truth the Agent Runtime and
// policy engine consume. See platform/okf/schema/zuno-okf-v0.2.schema.json
// for the authoritative schema this struct set mirrors.
package okf

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"

	"gopkg.in/yaml.v3"
)

// Agent is the top-level agent.okf.yaml document.
type Agent struct {
	APIVersion string   `yaml:"apiVersion"`
	Kind       string   `yaml:"kind"`
	Metadata   Metadata `yaml:"metadata"`
	Spec       Spec     `yaml:"spec"`
}

// Metadata mirrors the schema's metadata object.
type Metadata struct {
	Name        string `yaml:"name"`
	DisplayName string `yaml:"displayName"`
	Description string `yaml:"description"`
	Status      string `yaml:"status"` // "active" | "placeholder"
}

// Spec mirrors the schema's spec object (the Zuno profile).
type Spec struct {
	Tasks  []Task `yaml:"tasks"`
	Model  Model  `yaml:"model"`
	Access Access `yaml:"access"`
	UI     UI     `yaml:"ui"`
}

// Task is one entry in spec.tasks.
type Task struct {
	Name         string   `yaml:"name"`
	Description  string   `yaml:"description"`
	AllowedTools []string `yaml:"allowed_tools"`
}

// Model is spec.model.
type Model struct {
	PreferredClassification string `yaml:"preferred_classification"`
	Notes                   string `yaml:"notes"`
}

// Access is spec.access.
type Access struct {
	Groups []string `yaml:"groups"`
}

// UI is spec.ui, consumed directly by the portal tile template.
type UI struct {
	DisplayName     string `yaml:"displayName"`
	TileDescription string `yaml:"tileDescription"`
	Color           string `yaml:"color"`
	Icon            string `yaml:"icon"`
}

// IsActive reports whether this agent has a real, deployed FE/BFF (ADR-0007).
func (a Agent) IsActive() bool {
	return a.Metadata.Status == "active"
}

// AllowsAnyGroup reports whether any of the caller's JWT groups intersects
// this agent's spec.access.groups. Groups are compared without a leading
// "/" so callers can pass either the Keycloak "groups" claim's raw entries
// (e.g. "/consultant") or bare names.
func (a Agent) AllowsAnyGroup(callerGroups []string) bool {
	allowed := make(map[string]struct{}, len(a.Spec.Access.Groups))
	for _, g := range a.Spec.Access.Groups {
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

// LoadAll walks dir for <dir>/<name>/agent.okf.yaml files, one per agent
// subdirectory, and returns them sorted by agent name for stable portal
// rendering order.
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
		path := filepath.Join(dir, entry.Name(), "agent.okf.yaml")
		raw, err := os.ReadFile(path)
		if err != nil {
			if os.IsNotExist(err) {
				continue
			}
			return nil, fmt.Errorf("reading %q: %w", path, err)
		}
		var a Agent
		if err := yaml.Unmarshal(raw, &a); err != nil {
			return nil, fmt.Errorf("parsing %q: %w", path, err)
		}
		if a.Metadata.Name == "" {
			return nil, fmt.Errorf("%q: metadata.name is required", path)
		}
		agents = append(agents, a)
	}

	sort.Slice(agents, func(i, j int) bool {
		return agents[i].Metadata.Name < agents[j].Metadata.Name
	})

	return agents, nil
}

// Find returns the agent with the given metadata.name, if loaded.
func Find(agents []Agent, name string) (Agent, bool) {
	for _, a := range agents {
		if a.Metadata.Name == name {
			return a, true
		}
	}
	return Agent{}, false
}
