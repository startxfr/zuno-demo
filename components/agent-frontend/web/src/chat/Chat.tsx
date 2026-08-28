import * as React from "react";
import {
  Alert,
  Brand,
  Button,
  Content,
  ContentVariants,
  EmptyState,
  EmptyStateBody,
  Flex,
  FlexItem,
  Form,
  Label,
  Masthead,
  MastheadBrand,
  MastheadContent,
  MastheadMain,
  Page,
  PageSection,
  Spinner,
  Tab,
  TabAction,
  Tabs,
  TabTitleText,
  TextArea,
  TextInput,
  Toolbar,
  ToolbarContent,
  ToolbarGroup,
  ToolbarItem,
} from "@patternfly/react-core";
import { StarIcon, TimesIcon } from "@patternfly/react-icons";
import logoPlaceholder from "../assets/logo-placeholder.svg";
import type { ChatConfig } from "../shared/types";
import { AGENT_ICONS } from "../shared/agentIcons";
import { ConversationList } from "../shared/ConversationList";
import {
  getTranscript,
  listConversations,
  renameConversation,
  type Conversation,
} from "../shared/conversations";
import { can, type ProjectRole } from "../shared/projects";
import { Footer } from "../shared/Footer";
import { SSEParser } from "../shared/sse";
import { openAgentTab } from "../shared/tabTracker";
import { UserMenu } from "../shared/UserMenu";
import type {
  ChatMessage,
  Citation,
  DoneEventData,
  ErrorEventData,
  ImageArtifact,
  StartEventData,
  ToolEventData,
} from "./types";

let nextId = 0;
function newId(): string {
  nextId += 1;
  return `msg-${nextId}`;
}

let nextTabId = 0;
function newTempTabId(): string {
  nextTabId += 1;
  return `new-${nextTabId}`;
}

function newSessionId(): string {
  return `sess-${Math.random().toString(36).slice(2)}-${Date.now()}`;
}

// Masthead nav buttons (below) are filled with each agent's own
// zuno.ui.color - most are dark/mid-tone enough for white text, but a
// bright one (e.g. Comage's amber #F0AB00) would wash white out, so pick
// black vs. white by standard sRGB relative luminance rather than
// hand-tuning per agent.
function textColorFor(hex: string): "#000000" | "#ffffff" {
  const match = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!match) {
    return "#ffffff";
  }
  const n = parseInt(match[1], 16);
  const r = (n >> 16) & 0xff;
  const g = (n >> 8) & 0xff;
  const b = n & 0xff;
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.55 ? "#000000" : "#ffffff";
}

// ADR-0515: one open in-app tab - each holds its own conversation
// independently (own run_id/transcript/composer state), superseding the
// single-conversation-per-page-load model. `id` is the run_id once known,
// or a client-only placeholder ("new-N") for a not-yet-started
// conversation - stable either way, so React keys and lookups never churn.
interface TabState {
  id: string;
  runId: string | null;
  title: string;
  starred: boolean;
  sessionId: string;
  messages: ChatMessage[];
  input: string;
  sending: boolean;
  toolStatus: string | null;
  loadingHistory: boolean;
  error: string | null;
  // ADR-0213: true when the last send() hit the single-active-writer
  // lease's 409 (another collaborator is currently writing) - the
  // composer disables and offers a retry instead of showing this as a
  // generic error, since it's an expected, transient contention state,
  // not a failure.
  busy: boolean;
  // ADR-0527: the project this conversation belongs to (null for a
  // project-less one), and the caller's effective right on it.
  projectId: string | null;
  // null only for a tab opened before the list resolved. `read` and `clone`
  // render the tab WITHOUT a composer - the server refuses their sends with
  // 403 anyway, so offering the box would only produce a confusing error.
  role: ProjectRole | null;
}

function newTab(opts: {
  runId: string | null;
  title?: string;
  starred?: boolean;
  input?: string;
  projectId?: string | null;
  role?: ProjectRole | null;
}): TabState {
  return {
    id: opts.runId ?? newTempTabId(),
    runId: opts.runId,
    title: opts.title ?? "",
    starred: opts.starred ?? false,
    sessionId: newSessionId(),
    messages: [],
    input: opts.input ?? "",
    sending: false,
    toolStatus: null,
    loadingHistory: opts.runId !== null,
    error: null,
    busy: false,
    projectId: opts.projectId ?? null,
    // A conversation you are creating is yours, so you may write to it.
    role: opts.role ?? "write",
  };
}

