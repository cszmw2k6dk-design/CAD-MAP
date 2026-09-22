# LBD 标注工具

给识别结果（`agent3-debug` JSON）做人工修正的小工具：改框的位置/大小、改 LBD 名字、
删掉多余的框，改完另存一份**同格式 JSON**，直接给编排器（Voltage-CAD MAP）当识别结果用。
也可以不依赖识别结果，直接打开一份 PDF 从零标注。

## 怎么运行

直接跑源码（需要 Python + PySide6）：

```
python lbd_annotator.py                 # 打开后自己选 JSON
python lbd_annotator.py 某份识别结果.json   # 也可以直接把文件拖上来
```

打包成单文件 exe（需要 PyInstaller + PySide6）：

```
python 打包成exe.py            # 正式版（无控制台）
python 打包成exe.py --console  # 调试版，报错能直接看到
```

## 两条使用路径

| 手上有什么 | 用哪个入口 |
|---|---|
| 识别结果 JSON（`agent3-debug`，内嵌了页面图 + 框） | 「打开 JSON」 |
| 只有 PDF、没有识别结果 | 「打开 PDF（无 JSON，直接标注）」 |

「打开 JSON」时会自动按 JSON 里的 `project_name` 去找对应的 PDF（用来渲染更清楚的底图）；
找不到就在工具栏点「选 PDF…」手动指定。

## 底图清晰度

默认用 JSON 里内嵌的页面图（约 167 dpi）。想更清楚就点「选 PDF…」再把 DPI 切到 250 / 333，
程序会调 poppler 的 `pdftoppm.exe` 重新渲染，渲染结果缓存到程序旁边的 `render_cache\`。

poppler 的查找顺序：程序旁边的 `poppler\pdftoppm.exe` → 程序旁边的 `pdftoppm.exe` →
PATH → 常见安装位置（`C:\Program Files\poppler\...`）。只要走「打开 JSON + 内嵌图」这条路，
不需要 poppler。

## 保存规则

- 「另存为」：写一份新文件，原文件不动。
- 「覆盖原文件」：直接覆盖，**不留备份**。
- 只重写你改过的页，没改的页和段落逐字节照搬。
- 页面坐标始终用 JSON 里的原始像素空间，换底图分辨率不影响写回去的数据。

## 依赖

只用到 PySide6 + Python 标准库（没有 numpy / PIL / onnxruntime）。
PDF 渲染另外需要 poppler（`pdftoppm.exe` / `pdfinfo.exe`）。
