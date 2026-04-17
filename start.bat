@echo off
title MIG ECOMMERCE

echo ============================================
echo   MIG ECOMMERCE - Iniciando Sistema
echo ============================================

:: Backend (FastAPI + Uvicorn)
echo Iniciando Backend...
start "MIG BACKEND" cmd /k "cd /d c:\Sistema_Drop\BACKEND && uvicorn main:socket_app --host 0.0.0.0 --port 8000 --reload"

:: Aguarda 2s para o backend subir antes de abrir o frontend
timeout /t 2 /nobreak >nul

:: Frontend (Vite)
echo Iniciando Frontend...
start "MIG FRONTEND" cmd /k "cd /d c:\Sistema_Drop\FRONTEND && npm run dev"

echo.
echo ============================================
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:5173
echo   API Docs: http://localhost:8000/docs
echo ============================================
echo.
echo Pressione qualquer tecla para fechar esta janela...
pause >nul
