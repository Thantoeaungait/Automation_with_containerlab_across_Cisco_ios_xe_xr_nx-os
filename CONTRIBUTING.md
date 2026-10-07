# Contributing

Thanks for helping improve this lab! It's a learning project, so questions, corrections and
suggestions from experienced engineers are especially welcome.

## Ground rules

- **Never commit Cisco images, license files, or real credentials.** Pull requests containing them
  will be closed and the history cleaned.
- Keep the source of truth authoritative: new checks should derive expectations from `sot/`, not hard-code them.
- One logical change per pull request.

## Development setup

```bash
./scripts/00-host-setup.sh   # once
make deps
cp lab.env.example lab.env   # only if your image tags differ
```

## Before opening a pull request

```bash
make lint                    # yamllint, shellcheck, py_compile, template render (no lab needed)
make render                  # look at the generated configs
```

If you have a lab host, also run the stages your change touches, ideally the full pipeline:

```bash
KEEP_LAB=1 ./scripts/ci.sh
```

Mention the image versions (`make env`, `docker images`) and containerlab version in the pull request.

## Style

- **Python:** 3.12, type hints where useful; no new dependencies without discussion.
- **Ansible:** fully-qualified module names (`cisco.ios.ios_config`); `--check --diff` must work;
  templates must match running-config rendering.
- **Shell:** `set -euo pipefail`; must pass `shellcheck -S warning`.
- **YAML:** must pass `yamllint -c .yamllint`.
- **Commits:** imperative mood, e.g. `validation: check BGP sessions from SoT`. Prefixes like
  `feat:`, `fix:`, `docs:` are welcome.

## Adding a node or platform

1. Add the device to `sot/fabric.yml` (`devices`, plus a `platforms` entry and vault `credentials` if it is a new platform).
2. Run `make topology` to regenerate `topology/lab.clab.yml`. Ansible, Nornir, pyATS and the API scripts pick it up automatically.
3. Nothing else holds an inventory: there are no per-tool host files to update.
4. Add templates under `ansible/templates/{bootstrap,day1}/` and tasks in the playbooks.
5. Add OSPF/ping command mappings in `validation/validate.py` and audit rules in `nr/backup_and_audit.py`.
6. Document image preparation in `docs/IMAGES.md`.
7. Place the node in TopoViewer (updates `topology/lab.clab.yml.annotations.json`) and refresh `docs/topologyimages/topology.png`.

## Reporting bugs

Open an issue with the **Bug report** template and include the output listed in
[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md#collecting-information-for-an-issue).
