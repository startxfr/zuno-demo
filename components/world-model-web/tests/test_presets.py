"""The curated scenes pass the same rules as a visitor's prompt (ADR-0604 WP-236). No network.

Reads platform/world-model/config/presets.yaml, the file the Day-2 role hands to the chart.
"""
from __future__ import annotations

import pathlib

import yaml

from app.config import Settings
from app.main import load_presets
from app.prompts import Screener

PRESETS = pathlib.Path(__file__).resolve().parents[3] / "platform" / "world-model" / "config" / "presets.yaml"


def test_three_scenes_with_unique_ids_and_an_event_each():
    presets = yaml.safe_load(PRESETS.read_text())["presets"]
    assert [p["id"] for p in presets] == ["warehouse", "city", "village"]
    for p in presets:
        assert {"id", "title", "description", "prompt", "seed", "event"} <= p.keys()
        assert isinstance(p["seed"], int) and 0 <= p["seed"] < 2**31
        assert p["event"]["title"] and p["event"]["prompt"]


def test_every_scene_and_event_passes_the_visitor_rules():
    settings = Settings(gateway_url="")
    screener = Screener(settings)
    for p in yaml.safe_load(PRESETS.read_text())["presets"]:
        for text in (p["prompt"], p["event"]["prompt"]):
            assert len(text) <= settings.max_prompt_chars, f"{p['id']}: {len(text)} characters"
            assert screener.check_local(text) == text, f"{p['id']}: normalized differently"


def test_the_api_loader_reads_the_same_file():
    loaded = load_presets(PRESETS)
    assert [p["id"] for p in loaded] == ["warehouse", "city", "village"]
    assert all(p["_image_path"] is None for p in loaded), "no image is shipped: the image model makes the first frame"
