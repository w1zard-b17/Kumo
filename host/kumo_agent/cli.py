"""kumoctl: host-side administration for the storage agent.

Run as root. Steps needing root happen first, then the process drops to the
agent user so the database is never left owned by root.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys

from . import __version__, disks
from .config import human, load, parse_size
from .store import Store

GREEN, DIM, BOLD, RED, RESET = "\033[32m", "\033[2m", "\033[1m", "\033[31m", "\033[0m"
if not sys.stdout.isatty():
    GREEN = DIM = BOLD = RED = RESET = ""

AGENT_USER = "_kumo"


def die(msg: str, code: int = 1):
    print(f"{RED}kumoctl: {msg}{RESET}", file=sys.stderr)
    sys.exit(code)


def ok(msg: str):
    print(f"{GREEN}✓{RESET} {msg}")


def table(rows: list[list], head: list[str]):
    if not rows:
        print(f"{DIM}(none){RESET}")
        return
    cols = [head] + [[str(c) for c in r] for r in rows]
    w = [max(len(r[i]) for r in cols) for i in range(len(head))]
    print(BOLD + "  ".join(h.ljust(w[i]) for i, h in enumerate(head)) + RESET)
    for r in cols[1:]:
        print("  ".join(c.ljust(w[i]) for i, c in enumerate(r)))


def agent_ids() -> tuple[int, int] | None:
    try:
        import pwd

        pw = pwd.getpwnam(AGENT_USER)
        return pw.pw_uid, pw.pw_gid
    except (ImportError, KeyError):
        return None


def drop_privileges():
    """As root, become the agent user before touching the database."""
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        return
    ids = agent_ids()
    if not ids:
        die(f"user {AGENT_USER} does not exist; run install.sh first")
    uid, gid = ids
    os.setgroups([])
    os.setgid(gid)
    os.setuid(uid)


def make_root(mountpoint: str, root: str):
    path = os.path.join(mountpoint, root)
    os.makedirs(path, mode=0o750, exist_ok=True)
    ids = agent_ids()
    if ids and hasattr(os, "geteuid") and os.geteuid() == 0:
        os.chown(path, *ids)
    return path


def disk_scan(args, cfg):
    info = disks.scan()
    print(f"{BOLD}kernel disks{RESET}")
    table([[d["device"], d["duid"] or "-"] for d in info["disks"]], ["device", "duid"])
    print(f"\n{BOLD}mounted filesystems{RESET}")
    table([[m["source"], m["mountpoint"], m["fstype"]] for m in info["mounts"]], ["source", "mountpoint", "type"])
    print(f"\n{DIM}register with: kumoctl disk add <label> <mountpoint> --device <duid>{RESET}")


def disk_list(args, cfg):
    drop_privileges()
    rows = []
    for d in Store(cfg.db).disks():
        mounted = disks.is_mounted(d["mountpoint"])
        u = disks.usage(d["mountpoint"]) if mounted else None
        state = (GREEN + "online" + RESET) if mounted else (RED + "offline" + RESET)
        if not d["enabled"]:
            state = DIM + "disabled" + RESET
        rows.append([
            d["label"], d["mountpoint"], d["device"] or "-", state,
            human(u["used"]) if u else "-", human(u["free"]) if u else "-", human(u["total"]) if u else "-",
        ])
    table(rows, ["label", "mountpoint", "device", "state", "used", "free", "size"])


def disk_add(args, cfg):
    mp = os.path.abspath(args.mountpoint)
    if not os.path.isdir(mp):
        die(f"{mp} is not a directory")
    if not disks.is_mounted(mp):
        print(f"{DIM}note: nothing is mounted on {mp} right now{RESET}")
    drop_privileges()
    try:
        Store(cfg.db).add_disk(args.label, mp, args.device)
    except sqlite3.IntegrityError:
        die("label or mountpoint already registered")
    ok(f"disk {args.label} registered at {mp}")


def disk_toggle(args, cfg):
    drop_privileges()
    try:
        Store(cfg.db).set_disk(args.label, enabled=int(args.cmd == "enable"))
    except KeyError:
        die(f"no disk {args.label!r}")
    ok(f"disk {args.label} {args.cmd}d")


def disk_rm(args, cfg):
    drop_privileges()
    try:
        Store(cfg.db).remove_disk(args.label)
    except KeyError:
        die(f"no disk {args.label!r}")
    except ValueError as e:
        die(str(e))
    ok(f"disk {args.label} removed (data on it was not touched)")


def disk_mount(args, cfg):
    store = Store(cfg.db) if os.access(cfg.db, os.R_OK) else None
    d = store.disk(args.label) if store else None
    if not d:
        die(f"no disk {args.label!r}")
    fn = disks.mount if args.cmd == "mount" else disks.umount
    code, out = fn(d["mountpoint"])
    if code:
        die(out or f"{args.cmd} failed")
    ok(f"{args.cmd} {d['mountpoint']}")


def vm_add(args, cfg):
    store = Store(cfg.db)
    d = store.disk(args.disk)
    if not d:
        die(f"no disk {args.disk!r}; see 'kumoctl disk list'")
    if not disks.is_mounted(d["mountpoint"]):
        die(f"disk {args.disk} is not mounted")
    root = (args.root or f"kumo/{args.name}").strip("/")
    path = make_root(d["mountpoint"], root)
    drop_privileges()
    try:
        token = Store(cfg.db).add_vm(args.name, args.disk, root, args.ip or "", parse_size(args.quota or "0"))
    except sqlite3.IntegrityError:
        die(f"vm {args.name!r} already exists")
    ok(f"vm {args.name} → {path}")
    print_token(args.name, token)


def print_token(name, token):
    print(f"\n  token  {GREEN}{token}{RESET}\n")
    print(f"{DIM}Shown once. On the VM put it in /etc/kumo/kumo.env as KUMO_AGENT_TOKEN,")
    print(f"then run 'kumo-setup-token' (or re-run install.sh) so nginx gets it too.{RESET}")


def vm_list(args, cfg):
    drop_privileges()
    rows = []
    for v in Store(cfg.db).vms():
        state = (GREEN + "enabled" + RESET) if v["enabled"] else (DIM + "disabled" + RESET)
        quota = human(v["quota"]) if v["quota"] else "∞"
        rows.append([v["name"], state, v["disk_label"], v["root"], v["allowed_ips"] or "any",
                     f"{human(v['used'])}/{quota}", v["nfiles"], v["last_seen"] or "never"])
    table(rows, ["name", "state", "disk", "root", "allowed", "used/quota", "files", "last seen"])


def vm_rotate(args, cfg):
    drop_privileges()
    try:
        token = Store(cfg.db).rotate_token(args.name)
    except KeyError:
        die(f"no vm {args.name!r}")
    ok(f"token rotated for {args.name}; the old one stops working now")
    print_token(args.name, token)


def vm_set(args, cfg):
    store = Store(cfg.db)
    fields = {}
    if args.ip is not None:
        fields["allowed_ips"] = args.ip
    if args.quota is not None:
        fields["quota"] = parse_size(args.quota)
    if args.disk is not None:
        d = store.disk(args.disk)
        if not d:
            die(f"no disk {args.disk!r}")
        v = store.vm(args.name)
        if not v:
            die(f"no vm {args.name!r}")
        make_root(d["mountpoint"], v["root"])
        fields["disk_id"] = d["id"]
        print(f"{DIM}new uploads go to {args.disk}; existing files stay where they are{RESET}")
    drop_privileges()
    try:
        Store(cfg.db).set_vm(args.name, **fields)
    except KeyError:
        die(f"no vm {args.name!r}")
    ok(f"vm {args.name} updated")


def vm_toggle(args, cfg):
    drop_privileges()
    try:
        Store(cfg.db).set_vm(args.name, enabled=int(args.cmd == "enable"))
    except KeyError:
        die(f"no vm {args.name!r}")
    ok(f"vm {args.name} {args.cmd}d")


def vm_rm(args, cfg):
    drop_privileges()
    store = Store(cfg.db)
    v = store.vm(args.name)
    if not v:
        die(f"no vm {args.name!r}")
    files = store.files(v["id"], limit=10 ** 9)
    if files and not args.purge and not args.keep_files:
        die(f"{len(files)} files belong to {args.name}; pass --keep-files or --purge")
    if args.purge:
        for f in files:
            try:
                os.unlink(os.path.join(f["mountpoint"], f["relpath"]))
            except OSError:
                pass
    store.remove_vm(args.name)
    ok(f"vm {args.name} removed" + (f", {len(files)} files deleted" if args.purge else ""))


def files_cmd(args, cfg):
    drop_privileges()
    store = Store(cfg.db)
    v = store.vm(args.name)
    if not v:
        die(f"no vm {args.name!r}")
    rows = [[f["id"], human(f["size"]), f["relpath"]] for f in store.files(v["id"], args.prefix or "", args.limit)]
    table(rows, ["id", "size", "path"])


def audit_cmd(args, cfg):
    drop_privileges()
    rows = [[a["ts"], a["vm"] or "-", a["ip"] or "-", a["action"], a["detail"] or ""]
            for a in reversed(Store(cfg.db).audit_log(args.limit))]
    table(rows, ["time", "vm", "ip", "action", "detail"])


def verify_cmd(args, cfg):
    drop_privileges()
    store = Store(cfg.db)
    vms = [store.vm(args.name)] if args.name else store.vms()
    bad = 0
    for v in vms:
        if not v:
            die(f"no vm {args.name!r}")
        for f in store.files(v["id"], limit=10 ** 9):
            p = os.path.join(f["mountpoint"], f["relpath"])
            if not disks.is_mounted(f["mountpoint"]):
                print(f"{RED}offline{RESET}  {f['id']}  {p}")
                bad += 1
            elif not os.path.exists(p):
                print(f"{RED}missing{RESET}  {f['id']}  {p}")
                bad += 1
            elif os.path.getsize(p) != f["size"]:
                print(f"{RED}size{RESET}     {f['id']}  {p}")
                bad += 1
    (ok if not bad else die)(f"{bad} problem(s)" if bad else "all files present")


def init_cmd(args, cfg):
    drop_privileges()
    Store(cfg.db)
    ok(f"database ready at {cfg.db}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kumoctl", description="Kumo storage agent administration")
    ap.add_argument("-c", "--config", help="agent config (default /etc/kumo/agent.conf)")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="group", required=True)

    sub.add_parser("init", help="create the database").set_defaults(fn=init_cmd)

    dk = sub.add_parser("disk", help="manage storage disks").add_subparsers(dest="cmd", required=True)
    dk.add_parser("scan", help="show kernel disks and mounts").set_defaults(fn=disk_scan)
    dk.add_parser("list", help="registered disks with usage").set_defaults(fn=disk_list)

    p = dk.add_parser("add", help="register a mounted filesystem")
    p.add_argument("label")
    p.add_argument("mountpoint")
    p.add_argument("--device", help="DUID, e.g. 3eb7f9da875cb9ee")
    p.set_defaults(fn=disk_add)

    for c in ("enable", "disable"):
        p = dk.add_parser(c)
        p.add_argument("label")
        p.set_defaults(fn=disk_toggle)

    for c in ("mount", "umount"):
        p = dk.add_parser(c, help=f"{c} via /etc/fstab (root)")
        p.add_argument("label")
        p.set_defaults(fn=disk_mount)

    p = dk.add_parser("rm", help="unregister (data untouched)")
    p.add_argument("label")
    p.set_defaults(fn=disk_rm)

    vm = sub.add_parser("vm", help="manage VM clients").add_subparsers(dest="cmd", required=True)
    vm.add_parser("list").set_defaults(fn=vm_list)

    p = vm.add_parser("add", help="register a VM and print its token")
    p.add_argument("name")
    p.add_argument("--disk", required=True)
    p.add_argument("--ip", help="allowed source IPs/CIDRs, comma separated (e.g. 100.64.1.3)")
    p.add_argument("--root", help="directory on the disk (default kumo/<name>)")
    p.add_argument("--quota", help="e.g. 2T, 500G (default unlimited)")
    p.set_defaults(fn=vm_add)

    p = vm.add_parser("rotate", help="issue a new token")
    p.add_argument("name")
    p.set_defaults(fn=vm_rotate)

    p = vm.add_parser("set", help="change ip, quota or disk")
    p.add_argument("name")
    p.add_argument("--ip")
    p.add_argument("--quota")
    p.add_argument("--disk")
    p.set_defaults(fn=vm_set)

    for c in ("enable", "disable"):
        p = vm.add_parser(c)
        p.add_argument("name")
        p.set_defaults(fn=vm_toggle)

    p = vm.add_parser("rm", help="unregister a VM")
    p.add_argument("name")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--keep-files", action="store_true", help="forget the files, leave them on disk")
    g.add_argument("--purge", action="store_true", help="delete the VM's files from disk")
    p.set_defaults(fn=vm_rm)

    p = sub.add_parser("files", help="list a VM's files")
    p.add_argument("name")
    p.add_argument("--prefix")
    p.add_argument("--limit", type=int, default=200)
    p.set_defaults(fn=files_cmd)

    p = sub.add_parser("audit", help="recent agent activity")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(fn=audit_cmd)

    p = sub.add_parser("verify", help="check that every file is on disk")
    p.add_argument("name", nargs="?")
    p.set_defaults(fn=verify_cmd)

    args = ap.parse_args(argv)
    cfg = load(args.config)
    try:
        args.fn(args, cfg)
    finally:
        fix_owner(cfg.db)


def fix_owner(db: str):
    """If root created the database, hand it to the agent user."""
    ids = agent_ids()
    if not ids or not hasattr(os, "geteuid") or os.geteuid() != 0:
        return
    for p in (os.path.dirname(db), db):
        try:
            if os.stat(p).st_uid == 0:
                os.chown(p, *ids)
        except OSError:
            pass


if __name__ == "__main__":
    main()
