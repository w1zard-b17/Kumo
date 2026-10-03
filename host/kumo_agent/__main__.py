"""Run the agent:  python3 -m kumo_agent [-c /etc/kumo/agent.conf]"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading

from . import __version__, disks
from .config import load
from .store import Store


def main() -> None:
    ap = argparse.ArgumentParser(prog="kumo-agent", description="Kumo storage agent")
    ap.add_argument("-c", "--config", help="config file (default /etc/kumo/agent.conf)")
    ap.add_argument("-v", "--verbose", action="store_true", help="log every request")
    ap.add_argument("--version", action="version", version=__version__)
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    log = logging.getLogger("kumo-agent")

    cfg = load(args.config)
    store = Store(cfg.db)

    from .server import Agent  # after logging is configured

    for d in store.disks():
        state = "online" if disks.is_mounted(d["mountpoint"]) else "OFFLINE"
        log.warning("disk %s at %s: %s", d["label"], d["mountpoint"], state)

    httpd = Agent(cfg, store)
    log.warning("kumo-agent %s listening on %s:%d", __version__, cfg.bind, cfg.port)

    def stop(*_):
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        httpd.serve_forever(poll_interval=1)
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
