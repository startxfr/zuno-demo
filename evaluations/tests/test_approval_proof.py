"""approval_proof.unseen_requests: a retried tool call after a reject must be found and answered."""
import importlib.util
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "arkos"))
sys.path.insert(0, str(HERE.parent / "tekos"))
sys.path.insert(0, str(HERE.parent / "common"))


def _load():
    spec = importlib.util.spec_from_file_location("approval_proof", HERE.parent / "arkos" / "approval_proof.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class UnseenRequests(unittest.TestCase):
  def test_skips_answered_and_other_events(self):
    mod = _load()
    events = [
        {"type": "approval_required", "request_id": "a"},
        {"type": "message", "request_id": "x"},
        {"type": "approval_required", "request_id": "b"},
    ]
    self.assertEqual([e["request_id"] for e in mod.unseen_requests(events, {"a"})], ["b"])
    self.assertEqual(mod.unseen_requests(events, {"a", "b"}), [])
    self.assertEqual(mod.unseen_requests([], set()), [])


if __name__ == "__main__":
    unittest.main()
