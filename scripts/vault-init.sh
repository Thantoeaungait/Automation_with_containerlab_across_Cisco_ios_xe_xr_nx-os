#!/usr/bin/env bash
# Create the vault password (openssl rand -base64 32) and the encrypted secrets/vault.yml.
#   ./scripts/vault-init.sh          (also: make vault-init)
# Safe to re-run: never overwrites an existing password file or vault.
set -euo pipefail
cd "$(dirname "$0")/.."
PASS_FILE="${ANSIBLE_VAULT_PASSWORD_FILE:-$HOME/.config/mvauto/vault-pass}"
VAULT=secrets/vault.yml
VAULT_BIN="${VAULT_BIN:-.venv/bin/ansible-vault}"

rand() { openssl rand -base64 "$1" | tr -d '\n=+/' | cut -c1-"$2"; }   # CLI-safe characters

# 1. vault password: 32 random bytes, base64-encoded, readable only by you
if [[ -f "$PASS_FILE" ]]; then
  echo ">>> vault password file exists: $PASS_FILE"
else
  mkdir -p "$(dirname "$PASS_FILE")"
  ( umask 077; openssl rand -base64 32 > "$PASS_FILE" )
  echo ">>> created vault password file: $PASS_FILE (mode 600)"
  echo "    BACK IT UP somewhere safe (password manager). Without it the vault cannot be decrypted."
fi

# 2. secrets file from the template, with random values for the CHANGE_ME placeholders
if [[ -f "$VAULT" ]]; then
  echo ">>> $VAULT exists - edit it with: make vault-edit"
else
  sed -e "s/CHANGE_ME_TACACS_KEY/$(rand 48 32)/" \
      -e "s/CHANGE_ME_NETOPS_PASSWORD/$(rand 32 20)/" \
      -e "s/CHANGE_ME_P12_PASSWORD/$(rand 32 20)/" \
      secrets/vault.example.yml > "$VAULT"
  ANSIBLE_VAULT_PASSWORD_FILE="$PASS_FILE" "$VAULT_BIN" encrypt "$VAULT"
  echo ">>> created and encrypted $VAULT"
fi

head -c 14 "$VAULT" | grep -q '^\$ANSIBLE_VAULT' && echo ">>> vault is encrypted" \
  || { echo "!!! $VAULT is NOT encrypted: run make vault-encrypt"; exit 1; }
