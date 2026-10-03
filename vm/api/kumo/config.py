"""Runtime configuration from the environment (/etc/kumo/kumo.env on the VM)."""

from __future__ import annotations

import os
import secrets
from pathlib import Path


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _flag(key: str, default: bool) -> bool:
    v = _env(key)
    return default if not v else v.lower() in ("1", "yes", "true", "on")


class Settings:
    def __init__(self) -> None:
        self.data_dir = Path(_env("KUMO_DATA", "/var/lib/kumo"))
        self.db = Path(_env("KUMO_DB", str(self.data_dir / "kumo.db")))
        self.tmp = Path(_env("KUMO_TMP", str(self.data_dir / "tmp")))
        self.agent_url = _env("KUMO_AGENT_URL", "http://100.64.1.2:9090").rstrip("/")
        self.agent_token = _env("KUMO_AGENT_TOKEN")
        # Optional single-user password. Empty = open to the LAN.
        self.password = _env("KUMO_PASSWORD")
        # Let nginx stream media (X-Accel-Redirect). Turn off only for development.
        self.accel = _flag("KUMO_ACCEL", True)
        self.worker = _flag("KUMO_WORKER", True)
        # Serve the built frontend from FastAPI (development without nginx).
        self.web_dist = _env("KUMO_WEB_DIST")
        self.max_attempts = int(_env("KUMO_MAX_ATTEMPTS", "4"))
        self.secret = _env("KUMO_SECRET") or self._stored_secret()

    def _stored_secret(self) -> str:
        path = self.data_dir / "secret"
        try:
            return path.read_text().strip()
        except OSError:
            pass
        value = secrets.token_urlsafe(32)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value)
            path.chmod(0o600)
        except OSError:
            pass
        return value


settings = Settings()
