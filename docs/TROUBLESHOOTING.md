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
| `integer expression expected` near the XRv9000 size check | Older script parsed `qemu-img` JSON with sed and picked up nested values | Fixed: the size is read with a JSON parser (the warning was harmless) |

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

## Host resources

| Symptom | Cause | Fix |
|---|---|---|
| Containers exit, `docker ps -a` shows `Exited (137)`, `dmesg` shows `Out of memory: Killed process ... qemu` | Host out of RAM: the kernel killed a router VM | Check `free -h` (look at **available**, not free) and `docker stats --no-stream`; reduce VM sizes and add swap (below) |
| `free` shows 0 GB free | Normal: Linux uses spare RAM as cache | Only `available` matters; act if it is below ~1 GB |
| XRv9000 takes most of the RAM | vrnetlab default is ~16 GB | Default is now 10240 MB / 2 vCPU (`platforms.iosxr.clab_env`); raise with `XRV9K_MEMORY` in `lab.env` if XR fails to boot |
| Lab only fits with swap, then validation times out | VM memory swapped to disk: routers slow down, OSPF/BGP hellos are late | Swap is a safety net, not capacity. Stop unused containers (Batfish, NetBox), close the desktop browser, or deploy fewer nodes |

Add a swap file (16 GB, on SSD):

```bash
sudo fallocate -l 16G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swappiness.conf && sudo sysctl --system >/dev/null
```

`vm.swappiness=10` keeps the VMs in RAM until memory is really short.

## C8000v sizing

| Symptom | Cause | Fix |
|---|---|---|
| C8000v 17.16 never becomes ready; QFP process exits with `rc 139` | Too little memory/CPU for this release under nested virtualization | `C8KV_MEMORY ?= 8192` and `C8KV_SMP ?= 2` in `lab.env` (reported by Jeleel Muibi) |

## Wait (`make wait`)

| Symptom | Cause | Fix |
|---|---|---|
| `booting (no SSH banner)` for several minutes | VMs still booting | Normal; XRv9000 takes 10–20 min |
| `sshd up, login not ready: ['xr1(NetmikoAuthenticationException)']` | XRv9000 starts sshd before the `clab` user exists | Normal while booting |
| xr1 never becomes ready; XR log shows `Incoming SSH session rate limit exceeded` | IOS XR rate-limits SSH sessions from one source | Fixed by `topology/configs/xr1.cfg` (`ssh server rate-limit 600`) and a pause in `wait_ready.py`. On a running node: `conf t` → `ssh server rate-limit 600` → `commit` |
| A polling round seems frozen | Netmiko waits for its banner timeout | Normal; `banner_timeout` is 15 s in `nr/common.py` (SotInventory) |

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
| `make validate` right after `make deploy` shows 0 OSPF neighbors (older versions crashed with `Invalid command`) | `bootstrap` and `configure` were skipped, so OSPF isn't configured (on NX-OS even `feature ospf` is missing) | `make bootstrap configure validate` |
| `ParserNotFound: show ip ospf neighbors` for NX-OS | No Genie parser for this NX-OS release (e.g. 10.5) | Harmless: validation falls back to counting `FULL` in the raw output |
| `xe1 -> xr1:10.255.x.x` fails, other BGP prefixes pass | IOS XR delays BGP advertisements after its BGP process starts | Baseline validation skips BGP-only loopbacks; `make validate-bgp` waits up to 3 minutes |
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
| RESTCONF nx1: HTTP 200 but `Expecting value` / JSON decode error | Some NX-OS releases return YANG XML even when JSON is requested | Fixed: the script prints JSON or XML based on `Content-Type` |
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

## Topology and diagram

| Symptom | Cause | Fix |
|---|---|---|
| Deploy error mentioning `Gi1` on xe1 | `Gi1` is the C8000v management interface | Data links start at `Gi2` |
| Diagram still shows `eth1` / `eth2` | Endpoint labels come from `links:` in the topology, not from annotations | Use Cisco names in `links:`; `interfacePattern` only names links you create in the editor |
| Exported SVG has nodes and links but no text | TopoViewer writes free text as `<foreignObject>` (HTML inside SVG), which only browsers render | Open the SVG in Firefox/Chrome, or convert: `firefox --headless --window-size=1600,1000 --screenshot topology.png file://$PWD/topology.svg`. Check with `grep -c foreignObject topology.svg` |
| Text invisible in an exported SVG | Transparent background + dark text viewed on a dark background | Export with a custom background colour |
| Image not shown on GitHub | Wrong path or case (`Topology.png` ≠ `topology.png`) | Check `ls docs/topologyimages/` and the `src` in README |
| A new `docs/images/` folder is not committed | `.gitignore` ignores every `images/` folder (to keep Cisco images out of Git) | The diagram lives in `docs/topologyimages/` for that reason |

