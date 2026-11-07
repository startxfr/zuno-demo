"""H.264 encoding for the browser's WebCodecs decoder (ADR-0604 D4).

PyAV's wheels bundle FFmpeg with both h264_nvenc (needs the driver's video
capability: NVIDIA_DRIVER_CAPABILITIES includes `video`) and libx264 (GPL, like
this repository). `auto` tries NVENC first and falls back to x264, and the
choice is exported so the technical view shows which path is live.

Output: Annex-B access units, SPS/PPS repeated on every keyframe, no B-frames,
so a browser that joins late can start at the next keyframe.
"""
from __future__ import annotations

import logging
from fractions import Fraction
from typing import List, Optional, Tuple

import av
import numpy as np

from app.config import Settings

logger = logging.getLogger(__name__)


class FrameEncoder:
    def __init__(self, codec: str, settings: Settings, fps: int = 60):
        self.codec_name = codec
        self.name = "nvenc" if codec == "h264_nvenc" else "x264"
        ctx = av.CodecContext.create(codec, "w")
        ctx.width, ctx.height = settings.width, settings.height
        ctx.pix_fmt = "yuv420p"
        ctx.time_base = Fraction(1, fps)
        ctx.framerate = Fraction(fps, 1)
        ctx.bit_rate = settings.bitrate
        ctx.gop_size = settings.gop_frames
        ctx.max_b_frames = 0
        if codec == "libx264":
            ctx.options = {
                "preset": "ultrafast",
                "tune": "zerolatency",
                "profile": "baseline",
                "x264-params": "repeat-headers=1:annexb=1",
            }
        else:
            ctx.options = {"preset": "p1", "tune": "ull", "zerolatency": "1", "rc": "cbr",
                           "profile": "baseline", "repeat_headers": "1"}
        ctx.open()
        self.ctx = ctx
        self.pts = 0
        self._force_key = True

    def request_keyframe(self) -> None:
        self._force_key = True

    def encode(self, frame: np.ndarray) -> List[Tuple[bytes, bool]]:
        """(Annex-B access unit, is_keyframe) for each packet the frame produced."""
        video = av.VideoFrame.from_ndarray(np.ascontiguousarray(frame), format="rgb24").reformat(format="yuv420p")
        video.pts = self.pts
        self.pts += 1
        if self._force_key:
            video.pict_type = av.video.frame.PictureType.I
            self._force_key = False
        return [(bytes(packet), bool(packet.is_keyframe)) for packet in self.ctx.encode(video)]

    def close(self) -> None:
        try:
            self.ctx.encode(None)
        except Exception:  # flushing a closed encoder is harmless
            pass


def build_encoder(settings: Settings) -> FrameEncoder:
    """The configured encoder; `auto` falls back to x264 when NVENC cannot open."""
    order = {"nvenc": ["h264_nvenc"], "x264": ["libx264"], "auto": ["h264_nvenc", "libx264"]}[settings.encoder]
    last_error: Optional[Exception] = None
    for codec in order:
        try:
            encoder = FrameEncoder(codec, settings)
            # A real frame proves the hardware path; opening alone can succeed without a GPU session.
            encoder.encode(np.zeros((settings.height, settings.width, 3), dtype=np.uint8))
            encoder.request_keyframe()
            logger.info("video encoder: %s", codec)
            return encoder
        except Exception as exc:  # noqa: BLE001 - any failure means "try the next codec"
            last_error = exc
            logger.warning("video encoder %s unavailable: %s", codec, exc)
    raise RuntimeError(f"no H.264 encoder available ({order}): {last_error}")
