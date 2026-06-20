@echo off
REM ============================================================
REM  Inicia a API local do Coletor ML (Camoufox)
REM  Roda na venv dedicada .venv-camoufox (Python 3.11)
REM  Servico fica em http://127.0.0.1:8777  (health: /health)
REM ============================================================
cd /d "%~dp0..\.."
echo Iniciando Coletor ML local em http://127.0.0.1:8777 ...
echo (feche esta janela para parar o servico)
echo.
".venv-camoufox\Scripts\python.exe" "tools\collector\collector_api.py"
echo.
echo Servico encerrado.
pause
