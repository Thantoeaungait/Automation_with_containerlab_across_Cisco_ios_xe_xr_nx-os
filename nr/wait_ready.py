#!/usr/bin/env python3
"""Block until every lab node accepts SSH and answers a CLI command.

vrnetlab containers accept TCP :22 long before the VM inside has started sshd
(the container forwards the port, then drops the connection). So each round:
  1. cheap TCP probe: does :22 return an "SSH-" banner?   -> no: still booting
  2. only then a full Netmiko login + "show version"      -> yes: READY
"""
import argparse
import socket
import sys
import time

from nornir.core.task import Result, Task
from nornir_netmiko.tasks import netmiko_send_command

from common import init_nornir


def ssh_banner(host: str, port: int = 22, timeout: float = 8.0) -> str | None:
    """Return the SSH banner line if a real sshd answers, else None."""
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            s.settimeout(timeout)
            data = s.recv(256)
    except OSError:
        return None
    return data.decode(errors="replace").strip() if data.startswith(b"SSH-") else None


def probe(task: Task) -> Result:
    mr = task.run(task=netmiko_send_command, command_string="show version", read_timeout=60)
    first = next((l for l in mr[0].result.splitlines() if l.strip()), "")
    return Result(host=task.host, result=first.strip())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=1800, help="overall seconds to wait")
    ap.add_argument("--interval", type=int, default=30, help="seconds between rounds")
    args = ap.parse_args()

    nr = init_nornir()
    pending = set(nr.inventory.hosts)
    deadline = time.monotonic() + args.timeout
    start = time.monotonic()

    def ts() -> str:
        return f"[{int(time.monotonic() - start):>5}s]"

    while pending:
        # Stage 1: banner check (no paramiko involved, no noise)
        candidates, booting = set(), []
        for name in sorted(pending):
            if ssh_banner(nr.inventory.hosts[name].hostname):
                candidates.add(name)
            else:
                booting.append(name)

        # Stage 2: full login only where sshd is really up
        not_ready = []
        if candidates:
            time.sleep(5)  # let per-source SSH rate limits (IOS XR) reset after the banner probe
            sub = nr.filter(filter_func=lambda h: h.name in candidates)
            results = sub.run(task=probe, name="probe")
            for host, mr in results.items():
                if mr.failed:
                    exc = next((r.exception for r in reversed(mr) if r.exception), None)
                    root = getattr(exc, "result", None)  # NornirSubTaskError wraps the real error
                    if root is not None:
                        exc = next((r.exception for r in root if r.exception), exc)
                    not_ready.append(f"{host}({type(exc).__name__ if exc else 'unknown'})")
                else:
                    print(f"{ts()} READY    {host:<4} {mr[0].result}")
                    pending.discard(host)
            sub.close_connections(on_good=True, on_failed=True)
            nr.data.reset_failed_hosts()

        if pending:
            if time.monotonic() > deadline:
                print(f"TIMEOUT: not ready after {args.timeout}s: {sorted(pending)}", file=sys.stderr)
                return 1
            parts = []
            if booting:
                parts.append(f"booting (no SSH banner): {booting}")
            if not_ready:
                parts.append(f"sshd up, login not ready: {sorted(not_ready)}")
            print(f"{ts()} waiting  " + "; ".join(parts))
            time.sleep(args.interval)

    print("All nodes reachable over SSH.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
