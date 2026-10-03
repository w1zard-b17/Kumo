"""Client for the host storage agent (kumo-agent on the OpenBSD host)."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import urllib.parse
from typing import Callable

from .config import settings

CHUNK = 256 * 1024


class AgentError(Exception):
    def __init__(self, status: int, message: str, code: str | None = None, data: dict | None = None):
        super().__init__(message)
        self.status, self.message, self.code, self.data = status, message, code, data or {}

    @property
    def transient(self) -> bool:
        # 0 = network error; 5xx = agent/disk trouble; 507 (full) is not worth retrying blindly
        return self.status == 0 or (self.status >= 500 and self.status != 507)


def _conn(timeout: float = 30) -> http.client.HTTPConnection:
    u = urllib.parse.urlsplit(settings.agent_url)
    return http.client.HTTPConnection(u.hostname, u.port or 80, timeout=timeout)


def _headers(extra: dict | None = None) -> dict:
    return {"Authorization": f"Bearer {settings.agent_token}", **(extra or {})}


def request(method: str, path: str, body: dict | None = None, timeout: float = 15) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    headers = _headers({"Content-Type": "application/json"} if data else None)
    c = _conn(timeout)
    try:
        c.request(method, path, body=data, headers=headers)
        r = c.getresponse()
        raw = r.read()
    except OSError as e:
        raise AgentError(0, f"storage agent unreachable: {e}") from None
    finally:
        c.close()
    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        payload = {}
    if r.status >= 400:
        raise AgentError(r.status, payload.get("error", f"agent returned {r.status}"), payload.get("code"), payload)
    return payload


def health() -> dict:
    return request("GET", "/v1/health", timeout=5)


def storage() -> dict:
    return request("GET", "/v1/storage", timeout=5)


def move(file_id: str, directory: str) -> dict:
    return request("POST", f"/v1/files/{file_id}/move", {"dir": directory})


def delete(file_id: str) -> None:
    try:
        request("DELETE", f"/v1/files/{file_id}")
    except AgentError as e:
        if e.status != 404:
            raise


def upload(
    path: str,
    relpath: str,
    on_progress: Callable[[int, int], None] | None = None,
    should_stop: Callable[[], None] | None = None,
) -> dict:
    """Stream a local file to the agent. Hashes while sending and checks the agent's digest."""
    size = os.path.getsize(path)
    c = _conn(timeout=120)
    h = hashlib.sha256()
    sent = 0
    try:
        c.putrequest("PUT", "/v1/files", skip_accept_encoding=True)
        for k, v in _headers({
            "Content-Length": str(size),
            "Content-Type": "application/octet-stream",
            "X-Kumo-Path": urllib.parse.quote(relpath),
        }).items():
            c.putheader(k, v)
        c.endheaders()
        try:
            with open(path, "rb") as f:
                while chunk := f.read(CHUNK):
                    c.send(chunk)
                    h.update(chunk)
                    sent += len(chunk)
                    if on_progress:
                        on_progress(sent, size)
                    if should_stop:
                        should_stop()
        except (BrokenPipeError, ConnectionResetError):
            pass  # the agent refused early; its response below says why
        r = c.getresponse()
        raw = r.read()
    except OSError as e:
        raise AgentError(0, f"upload failed: {e}") from None
    finally:
        c.close()
    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        payload = {}
    if r.status >= 400:
        raise AgentError(r.status, payload.get("error", f"agent returned {r.status}"), payload.get("code"), payload)
    if payload.get("sha256") != h.hexdigest() or payload.get("size") != size:
        delete(payload.get("id", ""))
        raise AgentError(0, "upload corrupted in transit (checksum mismatch)")
    return payload


def open_stream(file_id: str, headers: dict) -> tuple[http.client.HTTPConnection, http.client.HTTPResponse]:
    """Development fallback when nginx is not in front: FastAPI relays the bytes itself."""
    c = _conn(timeout=60)
    fwd = {k: v for k, v in headers.items() if k.lower() in ("range", "if-range", "if-none-match")}
    try:
        c.request("GET", f"/v1/files/{file_id}", headers=_headers(fwd))
        return c, c.getresponse()
    except OSError as e:
        c.close()
        raise AgentError(0, f"storage agent unreachable: {e}") from None
