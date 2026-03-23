@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║   HVAC Enerji Yönetim Sistemi — Güvenli Güncelleme  ║
echo ╚══════════════════════════════════════════════════════╝
echo.

:: === ADIM 0: Yeni kod klasörü yolunu al ===
if "%~1"=="" (
    set /p KAYNAK="Yeni kod klasörünün yolunu girin (ör: E:\acibadem): "
) else (
    set "KAYNAK=%~1"
)

:: Sondaki \ varsa kaldır
if "!KAYNAK:~-1!"=="\" set "KAYNAK=!KAYNAK:~0,-1!"

if not exist "!KAYNAK!" (
    echo [HATA] Klasör bulunamadı: !KAYNAK!
    pause
    exit /b 1
)

:: === ADIM 1: Yedek klasörü oluştur ===
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value 2^>nul') do set "DT=%%I"
set "YEDEK=_yedek_!DT:~0,8!_!DT:~8,4!"

echo [1/5] Yedek klasörü: !YEDEK!\
mkdir "!YEDEK!" 2>nul

:: === ADIM 2: VERİ dosyalarını yedekle (SADECE VERİ, KOD DEĞİL) ===
echo [2/5] Kullanıcı verileri yedekleniyor...
set "SAYAC=0"

:: ─── Kök dizindeki veri dosyaları ───
for %%F in (energy_data.csv ml_training_data.json hvac_analysis_history.csv savings_training_data.json) do (
    if exist "%%F" (
        copy /Y "%%F" "!YEDEK!\%%F" >nul
        echo       ✓ %%F
        set /a SAYAC+=1
    )
)

:: ─── configs klasöründeki KULLANICI VERİLERİ (JSON ayarlar) ───
mkdir "!YEDEK!\configs" 2>nul
for %%F in (configs\hvac_settings.json configs\maintenance_cards.json configs\report_notifications.json configs\ml_forecast_model.pkl) do (
    if exist "%%F" (
        copy /Y "%%F" "!YEDEK!\%%F" >nul
        echo       ✓ %%F
        set /a SAYAC+=1
    )
)

:: ─── monthly_report klasöründeki SADECE VERİ dosyaları ───
:: NOT: .py dosyaları (kod) YEDEKLENMEZ — bunlar güncellenecek
mkdir "!YEDEK!\monthly_report" 2>nul
for %%F in (monthly_report\*.csv monthly_report\*.json) do (
    if exist "%%F" (
        copy /Y "%%F" "!YEDEK!\%%F" >nul
        echo       ✓ %%F
        set /a SAYAC+=1
    )
)

:: ─── Rapor çıktı klasörleri (tamamı veri) ───
for %%D in (daily_reports monthly_reports_summary) do (
    if exist "%%D" (
        xcopy /E /I /Y /Q "%%D" "!YEDEK!\%%D" >nul
        echo       ✓ %%D\
        set /a SAYAC+=1
    )
)



:: ─── static\outputs (analiz çıktıları) ───
if exist "static\outputs" (
    mkdir "!YEDEK!\static\outputs" 2>nul
    xcopy /E /I /Y /Q "static\outputs" "!YEDEK!\static\outputs" >nul
    echo       ✓ static\outputs\
    set /a SAYAC+=1
)

echo       → !SAYAC! öğe yedeklendi

:: === ADIM 3: YENİ KLASÖRÜN TAMAMINI KOPYALA ===
echo [3/5] Yeni sürüm kopyalanıyor (tüm dosyalar)...
xcopy /E /Y /Q "!KAYNAK!\*" "." >nul
echo       ✓ Tüm dosyalar kopyalandı

:: === ADIM 4: VERİYİ GERİ YÜKLE (SADECE VERİ DOSYALARI) ===
echo [4/5] Kullanıcı verileri geri yükleniyor...

:: ─── Kök veri dosyaları ───
for %%F in (energy_data.csv ml_training_data.json hvac_analysis_history.csv savings_training_data.json) do (
    if exist "!YEDEK!\%%F" (
        copy /Y "!YEDEK!\%%F" "%%F" >nul
        echo       ✓ %%F (geri yüklendi)
    )
)

:: ─── configs: sadece kullanıcı ayar dosyaları ───
for %%F in (configs\hvac_settings.json configs\maintenance_cards.json configs\report_notifications.json configs\ml_forecast_model.pkl) do (
    if exist "!YEDEK!\%%F" (
        copy /Y "!YEDEK!\%%F" "%%F" >nul
        echo       ✓ %%F (geri yüklendi)
    )
)

