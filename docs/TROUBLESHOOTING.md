# Troubleshooting

Every problem hit while building and running this lab, grouped by stage, with its cause and fix.
Search this page for the exact error text you see.

**General tips**

- Run `make` from the repository root. Otherwise: `No rule to make target 'ci'`.
- Debug with the lab kept up: `KEEP_LAB=1 ./scripts/ci.sh`, then rerun single stages (`make validate`, ...).
- Check host resources first: `free -g`, `docker stats --no-stream`. Swapping causes timeouts everywhere.
- Serial console of any node (bypasses SSH): `telnet 172.30.30.1X 5000` — exit with `Ctrl+]`, then `quit`.
- Boot progress: `docker logs -f clab-mvauto-<node>`.

---

## Host setup

| Symptom | Cause | Fix |
|---|---|---|
| `kvm-ok` fails | No hardware virtualization | Enable VT-x/AMD-V in BIOS, or nested virtualization on the hypervisor |
| Terminal closes after pasting a snippet | The snippet contained `exit` and was meant for a script | Put script snippets in the file, not the terminal |
| `shellcheck: command not found` in `make lint` | shellcheck not installed | `sudo apt-get install -y shellcheck` (included in `00-host-setup.sh`) |

## Image build (`scripts/01-build-images.sh`)

| Symptom | Cause | Fix |
|---|---|---|
| `ERROR: Incorrect version string (nexus9500v64-lite...qcow2)` | vrnetlab n9kv expects `n9kv-<version>.qcow2` | Use the build script (renames automatically) or rename by hand — see [IMAGES.md](IMAGES.md) |
| `ERROR: Incorrect version string (virtioa.qcow2)` | EVE-NG style file name without a version | Rename to `xrv9k-fullk9-x-<X.Y.Z>.qcow2`, or pass `XRV9K_VERSION=` |
| A second C8000v image `controller-...` appears | vrnetlab builds autonomous + controller mode by default | The script builds autonomous only; `C8KV_CONTROLLER=1` for both |
| `./scripts/01-build-images.sh: No such file or directory` | Wrong working directory | `cd` to the repository root |

## Fresh clone

| Symptom | Cause | Fix |
|---|---|---|
| `.venv/bin/python: No such file or directory` | `.venv` is gitignored, so it isn't in a fresh clone | `make deps` (`ci.sh` runs it automatically) |
| Image tags revert to defaults in a new folder | `lab.env` is gitignored | Copy your `lab.env` over, or recreate it from `lab.env.example` |

## Deploy

| Symptom | Cause | Fix |
|---|---|---|
| `pull access denied for vrnetlab/cisco_...` | The requested tag doesn't exist locally, so Docker tries Docker Hub | Compare the tag in the error with `docker images`; set the right tag in `lab.env`; check with `make env` |
| Same error after running `containerlab deploy` directly | Running containerlab directly skips `lab.env` | Use `make deploy`, or load it first: `set -a; eval "$(sed 's/ *?= */=/' lab.env)"; set +a` |
| `sudo: preserving the entire environment is not supported, '-E' is ignored` | Ubuntu 26.04 uses sudo-rs | The Makefile uses `sudo env ...`; best: `sudo usermod -aG clab_admins $USER` and log in again |
| `ERRO container "clab-mvauto-xe1" exited; container output: ...` during deploy | `--reconfigure` destroys the previous lab; that old container had already stopped | Harmless if the new deploy continues. If nodes keep exiting: `docker ps -a` (`Exited (137)` = killed) and `sudo dmesg \| grep -i oom` — usually not enough RAM |

## Wait (`make wait`)

| Symptom | Cause | Fix |
|---|---|---|
| `booting (no SSH banner)` for several minutes | VMs still booting | Normal; XRv9000 takes 10–20 min |
| `sshd up, login not ready: ['xr1(NetmikoAuthenticationException)']` | XRv9000 starts sshd before the `clab` user exists | Normal while booting |
| xr1 never becomes ready; XR log shows `Incoming SSH session rate limit exceeded` | IOS XR rate-limits SSH sessions from one source | Fixed by `topology/configs/xr1.cfg` (`ssh server rate-limit 600`) and a pause in `wait_ready.py`. On a running node: `conf t` → `ssh server rate-limit 600` → `commit` |
| A polling round seems frozen | Netmiko waits for its banner timeout | Normal; `banner_timeout` is 15 s in `nr/inventory/defaults.yaml` |

## Bootstrap (`make bootstrap`)

| Symptom | Cause | Fix |
|---|---|---|
| `host key mismatch for 172.30.30.11` | New VMs generate new SSH host keys at the same IPs | `make deploy` clears them; one-off: `for ip in 172.30.30.1{1,2,3}; do ssh-keygen -R $ip; done` |
| `gnxi ... % Invalid input detected`, then `gnmi-yang` too | This C8000v image has no gNMI CLI at its license level | Expected; bootstrap continues (`rescued=1`) |
| Red `fatal:` lines, but the recap shows `failed=0` | Output of the gNMI block/rescue fallback | Not an error |
| `Unable to connect to port 22` on all nodes | Lab not running (a failed `ci.sh` destroys it unless `KEEP_LAB=1`) | `make inspect`; then `make deploy wait` before `bootstrap` |

## Validate

| Symptom | Cause | Fix |
|---|---|---|
| `11/12 passed` right after `configure`; a rerun passes | OSPF still converging or routes not yet installed | Rerun `make validate`; validation retries pings automatically |
| A ping keeps failing | Missing route or interface mapping | On the source device: `show ip route <loopback>`; check OSPF neighbors on both ends |
| N9Kv 9500v interfaces don't match | The 9500v emulates a modular chassis | Check `show interface brief`; the 9300v-lite image is simpler for leaf/spine labs |

