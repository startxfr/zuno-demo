"""TLS verification argument for httpx clients.

httpx 0.28 deprecates `verify=<path>`; it wants an `ssl.SSLContext`. ADR-0603
M20 (WP-226) moved ai-gateway to httpx 0.28, so every place that passed a CA
bundle path now passes `verify_for(path)`, which keeps the old meaning:

- a bool is passed through (`True` verifies against the default store,
  `False` disables verification);
- a file path becomes a context trusting that file only (cafile), a
  directory path one trusting that directory (capath), as httpx did;
- an empty value or None means the default store (`True`).
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
