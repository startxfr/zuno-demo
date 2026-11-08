// Keyboard and mouse to control messages (ADR-0604 D4, §6.1).
//
// The browser samples at about 30 Hz; the runtime coalesces to the last value at each model step, so
// 30 Hz of input is not a 30 FPS promise. Key names are KeyboardEvent.code; the server maps them to
// the model's button ids and drops anything it does not know.

import { quantile } from "./video.ts";

const MOVE_KEYS = new Set([
  "KeyW", "KeyA", "KeyS", "KeyD", "Space", "ShiftLeft", "ShiftRight", "ControlLeft",
  "KeyE", "KeyQ", "KeyR", "KeyF", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
]);
const MOUSE_SENSITIVITY = 1 / 300; // 300 px of mouse movement is a full-scale look
const TICK_MS = 33;
const HEARTBEAT_MS = 10_000;

export class ControlSender {
  private pressed = new Set<string>();
  private lastSent = "";
  private dx = 0;
  private dy = 0;
  private seq = 0;
  private timer: number | undefined;
  private beat: number | undefined;
  private sentAt = new Map<number, number>();
  private samples: number[] = [];

  constructor(
    private ws: WebSocket,
    private canvas: HTMLCanvasElement,
    private onLatency: (p50: number, p95: number) => void,
  ) {}

  start(): void {
    window.addEventListener("keydown", this.keyDown);
    window.addEventListener("keyup", this.keyUp);
    window.addEventListener("blur", this.releaseAll);
    this.canvas.addEventListener("mousedown", this.mouseDown);
    window.addEventListener("mouseup", this.mouseUp);
    document.addEventListener("mousemove", this.mouseMove);
    this.timer = window.setInterval(this.tick, TICK_MS);
    // Keeps an attentive viewer's session alive; a hidden tab stops, and the idle timer ends it.
    this.beat = window.setInterval(() => {
      if (document.visibilityState === "visible" && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: "ping" }));
      }
    }, HEARTBEAT_MS);
  }

  stop(): void {
    window.removeEventListener("keydown", this.keyDown);
    window.removeEventListener("keyup", this.keyUp);
    window.removeEventListener("blur", this.releaseAll);
    this.canvas.removeEventListener("mousedown", this.mouseDown);
    window.removeEventListener("mouseup", this.mouseUp);
    document.removeEventListener("mousemove", this.mouseMove);
    window.clearInterval(this.timer);
    window.clearInterval(this.beat);
  }

  /** A frame that reflects control `seq` was displayed: the first one after an input closes its latency sample. */
  frameDisplayed(seq: number | null): void {
    if (seq === null || this.sentAt.size === 0) return;
    const now = performance.now();
    let worst = -1;
    for (const [n, t] of this.sentAt) {
      if (n <= seq) {
        worst = Math.max(worst, now - t);
        this.sentAt.delete(n);
      }
    }
    if (worst >= 0) {
      this.samples.push(worst);
      if (this.samples.length > 60) this.samples.shift();
      this.onLatency(quantile(this.samples, 0.5), quantile(this.samples, 0.95));
    }
  }

  latencySamples(): number[] {
    return this.samples;
  }

  private active(): boolean {
    return document.pointerLockElement === this.canvas || document.activeElement === this.canvas;
  }

  private keyDown = (e: KeyboardEvent): void => {
    if (!this.active() || !MOVE_KEYS.has(e.code)) return;
    e.preventDefault();
    this.pressed.add(e.code);
  };
  private keyUp = (e: KeyboardEvent): void => {
    if (MOVE_KEYS.has(e.code)) this.pressed.delete(e.code);
  };
  private mouseDown = (e: MouseEvent): void => {
    if (document.pointerLockElement !== this.canvas) {
      this.canvas.focus();
      void this.canvas.requestPointerLock?.();
      return;
    }
    this.pressed.add(`Mouse${e.button}`);
  };
  private mouseUp = (e: MouseEvent): void => {
    this.pressed.delete(`Mouse${e.button}`);
  };
  private mouseMove = (e: MouseEvent): void => {
    if (document.pointerLockElement !== this.canvas) return;
    this.dx += e.movementX * MOUSE_SENSITIVITY;
    this.dy += e.movementY * MOUSE_SENSITIVITY;
  };
  private releaseAll = (): void => {
    this.pressed.clear();
  };

  private tick = (): void => {
    if (this.ws.readyState !== WebSocket.OPEN) return;
    const keys = [...this.pressed].sort();
    const dx = Math.max(-1, Math.min(1, this.dx));
    const dy = Math.max(-1, Math.min(1, this.dy));
    this.dx = this.dy = 0;
    const signature = keys.join(",");
    const moved = dx !== 0 || dy !== 0;
    if (signature === this.lastSent && !moved) return;
    const changed = signature !== this.lastSent;
    this.lastSent = signature;
    const seq = ++this.seq;
    if (changed || moved) {
      this.sentAt.set(seq, performance.now());
      if (this.sentAt.size > 200) this.sentAt.delete(this.sentAt.keys().next().value as number);
    }
    this.ws.send(JSON.stringify({ type: "control", seq, keys, mouse: { dx, dy } }));
  };
}
