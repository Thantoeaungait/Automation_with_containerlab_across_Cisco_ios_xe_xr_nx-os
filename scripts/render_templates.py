#!/usr/bin/env python3
"""Render day-1 templates from the SoT without devices or Ansible collections.

Used by CI lint and handy locally:  python scripts/render_templates.py [--change sot/changes/loopback100.yml]
"""
import argparse
from pathlib import Path

import jinja2
import netaddr
import yaml

ROOT = Path(__file__).resolve().parents[1]


def ipaddr(value: str, query: str) -> str:
    net = netaddr.IPNetwork(value)
    return {"address": str(net.ip), "netmask": str(net.netmask)}[query]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--change", type=Path)
    args = ap.parse_args()

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(ROOT / "ansible/templates/day1"),
        trim_blocks=True, undefined=jinja2.StrictUndefined,
    )
    env.filters["ansible.utils.ipaddr"] = ipaddr
    sot = yaml.safe_load((ROOT / "sot/fabric.yml").read_text())
    changes = yaml.safe_load(args.change.read_text())["changes"] if args.change else {}

    for host, dev in sot["devices"].items():
        print(f"!---------------- {host} ({dev['platform']}) ----------------")
        print(env.get_template(f"{dev['platform']}.j2").render(
            inventory_hostname=host, dev=dev, ospf=sot["ospf"], devices=sot["devices"], **({"bgp": sot["bgp"]} if "bgp" in sot else {}),
            extra_loopbacks=changes.get(host, {}).get("loopbacks", []),
        ))


if __name__ == "__main__":
    main()
