# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Documentation
- README: community-tested section restored and updated with the full-pipeline reproduction by
  Jeleel Muibi (commit `a4cda79`: C8000v 17.16.01a, XRv9000 24.3.1, N9Kv 9500 10.4.2.F; Discussion #7).

## [2.0.0] - 2026-10-07

Production release: the lab is rebuilt around production automation practices (vault, single
source of truth, central AAA, rollback, failure testing, approval-gated pipeline). Overview:
`docs/PRODUCTION.md`. Reference run: `TACACS=1 FAILOVER=1 make ci`, all 16 stages passed.

### Added
- `docs/PRODUCTION.md`: approach to production — principles, coverage per practice, reference
  pipeline run, gaps to close before real devices.
- Encrypted secrets: `make vault-init` creates the vault password (`openssl rand -base64 32`, outside
  the repo) and `secrets/vault.yml` with all device credentials, the TACACS+ key and the PKCS#12 password.
- Single source of truth: `sot/fabric.yml` now holds platforms, management IPs and services.
  `lab/sot.py` loads it (with the vault) for Nornir, pyATS and the API scripts; Ansible uses the
  dynamic inventory `ansible/inventory/sot.py`; `make topology` generates `topology/lab.clab.yml`.
- TACACS+ server container in the lab, `make tacacs` (AAA with local fallback and local-only console)
  and `make tacacs-test`.
- Lab PKI: `make pki` creates a CA and device certificates; clients verify against the CA once
  `pki.verify_with_lab_ca` is true.
- Pre/post state snapshots: `make pre-check`, `make post-check`, `make state-diff` (genie learn/diff).
- `docs/PRODUCTION-PHASE1.md`.
- `make tacacs-test` prints the server's access log (failed logins with source IP) and, for a device
  that fails, its AAA config, `show tacacs` and a ping to the server in the management VRF (keys masked).
- `reports/run-manifest.json` written by `scripts/ci.sh` on exit: repository commit (and dirty flag),
  topology/SoT checksums, containerlab and image identities, host facts, per-stage result and
  duration, report checksums. Identifies a run for comparison with a rerun on another host.
- C8000v sizing via `C8KV_MEMORY` / `C8KV_SMP` (lab.env); C8000v 17.16 under nested virtualization
  needs 8192 MB / 2 vCPU (reported by Jeleel Muibi).
- `make tacacs-check`: validates the rendered TACACS+ config by starting the image briefly.
- Phase 2 (`docs/PRODUCTION-PHASE2.md`):
  - `make checkpoint`, `make rollback`, `make safe-change` (automatic rollback on failure), with a
    deliberately broken change set `sot/changes/bad-overlap.yml`
  - `make failover-test`: netem link failure with reroute and recovery timing (`FAILOVER=1` in ci.sh)
  - optional telemetry stack (gnmic, Prometheus, Grafana) generated from `services.telemetry`
  - `make batfish`: offline analysis of the rendered intent (parse, OSPF/BGP sessions, reachability)
  - `make netbox-sync`: idempotent push of the SoT into NetBox
  - `.github/workflows/lab.yml`: manual pipeline run on a self-hosted runner with an approval gate
  - `requirements-optional.txt` (`make deps-optional`)

### Changed (breaking)
- Credentials are no longer in inventories; run `make vault-init` once before deploying.
- Removed `ansible/inventory/hosts.yml`, per-platform group_vars, `nr/inventory/`, `validation/testbed.yaml`.
- `topology/lab.clab.yml` is generated; edit `sot/fabric.yml` and run `make topology`.
- The post-prune validation writes `reports/validation-after-prune.xml` instead of overwriting the
  baseline report.

### Fixed
- TACACS+ config is rendered in Marc Huber's tac_plus syntax used by `lfkeitel/tacacs_plus`
  (the container exited on the classic Shrubbery format).
- TACACS+ login failed on IOS XE only: the server group `TAC` was read as the keyword `tacacs+`
  (abbreviation), which uses the global server list without the management VRF. The group is now
  `MGMT-TACACS` on all platforms.
- `api/restconf_get.py` stopped the pipeline when NX-OS answered HTTP 200 with YANG XML instead of the
  requested JSON. Responses are now printed as JSON or XML based on the content type.
- `scripts/01-build-images.sh` printed a parsing warning in the XRv9000 image-size check (nested
  `virtual-size` entries in `qemu-img` JSON). The size is now read with a JSON parser.

  (These two found by Jeleel Muibi while reproducing the lab on a fresh Proxmox host.)

### Documentation
- README reframed as a production-style workflow on a lab: production approach, pipeline stages in
  order (TACACS+ and failover opt-in), vault-based credentials, new layout and variables, gaps before
  real devices.
- PRODUCTION-PHASE1/2 linked from the overview; TACACS+ server-group naming and test diagnostics.
- TROUBLESHOOTING: IOS XE `group TAC` → `tacacs+`, opt-in TACACS+ stages, update packs reverting fixes.
- SECURITY, ARCHITECTURE and CONTRIBUTING updated for the vault, SoT and AAA.

## [1.2.0] - 2026-10-04

### Added
- **iBGP** (AS 65000) full mesh between Loopback0 addresses, rendered from `bgp:` in the SoT. Neighbors are
  computed from the device list, so a new device gets peers automatically. `Loopback200` (10.255.x.x) is
  marked `ospf: false` and reachable only through BGP.
- `validation/validate_bgp.py` / `make validate-bgp`: Established sessions per device and reachability of
  BGP-advertised prefixes, with JUnit output.
- `ansible/playbooks/prune.yml` / `make prune`, `make prune-check`: removes loopbacks that exist on a device
  but not in the SoT. Loopback0 is protected; `KEEP_CHANGE=1` keeps a change set's loopbacks.
- Drift detection: `make drift-check` (Ansible check mode, SoT vs device) and `make golden` / `make drift`
  (`nr/drift.py`, running-config vs saved baseline, ignoring timestamp lines).
- Pipeline stages: validate BGP, prune the change, validate back to baseline, SoT drift check.
- Audit rules for the BGP process on all platforms.
- Topology diagram in the README (`docs/topologyimages/topology.png`, outside the git-ignored `images/`
  folders), drawn in the containerlab VS Code extension. `topology/lab.clab.yml.annotations.json` stores
  the layout: title, per-node info boxes (platform, Lo0, Lo200, mgmt), subnet and `.1`/`.2` labels.

### Changed
- Templates support `ospf: false` loopbacks; `scripts/render_templates.py` passes `devices` and `bgp`.
- `save_when: changed` instead of `modified` in all playbooks. IOS XE always shows small differences
  between running and startup config, so `modified` saved (and reported `changed`) on every run.
- Topology links use the devices' own interface names (`Gi2`, `Gi0/0/0/0`, `Ethernet1/1`) instead of
  `eth1`/`eth2`, so the topology file, the SoT and `show` output match.
- `validate_bgp.py` waits up to 3 minutes for BGP prefixes (IOS XR advertisement delay).

### Fixed
- IOS XE reported `changed=1` on every `make configure`, which also made drift checks unreliable.
- Baseline validation (`make validate`) failed intermittently on BGP-only loopbacks (e.g.
  `xe1 -> xr1:10.255.2.2`), because IOS XR can delay BGP advertisements after its BGP process starts.
  Baseline validation now pings only loopbacks that are in OSPF (`ospf: false` ones are skipped);
  BGP-advertised prefixes are checked by `make validate-bgp`, which waits for them.
- `validate.py` reports 0 OSPF neighbors instead of crashing when OSPF isn't configured yet
  (e.g. running `make validate` before `bootstrap`/`configure`).

### Documentation
- README: BGP in the topology, prune and drift sections, new targets and `KEEP_CHANGE`.
- TROUBLESHOOTING: idempotency on IOS XE, system vs venv Ansible (`paramiko` missing), BGP checks,
  drift false positives, yamllint warnings vs errors.
- README: topology diagram and section on how it is maintained; interface naming note.
- TROUBLESHOOTING: topology and diagram issues (interface names, SVG export without text, image paths).

## [1.1.0] - 2026-10-03

### Changed
- Single topology `topology/lab.clab.yml`: Catalyst 8000v 17.13.01a + XRv9000 24.3.1 + Nexus 9000v-lite
  (9500v) 10.5.5.M. Image defaults now match the tested versions; `lab.env` is only needed for overrides.
- N9Kv defaults sized for the lite image (6 GB RAM, 2 vCPU).
- XR bootstrap detects the management VRF and enables NETCONF (and the VRF address family) there.
- Audit rules split into required and optional; a missing optional rule (gNMI on C8000v) warns
  without failing the pipeline.
- gNMI test skips `xe1 xr1` by default (`GNMI_SKIP=none` tests all).
- Moved to GitHub: GitHub Actions lint workflow, issue and pull request templates. GitLab CI removed.
- `.yamllint` ignores downloaded Ansible collections; `00-host-setup.sh` installs shellcheck.

### Removed
- Second topology file (`lab-xrv9k.clab.yml`) and XRd image variable from the Makefile.

### Fixed
- XRv9000 NETCONF on port 830 (was listening in the wrong VRF).
- Validation retries pings longer while OSPF converges.

### Documentation
- README rewritten: tested versions, learning-project note, known limitations, production considerations.
- TROUBLESHOOTING extended: XRv9000 management VRF and gNMI investigation, deploy/lint/Git issues.

## [1.0.0] - 2026-10-02

### Added
- containerlab topology for IOS XE, IOS XR and NX-OS; source of truth with change-set overlays.
- Ansible day-0 bootstrap and idempotent day-1 configuration.
- Nornir readiness polling, backups and compliance audit; pyATS validation with JUnit output.
- NETCONF, RESTCONF and gNMI smoke tests; `scripts/ci.sh` lifecycle pipeline.
- Fixes for vrnetlab file naming, sudo-rs, SSH host keys and the IOS XR SSH rate limit.
