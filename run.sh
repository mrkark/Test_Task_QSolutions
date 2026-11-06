#!/usr/bin/env bash
set -e

echo "===================================================="
echo " QSolutions Browser Automation & Web Service"
echo "===================================================="

if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 could not be found. Please install Python 3.9+"
    exit 1
fi

echo "[1/2] Checking and installing dependencies..."
python3 -m pip install -r requirements.txt > /dev/null 2>&1 || python3 -m pip install -r requirements.txt

echo "[2/2] Ensuring Playwright Chromium is installed..."
python3 -m playwright install chromium

if [ "$#" -gt 0 ]; then
    echo "[RUN] Executing capture_video.py with arguments: $@"
    python3 capture_video.py "$@"
    exit 0
fi

echo ""
echo "===================================================="
echo " Select Run Mode:"
echo "===================================================="
echo " [1] Full Pipeline (Auto-start server + record + upload + preview)"
echo " [2] Web Service Dashboard (Start server at http://127.0.0.1:8000)"
echo " [3] Video Recorder Only (Task 1 local recording)"
echo " [4] Run Unit Tests (Task 2 API verification with server responses)"
echo " [5] Exit"
echo "===================================================="
read -p "Enter option [1-5] (default: 1): " choice
choice=${choice:-1}

case "$choice" in
    1)
        echo "[INFO] Running full pipeline..."
        python3 capture_video.py --auto-server --view-seconds 5
        ;;
    2)
        echo "[INFO] Starting web service dashboard on http://127.0.0.1:8000 ..."
        python3 web_service.py
        ;;
    3)
        echo "[INFO] Running video recorder only..."
        python3 capture_video.py
        ;;
    4)
        echo "[INFO] Running unit tests with server response logs..."
        python3 test_service.py -v
        ;;
    5)
        echo "Exiting."
        exit 0
        ;;
    *)
        echo "Invalid selection."
        exit 1
        ;;
esac

echo "===================================================="
echo "Execution finished."
echo "===================================================="
