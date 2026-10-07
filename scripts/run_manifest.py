#!/usr/bin/env python3
"""Write reports/run-manifest.json: what ran, on what, and with which result.

Identifies a pipeline run beyond the JUnit/audit reports, so a run can be compared with a
rerun on another host: repository commit, containerlab and image identities, host facts,
per-stage result and duration, and the list of report files produced.
Called by scripts/ci.sh on exit (before the lab is destroyed).
"""
import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


def sh(*cmd: str) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def images(topo: Path) -> dict:
    """Image references from the topology (env defaults resolved) with their local IDs."""
    out = {}
    for ref in re.findall(r"image:\s*(\S+)", topo.read_text()):
        m = re.fullmatch(r"\$\{(\w+):=(.+)\}", ref)
        if m:
            ref = os.environ.get(m.group(1)) or m.group(2)
        out[ref] = sh("docker", "image", "inspect", "-f", "{{.Id}}", ref) or None
    return out


def stages() -> list[dict]:
    path = REPORTS / "stages.tsv"
    rows = []
    if path.exists():
        for line in path.read_text().splitlines():
            name, t0, t1, rc = line.split("\t")
            rows.append({"stage": name, "result": "passed" if rc == "0" else "failed",
                         "rc": int(rc), "seconds": int(t1) - int(t0)})
    return rows


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topo", default="topology/lab.clab.yml")
    ap.add_argument("--rc", type=int, default=0)
    args = ap.parse_args()
    topo = ROOT / args.topo

    mem_kb = next((int(l.split()[1]) for l in Path("/proc/meminfo").read_text().splitlines()
                   if l.startswith("MemTotal")), 0) if Path("/proc/meminfo").exists() else 0
    reports = sorted(p for p in REPORTS.glob("*") if p.is_file() and p.name != "run-manifest.json")
    manifest = {
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "result": "passed" if args.rc == 0 else "failed",
        "exit_code": args.rc,
        "repository": {
            "commit": sh("git", "-C", str(ROOT), "rev-parse", "HEAD") or None,
            "dirty": bool(sh("git", "-C", str(ROOT), "status", "--porcelain")),
            "topology": args.topo,
            "topology_sha256": sha256(topo) if topo.exists() else None,
            "sot_sha256": sha256(ROOT / "sot" / "fabric.yml"),
        },
        "host": {
            "hostname": platform.node(),
            "kernel": platform.release(),
            "vcpus": os.cpu_count(),
            "memory_gib": round(mem_kb / 1024 / 1024, 1),
        },
        "tools": {
            "containerlab": (sh("containerlab", "version").splitlines() or [""])[0] or None,
            "docker": sh("docker", "version", "-f", "{{.Server.Version}}") or None,
            "sizing": {k: os.environ.get(k) for k in
                       ("C8KV_MEMORY", "C8KV_SMP", "N9KV_MEMORY", "N9KV_SMP") if os.environ.get(k)},
        },
        "images": images(topo) if topo.exists() else {},
        "stages": stages(),
        "reports": {p.name: sha256(p) for p in reports},
    }
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "run-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"run manifest: {REPORTS / 'run-manifest.json'} ({manifest['result']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
