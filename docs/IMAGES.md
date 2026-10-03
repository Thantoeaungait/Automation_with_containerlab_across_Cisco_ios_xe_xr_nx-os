# Images

This lab needs Cisco virtual images. They are licensed by Cisco and **must not be committed to this
repository or redistributed**. `.gitignore` blocks common image extensions as a safety net.

## What you need

| Node | File (tested) | Where to get it |
|---|---|---|
| Catalyst 8000v | `c8000v-universalk9.17.13.01a.qcow2` | software.cisco.com, CML reference platform ISO |
| Nexus 9000v-lite | `nexus9500v64-lite.10.5.5.M.qcow2` (9300v-lite also works) | software.cisco.com (10.x only) |
| XRv9000 | `xrv9k-fullk9-x-24.3.1.qcow2` | software.cisco.com, CML reference platform ISO |

Download the **KVM / qcow2** variants, not Vagrant boxes or OVAs. The full (non-lite) Nexus 9000v also
works; set `N9KV_MEMORY=10240` and `N9KV_SMP=4` in `lab.env`.

## Build

```bash
mkdir -p ~/cisco-images && cp /path/to/downloads/*.qcow2 ~/cisco-images/
N9KV_VARIANT=lite ./scripts/01-build-images.sh c8000v n9kv xrv9k
XRV9K_VERSION=24.3.1 ./scripts/01-build-images.sh xrv9k     # only if the XR file name has no version
docker images | grep -Ei 'c8000v|n9kv|xrv9k'
```

Expected result with the tested files:

```
vrnetlab/cisco_c8000v:17.13.01a
vrnetlab/cisco_n9kv:9500-lite-10.5.5.M
vrnetlab/cisco_xrv9k:24.3.1
```

These match the defaults in `topology/lab.clab.yml`. If your tags differ, set them in `lab.env`.

The script clones [srl-labs/vrnetlab](https://github.com/srl-labs/vrnetlab), places each file under the
name its Makefile expects (hard link when possible), and builds **only that file**.

## File naming rules (why builds fail with "Incorrect version string")

Each vrnetlab platform extracts the image tag from the file name. The build script renames
automatically; if you build by hand, rename first:

| Platform | vrnetlab expects | Example rename | Resulting image |
|---|---|---|---|
| N9Kv | `n9kv-<anything>.qcow2` | `nexus9500v64-lite.10.5.5.M.qcow2` → `n9kv-9500-lite-10.5.5.M.qcow2` | `vrnetlab/cisco_n9kv:9500-lite-10.5.5.M` |
| XRv9000 | `xrv9k-fullk9-x-<X.Y.Z>.qcow2` | `virtioa.qcow2` (EVE-NG layout) → `xrv9k-fullk9-x-24.3.1.qcow2` | `vrnetlab/cisco_xrv9k:24.3.1` |
| C8000v | `c8000v-universalk9.<ver>.qcow2` (or version from metadata) | usually none | `vrnetlab/cisco_c8000v:17.13.01a` |

## Platform notes

- **XRv9000 `INSTALL=true`** (script default): the first boot happens during the build and is stored in
  the image. The build takes 20–40 min; deploys become much faster. Use `XRV9K_INSTALL=false` if a
  release misbehaves in install mode. Check before building: `qemu-img info <file>` should show a
  virtual size of roughly 40–50 GB; much smaller usually means classic XRv, which is a different kind.
- **C8000v:** the controller-mode (SD-WAN) image is skipped unless `C8KV_CONTROLLER=1`.
- **N9Kv-lite:** runs with 6 GB RAM / 2 vCPU (the topology defaults). Check Cisco's release notes for
  data-plane limits; this lab only uses control-plane and management features.
- **XRd** (container, ~2 GB RAM) is supported by the build script (`./scripts/01-build-images.sh xrd`)
  but not used by the current topology. It needs a different `kind` (`cisco_xrd`) and interface names
  (`Gi0-0-0-0`) in the topology.
