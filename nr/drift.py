#!/usr/bin/env python3
"""Config drift detection: compare each device's running-config with a "golden" copy.

  python nr/drift.py --save   # after a validated run: store running-configs as golden/
  python nr/drift.py          # compare now; diffs in reports/drift-<host>.diff; exit 1 on drift

Unlike `make drift-check` (Ansible check mode), this catches changes to lines the
automation doesn't manage, e.g. someone adding an ACL or a static route by hand.
"""
import argparse
import difflib
import re
import sys

from nornir.core.task import Result, Task
from nornir_netmiko.tasks import netmiko_send_command

from common import ROOT, init_nornir

GOLDEN_DIR = ROOT / "golden"
REPORT_DIR = ROOT / "reports"

# Lines that change on their own (timestamps, counters) and must not count as drift
VOLATILE = re.compile(
    r"^(Building configuration"
    r"|Current configuration"
    r"|! Last configuration change"
    r"|! NVRAM config last updated"
    r"|!Command:"
    r"|!Running configuration last done"
    r"|!Time:"
    r"|\w{3} \w{3} +\d+ \d+:\d+:\d+\.\d+ \w+$)"   # IOS XR command timestamp
)


def normalise(cfg: str) -> list[str]:
    return [l.rstrip() for l in cfg.splitlines() if l.strip() and not VOLATILE.match(l.strip())]


def fetch(task: Task) -> Result:
    mr = task.run(task=netmiko_send_command, command_string="show running-config", read_timeout=180)
    return Result(host=task.host, result=normalise(mr[0].result))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true", help="store current configs as the golden baseline")
    args = ap.parse_args()
    GOLDEN_DIR.mkdir(exist_ok=True)
    REPORT_DIR.mkdir(exist_ok=True)

    results = init_nornir().run(task=fetch, name="fetch running-config")
    rc = 0
    for host, mr in results.items():
        if mr.failed:
            print(f"{host:<5} ERROR    {mr[0].exception}")
            rc = 1
            continue
        current = mr[0].result
        golden_file = GOLDEN_DIR / f"{host}.cfg"

        if args.save:
            golden_file.write_text("\n".join(current) + "\n")
            print(f"{host:<5} SAVED    {golden_file}")
            continue

        if not golden_file.exists():
            print(f"{host:<5} NO-GOLDEN  run: make golden")
            rc = 1
            continue

        golden = golden_file.read_text().splitlines()
        diff = list(difflib.unified_diff(golden, current, f"golden/{host}.cfg", f"running/{host}",
                                         lineterm="", n=1))
        report = REPORT_DIR / f"drift-{host}.diff"
        if diff:
            report.write_text("\n".join(diff) + "\n")
            added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
            removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
            print(f"{host:<5} DRIFT    +{added} / -{removed} lines  -> {report}")
            rc = 1
        else:
            report.unlink(missing_ok=True)
            print(f"{host:<5} OK       matches golden")
    return rc


if __name__ == "__main__":
    sys.exit(main())
