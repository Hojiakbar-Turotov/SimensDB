@echo off
title Siemens Altea & Fuji DryPix 2000 Spooler Server
color 0b
echo ============================================================
echo   RESPUBLIKA ONKOLOGIYA MARKAZI RADIODIAGNOSTIKA BO'LIMI
echo   Siemens Altea Spooler, DryPix 2000 & 6-Diskovod Tizimi
echo ============================================================
echo.
echo Server ishga tushirilmoqda...
cd /d %~dp0
start http://localhost:3000
node src/server.js
pause
