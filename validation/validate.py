#!/usr/bin/env python3
"""Intent-based validation with pyATS/Genie.

Expected state is DERIVED from sot/fabric.yml (+ optional change set), never hard-coded:
  1. Each device has exactly len(interfaces) OSPF neighbors in FULL state
  2. Each device reaches every other device's loopbacks, sourced from its own Loopback0

Writes reports/validation-<label>.xml (JUnit) and exits non-zero on any failure.
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import yaml
from genie.metaparser.util.exceptions import SchemaEmptyParserError
from genie.testbed import load

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab import sot  # noqa: E402  single source of truth (devices + vault credentials)

OSPF_NEIGHBOR_CMD = {
    "iosxe": "show ip ospf neighbor",
    "iosxr": "show ospf neighbor",
    "nxos": "show ip ospf neighbors",
}


@dataclass
class Case:
    suite: str
    name: str
    ok: bool
    detail: str
    seconds: float


def addr(prefix: str) -> str:
    return prefix.split("/")[0]


def load_intent(change_file: Path | None) -> tuple[dict, dict[str, int], dict[str, list[str]], dict[str, str]]:
    fabric = yaml.safe_load((ROOT / "sot" / "fabric.yml").read_text())
    devices = fabric["devices"]
    changes = {}
    if change_file:
        changes = (yaml.safe_load(change_file.read_text()) or {}).get("changes", {})

    neighbors = {n: len(d["interfaces"]) for n, d in devices.items()}
    loopbacks = {
        n: [addr(lo["ipv4"]) for lo in d["loopbacks"] + changes.get(n, {}).get("loopbacks", [])
            if lo.get("ospf", True)]        # BGP-only loopbacks are checked by validate_bgp.py
        for n, d in devices.items()
    }
    source = {n: addr(d["loopbacks"][0]["ipv4"]) for n, d in devices.items()}
    return devices, neighbors, loopbacks, source


def count_full(obj) -> int:
    """Count neighbor entries whose 'state' starts with FULL, regardless of parser schema shape."""
    if isinstance(obj, dict):
        total = 0
        for k, v in obj.items():
            if k == "state" and isinstance(v, str) and v.upper().startswith("FULL"):
                total += 1
            else:
                total += count_full(v)
        return total
    if isinstance(obj, list):
        return sum(count_full(i) for i in obj)
    return 0


def ospf_full_count(dev, os_name: str) -> int:
    cmd = OSPF_NEIGHBOR_CMD[os_name]
    try:
        return count_full(dev.parse(cmd))
    except SchemaEmptyParserError:
        return 0
    except Exception:  # parser gap on a new release (e.g. NX-OS 10.5) -> fall back to raw text
        try:
            raw = dev.execute(cmd, timeout=60)
        except Exception:  # command rejected, e.g. OSPF not configured yet
            return 0
        return len(re.findall(r"\bFULL\b", raw))


def ping_cmd(os_name: str, dst: str, src: str) -> str:
    if os_name == "iosxe":
        return f"ping {dst} source {src} repeat 5 timeout 1"
    return f"ping {dst} source {src} count 5"  # iosxr + nxos


def ping_success_pct(output: str) -> int:
    m = re.search(r"Success rate is (\d+) percent", output)  # IOS XE / XR
    if m:
        return int(m.group(1))
    m = re.search(r"([\d.]+)% packet loss", output)  # NX-OS
    if m:
        return round(100 - float(m.group(1)))
    return 0


def write_junit(cases: list[Case], path: Path, label: str) -> None:
    root = ET.Element("testsuites", name=f"mvauto-{label}")
    by_suite: dict[str, list[Case]] = {}
    for c in cases:
        by_suite.setdefault(c.suite, []).append(c)
    for suite, items in by_suite.items():
        s = ET.SubElement(
            root, "testsuite", name=suite, tests=str(len(items)),
            failures=str(sum(not c.ok for c in items)),
        )
        for c in items:
            tc = ET.SubElement(s, "testcase", classname=f"{label}.{suite}", name=c.name, time=f"{c.seconds:.2f}")
            if not c.ok:
                ET.SubElement(tc, "failure", message=c.detail).text = c.detail
            else:
                ET.SubElement(tc, "system-out").text = c.detail
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--testbed", type=Path, help="optional pyATS testbed file (default: built from the SoT)")
    ap.add_argument("--change", type=Path, help="change set YAML whose loopbacks must also be reachable")
    ap.add_argument("--label", default="baseline")
    ap.add_argument("--converge-timeout", type=int, default=240)
    ap.add_argument("--min-success", type=int, default=60, help="min ping success %% (first packet may drop on ARP)")
    args = ap.parse_args()

    logging.getLogger("unicon").setLevel(logging.WARNING)
    logging.getLogger("genie").setLevel(logging.WARNING)

    devices, exp_neighbors, exp_loopbacks, src_ip = load_intent(args.change)
    tb = load(str(args.testbed)) if args.testbed else load(sot.pyats_testbed())
    cases: list[Case] = []

    conns = {}
    for name in devices:
        t0 = time.monotonic()
        dev = tb.devices[name]
        try:
            dev.connect(log_stdout=False, learn_hostname=True, init_config_commands=[], connection_timeout=180)
            conns[name] = dev
            cases.append(Case("connect", name, True, f"connected ({dev.os})", time.monotonic() - t0))
        except Exception as exc:
            cases.append(Case("connect", name, False, f"connect failed: {exc}", time.monotonic() - t0))

    # --- 1. OSPF adjacencies (poll until converged or timeout) ---
    observed: dict[str, int] = {}
    pending = {n: c for n, c in exp_neighbors.items() if n in conns}
    t0 = time.monotonic()
    deadline = t0 + args.converge_timeout
    while pending:
        for name in list(pending):
            observed[name] = ospf_full_count(conns[name], conns[name].os)
            if observed[name] == pending[name]:
                del pending[name]
        if not pending or time.monotonic() > deadline:
            break
        time.sleep(10)
    for name, expected in exp_neighbors.items():
        if name not in conns:
            continue
        got = observed.get(name, 0)
        cases.append(Case("ospf", f"{name}-full-neighbors", got == expected,
                          f"expected {expected} FULL, observed {got}", time.monotonic() - t0))

    # --- 2. Loopback reachability (full mesh) ---
    for src, dev in conns.items():
        for dst_dev, targets in exp_loopbacks.items():
            if dst_dev == src:
                continue
            for dst in targets:
                t1 = time.monotonic()
                pct, out = 0, ""
                for _ in range(3):
                    out = dev.execute(ping_cmd(dev.os, dst, src_ip[src]), timeout=90)
                    pct = ping_success_pct(out)
                    if pct >= args.min_success:
                        break
                    time.sleep(20)
                cases.append(Case("reachability", f"{src}->{dst_dev}:{dst}", pct >= args.min_success,
                                  f"{pct}% success from {src_ip[src]}", time.monotonic() - t1))

    for dev in conns.values():
        try:
            dev.disconnect()
        except Exception:
            pass

    report = ROOT / "reports" / f"validation-{args.label}.xml"
    write_junit(cases, report, args.label)

    failed = [c for c in cases if not c.ok]
    for c in cases:
        print(f"{'PASS' if c.ok else 'FAIL'}  {c.suite:<12} {c.name:<28} {c.detail}")
    print(f"\n{len(cases) - len(failed)}/{len(cases)} passed. JUnit: {report}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
