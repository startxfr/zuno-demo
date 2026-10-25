"""RoutingWatcher reloads a routing table when its mounted file changes, and only then."""

from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.routing import RoutingTable
from app.routing_watch import RoutingWatcher

ROUTING = """providers:
  - name: local
    kind: local
    model: m
    max_model_len: {window}
    eligible_for: [C1, C2, C3]
"""


def _table(tmp_path: pathlib.Path, window: int = 32768):
    path = tmp_path / "provider-routing.yaml"
    path.write_text(ROUTING.format(window=window))
    table = RoutingTable(str(path))
    return path, table, RoutingWatcher({table.path: table.reload})


def _window(table: RoutingTable) -> int:
    return table._config["providers"][0]["max_model_len"]


def test_unchanged_file_is_not_reloaded(tmp_path):
    _, table, watcher = _table(tmp_path)
    assert watcher.check_once() == []
    assert _window(table) == 32768


def test_changed_file_is_reloaded(tmp_path):
    path, table, watcher = _table(tmp_path)
    path.write_text(ROUTING.format(window=131072))
    assert watcher.check_once() == [str(path)]
    assert _window(table) == 131072
    assert watcher.check_once() == []  # same content: no second reload


def test_invalid_change_keeps_the_loaded_table(tmp_path):
    """RoutingTable._load returns {} (local-only fail-closed) on a parse error; mid-flight that
    would drop every provider, so the watcher must not reload an invalid file."""
    path, table, watcher = _table(tmp_path)
    path.write_text("providers: [unclosed")
    assert watcher.check_once() == []
    assert _window(table) == 32768
    assert table.loaded
    path.write_text(ROUTING.format(window=65536))  # fixed later: picked up
    assert watcher.check_once() == [str(path)]
    assert _window(table) == 65536


def test_missing_file_keeps_the_loaded_table(tmp_path):
    path, table, watcher = _table(tmp_path)
    path.unlink()
    assert watcher.check_once() == []
    assert _window(table) == 32768


def test_kubelet_style_symlink_swap_is_seen(tmp_path):
    """ConfigMap volumes update by swapping the ..data symlink; the watcher reads through it."""
    v1, v2 = tmp_path / "v1", tmp_path / "v2"
    v1.mkdir()
    v2.mkdir()
    (v1 / "provider-routing.yaml").write_text(ROUTING.format(window=32768))
    (v2 / "provider-routing.yaml").write_text(ROUTING.format(window=131072))
    data = tmp_path / "..data"
    data.symlink_to(v1)
    link = tmp_path / "provider-routing.yaml"
    link.symlink_to(data / "provider-routing.yaml")
    table = RoutingTable(str(link))
    watcher = RoutingWatcher({table.path: table.reload})
    tmp = tmp_path / "..data_tmp"
    tmp.symlink_to(v2)
    tmp.rename(data)
    assert watcher.check_once() == [str(link)]
    assert _window(table) == 131072
