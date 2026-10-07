#!/usr/bin/env bash
# Lab PKI: a private CA plus one certificate per device, signed by that CA.
#   ./scripts/pki.sh            (also: make pki)
# Output in secrets/pki/ (git-ignored):
#   ca.crt / ca.key             the lab CA (clients trust ca.crt)
#   <dev>.crt / <dev>.key       device certificate, SAN = hostname + management IP
#   <dev>.p12                   PKCS#12 bundle for import on the device (password: vault pki.p12_password)
# Device installation is described in docs/PRODUCTION-PHASE1.md.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PY:-.venv/bin/python}"
OUT=secrets/pki
DAYS_CA=3650
DAYS_DEV=825
mkdir -p "$OUT"; chmod 700 "$OUT"

P12_PASS=$("$PY" -c 'from lab import sot; print(sot.secrets()["pki"]["p12_password"])')
mapfile -t DEVICES < <("$PY" -c 'from lab import sot
for n, d in sot.devices().items(): print(n, d["mgmt_ip"])')

if [[ ! -f "$OUT/ca.key" ]]; then
  openssl req -x509 -newkey rsa:4096 -nodes -sha256 -days "$DAYS_CA" \
    -subj "/CN=mvauto-lab-ca/O=mvauto lab" \
    -keyout "$OUT/ca.key" -out "$OUT/ca.crt" 2>/dev/null
  chmod 600 "$OUT/ca.key"
  echo ">>> created CA: $OUT/ca.crt"
else
  echo ">>> reusing CA: $OUT/ca.crt"
fi

for entry in "${DEVICES[@]}"; do
  read -r name ip <<<"$entry"
  openssl req -newkey rsa:2048 -nodes -sha256 -subj "/CN=${name}/O=mvauto lab" \
    -keyout "$OUT/${name}.key" -out "$OUT/${name}.csr" 2>/dev/null
  printf 'subjectAltName=DNS:%s,IP:%s\nextendedKeyUsage=serverAuth\nkeyUsage=digitalSignature,keyEncipherment\n' \
    "$name" "$ip" > "$OUT/${name}.ext"
  openssl x509 -req -in "$OUT/${name}.csr" -CA "$OUT/ca.crt" -CAkey "$OUT/ca.key" -CAcreateserial \
    -days "$DAYS_DEV" -sha256 -extfile "$OUT/${name}.ext" -out "$OUT/${name}.crt" 2>/dev/null
  # -legacy keeps the bundle readable by older device PKCS#12 parsers (OpenSSL 3 default is AES)
  openssl pkcs12 -export -legacy -inkey "$OUT/${name}.key" -in "$OUT/${name}.crt" -certfile "$OUT/ca.crt" \
    -name "$name" -passout "pass:${P12_PASS}" -out "$OUT/${name}.p12" 2>/dev/null \
  || openssl pkcs12 -export -inkey "$OUT/${name}.key" -in "$OUT/${name}.crt" -certfile "$OUT/ca.crt" \
    -name "$name" -passout "pass:${P12_PASS}" -out "$OUT/${name}.p12"
  chmod 600 "$OUT/${name}.key" "$OUT/${name}.p12"
  rm -f "$OUT/${name}.csr" "$OUT/${name}.ext"
  openssl verify -CAfile "$OUT/ca.crt" "$OUT/${name}.crt" >/dev/null && echo ">>> ${name}: certificate for ${ip} (verified against CA)"
done
