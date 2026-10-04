# Automation with containerlab across Cisco IOS XE, IOS XR and NX-OS

[![lint](https://github.com/Thantoeaungait/Automation_with_containerlab_across_Cisco_ios_xe_xr_nx-os/actions/workflows/lint.yml/badge.svg)](https://github.com/Thantoeaungait/Automation_with_containerlab_across_Cisco_ios_xe_xr_nx-os/actions/workflows/lint.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**A learning lab for Cisco network automation.** One containerlab topology runs a Catalyst 8000v,
an XRv9000 and a Nexus 9000v side by side. Ansible configures OSPF and iBGP from a single YAML
source of truth, pyATS validates the result, Nornir audits the devices and detects drift, and
NETCONF, RESTCONF and gNMI are tested from the host. The whole lifecycle — **deploy → configure →
validate → change → validate → prune → drift check → destroy** — runs with one command.

```
                 xe1  Catalyst 8000v (IOS XE)     172.30.30.11
             Gi2 /                       \ Gi3
        10.0.12.0/30                  10.0.13.0/30
      Gi0/0/0/0 /                           \ Eth1/2
   xr1  XRv9000 (IOS XR) —— 10.0.23.0/30 —— nx1  Nexus 9000v-lite (NX-OS)
   172.30.30.12   Gi0/0/0/1         Eth1/1         172.30.30.13

   OSPF area 0 (point-to-point) · Loopback0 1.1.1.1 / 2.2.2.2 / 3.3.3.3
   iBGP AS 65000 full mesh between Loopback0 · Loopback200 10.255.x.x advertised only via BGP
```

> **About this project.** I built this lab while learning network automation from scratch. I don't
> have experience in a real-world network automation job, so treat it as an educational lab, not a
> production framework. Every problem I hit along the way is documented with its fix in
> [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md). Feedback from experienced engineers is very welcome.

> **Cisco images are not included.** They are licensed software; you must obtain them yourself.
> See [docs/IMAGES.md](docs/IMAGES.md).

---

## Contents

- [What you'll practice](#what-youll-practice)
- [Tested versions](#tested-versions)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Pipeline stages](#pipeline-stages)
- [How each tool connects](#how-each-tool-connects)
- [Making a change](#making-a-change)
- [Repository layout](#repository-layout)
- [Configuration reference](#configuration-reference)
- [Known limitations](#known-limitations)
- [Going further: what production would add](#going-further-what-production-would-add)
- [Documentation](#documentation)

## What you'll practice

- **Lab as code** — the topology is a YAML file in Git; every deploy is identical.
- **Single source of truth** — `sot/fabric.yml` holds the intent. Ansible renders configuration from it,
  and pyATS derives the expected state (OSPF neighbors, reachability) from the same file.
- **Changes as data** — a change is a small YAML overlay in `sot/changes/`, validated before you keep it.
- **Day-0 vs day-1** — bootstrap enables model-driven interfaces over SSH, then day-1 configures the network.
- **Idempotent configuration** — resource modules for interface state; templates that match running-config.
- **Underlay + overlay routing** — OSPF carries the loopbacks, iBGP (full mesh) carries extra prefixes.
- **Removing what isn't declared** — `prune` deletes loopbacks that exist on a device but not in the SoT.
- **Drift detection** — two complementary methods: SoT vs device (Ansible check mode) and golden config diff.
- **Multiple automation interfaces** — Ansible, Nornir/Netmiko, pyATS/Genie, NETCONF, RESTCONF, gNMI.
- **A real pipeline** — readiness polling, JUnit reports, automatic teardown.

## Tested versions

| Component | Version |
|---|---|
| Host OS | Ubuntu 26.04 LTS |
| containerlab | 0.79.0 |
| Catalyst 8000v (IOS XE) | 17.13.01a — `vrnetlab/cisco_c8000v:17.13.01a` |
| XRv9000 (IOS XR) | 24.3.1 — `vrnetlab/cisco_xrv9k:24.3.1` (built with `INSTALL=true`) |
| Nexus 9000v-lite (NX-OS) | 9500v-lite 10.5.5.M — `vrnetlab/cisco_n9kv:9500-lite-10.5.5.M` |
| Python (venv) | 3.12 via uv |

Other versions will probably work; if your image tags differ, set them in `lab.env` (see below).

## Requirements

| | Minimum |
|---|---|
| vCPU | 8 (12 recommended) |
| RAM | 32 GB — XRv9000 ~16 GB · C8000v ~5 GB · N9Kv-lite 6 GB + host |
| Disk | 80 GB free |
| Virtualization | `/dev/kvm` (bare metal, or nested virtualization enabled) |

Host software (installed by `scripts/00-host-setup.sh`): Docker, QEMU/KVM, containerlab, gnmic, uv, shellcheck.

## Quick start

```bash
git clone https://github.com/Thantoeaungait/Automation_with_containerlab_across_Cisco_ios_xe_xr_nx-os.git
cd Automation_with_containerlab_across_Cisco_ios_xe_xr_nx-os

# 1. Host preparation (once) — then log out and back in
./scripts/00-host-setup.sh

# 2. Build the images (once) — put the Cisco files in ~/cisco-images first, see docs/IMAGES.md
N9KV_VARIANT=lite ./scripts/01-build-images.sh c8000v n9kv xrv9k
docker images | grep -Ei 'c8000v|n9kv|xrv9k'

# 3. Only if your tags differ from "Tested versions": create lab.env
cp lab.env.example lab.env && nano lab.env
make env                       # shows what containerlab will receive

# 4. Python toolchain (Python 3.12 venv + Ansible collections)
make deps

# 5. Run the whole pipeline
make ci
```

The first run takes a while: XRv9000 needs 10–20 minutes to boot. `make wait` polls until all nodes are ready.

**Run stages yourself** (the lab stays up; nothing is destroyed automatically):

```bash
make deploy wait           # start nodes and wait for SSH
make bootstrap configure   # enable APIs, push the configuration
make validate              # check OSPF and reachability
make ssh-xr                # log in to a node (ssh-xe, ssh-nx)
make destroy               # stop the lab
```

To keep the lab when the pipeline fails: `KEEP_LAB=1 ./scripts/ci.sh`.

## Pipeline stages

| `make` target | Tool | What it does |
|---|---|---|
| `deploy` | containerlab | Starts the topology; clears stale SSH host keys for the lab IPs |
| `wait` | Nornir | Polls until each node returns an SSH banner and accepts a login |
| `bootstrap` | Ansible | Day-0: enables NETCONF, RESTCONF, gNMI/gRPC (detects the XR management VRF) |
| `dry-run` | Ansible | Shows what day-1 would change (`--check --diff`) |
| `configure` | Ansible | Day-1: addressing + OSPF rendered from `sot/fabric.yml` |
| `validate` | pyATS/Genie | OSPF FULL neighbors per node + full-mesh pings of OSPF loopbacks → `reports/validation-baseline.xml` |
| `validate-bgp` | pyATS/Genie | iBGP sessions Established per node + reachability of BGP-only prefixes → `reports/validation-bgp.xml` |
| `change` | Ansible | Applies a change set (default `sot/changes/loopback100.yml`) |
| `validate-change` | pyATS/Genie | Re-validates including the change → `reports/validation-change.xml` |
| `prune` | Ansible | Removes loopbacks not declared in the SoT (Loopback0 is protected); `prune-check` previews |
| `drift-check` | Ansible | Check mode: fails if any device differs from what the SoT would render |
| `golden` / `drift` | Nornir | Save running-configs as a baseline / diff them later → `reports/drift-<host>.diff` |
| `audit` | Nornir | Config backups to `backups/` + compliance rules → `reports/audit.json` |
| `apis` | ncclient · requests · gnmic | NETCONF, RESTCONF and gNMI smoke tests |
| `destroy` | containerlab | Tears the lab down |

`make help` lists all targets, including `lint`, `render`, `env`, `inspect` and `graph`.

## How each tool connects

| Tool | Transport | xe1 (IOS XE) | xr1 (IOS XR) | nx1 (NX-OS) |
|---|---|---|---|---|
| Ansible `network_cli` | SSH :22 | ✔ | ✔ | ✔ |
| Nornir + Netmiko | SSH :22 | ✔ | ✔ | ✔ |
| pyATS / Genie | SSH :22 | ✔ | ✔ | ✔ |
| NETCONF (ncclient) | SSH :830 | ✔ | ✔ | ✔ (native-model fallback) |
| RESTCONF (requests) | HTTPS :443 | ✔ | — not implemented on IOS XR | ✔ via NX-API |
| gNMI (gnmic) | gRPC :57400 | — see limitations | — see limitations | ✔ TLS, self-signed |

Default credentials (containerlab defaults): xe1 / nx1 `admin` / `admin`, xr1 `clab` / `clab@123`.

## Removing configuration and detecting drift

Ansible's default behaviour only **adds** configuration. If you delete a loopback from the SoT, it
stays on the device. This lab handles that in two ways:

```bash
make change            # add Loopback100 everywhere
make prune-check       # preview: "remove ['loopback100']"
make prune             # delete loopbacks that are not in the SoT (Loopback0 is always protected)
make prune KEEP_CHANGE=1   # keep the change set's loopbacks
```

Drift is detected with two complementary methods:

| Method | Compares | Catches | Misses |
|---|---|---|---|
| `make drift-check` | SoT ↔ device (Ansible check mode) | Changes to lines the automation manages | Config the automation doesn't manage |
| `make golden` + `make drift` | Saved config ↔ current config | **Any** change, e.g. a manual `ip ospf cost` | Why it changed |

Try it: `make golden`, add `ip ospf cost 50` on xe1 by hand, then run both checks. Only the golden
diff sees it, because the templates don't manage OSPF cost. Remediate with `make configure prune`
(and remove unmanaged lines by hand, or bring them into the SoT).

## Making a change

```yaml
# sot/changes/my-change.yml
changes:
  xr1:
    loopbacks:
      - { name: Loopback200, ipv4: 200.0.0.2/32 }
```

```bash
make render CHANGE=sot/changes/my-change.yml           # preview the generated config (no lab needed)
make change CHANGE=sot/changes/my-change.yml
make validate-change CHANGE=sot/changes/my-change.yml  # now also expects 200.0.0.2 to be reachable
```

To change the permanent design (links, addressing, nodes), edit `sot/fabric.yml`; validation adapts automatically.

## Repository layout

```
.
├── topology/            lab.clab.yml · configs/xr1.cfg (startup snippet) · *.annotations.json (diagram layout)
├── sot/                 fabric.yml (intent) · changes/*.yml (change sets)
├── ansible/             inventory · playbooks (bootstrap, configure, prune) · templates (bootstrap, day1)
├── nr/                  Nornir: wait_ready.py · backup_and_audit.py · drift.py · inventory
├── validation/          pyATS testbed.yaml · validate.py · validate_bgp.py (intent-derived checks, JUnit)
├── api/                 netconf_get.py · restconf_get.py · gnmi_check.sh
├── scripts/             00-host-setup.sh · 01-build-images.sh · ci.sh · render_templates.py
├── docs/                IMAGES.md · ARCHITECTURE.md · TROUBLESHOOTING.md
├── .github/             lint workflow · issue and pull request templates
├── lab.env.example      optional local overrides (copy to lab.env)
└── Makefile             entry point for every stage
```

## Configuration reference

All optional. Set them in `lab.env` or on the command line (`make ci GNMI_SKIP=none`).

| Variable | Default | Purpose |
|---|---|---|
| `C8KV_IMAGE`, `XRV9K_IMAGE`, `N9KV_IMAGE` | tested versions above | Local image tags |
| `N9KV_MEMORY`, `N9KV_SMP` | `6144`, `2` | N9Kv sizing (full image: `10240`, `4`) |
| `GNMI_SKIP` | `xe1 xr1` | Nodes excluded from the gNMI test; `none` tests all |
| `TOPO` | `topology/lab.clab.yml` | Topology file |
| `CHANGE` | `sot/changes/loopback100.yml` | Change set for `change` / `validate-change` |
| `KEEP_LAB` | `0` | `1` keeps the lab after `ci.sh` |
| `KEEP_CHANGE` | unset | `1` makes `prune` / `prune-check` keep the loopbacks of `$(CHANGE)` |
| `WAIT_TIMEOUT` | `1800` | Seconds `make wait` polls |

## Known limitations

- **gNMI on xe1:** this C8000v image (unlicensed) has no `gnxi` / `gnmi-yang` CLI. Bootstrap tries both and continues.
- **gNMI on xr1:** vrnetlab puts the XRv9000 management interface in VRF `clab-mgmt`; in testing, the
  gRPC server was not reachable there. NETCONF works (bootstrap enables it in the management VRF).
  Details and what was tried: [TROUBLESHOOTING](docs/TROUBLESHOOTING.md#xrv9000-gnmi-and-the-management-vrf).
- **RESTCONF on xr1:** IOS XR does not implement RESTCONF.
- **One lab per host:** fixed management subnet `172.30.30.0/24` and node names.
- **Validation timing:** right after configuration, OSPF and BGP may still be converging; validation
  retries, and a rerun normally passes.
- **Prune scope:** `prune` only manages loopbacks. Other unmanaged config (interfaces, OSPF settings) is
  reported by `make drift`, not removed.

## Going further: what production would add

This lab keeps things simple on purpose. A production setup would typically add:

- **Secrets management** — Ansible Vault or a secrets manager instead of plaintext lab credentials.
- **Verified SSH host keys** and **TLS with real certificates** for NETCONF, RESTCONF and gNMI.
- **Full desired state for everything** — `prune` covers loopbacks; production would extend this to all
  managed resources (`state: replaced` / `overridden`), with guardrails for management interfaces.
- **Scheduled drift alerts** — `make drift` from cron or a pipeline, with notifications instead of a log file.
- **Change approval** — pull request reviews and a pipeline gate before anything reaches real devices.

## Documentation

- [docs/IMAGES.md](docs/IMAGES.md) — obtaining and building images, file naming rules
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — design decisions and trade-offs
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — every failure hit while building this lab, with fixes
- [CONTRIBUTING.md](CONTRIBUTING.md) · [SECURITY.md](SECURITY.md) · [CHANGELOG.md](CHANGELOG.md)

## License

[MIT](LICENSE) © 2026 Than Toe Aung. Cisco and related product names are trademarks of Cisco Systems, Inc.;
this project is not affiliated with Cisco. See [NOTICE](NOTICE).
