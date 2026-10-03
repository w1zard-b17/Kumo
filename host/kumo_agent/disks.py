"""Disk usage, mount state, OpenBSD disk discovery and path handling."""

from __future__ import annotations

import os
import re
import shutil
import subprocess

_BAD_CHARS = re.compile(r'[\x00-\x1f\x7f\\:*?"<>|]')
MAX_DEPTH = 6
MAX_COMPONENT = 180

REQUIRE_MOUNT = True


def usage(mountpoint: str) -> dict:
    try:
        if not hasattr(os, "statvfs"):
            u = shutil.disk_usage(mountpoint)
            return {"total": u.total, "free": u.free, "used": u.used}
        st = os.statvfs(mountpoint)
    except OSError:
        return {"total": 0, "free": 0, "used": 0}
    total = st.f_blocks * st.f_frsize
    free = st.f_bavail * st.f_frsize
    return {"total": total, "free": free, "used": total - st.f_bfree * st.f_frsize}


def is_mounted(mountpoint: str) -> bool:
    """Guards against writing into the bare mountpoint when the disk is absent."""
    if not os.path.isdir(mountpoint):
        return False
    return os.path.ismount(mountpoint) or not REQUIRE_MOUNT


def sanitize(path: str) -> str:
    """Normalise a client supplied relative path. Raises ValueError when unusable."""
    parts = []
    for raw in path.replace("\\", "/").split("/"):
        p = _BAD_CHARS.sub("", raw).strip().strip(".")
        if not p:
            continue
        if len(p.encode()) > MAX_COMPONENT:
            stem, ext = os.path.splitext(p)
            p = stem.encode()[: MAX_COMPONENT - len(ext.encode())].decode(errors="ignore").rstrip() + ext
        parts.append(p)
    if not parts:
        raise ValueError("empty path")
    if len(parts) > MAX_DEPTH:
        raise ValueError("path too deep")
    return "/".join(parts)


def inside(base: str, target: str) -> bool:
    base = os.path.realpath(base)
    target = os.path.realpath(target)
    return target == base or target.startswith(base + os.sep)


def free_name(path: str) -> str:
    """'Name.mp4' -> 'Name (2).mp4' when taken."""
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(f"{stem} ({n}){ext}"):
        n += 1
    return f"{stem} ({n}){ext}"


def place(src: str, dst: str) -> str:
    """Move src to dst without overwriting; returns the final path."""
    os.makedirs(os.path.dirname(dst), mode=0o750, exist_ok=True)
    while True:
        dst = free_name(dst)
        try:
            os.link(src, dst)
        except FileExistsError:
            continue
        except OSError:
            # no hard links on this filesystem
            if os.path.exists(dst):
                continue
            os.rename(src, dst)
            return dst
        os.unlink(src)
        return dst


def prune_empty_dirs(start: str, stop: str) -> None:
    d = os.path.dirname(start)
    stop = os.path.realpath(stop)
    while inside(stop, d) and os.path.realpath(d) != stop:
        try:
            os.rmdir(d)
        except OSError:
            return
        d = os.path.dirname(d)


def _run(*cmd) -> str:
    if not shutil.which(cmd[0]):
        return ""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def scan() -> dict:
    """Disks known to the kernel plus current mounts."""
    names = _run("sysctl", "-n", "hw.disknames").strip()
    disks = []
    for item in filter(None, names.split(",")):
        dev, _, duid = item.partition(":")
        disks.append({"device": dev, "duid": duid or None})
    mounts = []
    for line in _run("mount").splitlines():
        m = re.match(r"^(\S+) on (\S+) type (\S+) \(([^)]*)\)", line)
        if m:
            mounts.append({"source": m[1], "mountpoint": m[2], "fstype": m[3], "options": m[4]})
    return {"disks": disks, "mounts": mounts}


def mount(mountpoint: str) -> tuple[int, str]:
    r = subprocess.run(["mount", mountpoint], capture_output=True, text=True)
    return r.returncode, (r.stderr or r.stdout).strip()


def umount(mountpoint: str) -> tuple[int, str]:
    r = subprocess.run(["umount", mountpoint], capture_output=True, text=True)
    return r.returncode, (r.stderr or r.stdout).strip()
