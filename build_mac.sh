#!/bin/bash
# build_mac.sh — builds ENGR_Scheduler.app on macOS
# Run from the folder containing all project files.

echo "Installing dependencies..."
pip install pyinstaller ortools PySide6 plotly

echo "Building app..."
pyinstaller ENGR_Scheduler.spec

echo ""
echo "Done! Your app is at: dist/ENGR_Scheduler.app"
echo "To distribute: zip the dist/ENGR_Scheduler.app folder and share it."
