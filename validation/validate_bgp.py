#!/usr/bin/env python3
"""BGP validation derived from sot/fabric.yml (iBGP full mesh between Loopback0s).

Checks:
  1. Every device has (number of devices - 1) BGP sessions in Established state
  2. Every device reaches every other device's bgp_networks, sourced from Loopback0
Writes reports/validation-bgp.xml (JUnit).
"""
import argparse
import logging
import sys
import time

import yaml
from genie.testbed import load

from validate import ROOT, Case, addr, ping_cmd, ping_success_pct, write_junit

BGP_NEIGHBORS_CMD = {
    "iosxe": "show ip bgp neighbors",
    "iosxr": "show bgp neighbors",
    "nxos": "show ip bgp neighbors",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=240, help="seconds to wait for sessions")
    args = ap.parse_args()
    logging.getLogger("unicon").setLevel(logging.WARNING)

    fabric = yaml.safe_load((ROOT / "sot" / "fabric.yml").read_text())
    if "bgp" not in fabric:
        print("No 'bgp:' section in sot/fabric.yml - nothing to validate.")
        return 0
    devices = fabric["devices"]
    expected = len(devices) - 1
    tb = load(str(ROOT / "validation" / "testbed.yaml"))

    conns = {}
    for name in devices:
        dev = tb.devices[name]
        dev.connect(log_stdout=False, learn_hostname=True, init_config_commands=[], connection_timeout=180)
        conns[name] = dev

    # 1. Sessions: all three OSes print "BGP state = Established" per established neighbor
    established: dict[str, int] = {}
    pending = set(conns)
    t0 = time.monotonic()
    while pending:
        for name in list(pending):
            out = conns[name].execute(BGP_NEIGHBORS_CMD[conns[name].os], timeout=60)
            established[name] = out.count("BGP state = Established")
            if established[name] >= expected:
                pending.discard(name)
        if not pending or time.monotonic() - t0 > args.timeout:
            break
        time.sleep(10)

    cases = [Case("bgp", f"{n}-established", established.get(n, 0) == expected,
                  f"expected {expected}, observed {established.get(n, 0)}", time.monotonic() - t0)
             for n in conns]

    # 2. Reachability of BGP-advertised prefixes
    for src, dev in conns.items():
        src_ip = addr(devices[src]["loopbacks"][0]["ipv4"])
        for dst, d in devices.items():
            if dst == src:
                continue
            for net in d.get("bgp_networks", []):
                ip, pct, t1 = addr(net), 0, time.monotonic()
                for _ in range(6):
                    pct = ping_success_pct(dev.execute(ping_cmd(dev.os, ip, src_ip), timeout=90))
                    if pct >= 60:
                        break
                    time.sleep(10)
                cases.append(Case("bgp-reach", f"{src}->{dst}:{ip}", pct >= 60,
                                  f"{pct}% success from {src_ip}", time.monotonic() - t1))

    for dev in conns.values():
        dev.disconnect()

    report = ROOT / "reports" / "validation-bgp.xml"
    write_junit(cases, report, "bgp")
    failed = [c for c in cases if not c.ok]
    for c in cases:
        print(f"{'PASS' if c.ok else 'FAIL'}  {c.suite:<10} {c.name:<26} {c.detail}")
    print(f"\n{len(cases) - len(failed)}/{len(cases)} passed. JUnit: {report}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
