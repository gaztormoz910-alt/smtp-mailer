#!/bin/bash
# SMTP MAILER — macOS / Linux launcher
# Usage: chmod +x start.command && ./start.command

echo "============================================"
echo "  SMTP MAILER — Launcher"
echo "============================================"
echo ""

# cd to script directory (fixes relative paths)
cd "$(dirname "$0")" || exit 1

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 not found!"
    echo "Install Python from https://python.org"
    exit 1
fi

echo "[*] Installing dependencies..."
pip3 install -r requirements.txt --quiet 2>/dev/null || pip install -r requirements.txt --quiet

echo ""
echo "[*] Starting SMTP MAILER..."
python3 main.py
