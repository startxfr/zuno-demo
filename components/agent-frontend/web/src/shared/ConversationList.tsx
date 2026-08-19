import * as React from "react";
import {
  Button,
  EmptyState,
  EmptyStateBody,
  PageSidebar,
  PageSidebarBody,
  Spinner,
  TextInput,
} from "@patternfly/react-core";
import { listConversations, renameConversation, setStar, type Conversation } from "./conversations";
import { openConversationTab } from "./tabTracker";

export interface ConversationListProps {
  agent: string;
  conversationsURL: string;
  // This page's own URL with no query string (window.location.pathname) -
  // every conversation opens as "{chatURL}?run_id={run_id}" (ADR-0212).
  chatURL: string;
  // The run_id this tab currently has open, if any - highlighted in the
  // list, and refreshed into once this component's own actions
  // (star/rename) change it.
  activeRunId: string | null;
  // Bump this (e.g. on every SSE "start" event) to force a re-fetch from
  // outside this component - this codebase has no shared store/context,
  // so this is how chat/Chat.tsx tells this list a new conversation just
  // appeared.
  refreshSignal?: number;
}

// Left-hand conversation list (ADR-0212), rendered via PatternFly Page's
// sidebar prop (unused elsewhere in this codebase until now). No context/
// store, prop-driven like shared/UserMenu.tsx - this codebase has no
// client-side router, so every conversation open/focus goes through
// shared/tabTracker.ts's window.open, never in-place navigation.
//
// Star/rename controls are plain text/double-click here deliberately -
// ADR-0214 (part 3) swaps these for real PatternFly icons and, later,
// ADR-0213 adds a proper per-row kebab menu once share/clone exist.
export function ConversationList({
  agent,
  conversationsURL,
  chatURL,
  activeRunId,
  refreshSignal,
}: ConversationListProps): React.ReactElement {
  const [conversations, setConversations] = React.useState<Conversation[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [search, setSearch] = React.useState("");
  const [renamingRunId, setRenamingRunId] = React.useState<string | null>(null);
  const [renameValue, setRenameValue] = React.useState("");
  const renameInputRef = React.useRef<HTMLInputElement | null>(null);

  React.useEffect(() => {
    if (renamingRunId !== null) {
      renameInputRef.current?.focus();
    }
  }, [renamingRunId]);

  const refresh = React.useCallback(() => {
    listConversations(conversationsURL)
      .then(setConversations)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [conversationsURL]);

  React.useEffect(() => {
    refresh();
  }, [refresh, refreshSignal]);

  function openExisting(runId: string) {
    openConversationTab(agent, runId, `${chatURL}?run_id=${encodeURIComponent(runId)}`);
  }

  function openNew() {
    // No stable identity to track for a not-yet-started conversation -
    // always a fresh tab, never routed through tabTracker.
    window.open(chatURL, "_blank");
  }

  async function toggleStar(runId: string, starred: boolean) {
    try {
      await setStar(conversationsURL, runId, starred);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function commitRename(runId: string, title: string) {
    setRenamingRunId(null);
    const trimmed = title.trim();
    if (!trimmed) {
      return;
    }
    try {
      await renameConversation(conversationsURL, runId, trimmed);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  const filtered = (conversations ?? []).filter((c) =>
    c.title.toLowerCase().includes(search.trim().toLowerCase()),
  );

  return (
    <PageSidebar>
      <PageSidebarBody>
        <div style={{ padding: "1rem", display: "flex", flexDirection: "column", gap: "0.75rem", height: "100%" }}>
          <Button variant="primary" isBlock onClick={openNew}>
            New conversation
          </Button>
          <TextInput
            aria-label="Search conversations"
            placeholder="Search conversations…"
            value={search}
            onChange={(_e, value) => setSearch(value)}
          />
          {error && (
            <div style={{ color: "var(--pf-t--global--color--status--danger--100)", fontSize: "0.875rem" }}>
              {error}
            </div>
          )}
          {conversations === null && !error ? (
            <Spinner size="md" aria-label="Loading conversations" />
          ) : filtered.length === 0 ? (
            <EmptyState titleText="No conversations yet" headingLevel="h3">
              <EmptyStateBody>Start a new conversation to see it here.</EmptyStateBody>
            </EmptyState>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem", overflowY: "auto" }}>
              {filtered.map((c) => (
                <div
                  key={c.run_id}
                  role="button"
                  tabIndex={0}
                  onClick={() => openExisting(c.run_id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") openExisting(c.run_id);
                  }}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.5rem",
                    padding: "0.5rem",
                    borderRadius: "var(--pf-t--global--border-radius--medium, 4px)",
                    background:
                      c.run_id === activeRunId
                        ? "var(--pf-t--global--background--color--secondary--default)"
                        : undefined,
                    cursor: "pointer",
                  }}
                >
                  <button
                    type="button"
                    aria-label={c.starred ? "Unstar conversation" : "Star conversation"}
                    onClick={(e) => {
                      e.stopPropagation();
                      void toggleStar(c.run_id, !c.starred);
                    }}
                    style={{ background: "none", border: "none", cursor: "pointer", fontSize: "1rem", lineHeight: 1 }}
                  >
                    {c.starred ? "★" : "☆"}
                  </button>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    {renamingRunId === c.run_id ? (
                      <TextInput
                        ref={renameInputRef}
                        aria-label="Rename conversation"
                        value={renameValue}
                        onClick={(e) => e.stopPropagation()}
                        onChange={(_e, value) => setRenameValue(value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") void commitRename(c.run_id, renameValue);
                          if (e.key === "Escape") setRenamingRunId(null);
                        }}
                        onBlur={() => void commitRename(c.run_id, renameValue)}
                      />
                    ) : (
                      // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions -- onClick here is defensive stopPropagation only (see below), not a real interactive action; renaming itself stays reachable via double-click, an accepted mouse-only affordance ADR-0214's later icon/kebab pass can improve on.
                      <div
                        style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                        // A double-click's two constituent click events
                        // must not also open/focus this conversation's
                        // tab - only stopPropagation on the dblclick
                        // itself isn't enough, since those single clicks
                        // fire (and bubble to the row's own onClick)
                        // before the dblclick event does.
                        onClick={(e) => e.stopPropagation()}
                        onDoubleClick={(e) => {
                          e.stopPropagation();
                          setRenamingRunId(c.run_id);
                          setRenameValue(c.title);
                        }}
                        title={c.title || "Untitled conversation"}
                      >
                        {c.title || "Untitled conversation"}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </PageSidebarBody>
    </PageSidebar>
  );
}
