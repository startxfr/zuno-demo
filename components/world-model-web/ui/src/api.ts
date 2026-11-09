// REST client of world-model-web (ADR-0604 §6.1). Same origin: the oauth2-proxy session cookie authenticates it.

export interface Preset {
  id: string;
  title: string;
  description: string;
  prompt: string;
  has_image: boolean;
  event: { title: string; prompt: string } | null;
}

export interface Status {
  runtime_ready: boolean;
  busy: boolean;
  you_hold: boolean;
  enhancement: "on" | "off";
  limits: { idle_seconds: number; max_session_seconds: number; max_prompt_chars: number };
  engine?: string;
  image?: string;
  encoder?: string;
  precision?: string;
  last_step_ms?: number;
  holder?: string;
  holder_session_id?: string;
}

export interface PromptInfo {
  effective: string;
  original: string;
  enhancement: string; // "applied" or "off:<why>"
}

export interface SessionInfo {
  session_id: string;
  world_id: string;
  state: string;
  source: string;
  prompt_requested: number;
  prompt_applied: number;
  streaming: boolean;
  prompt: PromptInfo | null;
  preview_png_b64?: string | null;
}

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  get code(): string {
    const d = this.detail as { error?: string } | string;
    return typeof d === "object" && d !== null && d.error ? d.error : "";
  }
  get reason(): string {
    const d = this.detail as { reason?: string } | string;
    return typeof d === "object" && d !== null && d.reason ? d.reason : "";
  }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "same-origin",
  });
  if (res.status === 401) {
    // The front door's session ended: sign in again and come back.
    window.location.href = `/oauth2/start?rd=${encodeURIComponent(window.location.pathname)}`;
    throw new ApiError(401, "signing in again");
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown = text;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    /* keep the text */
  }
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail ?? data;
    throw new ApiError(res.status, detail);
  }
  return data as T;
}

export const api = {
  me: () => call<{ user: string; groups: string[]; ops: boolean; logout_url: string | null }>("GET", "/api/me"),
  presets: () => call<{ presets: Preset[] }>("GET", "/api/presets").then((r) => r.presets),
  status: () => call<Status>("GET", "/api/status"),
  createWorld: (body: { preset_id: string } | { prompt: string }) => call<SessionInfo>("POST", "/api/worlds", body),
  prompt: (sid: string, prompt: string) =>
    call<{ prompt_version: number; status: string; prompt: PromptInfo }>("POST", `/api/sessions/${sid}/prompts`, { prompt }),
  reset: (sid: string) => call<SessionInfo>("POST", `/api/sessions/${sid}/reset`),
  clientStats: (sid: string, stats: { fps?: number; latency_ms?: number }) =>
    call<void>("POST", `/api/sessions/${sid}/client-stats`, stats),
  release: (sid: string) => call<void>("DELETE", `/api/sessions/${sid}`),
};

export function streamUrl(sid: string): string {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/api/sessions/${sid}/stream`;
}
