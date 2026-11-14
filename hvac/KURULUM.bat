@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
title ACIBADEM Portal Kurulum
color 0B
echo.
echo ====================================================
echo    ACIBADEM HVAC ^& ENERJI PORTAL - KURULUM
echo ====================================================
echo.
REM Sira (12.11.2026): Python - kutuphaneler - lokasyon kimligi - merkez baglantisi -
REM merkezden geri yukleme - sablon (yalniz eksikler) - lisans / kontrol - kisayol, otomatik baslatma.
REM Geri yukleme sablondan ONCE: yeni PC'de ayarlar merkezdeki son halden gelir (PC arizasi);
REM yeni lokasyonda merkezde kayit yoktur, ayarlar sablondan gelir. Hicbir adim var olan ayari ezmez.

REM ---[1/7] Python -------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    REM Internetsiz kurulum paketi Python yukleyicisini de tasir (kurulum_paketi.py --python-yukleyici)
    for %%P in ("%~dp0python-*.exe") do (
        echo [BILGI] Python yuklu degil - paketteki yukleyici calistiriliyor: %%~nxP
        echo         ^(yonetici yetkisi gerekir^)
        "%%~fP" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
        echo.
        echo [OK] Python yuklendi. Bu pencereyi kapatip KURULUM.bat'i YENIDEN calistirin
        echo      ^(yeni PATH ancak yeni pencerede gecerli olur^).
        pause
        exit /b 0
    )
    echo [HATA] Python bulunamadi ve pakette yukleyici yok!
    echo.
    echo Lokasyonda internet yoksa python-3.x-amd64.exe dosyasini bu klasore koyun.
    echo Kurulumda "Add Python to PATH" secenegini isaretleyin.
    echo.
    pause
    exit /b 1
)
echo [1/7] Python bulundu.

cd /d "%~dp0"
cd deneme

REM ---[2/7] Kutuphaneler --------------------------------------------
REM Bu dosyanin yaninda "paketler" klasoru varsa kurulum INTERNETSIZ yapilir. Liste: requirements.txt
echo [2/7] Kutuphaneler yukleniyor...
if exist "%~dp0paketler\" (
    python -m pip install --no-index --find-links "%~dp0paketler" --upgrade pip --quiet
    python -m pip install --no-index --find-links "%~dp0paketler" -r "%~dp0requirements.txt"
) else (
    python -m pip install --upgrade pip --quiet
    python -m pip install -r "%~dp0requirements.txt" --quiet
)
if errorlevel 1 (
    echo [HATA] Kutuphane yukleme basarisiz!
    pause
    exit /b 1
)
echo [OK] Kutuphaneler yuklendi.
echo.

REM ---[3/7] Lokasyon kimligi ----------------------------------------
set "LOK="
for /f "usebackq delims=" %%L in (`python -c "import json,yollar;print(json.load(open(yollar.yol('configs/lokasyon_profili.json','.'),encoding='utf-8-sig')).get('lokasyon_id',''))" 2^>nul`) do set "LOK=%%L"
if not defined LOK if exist "%~dp0lokasyon.txt" set /p LOK=<"%~dp0lokasyon.txt"
if not defined LOK set /p LOK="[3/7] Lokasyon kimligi (or. atasehir): "
if not defined LOK (
    echo [HATA] Lokasyon kimligi gerekli.
    pause
    exit /b 1
)
echo [3/7] Lokasyon: !LOK!
echo.

REM ---[4/7] Merkez baglantisi ---------------------------------------
REM Baglanti dosyasi ve lokasyon anahtari pakette YOKTUR (paket kimlik dogrulamasiz indirilir);
REM merkezden ayrica alinir ve elle konur.
set "BAGLI="
:baglanti
if exist "ayar\supabase_config.json" set "BAGLI=1"
if exist "configs\supabase_config.json" set "BAGLI=1"
if defined BAGLI goto baglanti_var
echo [4/7] Merkez baglanti dosyasi bulunamadi. Su konuma koyun:
echo         %CD%\ayar\supabase_config.json
echo       Lokasyon anahtari da varsa:
echo         %CD%\ayar\lokasyon_anahtari.json
if not exist "ayar" mkdir "ayar"
choice /c DA /n /m "      Koydunuz mu? [D]evam (tekrar bak) / [A]tla (merkezsiz kurulum): "
if errorlevel 2 goto baglanti_yok
goto baglanti
:baglanti_var
echo [4/7] Merkez baglanti dosyasi var.
if not exist "ayar\lokasyon_anahtari.json" if not exist "configs\lokasyon_anahtari.json" echo [UYARI] Lokasyon anahtari yok - ortak anahtarla baglanilir.
:baglanti_yok
echo.

