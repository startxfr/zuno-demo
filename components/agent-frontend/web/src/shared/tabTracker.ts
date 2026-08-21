// ADR-0515: localStorage-only (never synced across devices or browsers, by
// design) mapping from one agent to a named window.open() target, so
// clicking that agent again (e.g. from the cross-agent masthead nav strip)
// focuses its already-open browser tab instead of opening a duplicate.
// Supersedes ADR-0212's per-conversation granularity: a browser tab is now
// scoped to one agent, not one conversation - switching between
// conversations inside an agent happens as an in-app tab
// (chat/Chat.tsx's Tabs bar), never a new window.open. Not every browser
// lets JS focus an existing tab by name without newer Tab/Window-Management
// permissions - the fallback is simply opening a new tab, never a hard
// failure, since window.open with an unfocusable but still-valid target
// name still opens/reuses a tab, just without guaranteed focus.

function storageKey(agent: string): string {
  return `zuno.openTabs.${agent}`;
}

// Opens (or, in browsers/contexts that support it, focuses) url in the tab
// dedicated to this agent - each agent gets its own stable target name so
// repeated clicks (from the masthead nav strip, or reopening this agent
// from elsewhere) reuse the same tab rather than opening a duplicate.
export function openAgentTab(agent: string, url: string): void {
  const key = storageKey(agent);
  let tabName = window.localStorage.getItem(key);
  if (!tabName) {
    tabName = `zuno-agent-${agent}-${Math.random().toString(36).slice(2)}`;
    window.localStorage.setItem(key, tabName);
  }
  window.open(url, tabName);
}
