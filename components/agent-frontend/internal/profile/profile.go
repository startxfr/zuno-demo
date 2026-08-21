// Package profile serves a read-only account page: the signed-in user's
// identity (name/email/groups) and the same per-agent entitlement
// computation the portal uses (portal.BuildTiles), for transparency into
// why the portal shows what it shows. No editing - group membership and
// access grants are managed in Keycloak, not here.
//
// ADR-0044: same thin-Go-shell + PatternFly-island pattern as
// internal/portal and internal/chat - see those packages' doc comments.
package profile

import (
	"encoding/json"
	"html/template"
	"net/http"

	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/assets"
	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/okf"
	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/portal"
	"github.com/startxfr/zuno-demo/components/agent-frontend/internal/session"
)

// config mirrors web/src/shared/types.ts's ProfileConfig field-for-field -
// see portal.go's identical comment for why this is kept in sync by hand.
type config struct {
	UserDisplayName string              `json:"userDisplayName"`
	Subject         string              `json:"subject"`
	Email           string              `json:"email"`
	Groups          []string            `json:"groups"`
	HomeURL         string              `json:"homeURL"`
	LogoutURL       string              `json:"logoutURL"`
	ProfileURL      string              `json:"profileURL"`
	Tiles           []portal.TileConfig `json:"tiles"`
}

const pageTemplate = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Profile - Zuno</title>
  {{range .CSS}}<link rel="stylesheet" href="{{.}}">
  {{end}}
</head>
<body>
  <div id="root"></div>
  <script id="zuno-config" type="application/json">{{.ConfigJSON}}</script>
  <script type="module" src="{{.JS}}"></script>
</body>
</html>`

var tmpl = template.Must(template.New("profile").Parse(pageTemplate))

type pageView struct {
	JS         string
	CSS        []string
	ConfigJSON template.JS
}

// Handler serves the read-only profile page, gated on being signed in
// (same redirect-to-/login behavior as chat.PageHandler - unlike the
// portal, which tolerates signed-out visitors). clusterBaseDomain - see
// portal.BuildTiles's own doc comment.
func Handler(agents []okf.Agent, sessions *session.Manager, asset assets.Asset, clusterBaseDomain string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		sess, err := sessions.Load(r)
		if err != nil || sess == nil {
			http.Redirect(w, r, "/login", http.StatusFound)
			return
		}

		cfg := config{
			UserDisplayName: sess.DisplayName(),
			Subject:         sess.Subject,
			Email:           sess.Email,
			Groups:          sess.Groups,
			HomeURL:         "/",
			LogoutURL:       "/logout",
			ProfileURL:      "/profile",
			Tiles:           portal.BuildTiles(agents, sess, clusterBaseDomain),
		}
		// json.Marshal HTML-escapes '<', '>' and '&' by default - safe to
		// embed directly in a <script> tag, see portal.go's identical
		// comment.
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
