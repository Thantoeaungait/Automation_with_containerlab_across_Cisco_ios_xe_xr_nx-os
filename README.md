# clab-multivendor-automation

**Cross-platform network automation lab: Cisco IOS XE, IOS XR and NX-OS on [containerlab](https://containerlab.dev).**

One YAML file runs a Catalyst 8000v, an XRd or XRv9000, and a Nexus 9000v side by side. Every node gets a
fixed management IP, so Ansible, Nornir, pyATS, NETCONF, RESTCONF and gNMI connect straight from the host.
The full lifecycle — **deploy → change → validate → destroy** — is one command, locally or in GitLab CI.

```
                 xe1  Catalyst 8000v (IOS XE)    172.30.30.11
             Gi2 /                       \ Gi3
        10.0.12.0/30                  10.0.13.0/30
      Gi0/0/0/0 /                           \ Eth1/2
   xr1  XRd / XRv9k (IOS XR) — 10.0.23.0/30 — nx1  Nexus 9000v (NX-OS)
   172.30.30.12      Gi0/0/0/1          Eth1/1     172.30.30.13

   OSPF area 0 (point-to-point) · Loopback0 1.1.1.1 / 2.2.2.2 / 3.3.3.3
```

> **Images are not included.** Cisco virtual images are licensed software. You must obtain them yourself
> (see [docs/IMAGES.md](docs/IMAGES.md)). This repository never contains or distributes them.

---

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Pipeline stages](#pipeline-stages)
- [How each tool connects](#how-each-tool-connects)
- [Making a change](#making-a-change)
- [Repository layout](#repository-layout)
- [CI/CD on GitLab](#cicd-on-gitlab)
- [Configuration reference](#configuration-reference)
- [Known limitations](#known-limitations)
- [Documentation](#documentation)
- [Contributing, security, license](#contributing-security-license)

## Features

- **Three NOSes, one topology** — C8000v + XRd (or XRv9000) + N9Kv / N9Kv-lite, selectable per run.
- **Single source of truth** — `sot/fabric.yml` drives configuration *and* validation. Expected OSPF
  adjacencies and reachability are computed from it, never hard-coded.
- **Changes as data** — a change is a small YAML overlay (`sot/changes/*.yml`), so CI validates exactly what an MR introduces.
- **Idempotent day-1** — resource modules for interface state, templates that match running-config rendering.
- **Six automation interfaces** — Ansible, Nornir/Netmiko, pyATS/Genie, NETCONF, RESTCONF, gNMI.
- **CI-ready** — readiness polling instead of sleeps, JUnit reports, artifacts, automatic teardown.

## Requirements

| | XRd topology (recommended) | XRv9000 topology |
|---|---|---|
| Host OS | Ubuntu 26.04 LTS (24.04 also works) | same |
| vCPU | 8 | 12 |
| RAM | 24 GB with N9Kv-lite · 32 GB with full N9Kv | 32 GB with N9Kv-lite · 48 GB with full N9Kv |
| Disk | 60 GB free | 80 GB free |
| Virtualization | `/dev/kvm` (bare metal or nested virt) | same |

Approximate per-node memory: C8000v ~5 GB · N9Kv 10 GB (lite 6 GB) · XRd ~2 GB · XRv9000 ~16 GB.

Software installed by `scripts/00-host-setup.sh`: Docker, QEMU/KVM, containerlab, gnmic, uv.

## Quick start

```bash
git clone https://github.com/Thantoeaungait/Automation_across_ios_xe_xr_nx-os.git
cd clab-multivendor-automation

# 1. Host preparation (once) — then log out and back in
./scripts/00-host-setup.sh

# 2. Images (once) — put Cisco files in ~/cisco-images first, see docs/IMAGES.md
./scripts/01-build-images.sh                     # or e.g.: N9KV_VARIANT=lite ./scripts/01-build-images.sh n9kv xrd

# 3. Tell the lab which image tags you have
cp lab.env.example lab.env && $EDITOR lab.env    # match `docker images`
make env                                         # verify what containerlab will receive

# 4. Python toolchain (Python 3.12 venv via uv + Ansible collections)
make deps

# 5. Run everything
make ci                                          # XRd topology
make ci TOPO=topology/lab-xrv9k.clab.yml         # XRv9000 topology
```

While iterating, keep the lab up and rerun only the stage you're working on:

```bash
KEEP_LAB=1 ./scripts/ci.sh        # full run, lab survives failures
make configure validate           # iterate without redeploying
make destroy                      # when done
```

## Pipeline stages

| `make` target | Tool | What it does |
|---|---|---|
| `deploy` | containerlab | Starts the topology; clears stale SSH host keys for the lab IPs |
| `wait` | Nornir | Polls until every node returns an SSH banner *and* accepts a login (vrnetlab VMs take 5–20 min) |
| `bootstrap` | Ansible | Day-0: enables NETCONF, RESTCONF, gNMI/gRPC; raises the IOS XR SSH rate limit |
| `dry-run` | Ansible | `--check --diff` of day-1 |
| `configure` | Ansible | Day-1: addressing + OSPF rendered from `sot/fabric.yml` |
| `validate` | pyATS/Genie | OSPF FULL count per node + full-mesh loopback pings → `reports/validation-baseline.xml` |
| `change` | Ansible | Applies `$(CHANGE)` (default `sot/changes/loopback100.yml`) |
| `validate-change` | pyATS/Genie | Re-validates including the change set → `reports/validation-change.xml` |
| `audit` | Nornir | Running-config backups to `backups/` + regex compliance → `reports/audit.json` |
| `apis` | ncclient / requests / gnmic | NETCONF, RESTCONF, gNMI smoke tests |
| `destroy` | containerlab | Tears down and removes the lab directory |

`make help` lists every target, including `lint`, `render`, `inspect`, `graph`, `ssh-xe`, `ssh-xr`, `ssh-nx`.

## How each tool connects

| Tool | Transport | xe1 (IOS XE) | xr1 (IOS XR) | nx1 (NX-OS) |
|---|---|---|---|---|
| Ansible `network_cli` | SSH :22 | ✔ | ✔ | ✔ |
| Nornir + Netmiko | SSH :22 | ✔ | ✔ | ✔ |
| pyATS / Genie | SSH :22 | ✔ | ✔ | ✔ |
| NETCONF (ncclient) | SSH :830 | ✔ | ✔ | ✔ (native-model fallback) |
| RESTCONF (requests) | HTTPS :443 | ✔ | ✘ not implemented on IOS XR | ✔ via NX-API |
| gNMI (gnmic) | gRPC :57400 | depends on image license¹ | plaintext | TLS, self-signed |

¹ Unlicensed C8000v images often hide the `gnxi`/`gnmi-yang` CLI. Bootstrap tries both and continues;
the gNMI test skips xe1 by default (`GNMI_SKIP=` to include it).

Default credentials (containerlab kind defaults): xe1 / nx1 `admin` / `admin`, xr1 `clab` / `clab@123`.

## Making a change

```yaml
# sot/changes/my-change.yml
changes:
  xr1:
    loopbacks:
      - { name: Loopback200, ipv4: 200.0.0.2/32 }
```

```bash
make render CHANGE=sot/changes/my-change.yml           # see the generated config, no lab needed
make change CHANGE=sot/changes/my-change.yml
make validate-change CHANGE=sot/changes/my-change.yml  # now also expects 200.0.0.2 to be reachable
```

To change the permanent design (links, addressing, new nodes), edit `sot/fabric.yml`; validation adapts automatically.

## Repository layout

```
.
├── topology/            lab.clab.yml (XRd) · lab-xrv9k.clab.yml · configs/ (startup snippets)
├── sot/                 fabric.yml (intent) · changes/*.yml (change sets)
├── ansible/             inventory · playbooks (bootstrap, configure) · templates (bootstrap, day1)
├── nr/                  Nornir: wait_ready.py · backup_and_audit.py · inventory
├── validation/          pyATS testbed.yaml · validate.py (intent-derived checks, JUnit)
├── api/                 netconf_get.py · restconf_get.py · gnmi_check.sh
├── scripts/             00-host-setup.sh · 01-build-images.sh · ci.sh · render_templates.py
├── docs/                IMAGES.md · ARCHITECTURE.md · TROUBLESHOOTING.md
├── lab.env.example      image tags / N9Kv sizing (copy to lab.env)
├── Makefile             entry point for every stage
└── .gitlab-ci.yml       lint (shared runners) + lab (self-hosted runner)
```

## CI/CD on GitLab

The pipeline has two jobs:

- **`lint`** runs on GitLab's shared runners for every merge request: yamllint, shellcheck, Python
  compile, Ansible syntax check, offline template rendering. No images or KVM required.
- **`lab`** runs the full lab on **your own** runner. It only runs when the project CI/CD variable
  `LAB_RUNNER_AVAILABLE=true` is set, so forks without a lab host stay green.

Runner requirements for `lab`: Ubuntu host with `/dev/kvm`, shell executor, tags `kvm` and `clab`,
images pre-built, `lab.env` present in the runner's environment (or variables set in CI/CD settings),
and the runner user in the `docker`, `kvm` and `clab_admins` groups. Reports are kept as job artifacts
and JUnit results appear in the merge request.

## Configuration reference

| Variable | Where | Default | Purpose |
|---|---|---|---|
| `TOPO` | make / ci.sh | `topology/lab.clab.yml` | Topology to run |
| `CHANGE` | make | `sot/changes/loopback100.yml` | Change set for `change` / `validate-change` |
| `KEEP_LAB` | ci.sh | `0` | `1` keeps the lab after the pipeline |
| `C8KV_IMAGE`, `N9KV_IMAGE`, `XRD_IMAGE`, `XRV9K_IMAGE` | lab.env / env | see topology files | Local image tags |
| `N9KV_MEMORY`, `N9KV_SMP` | lab.env / env | `10240`, `4` | N9Kv sizing (lite: `6144`, `2`) |
| `WAIT_TIMEOUT` | make | `1800` | Seconds `make wait` will poll |
| `GNMI_SKIP` | env | `xe1` | Nodes excluded from the gNMI test |
| `N9KV_VARIANT`, `XRV9K_VERSION`, `XRV9K_INSTALL`, `C8KV_CONTROLLER` | build script | — | See `scripts/01-build-images.sh` header |

## Known limitations

- IOS XR has no RESTCONF; use NETCONF or gNMI.
- gNMI on C8000v depends on the image's license level; vrnetlab images boot unlicensed.
- NX-OS gNMI uses an auto-generated self-signed certificate (short-lived); install your own for long-running labs.
- Fixed management subnet `172.30.30.0/24` and node names: one lab per host.
- Host-key checking is disabled for lab IPs because every deploy generates new keys. **Do not reuse these
  connection settings in production.**
- Lab credentials are plaintext defaults. Use Ansible Vault / a secrets manager anywhere real.

## Documentation

- [docs/IMAGES.md](docs/IMAGES.md) — obtaining and building images, file naming rules
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — design decisions and trade-offs
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — every failure we've hit and its fix

## Contributing, security, license

- Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).
- Security issues — see [SECURITY.md](SECURITY.md).
- Released under the [MIT License](LICENSE). See [NOTICE](NOTICE) for trademark and third-party information.
