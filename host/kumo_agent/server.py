"""HTTP API served to the VMs over the tap interface. Standard library only."""

from __future__ import annotations

import email.utils
import hashlib
import ipaddress
import json
import logging
import mimetypes
import os
import re
import socket
import threading
import time
import urllib.parse
import uuid
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__, disks
from .config import Config
from .store import Store, new_file_id

log = logging.getLogger("kumo-agent")

MIME = {
    ".mp4": "video/mp4", ".m4v": "video/mp4", ".m4a": "audio/mp4", ".webm": "video/webm",
    ".mkv": "video/x-matroska", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".vtt": "text/vtt; charset=utf-8", ".srt": "application/x-subrip",
    ".json": "application/json", ".nfo": "text/plain; charset=utf-8",
}
FILE_RE = re.compile(r"^/v1/files/([0-9a-f]{32})(/info|/move)?$")
RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
INCOMING = ".kumo-incoming"


class HTTPError(Exception):
    def __init__(self, status: int, message: str, **extra):
        super().__init__(message)
        self.status, self.message, self.extra = status, message, extra


class RateLimiter:
    """Counts failed authentications per IP over a sliding minute."""

    def __init__(self, limit: int):
        self.limit = limit
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def blocked(self, ip: str) -> bool:
        with self.lock:
            q = self.hits[ip]
            cutoff = time.monotonic() - 60
            while q and q[0] < cutoff:
                q.popleft()
            return len(q) >= self.limit

    def fail(self, ip: str) -> None:
        with self.lock:
            self.hits[ip].append(time.monotonic())


class Agent(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, cfg: Config, store: Store):
        self.cfg, self.store = cfg, store
        self.limiter = RateLimiter(cfg.auth_fail_limit)
        super().__init__((cfg.bind, cfg.port), Handler)


