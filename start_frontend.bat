@echo off
title MIG FRONTEND
cd /d c:\Sistema_Drop\FRONTEND
if not exist node_modules (
    echo Instalando dependencias...
    npm install
)
npm run dev
pause
