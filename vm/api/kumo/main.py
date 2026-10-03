"""FastAPI app. Run with:  uvicorn kumo.main:app --workers 1 --host 127.0.0.1 --port 8000"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, auth, db
from .config import settings
from .routes import downloads, system, taxonomy, videos
from .worker import worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("kumo")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    if not settings.agent_token:
        log.warning("KUMO_AGENT_TOKEN is not set, the storage agent will refuse every request")
    if settings.worker:
        worker.start()
    yield
    worker.stop()


app = FastAPI(title="Kumo-Film", version=__version__, lifespan=lifespan, docs_url="/api/docs",
              openapi_url="/api/openapi.json", redoc_url=None)

protected = [Depends(auth.require)]
app.include_router(system.public, prefix="/api")
app.include_router(system.router, prefix="/api", dependencies=protected)
app.include_router(downloads.router, prefix="/api", dependencies=protected)
app.include_router(videos.router, prefix="/api", dependencies=protected)
app.include_router(taxonomy.router, prefix="/api", dependencies=protected)


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException):
    # one error shape for the frontend: {"code": ..., "message": ...}
    d = exc.detail
    body = d if isinstance(d, dict) else {"code": str(exc.status_code), "message": str(d)}
    return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(p) for p in first.get("loc", [])[1:])
    msg = first.get("msg", "invalid request")
    return JSONResponse({"code": "validation", "message": f"{where}: {msg}" if where else msg}, status_code=422)


# Development convenience: serve the built SPA without nginx (KUMO_WEB_DIST=../web/dist)
if settings.web_dist and Path(settings.web_dist).is_dir():
    dist = Path(settings.web_dist)
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        f = dist / path
        if path and f.is_file() and dist in f.resolve().parents:
            return FileResponse(f)
        return FileResponse(dist / "index.html")
