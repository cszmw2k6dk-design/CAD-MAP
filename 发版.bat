@echo off
setlocal
chcp 936 >nul
cd /d "%~dp0"
title MAP-CAD 一键发版

set "PY=C:\pybuild\python\python.exe"
if not exist "%PY%" set "PY=%~dp0_pyinstaller_tool\python\python.exe"
if not exist "%PY%" (
  echo [错误] 找不到打包用的 Python（C:\pybuild\python\python.exe）。
  echo        请确认打包工具链还在，或改本脚本里的 PY 路径。
  pause
  exit /b 1
)

echo ============================================
echo   MAP-CAD 一键发版
echo   版本号自动 +1 -> 打包 -> 提交推送 -> 建 Release -^> 传附件
echo   想先预演不发布：发版.bat --dry
echo ============================================
echo.

"%PY%" "发版.py" %*
echo.
pause
