#!/bin/bash

echo "============================================"
echo "  Pinion — Launcher"
echo "============================================"
echo ""

cd "$(dirname "$0")" || exit 1

if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 not found!"
    echo "Install Python from https://python.org"
    exit 1
fi

echo "[*] Installing dependencies..."
pip3 install -r requirements.txt --quiet 2>/dev/null || pip install -r requirements.txt --quiet

echo ""
echo "[*] Starting Pinion..."
python3 main.py
