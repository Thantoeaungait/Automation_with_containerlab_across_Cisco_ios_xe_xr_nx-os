"""Lab device registry for the API scripts (override hosts via env for remote runners)."""
import os

DEVICES = {
    "xe1": {"host": os.getenv("XE1_HOST", "172.30.30.11"), "username": "admin", "password": "admin", "os": "iosxe"},
    "xr1": {"host": os.getenv("XR1_HOST", "172.30.30.12"), "username": "clab", "password": "clab@123", "os": "iosxr"},
    "nx1": {"host": os.getenv("NX1_HOST", "172.30.30.13"), "username": "admin", "password": "admin", "os": "nxos"},
}
