# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

## [1.0.0] - 2026-10-02

### Added
- Topologies: C8000v + XRd + N9Kv (`lab.clab.yml`) and C8000v + XRv9000 + N9Kv (`lab-xrv9k.clab.yml`).
- Source of truth (`sot/fabric.yml`) with change-set overlays (`sot/changes/`).
- Ansible day-0 bootstrap (NETCONF/RESTCONF/gNMI) and idempotent day-1 configuration.
- Nornir readiness polling, config backup and compliance audit.
- pyATS intent-based validation with JUnit output.
- NETCONF, RESTCONF and gNMI smoke tests.
- `scripts/ci.sh` full lifecycle pipeline; GitLab CI with lint (shared runners) and lab (self-hosted) jobs.
- `lab.env` for image tags and N9Kv sizing; N9Kv-lite support.
- Documentation: README, IMAGES, ARCHITECTURE, TROUBLESHOOTING, CONTRIBUTING, SECURITY.

### Fixed (found during first deployments on Ubuntu 26.04)
- vrnetlab file naming for N9Kv and XRv9000 handled automatically by the build script.
- containerlab env vars lost under sudo-rs (`sudo -E` unsupported): Makefile uses `sudo env` or `clab_admins`.
- SSH host-key mismatch after redeploy: keys no longer recorded; stale keys cleared on deploy.
- IOS XR SSH session rate limit breaking readiness polling: raised via startup-config and bootstrap.
- IOS XE images without gNMI CLI no longer fail bootstrap.
- Paramiko/Nornir traceback noise suppressed; readiness output shows per-node reasons.
