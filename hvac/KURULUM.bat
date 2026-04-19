@echo off
chcp 65001 >nul
title ACIBADEM Portal Kurulum
color 0B

echo.
echo ====================================================
echo    ACIBADEM HVAC ^& ENERJI PORTAL - KURULUM
echo ====================================================
echo.

REM Python kontrolu
python --version >nul 2>&1
if errorlevel 1 (
    echo [HATA] Python bulunamadi!
    echo.
    echo Python'u indirin: https://www.python.org/downloads/
    echo Kurulumda "Add Python to PATH" secenegini isaretleyin.
    echo.
    pause
    exit /b 1
)

echo [OK] Python bulundu.
echo.

REM Proje klasorune git
cd /d "%~dp0"
cd deneme

echo Gerekli kutuphaneler yukleniyor...
echo.

REM pip guncelle
python -m pip install --upgrade pip --quiet

REM Kutuphaneleri yukle (Eklenen: scikit-learn, numpy, kaleido, xlsxwriter, supabase)
pip install streamlit pandas plotly openpyxl xlrd fastapi uvicorn fpdf2 python-multipart kaleido scikit-learn numpy xlsxwriter supabase --quiet

if errorlevel 1 (
    echo [HATA] Kutuphane yukleme basarisiz!
    pause
    exit /b 1
)

echo.
echo [OK] Tum kutuphaneler yuklendi!
echo.

REM Masaustu kisayolu olustur
echo Masaustu kisayolu olusturuluyor...
echo.

set DESKTOP=%USERPROFILE%\Desktop
set SHORTCUT_NAME=HVAC Portal.lnk
set BAT_PATH=%~dp0PORTAL_BASLAT.bat

powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%DESKTOP%\%SHORTCUT_NAME%'); $SC.TargetPath = '%BAT_PATH%'; $SC.WorkingDirectory = '%~dp0'; $SC.IconLocation = 'shell32.dll,21'; $SC.Description = 'HVAC ve Enerji Portal Sistemi'; $SC.Save()"

if exist "%DESKTOP%\%SHORTCUT_NAME%" (
    echo [OK] Masaustu kisayolu olusturuldu!
) else (
    echo [UYARI] Kisayol olusturulamadi, manuel ekleyebilirsiniz.
)

echo.
echo ====================================================
echo    KURULUM TAMAMLANDI!
echo ====================================================
echo.
echo Masaustundeki "HVAC Portal" ikonuna cift tiklayarak
echo sistemi baslatabilirsiniz.
echo.
echo ====================================================
echo.
pause
