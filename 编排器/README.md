# PDF 半自动流程编排器（本地桌面版 v0.4）

把「MAP 文件工具箱」的 PDF 排版流程做成一个**原生 Windows 桌面软件**，已用 PyInstaller 打包成**单文件 exe**，发给别人双击即用、无需安装 Python。

**界面用 ctypes 直接调用 Win32 原生控件**（不依赖 tkinter/Tcl），因此**中文路径、打包分发都稳定**。

## 使用

双击 `dist\PdfLayoutOrchestrator.exe` 即可（首次运行会在 exe 同目录生成 `config.json`）。

功能：
- 输入 目标 DWG、ZWCAD 插件路径、PDF、LBD 名称 Excel、模板布局、命名规则、网格大小、输出目录、新文件名等参数；
- 「扫描 PDF(LBD)」：内置 pypdf 统计总页数与 LBD 标签分布；
- 「生成执行计划」：列出将要执行的步骤（含网格大小）；
- 「保存/载入配置」：参数写入 `config.json`（PDF/Excel 可点击「选择」）。
- **「执行 / 输出」**：调用 **中望 ZWCAD**（`ZWCAD.Application`，失败自动试 AutoCAD）打开目标 DWG → 自动执行「布局复制 → LBD 自动填写 → 另存新 DWG」，并实时轮询进度显示。

## 打包（本地重新出 exe）

运行：
```
build_exe.bat
```

（等价于：`python make_icon.py` 生成 `app.ico`，再 `python -m PyInstaller --onefile --windowed --icon app.ico --name PdfLayoutOrchestrator --exclude-module PIL app.py`）

打包工具链在 `C:\pybuild\python`（完整 Python + PyInstaller + pypdf + Pillow，**必须放纯英文路径**，否则打包工具本身可能出问题；最终 exe 不受影响）。

## 文件

- `app.py` — 桌面版主程序（Win32 原生窗口）
- `PdfLayout_auto.lsp` — 自动化层（复用主插件函数，不修改 PdfLayout.lsp）
- `make_icon.py` — 生成 app.ico 图标
- `config.json` — 默认配置
- `dist\PdfLayoutOrchestrator.exe` — 打包好的单文件程序（发给别人即可）
- `_web版_存档\` — 早期网页版源码（已弃用，仅存档）
- `app_tkinter_backup.py` — 早期 tkinter 版源码（已弃用）

## 说明

- 「执行 / 输出」已通过 `PdfLayout_auto.lsp` + COM 调用 ZWCAD/AutoCAD 完成自动排布；需本机装有 ZWCAD（或 AutoCAD）并加载对应插件。
- exe 为单文件，首次启动自解压略慢，属正常。

## 「执行 / 输出」使用说明

1. 「目标 DWG」选要处理的图纸（里面需已有“模板布局”）；
2. 「ZWCAD 插件路径」指到 `PdfLayout.lsp`；
3. 「模板布局名」填该 DWG 里带图框的布局名；「输出目录」「新文件名」决定另存的新 DWG；
4. 点「执行 / 输出」→ 切到 ZWCAD 看它自动跑，程序里实时显示进度。
