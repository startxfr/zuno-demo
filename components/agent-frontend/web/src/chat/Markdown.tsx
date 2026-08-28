import * as React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Content } from "@patternfly/react-core";
import "./markdown.css";

// Agent replies are Markdown (agent-runtime emits it, and ADR-0045 carries it
// unchanged byte-for-byte through agent-bff and this frontend's own /api/chat
// proxy). Until this component existed, Chat.tsx rendered that string as a bare
// React text node, so readers saw literal `**bold**` and `- item`.
//
// react-markdown is deliberately preferred over marked/markdown-it + DOMPurify:
// it builds React elements directly and never produces an HTML string, so there
// is no dangerouslySetInnerHTML anywhere on this path, and no sanitizer whose
// configuration could be wrong. Raw HTML embedded in the Markdown is ignored by
// default.
//
// DO NOT add rehype-raw here. This text is written by an LLM whose context
// includes the RAG corpus (Confluence, Salesforce), so a <script> or an
// <img onerror=...> injected into an ingested document is a real path into this
// page, not a theoretical one. Rendering raw HTML would open it.
//
// GFM is the dialect LLMs actually emit: tables, strikethrough, task lists,
// autolinks. No syntax-highlighting plugin - highlight.js/shiki cost hundreds
// of kilobytes for a purely cosmetic gain.

// A message bubble is capped at 42rem. A wide table or a long unbroken line of
// code would push past that instead of scrolling inside it - these two are
// containment, not styling. Typography comes from pf-v6-c-content's descendant
// selectors (.pf-v6-c-content ul, ... h1, ... pre, ... blockquote); the only
// gap is table cells, handled in markdown.css - see the note there.
const scrollX: React.CSSProperties = { overflowX: "auto", maxWidth: "100%" };

const components = {
  // Every link in a reply points off this page (a citation, a Confluence
  // article): open it in a new tab, and deny it access to window.opener.
  a: ({ ...props }: React.ComponentPropsWithoutRef<"a">) => (
    <a {...props} target="_blank" rel="noopener noreferrer" />
  ),
  table: ({ ...props }: React.ComponentPropsWithoutRef<"table">) => (
    <div style={scrollX}>
      <table {...props} />
    </div>
  ),
  pre: ({ style, ...props }: React.ComponentPropsWithoutRef<"pre">) => (
    <pre {...props} style={{ ...style, ...scrollX }} />
  ),
};

function MarkdownContent({ content }: { content: string }): React.ReactElement {
  return (
    <Content className="zuno-md" style={{ minWidth: 0 }}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </Content>
  );
}

// A streaming reply re-parses on every token, which is unavoidable and cheap
// for a single bubble. memo keeps that cost to the one bubble that changed:
// React re-renders the whole transcript whenever any tab state moves (a
// keystroke in the composer included), and without this every settled message
// would be re-parsed alongside it.
export const Markdown = React.memo(MarkdownContent);