class Handler(BaseHTTPRequestHandler):
    server: Agent
    protocol_version = "HTTP/1.1"
    server_version = f"kumo-agent/{__version__}"
    sys_version = ""

    def log_message(self, fmt, *args):
        log.info("%s %s", self.client_address[0], fmt % args)

    def _dispatch(self, method: str):
        self.vm = None
        try:
            url = urllib.parse.urlsplit(self.path)
            self.query = urllib.parse.parse_qs(url.query)
            route = url.path.rstrip("/") or "/"
            if route == "/v1/health" and method in ("GET", "HEAD"):
                return self.send_json({"ok": True, "service": "kumo-agent", "version": __version__})
            self.authenticate()
            if route == "/v1/whoami" and method == "GET":
                return self.whoami()
            if route == "/v1/storage" and method == "GET":
                return self.storage()
            if route == "/v1/files":
                if method == "GET":
                    return self.list_files()
                if method == "PUT":
                    return self.upload()
                raise HTTPError(405, "method not allowed")
            m = FILE_RE.match(route)
            if m:
                fid, sub = m.group(1), m.group(2)
                if sub is None and method in ("GET", "HEAD"):
                    return self.stream(fid, head=method == "HEAD")
                if sub is None and method == "DELETE":
                    return self.delete(fid)
                if sub == "/info" and method == "GET":
                    return self.info(fid)
                if sub == "/move" and method == "POST":
                    return self.move(fid)
                raise HTTPError(405, "method not allowed")
            raise HTTPError(404, "not found")
        except HTTPError as e:
            if method == "PUT":
                # the request body may be unread
                self.close_connection = True
            self.send_json({"error": e.message, **e.extra}, e.status)
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            self.close_connection = True
        except Exception:  # never leak a traceback to the client
            log.exception("unhandled error on %s %s", method, self.path)
            try:
                self.send_json({"error": "internal error"}, 500)
            except OSError:
                self.close_connection = True

    def do_GET(self):
        self._dispatch("GET")

    def do_HEAD(self):
        self._dispatch("HEAD")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_POST(self):
        self._dispatch("POST")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if status == 401:
            self.send_header("WWW-Authenticate", 'Bearer realm="kumo"')
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def read_json(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > 64 * 1024:
            raise HTTPError(413, "body too large")
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            raise HTTPError(400, "invalid json") from None
        if not isinstance(data, dict):
            raise HTTPError(400, "expected an object")
        return data

    def authenticate(self):
        ip = self.client_address[0]
        limiter = self.server.limiter
        if limiter.blocked(ip):
            raise HTTPError(429, "too many failed attempts")
        auth = self.headers.get("Authorization", "")
        token = auth[7:].strip() if auth[:7].lower() == "bearer " else ""
        vm = self.server.store.vm_by_token(token) if token else None
        if not vm or not vm["enabled"] or not _ip_allowed(ip, vm["allowed_ips"]):
            limiter.fail(ip)
            self.server.store.audit("auth_fail", vm=vm["name"] if vm else None, ip=ip)
            raise HTTPError(401, "unauthorized")
        self.vm = vm
        self.server.store.touch_vm(vm["id"])

    def require_disk(self):
        vm = self.vm
        if not vm["disk_enabled"]:
            raise HTTPError(503, "disk disabled", code="disk_disabled")
        if not disks.is_mounted(vm["mountpoint"]):
            raise HTTPError(503, "disk offline", code="disk_offline")

    def vm_root(self) -> str:
        return os.path.join(self.vm["mountpoint"], self.vm["root"])

    def visible(self, row) -> str:
        """Path as the VM sees it: relative to its own root."""
        root = self.vm["root"]
        rel = row["relpath"]
        return rel[len(root) + 1:] if root and rel.startswith(root + "/") else rel

    def file_json(self, row) -> dict:
        return {
            "id": row["id"], "path": self.visible(row), "size": row["size"],
            "sha256": row["sha256"], "mime": row["mime"], "created_at": row["created_at"],
        }

    def get_file(self, fid):
        row = self.server.store.file(self.vm["id"], fid)
        if not row:
            raise HTTPError(404, "no such file")
        if not row["disk_enabled"] or not disks.is_mounted(row["mountpoint"]):
            raise HTTPError(503, "disk offline", code="disk_offline")
        return row, os.path.join(row["mountpoint"], row["relpath"])

    def whoami(self):
        vm = self.vm
        self.send_json({"name": vm["name"], "disk": vm["disk_label"], "root": vm["root"], "quota": vm["quota"]})

    def storage(self):
        vm = self.vm
        mounted = bool(vm["disk_enabled"]) and disks.is_mounted(vm["mountpoint"])
        u = disks.usage(vm["mountpoint"]) if mounted else {"total": 0, "free": 0, "used": 0}
        used = self.server.store.used_by(vm["id"])
        free = max(0, u["free"] - self.server.cfg.reserve)
        if vm["quota"]:
            free = min(free, max(0, vm["quota"] - used))
        self.send_json({
            "disk": vm["disk_label"], "online": mounted,
            "disk_total": u["total"], "disk_free": u["free"],
            "quota": vm["quota"], "used": used, "available": free,
            "reserve": self.server.cfg.reserve,
        })

    def list_files(self):
        prefix = (self.query.get("prefix") or [""])[0]
        limit = min(int((self.query.get("limit") or ["500"])[0]), 5000)
        offset = int((self.query.get("offset") or ["0"])[0])
        root = self.vm["root"]
        full = f"{root}/{prefix}" if root else prefix
        rows = self.server.store.files(self.vm["id"], full, limit, offset)
        self.send_json({"files": [self.file_json(r) for r in rows]})

    def info(self, fid):
        row, _ = self.get_file(fid)
        self.send_json(self.file_json(row))

    def upload(self):
        self.require_disk()
        cfg, store, vm = self.server.cfg, self.server.store, self.vm
        try:
            rel = disks.sanitize(urllib.parse.unquote(self.headers.get("X-Kumo-Path", "")))
        except ValueError as e:
            raise HTTPError(400, f"bad X-Kumo-Path: {e}") from None
        if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
            raise HTTPError(411, "chunked uploads are not supported, send Content-Length")
        try:
            length = int(self.headers["Content-Length"])
        except (KeyError, TypeError, ValueError):
            raise HTTPError(411, "Content-Length required") from None
        if length < 0:
            raise HTTPError(400, "bad Content-Length")

        u = disks.usage(vm["mountpoint"])
        if length > u["free"] - cfg.reserve:
            raise HTTPError(507, "not enough space on disk", code="disk_full", available=max(0, u["free"] - cfg.reserve))
        used = store.used_by(vm["id"])
        if vm["quota"] and used + length > vm["quota"]:
            raise HTTPError(507, "quota exceeded", code="quota", available=max(0, vm["quota"] - used))

        root = self.vm_root()
        incoming = os.path.join(root, INCOMING)
        os.makedirs(incoming, mode=0o750, exist_ok=True)
        tmp = os.path.join(incoming, uuid.uuid4().hex + ".part")
        want = (self.headers.get("X-Kumo-Sha256") or "").lower() or None
        h = hashlib.sha256()
        self.connection.settimeout(cfg.upload_timeout)
        try:
            with open(tmp, "wb") as out:
                left = length
                while left:
                    chunk = self.rfile.read(min(cfg.chunk_size, left))
                    if not chunk:
                        raise HTTPError(400, "upload truncated")
                    out.write(chunk)
                    h.update(chunk)
                    left -= len(chunk)
                out.flush()
                os.fsync(out.fileno())
            digest = h.hexdigest()
            if want and want != digest:
                raise HTTPError(422, "sha256 mismatch", expected=want, got=digest)
            dest = os.path.join(root, rel)
            if not disks.inside(root, dest):
                raise HTTPError(400, "path escapes root")
            final = disks.place(tmp, dest)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            self.close_connection = True
            raise

        fid = new_file_id()
        relpath = os.path.relpath(final, vm["mountpoint"]).replace(os.sep, "/")
        mime = MIME.get(os.path.splitext(final)[1].lower()) or mimetypes.guess_type(final)[0] or "application/octet-stream"
        store.add_file(fid, vm["id"], vm["disk_id"], relpath, length, digest, mime)
        store.audit("upload", vm=vm["name"], ip=self.client_address[0], detail=f"{fid} {relpath} {length}")
        row = store.file(vm["id"], fid)
        self.send_json(self.file_json(row), 201)

    def move(self, fid):
        row, src = self.get_file(fid)
        body = self.read_json()
        root = self.vm_root()
        try:
            if body.get("path"):
                rel = disks.sanitize(body["path"])
            elif "dir" in body:
                rel = disks.sanitize(f"{body['dir']}/{os.path.basename(src)}")
            else:
                raise HTTPError(400, "dir or path required")
        except ValueError as e:
            raise HTTPError(400, str(e)) from None
        dest = os.path.join(root, rel)
        if not disks.inside(root, dest):
            raise HTTPError(400, "path escapes root")
        if os.path.realpath(dest) != os.path.realpath(src):
            final = disks.place(src, dest)
            disks.prune_empty_dirs(src, root)
            relpath = os.path.relpath(final, row["mountpoint"]).replace(os.sep, "/")
            self.server.store.move_file(fid, relpath)
            self.server.store.audit("move", vm=self.vm["name"], ip=self.client_address[0], detail=f"{fid} -> {relpath}")
        self.send_json(self.file_json(self.server.store.file(self.vm["id"], fid)))

    def delete(self, fid):
        row, path = self.get_file(fid)
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        disks.prune_empty_dirs(path, self.vm_root())
        self.server.store.delete_file(fid)
        self.server.store.audit("delete", vm=self.vm["name"], ip=self.client_address[0], detail=f"{fid} {row['relpath']}")
        self.send_json({"deleted": fid})

    def stream(self, fid, head=False):
        row, path = self.get_file(fid)
        try:
            f = open(path, "rb")
        except FileNotFoundError:
            raise HTTPError(410, "file missing on disk", code="missing") from None
        with f:
            st = os.fstat(f.fileno())
            size = st.st_size
            etag = f'"{fid[:12]}-{size:x}-{int(st.st_mtime):x}"'
            lastmod = email.utils.formatdate(st.st_mtime, usegmt=True)
            if self.headers.get("If-None-Match") == etag:
                self.send_response(304)
                self.send_header("ETag", etag)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            start, end, status = 0, size - 1, 200
            rng = self.headers.get("Range")
            if_range = self.headers.get("If-Range")
            if rng and (not if_range or if_range in (etag, lastmod)):
                m = RANGE_RE.match(rng.strip())
                if not m or (not m[1] and not m[2]):
                    return self._unsatisfiable(size)
                if m[1]:
                    start = int(m[1])
                    end = min(int(m[2]), size - 1) if m[2] else size - 1
                else:  # suffix range: last N bytes
                    start = max(0, size - int(m[2]))
                if start >= size or start > end:
                    return self._unsatisfiable(size)
                status = 206

            length = end - start + 1 if size else 0
            self.send_response(status)
            self.send_header("Content-Type", row["mime"] or "application/octet-stream")
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("ETag", etag)
            self.send_header("Last-Modified", lastmod)
            self.send_header("Cache-Control", "private, max-age=3600")
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if head or not length:
                return
            f.seek(start)
            left, chunk = length, self.server.cfg.chunk_size
            while left:
                buf = f.read(min(chunk, left))
                if not buf:
                    break
                self.wfile.write(buf)
                left -= len(buf)

    def _unsatisfiable(self, size):
        self.send_response(416)
        self.send_header("Content-Range", f"bytes */{size}")
        self.send_header("Content-Length", "0")
        self.end_headers()


def _ip_allowed(ip: str, allowed: str) -> bool:
    if not allowed.strip():
        return True
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for item in allowed.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            if addr in ipaddress.ip_network(item, strict=False):
                return True
        except ValueError:
            continue
    return False
