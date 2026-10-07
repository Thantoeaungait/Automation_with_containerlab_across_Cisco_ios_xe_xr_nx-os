"""Device registry for the API scripts, built from the single source of truth."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab import sot  # noqa: E402

DEVICES = {
    name: {"host": d["mgmt_ip"], "username": d["username"], "password": d["password"],
           "os": d["platform"], "ncclient": d["ncclient"]}
    for name, d in sot.devices().items()
}
CA_CERT = sot.lab_ca()   # None until pki.verify_with_lab_ca is true in the SoT
