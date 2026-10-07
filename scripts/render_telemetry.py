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
PATHS = {
    "nxos": ["/System/intf-items/phys-items", "/System/procsys-items/syscpusummary-items"],
    "iosxe": ["/interfaces/interface/state/counters"],
    "iosxr": ["/interfaces/interface/state/counters"],
}


def main() -> int:
    tel = sot.fabric()["services"]["telemetry"]
    if not tel.get("enabled"):
        print("telemetry disabled (services.telemetry.enabled: false) - nothing to render")
        return 0
    devs = sot.devices()
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
        subs[d["platform"]] = {"paths": PATHS[d["platform"]], "mode": "stream",
                               "stream-mode": "sample", "sample-interval": tel["sample_interval"]}
    gnmic = {"log": True, "targets": targets, "subscriptions": subs,
             "outputs": {"prom": {"type": "prometheus", "listen": ":9804",
                                  "strings-as-labels": True, "export-timestamps": True}}}
    prom = {"global": {"scrape_interval": "15s"},
            "scrape_configs": [{"job_name": "gnmic",
                                "static_configs": [{"targets": [f"{tel['gnmic_ip']}:9804"]}]}]}
    graf = {"apiVersion": 1, "datasources": [{"name": "Prometheus", "type": "prometheus", "access": "proxy",
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
