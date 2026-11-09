import { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert, Button, Card, CardBody, CardTitle, Content, DescriptionList, DescriptionListDescription,
  DescriptionListGroup, DescriptionListTerm, ExpandableSection, Flex, FlexItem, Grid, GridItem, Label,
  Masthead, MastheadBrand, MastheadContent, MastheadMain, Page, PageSection, Spinner, TextArea,
} from "@patternfly/react-core";
import { ApiError, Preset, SessionInfo, Status, api, streamUrl } from "./api.ts";
import { ControlSender } from "./controls.ts";
import { VideoPlayer, quantile } from "./video.ts";

type RuntimeEvent =
  | { type: "state"; state: string; engine?: string; image?: string; encoder?: string; precision?: string; message?: string; reason?: string }
  | { type: "stats"; step_ms: number; engine_fps: number }
  | { type: "prompt"; prompt_version: number; status: string; apply_ms?: number; message?: string };

const STATE_LABEL: Record<string, { text: string; color: "green" | "blue" | "red" | "grey" | "orange" }> = {
  PREPARING_IMAGE: { text: "Creating the first image", color: "blue" },
  READY: { text: "Ready", color: "grey" },
  STREAMING: { text: "Live", color: "green" },
  RECONDITIONING: { text: "Editing the world", color: "blue" },
  FAILED: { text: "Failed", color: "red" },
  CLOSED: { text: "Ended", color: "grey" },
};

function explain(e: unknown, maxChars: number): string {
  if (!(e instanceof ApiError)) return e instanceof Error ? e.message : String(e);
  if (e.status === 409) return "Another world is running on the GPU. Try again in a moment.";
  if (e.status === 422 && e.code === "prompt_refused") {
    const why: Record<string, string> = {
      deny_list: "This description is outside the content rules of the demo.",
      too_long: `This description is too long (at most ${maxChars} characters).`,
      empty: "Type a description first.",
      model_refused: "The safety check declined this description.",
    };
    return why[e.reason] ?? "This description was refused.";
  }
  if (e.status === 429) return "You started many worlds this hour. Try again later.";
  if (e.status === 503) return "The GPU runtime is not ready yet (models still loading). Try again in a minute.";
  if (e.status === 403) return "Your account is not allowed to open this demo.";
  return e.message;
}

