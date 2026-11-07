"""Low-cardinality Prometheus metrics of world-model-web (ADR-0604 §10).

No session id, user name or prompt ever becomes a label. The GPU-side metrics
(zuno_world_engine_step_seconds, ...) come from world-model-runtime; the ones
below are what only the web tier knows: who was refused, how prompts fared,
and what the browser itself measured.
"""
from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

REGISTRY = CollectorRegistry()

WORLDS = Counter("zuno_world_web_worlds_total", "World creation requests", ["source", "result"], registry=REGISTRY)
BUSY_REJECTED = Counter("zuno_world_web_busy_rejected_total", "Requests refused: the GPU serves another world",
                        registry=REGISTRY)
QUOTA_REJECTED = Counter("zuno_world_web_quota_rejected_total", "Requests refused by a per-user limit",
                         ["limit"], registry=REGISTRY)
AUTH_FAILURES = Counter("zuno_world_web_auth_failures_total", "Calls refused by identity checks", ["reason"],
                        registry=REGISTRY)
PROMPTS = Counter("zuno_world_web_prompts_total", "Prompts screened", ["kind", "result"], registry=REGISTRY)
ENHANCE = Histogram("zuno_world_web_enhance_seconds", "Prompt enhancement call to the ai-gateway", ["result"],
                    buckets=(0.25, 0.5, 1, 2, 4, 8, 16), registry=REGISTRY)
SESSIONS_ACTIVE = Gauge("zuno_world_web_sessions_active", "Worlds holding the GPU lease (0 or 1)", registry=REGISTRY)
SESSION_ENDED = Counter("zuno_world_web_session_ended_total", "Leases released", ["reason"], registry=REGISTRY)
# What the browser reports about itself (ADR-0604 §9.1): displayed frames and input-to-display latency.
CLIENT_FPS = Histogram("zuno_world_displayed_fps", "Frames per second the browser displayed", ["client_type"],
                       buckets=(5, 10, 15, 20, 24, 30, 45, 60, 90), registry=REGISTRY)
CLIENT_LATENCY = Histogram("zuno_world_action_to_display_seconds", "Input to first changed frame, measured in the browser",
                           ["client_type"], buckets=(0.05, 0.1, 0.15, 0.25, 0.4, 0.6, 1.0, 2.0), registry=REGISTRY)
