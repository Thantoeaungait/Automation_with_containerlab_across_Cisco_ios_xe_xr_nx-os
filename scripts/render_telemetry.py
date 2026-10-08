#!/usr/bin/env python3
"""Render the telemetry stack configs from the SoT + vault (services.telemetry).

  topology/configs/telemetry/gnmic.yaml               targets + credentials (git-ignored)
  topology/configs/telemetry/prometheus.yml           scrapes gnmic's Prometheus output
  topology/configs/telemetry/grafana-datasource.yaml  Prometheus as Grafana's default data source
Does nothing when services.telemetry.enabled is false.
"""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab import sot  # noqa: E402

OUT = ROOT / "topology" / "configs" / "telemetry"

# Native NX-OS (DME) paths: this lab's NX-OS image has no OpenConfig bundle.
# - Keep them narrow: the whole /System/intf-items/phys-items subtree makes NX-OS end the stream at the
#   first sample (gnmic exits 0 every sample_interval, no samples).
# - Key the interface list: with JSON encoding an unkeyed PhysIf-list arrives as ONE blob, gnmic flattens
#   it to PhysIf_list_0_..., PhysIf_list_1_... and every interface id becomes a label of a single series.
#   One keyed path per SoT interface gives one series per interface (see nxos_paths()).
NXOS_IF_LEAVES = ["dbgIfIn-items", "dbgIfOut-items"]
PATHS = {
    "nxos": ["/System/procsys-items/syscpusummary-items"],
    "iosxe": ["/interfaces/interface/state/counters"],
    "iosxr": ["/interfaces/interface/state/counters"],
}


def nxos_paths(dev: dict) -> list[str]:
    """Per-interface keyed DME paths for the device's SoT interfaces (Ethernet1/1 -> PhysIf-list[id=eth1/1])."""
    paths = []
    for itf in dev.get("interfaces", []):
        name = itf["name"]
        if name.lower().startswith("ethernet"):
            key = "eth" + name[len("ethernet"):]
            paths += [f"/System/intf-items/phys-items/PhysIf-list[id={key}]/{leaf}" for leaf in NXOS_IF_LEAVES]
    return paths


def main() -> int:
    tel = sot.fabric()["services"]["telemetry"]
    if not tel.get("enabled"):
        print("telemetry disabled (services.telemetry.enabled: false) - nothing to render")
        return 0
    devs = sot.devices()
    fab_devs = sot.fabric()["devices"]
    targets, subs = {}, {}
    for name in tel["targets"]:
        d = devs[name]
        g = d["gnmi"]
        t = {"name": name, "username": d["username"], "password": d["password"],
             "encoding": g["encoding"], "subscriptions": [d["platform"]]}
        ca = sot.lab_ca()
        if g["tls"] == "insecure":
            t["insecure"] = True
        elif ca:
            t["tls-ca"] = "/app/ca.crt"
        else:
            t["skip-verify"] = True
        targets[f"{d['mgmt_ip']}:57400"] = t
        paths = list(subs.get(d["platform"], {}).get("paths", PATHS[d["platform"]]))
        if d["platform"] == "nxos":
            paths += [x for x in nxos_paths(fab_devs[name]) if x not in paths]
        subs[d["platform"]] = {"paths": paths, "mode": "stream",
                               "stream-mode": "sample", "sample-interval": tel["sample_interval"]}
    # export-timestamps off: Prometheus stamps samples at scrape time. Device timestamps gave rate() spikes
    # of hundreds of Gb/s for a few-Mb/s ping on NX-OS.
    gnmic = {"log": True, "targets": targets, "subscriptions": subs,
             "outputs": {"prom": {"type": "prometheus", "listen": ":9804",
                                  "strings-as-labels": True, "export-timestamps": False}}}
    prom = {"global": {"scrape_interval": "15s"},
            "scrape_configs": [{"job_name": "gnmic",
                                "static_configs": [{"targets": [f"{tel['gnmic_ip']}:9804"]}]}]}
    graf = {"apiVersion": 1, "datasources": [{"name": "Prometheus", "uid": "prometheus", "type": "prometheus", "access": "proxy",
                                              "url": f"http://{tel['prometheus_ip']}:9090", "isDefault": True}]}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "gnmic.yaml").write_text(yaml.safe_dump(gnmic, sort_keys=False))
    (OUT / "gnmic.yaml").chmod(0o644)   # read by the container user; git-ignored, lab credentials only
    (OUT / "prometheus.yml").write_text(yaml.safe_dump(prom, sort_keys=False))
    (OUT / "grafana-datasource.yaml").write_text(yaml.safe_dump(graf, sort_keys=False))
    print(f"wrote {OUT.relative_to(ROOT)}/ ({len(targets)} gNMI target(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
