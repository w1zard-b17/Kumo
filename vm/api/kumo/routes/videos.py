"""Library: browse, edit, reclassify, delete, stream, playback state."""

from __future__ import annotations

import sqlite3
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from .. import agent, db, library, media

router = APIRouter()

SORTS = {
    "added": "v.added_at",
    "title": "v.title COLLATE NOCASE",
    "duration": "v.duration",
    "year": "COALESCE(v.year, 0)",
    "last_watched": "COALESCE(p.last_played_at, 0)",
    "rating": "v.rating",
}


@router.get("/videos")
def list_videos(
    q: str = "",
    category: list[int] = Query(default=[]),
    type: list[str] = Query(default=[]),
    tag: list[str] = Query(default=[]),
    language: str = "",
    year_from: int | None = None,
    year_to: int | None = None,
    dur_min: int | None = None,
    dur_max: int | None = None,
    watched: bool | None = None,
    unsorted: bool | None = None,
    status: Literal["ready", "pending", "failed", "any"] = "ready",
    collection: int | None = None,
    sort: str = "added",
    order: Literal["asc", "desc"] = "desc",
    limit: int = Query(120, le=1000),
    offset: int = 0,
    c: sqlite3.Connection = Depends(db.get_db),
):
    where, args = [], []

    def add(sql: str, *params) -> None:
        where.append(sql)
        args.extend(params)

    if status != "any":
        add("v.status=?", status)
    for word in q.split():
        like = f"%{word}%"
        add("""(v.title LIKE ? OR v.description LIKE ? OR v.channel LIKE ? OR v.subcategory LIKE ?
                OR EXISTS (SELECT 1 FROM video_tags vt JOIN tags t ON t.id=vt.tag_id
                           WHERE vt.video_id=v.id AND t.name LIKE ?))""", *([like] * 5))
    if category:
        add(f"v.category_id IN ({','.join('?' * len(category))})", *category)
    if type:
        add(f"v.type IN ({','.join('?' * len(type))})", *type)
    for t in tag:
        add("EXISTS (SELECT 1 FROM video_tags vt JOIN tags t ON t.id=vt.tag_id "
            "WHERE vt.video_id=v.id AND t.name=?)", t)
    if language:
        add("v.language=?", language)
    if year_from is not None:
        add("v.year>=?", year_from)
    if year_to is not None:
        add("v.year<=?", year_to)
    if dur_min is not None:
        add("v.duration>=?", dur_min)
    if dur_max is not None:
        add("v.duration<=?", dur_max)
    if watched is not None:
        add("COALESCE(p.watched,0)=?", int(watched))
    if unsorted is not None:
        add("v.classified=?", 0 if unsorted else 1)
    if collection is not None:
        add("EXISTS (SELECT 1 FROM collection_items ci WHERE ci.video_id=v.id AND ci.collection_id=?)", collection)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    order_sql = f"{SORTS.get(sort, SORTS['added'])} {order.upper()}, v.id DESC"
    total = c.execute(
        f"SELECT COUNT(*) FROM videos v LEFT JOIN playback p ON p.video_id=v.id{clause}", args
    ).fetchone()[0]
    rows = c.execute(f"{library.LIST_SQL}{clause} ORDER BY {order_sql} LIMIT ? OFFSET ?", (*args, limit, offset))
    return {"total": total, "items": [library.serialize(r) for r in rows]}


@router.get("/home")
def home(c: sqlite3.Connection = Depends(db.get_db)):
    recent = c.execute(f"{library.LIST_SQL} WHERE v.status='ready' ORDER BY v.added_at DESC LIMIT 12")
    cont = c.execute(
        f"""{library.LIST_SQL} WHERE v.status='ready' AND p.position > 30 AND p.watched=0
            ORDER BY p.last_played_at DESC LIMIT 12"""
    )
    active = c.execute(
        """SELECT * FROM jobs WHERE status IN ('queued','downloading','converting','uploading','paused')
           ORDER BY CASE WHEN status IN ('downloading','converting','uploading') THEN 0 ELSE 1 END, created_at"""
    )
    stats = c.execute(
        """SELECT COUNT(*) AS videos, COALESCE(SUM(duration),0) AS seconds, COALESCE(SUM(file_size),0) AS bytes,
                  (SELECT COUNT(*) FROM videos WHERE classified=0 AND status='ready') AS unsorted
           FROM videos WHERE status='ready'"""
    ).fetchone()
    return {
        "recent": [library.serialize(r) for r in recent],
        "continue": [library.serialize(r) for r in cont],
        "active": [library.job_json(j) for j in active],
        "stats": dict(stats),
    }


