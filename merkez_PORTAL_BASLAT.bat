@echo off
chcp 65001 >nul
title Acibadem Genel Merkez Portal
color 0D

echo.
echo ====================================================
echo    ACIBADEM GENEL MERKEZ PORTAL
echo ====================================================
echo.
echo Merkez Dashboard baslatiliyor...
cd /d "%~dp0"
if exist "merkez\app_merkez.py" (
    cd merkez
)

REM Merkez Portal (Streamlit) baslatiliyor
echo [1/1] Merkez Portal baslatiliyor (Port 8601)...
echo.
echo Sunucu baslatildi! Tarayici aciliyor...
echo 5 saniye bekleniyor...
echo.

REM 5 saniye bekle, sonra tarayiciyi ac
timeout /t 5 /nobreak > nul

REM Varsayilan tarayicida ac
start "" "http://localhost:8601"

streamlit run app_merkez.py --server.port 8601 --server.headless true

echo.
echo ====================================================
echo    MERKEZ PORTAL ADRESI
echo ====================================================
echo.
echo    Dashboard: http://localhost:8601
echo.
echo ====================================================
echo.
echo Bu pencereyi kapatmayin! Kapatirsaniz portal durur.
echo.
pause
