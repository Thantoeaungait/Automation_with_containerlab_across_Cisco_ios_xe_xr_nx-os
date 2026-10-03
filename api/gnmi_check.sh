#!/usr/bin/env bash
# gNMI smoke test with gnmic.
#   IOS XE / IOS XR: plaintext gRPC (--insecure) on :57400, OpenConfig paths
#   NX-OS:           TLS with self-signed cert (--skip-verify) on :57400, native path
# Capabilities failures fail the script; Get failures only warn (path support varies by release).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/reports"; mkdir -p "$OUT"
PORT="${GNMI_PORT:-57400}"
SKIP="${GNMI_SKIP:-xe1 xr1}"   # no gNMI on xe1 (unlicensed C8000v) or xr1 (XRv9k mgmt VRF); GNMI_SKIP=none tests all
command -v gnmic >/dev/null || { echo "gnmic not found: bash -c \"\$(curl -sL https://get-gnmic.openconfig.net)\""; exit 1; }

# name|address|user|password|tls-flag|encoding|get-path
TARGETS=(
  "xe1|172.30.30.11|admin|admin|insecure|json_ietf|/interfaces/interface[name=Loopback0]/state/oper-status"
  "xr1|172.30.30.12|clab|clab@123|insecure|json_ietf|/interfaces/interface[name=Loopback0]/state/oper-status"
  "nx1|172.30.30.13|admin|admin|skip-verify|json|/System/name"
)

fail=0
for t in "${TARGETS[@]}"; do
  IFS='|' read -r name addr user pass tls enc path <<<"$t"
  [[ " $SKIP " == *" $name "* ]] && { echo "=== ${name}: skipped (GNMI_SKIP)"; continue; }
  common=(-a "${addr}:${PORT}" -u "$user" -p "$pass" "--${tls}" --timeout 30s)
  echo "=== ${name} (${addr}:${PORT}, --${tls}) ==="

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
