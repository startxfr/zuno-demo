// Package assets resolves component/agent-frontend/web's Vite build
// manifest (ADR-0044) so the Go server can reference the right
// content-hashed JS/CSS files without hardcoding filenames. This is the
// standard Vite "backend integration" pattern
// (https://vite.dev/guide/backend-integration): `npm run build` in web/
// writes web/dist/.vite/manifest.json, and a non-JS backend reads it at
// startup to emit correct <script>/<link> tags per request.
package assets

import (
	"encoding/json"
	"fmt"
	"os"
	"path"
)

type manifestEntry struct {
	File    string   `json:"file"`
	CSS     []string `json:"css"`
	Imports []string `json:"imports"`
}

// Manifest is a parsed Vite manifest.json.
type Manifest struct {
	entries map[string]manifestEntry
	base    string
}

// Asset is what a page template needs for one Vite entry: its own JS
// module plus every CSS file it (transitively) depends on.
type Asset struct {
	JS  string
	CSS []string
}

// Load reads and parses a Vite manifest.json at manifestPath. base is
// prefixed onto every referenced file path - pass the same value as
// web/vite.config.ts's build.base ("/static/"), so URLs match the route
// main.go mounts the built dist/ directory under.
func Load(manifestPath, base string) (*Manifest, error) {
	data, err := os.ReadFile(manifestPath)
	if err != nil {
		return nil, fmt.Errorf(
			"reading Vite manifest %q: %w (run `npm run build` in components/agent-frontend/web first)",
			manifestPath, err,
		)
	}
	var raw map[string]manifestEntry
	if err := json.Unmarshal(data, &raw); err != nil {
		return nil, fmt.Errorf("parsing Vite manifest %q: %w", manifestPath, err)
	}
	return &Manifest{entries: raw, base: base}, nil
}

// Entry resolves the given manifest key (e.g. "src/chat/main.tsx", matching
// web/vite.config.ts's rollupOptions.input) to its JS entry module and the
// full, de-duplicated set of CSS files it needs. A Vite manifest entry's
// own "css" field lists only CSS the entry module itself imports directly
// - CSS pulled in by a shared chunk it imports (e.g. the PatternFly base
// stylesheet, bundled into a chunk both the portal and chat entries share)
// lives on that chunk's own manifest entry instead. This walks "imports"
// transitively to collect all of it, per Vite's own backend-integration
// guide.
func (m *Manifest) Entry(src string) (Asset, error) {
	e, ok := m.entries[src]
	if !ok {
		return Asset{}, fmt.Errorf("no manifest entry for %q", src)
	}

	seen := map[string]bool{}
	var css []string
	var walk func(key string)
	walk = func(key string) {
		if seen[key] {
			return
		}
		seen[key] = true
		ent, ok := m.entries[key]
		if !ok {
			return
		}
		for _, c := range ent.CSS {
			css = append(css, path.Join(m.base, c))
		}
		for _, imp := range ent.Imports {
			walk(imp)
		}
	}
	walk(src)

	return Asset{JS: path.Join(m.base, e.File), CSS: css}, nil
}
