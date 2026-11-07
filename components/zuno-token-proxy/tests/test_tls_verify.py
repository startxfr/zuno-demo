"""WP-226: verify_for keeps httpx's old `verify=<path>` meaning on httpx 0.28."""
import os
import ssl
import sys

import certifi

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.tls import verify_for  # noqa: E402

assert verify_for(True) is True and verify_for(False) is False
assert verify_for(None) is True and verify_for("") is True
ctx = verify_for(certifi.where())
assert isinstance(ctx, ssl.SSLContext) and ctx.cert_store_stats()["x509_ca"] > 0
print("OK")
