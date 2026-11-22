#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
echo "==================================================="
echo " Tokyo Ariake Arena Flight Tracker (Local Server)"
echo " URL: http://localhost:8000"
echo " 종료: Ctrl + C"
echo "==================================================="
(sleep 1 && (open "http://localhost:8000" 2>/dev/null || xdg-open "http://localhost:8000" 2>/dev/null || true)) &
python3 -m http.server 8000
