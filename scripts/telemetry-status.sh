#!/usr/bin/env bash
# Diagnose the telemetry stack: containers, endpoints, and whether metrics arrive.   (make telemetry-status)
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
LAB=$(sed -n 's/^  name: *//p' sot/fabric.yml | head -n1)
if ! grep -q '^    enabled: true' <(sed -n '/^  telemetry:/,/^  [a-z]/p' sot/fabric.yml); then
  echo "!!! services.telemetry.enabled is false in sot/fabric.yml -> set true, then: make topology && make deploy"
  exit 1
fi

echo "--- containers"
for c in gnmic prometheus grafana; do
  st=$(docker inspect -f '{{.State.Status}} (restarts: {{.RestartCount}})' "clab-${LAB}-${c}" 2>/dev/null || echo "not deployed")
  printf '%-11s %s\n' "$c" "$st"
done

check() {  # name url
  code=$(curl -s -o /dev/null -m 5 -w '%{http_code}' "$2")
  printf '%-30s %-40s %s\n' "$1" "$2" "$([[ $code =~ ^(200|302)$ ]] && echo OK || echo "FAIL ($code)")"
}
HOST_IP=$(hostname -I | awk '{print $1}')
echo; echo "--- endpoints"
check "gnmic metrics (mgmt IP)"      "http://172.30.30.21:9804/metrics"
check "prometheus (mgmt IP)"         "http://172.30.30.22:9090/-/ready"
check "grafana (mgmt IP)"            "http://172.30.30.23:3000/login"
check "prometheus (host port)"       "http://${HOST_IP}:9090/-/ready"
check "grafana (host port)"          "http://${HOST_IP}:3000/login"

echo; echo "--- metrics from devices"
n=$(curl -s -m 5 http://172.30.30.21:9804/metrics | grep -vc '^#')
echo "gnmic exports ${n:-0} sample lines"
[[ "${n:-0}" -gt 0 ]] || { echo "no samples: check  docker logs clab-${LAB}-gnmic"; docker logs --tail 15 "clab-${LAB}-gnmic" 2>&1 | sed 's/password[^,]*/password: ***/'; }

echo; echo "Open from another machine: http://${HOST_IP}:3000 (Grafana, admin/admin) and http://${HOST_IP}:9090 (Prometheus)"
