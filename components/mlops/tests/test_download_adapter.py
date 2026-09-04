"""WP-133 coverage for components/mlops/src/download_adapter.py - the
init-container script that gets a registered LoRA adapter onto a serving
pod's local filesystem (ADR-0301 point 2, the gap WP-34 documented and
never built).

Run from components/mlops:

    python3 tests/test_download_adapter.py
    python3 -m pytest tests/test_download_adapter.py -q
"""
from __future__ import annotations

import pathlib
import sys
import tempfile
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import download_adapter  # noqa: E402


class _FakePaginator:
    def __init__(self, pages):
        self._pages = pages

    def paginate(self, **_kwargs):
        return self._pages


class _FakeS3Client:
    def __init__(self, pages, downloaded: list):
        self._paginator = _FakePaginator(pages)
        self._downloaded = downloaded

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return self._paginator

    def download_file(self, bucket, key, dest):
        self._downloaded.append((bucket, key, dest))
        pathlib.Path(dest).write_text("fake-adapter-bytes")


def test_split_s3_uri_rejects_a_non_s3_scheme() -> None:
    try:
        download_adapter._split_s3_uri("https://example.com/x")
        raise AssertionError("expected SystemExit")
    except SystemExit as exc:
        assert "not an s3:// URI" in str(exc)


def test_split_s3_uri_rejects_a_bucket_with_no_prefix() -> None:
    try:
        download_adapter._split_s3_uri("s3://bucket-only")
        raise AssertionError("expected SystemExit")
    except SystemExit as exc:
        assert "malformed" in str(exc)


def test_download_adapter_writes_every_object_under_the_prefix_relative_to_dest() -> None:
    downloaded: list = []
    pages = [
        {
            "Contents": [
                {"Key": "mlops/models/tekos/run-1/adapter/adapter_model.safetensors"},
                {"Key": "mlops/models/tekos/run-1/adapter/adapter_config.json"},
                # A bare prefix marker (no trailing content) must be skipped,
                # not written as a file named "" under dest.
                {"Key": "mlops/models/tekos/run-1/adapter/"},
            ]
        }
    ]
    client = _FakeS3Client(pages, downloaded)

    with tempfile.TemporaryDirectory() as tmp:
        count = download_adapter.download_adapter(
            client, "s3://zuno-corpus/mlops/models/tekos/run-1/adapter", tmp
        )
        assert count == 2
        assert (pathlib.Path(tmp) / "adapter_model.safetensors").is_file()
        assert (pathlib.Path(tmp) / "adapter_config.json").is_file()

    assert {key for _, key, _ in downloaded} == {
        "mlops/models/tekos/run-1/adapter/adapter_model.safetensors",
        "mlops/models/tekos/run-1/adapter/adapter_config.json",
    }


def test_download_adapter_refuses_to_leave_the_destination_empty() -> None:
    client = _FakeS3Client([{"Contents": []}], [])
    with tempfile.TemporaryDirectory() as tmp:
        try:
            download_adapter.download_adapter(client, "s3://zuno-corpus/mlops/models/x/none", tmp)
            raise AssertionError("expected SystemExit on an empty prefix")
        except SystemExit as exc:
            assert "no adapter files found" in str(exc)


def test_main_requires_adapter_source_and_dest_env_vars() -> None:
    with mock.patch.dict("os.environ", {}, clear=True):
        try:
            download_adapter.main()
            raise AssertionError("expected SystemExit when ADAPTER_SOURCE_S3URI is unset")
        except SystemExit as exc:
            assert "ADAPTER_SOURCE_S3URI is required" in str(exc)


def test_main_downloads_using_env_configured_client() -> None:
    downloaded: list = []
    pages = [{"Contents": [{"Key": "mlops/models/tekos/run-1/adapter/adapter_model.safetensors"}]}]
    fake_client = _FakeS3Client(pages, downloaded)

    with tempfile.TemporaryDirectory() as tmp:
        env = {
            "ADAPTER_SOURCE_S3URI": "s3://zuno-corpus/mlops/models/tekos/run-1/adapter",
            "ADAPTER_DEST_PATH": tmp,
            "AWS_ACCESS_KEY_ID": "AKIAFAKE",
            "AWS_SECRET_ACCESS_KEY": "s3cr3t",
        }
        with mock.patch.dict("os.environ", env, clear=True):
            with mock.patch.object(download_adapter, "_s3_client", return_value=fake_client):
                assert download_adapter.main() == 0
        assert (pathlib.Path(tmp) / "adapter_model.safetensors").is_file()


TESTS = [
    test_split_s3_uri_rejects_a_non_s3_scheme,
    test_split_s3_uri_rejects_a_bucket_with_no_prefix,
    test_download_adapter_writes_every_object_under_the_prefix_relative_to_dest,
    test_download_adapter_refuses_to_leave_the_destination_empty,
    test_main_requires_adapter_source_and_dest_env_vars,
    test_main_downloads_using_env_configured_client,
]


def main() -> int:
    failed = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS {test.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
