"""WP-226: verify_for keeps httpx's old `verify=<path>` meaning on httpx 0.28."""
import os
import ssl
import sys

import certifi

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.tls import verify_for  # noqa: E402


def test_bools_pass_through():
    assert verify_for(True) is True
    assert verify_for(False) is False


def test_empty_means_the_default_store():
    assert verify_for(None) is True
    assert verify_for("") is True


def test_a_file_or_a_directory_becomes_a_context():
    ctx = verify_for(certifi.where())
    assert isinstance(ctx, ssl.SSLContext) and ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.cert_store_stats()["x509_ca"] > 0
    assert isinstance(verify_for(os.path.dirname(certifi.where())), ssl.SSLContext)


def test_a_missing_file_fails_loudly():
    try:
        verify_for("/nonexistent/ca.crt")
    except (FileNotFoundError, ssl.SSLError):
        return
    raise AssertionError("a missing CA file must not silently fall back")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
