"""World-model runtime tests on the CPU mock adapters (ADR-0604 WP-231). No GPU, no network.

Run from the component directory:  python -m pytest tests -q
"""
from __future__ import annotations

import base64
import io
import json
import time

import av
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.controls import ControlState, Ctrl
from app.encoder import build_encoder
from app.engine import MockEngine
from app.imagegen import MockFlux
from app.main import get_app
from app.session import VIDEO_TAG

SMALL = Settings(width=320, height=176, mock_step_seconds=0.01, encoder="x264", gop_frames=8)


# ---------------------------------------------------------------- controls
def test_known_keys_map_to_buttons_and_unknown_keys_are_dropped():
    state = ControlState()
    assert state.update(1, ["KeyW", "KeyD", "Meta", "<script>"], None)
    ctrl = state.take()
    assert ctrl.button == frozenset({87, 68})


def test_mouse_motion_accumulates_until_taken_and_is_clamped():
    state = ControlState()
    state.update(1, [], {"dx": 0.4, "dy": -0.1})
    state.update(2, [], {"dx": 0.9, "dy": 0.0})
    ctrl = state.take()
    assert ctrl.mouse == (1.0, pytest.approx(-0.1))
    assert state.take().mouse == (0.0, 0.0)  # consumed


def test_stale_or_malformed_messages_are_refused():
    state = ControlState()
    assert state.update(5, ["KeyW"], None)
    assert not state.update(4, ["KeyS"], None)          # older sequence
    assert not state.update(6, [], {"dx": "nan?"})       # not a number
    assert not state.update(7, [], {"dx": float("nan")})
    assert state.take().button == frozenset({87})


def test_arrow_keys_move_and_turn():
    state = ControlState()
    state.update(1, ["ArrowUp", "ArrowRight"], None)
    ctrl = state.take()
    assert 87 in ctrl.button and ctrl.mouse[0] > 0


# ---------------------------------------------------------------- engine + images
def test_mock_engine_returns_four_frames_that_move_with_the_controls():
    engine = MockEngine(SMALL)
    image = MockFlux().generate("a snowy village", 1, SMALL.width, SMALL.height)
    engine.reset(image)
    still = engine.step(Ctrl())
    moved = engine.step(Ctrl(button=frozenset({68}), mouse=(0.5, 0.0)))
    assert still.shape == (4, SMALL.height, SMALL.width, 3) and still.dtype == np.uint8
    assert not np.array_equal(still[-1], moved[-1])


def test_mock_edit_changes_the_image_and_is_deterministic():
    flux = MockFlux()
    image = flux.generate("a city at night", 3, SMALL.width, SMALL.height)
    assert np.array_equal(image, flux.generate("a city at night", 3, SMALL.width, SMALL.height))
    edited = flux.edit(image, "heavy rain starts", 4)
    assert edited.shape == image.shape and not np.array_equal(edited, image)


# ---------------------------------------------------------------- encoder
def test_x264_stream_is_annexb_starts_with_a_keyframe_and_decodes():
    encoder = build_encoder(SMALL)
    assert encoder.name == "x264"
    frames = MockEngine(SMALL)
    frames.reset(MockFlux().generate("warehouse", 2, SMALL.width, SMALL.height))
    packets = []
    for batch in (frames.step(Ctrl()) for _ in range(3)):
        for frame in batch:
            packets.extend(encoder.encode(frame))
    assert packets, "the zero-latency encoder must emit a packet per frame"
    first, is_key = packets[0]
    assert is_key and first.startswith((b"\x00\x00\x00\x01", b"\x00\x00\x01"))
    decoder = av.CodecContext.create("h264", "r")
    decoded = sum(len(decoder.decode(av.Packet(p))) for p, _ in packets)
    assert decoded >= len(packets) - 2


def test_auto_encoder_falls_back_to_x264_without_a_gpu():
    encoder = build_encoder(Settings(width=320, height=176, encoder="auto"))
    assert encoder.name in ("x264", "nvenc")


# ---------------------------------------------------------------- API
@pytest.fixture()
def client():
    app = get_app(SMALL)
    with TestClient(app) as c:
        deadline = time.time() + 20
        while c.get("/readyz").status_code != 200:
            assert time.time() < deadline, c.get("/readyz").json()
            time.sleep(0.05)
        yield c


