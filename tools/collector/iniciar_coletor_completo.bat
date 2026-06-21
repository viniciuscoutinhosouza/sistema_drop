@echo off
REM ============================================================
REM  Sobe o Coletor ML (API 8777) + o tunel fixo Cloudflare
REM  URL fixa: https://coletor1.madeingroup.api.br
REM  Pode ir no Inicializar do Windows (shell:startup).
REM ============================================================
cd /d "%~dp0..\.."

echo Iniciando Coletor ML (porta 8777)...
start "Coletor ML API" /min ".venv-camoufox\Scripts\python.exe" "tools\collector\collector_api.py"

echo Aguardando a API subir...
timeout /t 4 /nobreak >nul

echo Iniciando tunel Cloudflare (coletor-ml-1)...
"tools\collector\cloudflared.exe" tunnel run coletor-ml-1

echo.
echo Tunel encerrado.
pause
