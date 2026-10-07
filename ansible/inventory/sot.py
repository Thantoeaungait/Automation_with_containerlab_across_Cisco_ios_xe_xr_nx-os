#!/usr/bin/env python3
"""Ansible dynamic inventory built from sot/fabric.yml (single source of truth).

Credentials are NOT emitted here: group_vars/lab.yml maps them from the vault
(group_vars/all/vault.yml -> secrets/vault.yml, decrypted by Ansible).
  ansible-inventory --graph        show the generated inventory
"""
import json
import sys
from pathlib import Path

import yaml

FABRIC = Path(__file__).resolve().parents[2] / "sot" / "fabric.yml"


def build() -> dict:
    fab = yaml.safe_load(FABRIC.read_text())
    inv = {"_meta": {"hostvars": {}}, "all": {"children": ["lab"]}, "lab": {"children": []}}
    for plat, p in fab["platforms"].items():
        inv["lab"]["children"].append(plat)
        inv[plat] = {"hosts": [], "vars": {"ansible_network_os": p["ansible_network_os"]}}
    for name, d in fab["devices"].items():
        inv[d["platform"]]["hosts"].append(name)
        inv["_meta"]["hostvars"][name] = {"ansible_host": d["mgmt_ip"], "platform": d["platform"]}
    return inv


if __name__ == "__main__":
    if "--host" in sys.argv:
        print("{}")
    else:
        print(json.dumps(build(), indent=2))
