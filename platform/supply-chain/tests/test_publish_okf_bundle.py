"""ADR-0564 tests for publish_okf_bundle.py: the deterministic layer the
UnifAI operator pulls, the exact `oras push` arguments, and the refusal to
publish a bundle whose signature no longer verifies. The signing round trip
uses a throwaway cosign key and is skipped when cosign is not installed.

Run from this directory's parent:

    python3 tests/test_publish_okf_bundle.py
"""
from __future__ import annotations

import gzip
import io
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile

SUPPLY_CHAIN_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SUPPLY_CHAIN_DIR))

import publish_okf_bundle  # noqa: E402
import sign_okf_bundle  # noqa: E402


def _make_bundle(tmp: pathlib.Path) -> pathlib.Path:
    bundle_dir = tmp / "agents" / "demo"
    for rel, content in {"agent.okf.md": "---\ntype: agent\n---\nbody", "tasks/t.md": "task",
                         "__pycache__/x.pyc": "noise"}.items():
        path = bundle_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return bundle_dir


def test_layer_is_deterministic_and_reproduces_the_digest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        bundle_dir = _make_bundle(pathlib.Path(tmp))
        first = publish_okf_bundle.build_layer(bundle_dir)
        os.utime(bundle_dir / "tasks" / "t.md", (1, 1))
        assert publish_okf_bundle.build_layer(bundle_dir) == first, "mtime leaked into the layer"

        extracted = pathlib.Path(tmp) / "extracted"
        with tarfile.open(fileobj=io.BytesIO(gzip.decompress(first))) as tar:
            names = tar.getnames()
            for member in tar.getmembers():
                assert member.isfile() and member.uid == 0 and member.mtime == 0, member.name
            if hasattr(tarfile, "data_filter"):
                tar.extractall(extracted, filter="data")
            else:  # Python < 3.11.4
                tar.extractall(extracted)
        assert names == ["agent.okf.md", "tasks/t.md"], names
        assert sign_okf_bundle.compute_digest(extracted) == sign_okf_bundle.compute_digest(bundle_dir)


def test_oras_arguments_name_the_layer_type_and_annotations() -> None:
    args = publish_okf_bundle.oras_push_args("quay.io/zuno/okf-demo", "ab" * 32, "c2ln")
    assert args[1] == "quay.io/zuno/okf-demo:okf-" + "ab" * 8
    assert "application/vnd.zuno.okf.bundle.v1" in args
    assert "zuno.okf.signature=c2ln" in args and f"zuno.okf.digest={'ab' * 32}" in args
    assert args[-1] == "okf-bundle.tar.gz:application/vnd.zuno.okf.bundle.v1.tar+gzip"


def test_publish_refuses_a_bundle_changed_since_signing() -> None:
    if shutil.which("cosign") is None:
        print("SKIP cosign not installed")
        return
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        bundle_dir = _make_bundle(tmp_path)
        env = {**os.environ, "COSIGN_PASSWORD": ""}
        subprocess.run(["cosign", "generate-key-pair"], cwd=tmp, env=env, check=True, capture_output=True)
        digest_file = tmp_path / "demo.digest"
        digest_file.write_text(sign_okf_bundle.compute_digest(bundle_dir) + "\n")
        sig = tmp_path / "demo.sig"
        subprocess.run(["cosign", "sign-blob", "--yes", "--tlog-upload=false", "--key", "cosign.key",
                        "--output-signature", str(sig), str(digest_file)],
                       cwd=tmp, env=env, check=True, capture_output=True)
        (bundle_dir / "tasks" / "t.md").write_text("task, edited after signing")
        try:
            publish_okf_bundle.publish(bundle_dir, sig, "localhost:1/never-reached",
                                       tmp_path / "cosign.pub", oras_bin="oras-must-not-run")
        except publish_okf_bundle.PublishError as exc:
            assert "refusing to publish" in str(exc), exc
        else:
            raise AssertionError("an edited bundle was published")


TESTS = [
    test_layer_is_deterministic_and_reproduces_the_digest,
    test_oras_arguments_name_the_layer_type_and_annotations,
    test_publish_refuses_a_bundle_changed_since_signing,
]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
