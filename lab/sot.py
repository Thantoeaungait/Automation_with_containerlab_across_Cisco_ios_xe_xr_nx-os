"""Single source of truth loader shared by every tool in the lab.

  sot/fabric.yml      intent, devices, platforms, services   (in Git)
  secrets/vault.yml   credentials and keys, ansible-vault encrypted (NOT in Git)

CLI helpers (run from the repo root with the venv python):
  python -m lab.sot env            export lines with device credentials (for genie CLI)
  python -m lab.sot testbed        pyATS testbed YAML using %ENV{} for passwords
  python -m lab.sot gnmi-targets   name|address|user|password|tls|encoding|path per device
"""
from __future__ import annotations

import os
import shlex
import sys
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
FABRIC = ROOT / "sot" / "fabric.yml"
VAULT = ROOT / "secrets" / "vault.yml"
CA_CERT = ROOT / "secrets" / "pki" / "ca.crt"
DEFAULT_PASS_FILE = Path.home() / ".config" / "mvauto" / "vault-pass"


@lru_cache
def fabric() -> dict:
    return yaml.safe_load(FABRIC.read_text())


def _vault_password() -> bytes:
    path = Path(os.environ.get("ANSIBLE_VAULT_PASSWORD_FILE", DEFAULT_PASS_FILE)).expanduser()
    if not path.exists():
        sys.exit(f"Vault password file not found: {path}  ->  run: make vault-init")
    return path.read_bytes().strip()


@lru_cache
def secrets() -> dict:
    """Decrypt secrets/vault.yml with the same password file Ansible uses."""
    if not VAULT.exists():
        sys.exit(f"{VAULT} not found  ->  run: make vault-init")
    raw = VAULT.read_bytes()
    if raw.startswith(b"$ANSIBLE_VAULT"):
        from ansible.constants import DEFAULT_VAULT_ID_MATCH
        from ansible.parsing.vault import VaultLib, VaultSecret

        vault = VaultLib([(DEFAULT_VAULT_ID_MATCH, VaultSecret(_vault_password()))])
        raw = vault.decrypt(raw)
    else:
        print(f"WARNING: {VAULT} is not encrypted - run: make vault-encrypt", file=sys.stderr)
    return yaml.safe_load(raw)


def devices() -> dict[str, dict]:
    """Devices merged with their platform settings and credentials."""
    fab, sec = fabric(), secrets()
    out = {}
    for name, dev in fab["devices"].items():
        plat = dev["platform"]
        creds = sec["credentials"][plat]
        out[name] = {**fab["platforms"][plat], **dev, "name": name,
                     "username": creds["username"], "password": creds["password"]}
    return out


def lab_ca() -> Path | None:
    """CA bundle for TLS verification, or None while device certificates aren't installed."""
    enforce = fabric().get("pki", {}).get("verify_with_lab_ca", False)
    return CA_CERT if enforce and CA_CERT.exists() else None


def env_var(name: str) -> str:
    return f"MVAUTO_{name.upper()}_PASSWORD"


def pyats_testbed(use_env: bool = False) -> dict:
    """pyATS testbed as a dict (genie.testbed.load accepts it directly)."""
    tb = {"testbed": {"name": fabric()["lab"]["name"]}, "devices": {}}
    for name, d in devices().items():
        password = f"%ENV{{{env_var(name)}}}" if use_env else d["password"]
        tb["devices"][name] = {
            "os": d["pyats_os"],
            "type": "router",
            "credentials": {"default": {"username": d["username"], "password": password}},
            "connections": {"cli": {
                "protocol": "ssh", "ip": d["mgmt_ip"], "port": 22,
                "ssh_options": "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null",
            }},
        }
    return tb


def gnmi_targets() -> list[str]:
    lines = []
    for name, d in devices().items():
        g = d["gnmi"]
        tls = g["tls"]
        if tls == "skip-verify" and lab_ca():
            tls = f"tls-ca={lab_ca()}"      # device certs signed by our CA (make pki + install)
        lines.append("|".join([name, d["mgmt_ip"], d["username"], d["password"], tls, g["encoding"], g["path"]]))
    return lines


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "env":
        for name, d in devices().items():
            print(f"export {env_var(name)}={shlex.quote(d['password'])}")
    elif cmd == "testbed":
        print(yaml.safe_dump(pyats_testbed(use_env=True), sort_keys=False))
    elif cmd == "gnmi-targets":
        print("\n".join(gnmi_targets()))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
