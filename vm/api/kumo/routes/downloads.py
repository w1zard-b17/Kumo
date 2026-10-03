"""Fetch a link, then queue classified downloads and control the queue."""

from __future__ import annotations

import json
import shutil
import sqlite3
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from .. import agent, db, library, ytdl
from ..config import settings
from ..worker import worker

router = APIRouter()


class FetchIn(BaseModel):
    url: str
    playlist: bool = False


@router.post("/fetch")
async def fetch(body: FetchIn, c: sqlite3.Connection = Depends(db.get_db)):
    try:
        link = ytdl.parse_link(body.url, prefer_playlist=body.playlist)
    except ytdl.LinkError as e:
        raise HTTPException(422, {"code": e.code, "message": e.message}) from None
    try:
        preview = await run_in_threadpool(ytdl.fetch, link)
    except ytdl.LinkError as e:
        raise HTTPException(422, {"code": e.code, "message": e.message}) from None
    if preview["kind"] == "video" and preview["live"]:
        raise HTTPException(422, {"code": "live", "message": "Live streams and premieres aren't supported."})

    ids = [preview["youtube_id"]] if preview["kind"] == "video" else [e["youtube_id"] for e in preview["entries"]]
    dupes = {}
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        for r in c.execute(f"SELECT id, youtube_id, title, status FROM videos WHERE youtube_id IN "
                           f"({','.join('?' * len(chunk))})", chunk):
            dupes[r["youtube_id"]] = {"id": r["id"], "title": r["title"], "status": r["status"]}
    if preview["kind"] == "video":
        preview["duplicate"] = dupes.get(preview["youtube_id"])
        preview["in_playlist"] = link.playlist_id
    else:
        for e in preview["entries"]:
            e["duplicate"] = dupes.get(e["youtube_id"])
    return preview


class Item(BaseModel):
    youtube_id: str
    url: str
    title: str = Field(max_length=300)
    description: str = ""
    channel: str = ""
    duration: int = 0
    thumbnail: str | None = None
    year: int | None = None
    size_estimate: float | None = None


class Options(BaseModel):
    quality: Literal["720", "1080", "best"] = "1080"
    subtitles: bool = False
    sub_lang: str = "en"
    auto_subs: bool = True
    audio_fallback: bool = True


class Classification(BaseModel):
    type: Literal["documentary", "docuseries", "short", "lecture"] = "documentary"
    category_id: int
    subcategory: str = ""
    tags: list[str] = []
    year: int | None = None
    language: str = ""


class Meta(BaseModel):
    rating: int = Field(0, ge=0, le=5)
    watched: bool = False


class EnqueueIn(BaseModel):
    items: list[Item] = Field(min_length=1, max_length=500)
    options: Options = Options()
    classification: Classification | None = None   # None files the item under Unsorted
    meta: Meta = Meta()
    force: bool = False                            # ignore the disk space check


@router.post("/jobs", status_code=201)
def enqueue(body: EnqueueIn, c: sqlite3.Connection = Depends(db.get_db)):
    cls = body.classification
    if cls and not c.execute("SELECT 1 FROM categories WHERE id=?", (cls.category_id,)).fetchone():
        raise HTTPException(422, {"code": "category", "message": "Unknown category."})
    for it in body.items:
        if not ytdl.ID_RE.match(it.youtube_id):
            raise HTTPException(422, {"code": "invalid", "message": f"Bad video id {it.youtube_id!r}."})

    fresh, skipped, seen = [], [], set()
    for it in body.items:
        if it.youtube_id in seen or c.execute("SELECT 1 FROM videos WHERE youtube_id=?", (it.youtube_id,)).fetchone():
            skipped.append(it.youtube_id)
        else:
            fresh.append(it)
        seen.add(it.youtube_id)

    if not body.force and fresh:
        need = sum(it.size_estimate or 0 for it in fresh)
        try:
            space = agent.storage()
        except agent.AgentError as e:
            raise HTTPException(409, {"code": "storage_unreachable", "message": e.message}) from None
        if not space.get("online"):
            raise HTTPException(409, {"code": "storage_offline", "message": "The storage disk is offline."})
        if need and space["available"] < need * 1.05:
            raise HTTPException(409, {"code": "low_space", "message": "Not enough free space on the storage disk.",
                                      "needed": need, "available": space["available"]})
        tmp_free = shutil.disk_usage(settings.tmp).free
        biggest = max((it.size_estimate or 0) for it in fresh)
        if biggest and tmp_free < biggest * 1.1:
            raise HTTPException(409, {"code": "low_tmp", "message": "The VM's temp disk can't hold this download.",
                                      "needed": biggest, "available": tmp_free})

    now = time.time()
    created = []
    opts = body.options.model_dump()
    with db.tx(c):
        for it in fresh:
            cur = c.execute(
                """INSERT INTO videos(youtube_id, url, title, description, channel, duration, thumbnail_url, type,
                       category_id, subcategory, year, language, rating, classified, status, added_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'pending', ?, ?)""",
                (it.youtube_id, it.url, it.title.strip() or it.youtube_id, it.description, it.channel, it.duration,
                 it.thumbnail, cls.type if cls else "documentary", cls.category_id if cls else None,
                 cls.subcategory.strip() if cls else "", (cls.year if cls and cls.year else None) or it.year,
                 cls.language if cls else "", body.meta.rating, 1 if cls else 0, now, now),
            )
            vid = cur.lastrowid
            if cls and cls.tags:
                db.set_tags(c, vid, cls.tags)
            if body.meta.watched:
                c.execute("INSERT INTO playback(video_id, watched) VALUES (?,1)", (vid,))
            jcur = c.execute(
                "INSERT INTO jobs(video_id, url, title, options, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                (vid, it.url, it.title, json.dumps(opts), now, now),
            )
            created.append(jcur.lastrowid)
    worker.wake.set()
    jobs = [library.job_json(j) for j in c.execute(
        f"SELECT * FROM jobs WHERE id IN ({','.join('?' * len(created))})", created)] if created else []
    return {"jobs": jobs, "skipped": skipped}


