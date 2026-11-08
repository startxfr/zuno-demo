"""A non-interactive OAuth device sign-in for the Blender client (ADR-0610 clause 9, WP-245).

The golden-path probe and the prompt-set measurement need a token the workstation entry accepts: azp `blender` (a
public client with the device grant only), a user in the admitted group. This does what a person does in the
browser, as an evaluation persona: start the device authorization, open the verification page, submit Keycloak's
login form, accept the grant page when Keycloak shows one, then poll the token endpoint. It tests the real client,
the real AuthPolicy and the real C3 floor, and widens nothing (zuno-demo-3c review, 2026-11-07).

Never printed or put in an exception: the password, the tokens, the device_code and the verification URI (it embeds
the one-time user code). Errors carry HTTP statuses and Keycloak error names only. The flow gives up after its own
timeout, well inside the device code's 600 s lifespan. `revoke()` ends the SSO session afterwards.
"""
from __future__ import annotations

import html
import re
import time
from typing import Dict, Optional

CLIENT_ID = "blender"
_LOGIN_FORM_RE = re.compile(r'<form[^>]*id="kc-form-login"[^>]*action="([^"]+)"')
_GRANT_FORM_RE = re.compile(r'<form[^>]*action="([^"]*login-actions/consent[^"]*)"', re.IGNORECASE)
_HIDDEN_RE = re.compile(r'<input[^>]*type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"', re.IGNORECASE)


class DeviceLoginError(RuntimeError):
    """The device sign-in failed; the message holds no secret."""


class PersonaRefused(DeviceLoginError):
    """Keycloak showed the login form again: wrong password, or the persona does not exist (yet)."""


def grant_form(page: str) -> Optional[Dict[str, str]]:
    """The consent form Keycloak shows after the login (action + hidden fields + accept), or None."""
    match = _GRANT_FORM_RE.search(page or "")
    if not match:
        return None
    fields = {name: html.unescape(value) for name, value in _HIDDEN_RE.findall(page)}
    fields["accept"] = "Yes"
    return {"action": html.unescape(match.group(1)), **fields}


def poll_outcome(status: int, body: Dict) -> str:
    """'token' | 'pending' | 'slow_down' | 'error:<name>' for one token-endpoint answer."""
    if status == 200 and body.get("access_token"):
        return "token"
    err = body.get("error") or f"http_{status}"
    if err == "authorization_pending":
        return "pending"
    if err == "slow_down":
        return "slow_down"
    return f"error:{err}"


def device_token(issuer: str, username: str, password: str, *, verify=True, timeout: float = 60,
                 client_id: str = CLIENT_ID) -> Dict:
    """Run the device flow as `username`; return Keycloak's token response (access_token, refresh_token, ...)."""
    import httpx

    deadline = time.monotonic() + timeout
    with httpx.Client(follow_redirects=True, timeout=30, verify=verify) as c:
        r = c.post(f"{issuer}/protocol/openid-connect/auth/device", data={"client_id": client_id, "scope": "openid"})
        if r.status_code != 200:
            raise DeviceLoginError(f"device authorization refused: HTTP {r.status_code}")
        dev = r.json()
        page = c.get(dev["verification_uri_complete"])
        login = _LOGIN_FORM_RE.search(page.text)
        if login:
            # Keycloak may write form actions relative to the page: resolve them against the page's own URL.
            page = c.post(str(page.url.join(html.unescape(login.group(1)))),
                          data={"username": username, "password": password, "credentialId": ""})
            if _LOGIN_FORM_RE.search(page.text):
                raise PersonaRefused(f"Keycloak refused the sign-in of {username} (unknown persona or wrong password)")
        grant = grant_form(page.text)
        if grant:
            action = grant.pop("action")
            page = c.post(str(page.url.join(action)), data=grant)
        if page.status_code >= 400:
            raise DeviceLoginError(f"the verification page answered HTTP {page.status_code}")
        interval = int(dev.get("interval", 5))
        while time.monotonic() < deadline:
            t = c.post(f"{issuer}/protocol/openid-connect/token",
                       data={"grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                             "device_code": dev["device_code"], "client_id": client_id})
            try:
                body = t.json()
            except ValueError:
                body = {}
            outcome = poll_outcome(t.status_code, body)
            if outcome == "token":
                return body
            if outcome.startswith("error:"):
                raise DeviceLoginError(f"the token endpoint answered {outcome[6:]}")
            if outcome == "slow_down":
                interval += 5
            time.sleep(min(interval, max(0.0, deadline - time.monotonic())))
    raise DeviceLoginError(f"no token within {timeout:.0f} s (authorization still pending)")


def refresh(issuer: str, refresh_token: str, *, verify=True, client_id: str = CLIENT_ID) -> Dict:
    """A fresh token response from the refresh token (a measurement outlives one access token)."""
    import httpx

    r = httpx.post(f"{issuer}/protocol/openid-connect/token",
                   data={"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": client_id},
                   timeout=30, verify=verify)
    if r.status_code != 200:
        raise DeviceLoginError(f"the token refresh answered HTTP {r.status_code}")
    return r.json()


def revoke(issuer: str, refresh_token: str, *, verify=True, client_id: str = CLIENT_ID) -> bool:
    """End the SSO session the device sign-in opened (public client: client_id + refresh token)."""
    if not refresh_token:
        return False
    import httpx

    try:
        r = httpx.post(f"{issuer}/protocol/openid-connect/logout",
                       data={"client_id": client_id, "refresh_token": refresh_token}, timeout=15, verify=verify)
        return r.status_code in (200, 204)
    except httpx.HTTPError:
        return False
