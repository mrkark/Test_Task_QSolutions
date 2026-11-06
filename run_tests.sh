#!/usr/bin/env bash
set -e

echo "===================================================="
echo " Running Unit Tests for Web Service and API"
echo "===================================================="

if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 could not be found."
    exit 1
fi

python3 test_service.py -v

echo "===================================================="
echo " Tests finished."
echo "===================================================="
