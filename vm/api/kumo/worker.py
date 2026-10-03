"""Download worker: one job at a time, driven by the jobs table.

yt-dlp writes into a per-job temp folder, ffmpeg remuxes to MP4, the files are
streamed to the storage agent, then the temp folder is removed. Jobs move
through queued, downloading, converting, uploading and done, and can end up
paused, canceled or failed; transient failures are retried with backoff.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import sqlite3
import threading
import time
from pathlib import Path

from . import agent, db, library, ytdl
from .config import settings

log = logging.getLogger("kumo.worker")

ACTIVE = ("downloading", "converting", "uploading")
MEDIA_EXT = {".mp4", ".m4a", ".mkv", ".webm", ".mov"}


class Stop(Exception):
    """Raised in the yt-dlp hooks and upload loop when the user pauses or cancels."""

    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind


class Permanent(Exception):
    """Not worth retrying (private video, disk full, ...)."""


def _stop_exc(kind: str) -> BaseException:
    # yt-dlp re-raises DownloadCancelled untouched, so use it when available
    try:
        from yt_dlp.utils import DownloadCancelled

        class _Cancelled(DownloadCancelled):
            pass

        e = _Cancelled(kind)
        e.kind = kind  # type: ignore[attr-defined]
        return e
    except ImportError:
        return Stop(kind)


class Worker(threading.Thread):
    def __init__(self) -> None:
        super().__init__(name="kumo-worker", daemon=True)
        self.wake = threading.Event()
        self.halt = threading.Event()
        self.c: sqlite3.Connection | None = None

    def run(self) -> None:
        self.c = db.connect()
        self.c.execute(
            f"UPDATE jobs SET status='queued', control=NULL WHERE status IN ({','.join('?' * len(ACTIVE))})", ACTIVE
        )
        while not self.halt.is_set():
            try:
                job = self.claim()
            except sqlite3.Error:
                log.exception("claim failed")
                job = None
            if not job:
                self.wake.wait(3)
                self.wake.clear()
                continue
            try:
                self.process(job)
            except Exception:  # the loop must survive anything
                log.exception("job %s crashed", job["id"])
                self.update(job["id"], status="failed", error="internal error, see logs", finished_at=time.time())

    def stop(self) -> None:
        self.halt.set()
        self.wake.set()

    def claim(self) -> sqlite3.Row | None:
        c = self.c
        with db.tx(c):
            job = c.execute(
                """SELECT * FROM jobs WHERE status='queued' AND (next_attempt_at IS NULL OR next_attempt_at<=?)
                   ORDER BY created_at, id LIMIT 1""",
                (time.time(),),
            ).fetchone()
            if job:
                c.execute("UPDATE jobs SET status='downloading', error=NULL, updated_at=? WHERE id=?",
                          (time.time(), job["id"]))
        return job

    def update(self, job_id: int, **fields) -> None:
        fields["updated_at"] = time.time()
        sets = ", ".join(f"{k}=?" for k in fields)
        self.c.execute(f"UPDATE jobs SET {sets} WHERE id=?", (*fields.values(), job_id))

    def control(self, job_id: int) -> str | None:
        r = self.c.execute("SELECT control FROM jobs WHERE id=?", (job_id,)).fetchone()
        return r["control"] if r else "cancel"

    def process(self, job: sqlite3.Row) -> None:
        jid = job["id"]
        work = settings.tmp / f"job-{jid}"
        work.mkdir(parents=True, exist_ok=True)
        options = json.loads(job["options"] or "{}")
        video = self.c.execute("SELECT * FROM videos WHERE id=?", (job["video_id"],)).fetchone()
        if not video:
            self.update(jid, status="canceled", error="video was removed", finished_at=time.time())
            shutil.rmtree(work, ignore_errors=True)
            return
        try:
            info = self.download(jid, job["url"], work, options)
            if (c := self.control(jid)) in ("pause", "cancel"):
                raise Stop(c)
            self.update(jid, status="uploading", progress=0)
            self.store(jid, video, work, info, options)
        except Stop as s:
            self.stopped(jid, video, work, s.kind)
            return
        except Exception as e:
            kind = getattr(e, "kind", None)
            if kind in ("pause", "cancel"):
                self.stopped(jid, video, work, kind)
                return
            self.failed(job, video, e)
            return
        shutil.rmtree(work, ignore_errors=True)
        self.update(jid, status="done", progress=100, control=None, speed=None, eta=None, finished_at=time.time())
        log.info("job %s done: %s", jid, video["title"])

    def stopped(self, jid: int, video: sqlite3.Row, work: Path, kind: str) -> None:
        if kind == "pause":
            self.update(jid, status="paused", control=None, speed=None, eta=None)
            return
        shutil.rmtree(work, ignore_errors=True)
        self.update(jid, status="canceled", control=None, speed=None, eta=None, finished_at=time.time())
        v = self.c.execute("SELECT status FROM videos WHERE id=?", (video["id"],)).fetchone()
        if v and v["status"] != "ready":
            self.c.execute("DELETE FROM videos WHERE id=?", (video["id"],))

    def failed(self, job: sqlite3.Row, video: sqlite3.Row, e: Exception) -> None:
        jid = job["id"]
        attempts = job["attempts"] + 1
        if isinstance(e, agent.AgentError):
            msg, retry = e.message, e.transient
        elif isinstance(e, Permanent):
            msg, retry = str(e), False
        else:
            err = ytdl.classify_error(e)
            msg, retry = err.message, err.code not in ytdl.PERMANENT
        if retry and attempts < settings.max_attempts:
            delay = min(30 * 2 ** (attempts - 1), 900)
            log.warning("job %s attempt %d failed (%s), retrying in %ds", jid, attempts, msg, delay)
            self.update(jid, status="queued", attempts=attempts, error=f"{msg}, retrying",
                        next_attempt_at=time.time() + delay, speed=None, eta=None)
            return
        log.error("job %s failed: %s", jid, msg)
        self.update(jid, status="failed", attempts=attempts, error=msg, speed=None, eta=None, finished_at=time.time())
        self.c.execute("UPDATE videos SET status='failed', updated_at=? WHERE id=? AND status!='ready'",
                       (time.time(), video["id"]))

    def download(self, jid: int, url: str, work: Path, options: dict) -> dict:
        import yt_dlp

        last = {"t": 0.0}

        def progress(d: dict) -> None:
            now = time.time()
            if d.get("status") == "downloading" and now - last["t"] >= 1:
                last["t"] = now
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes") or 0
                # merged downloads run video then audio, so progress is per file
                pct = (done / total * 100) if total else 0
                self.update(jid, progress=min(pct, 99.9), downloaded_bytes=done, total_bytes=total or None,
                            speed=d.get("speed"), eta=d.get("eta"))
                c = self.control(jid)
                if c in ("pause", "cancel"):
                    raise _stop_exc(c)

        def postprocess(d: dict) -> None:
            if d.get("status") == "started" and d.get("postprocessor") in (
                "Merger", "FFmpegVideoRemuxer", "FFmpegExtractAudio", "FFmpegVideoConvertor"
            ):
                self.update(jid, status="converting", progress=100, speed=None, eta=None)

        def run(opts: dict) -> dict:
            with yt_dlp.YoutubeDL(ytdl.download_opts(str(work), opts, progress, postprocess)) as ydl:
                return ydl.extract_info(url, download=True) or {}

        try:
            return run(options)
        except yt_dlp.utils.DownloadError as e:
            low = str(e).lower()
            if options.get("subtitles") and "subtitle" in low:
                log.warning("job %s: subtitles failed, continuing without (%s)", jid, e)
                return run({**options, "subtitles": False})
            if options.get("audio_fallback") and "requested format is not available" in low:
                log.warning("job %s: no video formats, falling back to audio only", jid)
                return run({**options, "audio_only": True})
            raise

    def store(self, jid: int, video: sqlite3.Row, work: Path, info: dict, options: dict) -> None:
        media = sorted((p for p in work.iterdir() if p.suffix.lower() in MEDIA_EXT and p.stem == "video"),
                       key=lambda p: p.stat().st_size, reverse=True)
        if not media:
            raise Permanent("download produced no media file")
        media_file = media[0]
        poster = next((p for p in work.glob("poster.jpg")), None) or next(iter(work.glob("poster.*")), None)
        subs = pick_subtitles(work, options.get("sub_lang") or "en")

        c = self.c
        # the title may have been reclassified or deleted while it downloaded
        video = c.execute("SELECT * FROM videos WHERE id=?", (video["id"],)).fetchone()
        if not video:
            raise Stop("cancel")
        settings_ = db.get_settings(c)
        base = library.render_name(settings_.get("naming", "{title}"), dict(video))
        folder = library.category_dir(c, video["category_id"])

        files = [(media_file, f"{folder}/{base}{media_file.suffix.lower()}")]
        if poster:
            files.append((poster, f"{folder}/{base}{poster.suffix.lower()}"))
        files += [(p, f"{folder}/{base}.{lang}.vtt") for lang, p in subs]
        total = sum(p.stat().st_size for p, _ in files)

        try:
            space = agent.storage()
        except agent.AgentError:
            space = None
        if space is not None:
            if not space.get("online"):
                raise agent.AgentError(503, "storage disk is offline", "disk_offline")
            if space.get("available", 0) < total:
                raise Permanent(f"not enough space on the storage disk ({total} bytes needed)")

        sent_before = 0
        uploaded: dict[Path, dict] = {}
        last = {"t": 0.0}

        def on_progress(sent: int, _size: int) -> None:
            now = time.time()
            if now - last["t"] >= 1:
                last["t"] = now
                self.update(jid, progress=min((sent_before + sent) / total * 100, 99.9) if total else 0,
                            downloaded_bytes=sent_before + sent, total_bytes=total)

        checked = {"t": 0.0}

        def should_stop() -> None:
            # uploads can be canceled but not paused: a half-sent file can't be resumed
            now = time.time()
            if now - checked["t"] < 1:
                return
            checked["t"] = now
            if self.control(jid) == "cancel":
                raise Stop("cancel")

        try:
            for path, rel in files:
                uploaded[path] = agent.upload(str(path), rel, on_progress, should_stop)
                sent_before += path.stat().st_size
        except BaseException:
            for res in uploaded.values():  # never leave half an item on the host
                try:
                    agent.delete(res["id"])
                except agent.AgentError:
                    pass
            raise

        m = uploaded[media_file]
        height = info.get("height")
        resolution = "audio" if media_file.suffix.lower() == ".m4a" else (f"{height}p" if height else None)
        now = time.time()
        with db.tx(c):
            if not c.execute("SELECT 1 FROM videos WHERE id=?", (video["id"],)).fetchone():
                for res in uploaded.values():
                    agent.delete(res["id"])
                raise Stop("cancel")
            c.execute(
                """UPDATE videos SET file_id=?, poster_file_id=?, file_size=?, resolution=?, storage_path=?,
                       status='ready', chapters=?, duration=COALESCE(NULLIF(duration,0), ?),
                       description=CASE WHEN description='' THEN ? ELSE description END, updated_at=?
                   WHERE id=?""",
                (m["id"], uploaded[poster]["id"] if poster else None, m["size"], resolution, m["path"],
                 json.dumps(ytdl.chapters(info)), int(info.get("duration") or 0),
                 (info.get("description") or "")[:5000], now, video["id"]),
            )
            for lang, p in subs:
                c.execute("INSERT INTO subtitles(video_id, lang, label, file_id) VALUES (?,?,?,?)",
                          (video["id"], lang, lang_label(lang), uploaded[p]["id"]))


def pick_subtitles(work: Path, lang: str) -> list[tuple[str, Path]]:
    """Keep the best of subs.en.vtt / subs.en-US.vtt / subs.en-orig.vtt."""
    found = {}
    for p in work.glob("subs.*.vtt"):
        code = p.name[len("subs."):-len(".vtt")]
        found[code] = p
    if not found:
        return []
    rank = sorted(found, key=lambda k: (k != lang, k.endswith("-orig"), not k.startswith(lang), k))
    best = rank[0]
    return [(re.sub(r"-orig$", "", best), found[best])]


LANGS = {
    "en": "English", "it": "Italiano", "fr": "Français", "de": "Deutsch", "es": "Español", "pt": "Português",
    "ja": "日本語", "nl": "Nederlands", "ru": "Русский", "zh": "中文", "ko": "한국어", "ar": "العربية",
    "pl": "Polski", "sv": "Svenska", "tr": "Türkçe",
}


def lang_label(code: str) -> str:
    return LANGS.get(code.split("-")[0].lower(), code)


worker = Worker()
