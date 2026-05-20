@echo off
:: HVAC Enerji Portalı — Otomatik Başlatma
:: Bu dosya Windows Görev Zamanlayıcısı tarafından PC açılışında çalıştırılır.
:: Doğrudan çift tıklayarak da başlatılabilir.

title HVAC Enerji Portali - Baslatiliyor...

:: Programın bulunduğu klasöre geç
cd /d "%~dp0"

:: Python'un nerede olduğunu bul
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [HATA] Python bulunamadi! PATH kontrolu yapiniz.
    pause
    exit /b 1
)

:: Kısa bekleme — ağ ve sistem servislerinin hazır olması için
timeout /t 15 /nobreak >nul

echo [%date% %time%] HVAC Portali baslatiliyor...

:: Portalı arka planda başlat (pencere gizli)
start "" /min python run_portal.py

echo [%date% %time%] Portal baslatildi.
