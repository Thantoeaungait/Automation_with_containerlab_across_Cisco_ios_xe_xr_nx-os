#!/usr/bin/env python3
"""Render day-1 templates from the SoT without devices or Ansible collections.

Used by make lint / make render, and by scripts/batfish_check.py:
  python scripts/render_templates.py [--change sot/changes/loopback100.yml]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import jinja2
import netaddr
import yaml

ROOT = Path(__file__).resolve().parents[1]


def ipaddr(value: str, query: str) -> str:
    net = netaddr.IPNetwork(value)
    return {"address": str(net.ip), "netmask": str(net.netmask)}[query]


def render_all(change: Path | None = None) -> dict[str, str]:
    """Rendered day-1 config per device (same templates and variables as Ansible)."""
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(ROOT / "ansible/templates/day1"),
        trim_blocks=True, undefined=jinja2.StrictUndefined,
    )
    env.filters["ansible.utils.ipaddr"] = ipaddr
    fab = yaml.safe_load((ROOT / "sot/fabric.yml").read_text())
    changes = yaml.safe_load(change.read_text())["changes"] if change else {}
    extra = {"bgp": fab["bgp"]} if "bgp" in fab else {}
    return {
        host: env.get_template(f"{dev['platform']}.j2").render(
            inventory_hostname=host, dev=dev, ospf=fab["ospf"], devices=fab["devices"], **extra,
            extra_loopbacks=changes.get(host, {}).get("loopbacks", []),
        )
        for host, dev in fab["devices"].items()
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--change", type=Path)
    args = ap.parse_args()
    fab = yaml.safe_load((ROOT / "sot/fabric.yml").read_text())
    for host, cfg in render_all(args.change).items():
        print(f"!---------------- {host} ({fab['devices'][host]['platform']}) ----------------")
        print(cfg)


if __name__ == "__main__":
    main()
