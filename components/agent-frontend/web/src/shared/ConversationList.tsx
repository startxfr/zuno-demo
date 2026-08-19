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
import { OutlinedStarIcon, StarIcon, TrashIcon } from "@patternfly/react-icons";
import { deleteConversation, listConversations, renameConversation, setStar, type Conversation } from "./conversations";
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
  // Current sidebar width in px and its setter, owned by chat/Chat.tsx
  // (it applies the value as a CSS custom property on <Page>, the only
  // thing PageSidebar's own width actually listens to - see
  // ResizeHandle below). Lifted up rather than kept local so Chat.tsx can
  // persist/restore it.
  width: number;
  onWidthChange: (width: number) => void;
}

const MIN_SIDEBAR_WIDTH = 220;
const MAX_SIDEBAR_WIDTH = 600;

// PatternFly's PageSidebar has no width/resize prop of its own - its
// width is fixed by the --pf-v6-c-page__sidebar--Width CSS custom
// property, declared on <Page>'s own root element (confirmed by reading
// react-styles/css/components/Page/page.css). This drags that variable
// directly rather than reusing PatternFly's Drawer/DrawerPanelContent
// resize engine, which would require moving the sidebar out of Page's
// `sidebar` slot entirely - and Page's masthead only spans the full
// width (over both the sidebar and main content) *because* it stays in
// that slot; tried the Drawer approach first and confirmed live
// (screenshot) it silently narrows the masthead to the content area only.
function ResizeHandle({
  width,
  onWidthChange,
}: {
  width: number;
  onWidthChange: (width: number) => void;
}): React.ReactElement {
  const draggingRef = React.useRef<{ startX: number; startWidth: number } | null>(null);

  React.useEffect(() => {
    function onMouseMove(e: MouseEvent) {
      if (!draggingRef.current) {
        return;
      }
      onWidthChange(draggingRef.current.startWidth + (e.clientX - draggingRef.current.startX));
    }
    function onMouseUp() {
      draggingRef.current = null;
      document.body.style.userSelect = "";
    }
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [onWidthChange]);

  return (
    /* eslint-disable jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/no-noninteractive-tabindex -- a focusable, keyboard-operable "separator" is the WAI-ARIA-documented pattern for a window/panel resize splitter (unlike a plain structural separator); eslint-plugin-jsx-a11y's static rules don't special-case that. */
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize conversation list"
      aria-valuenow={width}
      aria-valuemin={MIN_SIDEBAR_WIDTH}
      aria-valuemax={MAX_SIDEBAR_WIDTH}
      tabIndex={0}
      onMouseDown={(e) => {
        draggingRef.current = { startX: e.clientX, startWidth: width };
        // Without this, a fast drag selects the sidebar's row text along
        // the way (confirmed in a real browser) - mousemove during a drag
        // fires outside the handle's own narrow hit area.
        document.body.style.userSelect = "none";
      }}
      onKeyDown={(e) => {
        if (e.key === "ArrowLeft") onWidthChange(width - 20);
        if (e.key === "ArrowRight") onWidthChange(width + 20);
      }}
      style={{
        position: "absolute",
        top: 0,
        bottom: 0,
        right: 0,
        width: "6px",
        cursor: "col-resize",
        touchAction: "none",
      }}
    />
    /* eslint-enable jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/no-noninteractive-tabindex */
  );
}

// Left-hand conversation list (ADR-0212), rendered via PatternFly Page's
// sidebar prop (unused elsewhere in this codebase until now). No context/
// store, prop-driven like shared/UserMenu.tsx - this codebase has no
// client-side router, so every conversation open/focus goes through
// shared/tabTracker.ts's window.open, never in-place navigation.
//
// ADR-0214 (part 3): every row carries @patternfly/react-icons icons -
// filled/outline StarIcon for the star toggle, TrashIcon to delete. The
// title itself is the row's link (single click opens/focuses the
// conversation's tab; double click renames) - no separate per-row icon
// for that. Rename stays double-click-to-edit (no kebab menu yet) -
// deliberately scoped down from ADR-0214's original text, which
// described the kebab's actions (share, clone, rename) as an ADR-0213
// dependency this codebase doesn't have yet; it lands once ADR-0213 does.
export function ConversationList({
  agent,
  conversationsURL,
  chatURL,
  activeRunId,
  refreshSignal,
  width,
  onWidthChange,
}: ConversationListProps): React.ReactElement {
  const [conversations, setConversations] = React.useState<Conversation[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [search, setSearch] = React.useState("");
  const [renamingRunId, setRenamingRunId] = React.useState<string | null>(null);
  const [renameValue, setRenameValue] = React.useState("");
  const renameInputRef = React.useRef<HTMLInputElement | null>(null);
  // The title is both the open-tab click target and the rename
  // double-click target - a double click's two constituent click events
  // would otherwise open two stray tabs before the dblclick handler ever
  // runs. Delaying the single-click action lets a following dblclick
  // cancel it (the standard click-vs-dblclick disambiguation pattern).
  const clickTimerRef = React.useRef<number | null>(null);

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

  function handleTitleClick(runId: string) {
    if (clickTimerRef.current !== null) {
      window.clearTimeout(clickTimerRef.current);
    }
    clickTimerRef.current = window.setTimeout(() => {
      openExisting(runId);
      clickTimerRef.current = null;
    }, 250);
  }

  function handleTitleDoubleClick(runId: string, title: string) {
    if (clickTimerRef.current !== null) {
      window.clearTimeout(clickTimerRef.current);
      clickTimerRef.current = null;
    }
    setRenamingRunId(runId);
    setRenameValue(title);
  }

  async function toggleStar(runId: string, starred: boolean) {
    try {
      await setStar(conversationsURL, runId, starred);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function deleteConversationRow(runId: string, title: string) {
    if (!window.confirm(`Delete "${title || "Untitled conversation"}"? This can't be undone from here.`)) {
      return;
    }
    try {
      await deleteConversation(conversationsURL, runId);
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
    <PageSidebar style={{ position: "relative" }}>
      <ResizeHandle width={width} onWidthChange={onWidthChange} />
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
                  }}
                >
                  <button
                    type="button"
                    aria-label={c.starred ? "Unstar conversation" : "Star conversation"}
                    onClick={() => void toggleStar(c.run_id, !c.starred)}
                    style={{
                      background: "none",
                      border: "none",
                      cursor: "pointer",
                      padding: 0,
                      display: "flex",
                      color: c.starred ? "var(--pf-t--global--icon--color--favorite--default)" : undefined,
                    }}
                  >
                    {c.starred ? <StarIcon /> : <OutlinedStarIcon />}
                  </button>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    {renamingRunId === c.run_id ? (
                      <TextInput
                        ref={renameInputRef}
                        aria-label="Rename conversation"
                        value={renameValue}
                        onChange={(_e, value) => setRenameValue(value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") void commitRename(c.run_id, renameValue);
                          if (e.key === "Escape") setRenamingRunId(null);
                        }}
                        onBlur={() => void commitRename(c.run_id, renameValue)}
                      />
                    ) : (
                      // The title itself is the row's link (ADR-0214
                      // follow-up) - single click opens/focuses the
                      // conversation's tab (delayed, so a following
                      // dblclick can cancel it - see handleTitleClick),
                      // double click renames.
                      <a
                        href={`${chatURL}?run_id=${encodeURIComponent(c.run_id)}`}
                        onClick={(e) => {
                          e.preventDefault();
                          handleTitleClick(c.run_id);
                        }}
                        onDoubleClick={(e) => {
                          e.preventDefault();
                          handleTitleDoubleClick(c.run_id, c.title);
                        }}
                        title={c.title || "Untitled conversation"}
                        style={{
                          display: "block",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                          color: "var(--pf-t--global--text--color--regular)",
                        }}
                      >
                        {c.title || "Untitled conversation"}
                      </a>
                    )}
                  </div>
                  <button
                    type="button"
                    aria-label="Delete conversation"
                    onClick={() => void deleteConversationRow(c.run_id, c.title)}
                    style={{
                      background: "none",
                      border: "none",
                      cursor: "pointer",
                      padding: 0,
                      display: "flex",
                      color: "var(--pf-t--global--icon--color--subtle)",
                    }}
                  >
                    <TrashIcon />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </PageSidebarBody>
    </PageSidebar>
  );
}
