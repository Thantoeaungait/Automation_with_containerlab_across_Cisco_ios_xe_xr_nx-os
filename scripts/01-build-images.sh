#!/usr/bin/env bash
# Build containerlab images for the multivendor lab.
#   vrnetlab: C8000v, N9Kv (full or lite), XRv9k   |   docker load: XRv
#
# Usage:
#   ./scripts/01-build-images.sh                  # build everything found in $IMAGES_DIR
#   ./scripts/01-build-images.sh n9kv xrv9k         # build only selected platforms
#
# Knobs (env):
#   IMAGES_DIR      where Cisco files live           (default ~/cisco-images)
#   VRNETLAB_DIR    vrnetlab checkout                 (default ~/vrnetlab)
#   N9KV_VARIANT    lite | full | any                 (default any; lite preferred if both exist)
#   XRV9K_VERSION   required if the XRv9k file has no version in its name (e.g. virtioa.qcow2)
#   XRV9K_INSTALL   true | false  pre-bake first boot (default true; build +20-40 min, deploy much faster)
#   C8KV_CONTROLLER 1 to also build the SD-WAN controller-mode variant (default 0)
#
# Cisco filenames are normalised to what each vrnetlab Makefile expects:
#   nexus9500v64-lite.10.5.5.M.qcow2  -> n9kv-9500-lite-10.5.5.M.qcow2   -> vrnetlab/cisco_n9kv:9500-lite-10.5.5.M
#   nexus9300v64.10.4.3.F.qcow2       -> n9kv-9300-10.4.3.F.qcow2        -> vrnetlab/cisco_n9kv:9300-10.4.3.F
#   virtioa.qcow2 (+XRV9K_VERSION)    -> xrv9k-fullk9-x-7.11.1.qcow2     -> vrnetlab/cisco_xrv9k:7.11.1
#   c8000v-universalk9.17.15.01a.qcow2 (unchanged)                       -> vrnetlab/cisco_c8000v:17.15.01a
set -euo pipefail

IMAGES_DIR="${IMAGES_DIR:-$HOME/cisco-images}"
VRNETLAB_DIR="${VRNETLAB_DIR:-$HOME/vrnetlab}"
N9KV_VARIANT="${N9KV_VARIANT:-any}"
XRV9K_INSTALL="${XRV9K_INSTALL:-true}"
C8KV_CONTROLLER="${C8KV_CONTROLLER:-0}"
PLATFORMS=("${@:-c8000v n9kv xrv9k }")
read -r -a PLATFORMS <<<"${PLATFORMS[*]}"

log()  { printf '\033[1;36m>>> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m!!! %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[1;31mERR %s\033[0m\n' "$*" >&2; exit 1; }
want() { [[ " ${PLATFORMS[*]} " == *" $1 "* ]]; }

[[ -d "$IMAGES_DIR" ]] || die "IMAGES_DIR $IMAGES_DIR does not exist"
[[ -e /dev/kvm ]] || die "/dev/kvm missing: vrnetlab install steps need KVM"
[[ -d "$VRNETLAB_DIR" ]] || git clone --depth 1 https://github.com/srl-labs/vrnetlab "$VRNETLAB_DIR"

vr_dir() {  # newer vrnetlab: cisco/<platform>; older: <platform>
  if [[ -d "$VRNETLAB_DIR/cisco/$1" ]]; then echo "$VRNETLAB_DIR/cisco/$1"; else echo "$VRNETLAB_DIR/$1"; fi
}

first_match() {  # first file in IMAGES_DIR matching any of the given globs
  local g f
  for g in "$@"; do
    f=$(compgen -G "$IMAGES_DIR/$g" | sort | head -n1 || true)
    [[ -n "$f" ]] && { echo "$f"; return; }
  done
}

stage() {  # copy source into vrnetlab dir under the normalised name (hardlink when possible: saves GBs)
  local src=$1 dir=$2 dest=$3
  if [[ -e "$dir/$dest" ]]; then
    log "reusing $dir/$dest"
  else
    ln "$src" "$dir/$dest" 2>/dev/null || cp "$src" "$dir/$dest"
  fi
}

