#!/usr/bin/env python3
"""Claude Code's apiKeyHelper for Praxis on Zuno (ADR-0619 clause 8, WP-298): the presenter's own Keycloak token.

    zuno_claude_token.py login     sign in once, in a terminal (OAuth device grant of the public client claude-code)
    zuno_claude_token.py           print a fresh access token on stdout (what Claude Code's apiKeyHelper runs)
    zuno_claude_token.py logout    end the Keycloak session and delete the cached refresh token

Claude Code runs its apiKeyHelper without a terminal, re-runs it every CLAUDE_CODE_API_KEY_HELPER_TTL_MS and on a
401 or 403, and sends its output in the Authorization (Bearer) and x-api-key headers. So the default command never
starts a sign-in: it trades the cached refresh token for a new access token, and when there is none, or Keycloak
refuses it, it says on stderr to run `login` and exits 1.

The refresh token is cached in ~/.cache/zuno/claude-code/token.json (directory 0700, file 0600, written atomically);
a cache file readable by anyone else is refused, never used. Keycloak rotates refresh tokens: each refresh writes the
new one. Nothing else is stored. No token or device code is ever written to stderr, a log or an exception: errors
carry HTTP statuses and Keycloak error names only. The one exception is `login`, which shows the user code and the
verification page on the terminal (stderr), because a person has to type them; they are single-use and expire in
600 s. The access token goes to stdout only, and only in the default command.

Settings, from the environment:
    ZUNO_CLUSTER_DOMAIN   the cluster's apps domain (e.g. apps.demo333.startx.fr); the issuer is
                          https://keycloak.<domain>/realms/zuno
    ZUNO_ISSUER           the issuer URL itself, instead of the domain
    ZUNO_CA_FILE          a CA bundle for Keycloak's certificate (default: the system trust store)
    ZUNO_CLAUDE_CODE_CACHE  the cache directory (default ~/.cache/zuno/claude-code)

Python 3.8+, standard library only.
"""
from __future__ import annotations

import json
import os
import pathlib
import ssl
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Dict, Optional, Tuple

CLIENT_ID = "claude-code"
CACHE_NAME = "token.json"
EARLY = 30                 # seconds: a refresh token this close to its end is treated as expired
HTTP_TIMEOUT = 20


class TokenError(RuntimeError):
    """Something the presenter must act on; the message holds no secret."""


# --- settings ----------------------------------------------------------------------------------------------------

def issuer_url(env=os.environ) -> str:
    issuer = (env.get("ZUNO_ISSUER") or "").strip().rstrip("/")
    if issuer:
        return issuer
    domain = (env.get("ZUNO_CLUSTER_DOMAIN") or "").strip().strip(".")
    if not domain:
        raise TokenError("set ZUNO_CLUSTER_DOMAIN (the cluster's apps domain, e.g. apps.demo333.startx.fr) "
                         "or ZUNO_ISSUER")
    return f"https://keycloak.{domain}/realms/zuno"


def cache_dir(env=os.environ) -> pathlib.Path:
    configured = (env.get("ZUNO_CLAUDE_CODE_CACHE") or "").strip()
    return pathlib.Path(configured).expanduser() if configured else pathlib.Path.home() / ".cache/zuno/claude-code"


# --- the cache ---------------------------------------------------------------------------------------------------

def load_cache(directory: pathlib.Path, issuer: str, client_id: str = CLIENT_ID,
               now: Optional[float] = None) -> Optional[str]:
    """The cached refresh token for this issuer and client, or None (absent, another issuer or client, expired).
    A cache file that group or others may read is refused: TokenError, and it is not read."""
    path = directory / CACHE_NAME
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        return None
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise TokenError(f"{path} is readable by other users (mode {stat.S_IMODE(mode):o}): delete it and run "
                         "`login` again")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("issuer") != issuer or data.get("client_id") != client_id:
        return None
    token = data.get("refresh_token")
    expires = data.get("refresh_expires_at")
    now = time.time() if now is None else now
    if not isinstance(token, str) or not token:
        return None
    if isinstance(expires, (int, float)) and expires and expires - EARLY <= now:
        return None
    return token


def save_cache(directory: pathlib.Path, issuer: str, answer: Dict, client_id: str = CLIENT_ID,
               now: Optional[float] = None) -> None:
    """Write the refresh token of a token-endpoint answer: directory 0700, file 0600, atomically (a temporary file
    created 0600 in the same directory, then renamed over the old one)."""
    token = answer.get("refresh_token")
    if not isinstance(token, str) or not token:
        raise TokenError("Keycloak gave no refresh token: is the client `claude-code` public with the device grant?")
    now = time.time() if now is None else now
    lifetime = answer.get("refresh_expires_in")
    record = {"issuer": issuer, "client_id": client_id, "refresh_token": token,
              # Keycloak says 0 for an offline token: no end of its own.
              "refresh_expires_at": now + lifetime if isinstance(lifetime, (int, float)) and lifetime > 0 else None,
              "saved_at": now}
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    fd, temporary = tempfile.mkstemp(prefix=".token-", suffix=".json", dir=str(directory))   # mkstemp: mode 0600
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle)
        os.chmod(temporary, 0o600)
        os.replace(temporary, directory / CACHE_NAME)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def clear_cache(directory: pathlib.Path) -> bool:
    try:
        (directory / CACHE_NAME).unlink()
        return True
    except FileNotFoundError:
        return False


