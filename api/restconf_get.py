#!/usr/bin/env python3
"""RESTCONF smoke test (IOS XE + NX-OS). IOS XR does not implement RESTCONF -> use NETCONF/gNMI.

  python api/restconf_get.py
  python api/restconf_get.py --set-description "managed-by-restconf"   # PATCH on xe1 Loopback0
"""
import argparse
import json
import sys
import time
from xml.dom import minidom

import requests
import urllib3

from lab_devices import DEVICES

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
HEADERS = {"Accept": "application/yang-data+json", "Content-Type": "application/yang-data+json"}

READS = {
    "xe1": ["/restconf/data/Cisco-IOS-XE-native:native/hostname",
            "/restconf/data/Cisco-IOS-XE-native:native/router/Cisco-IOS-XE-ospf:router-ospf"],
    "nx1": ["/restconf/data/Cisco-NX-OS-device:System/name"],
}


def get(session: requests.Session, url: str, retries: int = 6) -> requests.Response:
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, headers=HEADERS, verify=False, timeout=30)
            if r.status_code < 500:
                return r
        except requests.RequestException as exc:
            print(f"  attempt {attempt}: {exc}")
        time.sleep(10)
    raise RuntimeError(f"giving up on {url}")


def render(r: requests.Response) -> str:
    """Pretty-print a RESTCONF body as JSON or XML, whichever the device returned.

    Some NX-OS releases answer with YANG XML even when JSON is requested (HTTP 200).
    """
    ctype = r.headers.get("Content-Type", "")
    try:
        if "json" in ctype or r.text.lstrip().startswith(("{", "[")):
            return json.dumps(r.json(), indent=2)
        if "xml" in ctype or r.text.lstrip().startswith("<"):
            return minidom.parseString(r.text).toprettyxml(indent="  ").split("\n", 1)[1].strip()
    except ValueError:
        pass
    return r.text.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set-description", help="PATCH xe1 Loopback0 description via RESTCONF")
    args = ap.parse_args()
    failed = False

    for name, paths in READS.items():
        d = DEVICES[name]
        s = requests.Session()
        s.auth = (d["username"], d["password"])
        print(f"=== {name} (https://{d['host']}) ===")
        for path in paths:
            try:
                r = get(s, f"https://{d['host']}{path}")
                ctype = r.headers.get("Content-Type", "unknown").split(";")[0]
                print(f"  GET {path} -> {r.status_code} ({ctype})")
                if r.ok and r.text:
                    print("  " + render(r).replace("\n", "\n  "))
                elif not r.ok:
                    failed = True
            except Exception as exc:
                print(f"  FAILED: {exc}")
                failed = True

    if args.set_description:
        d = DEVICES["xe1"]
        url = f"https://{d['host']}/restconf/data/Cisco-IOS-XE-native:native/interface/Loopback=0"
        body = {"Cisco-IOS-XE-native:Loopback": {"name": 0, "description": args.set_description}}
        r = requests.patch(url, auth=(d["username"], d["password"]), headers=HEADERS,
                           json=body, verify=False, timeout=30)
        print(f"PATCH Loopback0 description -> {r.status_code}")
        failed |= not r.ok

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
