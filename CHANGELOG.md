# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

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
