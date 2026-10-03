"""Media responses. Production: X-Accel-Redirect so nginx streams from the agent
with Range support and near-zero RAM. Development: FastAPI relays the bytes."""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from . import agent
from .config import settings

PASS_HEADERS = ("content-type", "content-length", "content-range", "accept-ranges", "etag", "last-modified")


def serve(request: Request, file_id: str, mime: str, cached: bool = False) -> Response:
    if settings.accel:
        location = "/_agent_cached/" if cached else "/_agent/"
        return Response(
            status_code=200,
            media_type=mime,
            headers={"X-Accel-Redirect": location + file_id, "Cache-Control": "private, max-age=3600"},
        )
    try:
        conn, r = agent.open_stream(file_id, dict(request.headers))
    except agent.AgentError as e:
        raise HTTPException(502, e.message) from None
    if r.status >= 400:
        conn.close()
        raise HTTPException(503 if r.status == 503 else 404, "media unavailable")

    def body():
        try:
            while chunk := r.read(256 * 1024):
                yield chunk
        finally:
            conn.close()

    headers = {k: v for k, v in r.getheaders() if k.lower() in PASS_HEADERS}
    return StreamingResponse(body(), status_code=r.status, headers=headers)
