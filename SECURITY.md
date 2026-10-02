# Security policy

## Scope

This repository is a **lab**. Its defaults are intentionally insecure so that a fresh, throwaway
topology works out of the box:

- Plaintext default credentials (`admin/admin`, `clab/clab@123`) in inventories.
- SSH host-key checking disabled for lab management IPs.
- gNMI without TLS on IOS XE/XR; self-signed TLS on NX-OS.
- Self-signed HTTPS for RESTCONF, with certificate verification disabled in the client scripts.

**Do not point these playbooks, inventories or connection settings at production devices.** For real
networks, use Ansible Vault or a secrets manager, verified host keys, and TLS with proper certificates.

The lab management network (`172.30.30.0/24`) is a local Docker bridge. Do not expose it, or the lab
host's forwarded ports, to untrusted networks.

## Reporting a vulnerability

If you find a security problem in the code itself (for example, a script that leaks secrets or executes
untrusted input), please **do not open a public issue**. Use GitLab's confidential issue option
("This issue is confidential") or contact the maintainer listed in the project profile.

Please include steps to reproduce and the affected file or commit. You can expect an acknowledgement
within 7 days.

## Accidental image or credential commits

If a Cisco image, license, or real credential is ever committed, it must be removed from the full Git
history (e.g. `git filter-repo`), not just deleted in a new commit. Real credentials should be rotated
immediately.
