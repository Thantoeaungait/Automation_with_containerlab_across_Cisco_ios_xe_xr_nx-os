"""Shared Nornir bootstrap. Inventory comes from the single source of truth (lab/sot.py)."""
import logging
import sys
from pathlib import Path

from nornir import InitNornir
from nornir.core import Nornir
from nornir.core.inventory import (ConnectionOptions, Defaults, Group, Groups, Host, Hosts,
                                   Inventory, ParentGroups)
from nornir.core.plugins.inventory import InventoryPluginRegister

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
sys.path.insert(0, str(ROOT))
from lab import sot  # noqa: E402

# Paramiko/Netmiko/Nornir log every failed attempt with full tracebacks; failures are
# already reported through Nornir results, so keep those loggers quiet.
for _name in ("paramiko", "paramiko.transport", "netmiko", "nornir", "nornir.core"):
    _log = logging.getLogger(_name)
    _log.setLevel(logging.CRITICAL)
    _log.addHandler(logging.NullHandler())
    _log.propagate = False


class SotInventory:
    """Nornir inventory plugin: one group per platform, one host per SoT device."""

    def load(self) -> Inventory:
        defaults = Defaults(connection_options={"netmiko": ConnectionOptions(extras={
            "conn_timeout": 30, "auth_timeout": 60, "banner_timeout": 15, "fast_cli": False})})
        groups, hosts = Groups(), Hosts()
        for name, d in sot.devices().items():
            plat = d["platform"]
            if plat not in groups:
                groups[plat] = Group(name=plat, platform=d["netmiko"], defaults=defaults)
            hosts[name] = Host(name=name, hostname=d["mgmt_ip"], username=d["username"],
                               password=d["password"], groups=ParentGroups([groups[plat]]),
                               data={"platform_key": plat}, defaults=defaults)
        return Inventory(hosts=hosts, groups=groups, defaults=defaults)


InventoryPluginRegister.register("SotInventory", SotInventory)


def init_nornir(workers: int = 10) -> Nornir:
    return InitNornir(
        runner={"plugin": "threaded", "options": {"num_workers": workers}},
        inventory={"plugin": "SotInventory"},
        logging={"enabled": False},
    )
