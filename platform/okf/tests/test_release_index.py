"""release_cache.read_index: the corp artifact's index, refused by name when it
is absent or of an unknown schemaVersion (ADR-0508).

Run from the repository root:
    python3 platform/okf/tests/test_release_index.py
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import release_cache  # noqa: E402


class ReadIndex(unittest.TestCase):
    def _release(self, doc=None):
        root = pathlib.Path(tempfile.mkdtemp())
        if doc is not None:
            (root / "okf-index.json").write_text(json.dumps(doc))
        return root

    def test_a_schema_version_1_index_reads(self):
        doc = {"schemaVersion": 1, "release": "0.3.1", "agents": []}
        self.assertEqual(release_cache.read_index(self._release(doc)), doc)

    def test_a_missing_index_is_refused_by_name(self):
        with self.assertRaises(release_cache.ReleaseUnavailable) as caught:
            release_cache.read_index(self._release())
        self.assertIn("okf-index.json", str(caught.exception))

    def test_an_unknown_schema_version_is_refused_by_name(self):
        with self.assertRaises(release_cache.ReleaseUnavailable) as caught:
            release_cache.read_index(self._release({"schemaVersion": 2, "agents": []}))
        self.assertIn("unsupported index schemaVersion 2", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
