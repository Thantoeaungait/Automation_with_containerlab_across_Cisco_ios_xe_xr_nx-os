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
command -v gnmic >/dev/null || { echo "gnmic not installed (see scripts/00-host-setup.sh)"; exit 1; }

stage() { printf '\n\033[1;36m==== %s  [%s] ====\033[0m\n' "$1" "$(date +%T)"; }

cleanup() {
  local rc=$?
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

stage "deploy";            make deploy TOPO="$TOPO"
stage "wait for nodes";    make wait
stage "bootstrap (day-0)"; make bootstrap
stage "configure (day-1)"; make configure
stage "validate baseline"; make validate
stage "apply change";      make change
stage "validate change";   make validate-change
stage "backup + audit";    make audit
stage "model-driven APIs"; make apis