:: ─── monthly_report: sadece veri dosyaları (.csv, .json) ───
:: .py dosyaları GERİ YÜKLENMEZ — yeni kod kalır!
for %%F in (monthly_report\*.csv monthly_report\*.json) do (
    if exist "!YEDEK!\%%F" (
        copy /Y "!YEDEK!\%%F" "%%F" >nul
        echo       ✓ %%F (geri yüklendi)
    )
)

:: ─── Rapor çıktı klasörleri ───
for %%D in (daily_reports monthly_reports_summary) do (
    if exist "!YEDEK!\%%D" (
        xcopy /E /I /Y /Q "!YEDEK!\%%D" "%%D" >nul
        echo       ✓ %%D\ (geri yüklendi)
    )
)

:: ─── static\outputs ───
if exist "!YEDEK!\static\outputs" (
    xcopy /E /I /Y /Q "!YEDEK!\static\outputs" "static\outputs" >nul
    echo       ✓ static\outputs\ (geri yüklendi)
)



:: === ADIM 5: DOĞRULAMA RAPORU ===
echo [5/5] Doğrulama yapılıyor...
echo.

set "HATA=0"

:: Kritik KOD dosyası kontrolü
echo       ─────── Kod Dosyaları ───────
for %%F in (main_portal.py app_portal.py run_portal.py ai_progress.py daily_report.py monthly_summary_report.py location_manager.py) do (
    if exist "%%F" (
        echo       ✅ %%F — mevcut
    ) else (
        echo       ❌ %%F — EKSİK!
        set "HATA=1"
    )
)

:: monthly_report kod dosyaları kontrolü
for %%F in (monthly_report\pdf_generator.py monthly_report\savings_engine.py monthly_report\data_merger.py monthly_report\hvac_history.py monthly_report\yoy_analyzer.py monthly_report\forecast_engine.py) do (
    if exist "%%F" (
        echo       ✅ %%F — mevcut
    ) else (
        echo       ❌ %%F — EKSİK!
        set "HATA=1"
    )
)

:: Kritik klasör kontrolü
for %%D in (rules configs static .streamlit monthly_report fonts) do (
    if exist "%%D" (
        echo       ✅ %%D\ — mevcut
    ) else (
        echo       ❌ %%D\ — EKSİK!
        set "HATA=1"
    )
)

:: Font dosyaları kontrolü (PDF Türkçe karakter desteği)
echo       ─────── Font Dosyaları ───────
for %%F in (fonts\DejaVuSans.ttf fonts\DejaVuSans-Bold.ttf fonts\DejaVuSans-Oblique.ttf) do (
    if exist "%%F" (
        echo       ✅ %%F — mevcut
    ) else (
        echo       ⚠️ %%F — EKSİK (PDF Türkçe karakter sorunu olabilir)
    )
)

:: Korunan veri dosyaları kontrolü
echo       ─────── Korunan Veriler ───────
for %%F in (energy_data.csv ml_training_data.json hvac_analysis_history.csv) do (
    if exist "%%F" (
        echo       💾 %%F — korundu ✓
    ) else (
        echo       ⚠️  %%F — bulunamadı
    )
)
for %%F in (configs\hvac_settings.json configs\maintenance_cards.json configs\report_notifications.json) do (
    if exist "%%F" (
        echo       💾 %%F — korundu ✓
    ) else (
        echo       ⚠️  %%F — bulunamadı
    )
)
for %%D in (daily_reports monthly_reports_summary) do (
    if exist "%%D" (
        echo       💾 %%D\ — korundu ✓
    ) else (
        echo       ⚠️  %%D\ — bulunamadı
    )
)

echo.
if "!HATA!"=="1" (
    echo ╔══════════════════════════════════════════════════════╗
    echo ║   ⚠️  UYARI: Bazı dosyalar eksik!                   ║
    echo ║   USB klasöründe tüm dosyalar var mı kontrol edin.  ║
    echo ║   Yedek: !YEDEK!\                                   ║
    echo ╚══════════════════════════════════════════════════════╝
) else (
    echo ╔══════════════════════════════════════════════════════╗
    echo ║   ✅ GÜNCELLEME BAŞARILI!                            ║
    echo ║                                                      ║
    echo ║   • Tüm kod dosyaları güncellendi (.py)              ║
    echo ║   • Kullanıcı verileri korundu (.csv, .json)         ║
    echo ║   • monthly_report kodu güncellendi                  ║
    echo ║   • configs ayarları korundu                         ║
    echo ║                                                      ║
    echo ║   Yedek: !YEDEK!\                                   ║
    echo ╚══════════════════════════════════════════════════════╝
)
echo.
pause
