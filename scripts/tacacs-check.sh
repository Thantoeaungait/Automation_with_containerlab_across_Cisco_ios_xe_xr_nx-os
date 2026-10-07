#!/usr/bin/env bash
# Start the TACACS+ image with the rendered config for a few seconds, without deploying the lab.
# Passes if the server keeps running; prints its log either way.   (make tacacs-check)
set -euo pipefail
cd "$(dirname "$0")/.."
IMAGE=$(sed -n '/^  tacacs:/,/^[^ ]/s/^ *image: *//p' sot/fabric.yml | head -n1)
CFG="$PWD/topology/configs/tac_plus.cfg"
NAME=mvauto-tacacs-check
[[ -f "$CFG" ]] || { echo "missing $CFG - run: make tacacs-config"; exit 1; }

docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" -v "$CFG:/etc/tac_plus/tac_plus.cfg:ro" "$IMAGE" >/dev/null
sleep 4
state=$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null || echo false)
echo "--- $IMAGE log ---"
docker logs "$NAME" 2>&1 | sed -E 's/(key|clear) +"[^"]*"/\1 "***"/' | tail -n 20
docker rm -f "$NAME" >/dev/null
if [[ "$state" == "true" ]]; then echo ">>> TACACS+ config OK (server running)"; else echo "!!! TACACS+ server exited - fix the config above"; exit 1; fi
