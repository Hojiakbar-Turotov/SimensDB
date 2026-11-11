@echo off
title Siemens Altea & Fuji DryPix 2000 Spooler Server (Port 1005)
color 0b
cd /d %~dp0
echo ============================================================
echo   RESPUBLIKA ONKOLOGIYA VA RADIOLOGIYA MARKAZI
echo   Siemens Altea DICOM Spooler & Fuji DryPix 2000 Driver
echo ============================================================
echo.
echo [*] Server ishga tushirilmoqda...
echo [*] Qabul porti: 1005 (10.34.14.33:1005)
echo [*] Fuji Printer: 10.34.14.12:104 (DRYPIX2)
echo [*] Veb boshqaruv: http://localhost:3000
echo.
Siemens_Fuji_DICOM_Print_Server.exe
pause
