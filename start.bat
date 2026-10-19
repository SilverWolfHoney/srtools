@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo SRTools 4.6.53 - http://127.0.0.1:21100
python serve.py
pause
