import * as React from "react";
import {
  Button,
  Divider,
  EmptyState,
  EmptyStateBody,
  PageSidebar,
  PageSidebarBody,
  Spinner,
  TextInput,
} from "@patternfly/react-core";
import { AngleDownIcon, AngleRightIcon, FolderIcon, PlusIcon } from "@patternfly/react-icons";
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
import { listProjects, type Project } from "./projects";
import { ConversationRow } from "./ConversationRow";
import { ProjectDialog } from "./ProjectDialog";
import { ProjectRow } from "./ProjectRow";

export interface ConversationListProps {
  conversationsURL: string;
  // ADR-0527: the project base and the two Keycloak-Admin-backed lookups,
  // passed straight through to ProjectDialog - this component never calls
  // them itself.
  projectsURL: string;
  colleaguesURL: string;
  groupsURL: string;
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
  // thing PageSidebar's own width actually listens to - see ResizeHandle
  // below). Lifted up rather than kept local so Chat.tsx can
  // persist/restore it.
  width: number;
  onWidthChange: (width: number) => void;
  // ADR-0515: opening or creating a conversation activates an in-app tab in
  // chat/Chat.tsx - this list never navigates or opens a browser tab
  // itself. ADR-0527 widens the payload to the whole Conversation, because
  // the tab now needs project_id and the caller's role to decide read-only
  // mode, and threading four positional arguments would be worse.
  onOpenConversation: (conversation: Conversation) => void;
  onNewConversation: (projectId?: string) => void;
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

// ADR-0212's left-hand conversation list, restructured by ADR-0527 clause 9
// into two blocks: PROJECTS (each foldable, showing this agent's
// conversations for that project) and, below a separator, CONVERSATIONS -
// the caller's own project-less ones.
//
// Still prop-driven with no context/store, like shared/UserMenu.tsx:
// opening or creating a conversation is delegated to Chat.tsx, which owns
// the in-app tab set (ADR-0515). Both blocks render the SAME
// ConversationRow, extracted from this file rather than reimplemented, so
// ADR-0515's row layout cannot drift between them.
export function ConversationList({
  conversationsURL,
  projectsURL,
  colleaguesURL,
  groupsURL,
  activeRunId,
  refreshSignal,
  width,
  onWidthChange,
  onOpenConversation,
  onNewConversation,
}: ConversationListProps): React.ReactElement {
  const [conversations, setConversations] = React.useState<Conversation[] | null>(null);
  const [projects, setProjects] = React.useState<Project[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [search, setSearch] = React.useState("");
  const [renamingRunId, setRenamingRunId] = React.useState<string | null>(null);
  const [renameValue, setRenameValue] = React.useState("");
  const [draggedRunId, setDraggedRunId] = React.useState<string | null>(null);
  const [cloning, setCloning] = React.useState<string | null>(null);
  // undefined = closed, null = create mode, string = edit that project.
  const [dialogProjectId, setDialogProjectId] = React.useState<string | null | undefined>(undefined);
  const [expandedProjects, setExpandedProjects] = React.useState<Set<string>>(loadExpanded);
  const [projectsExpanded, setProjectsExpanded] = React.useState(true);
  const [conversationsExpanded, setConversationsExpanded] = React.useState(true);

  React.useEffect(() => {
    persistExpanded(expandedProjects);
  }, [expandedProjects]);

  const refresh = React.useCallback(() => {
    // Both lists in parallel - they are independent reads and the sidebar
    // needs both before it can group anything.
    Promise.all([listConversations(conversationsURL), listProjects(projectsURL)])
      .then(([conversationList, projectList]) => {
        setConversations(conversationList);
        setProjects(projectList);
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [conversationsURL, projectsURL]);

  React.useEffect(() => {
    refresh();
  }, [refresh, refreshSignal]);

  function fail(err: unknown) {
    setError(err instanceof Error ? err.message : String(err));
  }

  async function toggleStar(c: Conversation) {
    try {
      await setStar(conversationsURL, c.run_id, !c.starred);
      refresh();
    } catch (err) {
      fail(err);
    }
  }

  async function deleteConversationRow(c: Conversation) {
    if (
      !window.confirm(
        `Delete "${c.title || "Untitled conversation"}"? This hides it from the list, but keeps its history.`,
      )
    ) {
      return;
    }
    try {
      await deleteConversation(conversationsURL, c.run_id);
      refresh();
    } catch (err) {
      fail(err);
    }
  }

  async function hardDeleteConversationRow(c: Conversation) {
    if (
      !window.confirm(
        `Permanently delete "${c.title || "Untitled conversation"}"? This cannot be undone - its entire message history is erased.`,
      )
    ) {
      return;
    }
    try {
      await hardDeleteConversation(conversationsURL, c.run_id);
      refresh();
    } catch (err) {
      fail(err);
    }
  }

  async function cloneConversationRow(c: Conversation) {
    setCloning(c.run_id);
    try {
      // ADR-0527 clause 4: the copy stays in the source's project and the
      // cloner owns it, so they can write to it immediately - open it right
      // away rather than leaving them to find it in the refreshed list.
      const clone = await cloneConversation(conversationsURL, c.run_id);
      refresh();
      onOpenConversation({
        run_id: clone.run_id,
        title: clone.title,
        updated_at: new Date().toISOString(),
        starred: false,
        project_id: clone.project_id || null,
        role: "write",
      });
    } catch (err) {
      fail(err);
    } finally {
      setCloning(null);
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
      fail(err);
    }
  }

  // ADR-0515: manual drag-reorder, disabled while a search filter is active
  // (reordering a filtered subset against the full list's positions is
  // ambiguous). ADR-0527 narrows it further, per row: conversations.sort_order
  // is a single shared column, so reordering a colleague's conversation in a
  // shared project would move it in THEIR list too. A per-subject ordering
  // table is deliberately out of scope for WP-089.
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
      fail(err);
      refresh();
    });
  }

  const needle = search.trim().toLowerCase();
  const matching = (conversations ?? []).filter((c) => c.title.toLowerCase().includes(needle));
  const looseConversations = matching.filter((c) => c.project_id === null);
  const visibleProjects = (projects ?? []).filter(
    (p) =>
      needle === "" ||
      p.title.toLowerCase().includes(needle) ||
      matching.some((c) => c.project_id === p.project_id),
  );

  function toggleProject(projectId: string) {
    setExpandedProjects((current) => {
      const next = new Set(current);
      if (next.has(projectId)) {
        next.delete(projectId);
      } else {
        next.add(projectId);
      }
      return next;
    });
  }

  function renderConversation(c: Conversation, indent: boolean) {
    return (
      <ConversationRow
        key={c.run_id}
        conversation={c}
        indent={indent}
        isActive={c.run_id === activeRunId}
        dragEnabled={dragEnabled && c.project_id === null}
        isDragged={draggedRunId === c.run_id}
        isRenaming={renamingRunId === c.run_id}
        renameValue={renameValue}
        isCloning={cloning === c.run_id}
        onRenameValueChange={setRenameValue}
        onCommitRename={() => void commitRename(c.run_id, renameValue)}
        onCancelRename={() => setRenamingRunId(null)}
        onStartRename={() => {
          setRenamingRunId(c.run_id);
          setRenameValue(c.title);
        }}
        onOpen={() => onOpenConversation(c)}
        onToggleStar={() => void toggleStar(c)}
        onClone={() => void cloneConversationRow(c)}
        onDelete={() => void deleteConversationRow(c)}
        onHardDelete={() => void hardDeleteConversationRow(c)}
        onDragStart={() => setDraggedRunId(c.run_id)}
        onDrop={() => handleDrop(c.run_id)}
      />
    );
  }

  function blockHeader(
    label: string,
    expanded: boolean,
    onToggle: () => void,
    onAdd: () => void,
    addLabel: string,
  ) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
        <Button
          variant="plain"
          aria-label={expanded ? `Collapse all ${label.toLowerCase()}` : `Expand all ${label.toLowerCase()}`}
          aria-expanded={expanded}
          onClick={onToggle}
          style={{ padding: "0 0.125rem" }}
        >
          <FolderIcon />
        </Button>
        <span
          style={{
            flex: 1,
            fontSize: "0.75rem",
            letterSpacing: "0.05em",
            textTransform: "uppercase",
            color: "var(--pf-t--global--text--color--subtle)",
          }}
        >
          {label}
        </span>
        <Button variant="plain" aria-label={addLabel} onClick={onAdd} style={{ padding: "0 0.25rem" }}>
          <PlusIcon />
        </Button>
        <Button
          variant="plain"
          aria-hidden="true"
          tabIndex={-1}
          onClick={onToggle}
          style={{ padding: "0 0.125rem" }}
        >
          {expanded ? <AngleDownIcon /> : <AngleRightIcon />}
        </Button>
      </div>
    );
  }

