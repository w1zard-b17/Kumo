"""Settings, storage status, system info and login."""

from __future__ import annotations

import json
import shutil
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .. import __version__, agent, auth, db, ytdl
from ..config import settings

router = APIRouter()
public = APIRouter()


class LoginIn(BaseModel):
    password: str


@public.get("/auth")
def auth_status(request: Request):
    return {"required": auth.enabled(), "authenticated": not auth.enabled() or auth.valid(request.cookies.get(auth.COOKIE))}


@public.post("/auth/login")
def login(body: LoginIn, response: Response):
    if not auth.enabled():
        return {"authenticated": True}
    if not auth.check_password(body.password):
        raise HTTPException(401, "wrong password")
    response.set_cookie(auth.COOKIE, auth.issue(), max_age=auth.MAX_AGE, httponly=True, samesite="lax")
    return {"authenticated": True}


@public.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(auth.COOKIE)
    return {"authenticated": False}


@public.get("/health")
def health():
    return {"ok": True, "version": __version__}


class SettingsPatch(BaseModel):
    quality: Literal["720", "1080", "best"] | None = None
    subtitles: bool | None = None
    sub_lang: str | None = Field(None, max_length=12)
    auto_subs: bool | None = None
    audio_fallback: bool | None = None
    naming: str | None = Field(None, min_length=1, max_length=80)
    language: str | None = Field(None, max_length=12)
    autoplay_next: bool | None = None


@router.get("/settings")
def get_settings(c: sqlite3.Connection = Depends(db.get_db)):
    return db.get_settings(c)


@router.patch("/settings")
def patch_settings(body: SettingsPatch, c: sqlite3.Connection = Depends(db.get_db)):
    data = body.model_dump(exclude_none=True)
    if "naming" in data and "{title}" not in data["naming"] and "{youtube_id}" not in data["naming"]:
        raise HTTPException(422, "the naming pattern needs {title} or {youtube_id}")
    for k, v in data.items():
        c.execute("INSERT INTO settings(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                  (k, json.dumps(v)))
    return db.get_settings(c)


@router.get("/storage")
def storage():
    try:
        s = agent.storage()
    except agent.AgentError as e:
        return {"reachable": False, "error": e.message}
    return {"reachable": True, **s}


@router.get("/system")
def system(c: sqlite3.Connection = Depends(db.get_db)):
    try:
        a = agent.health()
        agent_info = {"reachable": True, "version": a.get("version")}
    except agent.AgentError as e:
        agent_info = {"reachable": False, "error": e.message}
    tmp = shutil.disk_usage(settings.tmp)
    return {
        "version": __version__,
        "yt_dlp": ytdl.version(),
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "agent": agent_info,
        "agent_url": settings.agent_url,
        "tmp": {"free": tmp.free, "total": tmp.total},
        "auth": auth.enabled(),
        "db_size": settings.db.stat().st_size if settings.db.exists() else 0,
    }
