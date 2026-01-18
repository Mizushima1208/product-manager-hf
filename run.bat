@echo off
chcp 65001 > nul
echo 🧾 領収書管理システムを起動中...
cd /d "%~dp0backend"
start "" http://localhost:8000
.venv\Scripts\python.exe -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
