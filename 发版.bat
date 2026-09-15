@echo off
setlocal
chcp 936 >nul 2>&1
cd /d "%~dp0"
title MAP-CAD 一键发版

rem ---- 找一个能跑 发版.py 的 Python（真正打包用哪个解释器由 发版.py 自己挑）----
set "PY="
for %%c in (
  "C:\pybuild\python\python.exe"
  "%~dp0_pyinstaller_tool\python\python.exe"
  "%~dp0..\.build-venv\Scripts\python.exe"
  "%~dp0.build-venv\Scripts\python.exe"
) do if not defined PY if exist %%c set "PY=%%~c"
if not defined PY for %%p in (python.exe) do set "PY=%%~$PATH:p"
if not defined PY (
  echo [错误] 找不到 Python。装一个 Python，或把打包用的 Python 放到 C:\pybuild\python\python.exe
  echo        也可以改本脚本开头那几行候选路径。
  echo.
  pause
  exit /b 1
)
if not exist "%~dp0发版.py" (
  echo [错误] 找不到 发版.py（它应该和本脚本放在同一个目录里）。
  echo.
  pause
  exit /b 1
)

echo ============================================
echo   MAP-CAD 一键发版
echo   版本号自动 +1 然后打包、提交推送、建 Release、传附件
echo   只想预演不发布：先开个命令行窗口执行  发版.bat --dry
echo   Python: %PY%
echo ============================================
echo.

"%PY%" "发版.py" %*
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" echo [失败] 发版脚本退出码 %RC%（原因见上面）
pause
exit /b %RC%