def _video(c: sqlite3.Connection, video_id: int) -> dict:
    v = library.get_video(c, video_id)
    if not v:
        raise HTTPException(404, "no such video")
    return v


@router.get("/videos/{video_id}")
def get_video(video_id: int, c: sqlite3.Connection = Depends(db.get_db)):
    return _video(c, video_id)


class VideoPatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    description: str | None = None
    type: Literal["documentary", "docuseries", "short", "lecture"] | None = None
    category_id: int | None = None
    unsorted: bool | None = None          # true = move back to the Unsorted inbox
    subcategory: str | None = None
    year: int | None = None
    language: str | None = None
    rating: int | None = Field(None, ge=0, le=5)
    tags: list[str] | None = None
    watched: bool | None = None


def _storage_error(e: agent.AgentError) -> HTTPException:
    return HTTPException(502, {"code": e.code or "storage", "message": f"Storage host: {e.message}"})


@router.patch("/videos/{video_id}")
def patch_video(video_id: int, body: VideoPatch, c: sqlite3.Connection = Depends(db.get_db)):
    before = _video(c, video_id)
    data = body.model_dump(exclude_unset=True)
    fields = {k: data[k] for k in ("title", "description", "type", "subcategory", "year", "language", "rating")
              if k in data and data[k] is not None}
    if "year" in data and data["year"] is None:
        fields["year"] = None
    if data.get("category_id") is not None:
        if not c.execute("SELECT 1 FROM categories WHERE id=?", (data["category_id"],)).fetchone():
            raise HTTPException(422, "unknown category")
        fields.update(category_id=data["category_id"], classified=1)
    elif data.get("unsorted"):
        fields.update(category_id=None, classified=0)
    fields["updated_at"] = time.time()
    with db.tx(c):
        c.execute(f"UPDATE videos SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?", (*fields.values(), video_id))
        if body.tags is not None:
            db.set_tags(c, video_id, body.tags)
        if body.watched is not None:
            _set_watched(c, video_id, body.watched)
    if "category_id" in fields and fields["category_id"] != (before["category"] or {}).get("id"):
        try:
            library.relocate(c, video_id)
        except agent.AgentError as e:
            raise _storage_error(e) from None
    return _video(c, video_id)


def _set_watched(c: sqlite3.Connection, video_id: int, watched: bool) -> None:
    c.execute(
        """INSERT INTO playback(video_id, watched, position, last_played_at) VALUES (?,?,0,?)
           ON CONFLICT(video_id) DO UPDATE SET watched=excluded.watched,
               position=CASE WHEN excluded.watched=1 THEN 0 ELSE position END""",
        (video_id, int(watched), time.time() if watched else None),
    )


@router.delete("/videos/{video_id}")
def delete_video(video_id: int, c: sqlite3.Connection = Depends(db.get_db)):
    v = _video(c, video_id)
    if v["job"] and v["job"]["status"] in ("downloading", "converting", "uploading"):
        raise HTTPException(409, "cancel the download first")
    try:
        library.remove_files(c, video_id)
    except agent.AgentError as e:
        raise _storage_error(e) from None
    c.execute("DELETE FROM videos WHERE id=?", (video_id,))
    return {"deleted": video_id}


class BulkIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=1000)
    action: Literal["reclassify", "add_tags", "delete", "watched", "unwatched", "add_to_collection"]
    type: Literal["documentary", "docuseries", "short", "lecture"] | None = None
    category_id: int | None = None
    tags: list[str] = []
    collection_id: int | None = None


@router.post("/videos/bulk")
def bulk(body: BulkIn, c: sqlite3.Connection = Depends(db.get_db)):
    done, errors = 0, []
    if body.action == "reclassify" and body.category_id is not None:
        if not c.execute("SELECT 1 FROM categories WHERE id=?", (body.category_id,)).fetchone():
            raise HTTPException(422, "unknown category")
    if body.action == "add_to_collection":
        if not c.execute("SELECT 1 FROM collections WHERE id=?", (body.collection_id,)).fetchone():
            raise HTTPException(422, "unknown collection")
    for vid in body.ids:
        if not c.execute("SELECT 1 FROM videos WHERE id=?", (vid,)).fetchone():
            continue
        try:
            if body.action == "reclassify":
                fields = {"updated_at": time.time()}
                if body.type:
                    fields["type"] = body.type
                if body.category_id is not None:
                    fields.update(category_id=body.category_id, classified=1)
                c.execute(f"UPDATE videos SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?",
                          (*fields.values(), vid))
                library.relocate(c, vid)
            elif body.action == "add_tags":
                db.set_tags(c, vid, body.tags, replace=False)
            elif body.action in ("watched", "unwatched"):
                _set_watched(c, vid, body.action == "watched")
            elif body.action == "add_to_collection":
                c.execute("INSERT OR IGNORE INTO collection_items(collection_id, video_id, added_at) VALUES (?,?,?)",
                          (body.collection_id, vid, time.time()))
            elif body.action == "delete":
                library.remove_files(c, vid)
                c.execute("DELETE FROM videos WHERE id=?", (vid,))
            done += 1
        except agent.AgentError as e:
            errors.append({"id": vid, "error": e.message})
    return {"done": done, "errors": errors}


