#!/bin/bash
set -e

VM_NAME="vm"
MEMORY=2048
VCPUS=2
DISK_SIZE="10G"

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
trap 'rm -f "$PROJECT_DIR/seed.iso" "${BASE_IMAGE}.tmp"' EXIT

BASE_IMAGE="$PROJECT_DIR/noble-server-cloudimg-amd64.img"
VM_DISK="/var/lib/libvirt/images/${VM_NAME}.qcow2"
SEED_ISO="/var/lib/libvirt/images/${VM_NAME}-seed.iso"


sudo virsh -c qemu:///system list --all >/dev/null

if sudo virsh -c qemu:///system dominfo "$VM_NAME" >/dev/null 2>&1; then
    echo "VM already exists: $VM_NAME"
    exit 1
fi

if sudo test -e "$VM_DISK" || sudo test -e "$SEED_ISO"; then
    echo "VM disk or Cloud-init ISO already exists"
    exit 1
fi

if [ "$(sudo virsh -c qemu:///system net-info default | awk '/Active:/ {print $2}')" != "yes" ]; then
    sudo virsh -c qemu:///system net-start default
fi

if [ ! -f "$BASE_IMAGE" ]; then
    wget -O "${BASE_IMAGE}.tmp" \
        "https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img"
    mv "${BASE_IMAGE}.tmp" "$BASE_IMAGE"
fi


cloud-localds \
    "$PROJECT_DIR/seed.iso" \
    "$PROJECT_DIR/cloud-init/user-data" \
    "$PROJECT_DIR/cloud-init/meta-data"

sudo cp "$BASE_IMAGE" "$VM_DISK"
sudo qemu-img resize "$VM_DISK" "$DISK_SIZE"
sudo cp "$PROJECT_DIR/seed.iso" "$SEED_ISO"

sudo virt-install \
    --connect qemu:///system \
    --name "$VM_NAME" \
    --memory "$MEMORY" \
    --vcpus "$VCPUS" \
    --import \
    --disk "path=$VM_DISK,format=qcow2" \
    --disk "path=$SEED_ISO,device=cdrom" \
    --os-variant ubuntu24.04 \
    --network network=default \
    --graphics none \
    --console pty,target_type=serial \
    --noautoconsole


echo "VM $VM_NAME created successfully"
