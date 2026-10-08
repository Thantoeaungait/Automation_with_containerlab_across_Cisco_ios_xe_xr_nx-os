# Approach to production

This lab started as a way to learn Cisco automation (v1.x). Version 2.0 rebuilds it around the
practices a production network automation setup depends on, and rehearses them end to end on
three virtual routers. It is still a lab: the goal is to practise the production workflow on
something you can break and redeploy, then know exactly what is missing before the same code
touches real devices.

| Document | Content |
|---|---|
| This page | Principles, what is covered, evidence, gaps before real devices |
| [PRODUCTION-PHASE1.md](PRODUCTION-PHASE1.md) | Vault, single source of truth, TACACS+, TLS, pre/post checks (how-to) |
| [PRODUCTION-PHASE2.md](PRODUCTION-PHASE2.md) | Rollback, failure tests, telemetry, Batfish, NetBox, self-hosted CI (how-to) |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Every failure hit on the way, with cause and fix |

---

## Principles

1. **Intent in one place.** `sot/fabric.yml` describes devices, links, routing and services. The
   topology, every tool's inventory and the expected state for validation are derived from it.
   Nothing else holds a device list.
2. **No secrets in Git.** Credentials, the TACACS+ key and certificate passwords live in an
   ansible-vault file encrypted with a random key that never enters the repository.
3. **Every change is proven, not assumed.** A change is validated against intent after it is
   applied; a failed validation rolls the devices back automatically.
4. **Humans authenticate centrally, automation keeps working.** Logins go through TACACS+ with
   accounting; local fallback and a local-only console prevent lock-out.
5. **Failure is tested on purpose.** The pipeline breaks a link and measures reroute and recovery.
6. **Every run leaves evidence.** JUnit reports, config backups, an audit report and a run manifest
   (commit, image IDs, per-stage results and durations) identify exactly what ran.

## Coverage

| Production practice | In this lab | Command | Status |
|---|---|---|---|
| Secrets management | ansible-vault, random 32-byte key outside the repo | `make vault-init` | Done |
| Single source of truth | `sot/fabric.yml`, generated topology and inventories | `make topology` | Done |
| Central AAA + accounting | tac_plus container, local fallback, local console | `make tacacs tacacs-test` | Done (IOS XE, NX-OS; IOS XR opt-in) |
| TLS with verified certificates | Lab CA + device certificates | `make pki` | Partial: manual install, verification opt-in |
| Idempotent configuration | Templates match running-config; resource modules | `make configure` | Done |
| Pre-deployment analysis | Batfish on the rendered intent | `make batfish` | Optional |
| Validation against intent | pyATS checks derived from the SoT, JUnit output | `make validate validate-bgp` | Done |
| State diff around a change | genie learn / diff | `make pre-check post-check state-diff` | Done |
| Checkpoint and rollback | Per-platform checkpoint, automatic rollback | `make safe-change` | Done |
| Removing undeclared config | Guarded prune (loopbacks only) | `make prune` | Partial |
| Drift detection | SoT vs device, and golden config diff | `make drift-check`, `make drift` | Done |
| Compliance audit + backups | Nornir rules, backups per run | `make audit` | Done |
| Failure testing | netem link failure, reroute and recovery timing | `make failover-test` | Done |
| Streaming telemetry | gnmic → Prometheus → Grafana | `services.telemetry.enabled` | Optional (NX-OS) |
| External inventory (NetBox) | Idempotent sync from the SoT | `make netbox-sync` | Optional (one-way) |
| Pipeline with approval gate | Self-hosted GitHub runner, manual trigger, required reviewer | `.github/workflows/lab.yml` | Done |
| Run traceability | `reports/run-manifest.json` | written by `scripts/ci.sh` | Done |

## Evidence: the full pipeline

```bash
TACACS=1 FAILOVER=1 make ci
```

Deploys a fresh lab, runs every stage below, writes the reports and destroys the lab.
Reference run for v2.0.0 (12 vCPU, 30 GiB host):

| Stage | Duration |
|---|---|
| deploy · wait for nodes · bootstrap (day-0) | 1 s · 322 s · 28 s |
| AAA via TACACS+ · TACACS+ login | 13 s · 11 s |
| configure (day-1) · validate baseline · validate BGP | 33 s · 89 s · 38 s |
| apply change · validate change · prune change · back to baseline | 15 s · 39 s · 14 s · 38 s |
| drift (SoT) · backup + audit · model-driven APIs | 9 s · 2 s · 3 s |
| failure test (OSPF dead interval ≈ 43 s, reroute < 1 s after detection) | 68 s |

All 16 stages passed. Without `TACACS=1` and `FAILOVER=1` the pipeline skips those stages, so it
also runs on a host without the extra time budget.

## Gaps before real devices

The workflow is the production one; these lab shortcuts are not. Close them before pointing any
of this at a real network:

| Gap | Lab today | Production needs |
|---|---|---|
| SSH host keys | Not verified (new keys on every deploy) | Known hosts managed and verified |
| Device certificates | Lab CA, manual install, verification off by default | Enterprise PKI, automated enrolment and renewal, verification always on |
| Vault key | File in the user's home directory | Secrets manager or CI secret store, rotation, access audit |
| Automation accounts | Shared platform accounts, privilege 15 | Per-system service accounts, least privilege via TACACS+ command authorization |
| TACACS+ | One server, permit-all group | Redundant servers, per-role command authorization, IOS XR task groups |
| Desired state | Additive config; prune covers loopbacks only | Full config replace or `state: overridden` with guardrails for management |
| Source of truth | YAML in Git; NetBox gets a copy | One authoritative SoT (often NetBox) with change review |
| Rollout | All devices at once | Canary device, batches, maintenance windows, stop-on-failure |
| Detection | OSPF dead interval (~40 s) | BFD, syslog collection, alerting on telemetry |
| Capacity | One host, VMs sized down (XRv9000 10 GB), swap as safety net | Capacity planning per node, resource limits and monitoring on the automation hosts |
| Pipeline | Manual trigger on one lab host | Pre-merge lab tests on every change, promotion to production with approval |

## Lessons from building it

- **Vendor parsers can rewrite what you send.** IOS XE reads `group TAC` as the keyword
  `tacacs+`, which silently dropped the management VRF. A server group name must not be a prefix
  of a CLI keyword; the test that logs in with a TACACS-only account is what caught it.
- **Test with an account that only exists centrally.** A login that succeeds through local
  fallback proves nothing about AAA.
- **Keep the evidence where the failure is.** The TACACS+ test prints the server's access log (failed
  logins with source IP) and the device's AAA state on failure, so a red run explains itself.
- **Update packs can undo fixes.** Applying a release on top of a branch that does not contain the
  latest fixes reverts them. Branch releases from the latest released branch, and let the pipeline
  decide.
