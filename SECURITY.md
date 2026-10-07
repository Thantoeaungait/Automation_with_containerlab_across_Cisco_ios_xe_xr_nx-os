# Security policy

## Scope

This repository is a **lab** that practises production automation workflows. Since v2.0:

- Secrets (device credentials, TACACS+ key, certificate passwords) are in `secrets/vault.yml`,
  encrypted with ansible-vault. The vault and its password file (`~/.config/mvauto/vault-pass`)
  are never committed; only `secrets/vault.example.yml` is.
- Human logins go through TACACS+ with accounting; the console stays local-only.

Some lab defaults remain intentionally insecure so that a throwaway topology works out of the box:

- The automation accounts keep the containerlab defaults (`admin/admin`, `clab/clab@123`), stored in the vault.
- SSH host-key checking is disabled (every deploy generates new host keys).
- gNMI without TLS on IOS XR; self-signed TLS on NX-OS and RESTCONF, with verification off until
  `make pki` certificates are installed and `pki.verify_with_lab_ca` is set.
- The TACACS+ server accepts any client address and gives every account privilege 15.

**Do not point these playbooks or connection settings at production devices** before closing the
gaps listed in [docs/PRODUCTION.md](docs/PRODUCTION.md#gaps-before-real-devices).

The lab management network (`172.30.30.0/24`) is a local Docker bridge. Do not expose it, or the lab
host's forwarded ports, to untrusted networks.

## Reporting a vulnerability

If you find a security problem in the code itself (for example, a script that leaks secrets or runs
untrusted input), please **don't open a public issue**. Use GitHub's private reporting instead:
**Security → Report a vulnerability** on the repository page.

Please include steps to reproduce and the affected file or commit.

## Accidental image or credential commits

If a Cisco image, license or real credential is ever committed, it must be removed from the full Git
history (for example with `git filter-repo`), not just deleted in a new commit. Rotate any real
credential immediately. If `secrets/vault.yml` or the vault password file is exposed, regenerate
both and change the TACACS+ key and account passwords (`make vault-edit`, then `make tacacs-config tacacs`).
