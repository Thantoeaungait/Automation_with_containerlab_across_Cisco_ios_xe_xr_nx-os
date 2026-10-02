"""Shared Nornir bootstrap: path-independent, so scripts run from any cwd."""
import logging
from pathlib import Path

from nornir import InitNornir
from nornir.core import Nornir

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent

# Paramiko logs every failed handshake (with full tracebacks) from its transport thread.
# With no handler configured, Python prints them to stderr via the "last resort" handler.
# Failures are already surfaced through Nornir results, so keep paramiko quiet.
for _name in ("paramiko", "paramiko.transport", "netmiko", "nornir", "nornir.core"):
    _log = logging.getLogger(_name)
    _log.setLevel(logging.CRITICAL)
    _log.addHandler(logging.NullHandler())
    _log.propagate = False


def init_nornir(workers: int = 10) -> Nornir:
    inv = BASE / "inventory"
    return InitNornir(
        runner={"plugin": "threaded", "options": {"num_workers": workers}},
        inventory={
            "plugin": "SimpleInventory",
            "options": {
                "host_file": str(inv / "hosts.yaml"),
                "group_file": str(inv / "groups.yaml"),
                "defaults_file": str(inv / "defaults.yaml"),
            },
        },
        logging={"enabled": False},
    )
