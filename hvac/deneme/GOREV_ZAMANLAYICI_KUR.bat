@echo off
:: HVAC Enerji Portalı — Windows Görev Zamanlayıcısı Kurulum
:: Yönetici olarak çalıştırın (sağ tık → Yönetici olarak çalıştır)

title Gorev Zamanlayici Kurulumu

echo ============================================================
echo   HVAC Enerji Portali - Otomatik Baslama Kurulumu
echo ============================================================
echo.

:: Bu bat dosyasının tam yolunu al
set BAT_YOLU=%~dp0OTOMATIK_BASLAT.bat

:: Görev adı
set GOREV_ADI=HVAC_Enerji_Portali

echo Gorev adi  : %GOREV_ADI%
echo Bat dosyasi: %BAT_YOLU%
echo.

:: Eski görevi sil (varsa hata vermesin)
schtasks /delete /tn "%GOREV_ADI%" /f >nul 2>&1

:: Yeni görevi oluştur:
::   /SC ONSTART = PC açılışında
::   /DELAY PT30S = 30 saniye gecikme (ağ hazır olsun)
::   /RU SYSTEM  = Sistem hesabıyla çalıştır (oturum açmadan da çalışır)
::   /RL HIGHEST = Yönetici yetkisi
::   /F          = Zorla oluştur
schtasks /create ^
    /tn "%GOREV_ADI%" ^
    /tr "\"%BAT_YOLU%\"" ^
    /sc ONSTART ^
    /delay 0000:30 ^
    /ru SYSTEM ^
    /rl HIGHEST ^
    /f

if %errorlevel% equ 0 (
    echo.
    echo [BASARILI] Gorev zamanlayici kuruldu!
    echo PC her acildiginda HVAC portali otomatik baslatilacak.
    echo.
    echo Kontrol etmek icin: Gorev Zamanlayicisi arac alin,
    echo "%GOREV_ADI%" gorevini Gorev Zamanlayicisi Kutuphanesi altinda bulun.
) else (
    echo.
    echo [HATA] Kurulum basarisiz! Sag tik - Yonetici olarak calistir deneyin.
)

echo.
pause
