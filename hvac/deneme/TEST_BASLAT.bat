@echo off
chcp 65001 >nul
title Mekanik Zeka - TEST (sahte saha verisi)
color 0E

REM ====================================================================
REM  SADECE GELISTIRME MAKINESI ICIN.
REM  Mekanik Zeka portalini ve sahte saha sunucusunu BIRLIKTE baslatir.
REM  Lokasyon yamalarina EKLENMEZ; sahada supabase_config.json gorulurse
REM  simulasyon zaten calismayi reddeder.
REM
REM  Mevsim degistirmek icin asagidaki satirda kis / yaz / ara yazin:
REM     kis = isitma senaryosu (kazanlar calisir)
REM     yaz = sogutma senaryosu (chiller'lar calisir)
REM     ara = ikisi ayni anda
REM ====================================================================
set MEVSIM=kis

cd /d "%~dp0"

echo.
echo ====================================================
echo    MEKANIK ZEKA - TEST ORTAMI (%MEVSIM%)
echo ====================================================
echo.
echo  Portal + sahte saha verisi baslatiliyor...
echo  Ekran: http://localhost:8005/hvac
echo  Durdurmak icin bu pencerede Ctrl+C.
echo.

timeout /t 6 /nobreak >nul
start "" "http://localhost:8005/hvac"

python simulasyon_sunucu.py --portal-ile --mevsim %MEVSIM%

echo.
echo Test ortami durduruldu.
pause
