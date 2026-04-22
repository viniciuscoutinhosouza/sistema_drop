@echo off
title MIG NGROK
echo Iniciando tunel ngrok na porta 8000...
echo.
echo URL publica sera exibida abaixo.
echo Pressione Ctrl+C para encerrar.
echo.
ngrok http 8000
pause
