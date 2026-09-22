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

## 常用操作

| 操作 | 怎么做 |
|---|---|
| 画框 | 工具栏点「画 Node / 画 Tracker / 画 Box」，在图上拖一个框；按 **ESC** 取消这一笔 / 退出画框模式 |
| 选中 | 单击框；空白处拖框 = 框选多个 |
| 移动 / 改大小 | 拖框内 = 移动；拖四角八点 = 改大小；方向键 = 微调（Shift 加快） |
| 复制 / 粘贴 | **Ctrl+C** 复制选中的框，**Ctrl+V** 粘贴。贴出来的**整组排在旁边、不会和原来的重叠**（偏移量按这组框的大小算），可以连着贴；**能贴到别的页**。按住 Ctrl+V 不放只算一次 |
| 删除 | 选中后 **Delete** |
| 改名字 | 选中 Node 框，右侧「LBD 名字」里改（这个名字就是下游读的编号） |
| 撤销 / 重做 | **Ctrl+Z** 撤销，**Ctrl+Y**（或 Ctrl+Shift+Z）重做；撤销/重做都会跟着跳到那一页 |
| 画乱了 / 粘多了 | 工具栏「重载本页」：把当前页恢复成上次打开/保存时的样子（只影响这一页，Ctrl+Z 可以撤销这次恢复） |
| 翻页 | 键盘 **A / D**，或左上角下拉框 |

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
