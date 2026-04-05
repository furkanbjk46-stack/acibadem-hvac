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
cd deneme

echo Tarayici aciliyor (5 saniye bekleniyor)...
timeout /t 5 /nobreak > nul
start "" "http://127.0.0.1:8005"

echo.
echo ====================================================
echo    PORTAL ADRESLERI
echo ====================================================
echo.
echo    HVAC Portal:   http://127.0.0.1:8005
echo    Enerji Portal: http://localhost:8501
echo.
echo    Uzaktan guncelleme alindiktan sonra sistem
echo    otomatik olarak yeniden baslatilacak.
echo.
echo ====================================================
echo.
echo Bu pencereyi kapatmayin! Kapatirsaniz sunucular durur.
echo.

REM Python kontrolu
python --version >nul 2>&1
if errorlevel 1 (
    echo [HATA] Python bulunamadi! Lutfen KURULUM.bat calistirin.
    pause
    exit /b 1
)

REM portal_watchdog.py var mi?
if not exist "portal_watchdog.py" (
    echo [HATA] portal_watchdog.py bulunamadi!
    echo Bulunulan klasor:
    cd
    echo Klasor icerigi:
    dir *.py
    pause
    exit /b 1
)

REM Watchdog portalları başlatır ve güncelleme sonrası yeniden başlatır
python portal_watchdog.py
if errorlevel 1 (
    echo.
    echo [HATA] Portal baslatma basarisiz oldu!
    pause
)