## Vault, SoT and TACACS+

| Symptom | Cause | Fix |
|---|---|---|
| `Vault password file not found` / `secrets/vault.yml not found` | Vault not created on this machine (it is git-ignored) | `make vault-init` |
| `Decryption failed` | Wrong password file (another machine, regenerated) | Restore `~/.config/mvauto/vault-pass` from your backup; otherwise recreate the vault |
| `topology/lab.clab.yml is out of date` | SoT changed without regenerating | `make topology` |
| `tacacs` exits: `Expected 'alias', 'id', ... but got 'key'` | Config in classic Shrubbery syntax; the image runs Marc Huber's tac_plus | Fixed in `render_tacacs.py` (spawnd + tac_plus blocks); check with `make tacacs-check` |
| Deploy fails with `context canceled` on xe1/xr1 after a container error | One node (e.g. `tacacs`) failed, so containerlab cancelled the rest | Fix the failing node first; for TACACS+: `make tacacs-check` |
| `tacacs` container restarting | Image or config path differs from `lfkeitel/tacacs_plus` | `docker logs clab-mvauto-tacacs`; adjust `services.tacacs.image` / bind path |
| `make tacacs-test`: xe1 `NetmikoAuthenticationException`, nx1 passes; no xe1 line in the server's access log; `show tacacs` shows socket opens but 0 packets sent | IOS XE read `group TAC` as the keyword `tacacs+` (abbreviation), so it used the global server list without the `clab-mgmt` VRF and fell back to local, where `netops` doesn't exist | Fixed: the group is `MGMT-TACACS`. Check `show running-config \| section ^aaa` shows `group MGMT-TACACS`, then `make tacacs tacacs-test`. Never name a server group with a prefix of a keyword |
| `make tacacs-test` fails, local accounts work | Device can't reach the server or the key differs | Read the diagnostics the test prints (server access log, device AAA config, ping in the management VRF); compare keys with `make vault-view` |
| `make ci` passes but TACACS+ was never tested | TACACS+ stages are opt-in | `TACACS=1 make ci` |
| Locked out after `make tacacs` | Server reachable but rejecting the account | Console (`telnet <mgmt-ip> 5000`) uses local login only; revert AAA to local there |

## Phase 2 (rollback, failover, telemetry, Batfish, NetBox)

