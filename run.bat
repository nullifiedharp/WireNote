@echo off
rem Run WireNote from source (no build needed). Drag an image onto this file to open it.
cd /d "%~dp0"
python -m pip show pillow >nul 2>nul || python -m pip install -r requirements.txt
start "" pythonw wirenote.py %*
