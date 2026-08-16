import * as React from "react";
import {
  Alert,
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
  ToolbarItem,
} from "@patternfly/react-core";
import { Flex, FlexItem } from "@patternfly/react-core";
import type { ChatConfig } from "../shared/types";
import { SSEParser } from "../shared/sse";
import { UserMenu } from "../shared/UserMenu";
import type {
  ChatMessage,
  Citation,
  DoneEventData,
  ErrorEventData,
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
  const sessionId = React.useRef(`sess-${Math.random().toString(36).slice(2)}-${Date.now()}`);

  React.useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [messages, toolStatus]);

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
        body: JSON.stringify({ session_id: sessionId.current, message: text }),
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

  return (
    <Page
      masthead={
        <Masthead>
          <MastheadMain>
            <MastheadBrand>
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
                <ToolbarItem>
                  <UserMenu
                    userDisplayName={config.userDisplayName}
                    profileURL={config.profileURL}
                    logoutURL={config.logoutURL}
                  />
                </ToolbarItem>
              </ToolbarContent>
            </Toolbar>
          </MastheadContent>
        </Masthead>
      }
    >
      <PageSection isFilled aria-label="Chat transcript">
        <div ref={logRef} style={{ height: "100%", overflowY: "auto" }}>
          {messages.length === 0 ? (
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
