# Production practices — phase 2

Part of the [approach to production](PRODUCTION.md). [Phase 1](PRODUCTION-PHASE1.md) covered
secrets, a single source of truth, AAA and TLS. Phase 2 adds what keeps changes safe and the network
observable:

| Topic | What you practise | Command |
|---|---|---|
| Rollback | Checkpoint before a change, automatic rollback when it fails | `make safe-change` |
| Failure testing | Break a link, measure reroute and recovery | `make failover-test` |
| Streaming telemetry | gNMI → gnmic → Prometheus → Grafana | `services.telemetry.enabled: true` |
| Offline validation | Check the intended configs with Batfish before touching a router | `make batfish` |
| NetBox | Keep a NetBox copy of the SoT through its API | `make netbox-sync` |
| Self-hosted CI | Run the full lab pipeline from GitHub with an approval gate | `.github/workflows/lab.yml` |

Everything is optional and off by default, so `make ci` still runs on the same host resources.
`TACACS=1 FAILOVER=1 make ci` runs the full pipeline including the failure test.

---

## 1. Checkpoint, safe change and rollback

```bash
make checkpoint       # save a rollback point on every device
make rollback         # return to it
make safe-change      # checkpoint -> apply $(CHANGE) -> validate -> roll back if anything fails
```

| Platform | Checkpoint | Rollback |
|---|---|---|
| IOS XE | `copy running-config bootflash:mvauto-checkpoint.cfg` (with `file prompt quiet`) | `configure replace bootflash:mvauto-checkpoint.cfg force` |
| NX-OS | `checkpoint mvauto` | `rollback running-config checkpoint mvauto` |
| IOS XR | latest commit ID saved to `reports/checkpoint/xr1.commit` | `rollback configuration to <commit-id>` |

**Try it with a change that fails on purpose:**

```bash
make safe-change CHANGE=sot/changes/bad-overlap.yml
```

`bad-overlap.yml` gives xe1 a loopback inside its own link subnet. IOS XE rejects it, the target
rolls every device back and re-validates (`reports/validation-after-rollback.xml`).
A good change (`make safe-change`, default `loopback100.yml`) is validated and kept.

Command syntax varies a little between releases; if a checkpoint or rollback task fails, check it
on the device with `?`.

## 2. Failure testing

```bash
make failover-test
FAILOVER=1 ./scripts/ci.sh     # include it in the pipeline
```

The link comes from the SoT (`failover:`): by default xe1 Gi2, the xe1–xr1 link. The test:

1. checks xe1 has all its OSPF neighbors;
2. adds 100 % packet loss on that link with `containerlab tools netem` (container side);
3. waits for the neighbor to drop and for xe1 to reach xr1's Loopback0 again **via nx1**,
   and records how long each took;
4. removes the loss and waits for full recovery.

Expect around 40 seconds to detect the failure: that is the OSPF dead interval, because the lab
has no BFD. Adding BFD and re-running the test is a good follow-up exercise.

`netem` needs `clab_admins` membership (or passwordless sudo). Container interfaces are mapped
from the SoT (`platforms.*.container_if`: Gi2 → eth1 on C8000v, Gi0/0/0/0 → eth1 on XRv9000,
Ethernet1/1 → eth1 on N9Kv).

## 3. Streaming telemetry

```yaml
# sot/fabric.yml
services:
  telemetry:
    enabled: true
```

```bash
make topology            # adds gnmic, prometheus and grafana containers
make deploy wait bootstrap configure
```

| Service | From the lab host | From another machine | Notes |
|---|---|---|---|
| gnmic | http://172.30.30.21:9804/metrics | http://&lt;lab-host-ip&gt;:9804/metrics | Subscribes to `services.telemetry.targets` (nx1) |
| Prometheus | http://172.30.30.22:9090 | http://&lt;lab-host-ip&gt;:9090 | Scrapes gnmic |
| Grafana | http://172.30.30.23:3000 | http://&lt;lab-host-ip&gt;:3000 | `admin` / `admin` on first login; Prometheus pre-configured |

The 172.30.30.x addresses live on a Docker bridge inside the lab host, so a browser on your laptop
(or Windows/WSL) cannot reach them. The containers therefore also publish their ports on the lab
host (`services.telemetry.host_ports`); use the lab host's IP (`hostname -I`). If the host has a
firewall: `sudo ufw allow 3000,9090/tcp`. Check everything with `make telemetry-status`.