ACTIVE = ("queued", "downloading", "converting", "uploading", "paused")
HISTORY = ("done", "failed", "canceled")


@router.get("/jobs")
def list_jobs(state: Literal["active", "history", "all"] = "all", limit: int = 200,
              c: sqlite3.Connection = Depends(db.get_db)):
    states = {"active": ACTIVE, "history": HISTORY, "all": ACTIVE + HISTORY}[state]
    rows = c.execute(
        f"""SELECT * FROM jobs WHERE status IN ({','.join('?' * len(states))})
            ORDER BY CASE WHEN status IN ('downloading','converting','uploading') THEN 0
                          WHEN status IN ('queued','paused') THEN 1 ELSE 2 END,
                     CASE WHEN status IN ('done','failed','canceled') THEN -COALESCE(finished_at, updated_at)
                          ELSE created_at END
            LIMIT ?""",
        (*states, limit),
    ).fetchall()
    return [library.job_json(r) for r in rows]


def _job(c: sqlite3.Connection, job_id: int) -> sqlite3.Row:
    j = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not j:
        raise HTTPException(404, "no such job")
    return j


def _set(c: sqlite3.Connection, job_id: int, **fields) -> dict:
    fields["updated_at"] = time.time()
    c.execute(f"UPDATE jobs SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?", (*fields.values(), job_id))
    return library.job_json(_job(c, job_id))


@router.post("/jobs/{job_id}/pause")
def pause(job_id: int, c: sqlite3.Connection = Depends(db.get_db)):
    j = _job(c, job_id)
    if j["status"] == "queued":
        return _set(c, job_id, status="paused")
    if j["status"] in ("downloading", "converting"):
        return _set(c, job_id, control="pause")
    raise HTTPException(409, f"can't pause a job that is {j['status']}")


@router.post("/jobs/{job_id}/resume")
def resume(job_id: int, c: sqlite3.Connection = Depends(db.get_db)):
    j = _job(c, job_id)
    if j["status"] != "paused":
        raise HTTPException(409, "job is not paused")
    out = _set(c, job_id, status="queued", control=None, next_attempt_at=None)
    worker.wake.set()
    return out


@router.post("/jobs/{job_id}/retry")
def retry(job_id: int, c: sqlite3.Connection = Depends(db.get_db)):
    j = _job(c, job_id)
    if j["status"] not in ("failed", "queued"):
        raise HTTPException(409, "only failed or waiting jobs can be retried")
    if not j["video_id"] or not c.execute("SELECT 1 FROM videos WHERE id=?", (j["video_id"],)).fetchone():
        raise HTTPException(409, "the video for this job was deleted")
    c.execute("UPDATE videos SET status='pending' WHERE id=? AND status='failed'", (j["video_id"],))
    out = _set(c, job_id, status="queued", control=None, error=None, attempts=0, next_attempt_at=None,
               finished_at=None, progress=0)
    worker.wake.set()
    return out


@router.post("/jobs/{job_id}/cancel")
def cancel(job_id: int, c: sqlite3.Connection = Depends(db.get_db)):
    j = _job(c, job_id)
    if j["status"] in ("downloading", "converting", "uploading"):
        return _set(c, job_id, control="cancel")
    if j["status"] in ("queued", "paused", "failed"):
        shutil.rmtree(settings.tmp / f"job-{job_id}", ignore_errors=True)
        out = _set(c, job_id, status="canceled", control=None, finished_at=time.time())
        c.execute("DELETE FROM videos WHERE id=? AND status!='ready'", (j["video_id"],))
        return out
    raise HTTPException(409, f"job is already {j['status']}")


@router.delete("/jobs/{job_id}")
def forget(job_id: int, c: sqlite3.Connection = Depends(db.get_db)):
    j = _job(c, job_id)
    if j["status"] not in HISTORY:
        raise HTTPException(409, "cancel the job first")
    c.execute("DELETE FROM jobs WHERE id=?", (job_id,))
    return {"deleted": job_id}


@router.delete("/jobs")
def clear_history(c: sqlite3.Connection = Depends(db.get_db)):
    n = c.execute(f"DELETE FROM jobs WHERE status IN ({','.join('?' * len(HISTORY))})", HISTORY).rowcount
    return {"deleted": n}
