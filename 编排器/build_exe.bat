@echo off
rem MAP 文件工具箱 · PDF 半自动流程编排器 打包脚本
rem 需已装好完整 Python(带 tkinter + pip)。注意：路径用纯英文 ASCII，
rem 否则 PyInstaller 的 tkinter 钩子会收不进去(报 No module named 'tkinter')。
set "PY=C:\pybuild\python\python.exe"
if not exist "%PY%" (
  echo [错误] 未找到工具链 Python：%PY%
  echo 请先安装含 tkinter/pip 的完整 Python 到 C:\pybuild\python。
  pause
  exit /b 1
)
cd /d "%~dp0"
"%PY%" make_icon.py
rem 生成 Voltage-CAD MAP 应用（exe 名称沿用产品名）
rem 打包 PySide6/Qt：必须用 --collect-binaries 把 Qt DLL 和插件打进去，否则运行报 DLL load failed。
set "PYSP=Lib\site-packages\PySide6\plugins"
rem Qt 依赖：MSVC 运行时也须原样带入，否则运行报 DLL load failed / 找不到指定的程序。
"%PY%" -m PyInstaller --onefile --windowed --icon app.ico --name "Voltage-CAD MAP" --add-data "%~dp0app_icon.png;." --add-data "%~dp0logo_blue.png;." --add-data "%~dp0PdfLayout_auto.lsp;." --add-data "%~dp0PdfLayout_ai.lsp;." --add-data "%~dp0..\PdfLayout插件包\PdfLayout.lsp;." --collect-binaries PySide6 --collect-binaries shiboken6 --add-data "C:\pybuild\python\%PYSP%\platforms;PySide6\plugins\platforms" --add-data "C:\pybuild\python\%PYSP%\styles;PySide6\plugins\styles" --add-binary "C:\pybuild\python\VCRUNTIME140.dll;." --add-binary "C:\pybuild\python\VCRUNTIME140_1.dll;." --add-binary "C:\pybuild\python\msvcp140.dll;." --add-binary "C:\pybuild\python\concrt140.dll;." --exclude-module PIL --clean --noconfirm app.py
copy /y "%~dp0PdfLayout_auto.lsp" "%~dp0dist\PdfLayout_auto.lsp" >nul
echo.
echo 打包完成：%~dp0dist\Voltage-CAD MAP.exe
pause
