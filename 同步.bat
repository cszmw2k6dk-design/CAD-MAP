@echo off
setlocal enabledelayedexpansion
chcp 936 >nul
cd /d "%~dp0"
title MAP-CAD 同步到 GitHub

set "REPO=%~dp0"
set "REPO=%REPO:~0,-1%"

rem ---- 找 git：PATH -> 常见安装位置 -> Codex 自带的 git ----
set "GIT=git"
where git >nul 2>&1
if errorlevel 1 (
  set "GIT="
  if exist "%ProgramFiles%\Git\cmd\git.exe" set "GIT=%ProgramFiles%\Git\cmd\git.exe"
  if not defined GIT if exist "%ProgramFiles(x86)%\Git\cmd\git.exe" set "GIT=%ProgramFiles(x86)%\Git\cmd\git.exe"
  if not defined GIT if exist "%ProgramFiles%\Git\bin\git.exe" set "GIT=%ProgramFiles%\Git\bin\git.exe"
  if not defined GIT if exist "%LOCALAPPDATA%\Programs\Git\cmd\git.exe" set "GIT=%LOCALAPPDATA%\Programs\Git\cmd\git.exe"
  if not defined GIT for /d %%d in ("%LOCALAPPDATA%\GitHubDesktop\app-*") do if exist "%%d\resources\app\git\cmd\git.exe" set "GIT=%%d\resources\app\git\cmd\git.exe"
  if not defined GIT for /d %%d in ("%USERPROFILE%\.cache\codex-runtimes\*") do if exist "%%d\dependencies\native\git\cmd\git.exe" set "GIT=%%d\dependencies\native\git\cmd\git.exe"
)
if not defined GIT (
  echo [错误] 找不到 git.exe。请确认装了 Git for Windows，
  echo        或把 git 的 cmd 目录加进系统 PATH，然后重开窗口再双击本脚本。
  echo.
  pause
  exit /b 1
)
if /i not "%GIT%"=="git" echo 用 git: %GIT%
set "GITOPT=-c safe.directory=%REPO%"

set "VER="
for /f "tokens=3" %%v in ('findstr /b /c:"APP_VERSION = " "编排器\app.py"') do set "VER=%%v"
if defined VER set VER=%VER:"=%
set "STAMP="
for /f "usebackq delims=" %%t in (`powershell -NoProfile -Command "Get-Date -Format 'yyyy-MM-dd HH:mm'"`) do set "STAMP=%%t"
if not defined STAMP set "STAMP=%DATE% %TIME%"

echo ============================================
echo   同步到 GitHub
echo   版本: v%VER%
echo   时间: %STAMP%
echo   目录: %REPO%
echo ============================================
echo.

"%GIT%" %GITOPT% rev-parse --is-inside-work-tree >"%TEMP%\vcadmap_gitcheck.txt" 2>&1
if errorlevel 1 (
  echo [错误] 这里不是可用的 git 仓库。git 的原话是：
  type "%TEMP%\vcadmap_gitcheck.txt"
  echo.
  echo 提示：请确认本脚本和 .git 都在 %REPO% 下。
  pause
  exit /b 1
)

rem ---- 代理探测：先看常见本地端口，再看 Windows 系统代理设置 ----
set "PROXY="
for /f "usebackq delims=" %%t in (`powershell -NoProfile -Command "$p=7890,7897,10809,10808,1080,2080,33210,8889;foreach($x in $p){try{$c=New-Object Net.Sockets.TcpClient;$c.Connect('127.0.0.1',$x);$c.Close();Write-Output ('127.0.0.1:'+$x);break}catch{}}"`) do set "PROXY=%%t"
set "SRC="
if defined PROXY set "SRC=本地端口"
if not defined PROXY (
  for /f "usebackq delims=" %%t in (`powershell -NoProfile -Command "try{$k=Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings';if($k.ProxyEnable -eq 1 -and $k.ProxyServer){Write-Output ($k.ProxyServer -replace '.*=','')}}catch{}"`) do set "PROXY=%%t"
  if defined PROXY set "SRC=系统代理"
)
if defined PROXY (
  set "HTTPS_PROXY=http://!PROXY!"
  set "HTTP_PROXY=http://!PROXY!"
  echo 走代理 !PROXY! ^(!SRC!^)。
) else (
  echo 没检测到代理，直连 GitHub。
)

echo.
echo [1/3] 检查改动...
"%GIT%" %GITOPT% add -A
"%GIT%" %GITOPT% diff --cached --quiet
if errorlevel 1 goto commit
echo       没有需要提交的改动。
goto push

:commit
echo [2/3] 提交...
"%GIT%" %GITOPT% commit -q -m "同步 %STAMP% (v%VER%)"
if errorlevel 1 (
  echo.
  echo [错误] 提交失败，请看上面的提示。
  pause
  exit /b 1
)
"%GIT%" %GITOPT% log --oneline -1
echo.
goto push

:push
set /a TRY=0
:pushtry
set /a TRY+=1
echo [3/3] 推送到 GitHub ... 第 !TRY! 次
"%GIT%" %GITOPT% -c http.version=HTTP/1.1 push
if not errorlevel 1 goto ok
if !TRY! GEQ 3 goto pushfail
echo       这次连不上，等 8 秒重试 ...
ping -n 9 127.0.0.1 >nul
goto pushtry

:pushfail
echo.
echo [失败] 连续 3 次没推上去。GitHub 时通时不通时可以这样：
echo        1) 等几分钟再双击本脚本（提交已存在本地，不会丢）；
echo        2) 挂上你的代理/加速器再双击（脚本会自动识别常见端口和系统代理）。
echo.
pause
exit /b 1

:ok
echo.
echo 同步完成。
pause
