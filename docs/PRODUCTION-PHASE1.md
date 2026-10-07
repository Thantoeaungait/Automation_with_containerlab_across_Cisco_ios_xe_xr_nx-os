# Production practices — phase 1

This phase moves the lab closer to how a production network is automated:

| Topic | Before | Now |
|---|---|---|
| Secrets | Plaintext passwords in four inventories | One encrypted vault (`secrets/vault.yml`), password from `openssl rand -base64 32` |
| Source of truth | Devices repeated in topology, Ansible, Nornir, pyATS, API scripts | `sot/fabric.yml` only; everything else is generated or read from it |
| AAA | Local accounts on each device | TACACS+ server in the lab, local fallback, local-only console |
| TLS | `--skip-verify` / `verify=False` | Lab CA and device certificates; clients can verify |
| Change safety | Validate after the change | Pre/post state snapshots and a diff |

Everything runs on the same lab host; the TACACS+ server is a small Linux container.

## Order of operations

```bash
make deps                  # once (adds nothing new, but keeps the venv current)
make vault-init            # 1. vault password + encrypted secrets
make topology              # 2. topology/lab.clab.yml from the SoT (also checked by make lint)
make deploy wait           # 3. deploy renders the TACACS+ config first, then starts the lab
make bootstrap configure validate
make tacacs tacacs-test    # 4. AAA via TACACS+
make pki                   # 5. lab CA + device certificates (install: see below)
make pre-check; make change; make post-check; make state-diff   # 6. change with state diff
```

---

## 1. Vault

```bash
make vault-init
```

- Creates `~/.config/mvauto/vault-pass` with `openssl rand -base64 32` (mode 600), **outside the repo**.
  Back it up in a password manager: without it the vault cannot be decrypted.
