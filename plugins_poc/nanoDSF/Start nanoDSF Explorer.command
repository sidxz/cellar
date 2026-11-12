#!/bin/bash
# Double-click this file to open nanoDSF Explorer in your web browser.
# Keep this window open while you use the app; close it to stop the app.
cd "$(dirname "$0")"
echo "Starting nanoDSF Explorer… (your browser will open in a few seconds)"
echo "Leave this window open while you use the app. Close it when you're done."
"$HOME/.local/bin/uv" run streamlit run app.py --server.port 8502 --browser.gatherUsageStats false
