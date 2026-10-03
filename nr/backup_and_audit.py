#!/usr/bin/env python3
"""Back up running configs and run a simple compliance audit (regex rules per platform).

Rule levels:
  REQUIRED  - missing -> VIOLATION, script exits 1 (fails the pipeline)
  OPTIONAL  - missing -> WARNING only (feature depends on image/license, e.g. gNMI on C8000v)

Outputs:
  backups/<host>.cfg
  reports/audit.json
Exit code 1 if any device violates a REQUIRED rule or can't be reached.
"""
import json
import re
import sys
from datetime import datetime, timezone

from nornir.core.task import Result, Task
from nornir_netmiko.tasks import netmiko_send_command

from common import ROOT, init_nornir

BACKUP_DIR = ROOT / "backups"
REPORT_DIR = ROOT / "reports"

# Each rule must match at least one line of the running config (multiline regex).
REQUIRED: dict[str, dict[str, str]] = {
    "cisco_xe": {
        "netconf enabled": r"^netconf-yang$",
        "restconf enabled": r"^restconf$",
        "ospf process": r"^router ospf 1$",
    },
    "cisco_xr": {
        "netconf agent": r"^netconf-yang agent$",
        "grpc enabled": r"^grpc$",
        "ospf process": r"^router ospf 1$",
    },
    "cisco_nxos": {
        "netconf feature": r"^feature netconf$",
        "grpc feature": r"^feature grpc$",
        "ospf feature": r"^feature ospf$",
        "ospf process": r"^router ospf 1$",
    },
}

OPTIONAL: dict[str, dict[str, str]] = {
    "cisco_xe": {
        "gnmi server enabled": r"^(gnxi|gnmi-yang) server$",  # absent on unlicensed C8000v images
    },
}


def missing(rules: dict[str, str], cfg: str) -> list[str]:
    return [name for name, rx in rules.items() if not re.search(rx, cfg, re.MULTILINE)]


def backup_and_audit(task: Task) -> Result:
    mr = task.run(task=netmiko_send_command, command_string="show running-config", read_timeout=180)
    cfg: str = mr[0].result
    (BACKUP_DIR / f"{task.host.name}.cfg").write_text(cfg)

    required = REQUIRED.get(task.host.platform, {})
    optional = OPTIONAL.get(task.host.platform, {})
    return Result(
        host=task.host,
        result={
            "lines": len(cfg.splitlines()),
            "checked": len(required) + len(optional),
            "violations": missing(required, cfg),
            "warnings": missing(optional, cfg),
        },
    )


def main() -> int:
    BACKUP_DIR.mkdir(exist_ok=True)
    REPORT_DIR.mkdir(exist_ok=True)

    nr = init_nornir()
    results = nr.run(task=backup_and_audit, name="backup+audit")

    report = {"timestamp": datetime.now(timezone.utc).isoformat(), "devices": {}}
    rc = 0
    print(f"{'host':<5} {'status':<10} {'lines':>6}  details")
    for host, mr in results.items():
        if mr.failed:
            report["devices"][host] = {"error": str(mr[0].exception)}
            print(f"{host:<5} {'ERROR':<10} {'-':>6}  {mr[0].exception}")
            rc = 1
            continue
        data = mr[0].result
        report["devices"][host] = data
        if data["violations"]:
            status, rc = "VIOLATION", 1
        elif data["warnings"]:
            status = "WARNING"
        else:
            status = "COMPLIANT"
        details = [f"missing: {v}" for v in data["violations"]] + [f"optional missing: {w}" for w in data["warnings"]]
        print(f"{host:<5} {status:<10} {data['lines']:>6}  {', '.join(details) or '-'}")

    (REPORT_DIR / "audit.json").write_text(json.dumps(report, indent=2))
    print(f"\nBackups: {BACKUP_DIR}/   Report: {REPORT_DIR / 'audit.json'}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
