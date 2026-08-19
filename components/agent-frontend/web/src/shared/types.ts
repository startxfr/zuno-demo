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
  // Best-available human-readable name (session.Session.DisplayName():
  // preferred_username, falling back to email, then subject) - only
  // meaningful when signedIn.
  userDisplayName: string;
  loginURL: string;
  logoutURL: string;
  profileURL: string;
  tiles: PortalTile[];
}

export interface ChatConfig {
  // The AGENT's display name (e.g. "Tekos") - not the signed-in user's.
  displayName: string;
  subject: string;
  // The signed-in USER's display name - see PortalConfig.userDisplayName.
  userDisplayName: string;
  homeURL: string;
  logoutURL: string;
  profileURL: string;
  // Same-origin path this page's Go server proxies to the BFF
  // (components/agent-frontend/internal/chat/chat.go's APIHandler).
  apiURL: string;
  // ADR-0212: same-origin base this page's Go server proxies to the BFF's
  // conversation-management routes (internal/chat/chat.go's
  // ConversationsProxyHandler) - always "/api/conversations" today.
  // shared/ConversationList.tsx builds the transcript/rename/star
  // endpoints by appending to this base at request time.
  conversationsURL: string;
}

// Shape of the JSON config Go injects for the read-only /profile page
// (components/agent-frontend/internal/profile/profile.go).
export interface ProfileConfig {
  userDisplayName: string;
  subject: string;
  email: string;
  groups: string[];
  homeURL: string;
  logoutURL: string;
  profileURL: string;
  tiles: PortalTile[];
}
