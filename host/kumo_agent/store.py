"""SQLite state: disks, VMs with hashed tokens, files and an audit log."""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS disks (
    id          INTEGER PRIMARY KEY,
    label       TEXT NOT NULL UNIQUE,
    mountpoint  TEXT NOT NULL UNIQUE,
    device      TEXT,                          -- disklabel DUID, informational
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vms (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    token_hash  TEXT NOT NULL UNIQUE,
    allowed_ips TEXT NOT NULL DEFAULT '',      -- comma separated IPs / CIDRs, empty = any
    disk_id     INTEGER NOT NULL REFERENCES disks(id),
    root        TEXT NOT NULL,                 -- directory under the disk mountpoint
    quota       INTEGER NOT NULL DEFAULT 0,    -- bytes, 0 = unlimited
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    last_seen   TEXT
);
CREATE TABLE IF NOT EXISTS files (
    id          TEXT PRIMARY KEY,              -- opaque hex id
    vm_id       INTEGER NOT NULL REFERENCES vms(id) ON DELETE CASCADE,
    disk_id     INTEGER NOT NULL REFERENCES disks(id),
    relpath     TEXT NOT NULL,                 -- relative to the disk mountpoint
    size        INTEGER NOT NULL,
    sha256      TEXT,
    mime        TEXT,
    created_at  TEXT NOT NULL,
    UNIQUE (disk_id, relpath)
);
CREATE INDEX IF NOT EXISTS files_vm ON files(vm_id);
CREATE TABLE IF NOT EXISTS audit (
    id      INTEGER PRIMARY KEY,
    ts      TEXT NOT NULL,
    vm      TEXT,
    ip      TEXT,
    action  TEXT NOT NULL,
    detail  TEXT
);
"""


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> str:
    return "kumo_" + secrets.token_urlsafe(32)


def new_file_id() -> str:
    return secrets.token_hex(16)


class Store:
    def __init__(self, path: str):
        self.path = path
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, mode=0o700, exist_ok=True)
        with self.conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self):
        c = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("PRAGMA synchronous=NORMAL")
        try:
            yield c
        finally:
            c.close()

    def disks(self):
        with self.conn() as c:
            return c.execute("SELECT * FROM disks ORDER BY label").fetchall()

    def disk(self, key):
        with self.conn() as c:
            col = "id" if isinstance(key, int) else "label"
            return c.execute(f"SELECT * FROM disks WHERE {col}=?", (key,)).fetchone()

    def add_disk(self, label, mountpoint, device=None):
        with self.conn() as c:
            c.execute(
                "INSERT INTO disks(label, mountpoint, device, created_at) VALUES (?,?,?,?)",
                (label, os.path.normpath(mountpoint), device, now()),
            )

    def set_disk(self, label, **fields):
        self._update("disks", "label", label, fields)

    def remove_disk(self, label):
        with self.conn() as c:
            d = c.execute("SELECT id FROM disks WHERE label=?", (label,)).fetchone()
            if not d:
                raise KeyError(label)
            used = c.execute(
                "SELECT (SELECT COUNT(*) FROM vms WHERE disk_id=?) + (SELECT COUNT(*) FROM files WHERE disk_id=?)",
                (d["id"], d["id"]),
            ).fetchone()[0]
            if used:
                raise ValueError("disk still has VMs or files assigned")
            c.execute("DELETE FROM disks WHERE id=?", (d["id"],))

    def vms(self):
        with self.conn() as c:
            return c.execute(
                """SELECT v.*, d.label AS disk_label, d.mountpoint,
                          COALESCE((SELECT SUM(size) FROM files f WHERE f.vm_id=v.id),0) AS used,
                          (SELECT COUNT(*) FROM files f WHERE f.vm_id=v.id) AS nfiles
                   FROM vms v JOIN disks d ON d.id=v.disk_id ORDER BY v.name"""
            ).fetchall()

    def vm(self, name):
        with self.conn() as c:
            return c.execute(
                """SELECT v.*, d.label AS disk_label, d.mountpoint, d.enabled AS disk_enabled
                   FROM vms v JOIN disks d ON d.id=v.disk_id WHERE v.name=?""",
                (name,),
            ).fetchone()

    def vm_by_token(self, token):
        with self.conn() as c:
            return c.execute(
                """SELECT v.*, d.label AS disk_label, d.mountpoint, d.enabled AS disk_enabled
                   FROM vms v JOIN disks d ON d.id=v.disk_id WHERE v.token_hash=?""",
                (hash_token(token),),
            ).fetchone()

    def add_vm(self, name, disk_label, root, allowed_ips="", quota=0) -> str:
        token = new_token()
        with self.conn() as c:
            d = c.execute("SELECT id FROM disks WHERE label=?", (disk_label,)).fetchone()
            if not d:
                raise KeyError(f"unknown disk {disk_label!r}")
            c.execute(
                """INSERT INTO vms(name, token_hash, allowed_ips, disk_id, root, quota, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (name, hash_token(token), allowed_ips, d["id"], root.strip("/"), quota, now()),
            )
        return token

    def rotate_token(self, name) -> str:
        token = new_token()
        self._update("vms", "name", name, {"token_hash": hash_token(token)})
        return token

    def set_vm(self, name, **fields):
        self._update("vms", "name", name, fields)

    def remove_vm(self, name):
        with self.conn() as c:
            if not c.execute("DELETE FROM vms WHERE name=?", (name,)).rowcount:
                raise KeyError(name)

    def touch_vm(self, vm_id):
        with self.conn() as c:
            c.execute("UPDATE vms SET last_seen=? WHERE id=?", (now(), vm_id))

    def used_by(self, vm_id) -> int:
        with self.conn() as c:
            return c.execute("SELECT COALESCE(SUM(size),0) FROM files WHERE vm_id=?", (vm_id,)).fetchone()[0]

    def file(self, vm_id, file_id):
        with self.conn() as c:
            return c.execute(
                """SELECT f.*, d.mountpoint, d.enabled AS disk_enabled FROM files f
                   JOIN disks d ON d.id=f.disk_id WHERE f.id=? AND f.vm_id=?""",
                (file_id, vm_id),
            ).fetchone()

    def files(self, vm_id, prefix="", limit=500, offset=0):
        with self.conn() as c:
            return c.execute(
                """SELECT f.*, d.mountpoint FROM files f JOIN disks d ON d.id=f.disk_id
                   WHERE f.vm_id=? AND f.relpath LIKE ? ESCAPE '\\'
                   ORDER BY f.relpath LIMIT ? OFFSET ?""",
                (vm_id, _like_prefix(prefix), limit, offset),
            ).fetchall()

    def add_file(self, file_id, vm_id, disk_id, relpath, size, sha256, mime):
        with self.conn() as c:
            c.execute(
                """INSERT INTO files(id, vm_id, disk_id, relpath, size, sha256, mime, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (file_id, vm_id, disk_id, relpath, size, sha256, mime, now()),
            )

    def move_file(self, file_id, relpath):
        with self.conn() as c:
            c.execute("UPDATE files SET relpath=? WHERE id=?", (relpath, file_id))

    def delete_file(self, file_id):
        with self.conn() as c:
            c.execute("DELETE FROM files WHERE id=?", (file_id,))

    def audit(self, action, vm=None, ip=None, detail=None):
        with self.conn() as c:
            c.execute(
                "INSERT INTO audit(ts, vm, ip, action, detail) VALUES (?,?,?,?,?)",
                (now(), vm, ip, action, detail),
            )

    def audit_log(self, limit=50):
        with self.conn() as c:
            return c.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    _WRITABLE = {
        "disks": {"mountpoint", "device", "enabled"},
        "vms": {"token_hash", "allowed_ips", "disk_id", "root", "quota", "enabled"},
    }

    def _update(self, table, keycol, key, fields):
        bad = set(fields) - self._WRITABLE[table]
        if bad:
            raise ValueError(f"cannot set {', '.join(sorted(bad))}")
        if not fields:
            return
        sets = ", ".join(f"{k}=?" for k in fields)
        with self.conn() as c:
            if not c.execute(f"UPDATE {table} SET {sets} WHERE {keycol}=?", (*fields.values(), key)).rowcount:
                raise KeyError(key)


def _like_prefix(prefix: str) -> str:
    return prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
