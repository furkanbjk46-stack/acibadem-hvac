@echo off
echo BACnet Tani - Yonetici olarak calistiriliyor...
cd /d "%~dp0"
powershell -Command "Start-Process python -ArgumentList 'bacnet_tani.py' -Verb RunAs -Wait"
pause
