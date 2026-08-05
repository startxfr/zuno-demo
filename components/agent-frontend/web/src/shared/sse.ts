// Browser-side half of the text/event-stream framing produced by
// components/agent-runtime/app/main.py:_sse and relayed byte-for-byte
// through components/agent-bff and this frontend's own /api/chat proxy
// (ADR-0045: SSE end to end). fetch()+ReadableStream is used instead of
// EventSource because the chat call is a POST with a JSON body and a
// same-origin session cookie, not a plain GET EventSource can express.
export interface SSEEvent {
  event: string;
  data: string;
}

export class SSEParser {
  private buffer = "";

  // Feeds one decoded chunk of the response body and returns any complete
  // frames it completed (a frame is terminated by a blank line, per the
  // SSE spec - see the second event: https://html.spec.whatwg.org/#server-sent-events).
  push(chunk: string): SSEEvent[] {
    this.buffer += chunk;
    const events: SSEEvent[] = [];
    let sepIndex = this.buffer.indexOf("\n\n");
    while (sepIndex !== -1) {
      const frame = this.buffer.slice(0, sepIndex);
      this.buffer = this.buffer.slice(sepIndex + 2);

      let eventName = "message";
      const dataLines: string[] = [];
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) {
          eventName = line.slice("event:".length).trim();
        } else if (line.startsWith("data:")) {
          dataLines.push(line.slice("data:".length).trim());
        }
      }
      if (dataLines.length > 0) {
        events.push({ event: eventName, data: dataLines.join("\n") });
      }

      sepIndex = this.buffer.indexOf("\n\n");
    }
    return events;
  }
}
