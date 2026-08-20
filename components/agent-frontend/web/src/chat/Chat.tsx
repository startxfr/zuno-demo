import * as React from "react";
import {
  Alert,
  Brand,
  Button,
  Content,
  ContentVariants,
  EmptyState,
  EmptyStateBody,
  Form,
  Label,
  Masthead,
  MastheadBrand,
  MastheadContent,
  MastheadMain,
  Page,
  PageSection,
  Spinner,
  TextArea,
  Toolbar,
  ToolbarContent,
  ToolbarGroup,
  ToolbarItem,
} from "@patternfly/react-core";
import { Flex, FlexItem } from "@patternfly/react-core";
import logoPlaceholder from "../assets/logo-placeholder.svg";
import type { ChatConfig } from "../shared/types";
import { ConversationList } from "../shared/ConversationList";
import { getTranscript } from "../shared/conversations";
import { Footer } from "../shared/Footer";
import { SSEParser } from "../shared/sse";
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

// Renders the Tekos chat UI (ADR-0044) and drives the end-to-end SSE
// stream (ADR-0045): fetch() -> this frontend's /api/chat -> agent-bff ->
// agent-runtime, with `token`/`tool`/`done`/`error` frames from
// components/agent-runtime/app/main.py:_sse relayed unmodified through
// every hop and rendered here as they arrive.
export function Chat({ config }: { config: ChatConfig }): React.ReactElement {
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [input, setInput] = React.useState("");
  const [sending, setSending] = React.useState(false);
  const [toolStatus, setToolStatus] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const abortRef = React.useRef<AbortController | null>(null);
  const logRef = React.useRef<HTMLDivElement | null>(null);
  // session_id (ADR-0045) is a per-page-load tracing/correlation id,
  // unrelated to run_id below - the backend still requires it on every
  // request regardless of whether this turn starts or resumes a
  // conversation.
  const sessionId = React.useRef(`sess-${Math.random().toString(36).slice(2)}-${Date.now()}`);
  // ADR-0212: identifies the conversation - null until either seeded from
  // a `?run_id=` URL param (a reopened conversation, below) or captured
  // from the SSE "start" event on this tab's first message (a brand new
  // one).
  const [runId, setRunId] = React.useState<string | null>(null);
  const [loadingHistory, setLoadingHistory] = React.useState(false);
  // Bumped whenever this tab's own action should be reflected in the left
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

  React.useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [messages, toolStatus]);

  // ADR-0212: the frontend half of ADR-0103's resume contract, exercised
  // end to end for the first time - seeded from a `?run_id=` query
  // parameter (set either by shared/tabTracker.ts's window.open or by
  // this same effect's own history.replaceState below on a fresh
  // conversation's first reply), fetching the exact prior message
  // history rather than starting empty.
  React.useEffect(() => {
    const seeded = new URLSearchParams(window.location.search).get("run_id");
    if (!seeded) {
      return;
    }
    setRunId(seeded);
    setLoadingHistory(true);
    getTranscript(config.conversationsURL, seeded)
      .then((turns) => {
        setMessages(
          turns.map((t) => ({
            id: newId(),
            role: t.role === "user" ? "user" : "agent",
            content: t.content,
            images: t.images,
          })),
        );
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => setLoadingHistory(false));
    // Intentionally run once on mount only - run_id is captured into
    // state above and driven by the SSE "start" event thereafter, not by
    // watching the URL.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function updateMessage(id: string, patch: Partial<ChatMessage>) {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, ...patch } : m)));
  }

  async function send() {
    const text = input.trim();
    if (!text || sending) {
      return;
    }
    setError(null);
    setInput("");
    setSending(true);
    setToolStatus(null);

    setMessages((prev) => [...prev, { id: newId(), role: "user", content: text }]);
    const agentMessageId = newId();
    setMessages((prev) => [...prev, { id: agentMessageId, role: "agent", content: "", pending: true }]);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const resp = await fetch(config.apiURL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({
          session_id: sessionId.current,
          message: text,
          run_id: runId ?? undefined,
        }),
        signal: controller.signal,
      });

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
            setRunId(data.run_id);
            setConversationsRefreshToken((n) => n + 1);
            // A brand new conversation's first reply: the URL had no
            // run_id yet, so a refresh (or copy-pasting the link) would
            // otherwise lose it - matches what a reopened conversation's
            // ?run_id= already provides.
            const url = new URL(window.location.href);
            if (url.searchParams.get("run_id") !== data.run_id) {
              url.searchParams.set("run_id", data.run_id);
              window.history.replaceState(null, "", url.toString());
            }
            // eslint-disable-next-line no-console
            console.debug("zuno chat request_id", data.request_id);
          } else if (evt.event === "tool") {
            const data = JSON.parse(evt.data) as ToolEventData;
            setToolStatus(data.status === "started" ? `Using ${data.name}…` : null);
          } else if (evt.event === "token") {
            const data = JSON.parse(evt.data) as { delta: string };
            accumulated += data.delta;
            updateMessage(agentMessageId, { content: accumulated, pending: true });
          } else if (evt.event === "done") {
            const data = JSON.parse(evt.data) as DoneEventData;
            citations = data.citations;
            images = data.images;
            setToolStatus(null);
          } else if (evt.event === "error") {
            const data = JSON.parse(evt.data) as ErrorEventData;
            throw new Error(data.message);
          }
        }
      }

      updateMessage(agentMessageId, {
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
      updateMessage(agentMessageId, { content: message, role: "error", pending: false });
      setError(message);
      setToolStatus(null);
    } finally {
      setSending(false);
      abortRef.current = null;
    }
  }

  function stop() {
    abortRef.current?.abort();
  }

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
          agent={config.displayName}
          conversationsURL={config.conversationsURL}
          chatURL={window.location.pathname}
          activeRunId={runId}
          refreshSignal={conversationsRefreshToken}
          width={sidebarWidth}
          onWidthChange={handleSidebarWidthChange}
        />
      }
      masthead={masthead}
    >
      <PageSection isFilled aria-label="Chat transcript">
        <div ref={logRef} style={{ height: "100%", overflowY: "auto" }}>
          {loadingHistory ? (
            <EmptyState titleText="Loading conversation…" headingLevel="h2">
              <EmptyStateBody>
                <Spinner size="lg" aria-label="Loading conversation history" />
              </EmptyStateBody>
            </EmptyState>
          ) : messages.length === 0 ? (
            <EmptyState titleText="Ask a technical question" headingLevel="h2">
              <EmptyStateBody>
                {config.displayName} answers from Zuno's technical documentation and, when relevant,
                live Confluence search.
              </EmptyStateBody>
            </EmptyState>
          ) : (
            <Flex direction={{ default: "column" }} gap={{ default: "gapMd" }}>
              {messages.map((m) => (
                <FlexItem key={m.id} alignSelf={{ default: m.role === "user" ? "alignSelfFlexEnd" : "alignSelfFlexStart" }}>
                  <MessageBubble message={m} />
                </FlexItem>
              ))}
              {toolStatus && (
                <FlexItem>
                  <Content component={ContentVariants.small}>
                    <Spinner size="sm" isInline aria-label="Tool call in progress" /> {toolStatus}
                  </Content>
                </FlexItem>
              )}
            </Flex>
          )}
        </div>
      </PageSection>
      <PageSection stickyOnBreakpoint={{ default: "bottom" }}>
        {error && (
          <Alert variant="danger" isInline title="Something went wrong" style={{ marginBottom: "1rem" }}>
            {error}
          </Alert>
        )}
        <Form
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          <Flex alignItems={{ default: "alignItemsFlexEnd" }} gap={{ default: "gapSm" }}>
            <FlexItem grow={{ default: "grow" }}>
              <TextArea
                aria-label="Ask a technical question"
                placeholder="Ask a technical question…"
                value={input}
                onChange={(_e, value) => setInput(value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void send();
                  }
                }}
                autoResize
                isDisabled={sending}
                rows={1}
              />
            </FlexItem>
            <FlexItem>
              {sending ? (
                <Button variant="secondary" onClick={stop}>
                  Stop
                </Button>
              ) : (
                <Button variant="primary" type="submit" isDisabled={!input.trim()}>
                  Send
                </Button>
              )}
            </FlexItem>
          </Flex>
        </Form>
      </PageSection>
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
