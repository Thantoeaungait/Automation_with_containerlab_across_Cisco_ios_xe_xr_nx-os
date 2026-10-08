#!/usr/bin/env python3
"""Push the SoT into NetBox (one-way, idempotent): sites, platforms, devices, interfaces, IPs, cables.

sot/fabric.yml stays the source of truth; NetBox becomes a browsable, API-queryable copy -
the usual first step before NetBox takes over as the SoT in a larger network.

  make netbox-sync          URL from services.netbox.url, token from vault netbox.token
                            (or NETBOX_URL / NETBOX_TOKEN environment variables)
Needs: pip install -r requirements-optional.txt, and a running NetBox (see docs/PRODUCTION-PHASE2.md).
"""
from __future__ import annotations

import ipaddress
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab import sot  # noqa: E402

MODELS = {"iosxe": "Catalyst 8000V", "iosxr": "XRv 9000", "nxos": "Nexus 9000v"}


def slug(text: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-")


def get_or_create(endpoint, lookup: dict, extra: dict | None = None):
    obj = endpoint.get(**lookup)
    return obj if obj else endpoint.create({**lookup, **(extra or {})})


def connect(pynetbox, url: str, token: str):
    """NetBox 4.5+ v2 tokens ("nbt_<key>.<secret>") need "Bearer"; v1 tokens use "Token".

    pynetbox only adds its own "Token ..." header when token= is set, so v2 tokens go on the session.
    """
    token = token.strip().removeprefix("Bearer ").removeprefix("Token ").strip()   # pasted header value
    if token.startswith("nbt_"):
        nb = pynetbox.api(url)
        nb.http_session.headers["Authorization"] = f"Bearer {token}"
        return nb
    return pynetbox.api(url, token=token)


def main() -> int:
    try:
        import pynetbox
    except ImportError:
        sys.exit("pynetbox missing: .venv/bin/pip install -r requirements-optional.txt")
    fab = sot.fabric()
    cfg = fab["services"]["netbox"]
    url = os.environ.get("NETBOX_URL", cfg["url"])
    token = os.environ.get("NETBOX_TOKEN") or sot.secrets().get("netbox", {}).get("token")
    if not token or token.startswith("CHANGE_ME"):
        sys.exit("NetBox API token missing: create one in NetBox, then make vault-edit (netbox.token)")
    nb = connect(pynetbox, url, token)

    site = get_or_create(nb.dcim.sites, {"slug": slug(cfg["site"])}, {"name": cfg["site"], "status": "active"})
    cisco = get_or_create(nb.dcim.manufacturers, {"slug": "cisco"}, {"name": "Cisco"})
    role = get_or_create(nb.dcim.device_roles, {"slug": "router"}, {"name": "Router", "color": "2196f3"})

    nb_if: dict[tuple[str, str], object] = {}
    for name, dev in fab["devices"].items():
        plat = dev["platform"]
        platform = get_or_create(nb.dcim.platforms, {"slug": plat}, {"name": plat, "manufacturer": cisco.id})
        dtype = get_or_create(nb.dcim.device_types, {"slug": slug(MODELS[plat])},
                              {"model": MODELS[plat], "manufacturer": cisco.id})
        device = get_or_create(nb.dcim.devices, {"name": name, "site_id": site.id},
                               {"site": site.id, "role": role.id, "device_type": dtype.id,
                                "platform": platform.id, "status": "active"})
        mgmt = get_or_create(nb.dcim.interfaces, {"device_id": device.id, "name": "mgmt"},
                             {"device": device.id, "type": "virtual", "mgmt_only": True})
        mgmt_prefix = ipaddress.ip_network(fab["lab"]["mgmt_subnet"]).prefixlen
        mip = get_or_create(nb.ipam.ip_addresses, {"address": f"{dev['mgmt_ip']}/{mgmt_prefix}"},
                            {"assigned_object_type": "dcim.interface", "assigned_object_id": mgmt.id})
        device.primary_ip4 = mip.id
        device.save()
        for intf in dev["loopbacks"] + dev["interfaces"]:
            kind = "virtual" if "loopback" in intf["name"].lower() else "1000base-t"
            i = get_or_create(nb.dcim.interfaces, {"device_id": device.id, "name": intf["name"]},
                              {"device": device.id, "type": kind})
            nb_if[(name, intf["name"])] = i
            get_or_create(nb.ipam.ip_addresses, {"address": intf["ipv4"]},
                          {"assigned_object_type": "dcim.interface", "assigned_object_id": i.id})
        print(f"synced {name}")

    done = set()
    for name, dev in fab["devices"].items():
        for intf in dev["interfaces"]:
            peer = fab["devices"][intf["peer"]]
            net = ipaddress.ip_interface(intf["ipv4"]).network
            other = next(i for i in peer["interfaces"]
                         if i["peer"] == name and ipaddress.ip_interface(i["ipv4"]).network == net)
            key = frozenset({(name, intf["name"]), (intf["peer"], other["name"])})
            a, b = nb_if[(name, intf["name"])], nb_if[(intf["peer"], other["name"])]
            if key in done or a.cable or b.cable:
                continue
            done.add(key)
            nb.dcim.cables.create({
                "a_terminations": [{"object_type": "dcim.interface", "object_id": a.id}],
                "b_terminations": [{"object_type": "dcim.interface", "object_id": b.id}],
                "status": "connected"})
            print(f"cable {name}:{intf['name']} <-> {intf['peer']}:{other['name']}")
    print(f"NetBox in sync: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
