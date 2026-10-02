# Troubleshooting

Problems found while building and running this lab, grouped by stage. Search this page for the exact
error text you see.

**General tips**

- Run `make` from the repository root. Otherwise you get `No rule to make target 'ci'`.
- While debugging, keep the lab up with `KEEP_LAB=1 ./scripts/ci.sh`, then rerun individual stages.
- Check host resources first: `free -g`, `docker stats --no-stream`. Swapping causes timeouts on every stage.

---

## Host setup

| Symptom | Cause | Fix |
|---|---|---|
| `kvm-ok` fails | No hardware virtualization | Enable VT-x/AMD-V in BIOS, or nested virtualization on the hypervisor |
| Terminal closes after pasting a snippet | A snippet meant for a script contained `exit` | Put script snippets in the file, not the terminal |

## Image build (`scripts/01-build-images.sh`)

| Symptom | Cause | Fix |
|---|---|---|
| `ERROR: Incorrect version string (nexus9500v64-lite...qcow2)` | vrnetlab n9kv expects `n9kv-<version>.qcow2` | Use the build script (renames automatically) or rename by hand, see [IMAGES.md](IMAGES.md) |
| `ERROR: Incorrect version string (virtioa.qcow2)` | EVE-NG style file name, no version | Rename to `xrv9k-fullk9-x-<X.Y.Z>.qcow2` or pass `XRV9K_VERSION=` |
| Two C8000v images built (`controller-...`) | vrnetlab default builds both modes | Script builds autonomous only; `C8KV_CONTROLLER=1` for both |
| `./scripts/01-build-images.sh: No such file or directory` | Ran from the wrong directory | `cd` to the repo root first |

## Deploy

| Symptom | Cause | Fix |
|---|---|---|
| `pull access denied for vrnetlab/cisco_c8000v` | containerlab didn't receive your tags and fell back to defaults | Create `lab.env` from `lab.env.example`; check with `make env` |
| `sudo: preserving the entire environment is not supported, '-E' is ignored` | Ubuntu 26.04 sudo-rs | Already handled by the Makefile (`sudo env ...`); best: `sudo usermod -aG clab_admins $USER` and re-login |
| `Command 'cexport' not found` | Typo while exporting variables | Use `lab.env` instead of manual exports |

## Wait (`make wait`)

| Symptom | Cause | Fix |
|---|---|---|
| `.venv/bin/python: No such file or directory` | Python environment not created | `make deps` (ci.sh now does this automatically) |
| Long tracebacks `Error reading SSH protocol banner` / `Bad file descriptor` | vrnetlab accepts TCP :22 before the VM's sshd runs | Normal while booting; current `wait_ready.py` probes the banner first and suppresses tracebacks |
| `sshd up, login not ready: ['xr1(NetmikoAuthenticationException)']` for a few minutes | XRv9k starts sshd before the `clab` user is configured | Normal while booting; wait |
| xr1 stays "login not ready"; device log shows `Incoming SSH session rate limit exceeded` | IOS XR rate-limits new SSH sessions from one source | Fixed by `topology/configs/xr1.cfg` (`ssh server rate-limit 600`) and a pause in `wait_ready.py`. On a running node: `conf t` → `ssh server rate-limit 600` → `commit` |
| Round seems frozen ~2 min | Netmiko waits for banner timeout | Normal; `banner_timeout` is 15 s in `nr/inventory/defaults.yaml` |

Watch boot progress: `docker logs -f clab-mvauto-xr1`. Serial console: `telnet 172.30.30.12 5000`.

## Bootstrap (`make bootstrap`)

| Symptom | Cause | Fix |
|---|---|---|
| `host key mismatch for 172.30.30.11` | New VMs = new host keys at the same IPs; old keys in `~/.ssh/known_hosts` | `make deploy` now runs `ssh-keygen -R` for lab IPs; one-off: `for ip in 172.30.30.1{1,2,3}; do ssh-keygen -R $ip; done` |
| `gnxi ... % Invalid input detected` (then `gnmi-yang` too) | C8000v image has no gNMI CLI at its license level | Expected; bootstrap continues (`rescued=1`). gNMI test skips xe1 by default |
| `Unable to connect to port 22` on all nodes | Lab not running (a failed `ci.sh` destroys it unless `KEEP_LAB=1`) | `make inspect`; redeploy and `make wait` before `bootstrap` |
| Red `fatal:` lines but recap shows `failed=0` | Output of the block/rescue fallback | Not an error |

## Audit / APIs

| Symptom | Cause | Fix |
|---|---|---|
| `make audit` fails for xr1 | XR bootstrap config missing on this deployment | `cat reports/audit.json`; rerun `make bootstrap`; verify `show running-config netconf-yang` |
| NETCONF xr1: `Connection reset by peer` (10 attempts) | Nothing listening on :830 inside the VM | On xr1: `netconf-yang agent` / ` ssh`, `ssh server netconf vrf default`, `commit`; verify `show tcp brief \| include 830`; test `ssh -p 830 clab@172.30.30.12 -s netconf` |
| NETCONF nx1 prints `hostname (native model)` only | NX-OS image lacks OpenConfig bundle | Expected fallback, counts as pass |
| RESTCONF has no xr1 section | IOS XR does not implement RESTCONF | By design |
| gNMI to nx1 TLS error | Self-signed cert expired (short-lived) | Install a certificate: `grpc certificate <trustpoint>` |
| gNMI refused on a vrnetlab node but SSH works | Port not in vrnetlab's forward list | Add `env: { CLAB_MGMT_PASSTHROUGH: "true" }` to the node, or use a forwarded port |

## Collecting information for an issue

```bash
lsb_release -d; uname -r; containerlab version; docker --version
free -g; nproc
make env
make inspect
docker logs --tail 100 clab-mvauto-<node> > node.log
```
