@echo off
chcp 65001 >nul
title RADAR - Noticias con IA
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  set "PY=py -3"
) else (
  set "PY=python"
)
%PY% --version >nul 2>nul
if errorlevel 1 (
  echo ERROR: Instala Python 3.10 o superior desde https://python.org
  pause
  exit /b 1
)
if not exist .venv (
  echo Creando entorno de Python...
  %PY% -m venv .venv
)
call .venv\Scripts\activate.bat
echo Instalando dependencias necesarias...
python -m pip install -r requirements.txt
if errorlevel 1 (
 echo ERROR: no se pudieron instalar dependencias. Revisa tu conexion.
 pause
 exit /b 1
)
echo.
echo Abre http://localhost:8000 en tu navegador.
echo Los datos iniciales estan marcados como DEMOSTRACION.
echo Credenciales admin iniciales: data\admin_credentials.txt
start "" http://localhost:8000
python run.py
pause
