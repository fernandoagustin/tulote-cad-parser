@echo off
title TuLote CAD Plan Importer (FastAPI + Shapely)
chcp 65001 > nul
cls
echo ====================================================================
echo         TULOTE CAD PLAN IMPORTER - MICROSERVICIO FASTAPI
echo ====================================================================
echo.
echo [*] Iniciando servidor FastAPI en el puerto 8095...
echo [*] Abrí tu navegador en: http://localhost:8095
echo.

start http://localhost:8095

"C:\Users\fernando.romero\AppData\Local\Programs\Python\Python313\python.exe" server.py

pause

