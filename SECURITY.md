# Security policy

## Scope

This repository is a **lab**. Its defaults are intentionally insecure so that a fresh, throwaway
topology works out of the box:

- Plaintext default credentials (`admin/admin`, `clab/clab@123`) in inventories.
- SSH host-key checking disabled for the lab management IPs.
- gNMI without TLS on IOS XR; self-signed TLS on NX-OS.
- Self-signed HTTPS for RESTCONF, with certificate verification disabled in the client scripts.

**Do not point these playbooks, inventories or connection settings at production devices.** Real
networks need a secrets manager or Ansible Vault, verified host keys, and TLS with proper certificates.

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
credential immediately.
