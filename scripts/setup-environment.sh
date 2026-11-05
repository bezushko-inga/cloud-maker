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
    gcc \
    prometheus \
    ca-certificates \
    curl \
    gnupg

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
    pyyaml \
    prometheus-client \
    httpx

sudo install -d -m 0755 /etc/apt/keyrings

curl -fsSL https://apt.grafana.com/gpg.key \
    | sudo gpg --dearmor --yes \
        -o /etc/apt/keyrings/grafana.gpg

sudo chmod 644 /etc/apt/keyrings/grafana.gpg

echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" \
    | sudo tee /etc/apt/sources.list.d/grafana.list > /dev/null

sudo apt update
sudo apt install -y grafana

sudo systemctl enable --now prometheus
sudo systemctl enable --now grafana-server