// Renders the Tekos chat UI (ADR-0044) and drives the end-to-end SSE
// stream (ADR-0045): fetch() -> this frontend's /api/chat -> agent-bff ->
// agent-runtime, with `token`/`tool`/`done`/`error` frames from
// components/agent-runtime/app/main.py:_sse relayed unmodified through
// every hop and rendered here as they arrive.
export function Chat({ config }: { config: ChatConfig }): React.ReactElement {
  const [tabs, setTabs] = React.useState<TabState[]>([]);
  const [activeTabId, setActiveTabId] = React.useState<string | null>(null);
  const abortRefs = React.useRef<Map<string, AbortController>>(new Map());
  const logRef = React.useRef<HTMLDivElement | null>(null);
  // Bumped whenever a tab's own action should be reflected in the left
  // panel (a new conversation appearing, a title changing) - the sidebar
  // has no other way to know, since this app has no shared store/context.
  const [conversationsRefreshToken, setConversationsRefreshToken] = React.useState(0);
  // ADR-0214 follow-up: the conversation sidebar's width, resizable via
  // shared/ConversationList.tsx's ResizeHandle - persisted so a reload
  // keeps the reader's preferred width.
  const [sidebarWidth, setSidebarWidth] = React.useState(() => {
    const saved = Number(window.localStorage.getItem("zuno.sidebarWidth"));
    return saved >= 220 && saved <= 600 ? saved : 320;
  });

  function handleSidebarWidthChange(width: number) {
    const clamped = Math.min(600, Math.max(220, width));
    setSidebarWidth(clamped);
    window.localStorage.setItem("zuno.sidebarWidth", String(clamped));
  }

  // Double-click-to-rename shortcut on the tab itself, alongside
  // ConversationList's kebab-menu rename (which stays the primary path
  // for tabs not currently open).
  const [renamingTabId, setRenamingTabId] = React.useState<string | null>(null);
  const [tabRenameValue, setTabRenameValue] = React.useState("");

  function startTabRename(tab: TabState) {
    if (!tab.runId) {
      return;
    }
    setRenamingTabId(tab.id);
    setTabRenameValue(tab.title);
  }

  async function commitTabRename(tab: TabState, title: string) {
    setRenamingTabId(null);
    const trimmed = title.trim();
    if (!trimmed || !tab.runId || trimmed === tab.title) {
      return;
    }
    updateTab(tab.id, (t) => ({ ...t, title: trimmed }));
    try {
      await renameConversation(config.conversationsURL, tab.runId, trimmed);
      setConversationsRefreshToken((n) => n + 1);
    } catch (err) {
      updateTab(tab.id, (t) => ({ ...t, error: err instanceof Error ? err.message : String(err) }));
    }
  }

  function updateTab(id: string, updater: (t: TabState) => TabState) {
    setTabs((prev) => prev.map((t) => (t.id === id ? updater(t) : t)));
  }

  function updateTabMessage(tabId: string, msgId: string, patch: Partial<ChatMessage>) {
    updateTab(tabId, (t) => ({
      ...t,
      messages: t.messages.map((m) => (m.id === msgId ? { ...m, ...patch } : m)),
    }));
  }

  function loadTranscriptInto(tabId: string, runId: string) {
    getTranscript(config.conversationsURL, runId)
      .then((turns) => {
        updateTab(tabId, (t) => ({
          ...t,
          messages: turns.map((turn) => ({
            id: newId(),
            role: turn.role === "user" ? "user" : "agent",
            content: turn.content,
            images: turn.images,
          })),
          loadingHistory: false,
        }));
      })
      .catch((err) => {
        updateTab(tabId, (t) => ({
          ...t,
          error: err instanceof Error ? err.message : String(err),
          loadingHistory: false,
        }));
      });
  }

  React.useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [tabs, activeTabId]);

  // ADR-0515 decision 3: first visit opens on the most recent conversation
  // if history exists (or a deep-linked ?run_id=, e.g. from the masthead
  // nav strip's tab-reuse reopening this agent's tab); otherwise the
  // "Create new chat" empty state renders instead (no tabs open at all).
  React.useEffect(() => {
    const seeded = new URLSearchParams(window.location.search).get("run_id");
    if (seeded) {
      const tab = newTab({ runId: seeded });
      setTabs([tab]);
      setActiveTabId(tab.id);
      loadTranscriptInto(tab.id, seeded);
      return;
    }
    listConversations(config.conversationsURL)
      .then((list) => {
        if (list.length === 0) {
          return;
        }
        // list_conversations' own default order (ADR-0515: the caller's
        // manual drag-reorder, "most recent" absent a manual reorder).
        const mostRecent = list[0];
        const tab = newTab({
          runId: mostRecent.run_id,
          title: mostRecent.title,
          starred: mostRecent.starred,
          projectId: mostRecent.project_id,
          role: mostRecent.role,
        });
        setTabs([tab]);
        setActiveTabId(tab.id);
        loadTranscriptInto(tab.id, mostRecent.run_id);
      })
      .catch(() => {
        // Best-effort - the empty state renders regardless of a listing
        // failure, same as before this ADR (no history = no error shown).
      });
    // Intentionally run once on mount only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keeps the URL's ?run_id= in sync with the ACTIVE tab only, so a
  // reload or a copy-pasted link reopens the same conversation - mirrors
  // what a reopened conversation's own seeded ?run_id= already provides.
  React.useEffect(() => {
    const active = tabs.find((t) => t.id === activeTabId);
    const desired = active?.runId ?? null;
    const url = new URL(window.location.href);
    const current = url.searchParams.get("run_id");
    if (current === desired) {
      return;
    }
    if (desired) {
      url.searchParams.set("run_id", desired);
    } else {
      url.searchParams.delete("run_id");
    }
    window.history.replaceState(null, "", url.toString());
  }, [activeTabId, tabs]);

  // ADR-0527: takes the whole Conversation rather than three positional
  // fields, because a tab now needs project_id and the caller's role to
  // decide read-only mode.
  function openConversation(c: Conversation) {
    const existing = tabs.find((t) => t.runId === c.run_id);
    if (existing) {
      setActiveTabId(existing.id);
      return;
    }
    const tab = newTab({
      runId: c.run_id,
      title: c.title,
      starred: c.starred,
      projectId: c.project_id,
      role: c.role,
    });
    setTabs((prev) => [...prev, tab]);
    setActiveTabId(tab.id);
    loadTranscriptInto(tab.id, c.run_id);
  }

  // projectId attaches the new conversation to a project (the "+" on a
  // project row). The server re-checks the caller holds `write` on it
  // before recording anything - this only carries the request.
  function openNewConversation(prefill = "", projectId: string | null = null) {
    const tab = newTab({ runId: null, input: prefill, projectId });
    setTabs((prev) => [...prev, tab]);
    setActiveTabId(tab.id);
  }

  function closeTab(id: string) {
    abortRefs.current.get(id)?.abort();
    abortRefs.current.delete(id);
    setTabs((prev) => {
      const idx = prev.findIndex((t) => t.id === id);
      const next = prev.filter((t) => t.id !== id);
      if (activeTabId === id) {
        const neighbor = next[idx] ?? next[idx - 1];
        setActiveTabId(neighbor ? neighbor.id : null);
      }
      return next;
    });
  }

  async function send(tab: TabState) {
    const text = tab.input.trim();
    if (!text || tab.sending) {
      return;
    }

    updateTab(tab.id, (t) => ({ ...t, input: "", sending: true, toolStatus: null, error: null, busy: false }));

    const userMessageId = newId();
    const agentMessageId = newId();
    updateTab(tab.id, (t) => ({
      ...t,
      messages: [
        ...t.messages,
        { id: userMessageId, role: "user", content: text },
        { id: agentMessageId, role: "agent", content: "", pending: true },
      ],
    }));

    const controller = new AbortController();
    abortRefs.current.set(tab.id, controller);

    try {
      const resp = await fetch(config.apiURL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({
          session_id: tab.sessionId,
          message: text,
          run_id: tab.runId ?? undefined,
          // ADR-0527: only meaningful when creating a conversation. On a
          // resume the server ignores it entirely (a conversation's project
          // is fixed at creation), so there is no reason to send it.
          project_id: tab.runId === null ? (tab.projectId ?? undefined) : undefined,
        }),
        signal: controller.signal,
      });

      if (resp.status === 409) {
        // ADR-0213: another collaborator currently holds the
        // single-active-writer lease - no turn was actually sent, so
        // drop the two placeholder messages just added and restore the
        // draft rather than showing this as a generic error.
        updateTab(tab.id, (t) => ({
          ...t,
          messages: t.messages.filter((m) => m.id !== userMessageId && m.id !== agentMessageId),
          input: text,
          busy: true,
        }));
        return;
      }

      if (!resp.ok || !resp.body) {
        const body = await resp.text().catch(() => "");
        let detail = body;
        try {
          detail = JSON.parse(body).error ?? body;
        } catch {
          // body wasn't JSON - use it verbatim
        }
        throw new Error(detail || `request failed with status ${resp.status}`);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      const parser = new SSEParser();
      let accumulated = "";
      let citations: Citation[] | undefined;
      let images: ImageArtifact[] | undefined;

      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }
        const events = parser.push(decoder.decode(value, { stream: true }));
        for (const evt of events) {
          if (evt.event === "start") {
            const data = JSON.parse(evt.data) as StartEventData;
            // ADR-0528: the start event now also carries the SERVER-RESOLVED
            // project, which is authoritative - a brand-new conversation's
            // requested project_id is only a request until the server has
            // checked the caller's grant on it.
            updateTab(tab.id, (t) => ({
              ...t,
              runId: data.run_id,
              projectId: data.project_id ? data.project_id : t.projectId,
            }));
            setConversationsRefreshToken((n) => n + 1);
            // eslint-disable-next-line no-console
            console.debug("zuno chat request_id", data.request_id);
          } else if (evt.event === "tool") {
            const data = JSON.parse(evt.data) as ToolEventData;
            updateTab(tab.id, (t) => ({ ...t, toolStatus: data.status === "started" ? `Using ${data.name}…` : null }));
          } else if (evt.event === "token") {
            const data = JSON.parse(evt.data) as { delta: string };
            accumulated += data.delta;
            updateTabMessage(tab.id, agentMessageId, { content: accumulated, pending: true });
          } else if (evt.event === "done") {
            const data = JSON.parse(evt.data) as DoneEventData;
            citations = data.citations;
            images = data.images;
            updateTab(tab.id, (t) => ({ ...t, toolStatus: null }));
          } else if (evt.event === "error") {
            const data = JSON.parse(evt.data) as ErrorEventData;
            throw new Error(data.message);
          }
        }
      }

      updateTabMessage(tab.id, agentMessageId, {
        content: accumulated || "(empty reply)",
        citations,
        images,
        pending: false,
      });
    } catch (err) {
      const message = controller.signal.aborted
        ? "Stopped."
        : err instanceof Error
          ? err.message
          : String(err);
      updateTabMessage(tab.id, agentMessageId, { content: message, role: "error", pending: false });
      updateTab(tab.id, (t) => ({ ...t, error: message, toolStatus: null }));
    } finally {
      updateTab(tab.id, (t) => ({ ...t, sending: false }));
      abortRefs.current.delete(tab.id);
    }
  }

  function stop(tabId: string) {
    abortRefs.current.get(tabId)?.abort();
  }

  // ADR-0515 decision 5: starred conversations sort left among open
  // in-app tabs - a stable sort so tabs otherwise keep their open order.
  const orderedTabs = React.useMemo(
    () => [...tabs].sort((a, b) => Number(b.starred) - Number(a.starred)),
    [tabs],
  );
  const activeTab = tabs.find((t) => t.id === activeTabId) ?? null;

  const masthead = (
    <Masthead>
      <MastheadMain>
        <MastheadBrand>
          <Brand src={logoPlaceholder} alt="Zuno" heights={{ default: "32px" }} style={{ marginRight: "0.75rem" }} />
          <Content component={ContentVariants.h1}>
            <a href={config.homeURL} style={{ color: "inherit", textDecoration: "none" }}>
              Zuno
            </a>{" "}
            / {config.displayName}
          </Content>
        </MastheadBrand>
      </MastheadMain>
      <MastheadContent>
        <Toolbar>
          <ToolbarContent>
            {config.agentNavStrip.length > 0 && (
              // ADR-0515: cross-agent nav - each link reuses/focuses that
              // agent's own browser tab (tabTracker.ts), never navigates
              // this tab away.
              <ToolbarGroup>
                {config.agentNavStrip.map((entry) => {
                  const isCurrent = entry.name === config.agentName;
                  const Icon = AGENT_ICONS[entry.icon];
                  return (
                    <ToolbarItem key={entry.name}>
                      <Button
                        variant="primary"
                        icon={Icon ? <Icon /> : undefined}
                        style={
                          entry.color
                            ? isCurrent
                              ? ({
                                  backgroundColor: entry.color,
                                  borderColor: entry.color,
                                  color: textColorFor(entry.color),
                                  "--pf-v6-c-button__icon--Color": textColorFor(entry.color),
                                } as React.CSSProperties)
                              : ({
                                  backgroundColor: "transparent",
                                  borderWidth: "0 0 2px 0",
                                  borderStyle: "solid",
                                  borderColor: entry.color,
                                  borderRadius: 0,
                                  color: entry.color,
                                  "--pf-v6-c-button__icon--Color": entry.color,
                                } as React.CSSProperties)
                            : undefined
                        }
                        onClick={(e) => {
                          e.preventDefault();
                          openAgentTab(entry.name, entry.href);
                        }}
                      >
                        {entry.displayName}
                      </Button>
                    </ToolbarItem>
                  );
                })}
              </ToolbarGroup>
            )}
            <ToolbarGroup align={{ default: "alignEnd" }}>
              <ToolbarItem>
                <UserMenu
                  userDisplayName={config.userDisplayName}
                  profileURL={config.profileURL}
                  logoutURL={config.logoutURL}
                />
              </ToolbarItem>
            </ToolbarGroup>
          </ToolbarContent>
        </Toolbar>
      </MastheadContent>
    </Masthead>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
    <Page
      style={
        {
          flex: "1 1 auto",
          minHeight: 0,
          // ADR-0214 follow-up: PageSidebar's width is fixed by this CSS
          // custom property (no width prop of its own) - overriding it
          // here is what shared/ConversationList.tsx's ResizeHandle
          // actually drives. Tried PatternFly's Drawer/isResizable engine
          // first; reverted after confirming live it silently narrows the
          // masthead to the content area only (Page's masthead spans the
          // full width, over both the sidebar and main content, only
          // while the sidebar stays in Page's own `sidebar` slot).
          "--pf-v6-c-page__sidebar--Width": `${sidebarWidth}px`,
          "--pf-v6-c-page__sidebar--xl--Width": `${sidebarWidth}px`,
        } as React.CSSProperties
      }
      sidebar={
        <ConversationList
          conversationsURL={config.conversationsURL}
          projectsURL={config.projectsURL}
          colleaguesURL={config.colleaguesURL}
          groupsURL={config.groupsURL}
          subject={config.subject}
          userDisplayName={config.userDisplayName}
          activeRunId={activeTab?.runId ?? null}
          refreshSignal={conversationsRefreshToken}
          width={sidebarWidth}
          onWidthChange={handleSidebarWidthChange}
          onOpenConversation={openConversation}
          onNewConversation={(projectId) => openNewConversation("", projectId ?? null)}
        />
      }
      masthead={masthead}
    >
      {orderedTabs.length > 0 && (
        <PageSection type="tabs" stickyOnBreakpoint={{ default: "top" }}>
          <Tabs
            activeKey={activeTabId ?? undefined}
            onSelect={(_e, key) => setActiveTabId(String(key))}
            aria-label="Open conversations"
          >
            {orderedTabs.map((tab) => (
              <Tab
                key={tab.id}
                eventKey={tab.id}
                title={
                  renamingTabId === tab.id ? (
                    <TextInput
                      aria-label="Rename conversation"
                      autoFocus
                      value={tabRenameValue}
                      onChange={(_e, value) => setTabRenameValue(value)}
                      onClick={(e) => e.stopPropagation()}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") void commitTabRename(tab, tabRenameValue);
                        if (e.key === "Escape") setRenamingTabId(null);
                      }}
                      onBlur={() => void commitTabRename(tab, tabRenameValue)}
                    />
                  ) : (
                    <TabTitleText onDoubleClick={() => startTabRename(tab)}>
                      {tab.starred && (
                        <span
                          aria-label="Starred"
                          style={{ display: "inline-flex", marginRight: "0.375rem", color: "var(--pf-t--global--icon--color--favorite--default)" }}
                        >
                          <StarIcon />
                        </span>
                      )}
                      {tab.sending && (
                        <span style={{ display: "inline-flex", marginRight: "0.375rem" }}>
                          <Spinner size="sm" aria-label="Thinking" />
                        </span>
                      )}
                      {tab.title || "New conversation"}
                    </TabTitleText>
                  )
                }
                actions={
                  <TabAction
                    onClick={(e) => {
                      e.stopPropagation();
                      closeTab(tab.id);
                    }}
                    aria-label={`Close ${tab.title || "New conversation"}`}
                  >
                    <TimesIcon />
                  </TabAction>
                }
              />
            ))}
          </Tabs>
        </PageSection>
      )}
      {activeTab === null ? (
        <PageSection isFilled aria-label="Create new chat">
          <EmptyState titleText="Create new chat" headingLevel="h2">
            <EmptyStateBody>
              {(config.promptExamples ?? []).length > 0 ? (
                <Flex direction={{ default: "column" }} alignItems={{ default: "alignItemsCenter" }} gap={{ default: "gapSm" }}>
                  {(config.promptExamples ?? []).map((example) => (
                    <FlexItem key={example}>
                      <Button variant="secondary" onClick={() => openNewConversation(example)}>
                        {example}
                      </Button>
                    </FlexItem>
                  ))}
                </Flex>
              ) : (
                <>Start a new conversation to begin.</>
              )}
            </EmptyStateBody>
            <Button variant="primary" onClick={() => openNewConversation()}>
              New conversation
            </Button>
          </EmptyState>
        </PageSection>
      ) : (
        <>
          <PageSection isFilled aria-label="Chat transcript">
            <div ref={logRef} style={{ height: "100%", overflowY: "auto" }}>
              {activeTab.loadingHistory ? (
                <EmptyState titleText="Loading conversation…" headingLevel="h2">
                  <EmptyStateBody>
                    <Spinner size="lg" aria-label="Loading conversation history" />
                  </EmptyStateBody>
                </EmptyState>
              ) : activeTab.messages.length === 0 ? (
                <EmptyState titleText="Ask a technical question" headingLevel="h2">
                  <EmptyStateBody>
                    {config.displayName} answers from Zuno's technical documentation and, when relevant,
                    live Confluence search.
                  </EmptyStateBody>
                </EmptyState>
              ) : (
                <Flex direction={{ default: "column" }} gap={{ default: "gapMd" }}>
                  {activeTab.messages.map((m) => (
                    <FlexItem key={m.id} alignSelf={{ default: m.role === "user" ? "alignSelfFlexEnd" : "alignSelfFlexStart" }}>
                      <MessageBubble message={m} />
                    </FlexItem>
                  ))}
                  {activeTab.toolStatus && (
                    <FlexItem>
                      <Content component={ContentVariants.small}>
                        <Spinner size="sm" isInline aria-label="Tool call in progress" /> {activeTab.toolStatus}
                      </Content>
                    </FlexItem>
                  )}
                </Flex>
              )}
            </div>
          </PageSection>
          <PageSection stickyOnBreakpoint={{ default: "bottom" }}>
            {activeTab.error && (
              <Alert variant="danger" isInline title="Something went wrong" style={{ marginBottom: "1rem" }}>
                {activeTab.error}
              </Alert>
            )}
            {activeTab.busy && (
              // ADR-0213: another collaborator holds the write lease -
              // expected, transient contention, not a failure. The lease
              // is short (30s), so a plain retry (clearing busy so the
              // composer re-enables) is the whole recovery flow.
              <Alert
                variant="info"
                isInline
                title="Someone else is currently writing to this conversation"
                style={{ marginBottom: "1rem" }}
                actionLinks={
                  <Button variant="link" isInline onClick={() => updateTab(activeTab.id, (t) => ({ ...t, busy: false }))}>
                    Retry
                  </Button>
                }
              >
                Your message wasn&rsquo;t sent. Try again in a moment.
              </Alert>
            )}
            {activeTab.role !== null && !can(activeTab.role, "write") ? (
              // ADR-0527 clause 9: a read-only tab hides the composer
              // entirely rather than disabling it. The server refuses these
              // roles' sends with 403 anyway, so offering a box that always
              // fails would teach the user nothing. Same inline-Alert shape
              // as the lease-contention state just above, which is the
              // precedent this codebase already set for "you cannot write
              // right now, and here is why".
              <Alert
                variant="info"
                isInline
                isPlain
                title={
                  activeTab.role === "read"
                    ? "You have read-only access to this project"
                    : "You can read and clone this conversation, but not send messages"
                }
                style={{ marginBottom: "1rem" }}
              >
                {activeTab.role === "clone"
                  ? "Clone it from the sidebar to continue in a copy of your own."
                  : "Ask a project admin for the write role if you need to take part."}
              </Alert>
            ) : (
            <Form
              onSubmit={(e) => {
                e.preventDefault();
                void send(activeTab);
              }}
            >
              <Flex alignItems={{ default: "alignItemsFlexEnd" }} gap={{ default: "gapSm" }}>
                <FlexItem grow={{ default: "grow" }}>
                  <TextArea
                    aria-label="Ask a technical question"
                    placeholder="Ask a technical question…"
                    value={activeTab.input}
                    onChange={(_e, value) => updateTab(activeTab.id, (t) => ({ ...t, input: value, busy: false }))}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        void send(activeTab);
                      }
                    }}
                    autoResize
                    isDisabled={activeTab.sending || activeTab.busy}
                    rows={1}
                  />
                </FlexItem>
                <FlexItem>
                  {activeTab.sending ? (
                    <Button variant="secondary" onClick={() => stop(activeTab.id)}>
                      Stop
                    </Button>
                  ) : (
                    <Button variant="primary" type="submit" isDisabled={!activeTab.input.trim() || activeTab.busy}>
                      Send
                    </Button>
                  )}
                </FlexItem>
              </Flex>
            </Form>
            )}
          </PageSection>
        </>
      )}
    </Page>
    <Footer />
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }): React.ReactElement {
  return (
    <div
      style={{
        maxWidth: "42rem",
        padding: "0.5rem 1rem",
        borderRadius: "var(--pf-t--global--border-radius--medium, 4px)",
        background:
          message.role === "user"
            ? "var(--pf-t--global--color--brand--default)"
            : message.role === "error"
              ? "var(--pf-t--global--color--status--danger--100)"
              : "var(--pf-t--global--background--color--secondary--default)",
        color: message.role === "user" ? "var(--pf-t--global--text--color--inverse)" : undefined,
        whiteSpace: "pre-wrap",
      }}
    >
      {message.content}
      {message.pending && !message.content && <Spinner size="sm" isInline aria-label="Waiting for a reply" />}
      {message.images && message.images.length > 0 && (
        // ADR-0415: generated images render inline in this same bubble,
        // between the reply text above and the citations below - the
        // sidecar-field placement convention citations already
        // established, extended to a second sidecar field.
        <Flex direction={{ default: "column" }} gap={{ default: "gapSm" }} style={{ marginTop: "0.5rem" }}>
          {message.images.map((img, i) => (
            <FlexItem key={i}>
              <img
                src={`data:${img.mime_type};base64,${img.data_base64}`}
                alt={img.alt}
                style={{ maxWidth: "100%", borderRadius: "var(--pf-t--global--border-radius--medium, 4px)" }}
              />
            </FlexItem>
          ))}
        </Flex>
      )}
      {message.citations && message.citations.length > 0 && (
        <Flex gap={{ default: "gapXs" }} style={{ marginTop: "0.5rem" }}>
          {message.citations.map((c, i) => (
            <FlexItem key={`${c.source}-${i}`}>
              <Label color="blue" isCompact href={c.source}>
                {c.title || c.source}
              </Label>
            </FlexItem>
          ))}
        </Flex>
      )}
    </div>
  );
}