- Copies `secrets/vault.example.yml` to `secrets/vault.yml`, fills the `CHANGE_ME` values with random
  strings (TACACS+ key, `netops` password, PKCS#12 password) and encrypts it.
- `ansible.cfg` points at the password file, so Ansible decrypts transparently.
  `lab/sot.py` uses the same file to decrypt for Nornir, pyATS and the API scripts.

| Command | Purpose |
|---|---|
| `make vault-edit` | Change secrets (opens the decrypted file in `$EDITOR`, re-encrypts on save) |
| `make vault-view` | Show the decrypted secrets |
| `ANSIBLE_VAULT_PASSWORD_FILE=/path make ...` | Use a password file somewhere else (e.g. a CI secret) |

`secrets/vault.yml` is git-ignored: every user creates their own. Only the template is in Git.

**Rotating device passwords (exercise):** change a password on the devices (Ansible
`*_user` modules or CLI), then update `credentials` with `make vault-edit`. Nothing else changes,
because every tool reads credentials from the vault.

## 2. Single source of truth

`sot/fabric.yml` now also holds:

- `lab` — lab name and management subnet
- `platforms` — containerlab kind and image, interface naming, Ansible network OS, Netmiko /
  pyATS / ncclient driver, gNMI settings
- `devices.<name>.mgmt_ip` and optional `clab_startup_config`
- `services.tacacs` — TACACS+ server address, image and which platforms use it
- `pki.verify_with_lab_ca` — whether clients verify TLS against the lab CA

| Consumer | How it gets the data |
|---|---|
| containerlab | `make topology` generates `topology/lab.clab.yml` (links derived from `interfaces[].peer`) |
| Ansible | `ansible/inventory/sot.py` dynamic inventory; credentials mapped from the vault in `group_vars/lab.yml` |
| Nornir | `SotInventory` plugin in `nr/common.py` |
| pyATS | testbed built in memory (`lab.sot.pyats_testbed()`); `make testbed` writes one with `%ENV{}` passwords for the genie CLI |
| API scripts | `api/lab_devices.py`, `api/gnmi_check.sh` via `python -m lab.sot gnmi-targets` |

To add a device: add it to `devices` (and a platform if new), run `make topology`, then the usual
pipeline. `make lint` fails if the topology is out of date.

Removed: `ansible/inventory/hosts.yml`, `ansible/inventory/group_vars/{iosxe,iosxr,nxos}.yml`,
`nr/inventory/`, `validation/testbed.yaml`.

## 3. TACACS+ (AAA)

The server runs as a container `tacacs` at `services.tacacs.mgmt_ip` (172.30.30.20) on the
management network. Its config is rendered from the vault by `scripts/render_tacacs.py`
(`topology/configs/tac_plus.cfg`, git-ignored) before every deploy.

> The image `lfkeitel/tacacs_plus` runs Marc Huber's tac_plus, which uses its own syntax
> (`id = spawnd { ... }` and `id = tac_plus { host ... group ... user ... }`), not the classic
> Shrubbery format. Validate the rendered config without deploying: `make tacacs-check`.
> Another image works if you adjust `services.tacacs.image`, the bind path in
> `scripts/gen_topology.py` and the syntax in `scripts/render_tacacs.py`.

**Accounts on the server**

- the automation accounts from `credentials` (so Ansible/Nornir/pyATS keep working when the server
  answers), and
- human accounts from `tacacs.users` (`netops`), which exist **only** on the server.

All are in group `netadmin`: `priv-lvl 15` for IOS XE, optional `shell:roles "network-admin"` for
NX-OS, optional XR task groups.

**Device side** (`make tacacs`, templates in `ansible/templates/aaa/`)

| | IOS XE | NX-OS | IOS XR (opt-in) |
|---|---|---|---|
| Server group | `MGMT-TACACS`, in the management VRF if one is found | `MGMT-TACACS`, `use-vrf management` | `MGMT-TACACS`, management VRF if found |
| Login | `group MGMT-TACACS local` | `group MGMT-TACACS` (falls back to local when unreachable) | `group MGMT-TACACS local` |
| Authorization | `exec default group MGMT-TACACS local` | role from the server | `exec default group MGMT-TACACS local` |
| Accounting | exec start-stop | default | exec start-stop |
| Console | **local only** (`CONSOLE` list) | **local only** | **local only** (`CONSOLE` list) |

IOS XR is not in `apply_to` by default: XR maps remote users to task groups, and the attribute
format should be checked against your release before enabling it.

**Test**

```bash
make tacacs-test
```

Logs in as `netops` (which has no local account, so success proves TACACS+ authentication) and prints
the server's accounting log.

**If you lock yourself out**

1. Console: `telnet <mgmt-ip> 5000`, log in with the **local** account (console never uses TACACS+).
2. Revert AAA to local, for example on IOS XE: `aaa authentication login default local` and
   `aaa authorization exec default local`.
3. Check reachability from the device to the server (`ping 172.30.30.20 vrf <mgmt-vrf>`) and the key.

Note: `make bootstrap` sets local AAA on IOS XE again. Run `make tacacs` after it.

## 4. TLS certificates

```bash
make pki
```

Creates `secrets/pki/` (git-ignored): a lab CA (`ca.crt`, `ca.key`) and per device a key, a
certificate with SAN = hostname + management IP, and a PKCS#12 bundle protected by
`pki.p12_password` from the vault.

Install on the devices that serve TLS today. These are manual steps; check the exact syntax on your
release (`?` in the CLI):

**IOS XE (RESTCONF / HTTPS)**

```text
xe1(config)# ip scp server enable
host$ scp secrets/pki/xe1.p12 admin@172.30.30.11:bootflash:xe1.p12
xe1# crypto pki import MVAUTO pkcs12 bootflash:xe1.p12 password <p12_password>
xe1(config)# ip http secure-trustpoint MVAUTO
xe1(config)# no ip http secure-server
xe1(config)# ip http secure-server
```

**NX-OS (gNMI)**

```text
nx1(config)# feature scp-server
host$ scp secrets/pki/nx1.p12 admin@172.30.30.13:nx1.p12
nx1(config)# crypto ca trustpoint MVAUTO
nx1# crypto ca import MVAUTO pkcs12 bootflash:nx1.p12 <p12_password>
nx1(config)# grpc certificate MVAUTO
```

Check from the host, then switch clients to verification:

```bash
openssl s_client -connect 172.30.30.13:57400 -CAfile secrets/pki/ca.crt </dev/null | grep 'Verify return code'
# set pki.verify_with_lab_ca: true in sot/fabric.yml
make apis      # RESTCONF uses the CA bundle; gNMI uses --tls-ca for nx1
```

IOS XR gRPC stays plaintext in this lab (gNMI on XRv9000 is skipped, see TROUBLESHOOTING).

## 5. Pre/post checks

```bash
make pre-check          # genie learn ospf bgp interface -> reports/state-pre
make change
make post-check         # -> reports/state-post
make state-diff         # genie diff -> reports/state-diff
```

The expected difference after `make change` is the new Loopback100 (interfaces, OSPF). Anything else
in the diff (a neighbor gone, a BGP prefix missing) is a side effect worth investigating.

## Next phases

- **Rollback:** `commit confirmed` on IOS XR, `configure terminal revert timer` on IOS XE,
  checkpoint/rollback on NX-OS
- **Failure testing:** `containerlab tools netem` to break a link, then validate convergence
- **Telemetry:** gnmic + Prometheus + Grafana as containers in the lab
- **NetBox** as the SoT backend: replace `lab/sot.py`'s file loader with the NetBox API
- **Batfish:** analyse rendered configs before deploying
