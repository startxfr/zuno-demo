// Package portal serves the agent portal: one tile per agent defined in
// agents/*/agent.okf.md (ADR-0038), enabled/clickable only when the signed-in
// user's JWT groups intersect that agent's zuno.access.groups AND the agent's
// status is active. Agents that are placeholder-only (four of five in v0,
// see platform/architecture/agent-platform-separation.md) always render as
// a disabled "coming soon" tile, regardless of the viewer's groups - an
// honest reflection of what's actually deployed, not an access-control
// decision.
//
// ADR-0044: the page itself is a thin, per-request HTML shell - the actual
// tile grid is a PatternFly React component (web/src/portal/Portal.tsx)
// mounted into #root, with this handler's server-computed state (session,
// tiles) passed across as a JSON blob rather than server-templated HTML.
// See internal/assets for how the Vite-built JS/CSS is resolved.
package portal

import (
	"encoding/json"
	"fmt"
	"html/template"
	"net/http"

	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/assets"
	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/okf"
	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/session"
)

// TileConfig/config mirror web/src/shared/types.ts's PortalTile/PortalConfig
// field-for-field - kept in sync by hand, the same tradeoff already made
// for the OKF Markdown bundle format elsewhere in this repo (ADR-0038)
// rather than adding a schema-generation step to this small a project.
// TileConfig is exported so internal/profile can reuse BuildTiles's output
// for the same per-agent access computation on the profile page.
type TileConfig struct {
	Name            string `json:"name"`
	DisplayName     string `json:"displayName"`
	TileDescription string `json:"tileDescription"`
	Color           string `json:"color"`
	Icon            string `json:"icon"`
	Status          string `json:"status"` // "active" | "placeholder"
	Authorized      bool   `json:"authorized"`
	Clickable       bool   `json:"clickable"`
	Href            string `json:"href"`
}

type config struct {
	SignedIn        bool         `json:"signedIn"`
	Subject         string       `json:"subject"`
	UserDisplayName string       `json:"userDisplayName,omitempty"`
	LoginURL        string       `json:"loginURL"`
	LogoutURL       string       `json:"logoutURL"`
	ProfileURL      string       `json:"profileURL"`
	Tiles           []TileConfig `json:"tiles"`
}

// BuildTiles computes the per-agent tile view (access-gating, ADR-0038) for
// a signed-in-or-not session. Shared by Handler (all agents, for the
// portal grid) and internal/profile.Handler (the same computation, viewed
// as "your entitlements" on the profile page).
//
// clusterBaseDomain is the platform-wide Route suffix (e.g.
// "apps.demo222.startx.fr") every agent-frontend Deployment already
// resolves to for its own hostname (config.Config.SelfBaseURL); every
// tile's Href is a full cross-origin URL (https://<name>.<domain>/<name>)
// because each agent is its own separate Deployment/Route (ADR-0008), not
// a path under this page's own origin - found live 2026-08-21: the old
// relative "/"+name href silently 404'd for every agent except whichever
// one happens to be this Deployment's own ACTIVE_AGENT.
func BuildTiles(agents []okf.Agent, sess *session.Session, clusterBaseDomain string) []TileConfig {
	tiles := make([]TileConfig, 0, len(agents))
	for _, a := range agents {
		authorized := sess != nil && a.AllowsAnyGroup(sess.Groups)
		tiles = append(tiles, TileConfig{
			Name:            a.Zuno.Name,
			DisplayName:     a.Zuno.UI.DisplayName,
			TileDescription: a.Zuno.UI.TileDescription,
			Color:           a.Zuno.UI.Color,
			Icon:            a.Zuno.UI.Icon,
			Status:          a.Zuno.Status,
			Authorized:      authorized,
			Clickable:       a.IsActive() && authorized,
			Href:            fmt.Sprintf("https://%s.%s/%s", a.Zuno.Name, clusterBaseDomain, a.Zuno.Name),
		})
	}
	return tiles
}

const pageTemplate = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Zuno Agent Portal</title>
  {{range .CSS}}<link rel="stylesheet" href="{{.}}">
  {{end}}
</head>
<body>
  <div id="root"></div>
  <script id="zuno-config" type="application/json">{{.ConfigJSON}}</script>
  <script type="module" src="{{.JS}}"></script>
</body>
</html>`

var tmpl = template.Must(template.New("portal").Parse(pageTemplate))

type pageView struct {
	JS         string
	CSS        []string
	ConfigJSON template.JS
}

// Handler returns an http.HandlerFunc that renders the portal page.
// asset is web/src/portal/main.tsx's resolved Vite manifest entry (see
// internal/assets and main.go's wiring). clusterBaseDomain - see
// BuildTiles's own doc comment.
func Handler(agents []okf.Agent, sessions *session.Manager, asset assets.Asset, clusterBaseDomain string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		sess, _ := sessions.Load(r)

		cfg := config{
			LoginURL:   "/login",
			LogoutURL:  "/logout",
			ProfileURL: "/profile",
		}
		if sess != nil {
			cfg.SignedIn = true
			cfg.Subject = sess.Subject
			cfg.UserDisplayName = sess.DisplayName()
		}

		cfg.Tiles = BuildTiles(agents, sess, clusterBaseDomain)

		// json.Marshal (the package-level function, unlike a custom
		// Encoder) HTML-escapes '<', '>' and '&' by default - safe to embed
		// directly in a <script> tag even if a claim (e.g. Subject, an
		// email from the validated OIDC token) contained "</script>".
		configJSON, err := json.Marshal(cfg)
		if err != nil {
			http.Error(w, "internal error", http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		view := pageView{JS: asset.JS, CSS: asset.CSS, ConfigJSON: template.JS(configJSON)}
		if err := tmpl.Execute(w, view); err != nil {
			http.Error(w, "template error", http.StatusInternalServerError)
		}
	}
}
