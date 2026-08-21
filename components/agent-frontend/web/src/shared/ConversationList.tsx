import * as React from "react";
import {
  Button,
  Dropdown,
  DropdownItem,
  DropdownList,
  EmptyState,
  EmptyStateBody,
  MenuToggle,
  type MenuToggleElement,
  PageSidebar,
  PageSidebarBody,
  Spinner,
  TextInput,
} from "@patternfly/react-core";
import {
  BanIcon,
  CloneIcon,
  EllipsisVIcon,
  GripVerticalIcon,
  OutlinedStarIcon,
  PencilAltIcon,
  ShareIcon,
  StarIcon,
  TrashIcon,
} from "@patternfly/react-icons";
import {
  cloneConversation,
  deleteConversation,
  hardDeleteConversation,
  listConversations,
  renameConversation,
  reorderConversations,
  setStar,
  type Conversation,
} from "./conversations";
import { ShareDialog } from "./ShareDialog";

export interface ConversationListProps {
  conversationsURL: string;
  // ADR-0213: same-origin colleague-search endpoint, passed straight
  // through to ShareDialog - this component never calls it directly.
  colleaguesURL: string;
  // The run_id of the currently active in-app tab, if any - highlighted
  // in the list.
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
  // ADR-0515: opening or creating a conversation now activates an in-app
  // tab in chat/Chat.tsx - this list never navigates or opens a browser
  // tab itself (shared/tabTracker.ts is agent-scoped now, used only by
  // the masthead's cross-agent nav strip).
  onOpenConversation: (runId: string, title: string, starred: boolean) => void;
  onNewConversation: () => void;
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
// sidebar prop. No context/store, prop-driven like shared/UserMenu.tsx -
// opening/creating a conversation is delegated to the parent (Chat.tsx)
// via onOpenConversation/onNewConversation, which own the in-app tab set
// (ADR-0515) - this component only ever renders and reorders the list.
//
// ADR-0515 (WP-061): every row now carries a drag handle (manual reorder,
// persisted via reorderConversations) and a right-aligned kebab menu
// consolidating rename/star/soft-delete/hard-delete - replacing ADR-0214's
// standalone star/trash buttons and double-click-to-rename stopgap.
export function ConversationList({
  conversationsURL,
  colleaguesURL,
  activeRunId,
  refreshSignal,
  width,
  onWidthChange,
  onOpenConversation,
  onNewConversation,
}: ConversationListProps): React.ReactElement {
  const [conversations, setConversations] = React.useState<Conversation[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [search, setSearch] = React.useState("");
  const [renamingRunId, setRenamingRunId] = React.useState<string | null>(null);
  const [renameValue, setRenameValue] = React.useState("");
  const [openKebabRunId, setOpenKebabRunId] = React.useState<string | null>(null);
  const [draggedRunId, setDraggedRunId] = React.useState<string | null>(null);
  // ADR-0213: the conversation currently open in the share dialog, if
  // any - null closes it. Only run_id/title are needed (ShareDialog
  // fetches its own member list once open).
  const [sharing, setSharing] = React.useState<{ runId: string; title: string } | null>(null);
  const [cloning, setCloning] = React.useState<string | null>(null);
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

  async function toggleStar(runId: string, starred: boolean) {
    try {
      await setStar(conversationsURL, runId, starred);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function deleteConversationRow(runId: string, title: string) {
    if (!window.confirm(`Delete "${title || "Untitled conversation"}"? This hides it from your list, but keeps its history.`)) {
      return;
    }
    try {
      await deleteConversation(conversationsURL, runId);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function hardDeleteConversationRow(runId: string, title: string) {
    if (
      !window.confirm(
        `Permanently delete "${title || "Untitled conversation"}"? This cannot be undone - its entire message history is erased.`,
      )
    ) {
      return;
    }
    try {
      await hardDeleteConversation(conversationsURL, runId);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function cloneConversationRow(runId: string, title: string) {
    setCloning(runId);
    try {
      const newRunId = await cloneConversation(conversationsURL, runId);
      refresh();
      // ADR-0213: the clone is immediately usable and solely owned by
      // the caller - open it right away rather than leaving them to
      // find it in the (now-refreshed) list themselves.
      onOpenConversation(newRunId, title, false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setCloning(null);
    }
  }

  function startRename(runId: string, title: string) {
    setRenamingRunId(runId);
    setRenameValue(title);
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

  // ADR-0515: manual drag-reorder, disabled while a search filter is
  // active - reordering a filtered subset's *visual* order against the
  // full underlying list's positions is ambiguous, so this pass simply
  // doesn't offer it while filtered.
  const dragEnabled = search.trim() === "";

  function handleDrop(targetRunId: string) {
    const draggedId = draggedRunId;
    setDraggedRunId(null);
    if (!draggedId || draggedId === targetRunId || conversations === null) {
      return;
    }
    const list = [...conversations];
    const fromIdx = list.findIndex((c) => c.run_id === draggedId);
    const toIdx = list.findIndex((c) => c.run_id === targetRunId);
    if (fromIdx === -1 || toIdx === -1) {
      return;
    }
    const [moved] = list.splice(fromIdx, 1);
    list.splice(toIdx, 0, moved);
    setConversations(list);
    reorderConversations(
      conversationsURL,
      list.map((c) => c.run_id),
    ).catch((err) => {
      setError(err instanceof Error ? err.message : String(err));
      refresh();
    });
  }

  const filtered = (conversations ?? []).filter((c) =>
    c.title.toLowerCase().includes(search.trim().toLowerCase()),
  );

  return (
    <PageSidebar style={{ position: "relative" }}>
      <ResizeHandle width={width} onWidthChange={onWidthChange} />
      <PageSidebarBody>
        <div style={{ padding: "1rem", display: "flex", flexDirection: "column", gap: "0.75rem", height: "100%" }}>
          <Button variant="primary" isBlock onClick={onNewConversation}>
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
                  draggable={dragEnabled}
                  onDragStart={() => dragEnabled && setDraggedRunId(c.run_id)}
                  onDragOver={(e) => {
                    if (dragEnabled) {
                      e.preventDefault();
                    }
                  }}
                  onDrop={(e) => {
                    if (!dragEnabled) {
                      return;
                    }
                    e.preventDefault();
                    handleDrop(c.run_id);
                  }}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.375rem",
                    padding: "0.5rem",
                    borderRadius: "var(--pf-t--global--border-radius--medium, 4px)",
                    opacity: draggedRunId === c.run_id ? 0.5 : 1,
                    background:
                      c.run_id === activeRunId
                        ? "var(--pf-t--global--background--color--secondary--default)"
                        : undefined,
                  }}
                >
                  {dragEnabled && (
                    <span
                      aria-hidden="true"
                      style={{ cursor: "grab", display: "flex", color: "var(--pf-t--global--icon--color--subtle)" }}
                    >
                      <GripVerticalIcon />
                    </span>
                  )}
                  {c.starred && (
                    <span
                      aria-label="Starred"
                      style={{ display: "flex", color: "var(--pf-t--global--icon--color--favorite--default)" }}
                    >
                      <StarIcon />
                    </span>
                  )}
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
                      <button
                        type="button"
                        onClick={() => onOpenConversation(c.run_id, c.title, c.starred)}
                        title={c.title || "Untitled conversation"}
                        style={{
                          display: "block",
                          width: "100%",
                          textAlign: "left",
                          background: "none",
                          border: "none",
                          padding: 0,
                          cursor: "pointer",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                          color: "var(--pf-t--global--text--color--regular)",
                        }}
                      >
                        {c.title || "Untitled conversation"}
                      </button>
                    )}
                  </div>
                  <Dropdown
                    isOpen={openKebabRunId === c.run_id}
                    onOpenChange={(isOpen) => setOpenKebabRunId(isOpen ? c.run_id : null)}
                    toggle={(toggleRef: React.Ref<MenuToggleElement>) => (
                      <MenuToggle
                        ref={toggleRef}
                        aria-label={`Actions for ${c.title || "Untitled conversation"}`}
                        variant="plain"
                        onClick={() => setOpenKebabRunId(openKebabRunId === c.run_id ? null : c.run_id)}
                        isExpanded={openKebabRunId === c.run_id}
                      >
                        <EllipsisVIcon />
                      </MenuToggle>
                    )}
                  >
                    <DropdownList>
                      <DropdownItem
                        key="rename"
                        icon={<PencilAltIcon />}
                        onClick={() => {
                          setOpenKebabRunId(null);
                          startRename(c.run_id, c.title);
                        }}
                      >
                        Rename
                      </DropdownItem>
                      <DropdownItem
                        key="star"
                        icon={c.starred ? <OutlinedStarIcon /> : <StarIcon />}
                        onClick={() => {
                          setOpenKebabRunId(null);
                          void toggleStar(c.run_id, !c.starred);
                        }}
                      >
                        {c.starred ? "Unstar" : "Star"}
                      </DropdownItem>
                      <DropdownItem
                        key="share"
                        icon={<ShareIcon />}
                        onClick={() => {
                          setOpenKebabRunId(null);
                          setSharing({ runId: c.run_id, title: c.title });
                        }}
                      >
                        Share
                      </DropdownItem>
                      <DropdownItem
                        key="clone"
                        icon={<CloneIcon />}
                        isDisabled={cloning === c.run_id}
                        onClick={() => {
                          setOpenKebabRunId(null);
                          void cloneConversationRow(c.run_id, c.title);
                        }}
                      >
                        {cloning === c.run_id ? "Cloning…" : "Clone"}
                      </DropdownItem>
                      <DropdownItem
                        key="delete"
                        icon={<TrashIcon />}
                        onClick={() => {
                          setOpenKebabRunId(null);
                          void deleteConversationRow(c.run_id, c.title);
                        }}
                      >
                        Delete
                      </DropdownItem>
                      <DropdownItem
                        key="hard-delete"
                        icon={<BanIcon />}
                        isDanger
                        onClick={() => {
                          setOpenKebabRunId(null);
                          void hardDeleteConversationRow(c.run_id, c.title);
                        }}
                      >
                        Delete permanently
                      </DropdownItem>
                    </DropdownList>
                  </Dropdown>
                </div>
              ))}
            </div>
          )}
        </div>
      </PageSidebarBody>
      {sharing && (
        <ShareDialog
          isOpen
          onClose={() => setSharing(null)}
          conversationsURL={conversationsURL}
          colleaguesURL={colleaguesURL}
          runId={sharing.runId}
          title={sharing.title}
        />
      )}
    </PageSidebar>
  );
}
