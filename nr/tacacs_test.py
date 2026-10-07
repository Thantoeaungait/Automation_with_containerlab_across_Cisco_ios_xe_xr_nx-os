#!/usr/bin/env python3
"""Check TACACS+ end to end: log in as a TACACS-only human account (vault tacacs.users).

A successful login proves the device asked the TACACS+ server: that account doesn't exist
locally. Also prints the server's access and accounting logs, and on failure the device's
AAA state (collected with the automation account through the local fallback).
"""
import re
import subprocess
import sys

from nornir_netmiko.tasks import netmiko_send_command

from common import init_nornir, sot

# Shown for a device that rejected the TACACS+ login (collected with the automation account,
# which still works through the local fallback). {ip} = TACACS+ server.
DIAG = {
    "iosxe": ["show running-config | section ^aaa|^tacacs|^line vty|^ip tacacs",
              "show tacacs", "show aaa servers", "ping vrf clab-mgmt {ip} repeat 2"],
    "nxos": ["show running-config tacacs+", "show tacacs-server", "ping {ip} vrf management count 2"],
}


def diagnose(nr, server_ip: str) -> None:
    """Dump AAA state from the failed devices, logged in with the automation account."""
    def task(t):
        out = []
        for cmd in DIAG.get(t.host.data["platform_key"], []):
            cmd = cmd.format(ip=server_ip)
            r = t.run(task=netmiko_send_command, command_string=cmd, read_timeout=60)
            out.append(f"[{t.host}] # {cmd}\n" + re.sub(r"(key(?: [067])?) \S+", r"\1 ***", r.result))
        return "\n\n".join(out)
    for name, mr in nr.run(task=task).items():
        print(f"[{name}] diagnostics failed: {mr[0].exception}" if mr.failed else mr[0].result)


def main() -> int:
    fab, sec = sot.fabric(), sot.secrets()
    user, password = next(iter(sec["tacacs"]["users"].items()))
    targets = set(fab["services"]["tacacs"]["apply_to"])
    nr = init_nornir().filter(filter_func=lambda h: h.data["platform_key"] in targets)
    for host in nr.inventory.hosts.values():
        host.username, host.password = user, password

    results = nr.run(task=netmiko_send_command, command_string="show users", read_timeout=60)
    failed = []
    for host, mr in results.items():
        if mr.failed:
            print(f"FAIL  {host:<4} login as '{user}' via TACACS+: {type(mr[0].exception).__name__}")
            failed.append(host)
        else:
            print(f"PASS  {host:<4} login as '{user}' via TACACS+")
    nr.close_connections()

    # The access log records failed logins with the device's source IP; the accounting log
    # only has sessions that got in. No line from a device = it never reached the server.
    container = f"clab-{fab['lab']['name']}-tacacs"
    for log in ("access", "acct"):
        print(f"\n--- TACACS+ {log} log (last 10 lines) ---", flush=True)
        subprocess.run(["docker", "exec", container, "tail", "-n", "10", f"/var/log/tac_plus.{log}"],
                       check=False)

    if failed:
        print("\n--- diagnostics (automation account, local fallback) ---")
        diagnose(init_nornir().filter(filter_func=lambda h: h.name in failed),
                 fab["services"]["tacacs"]["mgmt_ip"])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
