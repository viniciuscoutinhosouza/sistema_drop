@echo off
title MIG BACKEND
cd /d c:\Sistema_Drop\BACKEND
C:\Users\vinic\AppData\Local\Programs\Python\Python311\python.exe -m uvicorn main:socket_app --host 0.0.0.0 --port 8000 --reload
pause