| Symptom | Cause | Fix |
|---|---|---|
| `copy running-config` hangs or fails on IOS XE | Confirmation prompt | `checkpoint.yml` sets `file prompt quiet` first; check `show run \| include file prompt` |
| `rollback configuration to` not found on XR | No checkpoint file | Run `make checkpoint` first (`reports/checkpoint/xr1.commit`) |
| `netem failed` | Not in `clab_admins` and no passwordless sudo | `sudo usermod -aG clab_admins $USER`, log in again |
| Failover detects nothing | Wrong container interface | Check `platforms.*.container_if` against `docker exec clab-mvauto-xe1 ip link` |
| Grafana / Prometheus not reachable from a browser | Browser runs on another machine; 172.30.30.x is only reachable from the lab host | Use `http://<lab-host-ip>:3000` / `:9090` (published via `host_ports`); `make telemetry-status` |
| Telemetry containers missing | `services.telemetry.enabled` is false or `make topology` not re-run | Set it true, `make topology`, redeploy |
| `make telemetry-status`: 0 samples; gnmic log `transport: authentication handshake failed: EOF` for nx1 | TLS handshake to the NX-OS gRPC server fails. Likely cause: recent gnmic builds (newer Go) no longer offer RSA key-exchange cipher suites, which some NX-OS gRPC servers require | The generated gnmic node sets `GODEBUG: tlsrsakex=1` (`services.telemetry.gnmic_env`). Verify: `gnmic -a 172.30.30.13:57400 -u admin -p admin --skip-verify capabilities` from the host; if the host works and the container does not, compare `gnmic version` and the container's `docker logs` |
| gnmic restarts every `sample_interval` (~30 s), `exit=0`, `OOMKilled=false`, no error in the log, 0 samples | NX-OS ends the stream at the first sample when the subscription covers the whole `/System/intf-items/phys-items` subtree | Subscribe to narrow paths (`.../PhysIf-list/dbgIfIn-items`, `dbgIfOut-items`, `syscpusummary-items`, the default in `scripts/render_telemetry.py`), then `python3 scripts/render_telemetry.py && docker restart clab-mvauto-gnmic`. Check: `docker inspect -f '{{.RestartCount}} {{.State.StartedAt}}' clab-mvauto-gnmic` stays the same after 2 minutes |
| gnmic container uses several GB of RAM | Retry loop on a failing subscription | Capped at `services.telemetry.gnmic_memory` (512MB); fix the subscription error above |
| Grafana shows one flat 0 series whose labels list every NX-OS interface (`PhysIf_list_0_id="eth1/27", PhysIf_list_10_id=...`) | Unkeyed `PhysIf-list` path: NX-OS returns the whole list as one JSON blob and gnmic flattens it by index, so `PhysIf_list_0_*` is just the first (unused) port | Subscribe per interface with a keyed path, `PhysIf-list[id=eth1/1]/dbgIfIn-items` (generated from the SoT interfaces by `scripts/render_telemetry.py`) |
| Telemetry counters ~4.3 billion times the CLI value (`show interface` 18,476,574 bytes, gNMI `dbgIfIn-items/octets` 7.9355e16) | N9Kv DME uint64 counters arrive with their 32-bit halves swapped: value = real x 2^32 (measured: 1 unicast packet = +4294967296) | Divide by `4294967296` in PromQL (the shipped dashboard does). The counter will glitch once when the real value passes 2^32 (4 GB). Compare with the CLI before trusting a new path |
| Dashboard shows hundreds of Gb/s for a ping, zig-zag graph | `rate()` saw the counter go down and up (treated as resets) - device timestamps exported to Prometheus, and/or several series with the same labels | gnmic `export-timestamps: false` (default now); dashboard queries use `sum by (id) (rate(...{id!=""}))` |
| Grafana tab "Page Unresponsive" | Panels pulled thousands of flattened series with very long label sets | Use the shipped dashboard (exact metric names, `sum by (id)`, `maxDataPoints` 300); close old dashboard tabs |
| Prometheus query `nxos` returns nothing, target is UP | Metric names come from the gNMI origin and path, not the subscription name: NX-OS metrics start with `device_System_` | Query `{__name__=~"device_System_.*"}`, or type `device_` and use autocomplete |
| No `device_System_*` metrics in Prometheus | gnmic can't subscribe | `docker logs clab-mvauto-gnmic`; the native paths may differ on your NX-OS release |
| Batfish container exits or is slow | Not enough RAM | Run it with the lab destroyed; `docker logs batfish` |
| `netbox-sync`: 403 / token missing | Token not set or wrong | `make vault-edit` → `netbox.token` |
| `netbox-sync`: 403 `Invalid authorization header: Must be in the form "Bearer <key>.<token>"` | NetBox 4.5+ v2 token (`nbt_<key>.<secret>`) sent as `Token ...` | Store the **full** token `nbt_<key>.<secret>` in `netbox.token`; `netbox_sync.py` sends `Bearer` for `nbt_` tokens |

## Lint (`make lint`)

| Symptom | Cause | Fix |
|---|---|---|
| Hundreds of yamllint warnings under `ansible/collections/` | yamllint scanned downloaded collections | `.yamllint` ignores `ansible/collections/` and `.venv/` |
| `trailing spaces` error | Invisible spaces at line ends | `sed -i 's/[[:space:]]*$//' <file>` |
| `warning too many blank lines (1 > 0)` | An empty line at the end of a YAML file | Only a warning (lint still passes); remove it with `sed -i '${/^$/d}' <file>` |

## Releases and update packs

| Symptom | Cause | Fix |
|---|---|---|
| A problem fixed earlier comes back after applying an update pack (`APPLY.sh`) | The pack was built before the fix and copies older files over the working tree; or the release branch was created from `main` instead of the branch with the fix | Create release branches from the latest released branch; after applying a pack, `git diff <previous-release-branch> -- <file>` for files it touched, and run the full pipeline (`TACACS=1 FAILOVER=1 make ci`) before committing |

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
