# Architecture and design decisions

## Flow

```
            sot/fabric.yml  +  sot/changes/*.yml
                   │                    │
      ┌────────────┴───────┐   ┌────────┴──────────┐
      ▼                    │   ▼                   │
 Ansible templates         │  validation/validate.py (pyATS)
 (render + push)           │   expected state derived from SoT
      │                    │
      ▼                    ▼
 xe1 ── xr1 ── nx1   ◄── Nornir (readiness, backup, audit)
      ▲
      └── NETCONF / RESTCONF / gNMI smoke tests (api/)
```

## Decisions

**Single source of truth.** Intent lives in one YAML file. Config templates and validation both read it,
so adding a link or node automatically updates the expected OSPF neighbor counts and reachability matrix.
The alternative — hard-coding expectations in tests — drifts from reality the first time someone edits
the design.

**Change sets as overlays.** `-e @sot/changes/x.yml` layers extra intent on top of the baseline. A merge
request can carry a change file, and CI validates exactly that delta. Promotion = merging the overlay into
`fabric.yml`.

**Day-0 vs day-1.** Bootstrap uses only SSH CLI to enable model-driven interfaces; it's the one step that
can't assume NETCONF/gNMI exists. Day-1 then runs on a uniform foundation.

**Idempotency.** `no shutdown` never appears in running-config, so text-diff modules (`*_config`) would
report "changed" forever. Interface admin state therefore uses resource modules (`*_interfaces`), and
templates render lines exactly as each OS displays them (netmasks on IOS XE/XR, prefix length + dotted
area on NX-OS).

**Readiness by polling.** vrnetlab VMs boot in 5–25 minutes depending on host and image. `wait_ready.py`
first checks for a real `SSH-` banner (cheap, no auth), then pauses briefly (IOS XR rate-limits rapid
connections from one source) before attempting a login.

**Tool choice.**

| Need | Tool | Why |
|---|---|---|
| Declarative config push | Ansible | Reviewable, `--check --diff`, vendor collections |
| Programmatic tasks (polling, audit) | Nornir | Plain Python, threaded, easy custom logic |
| State validation | pyATS/Genie | Mature parsers for all three NOSes |
| Vendor-neutral config/state API | NETCONF | Most consistent across XE/XR/NX-OS |
| Streaming telemetry | gNMI | Industry standard; support varies per image |

**XRd vs XRv9000.** XRd (container, ~2 GB, ~2 min boot) is the CI default. XRv9000 (VM, ~16 GB, slow boot)
is available when you need features missing from XRd control-plane. Interface names, IPs and credentials
are identical, so all automation is shared.

**Python 3.12 via uv.** Ubuntu 26.04 ships a newer CPython than pyATS wheels typically support at
release; `uv` pins 3.12 without touching the system interpreter.

**`sudo env` instead of `sudo -E`.** Ubuntu 26.04 uses sudo-rs, which ignores `-E`. The Makefile passes
image variables explicitly, or runs containerlab directly for `clab_admins` members.
