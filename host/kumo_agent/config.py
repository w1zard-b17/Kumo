"""Agent configuration, read from an INI file."""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass

DEFAULT_PATH = "/etc/kumo/agent.conf"


@dataclass(frozen=True)
class Config:
    bind: str = "100.64.1.2"            # host side of the vmd tap
    port: int = 9090
    db: str = "/var/db/kumo/agent.db"
    chunk_size: int = 256 * 1024
    upload_timeout: int = 120           # seconds of socket inactivity
    reserve: int = 2 * 1024 ** 3        # free space never consumed by uploads
    auth_fail_limit: int = 20           # failed auths per IP per minute before 429
    require_mount: bool = True


def load(path: str | None = None) -> Config:
    path = path or os.environ.get("KUMO_AGENT_CONF", DEFAULT_PATH)
    cp = configparser.ConfigParser()
    if os.path.exists(path):
        cp.read(path)
    s = cp["agent"] if cp.has_section("agent") else {}
    d = Config()
    cfg = Config(
        bind=s.get("bind", d.bind),
        port=int(s.get("port", d.port)),
        db=s.get("db", d.db),
        chunk_size=int(s.get("chunk_size", d.chunk_size)),
        upload_timeout=int(s.get("upload_timeout", d.upload_timeout)),
        reserve=parse_size(s.get("reserve", str(d.reserve))),
        auth_fail_limit=int(s.get("auth_fail_limit", d.auth_fail_limit)),
        require_mount=str(s.get("require_mount", "yes")).lower() not in ("no", "false", "0", "off"),
    )
    from . import disks

    disks.REQUIRE_MOUNT = cfg.require_mount
    return cfg


_UNITS = {"": 1, "B": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4}


def parse_size(text: str) -> int:
    """'500G' -> bytes. Bare integers are bytes."""
    t = str(text).strip().upper().removesuffix("IB").removesuffix("B") if str(text).strip() else "0"
    num = t.rstrip("KMGT")
    unit = t[len(num):]
    return int(float(num or 0) * _UNITS[unit])


def human(n: int | float) -> str:
    n = float(n)
    for unit in ("B", "K", "M", "G", "T"):
        if abs(n) < 1024 or unit == "T":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}T"
