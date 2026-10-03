"""Categories, tags and collections."""

from __future__ import annotations

import sqlite3
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import agent, db, library

router = APIRouter()

HEX = r"^#[0-9a-fA-F]{6}$"


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    color: str = Field("#2be080", pattern=HEX)
    icon: str = Field("film", max_length=24)


class CategoryPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=40)
    color: str | None = Field(None, pattern=HEX)
    icon: str | None = Field(None, max_length=24)
    position: int | None = None


@router.get("/categories")
def categories(c: sqlite3.Connection = Depends(db.get_db)):
    rows = c.execute(
        """SELECT c.*, (SELECT COUNT(*) FROM videos v WHERE v.category_id=c.id AND v.status='ready') AS count
           FROM categories c ORDER BY c.position, c.name"""
    )
    unsorted = c.execute("SELECT COUNT(*) FROM videos WHERE classified=0 AND status='ready'").fetchone()[0]
    return {"categories": [dict(r) for r in rows], "unsorted": unsorted, "types": db.TYPES}


@router.post("/categories", status_code=201)
def add_category(body: CategoryIn, c: sqlite3.Connection = Depends(db.get_db)):
    pos = c.execute("SELECT COALESCE(MAX(position),0)+1 FROM categories").fetchone()[0]
    try:
        cur = c.execute("INSERT INTO categories(name, color, icon, position) VALUES (?,?,?,?)",
                        (body.name.strip(), body.color, body.icon, pos))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "a category with that name exists") from None
    return dict(c.execute("SELECT * FROM categories WHERE id=?", (cur.lastrowid,)).fetchone())


def _videos_in(c: sqlite3.Connection, category_id: int) -> list[int]:
    return [r["id"] for r in c.execute("SELECT id FROM videos WHERE category_id=?", (category_id,))]


@router.patch("/categories/{cat_id}")
def patch_category(cat_id: int, body: CategoryPatch, c: sqlite3.Connection = Depends(db.get_db)):
    old = c.execute("SELECT * FROM categories WHERE id=?", (cat_id,)).fetchone()
    if not old:
        raise HTTPException(404, "no such category")
    fields = body.model_dump(exclude_none=True)
    if "name" in fields:
        fields["name"] = fields["name"].strip()
    if fields:
        try:
            c.execute(f"UPDATE categories SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?",
                      (*fields.values(), cat_id))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "a category with that name exists") from None
    moved_errors = []
    if "name" in fields and library.safe(fields["name"]) != library.safe(old["name"]):
        # the folder on the storage host follows the category name
        for vid in _videos_in(c, cat_id):
            try:
                library.relocate(c, vid)
            except agent.AgentError as e:
                moved_errors.append({"id": vid, "error": e.message})
    out = dict(c.execute("SELECT * FROM categories WHERE id=?", (cat_id,)).fetchone())
    out["errors"] = moved_errors
    return out


@router.delete("/categories/{cat_id}")
def delete_category(cat_id: int, c: sqlite3.Connection = Depends(db.get_db)):
    if not c.execute("SELECT 1 FROM categories WHERE id=?", (cat_id,)).fetchone():
        raise HTTPException(404, "no such category")
    videos = _videos_in(c, cat_id)
    c.execute("UPDATE videos SET category_id=NULL, classified=0, updated_at=? WHERE category_id=?",
              (time.time(), cat_id))
    c.execute("DELETE FROM categories WHERE id=?", (cat_id,))
    errors = []
    for vid in videos:  # into the Unsorted inbox, on disk too
        try:
            library.relocate(c, vid)
        except agent.AgentError as e:
            errors.append({"id": vid, "error": e.message})
    return {"deleted": cat_id, "unsorted": len(videos), "errors": errors}


class TagPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=40)
    color: str | None = Field(None, pattern=HEX)


@router.get("/tags")
def tags(c: sqlite3.Connection = Depends(db.get_db)):
    rows = c.execute(
        """SELECT t.*, COUNT(vt.video_id) AS count FROM tags t LEFT JOIN video_tags vt ON vt.tag_id=t.id
           GROUP BY t.id ORDER BY count DESC, t.name COLLATE NOCASE"""
    )
    return [dict(r) for r in rows]


