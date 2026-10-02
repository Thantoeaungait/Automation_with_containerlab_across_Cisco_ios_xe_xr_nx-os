# Images

This lab needs Cisco virtual images. They are licensed by Cisco and **must not be committed to this
repository or redistributed**. `.gitignore` blocks common image extensions as a safety net.

## What you need

| Node | File (example) | Where to get it | Needed for |
|---|---|---|---|
| Catalyst 8000v | `c8000v-universalk9.17.13.01a.qcow2` | software.cisco.com, CML reference platform ISO | both topologies |
| Nexus 9000v | `nexus9300v64.10.4.3.F.qcow2` | software.cisco.com, CML reference platform ISO | both topologies |
| Nexus 9000v lite | `nexus9300v64-lite.10.5.x.qcow2` / `nexus9500v64-lite...` | software.cisco.com (10.x only) | optional, smaller footprint |
| XRd control-plane | `xrd-control-plane-container-x64.dockerv1.tgz` | software.cisco.com | `lab.clab.yml` |
| XRv9000 | `xrv9k-fullk9-x-24.3.1.qcow2` | software.cisco.com, CML reference platform ISO | `lab-xrv9k.clab.yml` |

Download the **KVM / qcow2** variants, not Vagrant boxes or OVAs.

## Build

```bash
mkdir -p ~/cisco-images && cp /path/to/downloads/* ~/cisco-images/
./scripts/01-build-images.sh                       # everything found
./scripts/01-build-images.sh n9kv xrd              # selected platforms only
N9KV_VARIANT=lite ./scripts/01-build-images.sh n9kv
XRV9K_VERSION=7.11.1 ./scripts/01-build-images.sh xrv9k   # only if the file name has no version
docker images | grep -Ei 'c8000v|n9kv|xrv9k|xrd'
```

The script clones [srl-labs/vrnetlab](https://github.com/srl-labs/vrnetlab), copies (hard-links) each
file under the name its Makefile expects, and builds **only that file**.

## File naming rules (why builds fail with "Incorrect version string")

Each vrnetlab platform extracts the image tag from the file name with its own regex. The build script
normalises names automatically; if you build by hand, rename first:

| Platform | vrnetlab expects | Example rename | Resulting image |
|---|---|---|---|
| N9Kv | `n9kv-<anything>.qcow2` | `nexus9500v64-lite.10.5.5.M.qcow2` → `n9kv-9500-lite-10.5.5.M.qcow2` | `vrnetlab/cisco_n9kv:9500-lite-10.5.5.M` |
| XRv9000 | `xrv9k-fullk9-x-<X.Y.Z>.qcow2` | `virtioa.qcow2` (EVE-NG layout) → `xrv9k-fullk9-x-24.3.1.qcow2` | `vrnetlab/cisco_xrv9k:24.3.1` |
| C8000v | `c8000v-universalk9.<ver>.qcow2` (or version from metadata) | usually none | `vrnetlab/cisco_c8000v:17.13.01a` |

## Platform notes

- **XRv9000 `INSTALL=true`** (script default): the first boot happens during the build and is baked into
  the image. Build takes 20–40 min; deploys become much faster. Use `XRV9K_INSTALL=false` if a newer XR
  release misbehaves in install mode. vrnetlab lists up to 7.11 as tested; 24.x has worked in practice.
- **C8000v**: vrnetlab can also build an SD-WAN controller-mode image; the script skips it unless
  `C8KV_CONTROLLER=1`.
- **N9Kv-lite**: set `N9KV_MEMORY=6144` and `N9KV_SMP=2` in `lab.env`. Check Cisco's release notes for
  data-plane feature limits; this lab only uses control-plane and management features.
- **XRd**: loaded with `docker load`. Host needs raised inotify limits (set by `00-host-setup.sh`).

After building, copy `lab.env.example` to `lab.env` and set the exact tags from `docker images`.
