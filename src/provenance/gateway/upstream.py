"""How the gateway identifies itself to the evidence server.

On the laptop the evidence server sits on a private Compose network that only the
gateway can reach, and no header is needed. In the cloud there is no private network
between services, so the evidence server admits only callers that present a signed
identity token for its own address, and the only identity granted that right is the
gateway's. Set EVIDENCE_MCP_AUDIENCE to the evidence server's URL and every forwarded
call carries such a token, fetched from the platform's metadata server and cached
until shortly before it expires.

Serves: BR-7, BR-8.
"""

from __future__ import annotations

import base64
import json
import os
import threading
import time
from typing import Callable

Fetcher = Callable[[str], str]


def _default_fetcher(audience: str) -> str:
    from google.auth.transport.requests import Request  # cloud-only path; the laptop never imports this
    from google.oauth2 import id_token

    return id_token.fetch_id_token(Request(), audience)


def _expiry(token: str) -> float:
    """The exp claim of a JWT, read without verification (we only decide when to refresh)."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload)).get("exp", 0))
    except Exception:
        return 0.0


class UpstreamIdentity:
    def __init__(self, audience: str | None, fetcher: Fetcher = _default_fetcher, refresh_margin: float = 60.0):
        self.audience = audience
        self._fetch = fetcher
        self._margin = refresh_margin
        self._token: str | None = None
        self._exp = 0.0
        self._lock = threading.Lock()

    def headers(self) -> dict[str, str]:
        """Authorization header for the evidence server, or nothing when no audience is set."""
        if not self.audience:
            return {}
        with self._lock:
            if self._token is None or time.time() >= self._exp - self._margin:
                self._token = self._fetch(self.audience)
                self._exp = _expiry(self._token) or (time.time() + 300)
            return {"Authorization": f"Bearer {self._token}"}


def identity_from_env(env: dict[str, str] | None = None) -> UpstreamIdentity:
    env = os.environ if env is None else env
    return UpstreamIdentity(env.get("EVIDENCE_MCP_AUDIENCE") or None)