@router.patch("/tags/{tag_id}")
def patch_tag(tag_id: int, body: TagPatch, c: sqlite3.Connection = Depends(db.get_db)):
    fields = body.model_dump(exclude_none=True)
    if fields:
        try:
            n = c.execute(f"UPDATE tags SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?",
                          (*fields.values(), tag_id)).rowcount
        except sqlite3.IntegrityError:
            raise HTTPException(409, "a tag with that name exists") from None
        if not n:
            raise HTTPException(404, "no such tag")
    return dict(c.execute("SELECT * FROM tags WHERE id=?", (tag_id,)).fetchone() or {})


@router.delete("/tags/{tag_id}")
def delete_tag(tag_id: int, c: sqlite3.Connection = Depends(db.get_db)):
    c.execute("DELETE FROM tags WHERE id=?", (tag_id,))
    return {"deleted": tag_id}


class CollectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    description: str = Field("", max_length=500)


class CollectionPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=60)
    description: str | None = Field(None, max_length=500)


class VideoIds(BaseModel):
    video_ids: list[int] = Field(min_length=1)


def _collection(c: sqlite3.Connection, cid: int) -> dict:
    r = c.execute(
        """SELECT c.*, (SELECT COUNT(*) FROM collection_items i JOIN videos v ON v.id=i.video_id
                        WHERE i.collection_id=c.id AND v.status='ready') AS count
           FROM collections c WHERE c.id=?""", (cid,)
    ).fetchone()
    if not r:
        raise HTTPException(404, "no such collection")
    out = dict(r)
    out["posters"] = [
        f"/api/videos/{x['id']}/poster?v={int(x['updated_at'])}"
        for x in c.execute(
            """SELECT v.id, v.updated_at FROM collection_items i JOIN videos v ON v.id=i.video_id
               WHERE i.collection_id=? AND v.status='ready' ORDER BY i.added_at DESC LIMIT 4""", (cid,))
    ]
    return out


@router.get("/collections")
def collections(c: sqlite3.Connection = Depends(db.get_db)):
    ids = [r["id"] for r in c.execute("SELECT id FROM collections ORDER BY name COLLATE NOCASE")]
    return [_collection(c, i) for i in ids]


@router.post("/collections", status_code=201)
def add_collection(body: CollectionIn, c: sqlite3.Connection = Depends(db.get_db)):
    try:
        cur = c.execute("INSERT INTO collections(name, description, created_at) VALUES (?,?,?)",
                        (body.name.strip(), body.description, time.time()))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "a collection with that name exists") from None
    return _collection(c, cur.lastrowid)


@router.get("/collections/{cid}")
def get_collection(cid: int, c: sqlite3.Connection = Depends(db.get_db)):
    return _collection(c, cid)


@router.patch("/collections/{cid}")
def patch_collection(cid: int, body: CollectionPatch, c: sqlite3.Connection = Depends(db.get_db)):
    _collection(c, cid)
    fields = body.model_dump(exclude_none=True)
    if fields:
        try:
            c.execute(f"UPDATE collections SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?",
                      (*fields.values(), cid))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "a collection with that name exists") from None
    return _collection(c, cid)


@router.delete("/collections/{cid}")
def delete_collection(cid: int, c: sqlite3.Connection = Depends(db.get_db)):
    c.execute("DELETE FROM collections WHERE id=?", (cid,))
    return {"deleted": cid}


@router.post("/collections/{cid}/videos")
def add_to_collection(cid: int, body: VideoIds, c: sqlite3.Connection = Depends(db.get_db)):
    _collection(c, cid)
    now = time.time()
    for vid in body.video_ids:
        c.execute(
            """INSERT OR IGNORE INTO collection_items(collection_id, video_id, added_at)
               SELECT ?, id, ? FROM videos WHERE id=?""", (cid, now, vid))
    return _collection(c, cid)


@router.delete("/collections/{cid}/videos/{vid}")
def remove_from_collection(cid: int, vid: int, c: sqlite3.Connection = Depends(db.get_db)):
    c.execute("DELETE FROM collection_items WHERE collection_id=? AND video_id=?", (cid, vid))
    return _collection(c, cid)