**If no samples arrive** (`make telemetry-status` shows `0 sample lines` and the gnmic log shows
`authentication handshake failed: EOF` for nx1): the TLS handshake to NX-OS fails. The generated
gnmic container sets `GODEBUG: tlsrsakex=1` to re-enable the RSA key-exchange ciphers that newer
gnmic builds drop and some NX-OS gRPC servers still need (`services.telemetry.gnmic_env`). Its
memory is capped at 512 MB (`gnmic_memory`), because a failing retry loop otherwise keeps growing.
If gnmic **restarts every `sample_interval` with exit 0** and no error, the subscribed NX-OS path is
too broad: the defaults subscribe only to the interface counters (`dbgIfIn-items`, `dbgIfOut-items`)
and CPU summary, not the whole `phys-items` subtree.

**Dashboard:** Grafana loads `topology/grafana/dashboards/nx1-telemetry.json` at deploy time
(folder *mvauto*): inbound/outbound bit/s, unicast packets/s, errors + discards, CPU summary.
On a Grafana that was deployed before this file existed, import it once: Dashboards → New → Import →
upload the JSON. To keep UI changes, export the JSON (Share → Export) back into that folder.

In Prometheus, metrics are named after the gNMI origin and path, so NX-OS metrics start with
`device_System_` (query `{__name__=~"device_System_.*"}` or type `device_` for autocomplete). On this N9Kv image the DME counters arrive multiplied by 2^32
(32-bit halves swapped; checked against `show interface`), so divide by 4294967296. Examples:
`sum by (id) (rate(device_System_intf_items_phys_items_PhysIf_list_0_dbgIfIn_items_octets{id!=""}[2m])) / 4294967296 * 8`
(inbound bit/s per interface) and `device_System_procsys_items_syscpusummary_items_idle` (CPU idle %). NX-OS uses native
(DME) paths because this image has no OpenConfig bundle; change them in `PATHS` in
`scripts/render_telemetry.py`. About 0.5 GB RAM in total (gnmic capped at 512 MB).

Exercise: build a Grafana panel for interface counters, then run `make failover-test` and watch
the traffic move.

## 4. Batfish

Batfish analyses configuration files and answers questions about the network they describe,
without any router running. Run it while the lab is **down** (it needs 2–3 GB RAM).

```bash
make deps-optional       # pybatfish, pynetbox
make batfish             # starts the batfish/allinone container if needed
make batfish CHANGE=sot/changes/loopback100.yml
docker rm -f batfish     # when done
```

It renders the same templates Ansible uses, adds the interface state that Ansible sets through
resource modules (`no shutdown`, `no switchport`), and checks parse issues, OSPF and BGP session
compatibility, and Loopback0 reachability. Snapshot in `reports/batfish/snapshot/`.

Rendered snippets are not full device configs, so treat parse warnings with judgement; a failing
session or traceroute is the useful signal.

## 5. NetBox

NetBox is the most common production SoT. Here `sot/fabric.yml` stays authoritative and NetBox
receives a copy through its API, so you can learn both sides.

Run NetBox on another machine, or on the lab host while the lab is down (about 1.5 GB):

```bash
git clone -b release https://github.com/netbox-community/netbox-docker.git
cd netbox-docker
docker compose up -d                                   # first start takes a few minutes
docker compose exec netbox /opt/netbox/netbox/manage.py createsuperuser
```

In NetBox create an API token (user menu → API Tokens), then:

```bash
make vault-edit          # set netbox.token (and services.netbox.url in the SoT if not localhost)
make deps-optional
make netbox-sync
```

The sync is idempotent: sites, platforms, device types, devices with management IPs, interfaces,
IP addresses and cables. Next step when you are comfortable: read inventory from NetBox
(`netbox.netbox.nb_inventory`) and make NetBox the SoT.

## 6. Self-hosted runner

`.github/workflows/lab.yml` runs `scripts/ci.sh` on your lab host and uploads `reports/` and
`backups/` (including `run-manifest.json`) as an artifact.

1. GitHub → Settings → Actions → Runners → **New self-hosted runner**, follow the Linux steps on the
   lab host, and add the labels `clab` (plus the defaults `self-hosted`, `linux`).
2. The runner user needs the lab setup: docker / kvm / clab_admins groups, images, and the vault
   password file at `~/.config/mvauto/vault-pass`.
3. Settings → Environments → **lab** → add yourself as required reviewer, so every run waits for approval.
4. Actions → **lab** → Run workflow.

The workflow is manual-only on purpose: on a public repository, never let pull requests from forks
run on a self-hosted runner.

## What's left for later

See also [gaps before real devices](PRODUCTION.md#gaps-before-real-devices).

- Event-driven automation (Ansible rulebooks reacting to syslog or alerts)
- Service automation: L3VPN on IOS XR/IOS XE, EVPN/VXLAN on NX-OS (check N9Kv-lite data-plane limits)
- Full configuration replace from complete rendered configs
- BFD, and syslog collection (e.g. Loki)