REM ---[5/7] Merkezden geri yukleme -----------------------------------
REM Ayarlar, enerji gecmisi, bakim kartlari. Var olan dosyanin uzerine YAZMAZ.
if defined BAGLI (
    echo [5/7] Merkezdeki kopya kontrol ediliyor ^(ayarlar, enerji gecmisi, bakim kartlari^)...
    python geri_yukle.py --lokasyon "!LOK!" --uygula
    if errorlevel 1 echo [UYARI] Merkezden geri yukleme yapilamadi - ayarlar sablondan gelecek.
) else (
    echo [5/7] Merkez baglantisi yok - geri yukleme atlandi.
)
echo.

REM ---[6/7] Profil, sablon, lisans ve kontrol ------------------------
set "LOKAD="
if not exist "ayar\lokasyon_profili.json" if not exist "configs\lokasyon_profili.json" set /p LOKAD="[6/7] Lokasyon adi (or. Acibadem Atasehir): "
python kurulum_kontrol.py --ilk --lokasyon "!LOK!" --ad "!LOKAD!" --agentsiz
echo.

REM ---[7/7] Kisayollar ------------------------------------------------
set "DESKTOP=%USERPROFILE%\Desktop"
set "SHORTCUT_NAME=HVAC Portal.lnk"
set "BAT_PATH=%~dp0PORTAL_BASLAT.bat"
powershell -NoProfile -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%DESKTOP%\%SHORTCUT_NAME%'); $SC.TargetPath = '%BAT_PATH%'; $SC.WorkingDirectory = '%~dp0'; $SC.IconLocation = 'shell32.dll,21'; $SC.Description = 'HVAC ve Enerji Portal Sistemi'; $SC.Save()"
if exist "%DESKTOP%\%SHORTCUT_NAME%" (
    echo [7/7] Masaustu kisayolu olusturuldu.
) else (
    echo [UYARI] Masaustu kisayolu olusturulamadi, elle ekleyebilirsiniz.
)
REM Otomatik baslatma: kullanicinin Baslangic klasorune kisayol. Program ikinci kez baslarsa
REM watchdog bunu fark edip kapanir (tek kopya), yani baska bir baslatma yolu varsa zarar vermez.
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
if exist "%STARTUP%\%SHORTCUT_NAME%" (
    echo [7/7] Otomatik baslatma zaten tanimli.
) else (
    choice /c EH /n /m "      Bilgisayar acilinca program otomatik baslasin mi? [E]vet / [H]ayir: "
    if not errorlevel 2 (
        powershell -NoProfile -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%STARTUP%\%SHORTCUT_NAME%'); $SC.TargetPath = '%BAT_PATH%'; $SC.WorkingDirectory = '%~dp0'; $SC.IconLocation = 'shell32.dll,21'; $SC.Description = 'HVAC ve Enerji Portal Sistemi'; $SC.Save()"
        if exist "%STARTUP%\%SHORTCUT_NAME%" (echo [7/7] Otomatik baslatma eklendi.) else (echo [UYARI] Otomatik baslatma eklenemedi.)
    )
)
echo.
echo ====================================================
echo    KURULUM TAMAMLANDI
echo ====================================================
echo.
choice /c EH /n /m "Program simdi baslatilsin ve ilk gun kontrolu yapilsin mi? [E]vet / [H]ayir: "
if errorlevel 2 goto son
start "HVAC Portal" "%BAT_PATH%"
python kurulum_kontrol.py --bekle 240
:son
echo.
echo Masaustundeki "HVAC Portal" ikonuyla sistemi baslatabilirsiniz.
echo Sonuc: deneme\durum\kurulum_kontrol.json
echo.
pause
