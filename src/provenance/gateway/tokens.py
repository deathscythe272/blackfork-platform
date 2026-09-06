"""Service identity tokens for the V1 slice.

Development stand-in for a real service-credential issuer: HS256 JWTs signed with a
key that lives only in the environment. Claims: `sub` is the agent identity the policy
reasons about, `aud` pins the token to this gateway, `exp` bounds replay.

Serves: BR-7 (identity on every call), BR-8 (spoofing mitigation, test T1-GW-01).
"""

from __future__ import annotations

import argparse
import datetime as dt
import os

import jwt

AUDIENCE = "blackfork-gateway"
ISSUER = "blackfork-dev-issuer"
ALGO = "HS256"


class IdentityError(Exception):
    """Raised when a token is missing, malformed, expired, or not for this gateway."""


def signing_key() -> str:
    key = os.environ.get("GATEWAY_SIGNING_KEY")
    if not key or len(key) < 32:
        raise IdentityError("GATEWAY_SIGNING_KEY must be set to at least 32 characters")
    return key


def mint(identity: str, ttl_seconds: int = 3600, key: str | None = None) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": identity,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(seconds=ttl_seconds)).timestamp()),
    }
    return jwt.encode(claims, key or signing_key(), algorithm=ALGO)


def verify(token: str, key: str | None = None) -> str:
    """Return the identity (`sub`) or raise IdentityError. Never returns a partial result."""
    try:
        claims = jwt.decode(
            token,
            key or signing_key(),
            algorithms=[ALGO],
            audience=AUDIENCE,
            issuer=ISSUER,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except jwt.PyJWTError as e:
        raise IdentityError(f"token rejected: {e.__class__.__name__}") from e
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise IdentityError("token has no subject")
    return sub


def main() -> None:
    ap = argparse.ArgumentParser(description="Mint a development service token.")
    ap.add_argument("identity")
    ap.add_argument("--ttl", type=int, default=3600)
    args = ap.parse_args()
    print(mint(args.identity, args.ttl))


if __name__ == "__main__":
    main()
