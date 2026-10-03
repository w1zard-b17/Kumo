"""yt-dlp integration: link validation, metadata preview, download options.

yt-dlp is imported lazily so the API starts fast and stays small until a link
is fetched.
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass

ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
YT_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtube-nocookie.com",
            "www.youtube-nocookie.com"}


class LinkError(Exception):
    """A link problem the UI can show. The code is stable."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass
class Link:
    kind: str                   # video | playlist
    video_id: str | None
    playlist_id: str | None

    @property
    def canonical(self) -> str:
        if self.kind == "playlist":
            return f"https://www.youtube.com/playlist?list={self.playlist_id}"
        return f"https://www.youtube.com/watch?v={self.video_id}"


def parse_link(raw: str, prefer_playlist: bool = False) -> Link:
    text = (raw or "").strip()
    if not text:
        raise LinkError("empty", "Paste a YouTube link.")
    if ID_RE.match(text):
        return Link("video", text, None)
    if "://" not in text:
        text = "https://" + text
    u = urllib.parse.urlsplit(text)
    host = (u.hostname or "").lower()
    q = urllib.parse.parse_qs(u.query)
    parts = [p for p in u.path.split("/") if p]
    vid = pl = None
    if host in ("youtu.be", "www.youtu.be"):
        vid = parts[0] if parts else None
    elif host in YT_HOSTS:
        if parts[:1] == ["watch"]:
            vid = (q.get("v") or [None])[0]
        elif parts[:1] in (["shorts"], ["live"], ["embed"], ["v"]) and len(parts) > 1:
            vid = parts[1]
        elif parts[:1] == ["playlist"]:
            pass
        elif not parts:
            raise LinkError("invalid", "That's the YouTube home page, not a video.")
        else:
            raise LinkError("unsupported", "Channel and search pages aren't supported. Paste a video or playlist link.")
    else:
        raise LinkError("invalid", "That doesn't look like a YouTube link.")
    pl = (q.get("list") or [None])[0]
    if pl and pl.startswith(("RD", "UL")):   # mixes and radio, not real playlists
        pl = None
    if vid and not ID_RE.match(vid):
        raise LinkError("invalid", "The video id in that link is malformed.")
    if pl and (prefer_playlist or not vid):
        return Link("playlist", vid, pl)
    if vid:
        return Link("video", vid, pl)
    raise LinkError("invalid", "No video or playlist found in that link.")


_ERRORS = [
    (("private video",), "private", "This video is private."),
    (("sign in to confirm your age", "age-restricted", "inappropriate for some users"), "age_restricted",
     "This video is age-restricted and needs a signed-in account."),
    (("not available in your country", "geo restrict", "blocked it in your country", "geo-restricted"),
     "geo_blocked", "This video is blocked in the VM's region."),
    (("members-only", "join this channel"), "members_only", "This video is for channel members only."),
    (("live event will begin", "premieres in", "this live event", "is live", "live stream"), "live",
     "Live streams and premieres aren't supported. Try again once it has finished."),
    (("sign in to confirm you", "not a bot"), "bot_check", "YouTube is asking for a bot check. Update yt-dlp or try later."),
    (("video unavailable", "has been removed", "does not exist", "account associated", "terminated"),
     "unavailable", "This video is unavailable."),
    (("unable to download webpage", "timed out", "temporary failure", "connection", "network is unreachable",
      "http error 5", "remote end closed"), "network", "Network problem while talking to YouTube."),
]
PERMANENT = {"private", "age_restricted", "geo_blocked", "members_only", "live", "unavailable", "invalid"}


def classify_error(err: BaseException | str) -> LinkError:
    msg = str(err)
    low = msg.lower()
    for needles, code, text in _ERRORS:
        if any(n in low for n in needles):
            return LinkError(code, text)
    clean = re.sub(r"^ERROR:\s*(\[[^\]]+\]\s*\S+:\s*)?", "", msg.strip())
    return LinkError("error", clean[:300] or "yt-dlp failed")


def version() -> str | None:
    try:
        from yt_dlp.version import __version__
        return __version__
    except ImportError:
        return None


def _base_opts() -> dict:
    return {"quiet": True, "no_warnings": True, "noprogress": True, "skip_download": True,
            "socket_timeout": 20, "retries": 3, "extractor_retries": 2}


def fetch(link: Link) -> dict:
    try:
        import yt_dlp
    except ImportError:
        raise LinkError("missing", "yt-dlp is not installed on the VM.") from None
    opts = _base_opts()
    if link.kind == "playlist":
        opts["extract_flat"] = "in_playlist"
    else:
        opts["noplaylist"] = True
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(link.canonical, download=False)
    except yt_dlp.utils.DownloadError as e:
        raise classify_error(e) from None
    if not info:
        raise LinkError("unavailable", "Nothing found at that link.")
    return playlist_preview(info) if link.kind == "playlist" else video_preview(info)


def _thumb(info: dict) -> str | None:
    if info.get("thumbnail"):
        return info["thumbnail"]
    thumbs = [t for t in info.get("thumbnails") or [] if t.get("url")]
    thumbs.sort(key=lambda t: (t.get("width") or 0) * (t.get("height") or 0))
    if thumbs:
        return thumbs[-1]["url"]
    return f"https://i.ytimg.com/vi/{info['id']}/hqdefault.jpg" if info.get("id") else None


def _year(info: dict) -> int | None:
    d = info.get("release_date") or info.get("upload_date") or ""
    return int(d[:4]) if len(d) >= 4 and d[:4].isdigit() else (info.get("release_year") or None)


