"""HTTP basic authentication and cross-site websocket protection."""

import asyncio
import base64
import binascii
import hmac
from typing import Optional
from urllib.parse import urlsplit

import aiohttp.web

# Delay applied to every failed login to slow down password guessing.
FAILED_LOGIN_DELAY = 1.0


def parse_basic_auth(header: Optional[str]) -> Optional[tuple[str, str]]:
    """Return (user, password) from an Authorization header, or None."""
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "basic" or not token:
        return None
    try:
        decoded = base64.b64decode(token.strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None
    user, sep, password = decoded.partition(":")
    if not sep:
        return None
    return user, password


def credentials_match(given: Optional[tuple[str, str]], username: str, password: str) -> bool:
    if given is None:
        return False
    # Compare both fields so timing does not reveal which one was wrong.
    user_ok = hmac.compare_digest(given[0].encode(), username.encode())
    pass_ok = hmac.compare_digest(given[1].encode(), password.encode())
    return user_ok and pass_ok


def origin_allowed(origin: Optional[str], host: Optional[str]) -> bool:
    """Browsers always send Origin on websocket handshakes: it has to match Host."""
    if origin is None:
        return True  # not a browser request
    return urlsplit(origin).netloc.lower() == (host or "").lower()


def make_auth_middleware(username: str, password: str):
    @aiohttp.web.middleware
    async def auth_middleware(request: aiohttp.web.Request, handler):
        if not origin_allowed(request.headers.get("Origin"), request.host):
            raise aiohttp.web.HTTPForbidden(text="cross-origin request refused")

        given = parse_basic_auth(request.headers.get("Authorization"))
        if not credentials_match(given, username, password):
            await asyncio.sleep(FAILED_LOGIN_DELAY if given else 0)
            raise aiohttp.web.HTTPUnauthorized(
                headers={"WWW-Authenticate": 'Basic realm="web-rdp", charset="UTF-8"'},
                text="authentication required",
            )

        return await handler(request)

    return auth_middleware
