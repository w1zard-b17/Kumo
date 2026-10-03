"""Library helpers shared by the routes and the worker: naming, folders, serialisation."""

from __future__ import annotations

import json
import re
import sqlite3

from . import agent
from .db import UNSORTED_DIR, TYPES

_UNSAFE = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|]+')


def safe(text: str, limit: int = 120) -> str:
    t = _UNSAFE.sub(" ", text or "").strip().strip(".")
    t = re.sub(r"\s+", " ", t)
    return t[:limit].rstrip() or "untitled"


def render_name(pattern: str, v: dict) -> str:
    values = {
        "title": v.get("title") or "",
        "year": str(v.get("year") or ""),
        "channel": v.get("channel") or "",
        "youtube_id": v.get("youtube_id") or "",
        "type": TYPES.get(v.get("type") or "", ""),
    }
    try:
        name = (pattern or "{title}").format(**values)
    except (KeyError, IndexError, ValueError):
        name = values["title"]
    name = re.sub(r"\(\s*\)|\[\s*\]", "", name)          # "Title ()" when there's no year
    name = re.sub(r"\s*-\s*$|^\s*-\s*", "", name.strip())
    return safe(name)


def category_dir(c: sqlite3.Connection, category_id: int | None) -> str:
    if category_id is None:
        return UNSORTED_DIR
    row = c.execute("SELECT name FROM categories WHERE id=?", (category_id,)).fetchone()
    return safe(row["name"]) if row else UNSORTED_DIR


def file_ids(c: sqlite3.Connection, video_id: int) -> list[str]:
    v = c.execute("SELECT file_id, poster_file_id FROM videos WHERE id=?", (video_id,)).fetchone()
    ids = [v["file_id"], v["poster_file_id"]] if v else []
    ids += [r["file_id"] for r in c.execute("SELECT file_id FROM subtitles WHERE video_id=?", (video_id,))]
    return [i for i in ids if i]


def relocate(c: sqlite3.Connection, video_id: int) -> None:
    """Move a ready video's files into its category folder on the storage host."""
    v = c.execute("SELECT status, category_id, file_id, storage_path FROM videos WHERE id=?", (video_id,)).fetchone()
    if not v or v["status"] != "ready" or not v["file_id"]:
        return
    target = category_dir(c, v["category_id"])
    if (v["storage_path"] or "").split("/")[0] == target:
        return
    new_path = None
    for fid in file_ids(c, video_id):
        res = agent.move(fid, target)
        if fid == v["file_id"]:
            new_path = res.get("path")
    if new_path:
        c.execute("UPDATE videos SET storage_path=? WHERE id=?", (new_path, video_id))


def remove_files(c: sqlite3.Connection, video_id: int) -> None:
    for fid in file_ids(c, video_id):
        agent.delete(fid)


LIST_SQL = """
SELECT v.*, c.name AS category_name, c.color AS category_color, c.icon AS category_icon,
       p.position AS pb_position, p.duration AS pb_duration, p.watched AS pb_watched,
       p.last_played_at AS pb_last_played_at,
       (SELECT GROUP_CONCAT(t.name, char(31)) FROM video_tags vt JOIN tags t ON t.id = vt.tag_id
         WHERE vt.video_id = v.id) AS tag_list
FROM videos v
LEFT JOIN categories c ON c.id = v.category_id
LEFT JOIN playback p ON p.video_id = v.id
"""


def serialize(r: sqlite3.Row, full: bool = False) -> dict:
    out = {
        "id": r["id"],
        "youtube_id": r["youtube_id"],
        "title": r["title"],
        "channel": r["channel"],
        "duration": r["duration"],
        "poster": f"/api/videos/{r['id']}/poster?v={int(r['updated_at'])}",
        "type": r["type"],
        "category": {"id": r["category_id"], "name": r["category_name"], "color": r["category_color"],
                     "icon": r["category_icon"]} if r["category_id"] else None,
        "subcategory": r["subcategory"],
        "year": r["year"],
        "language": r["language"],
        "rating": r["rating"],
        "tags": sorted(r["tag_list"].split("\x1f"), key=str.lower) if r["tag_list"] else [],
        "status": r["status"],
        "classified": bool(r["classified"]),
        "resolution": r["resolution"],
        "file_size": r["file_size"],
        "added_at": r["added_at"],
        "playback": {
            "position": r["pb_position"] or 0,
            "duration": r["pb_duration"] or r["duration"] or 0,
            "watched": bool(r["pb_watched"]),
            "last_played_at": r["pb_last_played_at"],
        },
    }
    if full:
        out.update({
            "url": r["url"],
            "description": r["description"],
            "storage_path": r["storage_path"],
            "chapters": json.loads(r["chapters"] or "[]"),
            "thumbnail_url": r["thumbnail_url"],
        })
    return out


def get_video(c: sqlite3.Connection, video_id: int, full: bool = True) -> dict | None:
    r = c.execute(LIST_SQL + " WHERE v.id=?", (video_id,)).fetchone()
    if not r:
        return None
    out = serialize(r, full)
    if full:
        out["subtitles"] = [
            {"id": s["id"], "lang": s["lang"], "label": s["label"],
             "src": f"/api/videos/{video_id}/subtitles/{s['id']}"}
            for s in c.execute("SELECT * FROM subtitles WHERE video_id=? ORDER BY lang", (video_id,))
        ]
        out["collections"] = [
            {"id": x["id"], "name": x["name"]}
            for x in c.execute(
                """SELECT c.id, c.name FROM collections c JOIN collection_items i ON i.collection_id=c.id
                   WHERE i.video_id=? ORDER BY c.name""", (video_id,))
        ]
        job = c.execute("SELECT * FROM jobs WHERE video_id=? ORDER BY id DESC LIMIT 1", (video_id,)).fetchone()
        out["job"] = job_json(job) if job else None
    return out


def job_json(j: sqlite3.Row) -> dict:
    return {
        "id": j["id"],
        "video_id": j["video_id"],
        "url": j["url"],
        "title": j["title"],
        "poster": f"/api/videos/{j['video_id']}/poster" if j["video_id"] else None,
        "status": j["status"],
        "progress": round(j["progress"] or 0, 1),
        "speed": j["speed"],
        "eta": j["eta"],
        "downloaded_bytes": j["downloaded_bytes"],
        "total_bytes": j["total_bytes"],
        "options": json.loads(j["options"] or "{}"),
        "error": j["error"],
        "attempts": j["attempts"],
        "next_attempt_at": j["next_attempt_at"],
        "created_at": j["created_at"],
        "finished_at": j["finished_at"],
    }
