#!/usr/bin/env bash
# gNMI smoke test with gnmic.
#   IOS XE / IOS XR: plaintext gRPC (--insecure) on :57400, OpenConfig paths
#   NX-OS:           TLS on :57400, native path; --skip-verify until `make pki` + cert install, then --tls-ca
# Capabilities failures fail the script; Get failures only warn (path support varies by release).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/reports"; mkdir -p "$OUT"
PORT="${GNMI_PORT:-57400}"
SKIP="${GNMI_SKIP:-xe1 xr1}"   # no gNMI on xe1 (unlicensed C8000v) or xr1 (XRv9k mgmt VRF); GNMI_SKIP=none tests all
command -v gnmic >/dev/null || { echo "gnmic not found: bash -c \"\$(curl -sL https://get-gnmic.openconfig.net)\""; exit 1; }

# name|address|user|password|tls|encoding|path  - generated from the SoT + vault (lab/sot.py)
PY="${PY:-$ROOT/.venv/bin/python}"
mapfile -t TARGETS < <(cd "$ROOT" && "$PY" -m lab.sot gnmi-targets)
(( ${#TARGETS[@]} > 0 )) || { echo "No gNMI targets from the SoT (vault missing? run: make vault-init)"; exit 1; }

fail=0
for t in "${TARGETS[@]}"; do
  IFS='|' read -r name addr user pass tls enc path <<<"$t"
  [[ " $SKIP " == *" $name "* ]] && { echo "=== ${name}: skipped (GNMI_SKIP)"; continue; }
  if [[ "$tls" == tls-ca=* ]]; then tlsflag=(--tls-ca "${tls#tls-ca=}"); else tlsflag=("--${tls}"); fi
  common=(-a "${addr}:${PORT}" -u "$user" -p "$pass" "${tlsflag[@]}" --timeout 30s)
  echo "=== ${name} (${addr}:${PORT}, ${tlsflag[*]}) ==="

  if gnmic "${common[@]}" capabilities >"$OUT/gnmi-${name}-capabilities.txt" 2>&1; then
    echo "  capabilities OK ($(grep -c 'Organization' "$OUT/gnmi-${name}-capabilities.txt" || true) models)"
    grep -m1 -i 'gNMI version' "$OUT/gnmi-${name}-capabilities.txt" | sed 's/^/  /' || true
  else
    echo "  capabilities FAILED:"; sed 's/^/    /' "$OUT/gnmi-${name}-capabilities.txt"; fail=1; continue
  fi

  if gnmic "${common[@]}" --encoding "$enc" get --path "$path" >"$OUT/gnmi-${name}-get.json" 2>&1; then
    echo "  get ${path} OK"; sed 's/^/    /' "$OUT/gnmi-${name}-get.json" | head -n 20
  else
    echo "  WARN get ${path} failed:"; sed 's/^/    /' "$OUT/gnmi-${name}-get.json" | head -n 5
  fi
done
exit "$fail"
