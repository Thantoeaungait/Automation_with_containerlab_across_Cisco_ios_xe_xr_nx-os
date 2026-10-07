#!/usr/bin/env python3
"""Failure test: break one link, prove the network reroutes, restore it, prove it recovers.

The link and expectations come from the SoT (`failover:` in sot/fabric.yml):
  1. baseline: the device has all its OSPF neighbors
  2. break:    100 % packet loss on the link (containerlab tools netem, container side)
  3. reroute:  the device still reaches the expected Loopback0s (via the remaining path);
               reports how long the reroute took (OSPF dead interval, no BFD in this lab)
  4. restore:  loss removed; all OSPF neighbors come back
JUnit: reports/validation-failover.xml.  Run: make failover-test
"""
from __future__ import annotations

import argparse
import logging
import re
import shutil
import subprocess
import sys
import time

from genie.testbed import load

from validate import ROOT, Case, addr, ospf_full_count, ping_cmd, ping_success_pct, sot, write_junit


def container_if(dev: dict, ifname: str) -> str:
    rule = dev["container_if"]
    m = re.match(rule["match"], ifname)
    if not m:
        sys.exit(f"cannot map {ifname} to a container interface (platforms.{dev['platform']}.container_if)")
    return f"eth{int(m.group(1)) + rule['offset']}"


def netem(container: str, iface: str, loss: int) -> None:
    cmd = ["containerlab", "tools", "netem", "set", "-n", container, "-i", iface, "--loss", str(loss)]
    if subprocess.run(cmd, capture_output=True, text=True).returncode != 0:
        # not in clab_admins: retry with sudo (non-interactive)
        res = subprocess.run(["sudo", "-n", *cmd], capture_output=True, text=True)
        if res.returncode != 0:
            sys.exit(f"netem failed: {res.stderr.strip()} (join clab_admins or allow sudo)")


def wait_until(check, timeout: int, interval: int = 5) -> float | None:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if check():
            return time.monotonic() - t0
        time.sleep(interval)
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=180, help="seconds to wait for reroute / recovery")
    args = ap.parse_args()
    logging.getLogger("unicon").setLevel(logging.WARNING)
    if not shutil.which("containerlab"):
        sys.exit("containerlab not found")

    fab = sot.fabric()
    spec = fab["failover"]
    devs = sot.devices()
    name = spec["device"]
    d = devs[name]
    iface = container_if(d, spec["interface"])
    container = f"clab-{fab['lab']['name']}-{name}"
    neighbors = len(fab["devices"][name]["interfaces"])
    src = addr(fab["devices"][name]["loopbacks"][0]["ipv4"])
    targets = [addr(fab["devices"][t]["loopbacks"][0]["ipv4"]) for t in spec["expect_reach"]]

    tb = load(sot.pyats_testbed())
    dev = tb.devices[name]
    dev.connect(log_stdout=False, learn_hostname=True, init_config_commands=[], connection_timeout=180)
    full = lambda: ospf_full_count(dev, dev.os)  # noqa: E731
    reach = lambda: all(ping_success_pct(dev.execute(ping_cmd(dev.os, t, src), timeout=60)) >= 60  # noqa: E731
                        for t in targets)
    cases: list[Case] = []

    n0 = full()
    cases.append(Case("failover", "baseline-neighbors", n0 == neighbors, f"{n0}/{neighbors} FULL", 0))
    print(f"baseline: {name} has {n0}/{neighbors} OSPF neighbors")

    print(f"break:    100% loss on {container} {iface} ({spec['interface']})")
    netem(container, iface, 100)
    try:
        t_down = wait_until(lambda: full() == neighbors - 1, args.timeout)
        cases.append(Case("failover", "neighbor-down-detected", t_down is not None,
                          f"after {t_down:.0f}s" if t_down is not None else "not detected", t_down or 0))
        t_reach = wait_until(reach, args.timeout)
        cases.append(Case("failover", "reachability-during-failure", t_reach is not None,
                          f"{', '.join(targets)} reachable after {t_reach:.0f}s" if t_reach is not None
                          else "not reachable", t_reach or 0))
        print(f"reroute:  neighbor down after {t_down}s, reachable after {t_reach}s")
    finally:
        print("restore:  loss removed")
        netem(container, iface, 0)

    t_up = wait_until(lambda: full() == neighbors, args.timeout)
    cases.append(Case("failover", "recovery-neighbors", t_up is not None,
                      f"{neighbors} FULL after {t_up:.0f}s" if t_up is not None else "not recovered", t_up or 0))
    dev.disconnect()

    write_junit(cases, ROOT / "reports" / "validation-failover.xml", "failover")
    for c in cases:
        print(f"{'PASS' if c.ok else 'FAIL'}  {c.name:<30} {c.detail}")
    return 0 if all(c.ok for c in cases) else 1


if __name__ == "__main__":
    sys.exit(main())
