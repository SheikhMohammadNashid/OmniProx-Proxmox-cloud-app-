#!/usr/bin/env bash
# ============================================================
# SETUP_GOLDEN_IMAGE.sh
# Run ONCE on your Proxmox node as root.
#
# Builds a single golden template from a **local** Ubuntu 24.04 (noble) cloud
# image. The qm steps match a typical manual sequence (see comments in repo).
#
# By default the script uses virt-customize to install qemu-guest-agent into a
# copy of the disk (needs: apt + libguestfs-tools, working DNS/internet).
#
# If apt/DNS is broken on the node, use:
#   SKIP_VIRT_CUSTOMIZE=1 ./SETUP_GOLDEN_IMAGE.sh
# The script will automatically create a cloud-init vendor snippet that installs
# and starts qemu-guest-agent on first boot (required for IP detection).
#
# Usage:
#   chmod +x SETUP_GOLDEN_IMAGE.sh
#   export CLOUD_IMG=/root/noble-server-cloudimg-amd64.img   # if needed
#   ./SETUP_GOLDEN_IMAGE.sh
#   # or: SKIP_VIRT_CUSTOMIZE=1 ./SETUP_GOLDEN_IMAGE.sh
#
# Matches app mapping: ubuntu-24.04 → VMID 9000 (CLOUD_TEMPLATE_MAP in proxmox_client.py).
# ============================================================

set -euo pipefail

CLOUD_IMG="${CLOUD_IMG:-/root/noble-server-cloudimg-amd64.img}"
VMID="${VMID:-9000}"
NAME="${NAME:-ubuntu-24.04-template}"
STORAGE="${STORAGE:-local-lvm}"
SKIP_VIRT_CUSTOMIZE="${SKIP_VIRT_CUSTOMIZE:-0}"
SNIPPETS_DIR="/var/lib/vz/snippets"
SNIPPET_FILE="$SNIPPETS_DIR/qemu-agent.yaml"

NODE=$(hostname)

echo "Proxmox golden template (Ubuntu 24.04 noble only)"
echo "Node: $NODE  |  Storage: $STORAGE  |  VMID: $VMID"
if [[ "$SKIP_VIRT_CUSTOMIZE" == "1" ]]; then
  echo "SKIP_VIRT_CUSTOMIZE=1 — importing .img as-is; cloud-init snippet will install guest-agent on first boot"
fi
echo ""

if [[ ! -f "$CLOUD_IMG" ]]; then
  echo "Image not found: $CLOUD_IMG"
  echo "  export CLOUD_IMG=/full/path/to/noble-server-cloudimg-amd64.img"
  exit 1
fi

if qm status "$VMID" &>/dev/null; then
  echo "⚠  VMID $VMID already exists — delete it first or set VMID to a free id."
  exit 1
fi

# ── Cloud-init snippet (always created) ─────────────────────────────────────
# Even when virt-customize bakes in the agent, the snippet is harmless (idempotent).
# When SKIP_VIRT_CUSTOMIZE=1 it is the ONLY way the agent gets installed.
echo "→ Creating cloud-init vendor snippet: $SNIPPET_FILE"
mkdir -p "$SNIPPETS_DIR"
cat > "$SNIPPET_FILE" << 'EOF'
#cloud-config
packages:
  - qemu-guest-agent
runcmd:
  - systemctl enable qemu-guest-agent
  - systemctl start qemu-guest-agent
EOF
echo "   Snippet written."

# ── Optional: virt-customize to bake agent into disk ────────────────────────
IMPORT_IMG="$CLOUD_IMG"

if [[ "$SKIP_VIRT_CUSTOMIZE" != "1" ]]; then
  TMP_DIR=$(mktemp -d)
  trap 'rm -rf "$TMP_DIR"' EXIT
  WORK_IMG="$TMP_DIR/noble-cloudimg-work.qcow2"
  echo "→ Copying image to temp (sparse) …"
  cp --sparse=always "$CLOUD_IMG" "$WORK_IMG"

  if ! command -v virt-customize &>/dev/null; then
    echo "→ Installing libguestfs-tools (virt-customize) …"
    if ! apt-get update -qq; then
      echo ""
      echo "apt-get update failed — falling back to cloud-init snippet only."
      echo "qemu-guest-agent will be installed on first boot via $SNIPPET_FILE"
      echo ""
      SKIP_VIRT_CUSTOMIZE=1
    else
      if ! apt-get install -y libguestfs-tools; then
        echo "apt-get install libguestfs-tools failed — falling back to cloud-init snippet only."
        SKIP_VIRT_CUSTOMIZE=1
      fi
    fi
  fi

  if [[ "$SKIP_VIRT_CUSTOMIZE" != "1" ]]; then
    echo "→ Installing qemu-guest-agent into disk image (libguestfs)"
    export LIBGUESTFS_BACKEND=direct
    if ! virt-customize -a "$WORK_IMG" --install qemu-guest-agent; then
      echo "virt-customize failed — falling back to cloud-init snippet only."
      SKIP_VIRT_CUSTOMIZE=1
    else
      IMPORT_IMG="$WORK_IMG"
    fi
  fi
fi

# ── Create the VM template ───────────────────────────────────────────────────
echo "→ qm create $VMID ($NAME)"
qm create "$VMID" \
  --name "$NAME" \
  --memory 2048 \
  --cores 2 \
  --cpu host \
  --machine q35 \
  --bios ovmf \
  --net0 virtio,bridge=vmbr0 \
  --scsihw virtio-scsi-single \
  --agent enabled=1

qm set "$VMID" --efidisk0 "${STORAGE}:1,format=raw,efitype=4m,pre-enrolled-keys=0"

echo "→ qm importdisk"
qm importdisk "$VMID" "$IMPORT_IMG" "$STORAGE"

DISK="${STORAGE}:vm-${VMID}-disk-1"
qm set "$VMID" \
  --scsi0 "${DISK},discard=on,ssd=1" \
  --boot order=scsi0 \
  --ide2 "${STORAGE}:cloudinit"

# ── Attach the vendor snippet to the template ────────────────────────────────
# All VMs cloned from this template will inherit cicustom and get the agent
# installed automatically on first boot.
echo "→ Attaching cloud-init vendor snippet to template"
qm set "$VMID" --cicustom "vendor=local:snippets/qemu-agent.yaml"

echo "→ qm template"
qm template "$VMID"

echo ""
echo "════════════════════════════════════════════════════════"
echo " Done. Template VMID $VMID ($NAME) is ready."
echo " App OS key: ubuntu-24.04 → template $VMID"
echo ""
echo " qemu-guest-agent setup:"
if [[ "$SKIP_VIRT_CUSTOMIZE" == "1" ]]; then
  echo "  • NOT baked into disk (virt-customize skipped)"
  echo "  • Will be installed on first boot via cloud-init snippet"
else
  echo "  • Baked into disk via virt-customize"
  echo "  • Also set as cloud-init vendor snippet (idempotent fallback)"
fi
echo " Snippet: $SNIPPET_FILE"
echo " Proxmox will be able to fetch the VM IP after first boot completes."
echo "════════════════════════════════════════════════════════"