def _row(c: sqlite3.Connection, video_id: int) -> sqlite3.Row:
    r = c.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
    if not r:
        raise HTTPException(404, "no such video")
    return r


@router.get("/videos/{video_id}/stream")
def stream(video_id: int, request: Request, c: sqlite3.Connection = Depends(db.get_db)):
    r = _row(c, video_id)
    if r["status"] != "ready" or not r["file_id"]:
        raise HTTPException(409, "not downloaded yet")
    mime = "audio/mp4" if r["resolution"] == "audio" else "video/mp4"
    return media.serve(request, r["file_id"], mime)


@router.get("/videos/{video_id}/poster")
def poster(video_id: int, request: Request, c: sqlite3.Connection = Depends(db.get_db)):
    r = _row(c, video_id)
    if r["poster_file_id"]:
        return media.serve(request, r["poster_file_id"], "image/jpeg", cached=True)
    if r["thumbnail_url"]:
        return RedirectResponse(r["thumbnail_url"], 302)
    return RedirectResponse(f"https://i.ytimg.com/vi/{r['youtube_id']}/hqdefault.jpg", 302)


@router.get("/videos/{video_id}/subtitles/{sub_id}")
def subtitle(video_id: int, sub_id: int, request: Request, c: sqlite3.Connection = Depends(db.get_db)):
    s = c.execute("SELECT * FROM subtitles WHERE id=? AND video_id=?", (sub_id, video_id)).fetchone()
    if not s:
        raise HTTPException(404, "no such subtitle")
    return media.serve(request, s["file_id"], "text/vtt", cached=True)


class PlaybackIn(BaseModel):
    position: float = Field(ge=0)
    duration: float = Field(ge=0)


@router.put("/videos/{video_id}/playback")
def save_playback(video_id: int, body: PlaybackIn, c: sqlite3.Connection = Depends(db.get_db)):
    _row(c, video_id)
    reached = body.duration > 0 and body.position >= body.duration * 0.9
    c.execute(
        """INSERT INTO playback(video_id, position, duration, watched, last_played_at) VALUES (?,?,?,?,?)
           ON CONFLICT(video_id) DO UPDATE SET position=excluded.position, duration=excluded.duration,
               watched=MAX(watched, excluded.watched), last_played_at=excluded.last_played_at""",
        (video_id, body.position, body.duration, int(reached), time.time()),
    )
    p = c.execute("SELECT * FROM playback WHERE video_id=?", (video_id,)).fetchone()
    return {"position": p["position"], "duration": p["duration"], "watched": bool(p["watched"])}


# sendBeacon on page unload can only POST
router.add_api_route("/videos/{video_id}/playback", save_playback, methods=["POST"], include_in_schema=False)


@router.get("/videos/{video_id}/next")
def next_up(video_id: int, c: sqlite3.Connection = Depends(db.get_db)):
    """Next in the same series (subcategory), else an unwatched pick from the same category."""
    r = _row(c, video_id)
    base = f"{library.LIST_SQL} WHERE v.status='ready' AND v.id!=? AND COALESCE(p.watched,0)=0"
    if r["subcategory"]:
        row = c.execute(
            f"{base} AND v.subcategory=? AND v.category_id IS ? AND v.added_at>=? ORDER BY v.added_at LIMIT 1",
            (video_id, r["subcategory"], r["category_id"], r["added_at"]),
        ).fetchone() or c.execute(
            f"{base} AND v.subcategory=? AND v.category_id IS ? ORDER BY v.added_at LIMIT 1",
            (video_id, r["subcategory"], r["category_id"]),
        ).fetchone()
        if row:
            return {"reason": "series", "video": library.serialize(row)}
    if r["category_id"]:
        row = c.execute(f"{base} AND v.category_id=? ORDER BY v.added_at DESC LIMIT 1",
                        (video_id, r["category_id"])).fetchone()
        if row:
            return {"reason": "category", "video": library.serialize(row)}
    return {"reason": None, "video": None}
