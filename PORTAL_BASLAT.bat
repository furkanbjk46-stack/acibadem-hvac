@echo off
chcp 65001 >nul
title HVAC & Enerji Portal Launcher
color 0A

echo.
echo ====================================================
echo    ACIBADEM HVAC ^& ENERJI PORTAL SISTEMI
echo ====================================================
echo.
echo Sunucular baslatiliyor...
echo.

cd /d "%~dp0"
cd acıbadem

REM Enerji Portal (Streamlit) baslatiliyor
echo [1/2] Enerji Portal baslatiliyor (Port 8501)...
start /min cmd /c "streamlit run app_portal.py --server.port 8501 --server.headless true"

REM HVAC Portal (FastAPI) baslatiliyor - 127.0.0.1:8005
echo [2/2] HVAC Portal baslatiliyor (Port 8005)...
start /min cmd /c "uvicorn main_portal:app --host 127.0.0.1 --port 8005"

echo.
echo Sunucular baslatildi! Tarayici aciliyor...
echo 5 saniye bekleniyor...
echo.

REM 5 saniye bekle
timeout /t 5 /nobreak > nul

REM Varsayilan tarayicida ac
start "" "http://127.0.0.1:8005"

echo.
echo ====================================================
echo    PORTAL ADRESLERI
echo ====================================================
echo.
echo    HVAC Portal:   http://127.0.0.1:8005
echo    Enerji Portal: http://localhost:8501
echo.
echo ====================================================
echo.
echo Bu pencereyi kapatmayin! Kapatirsaniz sunucular durur.
echo.
pause