def video_preview(info: dict) -> dict:
    live = info.get("live_status") in ("is_live", "is_upcoming", "post_live") or info.get("is_live")
    subs = sorted((info.get("subtitles") or {}).keys())
    auto = sorted(k for k in (info.get("automatic_captions") or {}).keys() if "-" not in k or k.endswith("-orig"))
    return {
        "kind": "video",
        "youtube_id": info["id"],
        "url": f"https://www.youtube.com/watch?v={info['id']}",
        "title": info.get("title") or info["id"],
        "description": (info.get("description") or "")[:5000],
        "channel": info.get("channel") or info.get("uploader") or "",
        "duration": int(info.get("duration") or 0),
        "thumbnail": _thumb(info),
        "year": _year(info),
        "language": info.get("language") or "",
        "tags": (info.get("tags") or [])[:15],
        "chapters": chapters(info),
        "live": bool(live),
        "age_limit": info.get("age_limit") or 0,
        "subtitles": subs,
        "auto_subtitles": auto,
        "heights": sorted({f["height"] for f in info.get("formats") or [] if f.get("height") and f.get("vcodec") != "none"}),
        "estimates": estimates(info),
    }


def playlist_preview(info: dict) -> dict:
    entries = []
    for e in info.get("entries") or []:
        if not e or not e.get("id") or not ID_RE.match(e["id"]):
            continue
        entries.append({
            "youtube_id": e["id"],
            "url": f"https://www.youtube.com/watch?v={e['id']}",
            "title": e.get("title") or e["id"],
            "channel": e.get("channel") or e.get("uploader") or "",
            "duration": int(e.get("duration") or 0),
            "thumbnail": _thumb(e),
            "unavailable": (e.get("title") or "") in ("[Private video]", "[Deleted video]"),
        })
    return {
        "kind": "playlist",
        "playlist_id": info.get("id"),
        "title": info.get("title") or "Playlist",
        "channel": info.get("channel") or info.get("uploader") or "",
        "thumbnail": entries[0]["thumbnail"] if entries else None,
        "entries": entries,
    }


def chapters(info: dict) -> list[dict]:
    return [
        {"start": float(c.get("start_time") or 0), "end": float(c.get("end_time") or 0), "title": c.get("title") or ""}
        for c in info.get("chapters") or []
    ]


def _fsize(f: dict, duration: float) -> float:
    return f.get("filesize") or f.get("filesize_approx") or ((f.get("tbr") or 0) * 125 * duration)


def estimates(info: dict) -> dict:
    """Rough final MP4 size per quality choice, in bytes."""
    formats = info.get("formats") or []
    dur = float(info.get("duration") or 0)
    audio = [f for f in formats if f.get("vcodec") == "none" and f.get("acodec") not in (None, "none")]
    video = [f for f in formats if f.get("vcodec") not in (None, "none") and f.get("height")]
    a = max(audio, key=lambda f: (f.get("ext") == "m4a", f.get("abr") or f.get("tbr") or 0), default=None)
    a_size = _fsize(a, dur) if a else 0

    def pick(maxh: int | None, compat: bool) -> float | None:
        c = [f for f in video if maxh is None or f["height"] <= maxh]
        if not c:
            return None
        key = (lambda f: (f["height"], (f.get("vcodec") or "").startswith("avc"), f.get("tbr") or 0)) if compat \
            else (lambda f: (f["height"], f.get("tbr") or 0))
        best = max(c, key=key)
        size = _fsize(best, dur)
        return size + (a_size if best.get("acodec") in (None, "none") else 0) if size else None

    return {
        "720": pick(720, True),
        "1080": pick(1080, True),
        "best": pick(None, False),
        "audio": a_size or None,
    }


FORMATS = {
    # H.264 + AAC in the capped modes remuxes to MP4 without re-encoding
    "720": ("bv*[height<=720]+ba/b[height<=720]/bv*+ba/b", ["res:720", "vcodec:h264", "acodec:m4a"]),
    "1080": ("bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b", ["res:1080", "vcodec:h264", "acodec:m4a"]),
    "best": ("bv*+ba/b", []),
}


def download_opts(workdir: str, options: dict, progress_hook, pp_hook) -> dict:
    quality = options.get("quality") if options.get("quality") in FORMATS else "1080"
    audio_only = options.get("audio_only", False)
    fmt, sort = ("ba/b", []) if audio_only else FORMATS[quality]
    pps = [{"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"}]
    if audio_only:
        pps.append({"key": "FFmpegExtractAudio", "preferredcodec": "m4a"})
    else:
        pps.append({"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"})
    subs = bool(options.get("subtitles"))
    if subs:
        pps.append({"key": "FFmpegSubtitlesConvertor", "format": "vtt"})
    lang = (options.get("sub_lang") or "en").strip()
    return {
        "format": fmt,
        "format_sort": sort,
        "merge_output_format": "mp4",
        "outtmpl": {
            "default": f"{workdir}/video.%(ext)s",
            "thumbnail": f"{workdir}/poster.%(ext)s",
            "subtitle": f"{workdir}/subs.%(ext)s",
        },
        "writethumbnail": True,
        "writesubtitles": subs,
        "writeautomaticsub": subs and options.get("auto_subs", True),
        # matches en, en-US, en-orig; the worker keeps the best one
        "subtitleslangs": [rf"{re.escape(lang)}(-.*)?"] if subs else [],
        "subtitlesformat": "vtt/srt/best",
        "postprocessors": pps,
        "progress_hooks": [progress_hook],
        "postprocessor_hooks": [pp_hook],
        "noplaylist": True,
        "continuedl": True,
        "retries": 10,
        "fragment_retries": 10,
        "file_access_retries": 5,
        "socket_timeout": 30,
        "concurrent_fragment_downloads": 1,   # one stream at a time on a 1 GB VM
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