def _video(message: bytes):
    assert message[:1] == VIDEO_TAG
    return bool(message[1] & 1), int.from_bytes(message[2:10], "big"), message[10:]


def test_health_ready_and_metrics(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").status_code == 200
    body = client.get("/metrics").text
    assert "zuno_world_engine_info" in body and "session" not in body.split("zuno_world_active_sessions")[0][-50:]


def test_internal_token_is_enforced_when_set(monkeypatch, client):
    monkeypatch.setenv("WORLD_MODEL_INTERNAL_TOKEN", "s3cret")
    assert client.get("/internal/status").status_code == 401
    assert client.get("/internal/status", headers={"X-World-Runtime-Token": "s3cret"}).status_code == 200


def test_world_from_prompt_streams_video_and_applies_a_world_edit(client):
    world = client.post("/internal/worlds", json={"prompt": "a snowy medieval village at dusk", "seed": 7}).json()
    assert world["state"] == "READY" and base64.b64decode(world["preview_png_b64"])[:4] == b"\x89PNG"
    with client.websocket_connect(f"/internal/worlds/{world['world_id']}/stream") as ws:
        state = json.loads(ws.receive_text())
        assert state["type"] == "state" and state["state"] == "STREAMING" and state["engine"] == "mock"
        first = ws.receive_bytes()
        assert _video(first)[0], "the stream must open on a keyframe"
        ws.send_text(json.dumps({"type": "control", "seq": 1, "keys": ["KeyW"], "mouse": {"dx": 0.2, "dy": 0}}))
        ws.send_text(json.dumps({"type": "edit", "prompt_version": 1, "prompt": "the sky turns red"}))
        events, videos = [], 0
        deadline = time.time() + 10
        while time.time() < deadline and not (any(e.get("type") == "prompt" for e in events)
                                               and any(e.get("type") == "stats" for e in events)):
            msg = ws.receive()
            if msg.get("bytes"):
                videos += 1
            elif msg.get("text"):
                events.append(json.loads(msg["text"]))
        applied = [e for e in events if e.get("type") == "prompt"]
        assert applied and applied[0]["status"] == "applied" and applied[0]["prompt_version"] == 1
        assert any(e.get("state") == "RECONDITIONING" for e in events)
        assert any(e.get("type") == "stats" for e in events) and videos >= 4  # one 4-frame step at least
        ws.send_text(json.dumps({"type": "stop"}))
    deadline = time.time() + 3  # the server ends the stream asynchronously after "stop"
    while client.get("/internal/status").json()["streaming"] and time.time() < deadline:
        time.sleep(0.05)
    status = client.get("/internal/status").json()
    assert status["streaming"] is False and status["world"]["prompt_version"] == 1


def test_a_second_stream_or_a_new_world_is_refused_while_streaming(client):
    world = client.post("/internal/worlds", json={"prompt": "a logistics warehouse", "seed": 1}).json()
    with client.websocket_connect(f"/internal/worlds/{world['world_id']}/stream") as ws:
        ws.receive_text()
        assert client.post("/internal/worlds", json={"prompt": "another", "seed": 2}).status_code == 409
        assert client.post("/internal/image", json={"prompt": "x", "seed": 2}).status_code == 409
        with pytest.raises(Exception):
            with client.websocket_connect(f"/internal/worlds/{world['world_id']}/stream") as second:
                second.receive_text()
        ws.send_text(json.dumps({"type": "stop"}))


def test_world_from_an_uploaded_image_and_bad_input(client):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (640, 360), (20, 80, 160)).save(buf, format="PNG")
    ok = client.post("/internal/worlds", json={"image_png_b64": base64.b64encode(buf.getvalue()).decode()})
    assert ok.status_code == 201
    assert client.post("/internal/worlds", json={}).status_code == 422
    assert client.post("/internal/worlds", json={"image_png_b64": "!!notbase64"}).status_code == 422
    assert client.post("/internal/worlds", json={"prompt": "x" * 700}).status_code == 422
    assert client.delete("/internal/worlds/nope").status_code == 404
