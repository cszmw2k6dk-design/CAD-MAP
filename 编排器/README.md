# PDF 半自动流程编排器（本地桌面版 v0.4）

把「MAP 文件工具箱」的 PDF 排版流程做成一个**原生 Windows 桌面软件**，已用 PyInstaller 打包成**单文件 exe**，发给别人双击即用、无需安装 Python。

**界面用 ctypes 直接调用 Win32 原生控件**（不依赖 tkinter/Tcl），因此**中文路径、打包分发都稳定**。

## 使用

双击 `dist\PdfLayoutOrchestrator.exe` 即可（首次运行会在 exe 同目录生成 `config.json`）。

功能：
- 输入 目标 DWG、ZWCAD 插件路径、PDF、LBD 名称 Excel、模板布局、复制数量、支架命名前缀、输出目录、新文件名等参数；
- 「扫描 PDF(LBD)」：内置 pypdf 统计总页数与 LBD 标签分布；
- 「生成执行计划」：列出将要执行的步骤（含支架命名前缀）；
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
- `lbd_regions.py` — LBD 区域范围 / Typical(支架)范围导出（app.py 调用，也可单独命令行跑）
- `PdfLayout_auto.lsp` — 自动化层（复用主插件函数，不修改 PdfLayout.lsp）
- `make_icon.py` — 生成 app.ico 图标
- `config.json` — 默认配置
- `dist\PdfLayoutOrchestrator.exe` — 打包好的单文件程序（发给别人即可）
- `_web版_存档\` — 早期网页版源码（已弃用，仅存档）
- `app_tkinter_backup.py` — 早期 tkinter 版源码（已弃用）

## 说明

- 「执行 / 输出」已通过 `PdfLayout_auto.lsp` + COM 调用 ZWCAD/AutoCAD 完成自动排布；需本机装有 ZWCAD（或 AutoCAD）并加载对应插件。
- exe 为单文件，首次启动自解压略慢，属正常。

## 区域范围导出（跟着「执行 / 输出」自动跑）

提取完 LBD 标签后，程序会自动把识别结果转成下游程序能直接读的表：

- LBD 区域范围 = `yolo_tracker_detection_results` 里 `label == "Node"` 的框（带名字、所属逆变器、区域内支架数）
- Typical(支架)范围 = 同数组里 `label == "Tracker"` 的框（带所属 LBD 区域）
- 另附 LBD 断开点符号位置和每页统计

输出文件：`lbd_regions.csv`、`typicals.csv`、`lbd_symbols.csv`、`pages.csv`、`lbd_typical.json`。
坐标同时给原图像素（`bbox_px`）和归一化值（`bbox_norm`），页面尺寸见 `pages.csv`。

识别 JSON 查找顺序：界面「识别结果 JSON文件」→ AI 输出目录 → 提取文件所在目录，
取最新一份能解析成功的；找不到时只提示一句，不打断 CAD 流程。

相关设置：
- 选项页「生成时自动导出 LBD区域/支架范围」（默认开）
- 文件与输出页「区域范围输出目录(可空)」；留空则输出到「默认保存目录\LBD区域_支架范围」

也可以点顶部「导出区域范围」手动跑一次，或命令行：
```
python ..\frame_detect\extract_lbd_typical.py --json "识别结果.json" --out 输出目录
```

## 支架命名前缀（「支架」页第一格）

**填 `STR`**：支架号在 CAD 里长这样 `STR01`、`STR02` …

`CIR` 不是支架号的前缀，它是插件里 **PDFGRID 网格编号** 用的前缀。本程序界面上的「网格编号」页已经拿掉了
（行数/列距/前缀那几格不影响执行流程，真正的网格编号参数在 CAD 插件自己的 PDFGRID 对话框里设）。

前缀改了会带到 CAD：识别结果 JSON 里形如 `STRxx` 的支架号，会按界面填的前缀改名后再画
（例如填 `CIR` 就画成 `CIR01`）；填回 `STR` 就是原样不动。留空按 `STR` 处理。

写回配置/ini 的键：`rackPrefix`（默认 `STR`）。

## 支架类型（自动填 + 手工选拆不拆）

「支架」页下面有**支架类型明细**，每个支架类型单独一行：支架类型 / 串数 / 长度FT / 数量 / 拆不拆。

- 类型来自识别结果 JSON 的 `input_data.tracker_definitions`（本项目为 `13-string`、`9-string`，
  含数量 1713 / 1256），**不用手填**；
- 每行的**拆不拆**自己选（不拆 / 2行 / 3行）；
- 长度 FT 若 JSON 里带（`length_ft` / `length` / `ft` 等键）会自动填上，没带就留空手填。

触发时机：载入配置、选「识别结果 JSON文件」、点「扫描」、点「从识别结果刷新支架类型」、
以及跑「执行输出」时（后台解析，不卡界面）。

写回配置/ini 的键：
- `rackTypes` = `9:100.3, 13:214.3`（只填了串数时就是 `9, 13`）
- `rackSplitByType` = `9=不拆; 13=3行`（每类单独的拆分选择）
- `rackSplit` 仍是原来的整行规则框，没动

「执行输出」时程序会把 `rackTypes` 补写进 ini，所以这一次 CAD 侧就能读到，不必先手动刷新。

## 生成布局后按 LBD 区域上下限对准视口

生成布局时，插件默认按**整张 PDF 页**对准视口（`PdfLayout_FitViewport` 用底图整体范围算比例）。
勾上选项页的「**生成布局后按 LBD 区域上下限对准视口**」（默认开）后，程序会多走一步：

1. 从识别结果 JSON 里取每页 **LBD 区域（Node 大框）的合并范围**（左/右/上/下），归一化成 0~1；
   - 本项目实测：LBD 区域只占页面高约 60%、宽 26%~42%，所以按整页对准时图会显得小、还有一圈空白；
2. 生成布局、插件对准完之后，CAD 侧再用这个范围**重新对准一次视口**（居中 + 按区域上下限缩放），
   布局视口里看到的就基本是 LBD 区域本身（视口仍留 5% 内边距，`*PdfLayout_ViewInset*`）。

细节：

- 区域范围文件：`%TEMP%\pdflbd_regions.txt`，每行 `R <序号> <fx1> <fy1> <fx2> <fy2>`
  （序号 1 = 第 1 个布局 / 第 1 张图，和布局顺序一一对应；某页没有区域数据就写整页 `0,0,1,1`，等于不缩放）
- 用的是识别结果里的 **LBD 区域**（`yolo_tracker_detection_results` 里 `label == "Node"` 的框），
  不是支架框、也不是 LBD 断开点小框
- 比例是**等比**的（`min(视口宽/区域宽, 视口高/区域高)`），不会把图拉变形；x 和 y 都用区域范围，
  所以除了放大，还会把视口**居中到区域中心**（区域偏左就会往右挪）
- 拿不到识别结果 / 读不到区域时自动跳过，视口还是按整页对准，不会报错中断
- 关掉这个勾就完全不执行这一步（也可在 ini 里写 `regionFit=0`）
- 实现放在 `编排器/PdfLayout_auto.lsp`（`PdfLayout_AutoRegionFit`），**没有改** 主插件 `PdfLayout.lsp`

## 标签位置（固定模型空间）

界面上的「标签位置：模型空间 / 当前布局」单选已经拿掉了，标签只填**模型空间**（ini 里 `labelWhere=M`，
老配置写成 `L` 也会被忽略）。原因：

- 填到布局要把模型坐标按**当前布局的最大视口**换算成图纸坐标；布局一多、或者一个布局里视口不止一个，
  换出来的位置就容易错；
- STR 号（`PdfLayout_ai.lsp`）本来一直画在模型空间，选「当前布局」会让 LBD 标签和 STR 号分处两个空间；
- 标签放模型空间后跟着图走：布局只是通过视口看它，移动/改视口不会让标签跑偏。

CAD 插件本身仍保留 `labelWhere=L` 的分支，手工改 ini 还能用，只是编排器不再提供这个选项。

## 「执行 / 输出」使用说明

1. 「目标 DWG」选要处理的图纸（里面需已有“模板布局”）；
2. 「ZWCAD 插件路径」指到 `PdfLayout.lsp`；
3. 「模板布局名」填该 DWG 里带图框的布局名；「输出目录」「新文件名」决定另存的新 DWG；
4. 点「执行 / 输出」→ 切到 ZWCAD 看它自动跑，程序里实时显示进度。

## 发版 / 同步（都在仓库根目录）

- `发版.bat`：一键发版 —— 版本号 +1 → PyInstaller 打包 → 提交推送 → 建 GitHub Release 并传附件。
  逻辑写在根目录 `发版.py` 里（中文路径 / 代码页 / HTTP 放 Python 里稳，见 `build.py` 的说明）。
  - 预演（一个文件都不改）：命令行执行 `发版.bat --dry`
  - 其它参数：`--version 2.18.0`、`--skip-build`、`--no-push`、`--no-release`、`--note "补充说明"`
  - 打包用的 Python 按这个顺序找：`C:\pybuild\python` → 仓库里 `_pyinstaller_tool` → 上一级 `.build-venv` → PATH 里的 python，
    要求能 `import PyInstaller, PySide6`
  - 打包用的 Python **还必须装 pywin32**（`pip install pywin32`）：连 CAD 走 COM，少了它打出来的 exe
    一点「执行输出」就报 `No module named 'pythoncom'`（`pywin32-ctypes` 是 PyInstaller 的依赖，不算）。
    `build.py` 打包前会检查并给出警告。
  - 建 Release 二选一：装了 GitHub CLI（`gh auth login` 过）或设了 `GITHUB_TOKEN` / `GH_TOKEN`；
    都没有时只打包 + 提示手动发布的步骤
- `同步.bat`：只提交推送，不打包不发版

两个 .bat 必须 **GBK + CRLF** 保存：cmd 读只有 LF 行尾的 .bat 会把 `if (...)` / `for (...)` 块拆成碎片
当命令执行，报一串「xxx 不是内部或外部命令」。脚本开头还加了 `chcp 936`，这样中文在 UTF-8 控制台里也不会乱码。