# ---------------------------------------------------------------- C8000v
build_c8000v() {
  local f dir dest
  f=$(first_match 'c8000v*.qcow2') || true
  [[ -z "${f:-}" ]] && { warn "skip c8000v: no c8000v*.qcow2 in $IMAGES_DIR"; return; }
  dir=$(vr_dir c8000v); dest=$(basename "$f")
  stage "$f" "$dir" "$dest"
  log "c8000v: building autonomous image from $dest"
  # docker-build = autonomous variant only (default docker-image also builds controller mode)
  make -C "$dir" IMAGE="$dest" MODE=autonomous docker-build
  if [[ "$C8KV_CONTROLLER" == "1" ]]; then
    local ver; ver=$(make -s -C "$dir" IMAGE="$dest" print-version)
    log "c8000v: building controller-mode image controller-$ver"
    make -C "$dir" IMAGE="$dest" VERSION="controller-$ver" MODE=controller docker-build
  fi
}

# ---------------------------------------------------------------- N9Kv
build_n9kv() {
  local f dir dest
  case "$N9KV_VARIANT" in
    lite) f=$(first_match 'nexus9[35]00v64-lite.*.qcow2' 'n9kv-*lite*.qcow2') || true ;;
    full) f=$(first_match 'nexus9[35]00v64.[0-9]*.qcow2') || true ;;
    any)  f=$(first_match 'nexus9[35]00v64-lite.*.qcow2' 'nexus9[35]00v64.[0-9]*.qcow2' 'n9kv-*.qcow2') || true ;;
    *)    die "N9KV_VARIANT must be lite|full|any" ;;
  esac
  [[ -z "${f:-}" ]] && { warn "skip n9kv: no $N9KV_VARIANT image in $IMAGES_DIR"; return; }
  dir=$(vr_dir n9kv); dest=$(basename "$f")
  if [[ "$dest" != n9kv-* ]]; then
    dest=$(sed -E 's/^nexus(9[35]00)v64(-lite)?\.(.+)\.qcow2$/n9kv-\1\2-\3.qcow2/' <<<"$dest")
    [[ "$dest" == n9kv-* ]] || die "cannot normalise n9kv filename $(basename "$f")"
  fi
  stage "$f" "$dir" "$dest"
  log "n9kv: building from $dest"
  make -C "$dir" IMAGES="$dest" docker-image     # IMAGES= limits the build to this one file
}

# ---------------------------------------------------------------- XRv9k
build_xrv9k() {
  local f dir dest
  f=$(first_match 'xrv9k-fullk9-x*.qcow2' 'xrv9k*.qcow2' 'virtioa.qcow2') || true
  [[ -z "${f:-}" ]] && { warn "skip xrv9k: no xrv9k image in $IMAGES_DIR"; return; }
  dir=$(vr_dir xrv9k); dest=$(basename "$f")
  if [[ ! "$dest" =~ [0-9]+\.[0-9]+\.[0-9]+ ]]; then
    [[ -n "${XRV9K_VERSION:-}" ]] || die "$dest has no version in its name: rerun with XRV9K_VERSION=7.11.1 (your real version)"
    dest="xrv9k-fullk9-x-${XRV9K_VERSION}.qcow2"
  fi
  local vsize
  vsize=$(qemu-img info --output=json "$f" 2>/dev/null | sed -n 's/.*"virtual-size": \([0-9]*\).*/\1/p' || true)
  if [[ -n "$vsize" && "$vsize" -lt 20000000000 ]]; then
    warn "$(basename "$f") virtual size is $((vsize/1024/1024/1024)) GB: may be classic XRv, not XRv9k"
  fi
  stage "$f" "$dir" "$dest"
  log "xrv9k: building from $dest (INSTALL=$XRV9K_INSTALL)"
  make -C "$dir" IMAGES="$dest" INSTALL="$XRV9K_INSTALL" docker-image
}

for p in "${PLATFORMS[@]}"; do
  case "$p" in
    c8000v|n9kv|xrv9k|xrv) want "$p" && "build_$p" ;;
    *) die "unknown platform '$p' (valid: c8000v n9kv xrv9k xrv)" ;;
  esac
done

echo
log "Available images (export C8KV_IMAGE / N9KV_IMAGE / XRV9K_IMAGE / XRV9K_IMAGE to match):"
docker images --format '{{.Repository}}:{{.Tag}}  {{.Size}}' | grep -Ei 'c8000v|n9kv|xrv9k|xrv' || true
