@echo off
setlocal
cd /d "%~dp0"
title MAP-CAD 打包

set "PY=C:\pybuild\python\python.exe"
if not exist "%PY%" set "PY=%~dp0_pyinstaller_tool\python\python.exe"
if not exist "%PY%" set "PY=%~dp0..\_pyinstaller_tool\python\python.exe"
if not exist "%PY%" (
  echo [错误] 找不到打包用的 Python（C:\pybuild\python\python.exe）。
  pause
  exit /b 1
)

echo ============================================
echo   MAP-CAD 打包（build.py）
echo ============================================
echo.

"%PY%" "build.py"
echo.
pause
