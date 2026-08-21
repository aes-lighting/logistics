@echo off
title AES Logistics Launcher
color 0A

echo ==========================================
echo   AES Logistics - Starting Up
echo ==========================================
echo.
echo This window will show your test link in a moment.
echo Keep this window open the whole time you're testing.
echo Close it when you're done to stop the server.
echo.

REM --- Edit this path if your project folder has a different name ---
wsl -e bash -lc "cd ~/aes_logistics_latest && bash start.sh"

echo.
echo Server stopped.
pause
