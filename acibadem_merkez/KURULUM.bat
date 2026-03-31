@echo off
chcp 65001 >nul
title ACIBADEM Genel Merkez Kurulum
color 0D

echo.
echo ====================================================
echo    ACIBADEM GENEL MERKEZ - KURULUM
echo ====================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [HATA] Python bulunamadi!
    echo Python'u indirin: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [OK] Python bulundu.
echo.

cd /d "%~dp0"
cd merkez

echo Gerekli kutuphaneler yukleniyor...
python -m pip install --upgrade pip --quiet
pip install streamlit pandas plotly supabase --quiet

if errorlevel 1 (
    echo [HATA] Kutuphane yukleme basarisiz!
    pause
    exit /b 1
)

echo.
echo [OK] Tum kutuphaneler yuklendi!
echo.

set DESKTOP=%USERPROFILE%\Desktop
set SHORTCUT_NAME=Merkez Portal.lnk
set BAT_PATH=%~dp0PORTAL_BASLAT.bat

powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%DESKTOP%\%SHORTCUT_NAME%'); $SC.TargetPath = '%BAT_PATH%'; $SC.WorkingDirectory = '%~dp0'; $SC.IconLocation = 'shell32.dll,43'; $SC.Description = 'Acibadem Genel Merkez Portal'; $SC.Save()"

echo.
echo ====================================================
echo    KURULUM TAMAMLANDI!
echo ====================================================
echo.
echo Masaustundeki "Merkez Portal" ikonuna cift tiklayarak
echo sistemi baslatabilirsiniz.
echo.
pause