## Audit

| Symptom | Cause | Fix |
|---|---|---|
| `xe1 WARNING optional missing: gnmi server enabled` | gNMI is unavailable on this C8000v image | Expected; optional rules warn without failing the pipeline |
| xr1 `VIOLATION` (netconf / grpc) | XR bootstrap config missing on this deployment | `cat reports/audit.json`; rerun `make bootstrap` |

## APIs

| Symptom | Cause | Fix |
|---|---|---|
| NETCONF xr1: `Connection reset by peer` on :830 | NETCONF enabled in the wrong VRF (XRv9000 management is in `clab-mgmt`) | Bootstrap detects the VRF and adds `ssh server netconf vrf <mgmt-vrf>`. Verify: `show tcp brief \| include 830` |
| NETCONF nx1 shows `hostname (native model)` only | NX-OS image lacks the OpenConfig bundle | Expected fallback; counts as a pass |
| RESTCONF has no xr1 section | IOS XR does not implement RESTCONF | By design |
| gNMI nx1 TLS error after a long uptime | NX-OS self-signed gRPC certificate is short-lived | Install your own: `grpc certificate <trustpoint>` |

### XRv9000 gNMI and the management VRF

gNMI to xr1 is skipped by default (`GNMI_SKIP=xe1 xr1`). This is what was found and tried:

| Observation | Meaning |
|---|---|
| `connection reset by peer`, also with `--skip-verify` | Not a TLS mismatch |
| `docker exec clab-mvauto-xr1 ps aux \| grep -o 'hostfwd=[^ ,]*'` lists `57400` | vrnetlab forwards the port; not a forwarding problem |
| `show running-config interface MgmtEth0/RP0/CPU0/0` shows `vrf clab-mgmt` | Management is in a VRF; gRPC must listen there |
| `show grpc` → `Server : disabled (Invalid VRF)` | The VRF needs an address family: `vrf clab-mgmt` / `address-family ipv4 unicast` (bootstrap now adds it) |
| After moving gRPC to the default VRF: `Server : enabled`, but `use of closed network connection` | gRPC and management in different VRFs |
| Moving management itself into the default VRF (`no vrf`, re-add the IP, default route `0.0.0.0/0 10.0.0.2`) | Not confirmed to fix gNMI; lost on every redeploy |

Useful XR commands: `show grpc`, `show tcp brief`, `process restart emsd` (restarts the gRPC server).
If you get gNMI working on XRv9000 under vrnetlab, a pull request is very welcome. Test it with
`make gnmi GNMI_SKIP=xe1`.

## Configure / idempotency

| Symptom | Cause | Fix |
|---|---|---|
| `xe1 changed=1` on every `make configure`, no diff shown | `save_when: modified` compares running vs startup; IOS XE always shows small differences, so it saves every run | Use `save_when: changed` (save only when the task pushed commands) — the default since v1.2.0 |
| A task stays `changed` and `-v` shows the same `updates` every run | A template line doesn't match how the OS renders it in running-config | Compare with `show running-config \| section <feature>` and make the template match exactly |
| `paramiko is not installed: No module named 'paramiko'` | You ran the system `ansible-playbook`, not the one in `.venv` (no `(.venv)` in the prompt) | Use `make ...`, `.venv/bin/ansible-playbook ...`, or `source .venv/bin/activate` first |

## BGP

| Symptom | Cause | Fix |
|---|---|---|
| Sessions stay `Idle` / `Active` | Loopback0s not reachable (OSPF problem) | `ping 2.2.2.2 source 1.1.1.1`; fix OSPF first (`make validate`) |
| Sessions Established, BGP prefix missing | `network` statement doesn't match an exact route | Check Loopback200 exists with the `/32` from `bgp_networks` |
| Check commands | | XE/NX `show ip bgp summary`, XR `show bgp summary`; routes: `show ip route bgp` / `show route bgp` |

## Prune and drift

| Symptom | Cause | Fix |
|---|---|---|
| `prune` wants to delete a change set's loopback | The change file wasn't passed, so it isn't "intended" | `make prune KEEP_CHANGE=1` (uses `$(CHANGE)`) |
| `make drift` reports drift right after deploy | `golden/` is from an earlier deployment | Run `make golden` after each successful `make configure validate` |
| Drift on lines that change by themselves | A volatile line (timestamp, counter) isn't filtered | Add its pattern to `VOLATILE` in `nr/drift.py` |
| `drift-check` says no drift but `drift` shows changes | The change is in config the templates don't manage | Expected — that's why both methods exist |

## Lint (`make lint`)

| Symptom | Cause | Fix |
|---|---|---|
| Hundreds of yamllint warnings under `ansible/collections/` | yamllint scanned downloaded collections | `.yamllint` ignores `ansible/collections/` and `.venv/` |
| `trailing spaces` error | Invisible spaces at line ends | `sed -i 's/[[:space:]]*$//' <file>` |
| `warning too many blank lines (1 > 0)` | An empty line at the end of a YAML file | Only a warning (lint still passes); remove it with `sed -i '${/^$/d}' <file>` |

## Git

| Symptom | Cause | Fix |
|---|---|---|
| `remote: This repository moved. Please use the new location` | Repository renamed on GitHub | `git remote set-url origin <new URL>` |
| `lab.env`, `node.log`, `.venv` appear in `git status` | Not ignored | They are in `.gitignore`; for tracked files: `git rm --cached <file>` |

## Collecting information for an issue

```bash
lsb_release -d; uname -r; containerlab version; docker --version
free -g; nproc
make env
make inspect
docker logs --tail 100 clab-mvauto-<node> > node.log
```
