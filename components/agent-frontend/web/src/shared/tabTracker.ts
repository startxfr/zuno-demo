// ADR-0212: localStorage-only (never synced across devices or browsers,
// by design) mapping from one conversation to a named window.open()
// target, so clicking an already-open conversation in this browser
// focuses that tab instead of duplicating it. Not every browser lets JS
// focus an existing tab by name without newer Tab/Window-Management
// permissions - the fallback is simply opening a new tab, never a hard
// failure, since window.open with an unfocusable but still-valid target
// name still opens/reuses a tab, just without guaranteed focus.

function storageKey(agent: string, runId: string): string {
  return `zuno.openTabs.${agent}.${runId}`;
}

// Opens (or, in browsers/contexts that support it, focuses) url in a tab
// dedicated to this existing conversation - each run_id gets its own
// stable target name so repeated clicks reuse the same tab rather than
// opening a duplicate. Only meaningful for a conversation that already
// has a run_id; starting a brand new conversation has no such stable
// identity to track and should just use a plain, unnamed window.open.
export function openConversationTab(agent: string, runId: string, url: string): void {
  const key = storageKey(agent, runId);
  let tabName = window.localStorage.getItem(key);
  if (!tabName) {
    tabName = `zuno-conv-${agent}-${runId}-${Math.random().toString(36).slice(2)}`;
    window.localStorage.setItem(key, tabName);
  }
  window.open(url, tabName);
}
