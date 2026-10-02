# Contributing

Thanks for helping improve this lab! Bug reports, platform fixes, new validation checks and docs are all welcome.

## Ground rules

- **Never commit Cisco images, license files, or real credentials.** Merge requests containing them will be closed and the history rewritten.
- Keep the source of truth authoritative: new checks should derive their expectations from `sot/`, not hard-code them.
- One logical change per merge request.

## Development setup

```bash
./scripts/00-host-setup.sh   # once
make deps
cp lab.env.example lab.env   # set your image tags
```

## Before opening a merge request

```bash
make lint                    # yamllint, shellcheck, py_compile, template render (no lab needed)
make render                  # eyeball the generated configs
```

If you have a lab host, also run the stages your change touches, ideally the full pipeline:

```bash
KEEP_LAB=1 ./scripts/ci.sh
```

State the topology, image versions (`make env`) and containerlab version in the MR description.

## Style

- **Python:** 3.12, type hints where useful, `ruff`/`black` defaults, no third-party deps beyond `requirements.txt` without discussion.
- **Ansible:** fully-qualified collection names (`cisco.ios.ios_config`), `--check --diff` must work, keep templates matching running-config rendering.
- **Shell:** `set -euo pipefail`, must pass `shellcheck -S warning`.
- **YAML:** must pass `yamllint -c .yamllint`.
- **Commits:** imperative mood, e.g. `validation: check BGP sessions from SoT`. Conventional Commit prefixes (`feat:`, `fix:`, `docs:`) are welcome.

## Adding a platform or node

1. Add the node to `topology/*.clab.yml` with a fixed `mgmt-ipv4`.
2. Add it to `sot/fabric.yml`.
3. Add inventory entries: `ansible/inventory`, `nr/inventory`, `validation/testbed.yaml`, `api/lab_devices.py`.
4. Add templates under `ansible/templates/{bootstrap,day1}/` and tasks in the playbooks.
5. Add ping/OSPF command mappings in `validation/validate.py` and audit rules in `nr/backup_and_audit.py`.
6. Document image preparation in `docs/IMAGES.md`.

## Reporting bugs

Use the **Bug** issue template and include the output listed in [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md#collecting-information-for-an-issue).
