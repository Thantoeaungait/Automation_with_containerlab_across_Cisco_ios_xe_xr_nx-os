#!/usr/bin/env bash
# Full pipeline: deploy -> wait -> bootstrap -> configure -> validate -> change -> validate -> audit -> APIs -> destroy
#   TOPO=topology/<other>.clab.yml ./scripts/ci.sh       # another topology
#   KEEP_LAB=1 ./scripts/ci.sh                           # leave lab running for debugging
set -euo pipefail
cd "$(dirname "$0")/.."
TOPO="${TOPO:-$(make -s print-topo)}"
KEEP_LAB="${KEEP_LAB:-0}"
mkdir -p reports backups

# Fail fast (before deploying anything) if the toolchain is missing
if [[ ! -x .venv/bin/python || ! -x .venv/bin/ansible-playbook ]]; then
  echo "Python venv missing -> running 'make deps'"
  make deps
fi
[[ -f secrets/vault.yml ]] || make vault-init      # credentials live in the encrypted vault
command -v gnmic >/dev/null || { echo "gnmic not installed (see scripts/00-host-setup.sh)"; exit 1; }

stage() { printf '\n\033[1;36m==== %s  [%s] ====\033[0m\n' "$1" "$(date +%T)"; }

# run "<stage name>" <command...>: prints the banner and records name/start/end/rc in
# reports/stages.tsv, which scripts/run_manifest.py turns into reports/run-manifest.json
STAGES=reports/stages.tsv
: > "$STAGES"
run() {
  local name=$1; shift
  stage "$name"
  local t0 rc=0; t0=$(date +%s)
  "$@" || rc=$?
  printf '%s\t%s\t%s\t%s\n' "$name" "$t0" "$(date +%s)" "$rc" >> "$STAGES"
  return "$rc"
}

cleanup() {
  local rc=$?
  .venv/bin/python scripts/run_manifest.py --topo "$TOPO" --rc "$rc" || true   # before destroy: images still in use
  if [[ "$KEEP_LAB" != "1" ]]; then
    stage "destroy"
    make destroy TOPO="$TOPO" || true
  else
    echo "KEEP_LAB=1 -> lab left running"
  fi
  [[ $rc -eq 0 ]] && echo "PIPELINE PASSED" || echo "PIPELINE FAILED (rc=$rc)"
  exit "$rc"
}
trap cleanup EXIT

run "deploy"            make deploy TOPO="$TOPO"
run "wait for nodes"    make wait
run "bootstrap (day-0)" make bootstrap
if [[ "${TACACS:-0}" == "1" ]]; then                # opt-in: TACACS=1 ./scripts/ci.sh
  run "AAA via TACACS+" make tacacs
  run "TACACS+ login"   make tacacs-test
fi
run "configure (day-1)" make configure
run "validate baseline" make validate
run "validate BGP"      make validate-bgp
run "apply change"      make change
run "validate change"   make validate-change
run "prune change"      make prune
run "back to baseline"  make validate LABEL=after-prune
run "drift (SoT)"       make drift-check
run "backup + audit"    make audit
run "model-driven APIs" make apis
