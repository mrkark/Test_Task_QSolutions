#!/usr/bin/env bash
set -e

echo "===================================================="
echo "Starting Browser Automation Video Recorder"
echo "===================================================="

if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 could not be found. Please install Python 3.9+"
    exit 1
fi

echo "[1/3] Checking and installing dependencies..."
python3 -m pip install -r requirements.txt

echo "[2/3] Ensuring Playwright Chromium is installed..."
python3 -m playwright install chromium

echo "[3/3] Running automation recorder..."
python3 capture_video.py "$@"

echo "===================================================="
echo "Finished! Videos saved in ./video"
echo "===================================================="
