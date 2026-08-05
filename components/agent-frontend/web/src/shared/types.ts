// Shapes of the JSON config Go injects into each page's
// `<script id="zuno-config" type="application/json">` tag (ADR-0044:
// "Keep runtime API endpoint injection from environment into JavaScript
// context" - these values are only known per-request/per-deployment, so
// they cannot be baked into the static Vite bundle at build time).

export interface PortalTile {
  name: string;
  displayName: string;
  tileDescription: string;
  color: string;
  icon: string;
  status: "active" | "placeholder";
  authorized: boolean;
  clickable: boolean;
  href: string;
}

export interface PortalConfig {
  signedIn: boolean;
  subject: string;
  loginURL: string;
  logoutURL: string;
  tiles: PortalTile[];
}

export interface ChatConfig {
  displayName: string;
  subject: string;
  homeURL: string;
  logoutURL: string;
  // Same-origin path this page's Go server proxies to the BFF
  // (components/agent-frontend/internal/chat/chat.go's APIHandler).
  apiURL: string;
}
