@echo off
chcp 65001 >nul
title Acibadem Genel Merkez Portal
color 0D

echo.
echo ====================================================
echo    ACIBADEM GENEL MERKEZ PORTAL
echo ====================================================
echo.
echo Merkez Dashboard baslatiliyor...
echo.

cd /d "%~dp0"
cd merkez

streamlit run app_merkez.py --server.port 8601 --server.headless true

echo.
echo ====================================================
echo    MERKEZ PORTAL ADRESI
echo ====================================================
echo.
echo    Dashboard: http://localhost:8601
echo.
echo ====================================================
echo.
echo Bu pencereyi kapatmayin! Kapatirsaniz portal durur.
echo.
pause