export default function App() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const controlsRef = useRef<ControlSender | null>(null);
  const playerRef = useRef<VideoPlayer | null>(null);
  const frames = useRef(0);
  const intentionalClose = useRef(false);
  const sessionRef = useRef<SessionInfo | null>(null);

  const [me, setMe] = useState<{ user: string; ops: boolean } | null>(null);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [status, setStatus] = useState<Status | null>(null);
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ended, setEnded] = useState<string | null>(null);
  const [runtimeState, setRuntimeState] = useState("");
  // The runtime redraws the picture from the scene prompt every few seconds of walking (drift control).
  const [stabilizing, setStabilizing] = useState(false);
  const [hasFrame, setHasFrame] = useState(false);
  const [stats, setStats] = useState<{ step_ms: number; engine_fps: number } | null>(null);
  const [fps, setFps] = useState(0);
  const [latency, setLatency] = useState<{ p50: number; p95: number } | null>(null);
  const [promptText, setPromptText] = useState("");
  const [sceneText, setSceneText] = useState("");
  const [promptNote, setPromptNote] = useState<string | null>(null);
  const [applied, setApplied] = useState<{ version: number; ms?: number; status: string } | null>(null);
  const [live, setLive] = useState<{ encoder?: string; engine?: string; image?: string; precision?: string }>({});

  const maxChars = status?.limits.max_prompt_chars ?? 300;
  sessionRef.current = session;

  // ---- first load and status polling
  useEffect(() => {
    api.me().then(setMe).catch((e) => setError(explain(e, maxChars)));
    api.presets().then(setPresets).catch(() => setPresets([]));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const load = () => api.status().then(setStatus).catch(() => undefined);
    load();
    const id = window.setInterval(load, 4000);
    return () => window.clearInterval(id);
  }, []);

  // ---- displayed FPS, and what the browser measured, reported every 5 s while live
  useEffect(() => {
    let sum = 0;
    let count = 0;
    const id = window.setInterval(() => {
      const f = frames.current;
      frames.current = 0;
      setFps(f);
      if (f > 0 && sessionRef.current) {
        sum += f;
        count += 1;
        if (count >= 5) {
          const p50 = quantile(controlsRef.current?.latencySamples() ?? [], 0.5);
          void api.clientStats(sessionRef.current.session_id, {
            fps: Math.round((sum / count) * 10) / 10, ...(p50 > 0 ? { latency_ms: Math.round(p50) } : {}),
          }).catch(() => undefined);
          sum = count = 0;
        }
      }
    }, 1000);
    return () => window.clearInterval(id);
  }, []);

  // ---- the stream
  const closeStream = useCallback(() => {
    intentionalClose.current = true;
    controlsRef.current?.stop();
    playerRef.current?.close();
    wsRef.current?.close();
    controlsRef.current = playerRef.current = wsRef.current = null;
  }, []);
  useEffect(() => closeStream, [closeStream]);

  const handleEvent = useCallback((ev: RuntimeEvent) => {
    if (ev.type === "state") {
      setRuntimeState(ev.state);
      setStabilizing(ev.state === "RECONDITIONING" && ev.reason === "stabilize");
      setLive((l) => ({ ...l, ...(ev.encoder ? { encoder: ev.encoder, engine: ev.engine, image: ev.image, precision: ev.precision } : {}) }));
      if (ev.state === "FAILED") setEnded(ev.message ?? "The world failed.");
      if (ev.state === "CLOSED") setEnded(ev.message ?? "The session ended.");
    } else if (ev.type === "stats") {
      setStats({ step_ms: ev.step_ms, engine_fps: ev.engine_fps });
    } else if (ev.type === "prompt") {
      setApplied({ version: ev.prompt_version, ms: ev.apply_ms, status: ev.status });
    }
  }, []);

  const openStream = useCallback((sid: string) => {
    closeStream();
    intentionalClose.current = false;
    setHasFrame(false);
    setEnded(null);
    const canvas = canvasRef.current;
    if (!canvas) return;
    if (!VideoPlayer.supported()) {
      setEnded("This browser cannot decode the video (WebCodecs). Use a recent Chrome or Edge.");
      return;
    }
    const ws = new WebSocket(streamUrl(sid));
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;
    const player = new VideoPlayer(
      canvas,
      {
        onFrame: (seq) => {
          frames.current += 1;
          controlsRef.current?.frameDisplayed(seq);
          setHasFrame(true);
        },
        onError: (m) => setPromptNote(`Video decoder: ${m}`),
      },
      () => ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify({ type: "keyframe" })),
    );
    playerRef.current = player;
    const controls = new ControlSender(ws, canvas, (p50, p95) => setLatency({ p50, p95 }));
    controlsRef.current = controls;
    ws.onopen = () => controls.start();
    ws.onmessage = (m) => {
      if (typeof m.data === "string") handleEvent(JSON.parse(m.data) as RuntimeEvent);
      else player.push(m.data as ArrayBuffer);
    };
    ws.onclose = (ev) => {
      controls.stop();
      if (!intentionalClose.current) setEnded(`The stream closed (code ${ev.code}). Your world may have expired: start a new one.`);
    };
  }, [closeStream, handleEvent]);

  // ---- actions
  const start = async (body: { preset_id: string } | { prompt: string }) => {
    setError(null);
    setCreating(true);
    setStats(null);
    setLatency(null);
    setApplied(null);
    setPromptNote(null);
    try {
      const created = await api.createWorld(body);
      setSession(created);
      setRuntimeState("READY");
      openStream(created.session_id);
    } catch (e) {
      setError(explain(e, maxChars));
    } finally {
      setCreating(false);
    }
  };

  const changeWorld = async (text: string) => {
    if (!session) return;
    setError(null);
    setPromptNote(null);
    try {
      const r = await api.prompt(session.session_id, text);
      setApplied({ version: r.prompt_version, status: "requested" });
      setPromptNote(
        r.prompt.enhancement === "applied"
          ? `Sent as: "${r.prompt.effective}"`
          : `Enhancement is off (${r.prompt.enhancement.replace("off:", "")}); sent as typed.`,
      );
      setPromptText("");
    } catch (e) {
      setError(explain(e, maxChars));
    }
  };

  const resetWorld = async () => {
    if (!session) return;
    setError(null);
    setCreating(true);
    try {
      closeStream();
      const r = await api.reset(session.session_id);
      setSession({ ...session, ...r });
      setApplied(null);
      openStream(session.session_id);
    } catch (e) {
      setError(explain(e, maxChars));
      setSession(null);
    } finally {
      setCreating(false);
    }
  };

  const endSession = async () => {
    const sid = session?.session_id;
    closeStream();
    setSession(null);
    setEnded(null);
    setRuntimeState("");
    setHasFrame(false);
    if (sid) await api.release(sid).catch(() => undefined);
  };

  const releaseOthers = async () => {
    if (status?.holder_session_id) await api.release(status.holder_session_id).catch(() => undefined);
    setStatus(await api.status());
  };

  const label = stabilizing && runtimeState === "RECONDITIONING"
    ? { text: "Stabilizing the world", color: "blue" as const }
    : STATE_LABEL[runtimeState] ?? STATE_LABEL[session?.state ?? ""] ?? { text: "No world", color: "grey" as const };
  const blocked = creating || (!!status?.busy && !status.you_hold);
  const mock = (live.engine ?? status?.engine) === "mock";
  const preset = presets.find((p) => session?.source === `preset:${p.id}`);

  return (
    <Page
      masthead={
        <Masthead>
          <MastheadMain>
            <MastheadBrand>
              <Content component="h1" style={{ margin: 0, fontSize: "1.25rem" }}>Zuno World Model</Content>
            </MastheadBrand>
          </MastheadMain>
          <MastheadContent>
            <Flex>
              <FlexItem><Label color={label.color}>{label.text}</Label></FlexItem>
              {me && <FlexItem>{me.user}</FlexItem>}
            </Flex>
          </MastheadContent>
        </Masthead>
      }
    >
      <PageSection>
        <Alert variant="info" isInline title="Generative AI, not a 3D simulation">
          The picture is invented frame by frame by a world model. It drifts, may ignore a request, and only remembers
          about ten seconds: use Reset to start again from the first image.
          {mock && " This server runs the SIMULATED mock engine: the frames are not produced by the model."}
        </Alert>
        {error && <Alert variant="danger" isInline title={error} style={{ marginTop: 12 }} actionClose={<Button variant="plain" onClick={() => setError(null)}>×</Button>} />}
        {status && !status.runtime_ready && (
          <Alert variant="warning" isInline title="The GPU runtime is not ready (models loading, or the demo is off)." style={{ marginTop: 12 }} />
        )}
        {status?.busy && !status.you_hold && (
          <Alert variant="warning" isInline style={{ marginTop: 12 }} title={`Another world is running on the GPU${status.holder ? ` (${status.holder})` : ""}.`}>
            {me?.ops && status.holder_session_id && <Button variant="link" onClick={releaseOthers}>Release it</Button>}
          </Alert>
        )}
      </PageSection>
      <PageSection>
        <Grid hasGutter>
          <GridItem lg={8} md={12}>
            <Card>
              <CardBody>
                <div style={{ position: "relative", width: "100%", aspectRatio: "16 / 9", background: "#111" }}>
                  <canvas
                    ref={canvasRef}
                    tabIndex={0}
                    width={1280}
                    height={720}
                    aria-label="World view. Click to look around, W A S D to move."
                    style={{ width: "100%", height: "100%", display: "block", outline: "none", cursor: "crosshair" }}
                  />
                  {session?.preview_png_b64 && !hasFrame && (
                    <img alt="First image of the world" src={`data:image/png;base64,${session.preview_png_b64}`}
                      style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", pointerEvents: "none" }} />
                  )}
                  {(creating || runtimeState === "RECONDITIONING") && (
                    <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,.45)", color: "#fff", gap: 12, pointerEvents: "none" }}>
                      <Spinner size="lg" /> {creating ? "Creating the world…" : stabilizing ? "Stabilizing the world…" : "Editing the world…"}
                    </div>
                  )}
                  {ended && (
                    <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,.7)", color: "#fff", gap: 12, padding: 24, textAlign: "center" }}>
                      <div>{ended}</div>
                      <Button onClick={endSession}>Start over</Button>
                    </div>
                  )}
                  {!session && !creating && (
                    <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", color: "#bbb" }}>
                      Pick a scene or describe one to enter a generated world.
                    </div>
                  )}
                </div>
                <Content component="small" style={{ display: "block", marginTop: 8 }}>
                  Click the picture to look around · W A S D or the arrows to move · Esc releases the mouse
                </Content>
              </CardBody>
            </Card>
          </GridItem>
          <GridItem lg={4} md={12}>
            {!session ? (
              <Card>
                <CardTitle>Start a world</CardTitle>
                <CardBody>
                  <Flex direction={{ default: "column" }} gap={{ default: "gapMd" }}>
                    {presets.map((p) => (
                      <FlexItem key={p.id}>
                        <strong>{p.title}</strong>
                        <div>{p.description}</div>
                        <Button isDisabled={blocked || !status?.runtime_ready} onClick={() => start({ preset_id: p.id })} style={{ marginTop: 4 }}>Enter this world</Button>
                      </FlexItem>
                    ))}
                    <FlexItem>
                      <strong>Or describe your own</strong>
                      <TextArea value={sceneText} onChange={(_e, v) => setSceneText(v)} maxLength={maxChars} rows={3}
                        aria-label="Describe a scene" placeholder="a snowy medieval village at dusk, first-person view" />
                      <Button isDisabled={blocked || !status?.runtime_ready || sceneText.trim() === ""} onClick={() => start({ prompt: sceneText })} style={{ marginTop: 4 }}>Generate and enter</Button>
                    </FlexItem>
                  </Flex>
                </CardBody>
              </Card>
            ) : (
              <Card>
                <CardTitle>Change the world</CardTitle>
                <CardBody>
                  <Flex direction={{ default: "column" }} gap={{ default: "gapMd" }}>
                    {session.prompt && <FlexItem><Content component="small">Started from: “{session.prompt.effective}”
                      {session.prompt.enhancement !== "applied" && " (prompt enhancement off)"}</Content></FlexItem>}
                    {preset?.event && (
                      <FlexItem>
                        <Button variant="secondary" isDisabled={!hasFrame} onClick={() => changeWorld(preset.event!.prompt)}>▶ {preset.event.title}</Button>
                      </FlexItem>
                    )}
                    <FlexItem>
                      <TextArea value={promptText} onChange={(_e, v) => setPromptText(v)} maxLength={maxChars} rows={3}
                        aria-label="Describe a change" placeholder="the sky turns red and a volcano erupts" />
                      <Button isDisabled={!hasFrame || promptText.trim() === ""} onClick={() => changeWorld(promptText)} style={{ marginTop: 4 }}>Apply to the world</Button>
                    </FlexItem>
                    {promptNote && <FlexItem><Content component="small">{promptNote}</Content></FlexItem>}
                    {applied && (
                      <FlexItem>
                        <Label color={applied.status === "applied" ? "green" : applied.status === "requested" ? "blue" : "red"}>
                          Change {applied.version}: {applied.status}{applied.ms ? ` in ${(applied.ms / 1000).toFixed(1)} s` : ""}
                        </Label>
                      </FlexItem>
                    )}
                    <FlexItem>
                      <Button variant="secondary" isDisabled={creating} onClick={resetWorld}>Reset to the first image</Button>{" "}
                      <Button variant="link" isDanger onClick={endSession}>End session</Button>
                    </FlexItem>
                  </Flex>
                </CardBody>
              </Card>
            )}
            <Card style={{ marginTop: 16 }}>
              <CardBody>
                <ExpandableSection toggleText="Technical view">
                  <DescriptionList isCompact isHorizontal>
                    <DescriptionListGroup><DescriptionListTerm>World engine</DescriptionListTerm>
                      <DescriptionListDescription>{live.engine ?? status?.engine ?? "—"}{(live.precision ?? status?.precision) ? ` (${live.precision ?? status?.precision})` : ""}</DescriptionListDescription></DescriptionListGroup>
                    <DescriptionListGroup><DescriptionListTerm>Image model</DescriptionListTerm>
                      <DescriptionListDescription>{live.image ?? status?.image ?? "—"}</DescriptionListDescription></DescriptionListGroup>
                    <DescriptionListGroup><DescriptionListTerm>Video encoder</DescriptionListTerm>
                      <DescriptionListDescription>{live.encoder ?? status?.encoder ?? "—"}</DescriptionListDescription></DescriptionListGroup>
                    <DescriptionListGroup><DescriptionListTerm>Server step</DescriptionListTerm>
                      <DescriptionListDescription>{stats ? `${stats.step_ms} ms (${stats.engine_fps} frames/s generated)` : "—"}</DescriptionListDescription></DescriptionListGroup>
                    <DescriptionListGroup><DescriptionListTerm>Displayed</DescriptionListTerm>
                      <DescriptionListDescription>{fps} frames/s</DescriptionListDescription></DescriptionListGroup>
                    <DescriptionListGroup><DescriptionListTerm>Input to display</DescriptionListTerm>
                      <DescriptionListDescription>{latency ? `median ${Math.round(latency.p50)} ms, p95 ${Math.round(latency.p95)} ms` : "—"}</DescriptionListDescription></DescriptionListGroup>
                    <DescriptionListGroup><DescriptionListTerm>Prompt enhancement</DescriptionListTerm>
                      <DescriptionListDescription>{status?.enhancement ?? "—"}</DescriptionListDescription></DescriptionListGroup>
                    <DescriptionListGroup><DescriptionListTerm>Changes</DescriptionListTerm>
                      <DescriptionListDescription>{session ? `${session.prompt_requested} requested, ${applied?.status === "applied" ? applied.version : 0} applied` : "—"}</DescriptionListDescription></DescriptionListGroup>
                  </DescriptionList>
                </ExpandableSection>
              </CardBody>
            </Card>
          </GridItem>
        </Grid>
      </PageSection>
    </Page>
  );
}
