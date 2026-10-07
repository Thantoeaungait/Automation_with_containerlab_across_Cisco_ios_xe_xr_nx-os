#!/usr/bin/env python3
"""NETCONF smoke test across IOS XE, IOS XR and NX-OS.

One vendor-neutral OpenConfig subtree filter is sent to every platform; NX-OS falls back
to its native device model if the OpenConfig bundle isn't present on that release.
"""
import logging
import sys
import time

from ncclient import manager

from lab_devices import DEVICES

for _n in ("paramiko", "paramiko.transport", "ncclient"):
    logging.getLogger(_n).setLevel(logging.CRITICAL)
    logging.getLogger(_n).propagate = False

OC_NS = "http://openconfig.net/yang/interfaces"
OC_FILTER = f'<interfaces xmlns="{OC_NS}"><interface><name/><state><oper-status/></state></interface></interfaces>'
NX_NS = "http://cisco.com/ns/yang/cisco-nx-os-device"
NX_FILTER = f'<System xmlns="{NX_NS}"><name/></System>'


def connect(d: dict, retries: int = 10, delay: int = 15):
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return manager.connect(
                host=d["host"], port=d.get("netconf_port", 830), username=d["username"], password=d["password"],
                hostkey_verify=False, look_for_keys=False, allow_agent=False,
                device_params={"name": d["ncclient"]}, timeout=60,
            )
        except Exception as exc:  # agent may still be starting right after bootstrap
            last = exc
            print(f"  attempt {attempt}/{retries} failed: {exc}")
            time.sleep(delay)
    raise RuntimeError(f"NETCONF unreachable: {last}")


def main() -> int:
    failed = False
    for name, d in DEVICES.items():
        print(f"=== {name} ({d['host']}:{d.get('netconf_port', 830)}, {d['os']}) ===")
        try:
            with connect(d) as m:
                caps = list(m.server_capabilities)
                print(f"  session-id={m.session_id}  capabilities={len(caps)}")
                if any(OC_NS in c for c in caps):
                    try:
                        reply = m.get(filter=("subtree", OC_FILTER))
                        for intf in reply.data_ele.iter(f"{{{OC_NS}}}interface"):
                            iname = intf.findtext(f"{{{OC_NS}}}name")
                            state = intf.findtext(f".//{{{OC_NS}}}oper-status")
                            print(f"    {iname:<28} {state}")
                        continue
                    except Exception as exc:
                        print(f"  WARN OpenConfig get failed: {exc}")
                if d["os"] == "nxos":
                    reply = m.get(filter=("subtree", NX_FILTER))
                    print(f"  hostname (native model): {reply.data_ele.findtext(f'.//{{{NX_NS}}}name')}")
        except Exception as exc:
            print(f"  FAILED: {exc}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
