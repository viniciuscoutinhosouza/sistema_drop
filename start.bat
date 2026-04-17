@echo off
title MIG ECOMMERCE

echo ============================================
echo   MIG ECOMMERCE - Iniciando Sistema
echo ============================================

echo Iniciando Backend...
start "MIG BACKEND" cmd /k c:\Sistema_Drop\start_backend.bat

timeout /t 2 /nobreak >nul

echo Iniciando Frontend...
start "MIG FRONTEND" cmd /k c:\Sistema_Drop\start_frontend.bat

echo.
echo ============================================
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:5173
echo   API Docs: http://localhost:8000/docs
echo ============================================
echo.
pause
