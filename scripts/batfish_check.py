#!/usr/bin/env python3
"""Validate the intended configs with Batfish - no routers needed.

Renders the day-1 configs from the SoT (same templates as Ansible), adds the interface
state that Ansible sets through resource modules (no shutdown / routed mode), and asks Batfish:
  - did every config parse?          (initIssues)
  - do OSPF and BGP sessions match?  (ospf/bgpSessionCompatibility)
  - does every Loopback0 reach every other Loopback0?   (traceroute)
Batfish runs as a container (batfish/allinone, ~2-3 GB RAM): run it while the lab is DOWN.
  make batfish                 (starts the container if needed)
  make batfish CHANGE=sot/changes/loopback100.yml
Needs: pip install -r requirements-optional.txt
"""
from __future__ import annotations

import argparse
import ipaddress
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from render_templates import render_all  # noqa: E402

from lab import sot  # noqa: E402

SNAP = ROOT / "reports" / "batfish" / "snapshot"
CONTAINER = "batfish"


def ensure_batfish(timeout: int = 180) -> None:
    running = subprocess.run(["docker", "ps", "-q", "-f", f"name=^{CONTAINER}$"],
                             capture_output=True, text=True).stdout.strip()
    if not running:
        subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
        print(">>> starting batfish/allinone")
        subprocess.run(["docker", "run", "-d", "--name", CONTAINER, "-p", "9996:9996", "-p", "9997:9997",
                        "batfish/allinone"], check=True, capture_output=True)
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        try:
            socket.create_connection(("localhost", 9996), timeout=3).close()
            time.sleep(5)  # service up a moment after the port opens
            return
        except OSError:
            time.sleep(3)
    sys.exit("Batfish did not start (docker logs batfish)")


def prelude(platform: str, ifname: str) -> str:
    """Interface state Ansible applies via resource modules, made explicit for Batfish."""
    if platform == "nxos":
        return f"interface {ifname}\n  no switchport\n  no shutdown\n"
    return f"interface {ifname}\n no shutdown\n!\n"


def write_snapshot(change: Path | None) -> None:
    fab = sot.fabric()
    if SNAP.exists():
        shutil.rmtree(SNAP)
    (SNAP / "configs").mkdir(parents=True)
    for host, cfg in render_all(change).items():
        dev = fab["devices"][host]
        head = {"iosxr": "!! IOS XR Configuration\n", "nxos": "!Command: show running-config\n",
                "iosxe": "version 17.13\n"}[dev["platform"]]
        pre = "".join(prelude(dev["platform"], i["name"]) for i in dev["interfaces"])
        (SNAP / "configs" / f"{host}.cfg").write_text(head + cfg.split("\n", 1)[0] + "\n" + pre + cfg.split("\n", 1)[1])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--change", type=Path)
    args = ap.parse_args()
    try:
        from pybatfish.client.session import Session
        from pybatfish.datamodel.flow import HeaderConstraints
    except ImportError:
        sys.exit("pybatfish missing: .venv/bin/pip install -r requirements-optional.txt")

    write_snapshot(args.change)
    ensure_batfish()
    bf = Session(host="localhost")
    bf.set_network("mvauto")
    bf.init_snapshot(str(SNAP), name="intent", overwrite=True)

    ok = True
    issues = bf.q.initIssues().answer().frame()
    print(f"\n=== parse issues: {len(issues)}")
    if len(issues):
        print(issues.to_string(max_colwidth=80))

    for q, good in (("ospfSessionCompatibility", {"ESTABLISHED"}),
                    ("bgpSessionCompatibility", {"UNIQUE_MATCH", "DYNAMIC_MATCH"})):
        df = getattr(bf.q, q)().answer().frame()
        col = "Session_Status" if "Session_Status" in df.columns else "Configured_Status"
        bad = df[~df[col].isin(good)] if len(df) else df
        print(f"\n=== {q}: {len(df)} sessions, {len(bad)} not OK")
        if len(bad):
            print(bad.to_string(max_colwidth=60))
        ok &= len(df) > 0 and len(bad) == 0

    fab = sot.fabric()
    lo0 = {h: str(ipaddress.ip_interface(d["loopbacks"][0]["ipv4"]).ip) for h, d in fab["devices"].items()}
    print("\n=== Loopback0 reachability (traceroute)")
    for src in lo0:
        for dst, ip in lo0.items():
            if src == dst:
                continue
            tr = bf.q.traceroute(startLocation=src, headers=HeaderConstraints(dstIps=ip)).answer().frame()
            accepted = any(t.disposition == "ACCEPTED" for row in tr["Traces"] for t in row)
            ok &= accepted
            print(f"{'PASS' if accepted else 'FAIL'}  {src} -> {dst} ({ip})")

    print(f"\n{'Batfish: intent looks consistent' if ok else 'Batfish: problems found'}"
          f"  (stop the container when done: docker rm -f {CONTAINER})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