# --- Keycloak ----------------------------------------------------------------------------------------------------

Post = Callable[[str, Dict[str, str]], Tuple[int, Dict]]


def http_post(ca_file: Optional[str] = None) -> Post:
    """POST a form, return (status, JSON body or {}). Never raises with a body in the message."""
    context = ssl.create_default_context(cafile=ca_file) if ca_file else ssl.create_default_context()

    def post(url: str, form: Dict[str, str]) -> Tuple[int, Dict]:
        request = urllib.request.Request(url, data=urllib.parse.urlencode(form).encode("ascii"), method="POST",
                                         headers={"Content-Type": "application/x-www-form-urlencoded",
                                                  "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT, context=context) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as exc:
            status, raw = exc.code, exc.read()
        except (urllib.error.URLError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise TokenError(f"cannot reach Keycloak at {urllib.parse.urlsplit(url).netloc}: {reason}") from None
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            body = {}
        return status, body if isinstance(body, dict) else {}
    return post


def refresh(issuer: str, refresh_token: str, post: Post, client_id: str = CLIENT_ID) -> Tuple[str, Dict]:
    """('ok', answer) | ('expired', {}) when Keycloak refuses the refresh token (invalid_grant) | TokenError."""
    status, body = post(f"{issuer}/protocol/openid-connect/token",
                        {"grant_type": "refresh_token", "client_id": client_id, "refresh_token": refresh_token})
    if status == 200 and body.get("access_token"):
        return "ok", body
    error = body.get("error") or f"http_{status}"
    if error in ("invalid_grant", "invalid_token"):
        return "expired", {}
    raise TokenError(f"Keycloak refused the refresh: HTTP {status} {error}")


def token(env=os.environ, post: Optional[Post] = None, now: Optional[float] = None) -> str:
    """A fresh access token from the cached refresh token; the new refresh token is cached. No sign-in here."""
    issuer = issuer_url(env)
    directory = cache_dir(env)
    cached = load_cache(directory, issuer, now=now)
    if cached is None:
        raise TokenError("no Zuno sign-in for Claude Code yet, or it has expired: run "
                         "`zuno_claude_token.py login` in a terminal")
    outcome, answer = refresh(issuer, cached, post or http_post(env.get("ZUNO_CA_FILE")))
    if outcome == "expired":
        clear_cache(directory)
        raise TokenError("the Zuno sign-in has ended (Keycloak refused the refresh token): run "
                         "`zuno_claude_token.py login` in a terminal")
    save_cache(directory, issuer, answer, now=now)
    return answer["access_token"]


def login(env=os.environ, post: Optional[Post] = None, out=sys.stderr,
          sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> None:
    """The device grant: show the user code and the page, poll until the person has signed in, cache the refresh
    token. The access token is not printed."""
    issuer = issuer_url(env)
    post = post or http_post(env.get("ZUNO_CA_FILE"))
    status, device = post(f"{issuer}/protocol/openid-connect/auth/device", {"client_id": CLIENT_ID, "scope": "openid"})
    if status != 200 or not device.get("device_code"):
        raise TokenError(f"Keycloak refused the device authorization: HTTP {status} "
                         f"{device.get('error') or ''}".rstrip())
    interval = float(device.get("interval") or 5)
    deadline = clock() + float(device.get("expires_in") or 600)
    out.write(f"Open {device.get('verification_uri')} and enter the code {device.get('user_code')}\n"
              "(or open the link below), then sign in with your company account.\n"
              f"{device.get('verification_uri_complete') or ''}\n")
    out.flush()
    while clock() < deadline:
        sleep(interval)
        status, body = post(f"{issuer}/protocol/openid-connect/token",
                            {"grant_type": "urn:ietf:params:oauth:grant-type:device_code", "client_id": CLIENT_ID,
                             "device_code": device["device_code"]})
        if status == 200 and body.get("access_token"):
            save_cache(cache_dir(env), issuer, body)
            out.write("Signed in. Claude Code can start.\n")
            return
        error = body.get("error") or f"http_{status}"
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval += 5
            continue
        raise TokenError(f"the sign-in did not complete: {error}")
    raise TokenError("the sign-in was not completed in time: run `login` again")


def logout(env=os.environ, post: Optional[Post] = None) -> str:
    """End the Keycloak session of the cached refresh token, then delete the cache."""
    issuer = issuer_url(env)
    directory = cache_dir(env)
    cached = load_cache(directory, issuer)
    if cached is not None:
        status, _ = (post or http_post(env.get("ZUNO_CA_FILE")))(
            f"{issuer}/protocol/openid-connect/logout", {"client_id": CLIENT_ID, "refresh_token": cached})
        ended = f"Keycloak answered HTTP {status}"
    else:
        ended = "no cached sign-in"
    clear_cache(directory)
    return ended


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    command = args[0] if args else "token"
    try:
        if command == "token":
            sys.stdout.write(token() + "\n")
        elif command == "login":
            login()
        elif command == "logout":
            sys.stderr.write(f"Signed out ({logout()}); the cached refresh token is deleted.\n")
        else:
            sys.stderr.write("usage: zuno_claude_token.py [token|login|logout]\n")
            return 2
    except TokenError as exc:
        sys.stderr.write(f"zuno_claude_token: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
