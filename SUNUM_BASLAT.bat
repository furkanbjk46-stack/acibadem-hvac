@echo off
title SYNAPSE - Sunum / Simulasyon Modu
cd /d "%~dp0"

REM ==========================================================
REM  SYNAPSE - SUNUM MODU
REM  21 hastanenin tamami entegre olmus gibi calisir.
REM  ORNEK VERI kullanilir; canli sisteme HICBIR istek gitmez.
REM
REM  NOT: Bu dosya SAF ASCII olmalidir. Turkce karakter veya
REM  kutu cizgisi (unicode) konursa batch ayristiricisi satiri
REM  boler ve "... is not recognized" hatalari verir.
REM ==========================================================

echo.
echo ==========================================================
echo   SYNAPSE - SUNUM MODU
echo   21 hastane entegre gibi calisir - ORNEK VERI
echo   Canli sisteme hicbir istek gitmez.
echo ==========================================================
echo.

REM --- Python bul -------------------------------------------
REM Aday sirayla DENENIR, sadece varligina bakilmaz: Windows'ta "python"
REM cogu zaman Microsoft Store kisayoluna cikar ve calismaz. Ayrica yolda
REM bosluk varsa deger TIRNAKLI saklanmalidir, yoksa "-m taninmiyor" hatasi olur.
set "PYCMD="

call :dene "py -3"
if defined PYCMD goto :python_bulundu
call :dene "python"
if defined PYCMD goto :python_bulundu
call :dene ""D:\Program Files (x86)\python.exe""
if defined PYCMD goto :python_bulundu

echo [HATA] Calisan bir Python bulunamadi.
echo        python.org adresinden kurun veya D: surucusunu takin.
echo.
pause
exit /b 1

:dene
if defined PYCMD goto :eof
%~1 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PYCMD=%~1"
goto :eof

:python_bulundu
echo Python: %PYCMD%

REM --- Sunum ayarlari ---------------------------------------
REM Portal bu adres sayesinde canli Supabase yerine yerel sunucuya baglanir.
set "SYNAPSE_SIM_URL=http://127.0.0.1:8099"
set "SYNAPSE_SIM_KEY=simulasyon"

REM Sunum girisi:  kullanici = acibadem   parola = sunum2026
set "SYNAPSE_GIRIS_KULLANICI=acibadem"
set "SYNAPSE_GIRIS_PAROLA_HASH=pbkdf2_sha256$200000$e107cd6db1fd1bfa079dbe8784e9d46b$c2e2fb7dbfc9617b2bb1527d6633af85ce50326adc176048872c74a61c046dc7"

echo [1/2] Simulasyon sunucusu baslatiliyor (port 8099)...
start "SYNAPSE Simulasyon Sunucusu" /min cmd /c %PYCMD% "merkez\_sim_sunucu.py" --port 8099

REM timeout yonlendirme altinda calismiyor; ping ile bekleniyor
ping -n 5 127.0.0.1 >nul

echo [2/2] Portal baslatiliyor (port 8600)...
echo.
echo   Tarayici birazdan acilacak.
echo   Giris:  acibadem  /  sunum2026
echo   Kapatmak icin bu pencereyi kapatin.
echo.

start "" http://localhost:8600
%PYCMD% -m streamlit run "merkez\app_merkez.py" --server.port 8600 --server.headless true --browser.gatherUsageStats false

pause
