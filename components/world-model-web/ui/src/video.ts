// The video path of the browser (ADR-0604 D4): binary messages from the session WebSocket,
// decoded by WebCodecs, drawn on a canvas. Pure helpers first (tested with node --test), then the player.

export interface VideoMessage {
  keyframe: boolean;
  ptsUs: number;
  seq: number | null; // the last control message the frame reflects, null before any
  data: Uint8Array; // one Annex-B access unit
}

export const HEADER_BYTES = 14; // 'V', flags, pts(8), seq(4)
const NO_SEQ = 0xffffffff;

/** Parse the runtime's binary video message; null when it is not one. */
export function parseVideoMessage(buf: ArrayBuffer): VideoMessage | null {
  if (buf.byteLength <= HEADER_BYTES) return null;
  const view = new DataView(buf);
  if (view.getUint8(0) !== 0x56 /* 'V' */) return null;
  const seq = view.getUint32(10);
  return {
    keyframe: (view.getUint8(1) & 1) === 1,
    ptsUs: Number(view.getBigUint64(2)),
    seq: seq === NO_SEQ ? null : seq,
    data: new Uint8Array(buf, HEADER_BYTES),
  };
}

/**
 * The WebCodecs codec string ("avc1.PPCCLL") read from the first SPS of an Annex-B access unit,
 * so the decoder is configured with what the encoder really produced. null when there is no SPS.
 */
export function codecFromAnnexB(data: Uint8Array): string | null {
  for (let i = 0; i + 6 < data.length; i++) {
    const startCode3 = data[i] === 0 && data[i + 1] === 0 && data[i + 2] === 1;
    if (!startCode3) continue;
    const nal = data[i + 3];
    if ((nal & 0x1f) === 7) {
      const hex = (n: number) => n.toString(16).padStart(2, "0");
      return `avc1.${hex(data[i + 4])}${hex(data[i + 5])}${hex(data[i + 6])}`;
    }
    i += 2;
  }
  return null;
}

/** Quantile of a list of numbers, 0 when empty. */
export function quantile(values: number[], q: number): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.floor(q * (sorted.length - 1) + 0.5))];
}

export interface PlayerEvents {
  onFrame: (seq: number | null) => void; // a frame was drawn
  onError: (message: string) => void;
}

/** Decodes the stream and paints the latest frame. Waits for a keyframe, asks for one after an error. */
export class VideoPlayer {
  private decoder: VideoDecoder | null = null;
  private codec: string | null = null;
  private needKey = true;
  private seqByTs = new Map<number, number | null>();
  private ctx: CanvasRenderingContext2D | null;

  constructor(private canvas: HTMLCanvasElement, private events: PlayerEvents, private requestKeyframe: () => void) {
    this.ctx = canvas.getContext("2d");
  }

  static supported(): boolean {
    return typeof VideoDecoder !== "undefined" && typeof EncodedVideoChunk !== "undefined";
  }

  push(buf: ArrayBuffer): void {
    const msg = parseVideoMessage(buf);
    if (!msg) return;
    if (msg.keyframe) {
      const codec = codecFromAnnexB(msg.data);
      if (codec && (codec !== this.codec || !this.decoder || this.decoder.state === "closed")) this.configure(codec);
      this.needKey = false;
    }
    if (this.needKey || !this.decoder || this.decoder.state !== "configured") return;
    if (this.decoder.decodeQueueSize > 8) {
      // The browser cannot keep up: drop until the next keyframe rather than add latency.
      this.needKey = true;
      this.requestKeyframe();
      return;
    }
    this.seqByTs.set(msg.ptsUs, msg.seq);
    if (this.seqByTs.size > 120) this.seqByTs.delete(this.seqByTs.keys().next().value as number);
    try {
      this.decoder.decode(new EncodedVideoChunk({ type: msg.keyframe ? "key" : "delta", timestamp: msg.ptsUs, data: msg.data }));
    } catch (e) {
      this.fail(e);
    }
  }

  private configure(codec: string): void {
    this.decoder?.close();
    this.codec = codec;
    this.decoder = new VideoDecoder({
      output: (frame) => {
        if (this.canvas.width !== frame.displayWidth) this.canvas.width = frame.displayWidth;
        if (this.canvas.height !== frame.displayHeight) this.canvas.height = frame.displayHeight;
        this.ctx?.drawImage(frame, 0, 0);
        const seq = this.seqByTs.get(frame.timestamp) ?? null;
        this.seqByTs.delete(frame.timestamp);
        frame.close();
        this.events.onFrame(seq);
      },
      error: (e) => this.fail(e),
    });
    // No `description`: the stream is Annex-B with the parameter sets repeated on every keyframe.
    this.decoder.configure({ codec, optimizeForLatency: true, hardwareAcceleration: "no-preference", avc: { format: "annexb" } } as VideoDecoderConfig);
  }

  private fail(e: unknown): void {
    this.events.onError(e instanceof Error ? e.message : String(e));
    this.needKey = true;
    this.codec = null; // reconfigure on the next keyframe
    this.requestKeyframe();
  }

  close(): void {
    if (this.decoder && this.decoder.state !== "closed") this.decoder.close();
    this.decoder = null;
  }
}
