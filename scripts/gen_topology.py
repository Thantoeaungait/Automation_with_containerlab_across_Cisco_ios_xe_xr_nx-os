#!/usr/bin/env python3
"""Generate topology/lab.clab.yml from sot/fabric.yml (single source of truth).

  python scripts/gen_topology.py           write topology/lab.clab.yml
  python scripts/gen_topology.py --check   exit 1 if the file is out of date (used by make lint)

Links are derived from `interfaces[].peer`: two interfaces form a link when each names
the other device as peer and both addresses are in the same subnet.
"""
import argparse
import ipaddress
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
FABRIC = ROOT / "sot" / "fabric.yml"
OUT = ROOT / "topology" / "lab.clab.yml"
TACACS_CFG = "configs/tac_plus.cfg"     # rendered from the vault by scripts/render_tacacs.py


def clab_ifname(name: str, rule: dict) -> str:
    return rule["to"] + name[len(rule["from"]):] if name.startswith(rule["from"]) else name


def links(fab: dict) -> list[list[str]]:
    seen, out = set(), []
    for a, da in fab["devices"].items():
        for ia in da["interfaces"]:
            b = ia["peer"]
            net = ipaddress.ip_interface(ia["ipv4"]).network
            ib = next((i for i in fab["devices"][b]["interfaces"]
                       if i["peer"] == a and ipaddress.ip_interface(i["ipv4"]).network == net), None)
            if ib is None:
                sys.exit(f"No matching interface on {b} for {a} {ia['name']} ({net})")
            key = frozenset({(a, ia["name"]), (b, ib["name"])})
            if key in seen:
                continue
            seen.add(key)
            ra = fab["platforms"][da["platform"]]["clab_if"]
            rb = fab["platforms"][fab["devices"][b]["platform"]]["clab_if"]
            out.append([f"{a}:{clab_ifname(ia['name'], ra)}", f"{b}:{clab_ifname(ib['name'], rb)}"])
    return out


def render() -> str:
    fab = yaml.safe_load(FABRIC.read_text())
    used = {d["platform"] for d in fab["devices"].values()}
    lines = [
        "# GENERATED from sot/fabric.yml by scripts/gen_topology.py - do not edit by hand.",
        "# Change the SoT, then run: make topology",
        f"name: {fab['lab']['name']}",
        "",
        "mgmt:",
        f"  network: {fab['lab']['name']}-mgmt",
        f"  ipv4-subnet: {fab['lab']['mgmt_subnet']}",
        "",
        "topology:",
        "  kinds:",
    ]
    for plat, p in fab["platforms"].items():
        if plat not in used:
            continue
        lines += [f"    {p['clab_kind']}:", f"      image: {p['image']}"]
        if p.get("clab_env"):
            lines.append("      env:")
            lines += [f"        {k}: {v}" for k, v in p["clab_env"].items()]
    lines += ["", "  nodes:"]
    for name, d in fab["devices"].items():
        p = fab["platforms"][d["platform"]]
        lines += [f"    {name}:", f"      kind: {p['clab_kind']}", f"      mgmt-ipv4: {d['mgmt_ip']}"]
        if d.get("clab_startup_config"):
            lines.append(f"      startup-config: {d['clab_startup_config']}")
    tac = fab.get("services", {}).get("tacacs")
    if tac:
        lines += ["    tacacs:", "      kind: linux", f"      image: {tac['image']}",
                  f"      mgmt-ipv4: {tac['mgmt_ip']}", "      binds:",
                  f"        - {TACACS_CFG}:/etc/tac_plus/tac_plus.cfg:ro"]
    lines += ["", "  links:"]
    lines += [f'    - endpoints: ["{x}", "{y}"]' for x, y in links(fab)]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    text = render()
    if args.check:
        if not OUT.exists() or OUT.read_text() != text:
            print("topology/lab.clab.yml is out of date with sot/fabric.yml -> run: make topology")
            return 1
        print("topology OK (matches sot/fabric.yml)")
        return 0
    OUT.write_text(text)
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
