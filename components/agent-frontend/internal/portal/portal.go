// Package portal renders the agent portal: one tile per agent defined in
// agents/*/agent.okf.yaml, enabled/clickable only when the signed-in user's
// JWT groups intersect that agent's spec.access.groups AND the agent's
// status is active. Agents that are placeholder-only (four of five in v0,
// see platform/architecture/agent-platform-separation.md) always render as
// a disabled "coming soon" tile, regardless of the viewer's groups - an
// honest reflection of what's actually deployed, not an access-control
// decision.
package portal

import (
	"html/template"
	"net/http"

	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/okf"
	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/session"
)

type tileView struct {
	Name            string
	DisplayName     string
	TileDescription string
	Color           string
	Icon            string
	Status          string // "active" | "placeholder"
	Authorized      bool   // caller's groups intersect access.groups
	Clickable       bool   // Status == active && Authorized
	Href            string
}

type pageView struct {
	SignedIn  bool
	Subject   string
	Tiles     []tileView
	LoginURL  string
	LogoutURL string
}

const pageTemplate = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Zuno Agent Portal</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body class="pf-body">
  <header class="zuno-header">
    <div class="zuno-header-title">Zuno Agent Portal</div>
    <div class="zuno-header-user">
      {{if .SignedIn}}
        <span class="zuno-user-sub">{{.Subject}}</span>
        <a class="pf-button pf-button-link" href="{{.LogoutURL}}">Sign out</a>
      {{else}}
        <a class="pf-button pf-button-primary" href="{{.LoginURL}}">Sign in</a>
      {{end}}
    </div>
  </header>
  <main class="zuno-tile-grid">
    {{range .Tiles}}
    <div class="zuno-tile {{if not .Clickable}}zuno-tile-disabled{{end}}" style="--tile-accent: {{.Color}}">
      <div class="zuno-tile-icon" data-icon="{{.Icon}}"></div>
      <div class="zuno-tile-title">{{.DisplayName}}</div>
      <div class="zuno-tile-desc">{{.TileDescription}}</div>
      {{if eq .Status "placeholder"}}
        <div class="zuno-tile-badge">Coming soon</div>
      {{else if not .Authorized}}
        <div class="zuno-tile-badge zuno-tile-badge-locked">Not authorized</div>
      {{else}}
        <a class="zuno-tile-link" href="{{.Href}}">Open</a>
      {{end}}
    </div>
    {{end}}
  </main>
</body>
</html>`

var tmpl = template.Must(template.New("portal").Parse(pageTemplate))

// Handler returns an http.HandlerFunc that renders the portal page.
func Handler(agents []okf.Agent, sessions *session.Manager) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		sess, _ := sessions.Load(r)

		view := pageView{
			LoginURL:  "/login",
			LogoutURL: "/logout",
		}
		if sess != nil {
			view.SignedIn = true
			view.Subject = sess.Subject
		}

		for _, a := range agents {
			authorized := sess != nil && a.AllowsAnyGroup(sess.Groups)
			view.Tiles = append(view.Tiles, tileView{
				Name:            a.Metadata.Name,
				DisplayName:     a.Spec.UI.DisplayName,
				TileDescription: a.Spec.UI.TileDescription,
				Color:           a.Spec.UI.Color,
				Icon:            a.Spec.UI.Icon,
				Status:          a.Metadata.Status,
				Authorized:      authorized,
				Clickable:       a.IsActive() && authorized,
				Href:            "/" + a.Metadata.Name,
			})
		}

		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		if err := tmpl.Execute(w, view); err != nil {
			http.Error(w, "template error", http.StatusInternalServerError)
		}
	}
}
