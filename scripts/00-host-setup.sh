#!/usr/bin/env bash
# Prepare an Ubuntu 26.04 host: Docker, KVM, containerlab, gnmic, uv, XRd sysctls.
# Run as a normal user with sudo rights. Log out/in afterwards (group membership).
set -euo pipefail
[[ $EUID -eq 0 ]] && { echo "Run as a regular user with sudo, not root."; exit 1; }
. /etc/os-release; echo ">>> Host: ${PRETTY_NAME}  kernel $(uname -r)"

echo ">>> Base packages, Docker (Ubuntu archive build), KVM"
sudo apt-get update
sudo apt-get install -y ca-certificates curl git make jq unzip iproute2 openssh-client \
  docker.io shellcheck qemu-system-x86 qemu-utils cpu-checker
sudo systemctl enable --now docker

echo ">>> KVM check (vrnetlab VMs need /dev/kvm)"
if ! kvm-ok; then
  echo "KVM unavailable: enable VT-x/AMD-V in BIOS, or nested virtualization on your hypervisor."
  exit 1
fi

echo ">>> XRd host requirements (inotify limits)"
sudo tee /etc/sysctl.d/90-xrd.conf >/dev/null <<'SYSCTL'
fs.inotify.max_user_instances=64000
fs.inotify.max_user_watches=524288
kernel.randomize_va_space=2
SYSCTL
sudo sysctl --system >/dev/null

echo ">>> containerlab"
bash -c "$(curl -sL https://get.containerlab.dev)"

echo ">>> gnmic"
bash -c "$(curl -sL https://get-gnmic.openconfig.net)"

echo ">>> uv (manages a Python 3.12 venv independent of the system Python)"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh

echo ">>> Group membership"
sudo usermod -aG docker,kvm "$USER"
getent group clab_admins >/dev/null && sudo usermod -aG clab_admins "$USER" || true

containerlab version || true
docker --version
echo ">>> Done. Log out and back in (or 'newgrp docker') before continuing."
