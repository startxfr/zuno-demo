"""TLS verification argument for httpx clients (same as ai-gateway's app/tls.py).

httpx 0.28 deprecates `verify=<path>`. A bool passes through, a file path
becomes an SSLContext trusting that file (a directory: capath), an empty
value means the default store.
"""
from __future__ import annotations

import os
import ssl
from typing import Optional, Union


def verify_for(value: Optional[Union[str, bool]]) -> Union[ssl.SSLContext, bool]:
    if isinstance(value, bool):
        return value
    if not value:
        return True
    if os.path.isdir(value):
        return ssl.create_default_context(capath=value)
    return ssl.create_default_context(cafile=value)
