"""Optional single-user password (KUMO_PASSWORD). Empty password = open to the LAN."""

from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import HTTPException, Request

from .config import settings

COOKIE = "kumo_session"
MAX_AGE = 60 * 60 * 24 * 30


def _sign(value: str) -> str:
    # the password is part of the MAC, so changing it logs every session out
    msg = f"{value}|{settings.password}".encode()
    return hmac.new(settings.secret.encode(), msg, hashlib.sha256).hexdigest()


def issue() -> str:
    exp = str(int(time.time()) + MAX_AGE)
    return f"{exp}.{_sign(exp)}"


def valid(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    exp, sig = token.split(".", 1)
    if not hmac.compare_digest(sig, _sign(exp)):
        return False
    return exp.isdigit() and int(exp) > time.time()


def check_password(password: str) -> bool:
    return bool(settings.password) and hmac.compare_digest(password.encode(), settings.password.encode())


def enabled() -> bool:
    return bool(settings.password)


def require(request: Request) -> None:
    """Router dependency, applied to the media endpoints too."""
    if enabled() and not valid(request.cookies.get(COOKIE)):
        raise HTTPException(401, "login required")
