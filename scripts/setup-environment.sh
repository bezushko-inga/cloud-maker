#!/bin/bash
set -e

cd "$(dirname "$0")/.."

sudo apt update
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-libvirt \
    libvirt-dev \
    pkg-config \
    gcc

if [ ! -d ".venv" ]; then
    python3 -m venv --system-site-packages .venv
fi

source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install \
    fastapi \
    "uvicorn[standard]" \
    pydantic \
    requests \
    pytest \
    pyyaml
