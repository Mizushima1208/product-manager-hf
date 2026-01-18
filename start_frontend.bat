@echo off
echo Starting Receipt Manager Frontend...
cd /d "%~dp0frontend"

REM Start simple HTTP server
echo Frontend available at http://localhost:3000
python -m http.server 3000
