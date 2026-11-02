@echo off
chcp 65001 >nul
title Sebeke Sayaci Denemesi (PAC3200 192.168.1.15)
cd /d "%~dp0"
REM Yalnizca OKUR, sayaca yazmaz. Ctrl+C ile durur.
REM Sonuc: bu klasorde sebeke_deneme_<tarih>.csv
python sebeke_deneme.py %*