  const loading = conversations === null || projects === null;

  return (
    <PageSidebar style={{ position: "relative" }}>
      <ResizeHandle width={width} onWidthChange={onWidthChange} />
      <PageSidebarBody>
        <div
          style={{
            padding: "1rem",
            display: "flex",
            flexDirection: "column",
            gap: "0.75rem",
            height: "100%",
          }}
        >
          <TextInput
            aria-label="Search projects and conversations"
            placeholder="Search…"
            value={search}
            onChange={(_e, value) => setSearch(value)}
          />
          {error && (
            <div
              style={{ color: "var(--pf-t--global--color--status--danger--100)", fontSize: "0.875rem" }}
            >
              {error}
            </div>
          )}
          {loading && !error ? (
            <Spinner size="md" aria-label="Loading projects and conversations" />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", overflowY: "auto" }}>
              {blockHeader(
                "Projects",
                projectsExpanded,
                () => setProjectsExpanded((v) => !v),
                () => setDialogProjectId(null),
                "New project",
              )}
              {projectsExpanded &&
                (visibleProjects.length === 0 ? (
                  <div
                    style={{
                      fontSize: "0.875rem",
                      color: "var(--pf-t--global--text--color--subtle)",
                      padding: "0 0.5rem",
                    }}
                  >
                    No projects yet.
                  </div>
                ) : (
                  visibleProjects.map((p) => (
                    <div key={p.project_id}>
                      <ProjectRow
                        project={p}
                        expanded={expandedProjects.has(p.project_id)}
                        onToggleExpanded={() => toggleProject(p.project_id)}
                        onOpenDialog={() => setDialogProjectId(p.project_id)}
                        onNewConversation={() => onNewConversation(p.project_id)}
                      />
                      {expandedProjects.has(p.project_id) &&
                        matching
                          .filter((c) => c.project_id === p.project_id)
                          .map((c) => renderConversation(c, true))}
                    </div>
                  ))
                ))}

              <Divider />

              {blockHeader(
                "Conversations",
                conversationsExpanded,
                () => setConversationsExpanded((v) => !v),
                () => onNewConversation(),
                "New conversation",
              )}
              {conversationsExpanded &&
                (looseConversations.length === 0 ? (
                  <EmptyState titleText="No conversations yet" headingLevel="h3">
                    <EmptyStateBody>Start a new conversation to see it here.</EmptyStateBody>
                  </EmptyState>
                ) : (
                  looseConversations.map((c) => renderConversation(c, false))
                ))}
            </div>
          )}
        </div>
      </PageSidebarBody>
      {dialogProjectId !== undefined && (
        <ProjectDialog
          isOpen
          onClose={() => setDialogProjectId(undefined)}
          onSaved={refresh}
          projectsURL={projectsURL}
          colleaguesURL={colleaguesURL}
          groupsURL={groupsURL}
          projectId={dialogProjectId}
        />
      )}
    </PageSidebar>
  );
}

// Which projects are unfolded, persisted the same local-only way ADR-0212
// persists the sidebar width - a view preference, never synced.
const _EXPANDED_KEY = "zuno.projects.expanded";

function loadExpanded(): Set<string> {
  try {
    const raw = window.localStorage.getItem(_EXPANDED_KEY);
    return new Set(raw ? (JSON.parse(raw) as string[]) : []);
  } catch {
    return new Set();
  }
}

function persistExpanded(expanded: Set<string>) {
  try {
    window.localStorage.setItem(_EXPANDED_KEY, JSON.stringify([...expanded]));
  } catch {
    // A blocked/full localStorage must never break the sidebar.
  }
}
