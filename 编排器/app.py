# -*- coding: utf-8 -*-
# Voltage-CAD MAP · PDF 半自动流程编排器（PySide6/Qt 界面）
# 业务逻辑（扫描/计划/配置/ZWCAD 自动化）与旧 ctypes 版保持一致。
import os, sys, json, re, glob, hashlib, tempfile, threading, time, subprocess, shutil
import urllib.request, urllib.error, urllib.parse
from PySide6.QtCore import Qt, Signal, QObject, QTimer, QRectF, QPointF, QSize
from PySide6.QtGui import QColor, QPainter, QIcon, QPixmap, QImage, QPen, QPolygonF, QCursor
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QProgressBar, QStackedWidget,
                               QScrollArea, QFileDialog, QButtonGroup, QPlainTextEdit,
                               QFrame, QGridLayout, QCheckBox, QRadioButton, QComboBox,
                               QMessageBox, QDialog, QMenu, QListWidget, QListWidgetItem,
                               QTableWidget, QTableWidgetItem,
                               QGraphicsView, QGraphicsScene, QGraphicsRectItem,
                               QGraphicsSimpleTextItem,
                               QSplitter,
                               QSizePolicy,
                                QTreeWidget, QTreeWidgetItem, QHeaderView, QInputDialog)
from pypdf import PdfReader

try:
    from lbd_regions import (candidate_debug_jsons as _lr_candidates,
                             write_region_file as _lr_write_regions,
                             write_region_file_for_sheets as _lr_write_regions_sheets,
                             sniff_json_kind as _lr_json_kind,
                             extract_lines_from_debug as _lr_extract_debug,
                             rack_lines_from_debug as _lr_rack_lines,
                             debug_page_map as _lr_page_map,
                             rack_types_from_json as _lr_rack_types,
                             preview_group as _lr_preview,
                             STR_ORDER_LABELS as _LR_ORDER_LABELS,
                             QUAD_DEFAULT_ORDERS as _LR_QUAD_DEFAULTS,
                             preview_quadrants as _lr_quad_preview,
                             parse_quad_map as _lr_parse_quad_map,
                             STR_ORDER_TEXT as _LR_ORDER_TEXT,
                             order_demo_cells as _lr_demo_cells,
                             quad_note as _lr_quad_note,
                             rack_types_text as _lr_rack_text,
                             set_rack_len_hints as _lr_set_hints,
                             lbd_mark_boxes as _lr_mark_boxes,
                             # 项目树里「每个 LBD 区有哪些支架号」用这套（和正式出图同一份规则）
                             _assign_parent as _lr_assign_parent,
                             _center as _lr_center,
                             _band as _lr_band,
                             parse_rack_split as _lr_parse_split,
                             rack_split_rows as _lr_split_rows,
                             expand_racks as _lr_expand_racks)
except Exception:                    # 模块缺失时不阻塞主程序
    _lr_candidates = _lr_json_kind = _lr_extract_debug = None
    _lr_write_regions = _lr_write_regions_sheets = None
    _lr_preview = _LR_ORDER_LABELS = None
    _LR_QUAD_DEFAULTS = _lr_quad_preview = _lr_quad_note = None
    _lr_parse_quad_map = None
    _LR_ORDER_TEXT = _lr_demo_cells = None
    _lr_rack_lines = _lr_page_map = None
    _lr_rack_types = _lr_rack_text = _lr_set_hints = None
    _lr_mark_boxes = None
    _lr_assign_parent = _lr_center = _lr_band = None
    _lr_parse_split = _lr_split_rows = _lr_expand_racks = None

APP_TITLE = "Voltage-CAD MAP"
APP_VERSION = "2.57"
# 这一版先不带「导出 PDF」：按钮和入口藏起来，代码保留（改成 True 就接回来）。
FEATURE_EXPORT_PDF = False
# 这一版先不上线「项目树」：入口和联动一起藏起来，实现保留（改成 True 就接回来）。
FEATURE_RECOG_PROJECT_TREE = False
UPDATE_REPO = "cszmw2k6dk-design/CAD-MAP"
UPDATE_ASSET = "Voltage-CAD MAP.exe"
UPDATE_API = "https://api.github.com/repos/%s/releases/latest" % UPDATE_REPO
UPDATE_PAGE = "https://github.com/%s/releases" % UPDATE_REPO
FIELDS = [
    ("dwg", "模板 DWG 文件"),
    ("pdf", "PDF 文件"), ("xlsx", "标签文件"), ("jsonPath", "识别结果 JSON文件"),
    ("newName", "新文件名(可空)"), ("pageStart", "起始页"), ("pageEnd", "结束页(0=全部)"),
    ("importPages", "导入页码(0=全部)"),
    ("count", "复制数量(0=按识别)"),
    ("textHeight", "标签高度(模型单位, 0=自动)"), ("labelBgColor", "标签背景色"),
    ("labelTextColor", "LBD 标签字色"),
    ("labelBgGap", "背景遮挡间隙(倍)"),
    ("rackPrefix", "支架命名前缀"),
    ("strHeight", "STR 字高(typical宽倍数)"),
    ("strOrder", "STR 编号顺序(8 种)"),
    ("strQuadOn", "按汇流箱四象限规律命名(开关)"),
    ("strQuadI", "象限 I 右上 的 STR 顺序"),
    ("strQuadII", "象限 II 左上 的 STR 顺序"),
    ("strQuadIII", "象限 III 左下 的 STR 顺序"),
    ("strQuadIV", "象限 IV 右下 的 STR 顺序"),
    ("rackAlign", "STR 号自动对齐"),
    ("rackAvoid", "避开 LBD 标号(按识别结果)"),
        ("rackTypes", "支架类型"), ("rackSplit", "拆几行(0=不拆)"), ("rackStringLen", "单串长度(FT)"),
    ("strBgOn", "STR背景填充"), ("strBgColor", "STR背景色"), ("strBgGap", "STR遮挡间隙"),
    ("strTextColor", "STR 标签字色"),
    ("margin", "视口边距(mm)"),
    ("regionInset", "区域对准留白(%)"),
]
BROWSE_KEYS = ("dwg", "pdf", "xlsx", "jsonPath")
DEFAULTS = {
    "dwg": "", "lspPath": "",
    "pdf": "", "xlsx": "", "jsonPath": "", "outputDir": "", "newName": "MAP文件",
    "regionOut": "",
    # templateLayout / filter 界面上不再给改（固定模板）：留空 = 自动取第一个带视口的布局，
    # filter = 底图标记名（插件那边认 "pdf"）。
    "pageStart": "1", "pageEnd": "0", "templateLayout": "", "count": "0", "filter": "pdf",
    "margin": "5",
    "regionInset": "90",
    "textHeight": "0.25", "labelBgColor": "1", "labelTextColor": "7", "labelBgGap": "1.0",
    "rackPrefix": "STR",
    "strHeight": "1.4",           # STR 号字高 = typical 条带宽(支架框短边)的倍数
    "strOrder": "2",
    # 象限 STR 顺序：以本页汇流箱(Box)的几何中心为原点，LBD 区域中心落在哪个象限就用哪个
    # 顺序编号那一片支架（0 = 该象限不改、用全局的 strOrder）。四个下拉框见 QUAD_FIELDS。
    # strQuadOn = 0 时整条规则关掉：四个下拉的选值留着不动，但一律按全局 strOrder 编号。
    "strQuadOn": "1",
    "strQuadI": (_LR_QUAD_DEFAULTS or {}).get("I", "5"),
    "strQuadII": (_LR_QUAD_DEFAULTS or {}).get("II", "6"),
    "strQuadIII": (_LR_QUAD_DEFAULTS or {}).get("III", "3"),
    "strQuadIV": (_LR_QUAD_DEFAULTS or {}).get("IV", "1"),
    "rackAlign": "1",
    "rackAvoid": "1",
    "rackTypes": "", "rackSplit": "", "rackStringLen": "",
    "rackAuto": True, "rackSplitByType": "",
    "strBgOn": "1", "strBgColor": "2", "strTextColor": "7", "strBgGap": "1.0",
    "overwrite": False, "labelWhere": "M",
    "regionFit": True,
}
# STR 编号顺序（8 种，和插件 PDFGRID 一致；值 = 界面上的序号）
STR_ORDER_CHOICES = _LR_ORDER_LABELS or [
    ("1 列优先: 左→右列、列内上→下", "1"),
    ("2 行优先: 上→下行、行内左→右", "2"),
    ("3 列优先: 右→左列、列内上→下", "3"),
    ("4 行优先: 下→上行、行内左→右", "4"),
    ("5 列优先: 左→右列、列内下→上", "5"),
    ("6 列优先: 右→左列、列内下→上", "6"),
    ("7 行优先: 上→下行、行内右→左", "7"),
    ("8 行优先: 下→上行、行内右→左", "8"),
]
# 上面 8 种顺序的英文（按值一一对应；中文标签来自 lbd_regions，不靠字符串匹配）
STR_ORDER_EN = [
    "1 Column-first: left→right, top→bottom",
    "2 Row-first: top→bottom, left→right",
    "3 Column-first: right→left, top→bottom",
    "4 Row-first: bottom→top, left→right",
    "5 Column-first: left→right, bottom→top",
    "6 Column-first: right→left, bottom→top",
    "7 Row-first: top→bottom, right→left",
    "8 Row-first: bottom→top, right→left",
]
# 象限 STR 顺序：四个象限各一个下拉框（值 = 8 种顺序的序号，0 = 该象限用全局顺序）。
# 原点 = 本页汇流箱(Box)的几何中心（识别结果 yolo_box_detection_results 的 Box 小框），
# 判据 = LBD 区域(Node 框)的中心，轴 = 图纸正交轴（u 右为正、v 上为正）。
# 页面上没有汇流箱、或区域中心压在轴上（死区）时，用上面的「STR 编号顺序」。
QUAD_FIELDS = (("strQuadI", "I 右上"), ("strQuadII", "II 左上"),
               ("strQuadIII", "III 左下"), ("strQuadIV", "IV 右下"))
QUAD_CN = {"I": "右上", "II": "左上", "III": "左下", "IV": "右下"}
_QUAD_CN2CODE = {v: k for k, v in QUAD_CN.items()}
# 顺序号 -> 说明文字（象限预览的抬头用）
STR_ORDER_TEXT = _LR_ORDER_TEXT or {v: l for (l, v) in STR_ORDER_CHOICES}
# 示意格子：这个顺序在 3x3 里怎么走（lbd_regions.order_demo_cells 的等价实现）
_DEMO_TABLE = {          # 顺序 -> (主轴, 主轴方向, 带内方向)
    "1": ("X", +1, +1), "2": ("Y", +1, +1), "3": ("X", -1, +1), "4": ("Y", -1, +1),
    "5": ("X", +1, -1), "6": ("X", -1, -1), "7": ("Y", +1, -1), "8": ("Y", -1, -1),
}


def demo_cells(order, cols=3, rows=3):
    """这个顺序的示意格子：返回 [{"n", "col", "row"}, ...]（lbd_regions 的同一套规则）。"""
    if _lr_demo_cells is not None:
        try:
            return _lr_demo_cells(order, cols, rows)
        except Exception:
            pass
    axis, mdir, sdir = _DEMO_TABLE.get(str(order), _DEMO_TABLE["2"])
    cells = [{"col": c, "row": r} for r in range(rows) for c in range(cols)]
    key = ((lambda it: (mdir * it["row"], sdir * it["col"])) if axis == "Y"
           else (lambda it: (mdir * it["col"], sdir * it["row"])))
    out = sorted(cells, key=key)
    return [{"n": i + 1, "col": c["col"], "row": c["row"]} for i, c in enumerate(out)]

COLOR_CHOICES = [("红", "1"), ("黄", "2"), ("绿", "3"), ("青", "4"),
                 ("蓝", "5"), ("洋红", "6"), ("白", "7"), ("灰", "8")]

# ---------------- 中英文 ----------------
# 界面上所有会显示给用户看的文字都走 T("中文原文")：中文环境原样返回，
# 英文环境查 TEXT_EN 换掉（查不到就退回中文，绝不报错）。
_LANG = ["zh"]
LANG_NAMES = {"zh": "中文", "en": "English"}


def fmt_hms(sec):
    """秒 -> mm:ss（进度条上显示已用/剩余时间用）。"""
    try:
        sec = max(0, int(round(float(sec))))
    except Exception:
        sec = 0
    return "%d:%02d" % (sec // 60, sec % 60)


def cur_lang():
    return _LANG[0]


def set_lang(code):
    _LANG[0] = "en" if str(code).lower().startswith("en") else "zh"
    return _LANG[0]


def T(zh, *args):
    s = TEXT_EN.get(zh, zh) if _LANG[0] == "en" else zh
    if args:
        try:
            return s % args
        except Exception:
            return s
    return s


TEXT_EN = {
    # ---- 顶栏 / 通用 ----
    "检查更新": "Check for updates",
    "更新": "Update",
    "更新日志": "Changelog",
    "在线更新": "Update",
    "版本": "Version",
    "下载并安装 %s": "Download & install %s",
    "正在下载…": "Downloading…",
    "已是最新版本": "Up to date",
    "检查中…": "Checking…",
    "发现新版本": "New version",
    "中英文切换": "Switch language",
    "语言：中文（点击切到 English）": "Language: 中文 (click for English)",
    "语言：English（点击切到中文）": "Language: English (click for 中文)",
    # ---- 页签 ----
    "文件与输出": "Files & output",
    "标签": "Labels",
    "LBD标签": "LBD label",
    "支架标签": "Rack label (STR)",
    "支架": "Rack",
    "选项": "Options",
    "识别": "Recognize",
    # ---- 文件与输出 ----
    "模板 DWG 文件": "Template DWG",
    "PDF 文件": "PDF file",
    "标签文件": "Label file (xlsx)",
    "识别结果 JSON文件": "Recognition JSON",
    "新文件名(可空)": "New file name",
    "选择": "Browse",
    # ---- PDF 页 ----
    "起始页": "First page",
    "结束页(0=全部)": "Last page (0 = all)",
    "导入页码(0=全部)": "Pages to import (0 = all)",
    "复制数量(0=按识别)": "Copy count (0 = auto)",
    "视口边距(mm)": "Viewport margin (mm)",
    "区域对准留白(%)": "Region fit inset (%)",
    # ---- LBD 标签页 ----
    "标签高度(模型单位, 0=自动)": "Label height (0 = auto)",
    "标签背景色": "Label background colour",
    "LBD 标签字色": "LBD label text colour",
    "背景遮挡间隙(倍)": "Background mask gap (x)",
    "标签页下面那块：LBD 标签的样式参数。": "LBD label appearance.",
    "刷新象限预览": "Refresh quadrant preview",
    # ---- 支架标签页 ----
    "命名前缀(支架号)": "Name prefix (rack no.)",
    "支架类型(串数:长度)": "Rack types (strings:length)",
    "拆几行(0=不拆)": "Rows to split (0 = none)",
    "拆几行": "Rows",
    "0 = 不拆；填 2 / 3 … 表示拆几行": "0 = no split; 2 / 3 … = number of rows",
    "拆不拆": "Split",
    "单串长度(FT,可空)": "String length (FT, optional)",
    "STR 字高(typical宽倍数)": "STR text height (x typical width)",
    "STR 编号顺序(8 种)": "STR numbering order (8)",
    "STR 号自动对齐": "Auto align STR numbers",
    "避开底图 LBD 标号": "Avoid LBD marks on the drawing",
    "STR背景填充": "STR background fill",
    "STR背景色": "STR background colour",
    "STR 标签字色": "STR label text colour",
    "STR遮挡间隙(倍)": "STR mask gap (x)",
    "按汇流箱(Box)四象限规律命名": "Name by combiner-box quadrant rule",
    "象限 I 右上 的顺序": "Quadrant I (top right) order",
    "象限 II 左上 的顺序": "Quadrant II (top left) order",
    "象限 III 左下 的顺序": "Quadrant III (bottom left) order",
    "象限 IV 右下 的顺序": "Quadrant IV (bottom right) order",
    "STR 编号方向 · 按汇流箱(Box)四象限规矩": "STR numbering direction · combiner-box quadrants",
    "判据：原点 = 本页汇流箱(Box)中心，看 LBD 区域中心的方位（u 右为正、v 上为正）"
    "——I 右上 / II 左上 / III 左下 / IV 右下；离原点太近、或这页没有汇流箱时用全局顺序。"
    "关掉开关时四个下拉都不生效。改完看下面的「象限预览」。":
        "Rule: origin = combiner-box centre on this page; look at the LBD-region centre "
        "(u right, v up) — I top-right / II top-left / III bottom-left / IV bottom-right. "
        "Too close to the origin, or no combiner box: the global order is used. "
        "When the switch is off none of the four dropdowns apply.",
    "支架类型明细": "Rack type detail",
    "从识别结果刷新支架类型": "Reload rack types from recognition",
    "刷新 STR 顺序预览": "Refresh STR order preview",
    "支架类型": "Rack type",
    "串数": "Strings",
    "长度FT": "Length",
    "长度": "Length",
    "长度px": "Len px",
    "数量": "Count",
    # ---- 选项 ----
    "覆盖同名布局": "Overwrite layouts with the same name",
    "生成布局后按 LBD 区域上下限对准视口": "Fit viewport to LBD region after layout",
    "支架类型自动读识别结果(免手填)": "Read rack types from recognition automatically",
    # ---- 下拉项（显示文字，值不变） ----
    "开": "On",
    "关": "Off",
    "不拆": "No split",
    "2行": "2 rows",
    "3行": "3 rows",
    "开：按四象限规律命名": "On: use the quadrant rule",
    "关：一律按「支架」页的全局顺序": "Off: use the global order on the rack page",
    "0 用全局顺序（该象限不改）": "0 use global order (leave this quadrant)",
    "红": "Red", "黄": "Yellow", "绿": "Green", "青": "Cyan",
    "蓝": "Blue", "洋红": "Magenta", "白": "White", "灰": "Grey",
    # ---- 识别页 ----
    "PDF 文件": "PDF file",
    "上传 PDF": "Upload PDF",
    "选要识别的 PDF（图纸集）": "PDF to recognize",
    "识别页码": "Pages",
    "留空 = 全部；也可写 3-8,12": "empty = all; also 3-8,12",
    "开始识别": "Recognize",
    "识别中…": "Recognizing…",
    "预览": "Preview",
    "页": "Page",
    "LBD 区": "LBD area",
    "支架": "Rack",
    "箱": "Box",
    "配到编号": "Matched",
    "编号位置": "No. position",
    "识别完这里会画出识别到的框（蓝=LBD 区，红=支架，橙=编号位置）":
        "Detected boxes appear here (blue = LBD area, red = rack, orange = number)",
    "放大（也可以滚轮）": "Zoom in (or wheel)",
    "缩小（也可以滚轮）": "Zoom out (or wheel)",
    "适应宽度": "Fit width",
    "删除选中": "Delete selected",
    "删掉选中的框（Delete 键同效）": "Delete the selected box (Delete key)",
    "撤销": "Undo",
    "撤销上一步改动": "Undo the last change",
    "加框": "Add box",
    "在画布上拖一下画一个新框（默认给 LBD 区）":
        "Drag on the canvas to draw a new box (LBD area by default)",
    "框类型": "Box type",
    "编号": "Name",
    "选中一个 LBD 区后可改名": "Select an LBD area to rename it",
    "改名": "Rename",
    "保存修改": "Save",
    "导出识别结果 JSON…": "Export recognition JSON…",
    "只保留": "Keep only",
    "页范围，如 23-108": "e.g. 23-108",
    "过滤": "Filter",
    "滚轮缩放 · 中键拖动平移 · 拖框改位置 · 拖控制点改大小 · Delete 删除":
        "Wheel = zoom · middle-drag = pan · drag = move · drag a control point = resize · Delete = remove",
    "项目树": "Tree",
    "LBD → ROW 列 → 每根支架；双击支架改串数，双击 LBD 改名":
        "LBD → ROW → each rack; double-click a rack to set its string count",
    "整册支架长度 → 串数": "Rack lengths → strings",
    "识别到的每一档都在这儿；填上串数就按它匹配整册支架类型":
        "Every detected length bucket is listed here; the string count you fill in drives the rack types",
    "日志": "Log",
    "展开 / 收起识别日志（上面那张支架类型表一直露着）":
        "Show / hide the recognition log (the rack-length table above stays visible)",
    "应用到支架页": "Apply to rack page",
    "下一步：填其它参数 →": "Next: other parameters →",
    "先选 PDF 文件（「文件与输出」页）": "Choose a PDF first (Files & output page)",
    "用「文件与输出」里选的 PDF 识别（模型 v4c，直接在程序里跑）。跑完自动填进「识别结果 JSON文件」，接着走标签 / 执行即可。":
        "Recognizes the PDF chosen on the Files page (model v4c, runs inside the app). "
        "The result is written into the recognition JSON; continue to Labels / Run.",
    "选要识别的 PDF（图纸集）": "PDF to recognize",
    "留空 = 全部；也可写 3-8,12": "empty = all; also 3-8,12",
    "页范围，如 23-108": "e.g. 23-108",
    # ---- 底部 / 执行 ----
    "返回识别": "← Back to recognition",
    "← 返回识别": "← Back",
    "回到识别界面（换 PDF / 重新识别 / 改框和编号）":
        "Back to recognition (change PDF / re-run / edit boxes and names)",
    "执行": "Run",
    "执行输出": "Run",
    "暂停": "Pause",
    "继续": "Resume",
    "停止": "Stop",
    "暂停执行（随时可停）": "Pause / stop the run at any time",
    "已暂停（画布与进度已冻结，点「继续」接着跑）":
        "Paused (frozen – click Resume to continue)",
    "已停止": "Stopped",
    # ---- 状态页 ----
    "准备就绪": "Ready",
    "已绘制  0 / ？": "Drawn  0 / ?",
    "生成完成后，点右下角「下载」选择保存位置":
        "When finished, click «Download» at the bottom right to pick a location",
    "不会再自动保存到“默认保存目录”，选完路径才写文件":
        "Nothing is saved automatically – you choose the path",
    "下载": "Download",
    "导出 PDF": "Export PDF",
    "再次另存…": "Save again…",
    # ---- 日志 / 状态 ----
    "正在连接 / 启动 CAD…": "Connecting / starting CAD…",
    "已绘制  %d / %d": "Drawn  %d / %d",
    "已对准  %d / %d": "Fitted  %d / %d",
    "完成": "Done",
    "执行出错：": "Run failed: ",
    "完成：": "Finished: ",
    "%s（%d/%d）": "%s (%d/%d)",
    # ---- 识别页补充（英文界面漏翻 / 显示不全的） ----
    "← 上一步": "← Back",
    "回到识别工作区（换 PDF / 重新识别 / 改框）":
        "Back to the recognition workspace (change PDF / re-run / edit boxes)",
    "立刻停止本次执行（CAD 侧会在下一个检查点收尾停下）":
        "Stop this run now (CAD wraps up at the next checkpoint)",
    "选要识别的 PDF（图纸集）；整本识别，跑完再用「过滤」挑页":
        "PDF to recognise (whole set); use Filter afterwards to pick pages",
    "整本识别（模型 v4c 在程序里跑），跑完自动填「识别结果 JSON文件」；"
    "页数多了就用下面的「只保留 / 过滤」挑页。":
        "Recognises the whole PDF (model v4c, in-app) and fills the recognition JSON; "
        "use Keep only / Filter below for long sets.",
    "LBD 数": "LBDs",
    "锁定 LBD": "Lock LBD",
    "锁住本页的 LBD 区：不能拖动 / 改大小 / 删除（支架、汇流箱照常编辑）；每页各记各的":
        "Lock this page's LBD areas: no move / resize / delete "
        "(racks and boxes stay editable); remembered per page",
    "把不在这段页码里的识别结果丢掉（封面/说明/清单页这类不该画的页）":
        "Drop results outside this page range (covers, notes, schedules)",
    "把这张表写进「支架」页明细行，并给整册支架标上串数":
        "Write this table into the rack page and tag every rack",
    "重算分档": "Re-bucket",
    "按当前识别到的支架框重新统计「支架长度分档」（改过框 / 删过框之后马上想看新分档就点）":
        "Recompute rack-length buckets from the current boxes",
    "重认编号": "Re-match",
    "按 PDF 文字层重新读这一页的 LBD 编号（挪过 / 加过 LBD 框之后用；读不到时保留原来的名字）":
        "Re-read LBD names from the PDF text layer (existing names kept if none found)",
    "检查": "Check",
    "扫一遍识别结果：没编号的 LBD、没落档的支架、不在任何 LBD 里的支架、重复编号":
        "Check for unnamed LBDs, unbucketed racks, racks outside every LBD, duplicate names",
    "画 Box": "Draw Box",
    "画支架": "Draw rack",
    "画 LBD 区": "Draw LBD area",
    "点一下进入「%s」模式，再在画布上拖一下就画出来；再点一下退出":
        "Click to draw a %s; drag on the canvas, click again to exit",
    "点一下进入这个绘制模式，再在画布上拖一下就画出来；再点一下退出":
        "Click to enter this draw mode; drag on the canvas, click again to exit",
    "本页问题：—": "Page issues: —",
    "⚠ %d 页有问题（点一下看哪页）": "⚠ %d page(s) with issues (click to see which)",
    "这一页没问题": "No issues on this page",
    "检查问题": "Check issues",
    "识别完成后点这里，看哪几页有问题": "After recognition, click here to see which pages have issues",
    "共 %d 页有问题，双击一条跳到那一页：": "%d page(s) with issues — double-click one to jump:",
    "跳到这一页": "Go to this page",
    "还没识别，先跑一次「开始识别」。": "Nothing recognised yet — run «Recognize» first.",
    "STR 顺序预览：%s": "STR order preview: %s",
    "（只显示前 %d / %d 个）": " (showing the first %d of %d)",
    "本页问题：没发现": "Page issues: none",
    "（点这里看全部页面的检查结果）": "(click to see all page issues)",
    "这一页没发现明显问题（点这里看全部页面的检查结果）":
        "No obvious issues on this page (click to see all pages)",
    "%d 个 LBD 没编号": "%d LBD(s) unnamed",
    "（其中 %d 个已填前缀，补数字即可）": " (%d with a prefix only — add the number)",
    "重复编号 %s": "Duplicate names %s",
    "%d 根支架不在任何 LBD 区（不会编号）": "%d rack(s) outside every LBD (won't be numbered)",
    "%d 根支架长度没落档": "%d rack(s) with an unmatched length",
    "有 LBD 区但没有支架框": "LBD areas but no rack boxes",
    "第 %s 页：%s": "Page %s: %s",
    "识别结果检查": "Recognition check",
    "没发现明显问题。": "No obvious issues found.",
    "查找识别结果出错：%s": "Could not read the recognition result: %s",
    "没找到识别结果 JSON：请先在上面选「识别结果 JSON文件」":
        "No recognition JSON found — pick one above first",
    "识别结果检查（%d 页有问题）": "Recognition check (%d page(s) with issues)",
    "…（还有 %d 页有问题，看看识别页左表和画布）":
        "…(%d more page(s) with issues — see the page list and canvas)",
    "已选择": "Selected",
    "未选择": "Not selected",
    "还没选 PDF，点右边「上传 PDF」": "No PDF yet — click Upload PDF",
    "（还没读到识别结果：指定「识别结果 JSON文件」或跑一次「执行输出」后，这里会自动列出）":
        "(No recognition result yet: pick a recognition JSON or run once — the list fills in automatically)",
    "稍后": "Later",
    "%s 串": "%sS",
    "关闭": "Close",
    "下载并安装": "Download & install",
}
SECTIONS = [
    ("文件与输出", [("dwg", "模板 DWG 文件"),
                  ("pdf", "PDF 文件"), ("xlsx", "标签文件"),
                  ("jsonPath", "识别结果 JSON文件"),
                  ("newName", "新文件名(可空)")]),
    # PDF：底图从哪几页来、怎么对准视口
    ("PDF", [("pageStart", "起始页"), ("pageEnd", "结束页(0=全部)"),
             ("importPages", "导入页码(0=全部)"),
             ("count", "复制数量(0=按识别)"),
             ("margin", "视口边距(mm)"),
             ("regionInset", "区域对准留白(%)")]),
    # LBD标签：只管 LBD 标签自己长什么样（字高/底色/字色/遮挡间隙）
    ("LBD标签", [("textHeight", "标签高度(模型单位, 0=自动)"),
               ("labelBgColor", "标签背景色"),
               ("labelTextColor", "LBD 标签字色"),
               ("labelBgGap", "背景遮挡间隙(倍)")]),
    # 支架标签：和 STR 有关的东西（前缀/类型明细/字高/编号顺序/四象限规律/背景/避让）
    ("支架标签", [("rackPrefix", "命名前缀(支架号)"),
              ("rackTypes", "支架类型(串数:长度)"),
        ("rackSplit", "拆几行(0=不拆)"),
              ("rackStringLen", "单串长度(FT,可空)"),
              ("strHeight", "STR 字高(typical宽倍数)"),
              ("strOrder", "STR 编号顺序(8 种)"),
              ("strQuadOn", "按汇流箱(Box)四象限规律命名"),
              ("strQuadI", "象限 I 右上 的顺序"),
              ("strQuadII", "象限 II 左上 的顺序"),
              ("strQuadIII", "象限 III 左下 的顺序"),
              ("strQuadIV", "象限 IV 右下 的顺序"),
              ("rackAlign", "STR 号自动对齐"),
              ("rackAvoid", "避开底图 LBD 标号"),
              ("strBgOn", "STR背景填充"),
              ("strBgColor", "STR背景色"),
              ("strTextColor", "STR 标签字色"),
              ("strBgGap", "STR遮挡间隙(倍)")]),
    ("选项", []),
]
FIELDS_INDEX = {k: i for i, (k, _) in enumerate(FIELDS)}


# ---------------- 业务逻辑（沿用旧版）----------------
def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def find_icon():
    if getattr(sys, "frozen", False):
        cand = os.path.join(getattr(sys, "_MEIPASS", ""), "app_icon.png")
        if os.path.exists(cand):
            return cand
    cand = os.path.join(app_dir(), "app_icon.png")
    if os.path.exists(cand):
        return cand
    return None


def find_logo():
    if getattr(sys, "frozen", False):
        cand = os.path.join(getattr(sys, "_MEIPASS", ""), "logo_blue.png")
        if os.path.exists(cand):
            return cand
    cand = os.path.join(app_dir(), "logo_blue.png")
    if os.path.exists(cand):
        return cand
    return None


# ---------------- 顶栏小图标（不额外带图片文件，直接画） ----------------
_ICON_CACHE = {}


def make_icon(name, size=36, color="#DADFE3"):
    """按名字画一个小图标（更新 / 日志 / 中英文）。"""
    key = (name, size, color)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    try:
        p.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(QColor(color))
        pen.setWidthF(max(1.6, size / 16.0))
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        s = float(size)
        if name == "update":
            # 刷新箭头：留缺口的圆环 + 实心三角箭头（18px 下也认得出）
            r = QRectF(s * 0.22, s * 0.22, s * 0.56, s * 0.56)
            p.drawArc(r, 35 * 16, 290 * 16)
            tri = QPolygonF([QPointF(s * 0.88, s * 0.24),
                             QPointF(s * 0.645, s * 0.26),
                             QPointF(s * 0.815, s * 0.42)])
            p.setBrush(QColor(color))
            p.drawPolygon(tri)
            p.setBrush(Qt.NoBrush)
        elif name == "notes":                      # 文档 + 三条线
            p.drawRoundedRect(QRectF(s * 0.24, s * 0.16, s * 0.52, s * 0.68), s * 0.08, s * 0.08)
            for i, y in enumerate((0.35, 0.50, 0.65)):
                p.drawLine(QPointF(s * 0.34, s * y), QPointF(s * 0.66, s * y))
        elif name == "lang":                       # 地球：圆 + 两条经线 + 赤道
            p.drawEllipse(QRectF(s * 0.18, s * 0.18, s * 0.64, s * 0.64))
            p.drawEllipse(QRectF(s * 0.34, s * 0.18, s * 0.32, s * 0.64))
            p.drawLine(QPointF(s * 0.18, s * 0.50), QPointF(s * 0.82, s * 0.50))
        else:
            p.drawEllipse(QRectF(s * 0.22, s * 0.22, s * 0.56, s * 0.56))
    finally:
        p.end()
    ico = QIcon(pm)
    _ICON_CACHE[key] = ico
    return ico


def config_path():
    """配置文件路径（只读）。

    以前这里会顺手 open(cand, "a") 建一个 config.json，关窗口时还会再写一遍；
    程序放在桌面（本机就是这样）时，桌面上就凭空多出一个 config.json。
    现在这个文件不再创建、也不再写入。
    """
    return os.path.join(app_dir(), "config.json")


def load_config():
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = {}
    out = dict(DEFAULTS)
    out.update({k: v for k, v in d.items() if k in DEFAULTS})
    # 文件路径一律不记忆（DWG / PDF / 标签文件 / 识别结果 JSON）：
    # 每次打开都是空的，用的时候自己选 —— 免得照着一台机器上的旧路径去跑。
    for k in BROWSE_KEYS:
        out[k] = ""
    return out


def pdf_page_range_count(cfg):
    # 按起始页~结束页识别底图页数（快速，只读页数，不抽取文字）
    pdf = (cfg.get("pdf") or "").strip()
    if not pdf or not os.path.exists(pdf):
        return None, "PDF 文件不存在：%s" % pdf
    try:
        ps = int(cfg.get("pageStart") or 1)
        pe = int(cfg.get("pageEnd") or 0)
    except Exception:
        ps, pe = 1, 0
    try:
        total = len(PdfReader(pdf).pages)
    except Exception as e:
        return None, "打开 PDF 失败：%s" % e
    if ps < 1:
        ps = 1
    if pe <= 0 or pe > total:
        pe = total
    if ps > pe:
        return None, "起始页大于结束页"
    return pe - ps + 1, "起始 %d ~ 结束 %d，共 %d 页（PDF 总页数 %d）" % (ps, pe, pe - ps + 1, total)


# 注：这里原先是一整套「Python 读 PDF 文字层」的代码 —— _pdf_rotate / _pdf_page_size /
# _pdf_norm_pt / _pdf_text_items（把一页的文字块换算成底图归一化坐标）和 pdf_lbd_boxes()
# （挑出含 "LBD" 的文字框，给 STR 号避让用）。现在文字层统一由标注工具读
# （「补全编号」/ 核对表，见 标注工具\lbd_annotator.py），主程序只吃 JSON，
# 不再自己解析文字层；依赖它的「避开底图 LBD 标号」开关也一起去掉了。
#
# 还留在主程序里的 pypdf 用法只有「数页数」（pdf_page_range_count / pdf_page_count）
# 和导出 PDF 时的合并（PdfWriter），都不碰文字层。


def rack_prefix(cfg):
    """支架号命名前缀（界面「支架」页）。留空按 STR。

    支架号在 CAD 里长这样：前缀 + 位数编号，例如 STR01、STR02 …
    （CIR 是网格编号 PDFGRID 用的前缀，不是支架号的，网格编号已在 CAD 插件里单独设。）
    """
    p = str(cfg.get("rackPrefix", "STR") or "").strip().upper()
    return p or "STR"


def quad_on(cfg):
    """「按汇流箱(Box)四象限规律命名」这个总开关是否打开（默认开）。"""
    v = str((cfg or {}).get("strQuadOn", "1") or "0").strip()
    return v not in ("0", "", "关", "否", "off", "false", "False")


def quad_orders_from_cfg(cfg):
    """界面四个象限下拉框 -> {I..IV: 顺序}（0 = 该象限不改，取全局 strOrder）。

    预览画图用：不管选了没有，四个象限都要有个号可显示。
    """
    c = cfg or {}
    g = str(c.get("strOrder", "2") or "2").strip() or "2"
    if g not in ("1", "2", "3", "4", "5", "6", "7", "8"):
        g = "2"
    if not quad_on(c):
        return {q: g for q in ("I", "II", "III", "IV")}       # 开关关了：四个都按全局
    out = {}
    for key, q in (("strQuadI", "I"), ("strQuadII", "II"),
                   ("strQuadIII", "III"), ("strQuadIV", "IV")):
        v = str(c.get(key, "0") or "0").strip()
        out[q] = v if v in ("1", "2", "3", "4", "5", "6", "7", "8") else g
    return out


def quad_map_spec(cfg):
    """界面四个象限下拉框 -> lbd_regions 认的象限顺序表（"右上=4; 左上=8; …"）。

    选「0 用全局顺序」的象限不写进去 —— 那边就按全局顺序编号；四个都是 0 时返回 ""，
    等于这套规则不用（和以前完全一样）。
    """
    c = cfg or {}
    if not quad_on(c):
        return ""                                  # 开关关了：一律按全局顺序（下拉的选值留着）
    parts = []
    for key, q in (("strQuadI", "I"), ("strQuadII", "II"),
                   ("strQuadIII", "III"), ("strQuadIV", "IV")):
        v = str(c.get(key, "0") or "0").strip()
        if v in ("1", "2", "3", "4", "5", "6", "7", "8"):
            parts.append("%s=%s" % (QUAD_CN.get(q, q), v))
    return "; ".join(parts)


def parse_quad_spec(text):
    """配置里那一行 "右上=4; 左上=8" -> {"I": "4", "II": "8"}（认不出来返回 {}）。"""
    if _lr_parse_quad_map is not None:
        try:
            return _lr_parse_quad_map(text)
        except Exception:
            return {}
    out = {}
    for part in re.split(r"[;,，、\s]+", str(text or "")):
        m = re.match(r"^([^=:：]+?)\s*[=:：]\s*([1-8])$", part)
        if not m:
            continue
        q = _QUAD_CN2CODE.get(m.group(1).strip())
        if q:
            out[q] = m.group(2)
    return out


def rack_split_spec(cfg):
    """界面「支架」页的「拆不拆」-> lbd_regions.parse_rack_split() 认的文字。

    支架明细行写的 rackSplitByType（每类一行，如 "9=不拆; 13=3行"）优先；
    没填明细行时才用「拆不拆」那一格 rackSplit。两处都没填就是全不拆。
    """
    by_type = str((cfg or {}).get("rackSplitByType") or "").strip()
    if by_type:
        return by_type
    return str((cfg or {}).get("rackSplit") or "").strip()


def apply_rack_len_hints(cfg):
    """把界面「支架」页明细行的「长度FT」交给 lbd_regions 判支架类型。

    支架拆分要靠它：识别结果里只有串数、没有长度，判不出「哪一列属于哪一类」
    （见 lbd_regions.rack_type_indices）。没填长度的类型，界面那边已经拿串数
    当比例值了（见 MainWindow.cfg()），所以不填也能把两类分开。
    """
    if _lr_set_hints is None:
        return
    try:
        _lr_set_hints((cfg or {}).get("rackLenHints") or {})
    except Exception:
        pass


def rack_len_hint_note(cfg):
    """日志用：这次判支架类型用的长度（哪些是拿串数代替的）。"""
    hints = (cfg or {}).get("rackLenHints") or {}
    proxy = (cfg or {}).get("rackLenProxy") or []
    if not hints:
        return ""
    parts = []
    for k in sorted(hints, key=lambda x: str(x)):
        parts.append("%s串=%g%s" % (k, hints[k], "（按串数代替）" if k in proxy else ""))
    return "、".join(parts)


def json_to_extract(json_path, out_path, prefix="STR"):
    """读取识别结果 JSON(X-AnyLabeling 格式) -> 输出 L 行(页号 fx fy 标签) 供 CAD 读取。
    Node 框= LBD 区域, Typical 框= 支架(STR号)。页号取文件名里的 _pNNN。
    prefix = 支架号命名前缀：识别结果里是 STRxx 时按这个前缀改名（默认 STR，等于不改）。"""
    import re as _re
    pre = (str(prefix or "STR").strip() or "STR").upper()
    d = json.load(open(json_path, "r", encoding="utf-8"))
    W = d.get("imageWidth") or 1
    H = d.get("imageHeight") or 1
    m = _re.search(r"[_\-]p(\d+)", os.path.basename(json_path))
    page = int(m.group(1)) if m else 1
    lines = []
    nodes = typs = 0
    for s in d.get("shapes", []):
        lab = (s.get("label") or "").strip()
        pts = s.get("points") or []
        if not lab or len(pts) < 2:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        bx1, bx2 = min(xs), max(xs)
        by1, by2 = min(ys), max(ys)
        # 注意: LBD 行必须保留 —— PdfLayout_auto.lsp 靠这些行拿到 LBD 的
        # 位置和编号, 再用 Excel 里的名称去填写。这里只是不再让 AI 画它们(见 PdfLayout_ai.lsp)。
        up = lab.upper()
        if pre != "STR" and up.startswith("STR"):
            lab = pre + lab[3:]          # 支架号改名：STR01 -> <前缀>01
            up = lab.upper()
        fx = ((bx1 + bx2) / 2.0) / W
        fy = 1.0 - (((by1 + by2) / 2.0) / H)
        # STR 号: 角度按支架框长宽比自动(竖条=90,横条=0); 字高按框短边(占页高比例,
        # CAD 端再乘 *PdfLayout_AiStrScale*)。其它标签(LBD)角度 0、字高用默认值。
        bw, bh = bx2 - bx1, by2 - by1
        if up.startswith(pre):
            ang = 90 if bh > bw else 0
            hgt = min(bw, bh) / float(H)
        elif "-LBD-" in up:
            ang = 0
            hgt = max(1.0, bw) / float(H)          # LBD 标签：按 LBD 区域宽算字高
        else:
            ang = 0
            hgt = 0.0
        lines.append("L\t%d\t%.6f\t%.6f\t%s\t%d\t%.6f" % (page, fx, fy, lab, ang, hgt))
        if "-LBD-" in up:
            nodes += 1
        elif up.startswith(pre):
            typs += 1
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return len(lines), nodes, typs


def write_auto_ini(cfg, ini_path):
    """把界面配置写成 LSP 读的 ini（on_run 与后台线程补写支架类型都用这个）。"""
    with open(ini_path, "w", encoding="gbk") as f:
        for k, v in cfg.items():
            f.write("%s=%s\n" % (k, 1 if v is True else (0 if v is False else v)))


def avoid_note(detail):
    """日志里那句"避开了多少处 LBD 标号"（位置来自识别结果 JSON 里的 label_pos）。"""
    if not detail:
        return ""
    n = int(detail.get("avoid") or 0)
    return ("；已按识别结果避开底图 LBD 标号 %d 处" % n) if n else ""


def build_extract_file(cfg, out_path, prog_path=None):
    """生成 CAD 读的标签提取文件（P/L 行）。返回 (ok, 说明, 明细)。

    按手上有什么自动选：
      1) 标注/编号结果 JSON（X-AnyLabeling，有 shapes）：LBD 名称和支架号都在里面，直接转；
      2) 识别结果 debug JSON（有 Node/Tracker 框）：LBD 标签填到「识别到的 LBD 区域」上，
         支架号 STRxx 由 debug JSON 按 LBD 分组现编，追加到同一个文件里。

    LBD 名字/位置一律来自 JSON —— 标注工具已经用「补全编号」从 PDF 文字层提过一遍写进
    JSON 了（见 标注工具\\lbd_annotator.py），主程序不再自己去翻 PDF 文字层。
    """
    jp = (cfg.get("jsonPath") or "").strip()
    pre = rack_prefix(cfg)
    order = str(cfg.get("strOrder", "2") or "2").strip() or "2"
    # 象限编号规则：以离每个 LBD 区域最近的汇流箱(Box)中心为原点判象限，
    # 用象限顺序表里对应的顺序编号那一片的 STR 号（见 lbd_regions.quad_order_map）。
    # 四个象限的顺序都在界面上选；选「0 用全局顺序」的象限不写进表，就不改那一片。
    quad_rule = ""
    quad_map = quad_map_spec(cfg)
    # 界面明细行的「长度FT」（没填的用串数当比例）-> lbd_regions：
    # 拆分要靠它判「哪一列属于哪一类」，不然只能全拆或全不拆。
    apply_rack_len_hints(cfg)
    split = rack_split_spec(cfg)
    # STR 号自动对齐：开 = 同一排的号按排线对齐（只动高度）；关 = 各画在自己格子中心
    align = str(cfg.get("rackAlign", "1")).strip() not in ("0", "", "关", "否", "off", "false", "False")
    detail = {"kind": "", "lbd": 0, "str": 0}

    kind = ""
    if jp and os.path.exists(jp) and _lr_json_kind is not None:
        try:
            kind = _lr_json_kind(jp)
        except Exception:
            kind = ""
    detail["kind"] = kind

    # 图纸页号 -> 底图顺序号：CAD 侧按「第几张底图」认页号，PDF 里的封面/说明页会让两者错位，
    # 所以按识别结果里出现过的页、页码升序重编号（这一步同时把样板文字页滤掉）。
    pgmap = None
    if kind == "debug" and _lr_page_map is not None:
        try:
            pgmap = _lr_page_map(jp)
        except Exception:
            pgmap = None
    detail["pages"] = len(pgmap) if pgmap else 0

    # STR 号要避开的障碍（带背景填充的号压上去会把编号盖掉）：底图上印着的 LBD 标号。
    # 位置来自识别结果 JSON 里每根 Node 的 raw.label_pos（标注工具从文字层/OCR 抓的，
    # 实测就是标号框中心，见 lbd_regions.lbd_mark_boxes），不再翻 PDF 文字层。
    # CAD 里画的 LBD 标签仍然由标签自己上下让位（PdfLayout_auto.lsp 的 PdfLayout_LbdPlace）。
    avoid = None
    _avoid_pad = 0.0        # 关掉避让时也要有值：下面几条输出路径都会用到它
    detail["avoid"] = 0
    if (kind == "debug" and _lr_mark_boxes is not None
            and str(cfg.get("rackAvoid", "1")).strip() not in ("0", "", "关", "否", "off", "false", "False")):
        try:
            avoid = _lr_mark_boxes(jp, page_map=pgmap) or None
        except Exception:
            avoid = None
        detail["avoid"] = sum(len(v) for v in (avoid or {}).values())
        # STR 号是"文字 + 背景填充(白底)"画出来的：白底比文字框大一圈，
        # 避让时不算白底的话，白底照样会盖住底图上的 LBD 标号。
        # 外扩量按填充间隙的一半估（实测口径；关掉背景填充就不外扩）。
        try:
            _bg_on = str(cfg.get("strBgOn", "1")).strip() not in (
                "0", "", "关", "否", "off", "false", "False")
            _gap = float(str(cfg.get("strBgGap", "1.0")).strip() or 1.0) if _bg_on else 0.0
        except Exception:
            _gap = 1.0
        _avoid_pad = min(1.0, max(0.0, _gap)) * 0.5
        detail["avoid_pad"] = round(_avoid_pad, 3)

    # 1) 标注/编号结果：LBD 名称 + 支架号都在 JSON 里
    if kind == "anylabeling":
        n, nn, nt = json_to_extract(jp, out_path, pre)
        detail.update(lbd=nn, str=nt)
        return True, ("标注结果 JSON：标签 %d 行（LBD %d / 支架 %d，前缀 %s）"
                      % (n, nn, nt, pre)), detail

    # 2) 识别结果 debug JSON + 开关打开：LBD 标签填到「识别到的 LBD 区域」上
    #    （PDF 文字层里那些 LBD 名常常在图纸右上角的清单表里，填出来会全跑到角落）
    if kind == "debug" and _lr_extract_debug is not None:
        try:
            r = _lr_extract_debug(jp, out_path, prefix=pre, page_map=pgmap,
                                  order=order, split=split, align=align, avoid=avoid,
                                  avoid_pad=_avoid_pad,
                                  quad_rule=quad_rule, quad_map=quad_map)
        except Exception as e:
            r = {"ok": False, "error": str(e)}
        if r.get("ok") and r["lbd"]:
            detail.update(lbd=r["lbd"], str=r["str"], pos="region")
            detail["unnamed"] = r.get("unnamed") or []
            detail["split"] = r.get("split") or ""
            detail["quad"] = r.get("quad") or {}
            _tip = ""
            if pgmap:
                _pgs = sorted(pgmap)
                _tip = ("；识别到 %d 页图纸（PDF 第 %d~%d 页），已按底图顺序重编号 1~%d"
                        % (len(pgmap), _pgs[0], _pgs[-1], len(pgmap)))
            if detail["split"]:
                _tip += "；" + detail["split"]
            if _lr_quad_note:
                _tip += _lr_quad_note(detail["quad"])
            _tip += avoid_note(detail)
            return True, ("识别结果：LBD %d 个（位置=识别到的 LBD 区域框中心）"
                          " + 支架号 %d 个（按 LBD 分组编号：默认行优先，选了象限规则就按象限走）%s"
                          % (r["lbd"], r["str"], _tip)), detail

    # 3) LBD 行不再由这里从 PDF 文字层提（标注工具已经提好了，名字/位置都在 JSON 里）。
    #    走到这儿说明「按区域填标签」那条没成：要么开关关了，要么 JSON 里没有可用的名字。
    lbd_err = ""

    # 支架号：debug JSON 现编（按 LBD 分组、组内行优先，每组从 01 起）
    rack_err = ""
    if kind == "debug" and _lr_rack_lines is not None:
        try:
            _sinfo = {}
            rl, nstr, _np = _lr_rack_lines(jp, pre, page_map=pgmap, order=order,
                                           split=split, info=_sinfo, align=align, avoid=avoid,
                                           avoid_pad=_avoid_pad,
                                           quad_rule=quad_rule, quad_map=quad_map)
            detail["split"] = _sinfo.get("split") or ""
            detail["quad"] = _sinfo.get("quad") or {}
        except Exception as e:
            rl, nstr, rack_err = [], 0, str(e)
        if rl:
            try:
                tail = ""
                if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                    with open(out_path, "r", encoding="utf-8") as f:
                        tail = f.read()[-1:]
                with open(out_path, "a", encoding="utf-8") as f:
                    if tail and tail not in ("\n", "\r"):
                        f.write("\n")
                    f.write("\n".join(rl) + "\n")
                detail["str"] = nstr
            except Exception as e:
                rack_err = str(e)

    # 兜底：上面那条没给出 LBD 行（开关关了 / 区域那套没成）时，用 debug JSON 的区域中心
    if detail["lbd"] == 0 and kind == "debug" and _lr_extract_debug is not None:
        # 注意要带 page_map：这条兜底同样要按「底图顺序号」写页号，
        # 漏了它（以前就是漏的）行会写成 JSON 里的原始页号，CAD 那边一张都对不上。
        r = _lr_extract_debug(jp, out_path, prefix=pre, page_map=pgmap,
                              order=order, split=split,
                              align=align, avoid=avoid, avoid_pad=_avoid_pad,
                              quad_rule=quad_rule, quad_map=quad_map)
        detail["split"] = r.get("split") or detail.get("split") or ""
        detail["quad"] = r.get("quad") or {}
        if r.get("ok"):
            detail["lbd"], detail["str"] = r["lbd"], r["str"]
            detail["unnamed"] = r.get("unnamed") or []
            _stip = ("；" + detail["split"]) if detail.get("split") else ""
            if _lr_quad_note:
                _stip += _lr_quad_note(detail["quad"])
            _stip += avoid_note(detail)
            return True, ("识别结果 JSON：%d 页、LBD %d 个（按区域中心）、支架号 %d 个"
                          "（位置按识别到的 LBD 区域中心放）%s"
                          % (r["pages"], r["lbd"], r["str"], _stip)), detail
        lbd_err = lbd_err or (r.get("error") or "")

    if detail["lbd"] == 0 and detail["str"] == 0:
        why = lbd_err or rack_err or ("这份 JSON 不是识别结果，也不是标注结果（没有 Node/Tracker 也没有 shapes）"
                                      if jp else "没有给识别 / 标注结果 JSON"
                                                 "（LBD 标签由标注工具提好放在 JSON 里带进来）")
        return False, "没能生成任何标签行：%s" % why, detail
    tip = ""
    if pgmap:
        _pgs = sorted(pgmap)
        if _pgs[-1] - _pgs[0] + 1 == len(_pgs):
            _rng = "PDF 第 %d~%d 页" % (_pgs[0], _pgs[-1])
        else:
            _rng = "%d 页（PDF 第 %d~%d 页，中间有跳页）" % (len(_pgs), _pgs[0], _pgs[-1])
        tip = "；识别到 %d 页图纸（%s），已按底图顺序重编号 1~%d —— 请确认 CAD 里正好是这些页、顺序一致" \
              % (len(pgmap), _rng, len(pgmap))
    if detail.get("split"):
        tip += "；" + detail["split"]
    if _lr_quad_note:
        tip += _lr_quad_note(detail.get("quad"))
    tip += avoid_note(detail)
    return True, ("标签 %d 行：LBD %d 个（来自识别 / 标注结果 JSON）"
                  " + 支架号 %d 个（按 LBD 分组编号：默认行优先，选了象限规则就按象限走）%s"
                  % (detail["lbd"] + detail["str"], detail["lbd"], detail["str"], tip)), detail


def prepare_region_file(cfg, extra_dirs=()):
    """按识别结果写「每页 LBD 区域上下限」文件，给 CAD 侧生成布局后对准视口用。

    返回 (文件路径, 一行说明)。拿不到识别结果时路径是空串，CAD 侧就按整页对准。
    """
    if _lr_write_regions is None:
        return "", "区域对准：缺少 lbd_regions.py，视口按整页对准"
    try:
        cands = _lr_candidates(cfg, extra_paths=extra_dirs)
    except Exception as e:
        return "", "区域对准：查找识别结果出错 %s（视口按整页对准）" % e
    if not cands:
        return "", "区域对准：没找到识别结果 JSON，视口按整页对准"
    out = os.path.join(tempfile.gettempdir(), "pdflbd_regions.txt")
    # 布局名来自 Excel 分表顺序，所以区域文件也按分表顺序写，保证 R 行与布局一一对应
    try:
        sheets, _nmsg = plan_names(cfg)
    except Exception:
        sheets = []
    last_err = ""
    for jp in cands:                       # 依次试，挑第一份能读出来的
        try:
            if sheets and _lr_write_regions_sheets is not None:
                r = _lr_write_regions_sheets(jp, out, sheets)
            else:
                r = _lr_write_regions(jp, out, page_start=cfg.get("pageStart", 1),
                                      count=cfg.get("count", 0))
        except Exception as e:
            last_err = str(e)
            continue
        if r.get("ok"):
            # 把"用了哪份 JSON、第几张对应 PDF 哪页"写进日志 —— 视口没对准时一眼能看出错在哪
            _tip = ""
            try:
                _pm = _lr_page_map(jp) if _lr_page_map else None
                if _pm:
                    _order = [p for p, _n in sorted(_pm.items(), key=lambda kv: kv[1])]
                    _tip = "；第 1~%d 张 = PDF 第 %s 页" % (
                        min(3, len(_order)),
                        "/".join(str(p) for p in _order[:3]))
            except Exception:
                pass
            return out, ("区域对准：用 %s；按分表顺序 %d 个布局，%d 个匹配到 LBD 区域%s"
                         " → 生成布局后按区域上下限调视口大小%s"
                         % (os.path.basename(jp), r["pages"], r["with_region"],
                            ("（%d 个分表没匹配到，按整页对准）" % len(r.get("miss") or []))
                            if r.get("miss") else "", _tip))
        last_err = r.get("error") or last_err
    return "", "区域对准：%s（视口按整页对准）" % (last_err or "读取失败")


def read_xlsx_sheet_names(path):
    """按表顺序读出 LBD Excel 的分表名（xlsx 的工作表名）。
    只解压 xl/workbook.xml，不依赖 Excel 或第三方库，用于界面预览。"""
    p = (path or "").strip()
    if not p or not os.path.exists(p):
        return []
    try:
        import zipfile
        import xml.etree.ElementTree as _ET
        with zipfile.ZipFile(p) as z:
            root = _ET.fromstring(z.read("xl/workbook.xml"))
        out = []
        for el in root.iter():
            if el.tag == "sheet" or el.tag.endswith("}sheet"):
                nm = (el.get("name") or "").strip()
                if nm:
                    out.append(nm)
        return out
    except Exception:
        return []


def xlsx_sheet_names_report(path):
    """读分表名，并把失败原因说清楚（路径不存在 / 老 .xls / 被占用 / 没工作表）。

    返回 (names, why)：names 非空时 why 为空字符串。
    """
    p = (path or "").strip().strip('"').strip("'")
    if not p:
        return [], "请先在“文件与输出”里选择标签文件(xlsx)"
    if not os.path.exists(p):
        return [], "这个路径不存在：%s" % p
    try:
        import zipfile
        ok_zip = zipfile.is_zipfile(p)
    except Exception as e:
        return [], "打不开这个文件（可能正被 Excel 占用）：%s（%s）" % (os.path.basename(p), e)
    if not ok_zip:
        return [], ("不是 .xlsx 格式（老 .xls 请先在 Excel 里「另存为 .xlsx」）：%s"
                    % os.path.basename(p))
    names = read_xlsx_sheet_names(p)
    if not names:
        return [], "%s 里没有工作表名（文件可能被加密或损坏）" % os.path.basename(p)
    return names, ""

def read_xlsx_lbd_labels(path):
    """LBD Excel -> {分表名(大写): {LBD编号: 名称串长度}}。

    规则和插件 PdfLayout_ReadAllLbdLabels 一样：每行 A 列是 LBD 名（"LBD-15"，
    空的续行归上一个 LBD），C 列是 Item Code；同一个 LBD 下多个 Item Code 在图上
    是用 "/" 连起来画的一串（见 PdfLayout_JoinLabelsList），所以长度 =
    各段长度之和 + 段数 - 1。给 STR 号避让 CAD 里画的 LBD 标签用。
    只认 xlsx（zip 格式）；.xls 老格式读不了，返回 {}（CAD 那边照旧能画）。
    """
    p = (path or "").strip()
    out = {}
    if not p or not os.path.exists(p) or not p.lower().endswith(".xlsx"):
        return out
    try:
        import zipfile
        import xml.etree.ElementTree as _ET
        NM = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        RN = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
        with zipfile.ZipFile(p) as z:
            have = set(z.namelist())

            def _read(nm_):
                return z.read(nm_) if nm_ in have else None

            wb = _ET.fromstring(_read("xl/workbook.xml"))
            rels = _ET.fromstring(_read("xl/_rels/workbook.xml.rels"))
            rid2t = {r.get("Id"): r.get("Target") for r in rels}
            shared = []
            sst = _read("xl/sharedStrings.xml")
            if sst is not None:
                for si in _ET.fromstring(sst):
                    shared.append("".join(t.text or "" for t in si.iter(NM + "t")))
            for el in wb.iter():
                if not el.tag.endswith("}sheet"):
                    continue
                sheet = (el.get("name") or "").strip()
                tgt = (rid2t.get(el.get(RN + "id")) or "").lstrip("/")
                if not sheet or not tgt:
                    continue
                if not tgt.startswith("xl/"):
                    tgt = "xl/" + tgt
                data = _read(tgt)
                if data is None:
                    continue
                cells = {}
                for row in _ET.fromstring(data).iter(NM + "row"):
                    rn = int(row.get("r") or 0)
                    for c in row:
                        if c.tag != NM + "c":
                            continue
                        ref = c.get("r") or ""
                        col = re.match(r"[A-Z]+", ref)
                        col = col.group(0) if col else ""
                        if col not in ("A", "C"):
                            continue
                        typ = c.get("t")
                        v = c.find(NM + "v")
                        val = ""
                        if typ == "s" and v is not None:
                            try:
                                val = shared[int(v.text)]
                            except Exception:
                                val = ""
                        elif typ == "inlineStr":
                            ins = c.find(NM + "is")
                            val = ("".join(x.text or "" for x in ins.iter(NM + "t"))
                                   if ins is not None else "")
                        else:
                            val = v.text if v is not None else ""
                        cells.setdefault(rn, {})[col] = (val or "").strip()
                cur = None
                for rn in sorted(cells):
                    a = cells[rn].get("A", "")
                    cval = cells[rn].get("C", "")
                    if not cval:
                        continue
                    m = re.search(r"LBD[^0-9]*(\d+)", a, re.I) if a else None
                    if m:
                        cur = int(m.group(1))
                    if cur is None:
                        continue
                    out.setdefault(sheet.upper(), {}).setdefault(cur, []).append(cval)
    except Exception:
        return {}
    return {sh: {n: (sum(len(x) for x in v) + len(v) - 1) for n, v in d.items()}
            for sh, d in out.items()}


def plan_names(cfg):
    """布局命名：只用 LBD Excel 的分表名（按表顺序），数量按“复制数量”截取。
    返回 (布局名列表, 说明文字)。读不到分表名时返回空列表（说明里写清原因）。"""
    sheets, why = xlsx_sheet_names_report(cfg.get("xlsx"))
    if not sheets:
        return [], "读不到分表名：%s" % (why or "请先在“文件与输出”里选择标签文件(xlsx)")
    try:
        cnt = int(str(cfg.get("count") or "0").strip() or 0)
    except Exception:
        cnt = 0
    if cnt <= 0:
        return list(sheets), "复制数量未定，按分表数 %d 个" % len(sheets)
    if cnt > len(sheets):
        return list(sheets), "复制数量 %d 多于分表数 %d，只能命名 %d 个" % (cnt, len(sheets), len(sheets))
    return list(sheets[:cnt]), "复制 %d 个 / 分表共 %d 个" % (cnt, len(sheets))


def ensure_auto_lsp():
    cand = None
    if getattr(sys, "frozen", False):
        cand = os.path.join(getattr(sys, "_MEIPASS", ""), "PdfLayout_auto.lsp")
    if not cand or not os.path.exists(cand):
        cand = os.path.join(app_dir(), "PdfLayout_auto.lsp")
    if not os.path.exists(cand):
        return None
    tmp = os.path.join(tempfile.gettempdir(), "PdfLayout_auto.lsp")
    try:
        with open(cand, "rb") as f:
            data = f.read()
        with open(tmp, "wb") as f:
            f.write(data)
    except Exception:
        return cand
    return tmp


def ensure_main_lsp():
    # 与 ensure_auto_lsp 等价：把 exe 内嵌的主 PdfLayout.lsp 解到临时目录，
    # 供运行时加载，避免依赖用户本地的源码路径。
    cand = None
    if getattr(sys, "frozen", False):
        cand = os.path.join(getattr(sys, "_MEIPASS", ""), "PdfLayout.lsp")
    if not cand or not os.path.exists(cand):
        cand = os.path.join(app_dir(), "PdfLayout.lsp")
    if not os.path.exists(cand):
        return None
    tmp = os.path.join(tempfile.gettempdir(), "PdfLayout.lsp")
    try:
        with open(cand, "rb") as f:
            data = f.read()
        with open(tmp, "wb") as f:
            f.write(data)
    except Exception:
        return cand
    return tmp


def lsp_supports_region_inset(path):
    """这个 PdfLayout.lsp 认不认界面的「区域对准留白」（*PdfLayout_ViewInset*）。

    判据是插件里的能力标记 *PdfLayout_LspFeatures* 含 viewinset：
    老插件（比如 2.17.14 那份）虽然也有这个全局变量，但算法把系数约掉了，
    光看变量名认不出来 —— 配上去就是「留白怎么改都不动」。认不出就改用内置插件。
    """
    try:
        with open(path, "rb") as f:
            data = f.read()
    except Exception:
        return False
    return b"*PdfLayout_LspFeatures*" in data and b"viewinset" in data


def ensure_ai_lsp():
    # 解出 PdfLayout_ai.lsp(读标签文件并在 CAD 里画 LBD/STR)
    cand = None
    if getattr(sys, "frozen", False):
        cand = os.path.join(getattr(sys, "_MEIPASS", ""), "PdfLayout_ai.lsp")
    if not cand or not os.path.exists(cand):
        cand = os.path.join(app_dir(), "PdfLayout_ai.lsp")
    if not os.path.exists(cand):
        cand = r"C:\Users\szk\Desktop\MAP-CAD\PdfLayout插件包\PdfLayout_ai.lsp"
    if not os.path.exists(cand):
        return None
    tmp = os.path.join(tempfile.gettempdir(), "PdfLayout_ai.lsp")
    try:
        with open(cand, "rb") as f:
            data = f.read()
        with open(tmp, "wb") as f:
            f.write(data)
    except Exception:
        return cand
    return tmp


def auto_worker(cfg, ini, prog, bus):
    try:
        # B2：标签文件在 exe 内就地生成（复用已打包的 pypdf / lbd_regions），不再外挂 Python。
        # LBD 名字和位置不再从这里翻 PDF 文字层：标注工具的「补全编号」已经提好、
        # 写进识别/标注结果 JSON 了，这一步只把 JSON 转成 CAD 认的 P/L 行。
        lbd_pre = str(cfg.get("lbdPre", "0"))
        lbd_out = (cfg.get("lbdOut") or "").strip()
        if lbd_pre == "1" and lbd_out:
            bus.prog.emit("0/4 正在生成 LBD / 支架标签…")
            logp = os.path.join(tempfile.gettempdir(), "pdflbd_log.txt")
            progx = os.path.join(tempfile.gettempdir(), "pdflbd_progress.txt")
            _jp = (cfg.get("jsonPath") or "").strip()
            if _jp and os.path.exists(_jp):
                try:
                    bus.prog.emit("0/4 读取识别 / 标注结果 JSON…")
                    _hn = rack_len_hint_note(cfg)
                    if _hn:
                        bus.prog.emit("0/4 支架类型长度FT：" + _hn)
                    bus.prog.emit("0/4 正在生成标签（LBD 名字/位置来自 JSON，支架号按 LBD 分组编号）…")
                    ok, _emsg, _edet = build_extract_file(cfg, lbd_out, progx)
                    bus.prog.emit("0/4 " + _emsg)
                    _un = (_edet or {}).get("unnamed") or []
                    if _un:
                        _by = {}
                        for _pg, _i in _un:
                            _by[_pg] = _by.get(_pg, 0) + 1
                        bus.prog.emit("0/4 注意：%s 有 LBD 框但没配上名字，标签不会画 —— "
                                      "回识别页选中那个 LBD 框改名再重跑"
                                      % "、".join("第 %s 页 %d 个" % (k, v)
                                                 for k, v in sorted(_by.items())))
                    err = "" if ok else _emsg
                except Exception as e:
                    ok, err = False, "JSON解析失败:" + str(e)
            else:
                # 没有 JSON 就没得可生成：LBD 标签由标注工具（读 PDF 文字层的「补全编号」）提好、
                # 写进识别/标注结果 JSON 里带过来，主程序这边不再自己去翻 PDF。
                ok, err = False, ("没有给识别 / 标注结果 JSON：LBD 标签由标注工具从 PDF 文字层"
                                  "提好放在 JSON 里，主程序不再单独提 PDF")
            if not ok:
                try:
                    with open(logp, "w", encoding="utf-8") as f:
                        f.write(err)
                except Exception:
                    pass
        # 支架类型：从识别结果 JSON 自动读（填「支架」页明细行 + 补写 ini，CAD 侧这次就能读到）。
        # 支架拆分用的「长度FT」在生成标签那一步用（build_extract_file -> apply_rack_len_hints）。
        _rackauto = str(cfg.get("rackAuto", "1")).strip() not in ("0", "", "关", "否", "off", "false", "False")
        if _rackauto:
            _rt = []
            for _jp in (_lr_candidates(cfg, extra_paths=[lbd_out]) if _lr_candidates else []):
                try:
                    _rt = _lr_rack_types(_jp) if _lr_rack_types else []
                except Exception:
                    _rt = []
                if _rt:
                    break
            if _rt:
                bus.racks.emit(_rt)              # 界面「支架」页明细行自动填上
                _rtext = _lr_rack_text(_rt) if _lr_rack_text else ""
                if _rtext:
                    cfg["rackTypes"] = _rtext
                    try:
                        write_auto_ini(cfg, ini)  # 补写 ini, LSP 这一次就能读到支架类型
                    except Exception as e:
                        bus.prog.emit("支架类型写入 ini 失败：" + str(e))

        # 布局生成后按 LBD 区域上下限对准视口：先把区域范围文件写出来，再补写一次 ini
        _rfile = ""
        if cfg.get("regionFit", True):
            _rfile, _rmsg = prepare_region_file(cfg, extra_dirs=[lbd_out])
            bus.prog.emit(_rmsg)
        cfg["regionFile"] = _rfile
        try:
            write_auto_ini(cfg, ini)
        except Exception as e:
            bus.prog.emit("区域范围写入 ini 失败：" + str(e))

        try:
            import pythoncom
            import win32com.client as win32
        except Exception as e:
            bus.err.emit("连接 CAD 需要 pywin32（pythoncom / win32com），这个 Python 里没有：%s\n"
                         "  源码运行：pip install pywin32\n"
                         "  打包版：打包用的那个 Python 也要装 pywin32，装完重新打包" % e)
            return
        pythoncom.CoInitialize()
        bus.prog.emit("1/4 连接/启动 CAD…")
        conn_stop = threading.Event()

        def _tick_conn_wait():
            t0 = time.time()
            while not conn_stop.is_set():
                el = int(time.time() - t0)
                bus.status.emit("正在连接 / 启动 ZWCAD… 已等待 %d 秒"
                                "（冷启动通常 10-30 秒；若已打开 ZWCAD 可秒连）" % el)
                conn_stop.wait(1.0)

        threading.Thread(target=_tick_conn_wait, daemon=True).start()
        acad = None
        for progid in ("ZWCAD.Application", "AutoCAD.Application"):
            try:
                acad = win32.GetActiveObject(progid)
            except Exception:
                acad = None
            if not acad:
                try:
                    acad = win32.DispatchEx(progid)
                except Exception:
                    acad = None
            if acad:
                break
        conn_stop.set()
        if not acad:
            bus.err.emit("连接 CAD 失败：请确认已安装 ZWCAD/AutoCAD 并注册 COM。")
            return
        try:
            acad.Visible = True
        except Exception:
            pass
        bus.prog.emit("2/4 已连接，准备打开 DWG…")
        doc = None
        dwg = (cfg.get("dwg") or "").strip()
        try:
            cur = acad.ActiveDocument
            cname = ""
            try:
                cname = cur.FullName or ""
            except Exception:
                cname = ""
            if dwg and os.path.exists(dwg):
                cur_match = cname and os.path.exists(cname) and \
                    cname.replace("\\", "/").lower() == dwg.replace("\\", "/").lower()
                if cur_match:
                    doc = cur
                else:
                    try:
                        doc = acad.Documents.Open(dwg)
                    except Exception:
                        doc = cur
            else:
                doc = getattr(acad, "ActiveDocument", None)
        except Exception:
            doc = None
        if not doc:
            bus.err.emit("无活动文档或无法打开 DWG")
            return
        bus.prog.emit("3/4 DWG 就绪，加载插件并执行…")
        lsp = (cfg.get("lspPath") or "").strip()
        # 配置里可能留着老版插件（比如以前在桌面上放着的那份）：
        # 老版认不出「区域对准留白」，「留白」改了也不生效 → 这次改用内置插件。
        if lsp and os.path.exists(lsp) and not lsp_supports_region_inset(lsp):
            bus.prog.emit("提示：%s 是旧版插件（不认「区域对准留白」），本次改用程序内置的 PdfLayout.lsp。"
                          % lsp)
            lsp = ""
        if not lsp or not os.path.exists(lsp):
            lsp = ensure_main_lsp()
        if not lsp:
            bus.err.emit("找不到内置 PdfLayout.lsp")
            return
        auto = ensure_auto_lsp()
        if not auto:
            bus.err.emit("找不到 PdfLayout_auto.lsp")
            return

        def L(p):
            return '"' + p.replace("\\", "/") + '"'

        ai = ensure_ai_lsp()
        _lbdout = (cfg.get("lbdOut") or "").strip()
        # 区域对准留白：CAD 侧按 *PdfLayout_ViewInset* 把「LBD 区域范围」缩放进视口。
        # 100 = 铺满视口（最大）；越小图纸越小、四周留白越多（95 = 上一版，90 = 现在默认）。
        try:
            _vins = float(str(cfg.get("regionInset", "90")).strip() or 90)
        except Exception:
            _vins = 90.0
        _vins = max(50.0, min(100.0, _vins)) / 100.0
        _vinsnip = "(setq *PdfLayout_ViewInset* %.4f)\n" % _vins
        bus.prog.emit("区域对准留白：%.1f%%（发给 CAD 的 *PdfLayout_ViewInset* = %.3f；"
                      "100%% = 铺满视口，越小图纸越小、四周留白越多）" % (_vins * 100.0, _vins))
        # LBD 标签字高统一用「PDF 与标签」页的「标签高度」那格（默认 0.25 模型单位，可调）；
        # 插件里按区域宽算字高的那套（*PdfLayout_LbdRegionScale*）保持关闭(0)。
        try:
            _thv = float(str(cfg.get("textHeight", "0.25")).strip() or 0)
        except Exception:
            _thv = 0.25
        bus.prog.emit("LBD 标签字高：按「标签高度」那格（%s）"
                      % ("自动" if _thv <= 0 else "%.3g 模型单位" % _thv))
        # *PdfLayout_AiPage* = 0 → CAD 侧逐页画 STR 号（第 i 张底图配第 i 页）；
        # 以前这里传的是起始页，结果只有一页会画上支架号。
        _pg = "0"
        if ai:
            # STR 号背景填充：UI 设置 -> LISP 全局变量(*PdfLayout_AiStrBgOn/Color/Gap)
            _sbg_on = "nil" if str(cfg.get("strBgOn", "1")).strip() in ("0", "", "关", "否", "off", "false", "False") else "T"
            # 画完之后那步「LBD 标签避让 STR 号」要不要跑（卡死时可以关掉）
            try:
                _sbg_c = int(float(str(cfg.get("strBgColor", "1")).strip() or 1))
            except Exception:
                _sbg_c = 1
            try:
                _sbg_g = float(str(cfg.get("strBgGap", "1.0")).strip() or 1.0)
            except Exception:
                _sbg_g = 1.0
            _rp = rack_prefix(cfg).replace('"', "")      # 支架号前缀：LISP 端按它认支架号
            # STR 号字高 = typical 条带宽（支架框短边）的倍数：「支架」页那格填倍数，默认 1.4。
            # CAD 端字高 = 支架框短边 x *PdfLayout_AiStrScale*(这个倍数)，见 PdfLayout_ai.lsp。
            # 「标签高度」那一格只管 LBD 标签，不动 STR 号。
            try:
                _shv = float(str(cfg.get("strHeight", "1.4")).strip() or 1.4)
            except Exception:
                _shv = 1.4
            if not (_shv > 0):
                _shv = 1.4
            _auto_h, _txt_h, _scale = "T", "0.15", ("%.6g" % _shv)
            # 标签字色（ACI 色号）：STR 用 *PdfLayout_AiStrColor*；
            # LBD 标签由 PdfLayout_auto.lsp 画，主用 ini 的 labelTextColor，
            # 这里再发一份 *PdfLayout_AiLabelColor*，万一由 AI 侧画 LBD 也能上色。
            try:
                _ltc = int(float(str(cfg.get("labelTextColor", "7")).strip() or 7))
            except Exception:
                _ltc = 7
            try:
                _stc = int(float(str(cfg.get("strTextColor", "7")).strip() or 7))
            except Exception:
                _stc = 7
            _strbg = ("(setq *PdfLayout_AiStrBgOn* %s)\n"
                      "(setq *PdfLayout_AiStrBgColor* %s)\n"
                      "(setq *PdfLayout_AiStrBgGap* %s)\n"
                      "(setq *PdfLayout_AiStrPrefix* \"%s\")\n"
                      "(setq *PdfLayout_AiStrScale* %s)\n"
                      "(setq *PdfLayout_AiStrAutoH* %s)\n"
                      "(setq *PdfLayout_AiTextH* %s)\n"
                      "(setq *PdfLayout_AiStrColor* %s)\n"
                      "(setq *PdfLayout_AiLabelColor* %s)\n"
                      % (_sbg_on, _sbg_c, _sbg_g, _rp, _scale, _auto_h, _txt_h, _stc, _ltc))
            cmd = ("(load %s)\n(load %s)\n(load %s)\n"
                   "%s"
                   "(setq *PdfLayout_GridAutoFile* %s)\n(setq *PdfLayout_AiPage* %s)\n"
                   "%s"
                   "(PdfLayout_AutoRun %s %s)\n(c:pdfgridai)\n(PdfLayout_Prog \"RUN_DONE\")\n"
                   % (L(lsp), L(auto), L(ai), _vinsnip, L(_lbdout), _pg, _strbg,
                      L(ini), L(prog)))
        else:
            cmd = ("(load %s)\n(load %s)\n%s(PdfLayout_AutoRun %s %s)\n(PdfLayout_Prog \"RUN_DONE\")\n"
                   % (L(lsp), L(auto), _vinsnip, L(ini), L(prog)))
        bus.prog.emit("发送命令给 ZWCAD：\n" + cmd.replace("\n", " "))
        doc.SendCommand(cmd)
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
    except Exception as e:
        bus.err.emit("执行出错：" + str(e))


def ver_tuple(s):
    """把 v1.2.3 / 1.2 之类转成可比较的元组。"""
    nums = re.findall(r"\d+", str(s or ""))
    return tuple(int(x) for x in nums[:3]) if nums else (0,)


def asset_key(name):
    """附件名归一化：GitHub 会把空格换成点（Voltage-CAD.MAP.exe），所以忽略所有非字母数字。"""
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


def http_get(url, timeout=15):
    """带 UA 的 GET（GitHub API 要求 User-Agent）。"""
    import urllib.request
    req = urllib.request.Request(url, headers={
        "User-Agent": "%s/%s" % (APP_TITLE, APP_VERSION),
        "Accept": "application/vnd.github+json",
    })
    return urllib.request.urlopen(req, timeout=timeout)


# ---- 更新包下载：GitHub 直连在国内常年几十 KB/s 甚至被重置，这里先测速再挑源 ----
# 顺序只是备选清单，真正用哪个由测速决定；最后一项 "" 是直连。
DOWNLOAD_MIRRORS = (
    "https://gh-proxy.com/",
    "https://ghfast.top/",
    "https://ghproxy.net/",
    "",
)
PROBE_BYTES = 1024 * 1024        # 每个源先下 1MB 测速
IDLE_TIMEOUT = 20                # 连续这么多秒没有新数据就当卡住，换源


def dl_headers(extra=None):
    h = {"User-Agent": "%s/%s" % (APP_TITLE, APP_VERSION),
         "Accept": "application/octet-stream"}
    if extra:
        h.update(extra)
    return h


def short_url(u):
    """日志里用：只保留主机名，免得整条签名地址糊满日志。"""
    try:
        return urllib.parse.urlsplit(u).netloc or u
    except Exception:
        return u


def probe_speed(url, probe_bytes=PROBE_BYTES, timeout=6, max_secs=3):
    """下 probe_bytes 字节测速，返回「下满这些字节大约要几秒」；不通返回 None。

    慢源不能干等：超过 max_secs 就按已经下到的字节折算，免得一个死慢的镜像
    把测速阶段拖成几分钟。
    """
    import urllib.request
    req = urllib.request.Request(
        url, headers=dl_headers({"Range": "bytes=0-%d" % (probe_bytes - 1)}))
    t0 = time.time()
    got = 0
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            while got < probe_bytes:
                chunk = r.read(65536)
                if not chunk:
                    break
                got += len(chunk)
                if time.time() - t0 > max_secs:
                    break
    except Exception:
        return None
    if got <= 0:
        return None
    return (time.time() - t0) * probe_bytes / float(got)


def pick_sources(url, log=None):
    """把各个镜像 + 直连测速排序，返回 [(地址, 耗时秒或 None), ...]，最快的排前面。

    几个源同时测，不然串行等慢源会很久。
    """
    cands = [(url if not p else p + url) for p in DOWNLOAD_MIRRORS]
    result = {}

    def worker(u):
        result[u] = probe_speed(u)

    threads = [threading.Thread(target=worker, args=(u,), daemon=True) for u in cands]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    scored = [(u, result.get(u)) for u in cands]
    if log:
        for u, sec in scored:
            log("测速 %s：%s" % (short_url(u),
                                ("约 %.1f 秒 / 1MB" % sec) if sec else "不通"))
    scored.sort(key=lambda x: (x[1] is None, x[1] or 0))
    return scored


def fetch_into(src, part, got, total, progress=None, detail=None):
    """从 src 把数据续写到 part；返回 (已下载字节, 总字节)。

    连接断开或卡住（IDLE_TIMEOUT 秒没有新数据）会抛异常，交给调用方换源。
    """
    import urllib.request
    headers = dl_headers({"Range": "bytes=%d-" % got} if got else None)
    mode = "ab" if got else "wb"
    req = urllib.request.Request(src, headers=headers)
    with urllib.request.urlopen(req, timeout=IDLE_TIMEOUT) as r:
        code = getattr(r, "status", 200) or 200
        if got and code != 206:          # 这个源不认 Range：只能从头下
            got = 0
            mode = "wb"
        try:
            clen = int(r.headers.get("Content-Length") or 0)
        except Exception:
            clen = 0
        if clen:
            total = clen + (got if code == 206 else 0)
        t0 = time.time()
        with open(part, mode) as f:
            while True:
                chunk = r.read(262144)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if progress and total:
                    progress(int(got * 100 / total))
                if detail:
                    speed = got / max(0.001, time.time() - t0)
                    detail("%.1f/%.1fMB  %.0fKB/s"
                           % (got / 1048576.0, (total or 0) / 1048576.0, speed / 1024.0))
    return got, total


def download_file(url, dest, progress=None, detail=None, log=None, key=""):
    """下载 url 到 dest：先测速选源，中途卡住/断开就换源续传。

    进度：progress(百分比)、detail(「已下 12.3/68.7MB 1.2MB/s」)；log(一行日志)。
    下载先写 <dest>.<key>.part，下完再改名，所以中断了下次能接着下。
    """
    part = "%s.%s.part" % (dest, key) if key else (dest + ".part")
    got = os.path.getsize(part) if os.path.exists(part) else 0
    total = 0
    sources = [s for s, _ in pick_sources(url, log=log)]
    errors = []
    for _round in range(3):
        for src in list(sources):
            try:
                if log:
                    log("从 %s 下载…（已有 %.1fMB）" % (short_url(src), got / 1048576.0))
                got, total = fetch_into(src, part, got, total, progress, detail)
            except Exception as e:
                # 断开时 fetch_into 没来得及返回，已下的字节数在 part 文件里，得自己捡回来
                try:
                    if os.path.exists(part):
                        got = os.path.getsize(part)
                except Exception:
                    pass
                errors.append("%s: %s" % (short_url(src), e))
                if log:
                    log("  %s 断了（%s）；已下 %.1fMB，这里排到最后，换个源接着下"
                        % (short_url(src), e, got / 1048576.0))
                # 这个源刚断过，后面的轮次里放最后再试
                if src in sources:
                    sources.remove(src)
                    sources.append(src)
                continue
            if not total or got >= total:      # 没有 Content-Length 时按「读完了」算完成
                if os.path.exists(dest):
                    try:
                        os.remove(dest)
                    except Exception:
                        pass
                os.replace(part, dest)
                if detail:
                    detail("下载完成 %.1fMB" % (os.path.getsize(dest) / 1048576.0))
                if log:
                    log("下载完成：%s（%.1fMB）"
                        % (dest, os.path.getsize(dest) / 1048576.0))
                for stale in glob.glob(dest + ".*.part"):     # 清掉别的版本的半截文件
                    if os.path.abspath(stale) != os.path.abspath(part):
                        try:
                            os.remove(stale)
                        except Exception:
                            pass
                return dest
        if total and got >= total:
            break
    raise RuntimeError("下载没完成（已下 %s / %s）：%s"
                       % (got, total or "未知", "；".join(errors[-3:]) or "所有源都不通"))


def fmt_time(iso):
    """GitHub 的 ISO 时间 -> 本地 2026-09-14 20:05。"""
    import datetime
    s = str(iso or "").strip()
    if not s:
        return ""
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:
        return s


def fetch_release():
    """查 GitHub 最新 release。返回 (info, 错误)；info=None 表示查不到。
    info = {version, notes, url, published, page}；version 为空表示仓库还没发过版本。"""
    try:
        with http_get(UPDATE_API) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # 还没发布过任何版本：视作“已是最新”，不报错
            return {"version": "", "notes": "", "url": "", "published": "", "page": UPDATE_PAGE}, ""
        return None, "检查更新失败：HTTP %s" % e.code
    except Exception as e:
        return None, "检查更新失败（网络或仓库不可达）：%s" % e
    tag = (data.get("tag_name") or "").strip()
    notes = (data.get("body") or "").strip()
    url = ""
    want = asset_key(UPDATE_ASSET)
    for a in (data.get("assets") or []):
        if asset_key(a.get("name")) == want:
            url = a.get("browser_download_url") or ""
            break
    if not url:
        for a in (data.get("assets") or []):
            if (a.get("name") or "").lower().endswith(".exe"):
                url = a.get("browser_download_url") or ""
                break
    return ({
        "version": tag,
        "notes": notes,
        "url": url,
        "published": fmt_time(data.get("published_at")),
        "page": (data.get("html_url") or UPDATE_PAGE),
    }, "")


def update_check_worker(bus):
    info, err = fetch_release()
    if err or not info:
        bus.upd_error.emit(err)
        return
    tag = info.get("version") or ""
    if tag and ver_tuple(tag) > ver_tuple(APP_VERSION):
        bus.upd_found.emit(tag, info.get("notes") or "", info.get("url") or "",
                           info.get("published") or "")
    else:
        bus.upd_none.emit(tag or ("v" + APP_VERSION), info.get("notes") or "",
                          info.get("published") or "")


def update_notes_worker(bus):
    """只看更新日志（不关心要不要更新）。"""
    info, err = fetch_release()
    if err or not info:
        bus.upd_error.emit(err)
        return
    tag = info.get("version") or ""
    bus.upd_notes.emit(tag, info.get("notes") or "", info.get("published") or "",
                       bool(tag) and ver_tuple(tag) > ver_tuple(APP_VERSION))


def update_download_worker(url, bus):
    try:
        d = os.path.join(tempfile.gettempdir(), "VCADMAP_update")
        os.makedirs(d, exist_ok=True)
        dest = os.path.join(d, UPDATE_ASSET)
        # 半截文件按下载地址区分：换了版本就从新的一份开始，不会拿旧版残留续传
        key = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]
        download_file(url, dest,
                      progress=lambda p: bus.upd_progress.emit(p),
                      detail=lambda t: bus.upd_detail.emit(t),
                      log=lambda m: bus.upd_log.emit(m),
                      key=key)
        bus.upd_ready.emit(dest)
    except Exception as e:
        bus.upd_error.emit("下载更新失败：%s" % e)


def apply_update(new_exe):
    """写一个替换脚本：等本程序退出 -> 覆盖原 exe -> 重启。返回 (是否已启动, 提示)。"""
    if not getattr(sys, "frozen", False):
        return False, ("当前是源码方式运行，不能自动替换程序。\n"
                       "可以手动下载新版本：\n%s\n%s" % (new_exe, UPDATE_PAGE))
    target = os.path.abspath(sys.executable)
    bat = os.path.join(tempfile.gettempdir(), "vcadmap_apply_update.bat")
    lines = [
        "@echo off",
        "setlocal",
        'set "TARGET=%~1"',
        'set "NEW=%~2"',
        'echo [update] %DATE% %TIME% start > "%~dp0vcadmap_update_log.txt"',
        # 用 ping 等待（timeout 会弹出控制台窗口，一次重试跳一个，很难看）
        "ping -n 4 127.0.0.1 >nul",
        "set /a N=0",
        ":retry",
        "set /a N+=1",
        'copy /y "%NEW%" "%TARGET%" >nul 2>&1',
        "if not errorlevel 1 goto ok",
        "if %N% GEQ 40 goto fail",
        "ping -n 2 127.0.0.1 >nul",
        "goto retry",
        ":ok",
        'echo [update] ok after %N% tries >> "%~dp0vcadmap_update_log.txt"',
        # 交给资源管理器启动：父进程是 explorer，避免从隐藏控制台直接拉起的那些安全校验问题
        "ping -n 3 127.0.0.1 >nul",
        'explorer.exe "%TARGET%"',
        "goto end",
        ":fail",
        'echo [update] FAILED after %N% tries, new exe kept at: "%NEW%" >> "%~dp0vcadmap_update_log.txt"',
        ":end",
        'del "%~f0"',
    ]
    try:
        with open(bat, "w", encoding="ascii", errors="ignore", newline="\r\n") as f:
            f.write("\n".join(lines) + "\n")
    except Exception as e:
        return False, "写更新脚本失败：%s" % e
    try:
        subprocess.Popen(["cmd", "/c", bat, target, new_exe],
                         # CREATE_NO_WINDOW：整个过程不弹黑窗（原来 detached 时 timeout 会跳窗）
                         creationflags=0x08000000 | 0x00000200, close_fds=True)
    except Exception as e:
        return False, "启动更新脚本失败：%s" % e
    return True, ""


def save_worker(path, bus):
    """把当前 CAD 图纸另存到用户选的路径（连回 ZWCAD/AutoCAD 执行 SAVEAS）。"""
    pythoncom = None
    try:
        import pythoncom
        import win32com.client as win32
        pythoncom.CoInitialize()
        acad = None
        for progid in ("ZWCAD.Application", "AutoCAD.Application"):
            try:
                acad = win32.GetActiveObject(progid)
            except Exception:
                acad = None
            if acad:
                break
        if not acad:
            bus.save_result.emit(False, "连接不上 CAD，请回到 CAD 里手动另存。")
            return
        try:
            doc = acad.ActiveDocument
        except Exception:
            doc = None
        if not doc:
            bus.save_result.emit(False, "CAD 里没有打开的图纸，请手动另存。")
            return
        doc.SendCommand('(command "._SAVEAS" "" "%s")\n' % path.replace("\\", "/"))
        bus.save_result.emit(True, path)
    except Exception as e:
        msg = str(e)
        if "pythoncom" in msg or "win32com" in msg or "pywintypes" in msg:
            msg = ("连接 CAD 需要 pywin32（pythoncom）：%s\n"
                   "请 pip install pywin32 后重试；打包版要用装了 pywin32 的 Python 重新打包。" % msg)
        bus.save_result.emit(False, msg)
    finally:
        if pythoncom is not None:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass


# ---------------- 导出 PDF（打印布局） ----------------
# 实测（ZWCAD 2026）：设备/纸型列表要问布局对象 ActiveLayout.GetPlotDeviceNames /
# GetCanonicalMediaNames；Plot.PlotToFile 的参数顺序是「文件名, 设备名」，和 AutoCAD
# 文档里写的相反，所以下面先按 ZWCAD 的顺序试，失败再试另一种写法。
CAD_PROGIDS = ("ZWCAD.Application", "AutoCAD.Application")


def cad_connect(create=False):
    """连正在运行的 CAD。导出 PDF 要用当前打开的那张图，所以默认不新开实例。"""
    import win32com.client as win32
    for progid in CAD_PROGIDS:
        try:
            acad = win32.GetActiveObject(progid)
        except Exception:
            acad = None
        if acad:
            return acad, ""
    if not create:
        return None, "连不上 CAD：请先打开 ZWCAD 和要导出的图纸。"
    for progid in CAD_PROGIDS:
        try:
            return win32.DispatchEx(progid), ""
        except Exception:
            continue
    return None, "连不上 CAD，也没有可启动的 ZWCAD / AutoCAD。"


def cad_doc_or_none(acad):
    try:
        return acad.ActiveDocument
    except Exception:
        return None


def cad_layout_names(doc):
    """当前图纸里可以打印的布局名（不含 Model）。"""
    out = []
    try:
        layouts = doc.Layouts
        for i in range(layouts.Count):
            nm = str(layouts.Item(i).Name or "")
            if nm and nm.lower() != "model":
                out.append(nm)
    except Exception:
        pass
    return out


def cad_plot_devices(doc):
    """CAD 里可用的 PDF 类打印设备。只列名字带 PDF 的，不列实体打印机。"""
    out = []
    try:
        names = doc.ActiveLayout.GetPlotDeviceNames()
    except Exception:
        return out
    try:
        for i in range(len(names)):
            nm = str(names[i] or "").strip()
            if nm and "PDF" in nm.upper() and nm not in out:
                out.append(nm)
    except Exception:
        pass
    return out


def cad_plot_media(doc, device):
    """切到指定设备后取该设备的纸型 [(友好名, 规范名), ...]，取完把设备还原。"""
    lay = doc.ActiveLayout
    try:
        old = lay.ConfigName
    except Exception:
        old = None
    pairs = []
    try:
        lay.ConfigName = device
        names = lay.GetCanonicalMediaNames()
        for i in range(len(names)):
            canon = str(names[i])
            label = canon
            try:
                label = str(lay.GetLocaleMediaName(canon))
            except Exception:
                pass
            pairs.append((label, canon))
    except Exception:
        pairs = []
    finally:
        if old:
            try:
                lay.ConfigName = old
            except Exception:
                pass
    return pairs


def media_match_by_size(old_media, candidates):
    """换设备后原纸型名可能不认：按尺寸数字（如 420.00_x_297.00）找同规格的纸型。"""
    key = re.findall(r"\d+(?:\.\d+)?", old_media or "")
    if not key:
        return ""
    want = set(key)
    loose = ""
    for c in candidates:
        got = set(re.findall(r"\d+(?:\.\d+)?", c))
        if got == want:              # 尺寸完全一样的优先（避开 full_bleed 之类）
            return c
        if not loose and got >= want:
            loose = c
    return loose


def plot_one_to_file(plot, device, out_file):
    """ZWCAD 是 PlotToFile(文件, 设备)；AutoCAD 文档写的是反的，两种都试。"""
    try:
        plot.PlotToFile(out_file, device)
    except Exception as first:
        try:
            plot.PlotToFile(device, out_file)
        except Exception:
            raise first


# ---------------- 导出 PDF：质量 ----------------
# ZWCAD / AutoCAD 的 PDF 打印驱动把「清晰度」写在绘图仪配置（.pc5）里：
#   resolution_x / resolution_y                 = 矢量质量（dpi）
#   raster_resolution_x / raster_resolution_y   = 图片（光栅）质量（dpi）
# 这些键是打印时现读的，所以「调质量」的做法是：打印前把用户选的那份 .pc5 就地改一下，
# 打完（不管成没成）按原样写回去。
# ★ 为什么不另存一份新名字的绘图仪配置给 CAD 用：ZWCAD 在本会话里第一次问设备清单时
#   就把清单缓存住了，之后新写进去的 .pc5 它认不到，ConfigName 设过去会被打回「无」
#   （2025 实测）；而改了已有设备的 .pc5，下一次打印立刻生效（layerinclude 实测过）。
PDF_QUALITY_DEFAULT = 0            # 默认「跟随设备」，不改用户原来的打印配置
PDF_QUALITY_CHOICES = [("跟随设备（不改质量）", 0), ("标准 300 dpi", 300), ("清晰 600 dpi", 600),
                       ("高 1200 dpi", 1200), ("超清 2400 dpi（文件较大）", 2400),
                       ("极致 4800 dpi（文件很大）", 4800)]
PDF_RASTER_CHOICES = [("跟矢量质量", -1), ("跟随设备（不改）", 0), ("图片 300 dpi", 300),
                      ("图片 600 dpi", 600), ("图片 1200 dpi", 1200), ("图片 2400 dpi", 2400)]


def plotter_dirs():
    """CAD 的「绘图仪配置」目录（.pc5 放这些地方）；用户目录排在前面。"""
    env = os.environ.get
    pats = []
    if env("APPDATA"):
        pats += [os.path.join(env("APPDATA"), r"ZWSOFT\ZWCAD\*\*\Plotters"),
                 os.path.join(env("APPDATA"), r"ZWSoft\ZWCAD\*\*\Plotters"),
                 os.path.join(env("APPDATA"), r"Autodesk\AutoCAD *\R*\*\Plotters")]
    if env("LOCALAPPDATA"):
        pats += [os.path.join(env("LOCALAPPDATA"), r"Autodesk\AutoCAD *\R*\*\Plotters")]
    for k in ("ProgramFiles", "ProgramFiles(x86)"):
        if env(k):
            pats += [os.path.join(env(k), r"ZWSOFT\ZWCAD *\UserDataCache\*\Plotters"),
                     os.path.join(env(k), r"ZWSOFT\ZWCAD *\Plotters"),
                     os.path.join(env(k), r"Autodesk\AutoCAD *\Plotters")]
    out, seen = [], set()
    for p in pats:
        for d in glob.glob(p):
            if os.path.isdir(d) and os.path.normcase(d) not in seen:
                seen.add(os.path.normcase(d))
                out.append(d)
    return out


def device_pc5(device):
    """设备名（ZWCAD 报出来的名字带 .pc5 后缀）-> 它的绘图仪配置文件路径。"""
    name = str(device or "").strip()
    if not name:
        return ""
    cands = [name, name + ".pc5"]
    if name.lower().endswith(".pc5"):
        cands.append(name[:-4])
    for d in plotter_dirs():
        for c in cands:
            p = os.path.join(d, c)
            if os.path.isfile(p):
                return p
    return ""


def _pc5_set(data, key, val):
    """把 .pc5（bytes，别管它是什么编码）里 key=... 这行换成新值；没有就加到 [res_color_mem] 里。"""
    k = str(key).encode("ascii")
    pat = re.compile(rb"(?mi)^" + re.escape(k) + rb"=[^\r\n]*")
    line = k + b"=" + str(val).encode("ascii")
    if pat.search(data):
        return pat.sub(line, data, count=1)
    sec = re.compile(rb"(?mi)^\[res_color_mem\][^\r\n]*\r?\n")
    m = sec.search(data)
    if not m:
        return data + b"\r\n" + line + b"\r\n"
    return data[:m.end()] + line + b"\r\n" + data[m.end():]


def pc5_set_quality(data, quality, raster=-1, auto_open=0):
    """按界面选的「质量」改 .pc5：矢量 dpi / 图片 dpi / 打完要不要驱动自己打开文件。"""
    out = data
    q = int(quality or 0)
    if q > 0:
        out = _pc5_set(out, "resolution_x", q)
        out = _pc5_set(out, "resolution_y", q)
    ras = q if int(raster) < 0 else int(raster or 0)      # -1 = 跟矢量质量
    if ras > 0:
        out = _pc5_set(out, "raster_resolution_x", ras)
        out = _pc5_set(out, "raster_resolution_y", ras)
    # 驱动自己开文件会打开我们中途用的临时文件，一律关掉；要打开由我们合成完再开
    return _pc5_set(out, "autoopenfile", 1 if auto_open else 0)


class Pc5Quality(object):
    """打印期间把绘图仪配置里的质量改掉，打完自动改回来。"""

    def __init__(self, device, quality, raster=-1):
        self.device = str(device or "")
        self.path = device_pc5(device)
        self.quality = int(quality or 0)
        self.raster = int(raster if raster is not None else -1)
        self.orig = None
        self.done = False
        self.backup = ""

    def wanted(self):
        return self.quality > 0 or self.raster > 0

    def apply(self):
        """改配置。返回 (改没改成, 说明)，说明是要写进结果提示里的那一句。

        就算质量选的是「跟随设备」也要碰一下这份配置：顺手把「打完自动打开文件」关掉
        —— 不然 CAD 每打一页就弹一个 PDF 阅读器（打的是我们中途那些临时页）。
        """
        if not self.path:
            if not self.wanted():
                return False, ""
            return False, ("没找到设备「%s」的绘图仪配置（.pc5），质量这次按设备自带设置打印"
                           % self.device)
        try:
            with open(self.path, "rb") as f:
                self.orig = f.read()
        except Exception as e:
            if not self.wanted():
                return False, ""
            return False, "读不了绘图仪配置 %s：%s" % (self.path, e)
        if not re.search(rb"(?mi)^\[res_color_mem\]", self.orig):
            if not self.wanted():
                return False, ""
            return False, ("%s 不是能改质量的绘图仪配置，质量这次按设备自带设置打印"
                           % os.path.basename(self.path))
        data = pc5_set_quality(self.orig, self.quality, self.raster, auto_open=0)
        if data == self.orig:                     # 本来就一样，不用改
            return False, ""
        try:
            with open(self.path, "wb") as f:
                f.write(data)
        except Exception as e:
            if not self.wanted():
                return False, ""
            return False, ("改不了绘图仪配置 %s（%s），质量这次没生效" % (self.path, e))
        self.backup = _pc5_backup(self.orig, self.path)
        if not self.wanted():
            return True, ""
        return True, ("质量 %s（打印期间临时改 %s，打完已改回）"
                      % (quality_text(self.quality, self.raster), os.path.basename(self.path)))

    def restore(self):
        """把配置改回打印前那样；改不回去返回 False（原文在 %TEMP% 里有一份）。"""
        if self.orig is None or self.done:
            return True
        self.done = True
        try:
            with open(self.path, "rb") as f:
                if f.read() == self.orig:
                    return True
            with open(self.path, "wb") as f:
                f.write(self.orig)
            return True
        except Exception:
            return False


def _pc5_backup(data, path):
    """改之前先把原文另存一份到 %TEMP%，万一半路崩了还能自己找回来。"""
    try:
        d = os.path.join(tempfile.gettempdir(), "MAP-CAD-绘图仪配置备份")
        if not os.path.isdir(d):
            os.makedirs(d)
        dst = os.path.join(d, os.path.basename(path))
        with open(dst, "wb") as f:
            f.write(data)
        return dst
    except Exception:
        return ""


def quality_text(quality, raster=-1):
    """界面上选的质量 -> 一句话（写进提示和日志）。"""
    q = int(quality or 0)
    r = int(raster if raster is not None else -1)
    if q <= 0 and r <= 0:
        return "矢量/图片都跟随设备"
    if r < 0:
        r = q
    return "、".join(["矢量 %d dpi" % q if q > 0 else "矢量跟设备",
                      "图片 %d dpi" % r if r > 0 else "图片跟设备"])


def device_pc5_quality(device):
    """这个设备配置里现在的质量（直接读 .pc5）：返回 (矢量 dpi, 图片 dpi)，读不出给 0。"""
    path = device_pc5(device)
    if not path:
        return 0, 0
    try:
        with open(path, "rb") as f:
            data = f.read()
    except Exception:
        return 0, 0

    def num(key):
        m = re.search(rb"(?mi)^" + re.escape(key.encode("ascii")) + rb"=(\d+)", data)
        return int(m.group(1)) if m else 0

    v = num("resolution_x")
    return v, (num("raster_resolution_x") or v)


# ---------------- 导出 PDF：一次打一批 ----------------
def set_plot_layouts(plot, names):
    """告诉 CAD「这次要打这几个布局」（AcadPlot.SetLayoutsToPlot）。
    接口不存在 / 传参不认就返回 False，调用方自己决定怎么办。

    实测 ZWCAD 2025：直接传 Python 列表会抛「类型不对」，一定要包成 BSTR 数组；
    所以先试 BSTR 数组，不认再退回普通列表。"""
    want = [str(x) for x in (names or []) if str(x)]
    if not want:
        return False
    try:
        import pythoncom
        from win32com.client import VARIANT
        plot.SetLayoutsToPlot(VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_BSTR, want))
        return True
    except Exception:
        pass
    try:
        plot.SetLayoutsToPlot(want)
        return True
    except Exception:
        return False


def set_layout_device(lay, device, raise_=True):
    """给布局换打印设备（设备名照 CAD 清单报的原样传就行，ZWCAD 报的名字带 .pc5）。

    ★ 别拿「加/去 .pc5」当兜底：实测 ZWCAD 里给它一个不认的名字，它会把布局的打印设备
      直接清成「无」，比失败还糟；所以只按给的名字设一次，不行就如实报错。
    """
    try:
        lay.ConfigName = str(device)
        return True
    except Exception as e:
        if raise_:
            raise RuntimeError("切换到打印设备「%s」失败：%s" % (device, e))
        return False


def pdf_page_count(path):
    """PDF 页数；读不出来返回 -1。"""
    try:
        return len(PdfReader(path).pages)
    except Exception:
        return -1


def pdf_page_count_wait(path, tries=8, gap=0.4):
    """等 PDF 落盘再读页数（驱动写文件到能读之间偶尔差一点时间）；还是没有就是 0。"""
    for i in range(max(1, tries)):
        if os.path.exists(path) and os.path.getsize(path) > 0:
            n = pdf_page_count(path)
            if n > 0:
                return n
        if i < tries - 1:
            time.sleep(gap)
    return 0


def new_tmpdir(prefix, prefer=""):
    """建个临时目录，并确认它真的写得进去（个别环境 mkdtemp 出来的目录写不了）。"""
    cands = []
    try:
        cands.append(tempfile.mkdtemp(prefix=prefix))
    except Exception:
        pass
    for base in (tempfile.gettempdir(), prefer):
        if base:
            cands.append(os.path.join(base, "%s%d" % (prefix, int(time.time() * 1000))))
    for d in cands:
        try:
            if not os.path.isdir(d):
                os.makedirs(d, exist_ok=True)
            probe = os.path.join(d, ".w_probe")
            with open(probe, "wb") as f:
                f.write(b"x")
            os.remove(probe)
            return d
        except Exception:
            shutil.rmtree(d, ignore_errors=True)
            continue
    raise RuntimeError("建不了临时目录（%s）" % "；".join(cands[:3]))


def pdf_files_for(folder, layouts, dwg_stem=""):
    """CAD 一次打多个布局时，是按「图纸名_布局名.pdf」一个布局存一个文件。
    按布局顺序把它们挑出来（先按图纸名精确找，再按后缀找，一个文件只配一个布局）；
    有一个对不上就返回 None（调用方会退回逐张打印）。"""
    try:
        files = [f for f in os.listdir(folder) if f.lower().endswith(".pdf")]
    except Exception:
        return None
    used = set()

    def pick(nm):
        nm = str(nm)
        if dwg_stem:                     # 图纸名_布局名.pdf（ZWCAD 的命名）
            exact = ("%s_%s.pdf" % (dwg_stem, nm)).lower()
            for f in files:
                if f.lower() == exact and f not in used:
                    return f
        cands = [f for f in files if f not in used and f[:-4].endswith("_" + nm)]
        if not cands:
            return None
        return sorted(cands, key=len)[0]      # 前缀最短的最像（避开 1 和 x1 这种）

    out = []
    for nm in layouts:
        f = pick(nm)
        if not f:
            return None
        used.add(f)
        out.append(os.path.join(folder, f))
    return out


def plot_worker(layouts, device, media_canon, out_path, bus,
                quality=0, raster=-1, open_after=False):
    """把勾选的布局一次交给 CAD 打印，再合成一份多页 PDF。

    打印是一次打完所有页面：SetLayoutsToPlot(整份布局清单) + 一次 PlotToFile，
    不再一页一次地切换布局反复调打印。
    （ZWCAD 的 PDF 驱动对多布局是「一个布局存一个文件、按 图纸名_布局名.pdf 存」，
    这跟它自己的批量打印工具一样 —— 工具里也是打完再合并成一份多页 PDF。）
    只有这个 CAD 版本不认批量接口时，才退回逐张打印（结果里会写明）。
    """
    pythoncom = None
    tmpdir = None
    notes = []
    qual = Pc5Quality(device, quality, raster)
    try:
        import pythoncom
        import win32com.client as win32
        from pypdf import PdfWriter
        pythoncom.CoInitialize()
        acad, msg = cad_connect()
        if not acad:
            bus.plot_result.emit(False, msg)
            return
        doc = cad_doc_or_none(acad)
        if doc is None:
            bus.plot_result.emit(False, "CAD 里没有打开的图纸。")
            return
        plot = doc.Plot
        try:
            plot.QuietErrorMode = True          # ZWCAD 里是属性，不是方法
        except Exception:
            pass
        try:
            plot.BackgroundPlot = False         # 批量打印要等它打完，别让它后台跑
        except Exception:
            pass
        try:
            old_tab = doc.GetVariable("CTAB")
        except Exception:
            old_tab = None
        try:
            dwg_stem = os.path.splitext(os.path.basename(str(doc.Name or "")))[0]
        except Exception:
            dwg_stem = ""

        # 质量：打印期间把这份绘图仪配置里的 dpi 改掉，打完就改回来
        _ok_q, why = qual.apply()
        if why:
            notes.append(why)

        media_of = {}

        def dev_medias(d):
            """某设备的纸型清单（"随布局页面设置" 时用来找同规格纸型）。"""
            if d not in media_of:
                try:
                    media_of[d] = [canon for _lab, canon in cad_plot_media(doc, d)]
                except Exception:
                    media_of[d] = []
            return media_of[d]

        total = len(layouts)

        # 先把要打的布局逐个设好设备 / 纸型（都不打印），再一次性提交给 CAD
        old_setup = []
        for name in layouts:
            doc.SetVariable("CTAB", name)
            lay = doc.ActiveLayout
            try:
                old_dev = str(lay.ConfigName or "")
            except Exception:
                old_dev = ""
            try:
                old_media = str(lay.CanonicalMediaName or "")
            except Exception:
                old_media = ""
            old_setup.append((name, old_dev, old_media))
            set_layout_device(lay, device)           # 失败就抛出来（带设备名）
            dev_media = dev_medias(device)
            want = media_canon or ""
            if not want and old_media:
                if old_media in dev_media:
                    want = old_media
                else:
                    want = media_match_by_size(old_media, dev_media)
                    if not want:
                        notes.append("布局「%s」原来的纸型在新设备里没有同规格的，按设备默认纸型打印" % name)
            if want:
                try:
                    lay.CanonicalMediaName = want
                except Exception as e:
                    raise RuntimeError("布局「%s」设置纸型失败（%s）：%s" % (name, want, e))

        tmpdir = new_tmpdir("vcad_pdf_", prefer=os.path.dirname(os.path.abspath(out_path)))
        out_pdf = os.path.join(tmpdir, "out.pdf")
        bus.plot_prog.emit(0, total)

        # ① 一次把这一批全打了（CAD 的批量打印）
        parts = None
        if total > 1 and set_plot_layouts(plot, layouts):
            try:
                plot_one_to_file(plot, device, out_pdf)
                if os.path.exists(out_pdf) and os.path.getsize(out_pdf) > 0:
                    # 这个 CAD 一次就给了一份多页 PDF，直接用
                    pages = pdf_page_count(out_pdf)
                    if pages == total:
                        parts = [out_pdf]
                    else:
                        notes.append("一次打一批出来 %d 页（要 %d 页），这次改用逐张打印后合并"
                                     % (pages, total))
                else:
                    # ZWCAD 的 PDF 驱动是「一个布局存一个」：图纸名_布局名.pdf
                    got = pdf_files_for(tmpdir, layouts, dwg_stem)
                    if not got:
                        notes.append("一次打一批没看到打出来的 PDF，这次改用逐张打印后合并")
                    else:
                        pages = sum(max(0, pdf_page_count_wait(f)) for f in got)
                        if pages == total:
                            parts = got
                        else:
                            notes.append("一次打一批出来 %d 页（要 %d 页），这次改用逐张打印后合并"
                                         % (pages, total))
            except Exception as e:
                notes.append("一次打一批失败（%s），这次改用逐张打印后合并" % e)
        elif total > 1:
            notes.append("这张 CAD 不支持「一次打多个布局」（AcadPlot.SetLayoutsToPlot），"
                         "这次退回逐张打印后合并")

        if parts:
            bus.plot_prog.emit(total, total)
        else:
            # ② 退回逐张打（每次只让它打当前这一个布局），再合并 —— 保证功能可用
            parts = []
            for i, name in enumerate(layouts, 1):
                bus.plot_prog.emit(i - 1, total)
                doc.SetVariable("CTAB", name)
                try:
                    set_plot_layouts(plot, [name])
                except Exception:
                    pass
                out_i = os.path.join(tmpdir, "%04d.pdf" % i)
                plot_one_to_file(plot, device, out_i)
                if not os.path.exists(out_i) or os.path.getsize(out_i) <= 0:
                    raise RuntimeError("布局「%s」没有生成 PDF（设备 %s）。" % (name, device))
                n_i = pdf_page_count_wait(out_i, tries=4, gap=0.3)
                if n_i != 1:      # 逐张打就该是一页；不是一页说明「只打当前布局」没生效
                    raise RuntimeError("布局「%s」一次打出来 %d 页（应该 1 页），先停在这里。"
                                       % (name, n_i))
                parts.append(out_i)
                bus.plot_prog.emit(i, total)

        writer = PdfWriter()
        for p in parts:
            writer.append(p)
        out_merge = os.path.join(tmpdir, "merge.pdf")
        with open(out_merge, "wb") as f:
            writer.write(f)

        if not os.path.exists(out_merge) or os.path.getsize(out_merge) <= 0:
            raise RuntimeError("没有生成 PDF（设备 %s）。" % device)
        try:
            os.replace(out_merge, out_path)
        except OSError:
            shutil.move(out_merge, out_path)

        # 布局的打印设备 / 纸型改回原来的（导入时改的东西不留在图上）
        for name, old_dev, old_media in old_setup:
            try:
                doc.SetVariable("CTAB", name)
                lay = doc.ActiveLayout
                if old_dev:
                    set_layout_device(lay, old_dev, raise_=False)
                if old_media:
                    lay.CanonicalMediaName = old_media
            except Exception:
                pass
        if old_tab:
            try:
                doc.SetVariable("CTAB", old_tab)
            except Exception:
                pass
    except Exception as e:
        msg = str(e)
        if "pythoncom" in msg or "win32com" in msg or "pywintypes" in msg:
            msg = ("连接 CAD 需要 pywin32（pythoncom）：%s\n"
                   "打包版要用装了 pywin32 的 Python 重新打包。" % msg)
        if not qual.restore():
            msg += "\n（绘图仪配置没改回去，原文在 %s）" % (qual.backup or "（没存成）")
        bus.plot_result.emit(False, msg)
        return
    finally:
        if not qual.restore():
            notes.append("绘图仪配置没改回去，原文在 %s" % (qual.backup or "（没存成）"))
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)
        if pythoncom is not None:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
    if open_after:
        try:
            os.startfile(out_path)
        except Exception:
            notes.append("（自动打开 PDF 失败，文件已经导出）")
    if notes:
        bus.plot_result.emit(True, "%s\n（%s）" % (out_path, "；".join(notes)))
    else:
        bus.plot_result.emit(True, out_path)


# ---------------- Qt 界面 ----------------
QSS = """
* { font-family: 'Microsoft YaHei', 'SimHei'; font-size: 14px; color: #DADFE3; }
QWidget { background-color: #131415; }
QMainWindow, #Root { background-color: #131415; }
QFrame#Header { background-color: #131415; border-bottom: 1px solid #2a2c2e; }
QFrame#Footer { background-color: #17181a; border-top: 1px solid #2a2c2e; }
QLabel#Logo { color: #0432FA; font-size: 30px; font-weight: 800; background: transparent; }
QLabel#AppTitle { color: #DADFE3; font-size: 17px; font-weight: 600; background: transparent; }
QLabel#VerLabel { color: #727577; background: transparent; }
QLabel#UpdLabel { color: #F5A800; background: transparent; }
QPushButton#UpdBtn { background-color: rgba(255,255,255,0.06); color: #DADFE3;
  border: 1px solid rgba(255,255,255,0.10); border-radius: 6px; padding: 4px 12px; }
/* 顶栏图标按钮：不给内边距，否则 28px 的方块里图标会被压掉一半（显示不全） */
QPushButton#IconBtn { background-color: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.10);
  border-radius: 6px; padding: 0px; margin: 0px; }
QPushButton#IconBtn:hover { background-color: rgba(255,255,255,0.12); }
QPushButton#UpdBtn:hover { background-color: rgba(255,255,255,0.12); }
QPushButton#UpdBtn:disabled { color: #5c6064; border: 1px solid rgba(255,255,255,0.06); }
QFrame#Sidebar { background-color: #131415; border-right: 1px solid #2a2c2e; }
QPushButton#Nav { background-color: transparent; color: #B9BEC3; border: none; border-radius: 8px;
  text-align: left; padding-left: 8px; }
QPushButton#Nav:hover { background-color: rgba(255,255,255,0.05); }
QPushButton#Nav:checked { background-color: rgba(255,255,255,0.10); color: #fff;
  border-left: 4px solid #0432FA; }
QLabel#PageTitle { color: #DADFE3; font-size: 20px; font-weight: 600; background: transparent; }
QLabel#BigCount { color: #0432FA; font-size: 32px; font-weight: 700; background: transparent; }
QLabel#FieldLabel { color: #727577; background: transparent; }
QLabel#Hint { color: #5c6064; font-size: 12px; background: transparent; }
QLineEdit { background-color: #1f2124; border: 1px solid #2a2c2e; border-radius: 8px;
  padding: 6px 10px; color: #DADFE3; selection-background-color: #0432FA; }
QLineEdit:focus { border: 1px solid #0432FA; }
QPushButton { background-color: rgba(255,255,255,0.06); color: #DADFE3;
  border: 1px solid rgba(255,255,255,0.10); border-radius: 8px; padding: 8px 16px; }
QPushButton:hover { background-color: rgba(255,255,255,0.12); }
QPushButton#Primary { background-color: #0432FA; color: #fff; border: none; font-weight: 600; }
QPushButton#DrawTool:checked { background-color: #0432FA; color: #fff; border: none; font-weight: 600; }
QPushButton#Primary:hover { background-color: #0a46ff; }
QProgressBar { border: 0; border-radius: 8px; background: rgba(255,255,255,0.12);
  color: #DADFE3; }
QProgressBar::chunk { background-color: #0432FA; border-radius: 8px; }
QPlainTextEdit#Log { background-color: #101113; color: #a8adb2; border: 1px solid #2a2c2e;
  border-radius: 8px; font-family: Consolas, 'Microsoft YaHei'; }
QFrame#FinishBox { background-color: #17181a; border: 1px solid #2a2c2e; border-radius: 10px; }
QLabel#FinishTitle { color: #DADFE3; font-size: 15px; font-weight: 600; background: transparent; }
QDialog { background-color: #131415; }
QLabel#UpdTitle { color: #DADFE3; font-size: 16px; font-weight: 600; background: transparent; }
QLabel#UpdSub { color: #727577; background: transparent; }
QPlainTextEdit#Notes { background-color: #101113; color: #c9ced3; border: 1px solid #2a2c2e;
  border-radius: 8px; font-family: Consolas, 'Microsoft YaHei'; }
QScrollArea { border: none; background: transparent; }
QCheckBox, QRadioButton { background: transparent; color: #DADFE3; }
QPushButton:disabled { background-color: rgba(255,255,255,0.03); color: #5c6064;
  border: 1px solid rgba(255,255,255,0.06); }
QComboBox { background-color: #1f2124; border: 1px solid #2a2c2e; border-radius: 8px;
  padding: 4px 8px; color: #DADFE3; }
QComboBox QAbstractItemView { background-color: #1f2124; color: #DADFE3;
  selection-background-color: #0432FA; }
QListWidget { background-color: #1f2124; border: 1px solid #2a2c2e; border-radius: 8px;
  color: #DADFE3; }
QListWidget::item { padding: 4px 6px; }
/* 识别页右栏的「项目树」（LBD 编号 -> 里面的支架号）跟列表同一个样子 */
QTreeWidget { background-color: #1f2124; border: 1px solid #2a2c2e; border-radius: 8px;
  color: #DADFE3; }
QTreeWidget::item { padding: 3px 4px; }
/* 识别页顶部控件多，这一页单独用更紧凑的尺寸（不动其他页） */
QWidget#RecogPage QPushButton { padding: 4px 12px; }
QWidget#RecogPage QLineEdit { padding: 3px 8px; }
QWidget#RecogPage QComboBox { padding: 1px 8px; }
QWidget#RecogPage QProgressBar { max-height: 10px; }
QWidget#RecogPage QListWidget { padding: 0px; }
QWidget#RecogPage QTreeWidget { padding: 0px; }
QLabel#RecogStatus { color: #5c6064; font-size: 11px; background: transparent; }
QLabel#RecogTip { color: #5c6064; font-size: 11px; background: transparent; }
/* 识别页左表：三列平分，表头/单元格留白收窄，不横向滚动 */
QTableWidget#RecogPages { padding: 0px; }
QTableWidget#RecogPages::item { padding: 1px 3px; }
QTableWidget#RecogPages QHeaderView::section { padding: 2px 3px; }
"""


class Bus(QObject):
    prog = Signal(str)
    err = Signal(str)
    done = Signal(str)
    status = Signal(str)
    racks = Signal(list)          # 支架类型明细（后台线程解析完推给界面）
    strprev = Signal(object)        # STR 顺序预览（后台线程 -> 界面）
    quadprev = Signal(object)       # 象限预览（后台线程 -> 界面）
    save_result = Signal(bool, str)
    plot_prog = Signal(int, int)          # 导出 PDF：已完成 / 总数
    plot_result = Signal(bool, str)       # 导出 PDF：成功?, 路径或错误
    upd_found = Signal(str, str, str, str)
    upd_none = Signal(str, str, str)
    upd_notes = Signal(str, str, str, bool)
    upd_error = Signal(str)
    upd_progress = Signal(int)
    upd_detail = Signal(str)      # 下载明细：已下多少 / 总大小 / 速度
    upd_log = Signal(str)         # 下载过程写进界面日志（测速、换源等）
    upd_ready = Signal(str)
    recog_prog = Signal(int, int, str)     # 识别：已识别 / 总数 / 说明
    recog_log = Signal(str)                # 识别：日志行
    recog_done = Signal(object)            # 识别：结束（摘要 dict）


class RecogBoxItem(QGraphicsRectItem):
    """识别预览画布上的一个框：可选中、可拖动；右下角小方块改大小。"""

    def __init__(self, canvas, det_index, kind, rect):
        super().__init__(rect)
        self.canvas = canvas
        self.det_index = det_index
        self.kind = kind
        self.locked = False            # 锁定的 LBD 区：不能拖动 / 改大小 / 删除
        self.setFlag(QGraphicsRectItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsRectItem.ItemIsMovable, True)
        self.setFlag(QGraphicsRectItem.ItemSendsGeometryChanges, True)
        # 和标注软件同一套配色（Node 蓝 / Tracker 红 / Box 绿）
        col = {"Node": QColor(0, 120, 255), "Tracker": QColor(255, 40, 40),
               "Box": QColor(0, 200, 0)}.get(kind, QColor(255, 200, 0))
        pen = QPen(col)
        pen.setWidth(2 if kind == "Node" else 1)
        pen.setCosmetic(True)          # 线宽不跟着缩放变：缩小看整页时框也看得见
        self.setPen(pen)
        self.setBrush(Qt.NoBrush)
        self.setZValue(10 if kind == "Node" else (8 if kind == "Box" else 5))

    def itemChange(self, change, value):
        if change == QGraphicsRectItem.ItemPositionHasChanged:
            self.canvas.note_box_changed(self)
        elif change == QGraphicsRectItem.ItemSelectedHasChanged:
            self.canvas.note_selected(self if value else None)
        return super().itemChange(change, value)


# 识别页的快捷键说明：挂在「快捷键」小按钮的提示/弹窗里，不挂在画布上（悬停弹字太烦）
RECOG_SHORTCUTS = (
    "滚轮或 Ctrl+＋/－ 缩放 · Ctrl+0 适应页面 · Ctrl+1 适应宽度 · 中键拖动平移 · "
    "拖框改位置 · 拖八个控制点改大小 · A/D 或 PgUp/PgDn 前后翻页 · "
    "Delete 删除 · Ctrl+Z 撤销 · Ctrl+C / Ctrl+V 复制粘贴框")


class RecogCanvas(QGraphicsView):
    """识别结果预览/编辑画布：滚轮缩放、中键平移、框可拖动/改大小/删除、编号可改名。

    改动直接写回识别结果 doc（和 JSON 一份数据）；保存交给页面上的「保存修改」。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        # 和标注工具一样：抗锯齿 + 图片平滑缩放（缩小时底图不毛糙）
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        # 重绘便宜一点：只刷变化的那块区域，且不用为每个图元保存画笔状态
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setOptimizationFlag(QGraphicsView.DontSavePainterState, True)
        self.setBackgroundBrush(QColor(20, 20, 20))
        self.doc = None
        self.page = None
        self.pix_item = None
        self._img_cache = {}           # {(pdf, 页, dpi, max_w): QImage} —— 同一页不重复渲染
        self.disp_w = 1.0
        self.page_w = 1.0
        self.page_h = 1.0
        self.box_items = []
        self.name_items = {}
        self.ocr_of = {}
        self.on_changed = None
        self.on_changed_fast = None    # 拖动/缩放过程中用（只标记改动，别重建表格）
        self.on_selected = None
        self.on_added = None           # 拖出一个新框之后的回调（界面刷新名字栏/统计）
        self.on_deleted = None         # 删框之后的回调（界面同步刷新结果）
        self.on_renamed = None         # 改编号之后的回调（界面刷新右栏名字栏）
        self.on_lock_changed = None    # Ctrl+点解锁单个框之后（界面同步「锁定 LBD」按钮）
        self.on_escape = None          # ESC 退出画框模式的回调（界面把工具按钮弹起来）
        self.on_page_key = None        # 键盘翻页回调（PgUp/PgDn、Ctrl+←/→）
        self.on_rack_step = None       # A/D：前/后跳一个支架（回调给主窗口）
        self.add_mode = ""             # "" = 不在加框模式；否则 = 要画的框类型
        self._rubber = None
        self._rubber_from = None
        self._panning = False
        self._pan_from = None
        self._undo = []
        self._fit_mode = "page"        # "page"=整页装进视口 / "width"=适应宽度 / ""=手动缩放
        self.sel_label = None          # 选中框的名字（和标注软件一样：只显示选中的那个）
        self._resize = None            # 正在拖控制点改大小：{box, idx, start, rect}
        self._drag_active = False      # 正按着鼠标拖框/拖控制点
        self.lbd_locked = False        # 锁住本页 LBD 区（不能拖动/改大小/删除）
        self._make_handle()

    def _make_handle(self):
        """（重新）造名字标签 —— scene.clear() 之后必须重建。

        改大小的控制点不用图元了（老做法是一个「可移动」的小方块，Qt 在按下时会
        忽略它、把事件交给下面的框，结果拖角只会把框拖走、尺寸根本不改），
        改成和标注工具一样：画布自己画 8 个控制点 + 自己做命中检测 + 实时改尺寸。
        """
        self._resize = None
        # 选中框的名字标签（只有一个，跟着选中项走）
        self.sel_label = QGraphicsSimpleTextItem()
        self.sel_label.setBrush(QColor(255, 196, 0))
        self.sel_label.setZValue(60)
        self.sel_label.setVisible(False)
        self.scene().addItem(self.sel_label)

    # ---------- 载入一页 ----------
    def load(self, doc, page, pdf_path, dpi=110, max_w=1100, keep_view=False):
        import detect as _d
        # 编辑后重载（加框/撤销/粘贴）要保持当前缩放和位置，别把整页缩回"适应页面"
        prev = None
        if keep_view and self.pix_item is not None:
            prev = (self.transform(),
                    self.horizontalScrollBar().value(),
                    self.verticalScrollBar().value())
        self.doc, self.page = doc, page
        # 记住这次用的清晰度：加框/撤销/粘贴后的重载要沿用，否则底图会掉回低清
        self._load_dpi, self._load_maxw = int(dpi), int(max_w)
        self.scene().clear()
        self._make_handle()
        self.box_items, self.name_items, self.ocr_of = [], {}, {}
        trk = next((p for p in doc.get("yolo_tracker_detection_results") or []
                    if p.get("page_number") == page), None)
        ocr = next((p for p in doc.get("ocr_node_name_results") or []
                    if p.get("page_number") == page), None)
        dets = ((trk or {}).get("data") or {}).get("detections") or []
        recs = (ocr or {}).get("data") or []
        for p in (doc.get("input_data") or {}).get("pages") or []:
            if p.get("page_number") == page:
                self.page_w = p.get("width") or 1
                self.page_h = p.get("height") or 1
        # 底图渲染一次要 1 秒上下（大图纸更久），而加框/删框/撤销都会重新 load —— 
        # 缓存住同一页，编辑时就不用反复重渲染（这是「拖起来不顺」的大头）。
        ck = (pdf_path, page, int(dpi), int(max_w))
        qimg = self._img_cache.get(ck)
        if qimg is None:
            im = _d.render_page(pdf_path, page, dpi=dpi)
            if im.width > max_w:
                sc = max_w / float(im.width)
                im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))))
            qimg = QImage(im.tobytes(), im.width, im.height, 3 * im.width,
                          QImage.Format_RGB888)
            self._img_cache[ck] = qimg
            while len(self._img_cache) > 4:        # 最多留 4 页（一页十几 MB）
                self._img_cache.pop(next(iter(self._img_cache)))
        self.pix_item = self.scene().addPixmap(QPixmap.fromImage(qimg))
        self.pix_item.setZValue(0)
        self.disp_w = float(qimg.width())       # 用缓存里的图也要拿得到宽高
        self.resetTransform()
        self.scene().setSceneRect(0, 0, qimg.width(), qimg.height())
        k = 0
        for i, d in enumerate(dets):
            kind = d.get("label") or ""
            if kind not in ("Node", "Tracker", "Box"):
                continue
            it = RecogBoxItem(self, i, kind, self._disp_rect(d.get("bbox") or {}))
            self.scene().addItem(it)
            self.box_items.append(it)
            if kind == "Node" and (d.get("raw") or {}).get("lbd_locked"):
                it.locked = True
                it.setFlag(QGraphicsRectItem.ItemIsSelectable, False)
                it.setFlag(QGraphicsRectItem.ItemIsMovable, False)
            if kind == "Node":
                if k < len(recs):
                    self.ocr_of[i] = k
                k += 1
        self.name_items = {}          # 名字只显示选中的那个（和标注软件一致）
        if prev is not None:
            self.setTransform(prev[0])
            self.horizontalScrollBar().setValue(prev[1])
            self.verticalScrollBar().setValue(prev[2])
            self._fit_mode = ""       # 手动缩放：窗口变化也别再自动缩回整页
            self._place_handle()
        else:
            self.fit_page()

    def reload_page(self):
        """按上次的清晰度重画当前页（加框 / 撤销 / 粘贴之后用）。

        这几处以前是 self.load(..., pdf) 用默认参数重载的：底图会从
        200dpi / 2600px 掉回 110dpi / 1100px —— 画完一个框整页就变糊了。
        """
        pdf = getattr(self, "_pdf", "") or ""
        if not (self.doc and self.page and pdf):
            return
        self.load(self.doc, self.page, pdf,
                  dpi=getattr(self, "_load_dpi", 200),
                  max_w=getattr(self, "_load_maxw", 2600), keep_view=True)

    # ---------- 坐标换算（页像素 <-> 画布像素）----------
    def _k(self):
        return self.disp_w / float(self.page_w or 1)

    def _dx(self, x):
        return float(x) * self._k()

    def _dy(self, y):
        return float(y) * self._k()

    def _disp_rect(self, b):
        return QRectF(self._dx(b.get("x1", 0)), self._dy(b.get("y1", 0)),
                      max(1.0, self._dx(b.get("x2", 0)) - self._dx(b.get("x1", 0))),
                      max(1.0, self._dy(b.get("y2", 0)) - self._dy(b.get("y1", 0))))

    # ---------- 缩放 / 平移 ----------
    def wheelEvent(self, e):
        # 按滚轮事件自带的坐标缩放（那个坐标就是此刻光标的视口位置）
        dy = e.angleDelta().y()
        if dy:
            f = 1.15 if dy > 0 else 1 / 1.15
            if 0.01 < self.transform().m11() * f < 40:
                self.zoom_at(f, e.position().toPoint())
        e.accept()

    def zoom(self, factor):
        """键盘缩放（Ctrl+＋/－）：跟着光标；光标不在画布里就按视口中心。"""
        self.zoom_at(factor, self._zoom_anchor())

    def _zoom_anchor(self):
        p = self.viewport().mapFromGlobal(QCursor.pos())
        if self.viewport().rect().contains(p):
            return p
        return self.viewport().rect().center()

    def zoom_at(self, factor, view_pos):
        """按指定的视口位置缩放：缩放前后让那个点下面的场景点待在原地。

        原来靠 setTransformationAnchor(AnchorUnderMouse)，但那个锚点用的是 Qt 内部
        记的「最后一次鼠标位置」；画框模式下 mouseMoveEvent 会把移动事件吞掉、不传
        基类，这个记录就冻在「按下第一个角」的地方 —— 滚轮于是按那个旧位置缩放，
        表现就是「不跟十字光标的位置缩放」（拖控制点改大小时同理）。

        这里不再指望 Qt 的锚点，自己算：视口坐标 = 场景坐标 × 缩放 − 滚动条位置，
        反过来解出「要让那个点留在光标上，滚动条该在哪儿」（QGraphicsView 的滚动条
        1 格 = 1 个视口像素）。算的是目标绝对值，不是每步补差值，所以不会越滚越偏。
        """
        self._fit_mode = ""
        self.setTransformationAnchor(QGraphicsView.NoAnchor)   # 锚点由下面自己算
        old = self.mapToScene(view_pos)
        self.scale(factor, factor)
        hb, vb = self.horizontalScrollBar(), self.verticalScrollBar()
        t = self.transform()
        hb.setValue(int(round(old.x() * t.m11() - view_pos.x())))
        vb.setValue(int(round(old.y() * t.m22() - view_pos.y())))
        self._place_handle()

    def fit_width(self):
        """适应宽度：整页宽铺满视口（看细节用）。"""
        self._fit_mode = "width"
        if not self.pix_item:
            return
        self.resetTransform()
        w = self.viewport().width() - 4
        if w > 50 and self.pix_item.boundingRect().width() > 0:
            s = w / self.pix_item.boundingRect().width()
            self.scale(s, s)
        self._place_handle()

    def fit_page(self, margin=8):
        """适应页面：整张图纸缩到视口里 —— 一屏看全这一页（默认就按这个来）。"""
        self._fit_mode = "page"
        if not self.pix_item:
            return
        self.resetTransform()
        r = self.pix_item.boundingRect()
        vw = max(60, self.viewport().width() - margin * 2)
        vh = max(60, self.viewport().height() - margin * 2)
        if r.width() <= 1 or r.height() <= 1:
            return
        s = min(vw / r.width(), vh / r.height())
        s = max(0.02, min(s, 4.0))
        self.scale(s, s)
        self.centerOn(r.center())
        self._place_handle()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        mode = getattr(self, "_fit_mode", "")
        if mode == "page":
            self.fit_page()
        elif mode == "width":
            self.fit_width()

    def mousePressEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self._panning = True
            self._pan_from = e.position()
            self.setCursor(Qt.ClosedHandCursor)
            e.accept()
            return
        # 和标注软件一样：锁上的框 Ctrl+点 = 只解锁这一个
        if e.button() == Qt.LeftButton and (e.modifiers() & Qt.ControlModifier):
            hit = self.itemAt(e.position().toPoint())
            if isinstance(hit, RecogBoxItem) and getattr(hit, "locked", False):
                hit.locked = False
                hit.setFlag(QGraphicsRectItem.ItemIsSelectable, True)
                hit.setFlag(QGraphicsRectItem.ItemIsMovable, True)
                trk, _ocr = self._page_data()
                dets = ((trk or {}).get("data") or {}).get("detections") or []
                if 0 <= hit.det_index < len(dets):
                    raw = dict(dets[hit.det_index].get("raw") or {})
                    raw.pop("lbd_locked", None)
                    dets[hit.det_index]["raw"] = raw
                if self.on_lock_changed:
                    try:
                        self.on_lock_changed()
                    except Exception:
                        pass
                if self.on_changed:
                    try:
                        self.on_changed()
                    except Exception:
                        pass
                self._place_handle()
                e.accept()
                return
        # 加框模式（和标注工具一样）：第一次点定一个角 → 鼠标移到对角 → 第二次点成框；
        # 也可以按住左键直接拖出来（拖着画的松手即成型）
        if self.add_mode and e.button() == Qt.LeftButton and self.pix_item is not None:
            if self._rubber is not None:        # 已经点过第一个角了：这一下就是对角
                self._finish_add()
                e.accept()
                return
            self._rubber_from = self.mapToScene(e.position().toPoint())
            # 和标注软件一致：类别色、2px 实线（线宽不随缩放）、40 透明填充
            _col = {"Node": QColor(0, 120, 255), "Tracker": QColor(255, 40, 40),
                    "Box": QColor(0, 200, 0)}.get(self.add_mode, QColor(255, 0, 255))
            self._rubber = QGraphicsRectItem(QRectF(self._rubber_from, self._rubber_from))
            _pen = QPen(_col)
            _pen.setCosmetic(True)
            _pen.setWidthF(2.0)
            self._rubber.setPen(_pen)
            self._rubber.setBrush(QColor(_col.red(), _col.green(), _col.blue(), 40))
            self._rubber.setZValue(50)
            self.scene().addItem(self._rubber)
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)
            e.accept()
            return
        # 拖控制点改大小：命中检测放在最前面，免得被下面的框把事件抢走
        if e.button() == Qt.LeftButton:
            box = self.selected_box()
            if box is not None and not getattr(box, "locked", False):
                sp = self.mapToScene(e.position().toPoint())
                idx = self._handle_at(sp)
                if idx is not None:
                    self.push_undo()
                    self._resize = {"box": box, "idx": idx, "start": sp,
                                    "rect": QRectF(box.rect())}
                    self._drag_active = True
                    e.accept()
                    return
            # 按在框上（准备拖框）也算开始拖动：拖动过程中走「轻量」回调
            if isinstance(self.itemAt(e.position().toPoint()), RecogBoxItem):
                self._drag_active = True
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._rubber is not None and self._rubber_from is not None:
            cur = self.mapToScene(e.position().toPoint())
            self._rubber.setRect(QRectF(self._rubber_from, cur).normalized())
            e.accept()
            return
        if self._panning and self._pan_from is not None:
            d = e.position() - self._pan_from
            self._pan_from = e.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))
            e.accept()
            return
        if self._resize is not None:
            d = self._resize
            p = self.mapToScene(e.position().toPoint())
            d["box"].setRect(self._resized_rect(d["rect"], d["idx"],
                                                p.x() - d["start"].x(),
                                                p.y() - d["start"].y()))
            self.note_box_changed(d["box"])
            e.accept()
            return
        self._update_handle_cursor(e.position().toPoint())
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        # 右键：画到一半取消这一笔（画框模式本身不退，方便接着画）
        if e.button() == Qt.RightButton and self._rubber is not None:
            self.cancel_draw()
            e.accept()
            return
        if self._rubber is not None:
            # 拖着画出来的（有面积）→ 直接成型；只是点了一下 → 留在两点画法里等第二次点击
            r = self._rubber.rect().normalized()
            if r.width() >= 3 and r.height() >= 3:
                self._finish_add()
            e.accept()
            return
        if e.button() == Qt.MiddleButton and self._panning:
            self._panning = False
            self.unsetCursor()
            e.accept()
            return
        if self._resize is not None and e.button() == Qt.LeftButton:
            box = self._resize["box"]
            self._resize = None
            self._drag_active = False
            self.note_box_changed(box)          # 松手再写一次，收尾
            self._update_handle_cursor(e.position().toPoint())
            e.accept()
            return
        super().mouseReleaseEvent(e)
        if self._drag_active:
            # 拖框收尾：整个过程只标了脏，这里把表格/统计一次性刷新
            self._drag_active = False
            if self.on_changed:
                try:
                    self.on_changed()
                except Exception:
                    pass
        self._place_handle()

    def keyPressEvent(self, e):
        # ESC：画到一半先丢掉这一笔；再按一次退回选择模式
        # （不这样的话 add_mode 一直挂着：鼠标一动就拖出虚线框、框也选不中）
        if e.key() == Qt.Key_Escape:
            if self.cancel_draw():
                e.accept()
                return
            if self.add_mode and self.on_escape:
                try:
                    self.on_escape()
                except Exception:
                    pass
            e.accept()
            return
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selected()
            e.accept()
            return
        if e.key() == Qt.Key_Z and (e.modifiers() & Qt.ControlModifier):
            self.undo()
            e.accept()
            return
        if e.key() == Qt.Key_C and (e.modifiers() & Qt.ControlModifier):
            if self.copy_selected():
                e.accept()
                return
        if e.key() == Qt.Key_V and (e.modifiers() & Qt.ControlModifier):
            if self.paste_box():
                e.accept()
                return
        # A/D：前 / 后翻一页（和标注软件一致）
        if (e.key() in (Qt.Key.Key_A, Qt.Key.Key_D)
                and not (e.modifiers() & (Qt.ControlModifier | Qt.AltModifier))):
            if self.on_page_key:
                self.on_page_key(-1 if e.key() == Qt.Key.Key_A else 1)
            e.accept()
            return
        if e.key() == Qt.Key_PageDown or (e.key() == Qt.Key_Right and (e.modifiers() & Qt.ControlModifier)):
            if self.on_page_key:
                self.on_page_key(1)
            e.accept()
            return
        if e.key() == Qt.Key_PageUp or (e.key() == Qt.Key_Left and (e.modifiers() & Qt.ControlModifier)):
            if self.on_page_key:
                self.on_page_key(-1)
            e.accept()
            return
        super().keyPressEvent(e)

    def _finish_add(self):
        """把刚拖出来的矩形落成一个新框（写回识别结果 doc）。"""
        r = self._rubber.rect().normalized() if self._rubber is not None else QRectF()
        if self._rubber is not None:
            self.scene().removeItem(self._rubber)
        self._rubber = None
        self._rubber_from = None
        if r.width() < 3 or r.height() < 3 or self.doc is None:
            return False
        kind = self.add_mode or "Node"
        k = float(self.page_w or 1) / max(1.0, self.disp_w)
        bb = {"x1": r.left() * k, "y1": r.top() * k,
              "x2": r.right() * k, "y2": r.bottom() * k}
        self.push_undo()
        trk, ocr = self._page_data()
        if trk is None:
            trk = {"page_number": self.page, "data": {"detections": []}}
            self.doc.setdefault("yolo_tracker_detection_results", []).append(trk)
        dets = (trk.setdefault("data", {})).setdefault("detections", [])
        dets.append({"label": kind, "bbox": bb, "confidence": 1.0,
                     "source": "manual", "raw": {}})
        if kind == "Node":
            if ocr is None:
                ocr = {"page_number": self.page, "data": []}
                self.doc.setdefault("ocr_node_name_results", []).append(ocr)
            ocr.setdefault("data", []).append(
                {"node_bbox": dict(bb), "final_node_name": "",
                 "preliminary_node_name": "", "selected": {}})
        pdf = getattr(self, "_pdf", "")
        if pdf:
            self.reload_page()
        # 和标注软件一样：画完直接选中新框（编号框可用）
        for b in self.box_items:
            if b.det_index == len(dets) - 1:
                self.scene().clearSelection()
                b.setSelected(True)
                self._place_handle()
                break
        if self.on_added:
            try:
                self.on_added(kind, len(dets) - 1)
            except Exception:
                pass
        if self.on_changed:
            self.on_changed()
        return True

    def cancel_draw(self):
        """丢掉画到一半的那一笔（画框模式不退）。返回是否真的取消了东西。"""
        if self._rubber is None:
            return False
        try:
            self.scene().removeItem(self._rubber)
        except Exception:
            pass
        self._rubber = None
        self._rubber_from = None
        return True

    # ---------- 选中 / 编辑 ----------
    def selected_box(self):
        for it in self.scene().selectedItems():
            if isinstance(it, RecogBoxItem):
                return it
        return None

    def select_det(self, det_index, min_px=70.0):
        """选中第 det_index 个框并把它挪到视野中间；太小就顺手放大一点。"""
        for it in self.box_items:
            if it.det_index != det_index:
                continue
            self.scene().clearSelection()
            it.setSelected(True)
            self._place_handle()
            self.centerOn(it)
            r = it.sceneBoundingRect()
            sc = self.transform().m22()
            if r.height() * sc < min_px:          # 太小看不见：放大到能看清
                self.zoom(max(1.5, min_px / max(1.0, r.height() * sc)))
                self.centerOn(it)
            return True
        return False

    def note_selected(self, box):
        self._place_handle()
        if self.on_selected:
            try:
                self.on_selected(box)
            except Exception:
                pass

    def set_lbd_locked(self, on, persist=True):
        """锁住本页的 LBD 区（和标注软件同一套）：点不中、框选不到、拖不动、删不掉。

        锁定状态写进识别结果 raw.lbd_locked，重开 / 重跑还在；支架、汇流箱不受影响。
        persist=False 用于「按识别结果恢复显示」，不重复写 doc。
        """
        self.lbd_locked = bool(on)
        trk, _ocr = self._page_data()
        dets = ((trk or {}).get("data") or {}).get("detections") or []
        for b in self.box_items:
            if b.kind != "Node":
                continue
            b.locked = self.lbd_locked
            b.setFlag(QGraphicsRectItem.ItemIsSelectable, not b.locked)
            b.setFlag(QGraphicsRectItem.ItemIsMovable, not b.locked)
            if persist and 0 <= b.det_index < len(dets):
                raw = dict(dets[b.det_index].get("raw") or {})
                if b.locked:
                    raw["lbd_locked"] = True
                else:
                    raw.pop("lbd_locked", None)
                dets[b.det_index]["raw"] = raw
        sel = self.selected_box()
        if sel is not None and getattr(sel, "locked", False):
            self.scene().clearSelection()
        self._place_handle()

    def _place_handle(self):
        """控制点是画上去的，这里只负责刷新名字标签 + 重绘（名字变了/缩放变了都要叫）。"""
        box = self.selected_box()
        if box is None:
            if getattr(self, "sel_label", None) is not None:
                self.sel_label.setVisible(False)
        else:
            self._update_sel_label(box)
        self.viewport().update()
        self.scene().update()          # drawForeground 挂在场景上，也要催一下

    # ---- 改大小的控制点（对齐标注工具：8 个点、屏幕恒定大小、实时改）----
    HANDLE_CURSORS = [Qt.CursorShape.SizeFDiagCursor,
                      Qt.CursorShape.SizeVerCursor,
                      Qt.CursorShape.SizeBDiagCursor,
                      Qt.CursorShape.SizeHorCursor,
                      Qt.CursorShape.SizeHorCursor,
                      Qt.CursorShape.SizeBDiagCursor,
                      Qt.CursorShape.SizeVerCursor,
                      Qt.CursorShape.SizeFDiagCursor]
    HANDLE_PX = 9.0                    # 控制点在屏幕上的边长

    @staticmethod
    def _handle_points(r):
        """左上、上中、右上、左中、右中、左下、下中、右下（和标注工具同一顺序）。"""
        x1, y1, x2, y2 = r.left(), r.top(), r.right(), r.bottom()
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        return [QPointF(x1, y1), QPointF(cx, y1), QPointF(x2, y1),
                QPointF(x1, cy), QPointF(x2, cy),
                QPointF(x1, y2), QPointF(cx, y2), QPointF(x2, y2)]

    def _handle_at(self, scene_pos):
        """鼠标是不是落在选中框的控制点上，返回控制点序号。"""
        box = self.selected_box()
        if box is None or self.add_mode:
            return None
        sc = max(1e-6, abs(float(self.transform().m11() or 1.0)))
        tol = (self.HANDLE_PX / sc) * 0.8
        for i, p in enumerate(self._handle_points(box.sceneBoundingRect())):
            if abs(scene_pos.x() - p.x()) <= tol and abs(scene_pos.y() - p.y()) <= tol:
                return i
        return None

    @staticmethod
    def _resized_rect(base, idx, dx, dy):
        """按第 idx 个控制点拖 (dx,dy)，返回新矩形（允许拖过头翻转）。"""
        left, top, right, bottom = base.left(), base.top(), base.right(), base.bottom()
        if idx in (0, 3, 5):
            left += dx
        if idx in (2, 4, 7):
            right += dx
        if idx in (0, 1, 2):
            top += dy
        if idx in (5, 6, 7):
            bottom += dy
        r = QRectF(QPointF(left, top), QPointF(right, bottom)).normalized()
        if r.width() < 6.0:
            r.setWidth(6.0)
        if r.height() < 6.0:
            r.setHeight(6.0)
        return r

    def _update_handle_cursor(self, viewport_pos):
        if self.add_mode or self._panning or self._resize is not None:
            return
        sp = self.mapToScene(viewport_pos)
        idx = self._handle_at(sp)
        self.viewport().setCursor(self.HANDLE_CURSORS[idx] if idx is not None
                                  else Qt.CursorShape.ArrowCursor)

    def drawForeground(self, painter, rect):
        """在视口坐标里画控制点：不管缩放到多少，屏幕上始终是同样大小的小方块。"""
        super().drawForeground(painter, rect)
        box = self.selected_box()
        if box is None or self.add_mode:
            return
        hs = self.HANDLE_PX
        painter.save()
        painter.resetTransform()                    # 切到视口坐标
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setPen(QPen(QColor(20, 20, 20, 230), 1))
        painter.setBrush(QColor(255, 216, 0, 235))
        for p in self._handle_points(box.sceneBoundingRect()):
            v = self.mapFromScene(p)
            painter.drawRect(QRectF(v.x() - hs / 2.0 + 0.5, v.y() - hs / 2.0 + 0.5, hs, hs))
        painter.restore()

    def _update_sel_label(self, box, sc=None):
        """选中框的名字：贴在框上方，字号按缩放反算，屏幕上看始终是同一个大小。"""
        lbl = getattr(self, "sel_label", None)
        if lbl is None:
            return
        try:
            trk, ocr = self._page_data()
            recs = ((ocr or {}).get("data") or []) if ocr is not None else []
            j = self.ocr_of.get(box.det_index)
            name = (recs[j].get("final_node_name") or "").strip() if (j is not None and j < len(recs)) else ""
        except Exception:
            name = ""
        if not name:
            lbl.setVisible(False)
            return
        if sc is None:
            sc = max(0.02, float(self.transform().m22() or 1.0))
        f = lbl.font()
        f.setPixelSize(max(9, int(round(13.0 / sc))))
        lbl.setFont(f)
        r = box.sceneBoundingRect()
        lbl.setText(name)
        lb = lbl.boundingRect()
        lbl.setPos(r.left(), r.top() - lb.height() - 2.0 / sc)
        lbl.setVisible(True)

    def _page_data(self):
        doc = self.doc or {}
        trk = next((p for p in doc.get("yolo_tracker_detection_results") or []
                    if p.get("page_number") == self.page), None)
        ocr = next((p for p in doc.get("ocr_node_name_results") or []
                    if p.get("page_number") == self.page), None)
        return trk, ocr

    def push_undo(self):
        import copy
        trk, ocr = self._page_data()
        snap = copy.deepcopy({"trk": (trk or {}).get("data"),
                              "ocr": (ocr or {}).get("data")})
        self._undo.append((self.page, snap))
        if len(self._undo) > 30:
            self._undo.pop(0)

    def undo(self):
        if not self._undo:
            return False
        page, snap = self._undo.pop()
        trk, ocr = self._page_data()
        if trk is not None:
            trk["data"] = snap["trk"]
        if ocr is not None:
            ocr["data"] = snap["ocr"]
        pdf = getattr(self, "_pdf", "")
        if page == self.page and pdf:
            self.reload_page()
        if self.on_changed:
            self.on_changed()
        return True

    def note_box_changed(self, box):
        """框被拖动/改大小后：写回 doc 里的 bbox（Node 同时更新名字记录里的 node_bbox）。"""
        trk, ocr = self._page_data()
        dets = ((trk or {}).get("data") or {}).get("detections") or []
        if not (0 <= box.det_index < len(dets)):
            return
        r = box.sceneBoundingRect()
        k = float(self.page_w or 1) / max(1.0, self.disp_w)
        bb = {"x1": r.left() * k, "y1": r.top() * k,
              "x2": r.right() * k, "y2": r.bottom() * k}
        dets[box.det_index]["bbox"] = bb
        j = self.ocr_of.get(box.det_index)
        recs = ((ocr or {}).get("data") or []) if ocr is not None else []
        if j is not None and j < len(recs):
            recs[j]["node_bbox"] = dict(bb)
        self._place_handle()
        # 拖动过程中只标记改动：每动一下就重建左边表格 + 重算统计会明显卡手
        cb = self.on_changed_fast if self._drag_active else self.on_changed
        if cb:
            cb()

    def delete_selected(self):
        boxes = [it for it in self.scene().selectedItems()
                 if isinstance(it, RecogBoxItem) and not getattr(it, "locked", False)]
        if not boxes:
            return 0
        self.push_undo()
        trk, ocr = self._page_data()
        dets = ((trk or {}).get("data") or {}).get("detections") or []
        recs = ((ocr or {}).get("data") or []) if ocr is not None else []
        kill = sorted({b.det_index for b in boxes}, reverse=True)
        for i in kill:
            if 0 <= i < len(dets):
                del dets[i]
            j = self.ocr_of.get(i)
            if j is not None and j < len(recs):
                recs.pop(j)
                self.ocr_of = {k: (v - 1 if v > j else v)
                               for k, v in self.ocr_of.items() if k != i}
            self.ocr_of.pop(i, None)
        for b in boxes:
            self.scene().removeItem(b)
        self.box_items = [b for b in self.box_items if b.det_index not in kill]
        self._reindex()
        if self.on_changed:
            self.on_changed()
        if self.on_deleted:
            try:
                self.on_deleted(len(kill))
            except Exception:
                pass
        return len(kill)

    def _reindex(self):
        """删过之后 det 下标变了：按当前 dets 顺序重排框和名字下标。"""
        trk, ocr = self._page_data()
        dets = ((trk or {}).get("data") or {}).get("detections") or []
        recs = ((ocr or {}).get("data") or []) if ocr is not None else []
        order = sorted(self.box_items, key=lambda b: b.det_index)
        for new_i, b in enumerate(order):
            b.det_index = new_i
        self.box_items = order
        self.ocr_of = {}
        k = 0
        for i, d in enumerate(dets):
            if (d.get("label") or "") == "Node":
                if k < len(recs):
                    self.ocr_of[i] = k
                k += 1

    def rename_selected(self, name):
        box = self.selected_box()
        if box is None or box.kind != "Node":
            return False
        j = self.ocr_of.get(box.det_index)
        trk, ocr = self._page_data()
        recs = ((ocr or {}).get("data") or []) if ocr is not None else []
        if j is None or j >= len(recs):
            return False
        self.push_undo()
        recs[j]["final_node_name"] = name
        recs[j]["preliminary_node_name"] = name
        sel = recs[j].get("selected") or {}
        sel["text"] = name
        recs[j]["selected"] = sel
        self._place_handle()          # 名字标签跟着刷新（只显示选中这个框）
        if self.on_changed:
            self.on_changed()
        # 项目树开启时也要跟着换名字（以前漏了这一步：改完编号还挂着旧名字）
        if self.on_renamed:
            try:
                self.on_renamed(box.det_index)
            except Exception:
                pass
        return True

    def selected_info(self):
        box = self.selected_box()
        if box is None:
            return None
        trk, ocr = self._page_data()
        dets = ((trk or {}).get("data") or {}).get("detections") or []
        recs = ((ocr or {}).get("data") or []) if ocr is not None else []
        j = self.ocr_of.get(box.det_index)
        nm = (recs[j].get("final_node_name") or "") if (j is not None and j < len(recs)) else ""
        cf = (dets[box.det_index].get("confidence")
              if 0 <= box.det_index < len(dets) else None)
        return {"kind": box.kind, "name": nm, "conf": cf, "ocr_index": j}

    # ---------- 复制 / 粘贴（和标注软件一样：Ctrl+C / Ctrl+V 复制一个框）----------
    def copy_selected(self):
        import copy as _copy
        box = self.selected_box()
        if box is None:
            return False
        trk, ocr = self._page_data()
        dets = ((trk or {}).get("data") or {}).get("detections") or []
        recs = ((ocr or {}).get("data") or []) if ocr is not None else []
        if not (0 <= box.det_index < len(dets)):
            return False
        j = self.ocr_of.get(box.det_index)
        self._clip = {
            "det": _copy.deepcopy(dets[box.det_index]),
            "ocr": _copy.deepcopy(recs[j]) if (j is not None and j < len(recs)) else None,
        }
        return True

    def paste_box(self, offset=12.0):
        """把复制过的框贴到旁边（新框直接选中，方便接着拖）。"""
        clip = getattr(self, "_clip", None)
        if not clip or self.doc is None:
            return False
        import copy as _copy
        self.push_undo()
        trk, ocr = self._page_data()
        if trk is None:
            trk = {"page_number": self.page, "data": {"detections": []}}
            self.doc.setdefault("yolo_tracker_detection_results", []).append(trk)
        det = _copy.deepcopy(clip["det"])
        b = dict(det.get("bbox") or {})
        for k in ("x1", "x2"):
            b[k] = b.get(k, 0) + offset
        for k in ("y1", "y2"):
            b[k] = b.get(k, 0) + offset
        det["bbox"] = b
        det["source"] = "manual"
        dets = (trk.setdefault("data", {})).setdefault("detections", [])
        dets.append(det)
        new_i = len(dets) - 1
        if (det.get("label") or "") == "Node":
            if ocr is None:
                ocr = {"page_number": self.page, "data": []}
                self.doc.setdefault("ocr_node_name_results", []).append(ocr)
            rec = _copy.deepcopy(clip["ocr"]) if clip.get("ocr") else {}
            rec["node_bbox"] = dict(b)
            ocr.setdefault("data", []).append(rec)
        pdf = getattr(self, "_pdf", "")
        if pdf:
            self.reload_page()
            self.select_det(new_i)
        if self.on_added:
            try:
                self.on_added(det.get("label") or "Node", new_i)
            except Exception:
                pass
        if self.on_changed:
            self.on_changed()
        return True


class NoWheelCombo(QComboBox):
    """下拉框：滚轮不切换选项，只能点开列表选。

    Qt 默认鼠标停在下拉框上滚滚轮就会改值，翻页/滚动时很容易误改；
    这里直接忽略滚轮事件（事件会被忽略并传给父级，所以页面照常滚动；
    点开后的列表里照样能用滚轮翻选项）。
    """

    def wheelEvent(self, e):
        e.ignore()


class DrawGrid(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(150)
        self.done = 0
        self.total = 0

    def set_value(self, done, total):
        self.done = done
        self.total = total
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.total <= 0:
            p.setPen(QColor("#727577"))
            p.drawText(self.rect(), Qt.AlignCenter, "等待布局开始后显示每张图进度")
            p.end()
            return
        cols = 8
        gap = 8
        avail = self.width() - 16
        cell = (avail - (cols - 1) * gap) // cols
        x0 = 8
        y0 = 8
        shown = 0
        for i in range(self.total):
            r = i // cols
            c = i % cols
            x = x0 + c * (cell + gap)
            y = y0 + r * (cell + gap)
            if y + cell > self.height():
                break
            if i < self.done:
                col = QColor("#0432FA")
            elif i == self.done:
                col = QColor("#F5A800")
            else:
                col = QColor("#2e3134")
            p.setBrush(col)
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(x, y, cell, cell, 6, 6)
            shown += 1
        p.setPen(QColor("#727577"))
        p.drawText(self.rect().adjusted(8, 0, -8, 0), Qt.AlignBottom | Qt.AlignRight,
                   "已显示 %d / %d 张" % (shown, self.total))
        p.end()


class UpdateDialog(QDialog):
    """更新日志 / 发现新版本的对话框。mode: "update" | "log"。"""

    def __init__(self, version, notes, published, mode, parent=None):
        super().__init__(parent)
        self.chosen = "close"
        self.setWindowTitle("发现新版本" if mode == "update" else "更新日志")
        self.setMinimumSize(640, 470)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 16)
        v.setSpacing(10)

        if mode == "update":
            head = "发现新版本 %s（当前 v%s）" % (version or "-", APP_VERSION)
        else:
            head = "更新日志 %s（当前 v%s）" % (version or "-", APP_VERSION)
        ttl = QLabel(head)
        ttl.setObjectName("UpdTitle")
        v.addWidget(ttl)

        sub = "%s 发布" % published if published else ""
        lab = QLabel(sub)
        lab.setObjectName("UpdSub")
        v.addWidget(lab)

        self.notes = QPlainTextEdit()
        self.notes.setObjectName("Notes")
        self.notes.setReadOnly(True)
        self.notes.setPlainText(notes or "（这个版本没有写更新说明）")
        v.addWidget(self.notes, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        if mode == "update":
            later = QPushButton(T("稍后"))
            later.clicked.connect(self.reject)
            row.addWidget(later)
            go = QPushButton(T("下载并安装"))
            go.setObjectName("Primary")
            go.clicked.connect(self._on_go)
            row.addWidget(go)
        else:
            close = QPushButton(T("关闭"))
            close.setObjectName("Primary")
            close.clicked.connect(self.reject)
            row.addWidget(close)
        v.addLayout(row)

    def _on_go(self):
        self.chosen = "download"
        self.accept()


class StrOrderPreview(QWidget):
    """STR 编号顺序预览：把一个 LBD 组里的支架按当前顺序画成格子示意。

    格子里的号 = 该支架会得到的 STR 号；绿=第 1 个、橙=最后一个；
    连线 = 编号走向（格子行列按支架在图上的左右/上下关系排）。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.page = None
        self.group = ""
        self.cols = 1
        self.rows = 1
        self.items = []
        self.hint = "还没有预览：选好「识别结果 JSON文件」后点「刷新 STR 顺序预览」"
        self.setMinimumHeight(170)
        self.setObjectName("StrPreview")

    def set_data(self, page=None, group="", items=None, hint="", cols=1, rows=1):
        self.page = page
        self.group = group or ""
        self.items = list(items or [])
        self.cols = max(1, int(cols or 1))
        self.rows = max(1, int(rows or 1))
        if hint:
            self.hint = hint
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QColor("#ffffff"))
        p.setPen(QColor("#ccd3dc"))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        f = p.font()
        f.setPointSize(max(8, f.pointSize() - 1))
        p.setFont(f)
        if not self.items:
            p.setPen(QColor("#8a93a0"))
            p.drawText(self.rect().adjusted(12, 12, -12, -12),
                       Qt.AlignCenter | Qt.TextWordWrap, self.hint)
            return
        pad, head, gap = 12, 22, 6
        w = max(40, self.width() - 2 * pad)
        h = max(30, self.height() - 2 * pad - head)
        # 只画前 12 个示意：380 个全塞进来会挤成一片（之前糊成一团就是这个原因）
        MAXN = 12
        items = self.items[:MAXN]
        n = len(items)
        cols = min(4, max(1, n))
        rows = max(1, (n + cols - 1) // cols)
        cw = max(12.0, min(96.0, float(w) / cols))
        chh = max(12.0, min(44.0, float(h) / rows))
        ox = pad + max(0, int((w - cw * cols) / 2.0))
        oy = pad + head + max(0, int((h - chh * rows) / 2.0))
        p.setPen(QColor("#39424e"))
        _title = T("STR 顺序预览：%s", self.hint)
        if len(self.items) > n:
            _title += T("（只显示前 %d / %d 个）", n, len(self.items))
        p.drawText(pad, 2, self.width() - 2 * pad, head, Qt.AlignLeft | Qt.AlignVCenter, _title)

        def cell(i):
            return (ox + (i % cols) * cw, oy + (i // cols) * chh, max(6.0, cw - gap),
                    max(6.0, chh - gap))

        pts = []
        for i in range(n):
            x, y, w2, h2 = cell(i)
            pts.append((int(x + w2 / 2.0), int(y + h2 / 2.0)))
        p.setPen(QColor("#b9c6d6"))
        for i in range(1, len(pts)):
            p.drawLine(pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1])
        for i, it in enumerate(items):
            x, y, w2, h2 = cell(i)
            if i == 0:
                p.setBrush(QColor("#d6f5d6"))
                p.setPen(QColor("#2e8b57"))
            elif i == n - 1:
                p.setBrush(QColor("#ffe6cc"))
                p.setPen(QColor("#d2691e"))
            else:
                p.setBrush(QColor("#eef3f9"))
                p.setPen(QColor("#8aa0b8"))
            p.drawRect(int(x), int(y), int(w2), int(h2))
            p.setPen(QColor("#33414f"))
            _s = str(it[0])
            _fm = p.fontMetrics()
            if _fm.horizontalAdvance(_s) + 2 <= w2:
                p.drawText(int(x), int(y), int(w2), int(h2), Qt.AlignCenter, _s)
            else:                     # 格子太窄：字缩到格子外面一点，至少能认出号
                p.drawText(int(x + w2 / 2.0 - _fm.horizontalAdvance(_s) / 2.0),
                           int(y + h2 / 2.0 - 7), _fm.horizontalAdvance(_s) + 2, 14,
                           Qt.AlignCenter, _s)



class QuadPreview(QWidget):
    """象限预览：只画**规律示意图**，不看识别结果也不用选 JSON。

    中间是原点（= 汇流箱 Box 的几何中心），四个象限各画一小片格子（3 列 x 3 行），
    格子里的号按这个象限当前选的顺序排出来，连线就是编号走向 —— 换一个顺序，
    号立刻换位置，8 种顺序的差别一眼能看出来。
    """

    COLORS = {"I": ("#eaf7ec", "#2e8b57"), "II": ("#e9f0fb", "#31589c"),
              "III": ("#fdf1e4", "#c1701c"), "IV": ("#f4eafc", "#7a49a6")}
    GREY = ("#eef2f6", "#93a2b2")
    COLS, ROWS = 3, 3          # 示意格子：3 列 x 3 行，行优先/列优先一眼能分出来

    def __init__(self, parent=None):
        super().__init__(parent)
        self.orders = {}
        self.hint = "四个象限各用什么顺序（原点 = 本页汇流箱 Box 的几何中心）"
        self.setMinimumHeight(300)
        self.setObjectName("StrPreview")

    def set_data(self, orders=None, hint=""):
        self.orders = dict(orders or {})
        if hint:
            self.hint = hint
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QColor("#ffffff"))
        p.setPen(QColor("#ccd3dc"))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        f = p.font()
        f.setPointSize(max(7, f.pointSize() - 1))
        p.setFont(f)
        pad, head = 12, 20
        p.setPen(QColor("#39424e"))
        p.drawText(pad, 2, max(10, self.width() - 2 * pad), head,
                   Qt.AlignLeft | Qt.AlignVCenter, "象限预览：%s" % self.hint)
        top = head + 4
        aw = max(40, self.width() - 2 * pad)
        ah = max(40, self.height() - pad - top)
        cx0, cy0 = pad + aw // 2, top + ah // 2
        # 四个象限的底色（图像坐标 y 向下：上 = y 小）
        quads = {"I": (cx0, top, pad + aw, cy0), "II": (pad, top, cx0, cy0),
                 "III": (pad, cy0, cx0, top + ah), "IV": (cx0, cy0, pad + aw, top + ah)}
        for q in ("I", "II", "III", "IV"):
            fill, _line = self.COLORS.get(q, self.GREY)
            x1, y1, x2, y2 = quads[q]
            p.fillRect(x1, y1, max(1, x2 - x1 - 1), max(1, y2 - y1 - 1), QColor(fill))
        p.setPen(QColor("#c8d2dc"))
        p.drawLine(pad, cy0, pad + aw, cy0)
        p.drawLine(cx0, top, cx0, top + ah)
        p.setPen(QColor("#d02020"))
        p.setBrush(QColor("#d02020"))
        p.drawEllipse(cx0 - 3, cy0 - 3, 6, 6)
        for q in ("I", "II", "III", "IV"):
            x1, y1, x2, y2 = quads[q]
            self._draw_quad(p, q, x1, y1, x2, y2)

    def _draw_quad(self, p, q, X1, Y1, X2, Y2):
        """一个象限：抬头写「哪个方位 + 用哪条顺序」，下面画 3x3 的号怎么走。"""
        fill, line = self.COLORS.get(q, self.GREY)
        _o = str(self.orders.get(q) or "0")
        _txt = STR_ORDER_TEXT.get(_o, "") or ""
        _txt = _txt.split(":", 1)[-1].strip() if ":" in _txt else _txt
        inner, top = 8, q in ("I", "II")
        p.setPen(QColor(line))
        p.drawText(X1 + inner, (Y1 + 3) if top else (Y2 - 19),
                   max(40, (X2 - X1) - 2 * inner), 16, Qt.AlignLeft | Qt.AlignVCenter,
                   "%s %s → %s %s" % (q, QUAD_CN.get(q, ""), _o, _txt[:10]))
        # 3x3 示意格子：号按这个顺序排（和正式编号同一套规则，见 order_demo_cells）
        cells = demo_cells(_o, self.COLS, self.ROWS)
        gal = max(10, (X2 - X1) - 2 * inner)
        gah = max(10, (Y2 - Y1) - 26 - inner)
        cw = min(38.0, gal / float(self.COLS))
        chh = min(30.0, gah / float(self.ROWS))
        gw, gh = cw * self.COLS, chh * self.ROWS
        ox = (X1 + X2) / 2.0 - gw / 2.0
        oy = (Y1 + Y2) / 2.0 + (8 if top else -8) - gh / 2.0
        oy = max(Y1 + 22 if top else Y1 + 4, min(oy, Y2 - gh - 4))
        fm = p.fontMetrics()
        centers = {}
        for c in cells:
            x = ox + c["col"] * cw
            y = oy + c["row"] * chh
            p.setBrush(QColor("#ffffff"))
            p.setPen(QColor(line))
            p.drawRect(int(x), int(y), int(max(8.0, cw - 4)), int(max(8.0, chh - 4)))
            centers[c["n"]] = (x + (cw - 4) / 2.0, y + (chh - 4) / 2.0)
        p.setPen(QColor("#9fb0c4"))
        for n in range(1, len(cells)):
            if n in centers and (n + 1) in centers:
                p.drawLine(int(centers[n][0]), int(centers[n][1]),
                           int(centers[n + 1][0]), int(centers[n + 1][1]))
        for c in cells:
            _s = "%02d" % c["n"]
            _w = fm.horizontalAdvance(_s)
            x = ox + c["col"] * cw
            y = oy + c["row"] * chh
            p.setPen(QColor("#1f2b3a"))
            if _w + 4 <= cw - 4:
                p.drawText(int(x), int(y), int(max(8.0, cw - 4)), int(max(8.0, chh - 4)),
                           Qt.AlignCenter, _s)
            else:
                p.drawText(int(x + cw / 2 - _w / 2), int(y + chh / 2 - 7), _w + 2, 14,
                           Qt.AlignCenter, _s)


class PrintDialog(QDialog):
    """导出 PDF：勾选要打印的布局 + 选打印设备 / 纸型 / 质量 + 选输出位置。"""

    def __init__(self, parent, layouts, prechecked, devices, default_device,
                 media_provider, out_dir, file_name, prefs=None):
        super().__init__(parent)
        self.setWindowTitle("导出 PDF")
        self.setMinimumWidth(580)
        self._media_provider = media_provider
        self._media_cache = {}
        self._media_note = ""
        self._dpi_cache = {}
        prefs = prefs or {}
        self.data = {}

        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 16)
        v.setSpacing(12)

        title = QLabel("导出 PDF")
        title.setObjectName("PageTitle")
        v.addWidget(title)
        sub = QLabel("勾选要打印的布局；一次把选中的布局打成一份多页 PDF（质量可调）。")
        sub.setObjectName("Hint")
        sub.setWordWrap(True)
        v.addWidget(sub)

        self.list = QListWidget()
        self.list.setMinimumHeight(190)
        preset = set(prechecked or [])
        for nm in layouts:
            it = QListWidgetItem(nm)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            # 没指定默认勾选（比如不是刚跑完流程）就全勾上
            it.setCheckState(Qt.Checked if (not preset or nm in preset) else Qt.Unchecked)
            self.list.addItem(it)
        v.addWidget(self.list)

        hb = QHBoxLayout()
        hb.setSpacing(8)
        for txt, state in (("全选", True), ("全不选", False)):
            b = QPushButton(txt)
            b.setFixedHeight(30)
            b.clicked.connect(lambda _=False, s=state: self._check_all(s))
            hb.addWidget(b)
        self.count_hint = QLabel("")
        self.count_hint.setObjectName("Hint")
        hb.addWidget(self.count_hint, 1)
        v.addLayout(hb)

        g = QGridLayout()
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(10)
        g.addWidget(QLabel("打印设备"), 0, 0)
        self.dev = NoWheelCombo()
        self.dev.setMinimumWidth(360)
        for d in devices:
            self.dev.addItem(d)
        if default_device in devices:
            self.dev.setCurrentIndex(devices.index(default_device))
        g.addWidget(self.dev, 0, 1)
        g.addWidget(QLabel("纸型"), 1, 0)
        self.media = NoWheelCombo()
        g.addWidget(self.media, 1, 1)
        g.addWidget(QLabel("输出目录"), 2, 0)
        dh = QHBoxLayout()
        dh.setSpacing(8)
        self.dir = QLineEdit(out_dir or "")
        dh.addWidget(self.dir, 1)
        db = QPushButton("浏览…")
        db.setFixedHeight(30)
        db.clicked.connect(self._pick_dir)
        dh.addWidget(db)
        g.addLayout(dh, 2, 1)
        g.addWidget(QLabel("文件名"), 3, 0)
        self.name = QLineEdit(file_name or "")
        g.addWidget(self.name, 3, 1)

        # ---- 质量（PDF 清晰度）：打印期间临时改打印设备配置的 dpi，打完自动改回 ----
        g.addWidget(QLabel("质量(线条)"), 4, 0)
        self.qual = NoWheelCombo()
        for lab, val in PDF_QUALITY_CHOICES:
            self.qual.addItem(lab, val)
        self._select_data(self.qual, prefs.get("quality", PDF_QUALITY_DEFAULT))
        g.addWidget(self.qual, 4, 1)
        g.addWidget(QLabel("质量(图片)"), 5, 0)
        self.raster = NoWheelCombo()
        for lab, val in PDF_RASTER_CHOICES:
            self.raster.addItem(lab, val)
        self._select_data(self.raster, prefs.get("raster", -1))
        g.addWidget(self.raster, 5, 1)
        self.open_after = QCheckBox("打完后打开 PDF")
        self.open_after.setChecked(bool(prefs.get("open_after")))
        g.addWidget(self.open_after, 6, 1)
        v.addLayout(g)

        self.hint = QLabel("")
        self.hint.setObjectName("Hint")
        self.hint.setWordWrap(True)
        v.addWidget(self.hint)

        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setFixedHeight(34)
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        self.ok = QPushButton("开始导出")
        self.ok.setObjectName("Primary")
        self.ok.setFixedHeight(34)
        self.ok.clicked.connect(self._accept)
        btns.addWidget(self.ok)
        v.addLayout(btns)

        self.list.itemChanged.connect(self._sync_hint)
        self.dir.textChanged.connect(self._sync_hint)
        self.name.textChanged.connect(self._sync_hint)
        self.dev.currentIndexChanged.connect(self._reload_media)
        self.qual.currentIndexChanged.connect(self._sync_hint)
        self.raster.currentIndexChanged.connect(self._sync_hint)
        self._reload_media()
        self._sync_hint()

    # ---- 内部 ----
    def _select_data(self, combo, val):
        """按值选一项（存的是数字，界面上显示的是文字），没有就保持第一项。"""
        idx = combo.findData(val)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _check_all(self, state):
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(Qt.Checked if state else Qt.Unchecked)

    def checked_layouts(self):
        out = []
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.checkState() == Qt.Checked:
                out.append(it.text())
        return out

    def out_name(self):
        nm = (self.name.text() or "").strip() or "MAP文件"
        if not nm.lower().endswith(".pdf"):
            nm += ".pdf"
        return nm

    def _sync_hint(self, *_a):
        n = len(self.checked_layouts())
        self.count_hint.setText("已勾选 %d 个布局" % n)
        d = (self.dir.text() or "").strip()
        where = os.path.join(d, self.out_name()) if d else self.out_name()
        q = int(self.qual.currentData() or 0)
        rr = self.raster.currentData()
        r = int(rr if rr is not None else -1)
        txt = ("输出：%s（一次把这 %d 个布局交给 CAD 打完，再合成一份多页 PDF）"
               % (where, n))
        if q > 0 or r > 0:
            txt += "\n质量：%s（打印期间临时改打印设备的配置，打完自动改回）" % quality_text(q, r)
        else:
            dev = self.dev.currentText()
            if dev not in self._dpi_cache:
                self._dpi_cache[dev] = device_pc5_quality(dev)
            vdpi, rdpi = self._dpi_cache[dev]
            if vdpi:
                txt += ("\n质量：跟随设备（%s 现在矢量 %d dpi、图片 %d dpi）—— 想改就在上面选"
                        % (dev, vdpi, rdpi))
            else:
                txt += "\n质量：跟随设备（这台设备不是 CAD 的绘图仪配置，质量改不了）"
        if self._media_note:
            txt += "\n" + self._media_note
        self.hint.setText(txt)
        self.ok.setEnabled(n > 0)

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择导出目录",
                                             (self.dir.text() or "").strip())
        if d:
            self.dir.setText(d)

    def _reload_media(self, *_a):
        dev = self.dev.currentText()
        keep = self.media.currentData() if self.media.count() else None
        self.media.clear()
        self.media.addItem("随布局页面设置（不改纸型）", "")
        pairs = self._media_cache.get(dev)
        if pairs is None:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                pairs = list(self._media_provider(dev) or []) if self._media_provider else []
            except Exception:
                pairs = []
            finally:
                QApplication.restoreOverrideCursor()
            self._media_cache[dev] = pairs
        for label, canon in pairs:
            self.media.addItem(label, canon)
        if keep:
            idx = self.media.findData(keep)
            if idx >= 0:
                self.media.setCurrentIndex(idx)
        self._media_note = ("（没读到这个设备的纸型清单，将按图纸原来的纸型打印）"
                            if self.media.count() <= 1 else "")
        self._sync_hint()

    def _accept(self):
        if not self.checked_layouts():
            QMessageBox.warning(self, "导出 PDF", "至少要勾选一个布局。")
            return
        d = (self.dir.text() or "").strip()
        if not d:
            QMessageBox.warning(self, "导出 PDF", "请填输出目录。")
            return
        if not os.path.isdir(d):
            if QMessageBox.question(self, "导出 PDF", "目录不存在：\n%s\n\n要新建吗？" % d) != QMessageBox.Yes:
                return
            try:
                os.makedirs(d, exist_ok=True)
            except Exception as e:
                QMessageBox.warning(self, "导出 PDF", "建目录失败：%s" % e)
                return
        self.data = {"layouts": self.checked_layouts(),
                     "device": self.dev.currentText(),
                     "media": self.media.currentData() or "",
                     "quality": int(self.qual.currentData() or 0),
                     "raster": int(self.raster.currentData() if self.raster.currentData() is not None else -1),
                     "open_after": bool(self.open_after.isChecked()),
                     "out_path": os.path.join(d, self.out_name())}
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.bus = Bus()
        self.bus.prog.connect(self.on_prog)
        self.bus.racks.connect(self.on_rack_types)
        self.bus.strprev.connect(self.on_str_preview)
        self.bus.quadprev.connect(self.on_quad_preview)
        self.bus.err.connect(self.on_err)
        self.bus.done.connect(self.on_done)
        self.bus.status.connect(self.on_status)
        self.bus.save_result.connect(self.on_save_result)
        self.bus.plot_prog.connect(self.on_plot_prog)
        self.bus.plot_result.connect(self.on_plot_result)
        self.bus.upd_found.connect(self.on_upd_found)
        self.bus.upd_none.connect(self.on_upd_none)
        self.bus.upd_notes.connect(self.on_upd_notes)
        self.bus.upd_error.connect(self.on_upd_error)
        self.bus.upd_progress.connect(self.on_upd_progress)
        self.bus.upd_detail.connect(self.on_upd_detail)
        self.bus.upd_log.connect(self.on_upd_log)
        self.bus.upd_ready.connect(self.on_upd_ready)
        self.bus.recog_prog.connect(self.on_recog_prog)
        self.bus.recog_log.connect(self.on_recog_log)
        self.bus.recog_done.connect(self.on_recog_done)
        self.edits = {}
        self.checkbox = {}
        self.combo = {}
        self.run_active = False
        self._finish_ready = False
        self._ai_step = False
        self._phase = ""
        self._upd_url = ""
        self._upd_tag = ""
        self._upd_install = False
        self._upd_silent = False
        self._upd_pct = 0
        self._upd_detail = ""
        self._upd_logged = -1
        self.total = 0
        self.done_n = 0
        self.run_status = ""
        self._prog_path = None
        self._prog_len = 0
        self._poll_timer = None
        self._generated_layouts = []      # 本次生成的布局名（导出 PDF 默认勾这些）
        self._print_prefs = {}            # 上次选过的设备/纸型/目录（只在本次运行内记）
        # 中英文：所有会显示文字、并且要跟着语言切换刷新的控件
        self._i18n = []                   # [(控件, 中文原文)]
        self._i18n_tip = []               # [(控件, 中文 tooltip)]
        self._i18n_combo = []             # [(下拉框, [(中文, 值)])]
        self._i18n_headers = []           # [(表格, [中文表头])]
        self._i18n_ph = []                # [(输入框, 中文占位提示)]
        self._i18n_nav = []               # 侧边栏导航按钮
        self._step_times = {}             # 本轮执行每一步的耗时
        self._run_started = None
        self._paused = False
        self._build_ui()
        self.set_cfg(load_config())
        # 打开就是「识别」这一屏（没有参数页/侧边栏）：选 PDF → 识别 → 改好 → 下一步才进画图流程
        self.show_recog_workspace()
        # 起始页/结束页 失焦或按回车时，按范围自动算出“复制数量”（不逐字触发，避免卡输入）
        for _k in ("pageStart", "pageEnd"):
            _w = self.edits.get(_k)
            if _w:
                _w.editingFinished.connect(self._recalc_count_from_range)
        self.setWindowTitle("%s v%s" % (APP_TITLE, APP_VERSION))
        # 键盘：Ctrl+B 随时回识别（生成完想改识别结果就按它）；PgUp/PgDn 在识别页翻页
        try:
            from PySide6.QtGui import QShortcut, QKeySequence
            self._sc_back = QShortcut(QKeySequence("Ctrl+B"), self)
            self._sc_back.activated.connect(self.show_recog_workspace)
            # 识别画布：缩放 / 适应不再放按钮，全靠快捷键（和标注软件的习惯一致）
            for _seq, _slot in (("Ctrl++", self.on_recog_zoom_in),
                                ("Ctrl+=", self.on_recog_zoom_in),
                                ("Ctrl+-", self.on_recog_zoom_out),
                                ("Ctrl+0", self.on_recog_fit_page),
                                ("Ctrl+1", self.on_recog_fit)):
                _sc = QShortcut(QKeySequence(_seq), self)
                _sc.activated.connect(_slot)
        except Exception:
            pass
        # 窗口尺寸：默认开到能一眼看全（识别页三栏 + 支架表 + 日志），最小尺寸也放宽一点，
        # 但页面都能滚动，小屏也不会把控件挤没。
        self.resize(1560, 960)
        self.setMinimumSize(1180, 720)
        try:
            scr = QApplication.primaryScreen()
            if scr is not None:
                av = scr.availableGeometry()
                w = min(1560, max(1180, av.width() - 80))
                h = min(960, max(720, av.height() - 80))
                self.resize(w, h)
        except Exception:
            pass
        # 启动后静默查一次更新（只有发现新版才会提示）
        QTimer.singleShot(2500, lambda: self.on_check_update(silent=True))

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("Root")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        # 顶栏
        header = QFrame()
        header.setObjectName("Header")
        header.setFixedHeight(56)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(18, 0, 18, 0)
        logo = self._logo_label(30)
        ttl = QLabel(APP_TITLE)
        ttl.setObjectName("AppTitle")
        hl.addWidget(logo)
        hl.addSpacing(10)
        hl.addWidget(ttl)
        hl.addStretch(1)
        # 顶部栏右侧：当前版本 + 在线更新
        self.upd_label = QLabel("")
        self.upd_label.setObjectName("UpdLabel")
        self.upd_label.setFixedWidth(190)          # 固定宽度：进度数字变化时不再顶动旁边的控件
        self.upd_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        hl.addWidget(self.upd_label)
        ver = QLabel("v%s" % APP_VERSION)
        ver.setObjectName("VerLabel")
        ver.setFixedWidth(64)      # 中英文字体宽度不同，留一点余量别把字切掉
        ver.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        hl.addWidget(ver)
        hl.addSpacing(8)
        # 语言切换（图标按钮，最右边）
        self.lang_btn = QPushButton()
        self.lang_btn.setObjectName("IconBtn")
        self.lang_btn.setFixedSize(28, 28)
        self.lang_btn.setIcon(make_icon("lang"))
        self.lang_btn.setIconSize(QSize(18, 18))
        self.lang_btn.clicked.connect(self.on_switch_lang)
        self._reg_tip(self.lang_btn, "中英文切换")
        hl.addWidget(self.lang_btn)
        hl.addSpacing(6)
        # 更新 / 更新日志：都改成图标按钮（鼠标悬停有说明）
        self.upd_btn = QPushButton()
        self.upd_btn.setObjectName("IconBtn")
        self.upd_btn.setFixedSize(28, 28)
        self.upd_btn.setIcon(make_icon("update"))
        self.upd_btn.setIconSize(QSize(18, 18))
        self.upd_btn.clicked.connect(self.on_upd_click)
        self.upd_btn.setToolTip("检查更新")
        hl.addWidget(self.upd_btn)
        self.notes_btn = QPushButton()
        self.notes_btn.setObjectName("IconBtn")
        self.notes_btn.setFixedSize(28, 28)
        self.notes_btn.setIcon(make_icon("notes"))
        self.notes_btn.setIconSize(QSize(18, 18))
        self.notes_btn.clicked.connect(self.on_show_notes)
        self.notes_btn.setToolTip("更新日志")
        hl.addWidget(self.notes_btn)
        root.addWidget(header)
        # 主体：侧边栏 + 内容
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.sidebar = self._build_sidebar()
        body.addWidget(self.sidebar)
        self.content_stack = QStackedWidget()
        self.section_stack = QStackedWidget()
        for s_i, (sec_title, keys) in enumerate(SECTIONS):
            # 每页套一层滚动区：窗口小的时候也不会把控件挤没/挤出去
            _page = self._build_section_page(s_i, sec_title, keys)
            _sa = QScrollArea()
            _sa.setWidgetResizable(True)
            _sa.setFrameShape(QFrame.NoFrame)
            _sa.setWidget(_page)
            self.section_stack.addWidget(_sa)
        self.content_stack.addWidget(self.section_stack)   # 0 = 表单
        self.content_stack.addWidget(self._build_status_page())  # 1 = 执行状态
        self.content_stack.addWidget(self._build_recog_page())    # 2 = 识别工作区（独立一屏）
        body.addWidget(self.content_stack, 1)
        root.addLayout(body, 1)
        # 底部：操作按钮 + 日志
        footer = QFrame()
        footer.setObjectName("Footer")
        fl = QVBoxLayout(footer)
        fl.setContentsMargins(16, 8, 16, 12)
        fl.setSpacing(8)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.back_recog_btn = self._reg(QPushButton(), "← 返回识别")
        self._reg_tip(self.back_recog_btn, "回到识别界面（换 PDF / 重新识别 / 改框和编号）")
        self.back_recog_btn.clicked.connect(self.show_recog_workspace)
        actions.addWidget(self.back_recog_btn)
        # 识别工作区用到的两个：上一步 / 下一步（只在识别页显示，和暂停/停止/执行同一行）
        self.recog_prev_btn = self._reg(QPushButton(), "← 上一步")
        self._reg_tip(self.recog_prev_btn, "回到识别工作区（换 PDF / 重新识别 / 改框）")
        self.recog_prev_btn.clicked.connect(self.show_recog_workspace)
        self.recog_prev_btn.setVisible(False)
        actions.addWidget(self.recog_prev_btn)
        self.recog_next_btn = self._reg(QPushButton(), "下一步：填其它参数 →")
        self.recog_next_btn.setObjectName("Primary")
        self.recog_next_btn.clicked.connect(self.on_recog_next)
        self.recog_next_btn.setVisible(False)
        actions.addWidget(self.recog_next_btn)
        actions.addStretch(1)
        # 随时可停：执行旁边一个「暂停 / 继续」（执行中才可用）
        self.pause_btn = self._reg(QPushButton(), "暂停")
        self.pause_btn.setObjectName("WarnBtn")
        self.pause_btn.setEnabled(False)
        self._reg_tip(self.pause_btn, "暂停执行（随时可停）")
        self.pause_btn.clicked.connect(self.on_pause)
        actions.addWidget(self.pause_btn)
        # 真·随时停止：写停止标记，CAD 侧的插件在每个检查点看到就收尾停下
        self.stop_btn = self._reg(QPushButton(), "停止")
        self.stop_btn.setObjectName("WarnBtn")
        self.stop_btn.setEnabled(False)
        self._reg_tip(self.stop_btn, "立刻停止本次执行（CAD 侧会在下一个检查点收尾停下）")
        self.stop_btn.clicked.connect(self.on_stop)
        actions.addWidget(self.stop_btn)
        b = self._reg(QPushButton(), "执行")
        b.setObjectName("Primary")
        b.clicked.connect(self.on_run)
        self.run_btn = b
        actions.addWidget(b)
        fl.addLayout(actions)
        self.log = QPlainTextEdit()
        self.log.setObjectName("Log")
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(130)
        fl.addWidget(self.log)
        root.addWidget(footer)
        self.show_section(0)

    def _logo_label(self, size):
        lbl = QLabel()
        lbl.setObjectName("Logo")
        path = find_logo()
        if path:
            pm = QPixmap(path)
            if not pm.isNull():
                lbl.setPixmap(pm.scaled(int(size), int(size), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            lbl.setText("V")
        lbl.setAlignment(Qt.AlignCenter)
        return lbl

    def _build_sidebar(self):
        sb = QFrame()
        sb.setObjectName("Sidebar")
        sb.setFixedWidth(258)
        v = QVBoxLayout(sb)
        v.setContentsMargins(14, 18, 14, 18)
        v.setSpacing(6)
        logo = self._logo_label(72)
        v.addWidget(logo)
        v.addSpacing(20)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        for i, (sec_title, _) in enumerate(SECTIONS):
            b = QPushButton(T(sec_title))
            b.setObjectName("Nav")
            b.setCheckable(True)
            b.setFixedHeight(44)
            b.clicked.connect(lambda _=False, idx=i: self.show_section(idx))
            self.nav_group.addButton(b, i)
            self._i18n_nav.append((b, sec_title))
            v.addWidget(b)
        if SECTIONS:
            self.nav_group.button(0).setChecked(True)
        v.addStretch(1)
        return sb

    def _build_section_page(self, s_idx, sec_title, keys):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(14)
        h = self._reg(QLabel(), sec_title)
        h.setObjectName("PageTitle")
        outer.addWidget(h)
        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        rack_panel = None
        label_panel = None
        if sec_title == "选项":
            r = 0
            for key, txt, init in [("regionFit", "生成布局后按 LBD 区域上下限对准视口", True)]:
                cb = self._reg(QCheckBox(), txt)
                cb.setChecked(init)
                self.checkbox[key] = cb
                form.addWidget(cb, r, 0, 1, 2)
                r += 1
            # 标签位置固定模型空间（界面不再给选）：CAD 侧「填到布局」要按当前布局的最大视口
            # 把模型坐标换成图纸坐标，多布局/视口不规则时容易错位；见 cfg() 里的 labelWhere = "M"。
        else:
            # 支架类型 + 拆不拆：每类支架可以选 不拆 / 2行 / 3行；
            # 选了几行，这个支架框就沿长边均分成几行，每行各一个 STR 号；
            # 号按上面的「STR 编号顺序」在整个 LBD 区域里走一个顺序，不是同一张支架连号。
            # 哪一列属于哪一类，按框长比例对「长度FT」（见 lbd_regions.rack_type_indices）。
            r = 0
            for key, label in keys:
                if key == "strQuadOn":
                    # 标签页里给「四象限规矩」这一段单独起个小标题，和上面的标签设置分开
                    sub = self._reg(QLabel(), "STR 编号方向 · 按汇流箱(Box)四象限规矩")
                    sub.setObjectName("FieldLabel")
                    form.addWidget(sub, r, 0, 1, 2)
                    r += 1
                lb = self._reg(QLabel(), label)
                lb.setObjectName("FieldLabel")
                form.addWidget(lb, r, 0)
                if key in ("strBgColor", "strTextColor", "labelBgColor", "labelTextColor"):
                    cb = NoWheelCombo()
                    cb.setObjectName("Field")
                    cb.setMinimumWidth(320)
                    self._reg_combo(cb, COLOR_CHOICES)
                    self.combo[key] = cb
                    form.addWidget(cb, r, 1)
                elif key in ("strOrder",) + tuple(k for k, _t in QUAD_FIELDS):
                    cb = NoWheelCombo()
                    cb.setObjectName("Field")
                    cb.setMinimumWidth(320)
                    if key == "strOrder":
                        self._reg_combo(cb, STR_ORDER_CHOICES, en=STR_ORDER_EN)
                    else:
                        # 象限下拉：第一项是「0 = 这个象限不改」，其余就是 8 种顺序
                        self._reg_combo(cb, [("0 用全局顺序（该象限不改）", "0")] + list(STR_ORDER_CHOICES),
                                        en=["0 use global order (leave this quadrant)"] + list(STR_ORDER_EN))
                    self.combo[key] = cb
                    cb.currentIndexChanged.connect(lambda *_: self.on_refresh_str_preview())
                    cb.currentIndexChanged.connect(lambda *_: self.on_refresh_quad_preview())
                    form.addWidget(cb, r, 1)

                elif key in ("strBgOn", "rackAlign", "rackAvoid"):
                    cb = NoWheelCombo()
                    cb.setObjectName("Field")
                    cb.setMinimumWidth(320)
                    self._reg_combo(cb, [("开", "1"), ("关", "0")])
                    self.combo[key] = cb
                    form.addWidget(cb, r, 1)
                elif key == "rackSplit":
                    # 直接填「拆几行」：0 / 空 = 不拆，2 = 拆 2 行，3 = 拆 3 行……
                    edit = QLineEdit()
                    edit.setObjectName("Field")
                    edit.setMinimumWidth(320)
                    self._reg_ph(edit, "0 = 不拆；填 2 / 3 … 表示拆几行")
                    self.edits[key] = edit
                    form.addWidget(edit, r, 1)
                elif key == "strQuadOn":
                    cb = NoWheelCombo()
                    cb.setObjectName("Field")
                    cb.setMinimumWidth(320)
                    self._reg_combo(cb, [("开：按四象限规律命名", "1"),
                                         ("关：一律按「支架」页的全局顺序", "0")])
                    self.combo[key] = cb
                    cb.currentIndexChanged.connect(lambda *_: self.on_quad_on_changed())
                    form.addWidget(cb, r, 1)
                else:
                    edit = QLineEdit()
                    edit.setObjectName("Field")
                    edit.setMinimumWidth(320)
                    self.edits[key] = edit
                    form.addWidget(edit, r, 1)
                    if key in BROWSE_KEYS:
                        bb = self._reg(QPushButton(), "选择")
                        bb.clicked.connect(lambda _=False, k=key: self.browse(k))
                        form.addWidget(bb, r, 2)
                r += 1
                if key == "strQuadIV":
                    _qh = self._reg(QLabel(),
                        "判据：原点 = 本页汇流箱(Box)中心，看 LBD 区域中心的方位（u 右为正、v 上为正）"
                        "——I 右上 / II 左上 / III 左下 / IV 右下；离原点太近、或这页没有汇流箱时用全局顺序。"
                        "关掉开关时四个下拉都不生效。改完看下面的「象限预览」。")
                    _qh.setObjectName("Hint")
                    self._shrinkable(_qh, 120)
                    form.addWidget(_qh, r, 0, 1, 2)
                    r += 1
            if sec_title == "支架标签":
                rack_panel = self._build_rack_panel()
                label_panel = self._build_label_panel()
        outer.addLayout(form)
        if rack_panel is not None:
            outer.addWidget(rack_panel)
        if label_panel is not None:
            outer.addWidget(label_panel)
        outer.addStretch(1)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setWidget(page)
        return sc

    # ---------------- 识别页：主程序自带识别（v4c / onnxruntime） ----------------
    def _build_recog_page(self):
        page = QWidget()
        page.setObjectName("RecogPage")          # 这一页单独用紧凑尺寸（见 QSS）
        outer = QVBoxLayout(page)
        outer.setContentsMargins(16, 10, 16, 10)
        outer.setSpacing(6)
        # 标题和操作挤在同一行：PDF 走「上传」按钮，文件名不占地方
        # （长路径显示不下也没意义；完整路径放在状态小字的提示里）
        head = QHBoxLayout()
        head.setSpacing(8)
        h = self._reg(QLabel(), "识别")
        h.setObjectName("PageTitle")
        head.addWidget(h)
        head.addStretch(1)
        # 顶部：当前页 / 总页数（跟着左边表格和画布翻页走）
        self.recog_page_label = QLabel("")
        self.recog_page_label.setObjectName("RecogStatus")
        head.addWidget(self.recog_page_label)
        self.recog_pdf_state = QLabel("")
        self.recog_pdf_state.setObjectName("RecogStatus")
        head.addWidget(self.recog_pdf_state)
        b = self._reg(QPushButton(), "上传 PDF")
        self._reg_tip(b, "选要识别的 PDF（图纸集）；整本识别，跑完再用「过滤」挑页")
        b.clicked.connect(lambda: self._recog_pick("pdf"))
        head.addWidget(b)
        self.recog_btn = self._reg(QPushButton(), "开始识别")
        self.recog_btn.setObjectName("Primary")
        self.recog_btn.clicked.connect(self.on_recognize)
        self.recog_btn.setMinimumWidth(110)
        head.addWidget(self.recog_btn)
        outer.addLayout(head)

        # 数据载体：PDF 路径和「文件与输出」页共用一份，界面上不显示（只显示上面的「已选择」）
        self.recog_pdf_edit = QLineEdit()
        self.recog_pdf_edit.setObjectName("Field")
        self._reg_ph(self.recog_pdf_edit, "选要识别的 PDF（图纸集）")
        self.recog_pdf_edit.setVisible(False)

        tip = self._reg(QLabel(),
                        "整本识别（模型 v4c 在程序里跑），跑完自动填「识别结果 JSON文件」；"
                        "页数多了就用下面的「只保留 / 过滤」挑页。")
        tip.setObjectName("RecogTip")
        tip.setVisible(False)          # 识别下方的小字不要（用户要求）
        self._shrinkable(tip, 120)
        outer.addWidget(tip)

        # 进度条 + 状态并成一行：进度条细一点，百分比和时间都写在右边文字里
        prow0 = QHBoxLayout()
        prow0.setSpacing(8)
        self.recog_bar = QProgressBar()
        self.recog_bar.setTextVisible(False)     # 细条只画进度，百分比/时间在右边单独一行
        self.recog_bar.setValue(0)
        self.recog_bar.setMinimumWidth(240)
        self.recog_bar.setFixedHeight(8)
        prow0.addWidget(self.recog_bar)
        self.recog_prog_text = QLabel("")
        self.recog_prog_text.setObjectName("RecogStatus")
        self.recog_prog_text.setFixedWidth(260)
        prow0.addWidget(self.recog_prog_text)
        self.recog_status = QLabel("")
        self.recog_status.setObjectName("RecogStatus")   # 单独的小字号（见 QSS）
        self._shrinkable(self.recog_status, 120)
        prow0.addWidget(self.recog_status, 1)
        outer.addLayout(prow0)
        # 结果区：左表格 / 中画布 / 右侧支架长度分档
        res = QHBoxLayout()
        res.setSpacing(10)
        self.recog_table = QTableWidget(0, 3)
        self.recog_table.setObjectName("RecogPages")
        self._reg_headers(self.recog_table, ["页", "LBD 数", "配到编号"])
        self.recog_table.verticalHeader().setVisible(False)
        self.recog_table.verticalHeader().setDefaultSectionSize(20)   # 行紧凑一点
        self.recog_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.recog_table.setSelectionBehavior(QTableWidget.SelectRows)
        # 三列平铺、不横向滚：以前最后一列被拉伸、其余列按内容撑宽，看着空还得左右拖
        self.recog_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        try:
            _h = self.recog_table.horizontalHeader()
            _h.setSectionResizeMode(QHeaderView.Stretch)
            _h.setMinimumSectionSize(34)
            _h.setStretchLastSection(False)
            _h.setDefaultAlignment(Qt.AlignCenter)
        except Exception:
            pass
        self.recog_table.setMinimumWidth(150)
        self.recog_table.setMaximumWidth(205)
        _sep = QFrame()
        _sep.setFixedWidth(1)
        _sep.setStyleSheet("background-color:#2a2c2e;")
        res.addWidget(_sep)
        res.addSpacing(4)
        self.recog_table.itemSelectionChanged.connect(self.on_recog_page_changed)
        res.addWidget(self.recog_table)
        pv = QVBoxLayout()
        # 「预览」那一行去掉了：换页直接点左边表格里的页，或者 PgUp/PgDn（Ctrl+←/→），
        # 支架前后用 A/D。这行原来的信息（本页统计 / 选中情况）挪到画布下面那行。
        # 工具条分两行摆：窗口窄的时候也不会把整页撑宽（否则只能左右滑）
        tb = QGridLayout()
        tb.setHorizontalSpacing(6)
        tb.setVerticalSpacing(4)
        # 缩放 / 适应 / 删除 / 撤销 都不放按钮了 —— 键盘和鼠标就能做（见下面的快捷键说明）
        col = 0
        # 画框工具：和标注软件一套（画 Box / 画支架 / 画 LBD 区），点一下进去、再点一下退出
        self.recog_draw_btns = {}
        for _label, _kind in (("画 Box", "Box"), ("画支架", "Tracker"), ("画 LBD 区", "Node")):
            b = self._reg(QPushButton(), _label)
            b.setCheckable(True)
            b.setObjectName("DrawTool")
            self._reg_tip(b, "点一下进入这个绘制模式，再在画布上拖一下就画出来；再点一下退出")
            b.clicked.connect(lambda _=False, k=_kind: self.on_recog_draw_mode(k))
            tb.addWidget(b, 1, col)
            col += 1
            self.recog_draw_btns[_kind] = b
        # 锁定本页 LBD 区：改支架时别把 LBD 框碰歪（每页各记各的）
        self.recog_lock_btn = self._reg(QPushButton(), "锁定 LBD")
        self.recog_lock_btn.setCheckable(True)
        self._reg_tip(self.recog_lock_btn,
                      "锁住本页的 LBD 区：不能拖动 / 改大小 / 删除（支架、汇流箱照常编辑）；每页各记各的")
        self.recog_lock_btn.toggled.connect(self.on_recog_lock_lbd)
        tb.addWidget(self.recog_lock_btn, 1, col)
        col += 1
        tb.addWidget(self._reg(QLabel(), "编号"), 1, col)
        col += 1
        self.recog_name_edit = QLineEdit()
        self.recog_name_edit.setObjectName("Field")
        self._reg_ph(self.recog_name_edit, "选中一个 LBD 区后可改名")
        self.recog_name_edit.setMinimumWidth(120)
        self.recog_name_edit.returnPressed.connect(self.on_recog_rename)
        tb.addWidget(self.recog_name_edit, 1, col, 1, 3)
        col += 3
        b = self._reg(QPushButton(), "改名")
        b.clicked.connect(self.on_recog_rename)
        tb.addWidget(b, 1, col)
        col += 1
        self.recog_save_btn = self._reg(QPushButton(), "保存修改")
        self.recog_save_btn.setEnabled(False)
        self.recog_save_btn.clicked.connect(self.on_save_recog_edits)
        tb.addWidget(self.recog_save_btn, 1, col)
        col += 1
        pv.addLayout(tb)
        # 总体问题条：在画布正上方，显示“几页有问题”，点一下列出有问题的页并跳过去
        self.recog_issue_bar = QPushButton(T("检查问题"))
        self.recog_issue_bar.setCursor(Qt.PointingHandCursor)
        self.recog_issue_bar.setMinimumHeight(26)
        self.recog_issue_bar.setToolTip(T("识别完成后点这里，看哪几页有问题"))
        self.recog_issue_bar.clicked.connect(self._on_issue_bar_clicked)
        pv.addWidget(self.recog_issue_bar, 0, Qt.AlignLeft)
        self.recog_canvas = RecogCanvas(self)
        self.recog_canvas.setMinimumWidth(200)     # 窄窗口下画布先让出宽度，别撑出横向滚动
        self.recog_canvas.setMinimumHeight(260)
        # 画布上**不挂**鼠标提示：悬停就弹一大串字很烦（用户反馈过）。
        # 快捷键改挂到工具条那个「快捷键」小按钮上，要看自己点。
        self.recog_canvas.on_changed = self._recog_mark_dirty
        self.recog_canvas.on_changed_fast = self._recog_mark_dirty_light
        self.recog_canvas.on_selected = self.on_recog_box_selected
        self.recog_canvas.on_added = self.on_recog_box_added
        self.recog_canvas.on_deleted = self.on_recog_box_deleted
        self.recog_canvas.on_renamed = self.on_recog_renamed
        self.recog_canvas.on_lock_changed = self._sync_lock_btn
        self.recog_canvas.on_escape = self.on_recog_escape
        self.recog_canvas.on_page_key = self.on_recog_page_step
        self.recog_canvas.on_rack_step = self.on_recog_rack_step
        pv.addWidget(self.recog_canvas, 1)
        prow2 = QHBoxLayout()
        # 本页统计 / 选中情况（原来挂在「预览」那一行，那行去掉了挪到这里）
        self.recog_preview_info = self._reg(
            QLabel(), "识别完这里会画出识别到的框（蓝=LBD 区，红=支架，橙=编号位置）")
        self.recog_preview_info.setObjectName("RecogTip")
        self._shrinkable(self.recog_preview_info, 160)
        prow2.addWidget(self.recog_preview_info, 1)
        self.recog_export_btn = self._reg(QPushButton(), "导出识别结果 JSON…")
        self.recog_export_btn.setEnabled(False)
        self.recog_export_btn.clicked.connect(self.on_export_recog_json)
        prow2.addWidget(self.recog_export_btn)
        prow2.addWidget(self._reg(QLabel(), "只保留"))
        self.recog_keep_edit = QLineEdit()
        self.recog_keep_edit.setObjectName("Field")
        self._reg_ph(self.recog_keep_edit, "页范围，如 23-108")
        self.recog_keep_edit.setMaximumWidth(140)
        prow2.addWidget(self.recog_keep_edit)
        b = self._reg(QPushButton(), "过滤")
        self._reg_tip(b, "把不在这段页码里的识别结果丢掉（封面/说明/清单页这类不该画的页）")
        b.clicked.connect(self.on_recog_filter_pages)
        prow2.addWidget(b)
        pv.addLayout(prow2)
        res.addLayout(pv, 1)
        # 右栏：整册支架长度 → 串数（整册的支架类型在这儿填）
        nv = QVBoxLayout()
        rt = self._reg(QLabel(), "整册支架长度 → 串数")
        rt.setObjectName("Hint")
        self._reg_tip(rt, "识别到的每一档都在这儿；填上串数就按它匹配整册支架类型")
        self._shrinkable(rt, 110)
        nv.addWidget(rt)
        self.recog_rack_table = QTableWidget(0, 4)
        self._reg_headers(self.recog_rack_table, ["串数", "长度", "数量", "拆几行"])
        self.recog_rack_table.verticalHeader().setVisible(False)
        self.recog_rack_table.setMinimumWidth(232)     # 右栏窄，四列摊开自动缩，不出横向滚动
        self.recog_rack_table.setMinimumHeight(108)
        self.recog_rack_table.setMaximumHeight(150)
        self.recog_rack_table.setToolTip("点某一档 → 跳到那档支架的实际位置（再点一次看下一个）")
        try:
            # 英文表头比中文长（Strings / Len FT / Count / Split），按内容给宽度，
            # 否则 Stretch 均分后「Len FT」会被截成「ngth F」这种半截字
            _rh = self.recog_rack_table.horizontalHeader()
            _rh.setSectionResizeMode(QHeaderView.ResizeToContents)
            _rh.setMinimumSectionSize(34)
            _rh.setStretchLastSection(False)
            _rh.setDefaultAlignment(Qt.AlignCenter)
        except Exception:
            pass
        self.recog_rack_table.cellClicked.connect(self.on_recog_rack_row)
        nv.addWidget(self.recog_rack_table)
        hb = QHBoxLayout()
        b = self._reg(QPushButton(), "应用到支架页")
        self._reg_tip(b, "把这张表写进「支架」页明细行，并给整册支架标上串数")
        b.clicked.connect(self.on_apply_recog_racks)
        hb.addWidget(b)
        hb.addStretch(1)
        nv.addLayout(hb)
        hb2 = QHBoxLayout()
        b = self._reg(QPushButton(), "重算分档")
        self._reg_tip(b, "按当前识别到的支架框重新统计「支架长度分档」（改过框 / 删过框之后马上想看新分档就点）")
        b.clicked.connect(self.on_recog_regroup_now)
        hb2.addWidget(b)
        b = self._reg(QPushButton(), "重认编号")
        self._reg_tip(b, "按 PDF 文字层重新读这一页的 LBD 编号（挪过 / 加过 LBD 框之后用；读不到时保留原来的名字）")
        b.clicked.connect(self.on_recog_relabel)
        hb2.addWidget(b)
        hb2.addStretch(1)
        nv.addLayout(hb2)
        self.recog_names = None
        if FEATURE_RECOG_PROJECT_TREE:
            nl = self._reg(QLabel(), "项目树")
            nl.setObjectName("Hint")
            self._reg_tip(nl, "LBD → ROW 列 → 每根支架；双击支架改串数，双击 LBD 改名")
            self._shrinkable(nl, 90)
            nv.addWidget(nl)
            # 项目树：一级 = LBD 编号（可改名），展开 = 这个 LBD 里各列的串数
            self.recog_names = QTreeWidget()
            self.recog_names.setObjectName("RecogTree")
            self.recog_names.setColumnCount(2)        # 第 2 列：这个 LBD 有几列
            self.recog_names.setHeaderHidden(True)
            self.recog_names.setIndentation(11)
            self.recog_names.setExpandsOnDoubleClick(False)   # 双击是改名，别顺手折叠
            self.recog_names.setMinimumWidth(150)      # 窄窗口下先压窄，不撑页面
            self.recog_names.setMaximumWidth(340)      # 上面那张表放右栏，给宽一点
            try:
                self.recog_names.header().setStretchLastSection(False)
                self.recog_names.header().setSectionResizeMode(0, QHeaderView.Stretch)
                self.recog_names.header().setSectionResizeMode(1, QHeaderView.Fixed)
                self.recog_names.setColumnWidth(1, 46)
            except Exception:
                pass
            self.recog_names.itemClicked.connect(self.on_recog_name_clicked)
            self.recog_names.itemDoubleClicked.connect(self.on_recog_name_double)
            self.recog_names.itemChanged.connect(self.on_recog_name_edited)
            nv.addWidget(self.recog_names, 1)
        res.addLayout(nv)
        # 下半区只剩识别日志（「日志」按钮展开 / 收起）；支架长度那张表在右栏上面
        self.recog_view = QPlainTextEdit()
        self.recog_view.setObjectName("Log")
        self.recog_view.setReadOnly(True)
        self.recog_view.setVisible(False)     # 日志不上界面（仍写到 %TEMP%\vcad_recog_log.txt）
        main_w = QWidget()
        main_w.setLayout(res)
        outer.addWidget(main_w, 1)
        # 「← 上一步 / 下一步 →」放到底部那一行，和「暂停 / 停止 / 执行」并排（见 _build_window）
        # 外面套一层滚动区：只允许上下滚，横向滚动条一律不放（窗口窄也不会左右滑）
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sc.setWidget(page)
        return sc

    def on_recognize(self):
        """点「开始识别」：后台起线程跑（不卡界面）。整本识别，挑页交给下面的「过滤」。"""
        self._recog_sync_inputs(to_cfg=True)
        cfg = self.cfg()
        pdf = (cfg.get("pdf") or "").strip()
        self._recog_write("=== 点了「开始识别」：pdf=%s（整本）running=%s"
                          % (pdf, getattr(self, "_recog_running", False)))
        if not pdf or not os.path.exists(pdf):
            self.log_msg("先选 PDF 文件（「文件与输出」页）")
            self.recog_view.appendPlainText("先选 PDF 文件。")
            return
        if getattr(self, "_recog_running", False):
            self._recog_write("上一轮还在跑（running=True），这次点击忽略")
            return
        self._recog_running = True
        self._recog_t0 = time.time()      # 进度条上「已用 / 剩余」的起点
        self.recog_btn.setEnabled(False)
        self.recog_btn.setText("识别中…")
        self.recog_view.clear()
        self._recog_t0 = time.time()
        self.recog_bar.setMaximum(0)
        self.recog_status.setText("准备中…")
        threading.Thread(target=self._recog_worker,
                         args=(cfg, ""),          # 空 = 全部页
                         daemon=True).start()

    def _recog_write(self, msg):
        """识别过程的落盘日志（%TEMP%\\vcad_recog_log.txt）—— 卡住时靠它定位。

        可能在后台线程里被调，所以只写文件 + 发信号，界面更新交给主线程。
        """
        line = "%s  %s" % (time.strftime("%H:%M:%S"), msg)
        try:
            p = os.path.join(tempfile.gettempdir(), "vcad_recog_log.txt")
            with open(p, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
        self.bus.recog_log.emit(msg)

    def _recog_worker(self, cfg, pages_spec):
        import traceback
        try:
            self._recog_worker_inner(cfg, pages_spec)
        except BaseException:
            self._recog_write("识别线程异常：\n" + traceback.format_exc())
            self.bus.recog_done.emit({"ok": False})

    def _recog_worker_inner(self, cfg, pages_spec):
        import traceback
        self._recog_write("线程起来了，开始导入识别模块…")
        try:
            import detect as _d
        except Exception as e:
            self._recog_write("识别模块用不了：%s（打包版应自带 onnxruntime / pypdfium2）" % e)
            self.bus.recog_done.emit({"ok": False})
            return
        pdf = (cfg.get("pdf") or "").strip()
        try:
            self._recog_write("识别模块 OK（模型：%s）" % _d.model_path())
        except Exception:
            pass
        try:
            sheets = read_xlsx_lbd_labels(cfg.get("xlsx") or "")
        except Exception:
            sheets = {}
        self._recog_write("标签文件分表数：%d" % len(sheets))
        try:
            total = _d.pdf_page_count(pdf)
            pages = _d.parse_pages(pages_spec, total)
            self._recog_write("PDF %d 页，%s" % (total, "识别全部" if not pages
                                              else "识别 %d 页" % len(pages)))
            self._recog_write("开始识别（第一页要先建模型会话 / 渲染，稍等）…")

            def _prog(n, alln, pg):
                self.bus.recog_prog.emit(n, alln, "第 %s 页" % pg)
                self._recog_write("第 %s 页识别完（%d/%d）" % (pg, n, alln))

            doc, sm = _d.detect_and_name(
                pdf, pages=pages, sheets=sheets, sheet_names=list(sheets),
                progress=_prog, log=lambda m: self.bus.recog_log.emit(m))
        except Exception as e:
            self._recog_write("识别失败：%s\n%s" % (e, traceback.format_exc()))
            self.bus.recog_done.emit({"ok": False})
            return
        self._recog_write("识别跑完，写 JSON…")
        out = os.path.join(tempfile.gettempdir(), "vcad_recognize.json")
        try:
            with open(out, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False)
        except Exception as e:
            self._recog_write("写识别结果失败：%s" % e)
            self.bus.recog_done.emit({"ok": False})
            return
        self._recog_write("JSON 写好：%s" % out)
        self.bus.recog_done.emit({"ok": True, "path": out, "summary": sm, "doc": doc})

    def on_recog_prog(self, done, total, text):
        if not hasattr(self, "recog_bar"):
            return
        self.recog_bar.setMaximum(max(1, total))
        self.recog_bar.setValue(done)
        pct = int(round(done * 100.0 / max(1, total)))
        # 时间进度：已用 + 按当前速度估的剩余（至少跑完一页才估，不然会乱跳）
        extra = ""
        t0 = getattr(self, "_recog_t0", 0.0) or 0.0
        if t0:
            el = time.time() - t0
            extra = "　已用 %s" % self._fmt_mmss(el)
            if done >= 1 and total > done:
                extra += " · 剩约 %s" % self._fmt_mmss(el * (total - done) / float(done))
        if hasattr(self, "recog_prog_text"):
            _l = self.recog_prog_text
            _l.setText("%d%%（%d/%d）%s" % (pct, done, total,
                                            extra.replace("　", " · ").strip(" ·")))
            _l.setToolTip("共 %d 页" % total)
        self.recog_status.setText("%s（%d/%d，%d%%）%s" % (text, done, total, pct, extra))

    @staticmethod
    def _fmt_mmss(sec):
        try:
            sec = int(max(0, sec))
        except Exception:
            return "?"
        if sec >= 3600:
            return "%d:%02d:%02d" % (sec // 3600, (sec % 3600) // 60, sec % 60)
        return "%d:%02d" % (sec // 60, sec % 60)

    def on_recog_log(self, msg):
        if hasattr(self, "recog_view"):
            self.recog_view.appendPlainText(msg)
            self.recog_view.verticalScrollBar().setValue(
                self.recog_view.verticalScrollBar().maximum())
        if hasattr(self, "recog_status"):
            self.recog_status.setText(msg[:70])
        self.log_msg(msg)

    def on_recog_done(self, info):
        info = info or {}
        self._recog_running = False
        if hasattr(self, "recog_btn"):
            self.recog_btn.setEnabled(True)
            self.recog_btn.setText("开始识别")
        if not info.get("ok"):
            if hasattr(self, "recog_status"):
                self.recog_status.setText("识别失败（看下面日志）")
            return
        path = info.get("path") or ""
        self.set_text("jsonPath", path)
        sm = info.get("summary") or {}
        st = sm.get("stat") or {}
        self.on_recog_log("识别完成：%d 页；LBD 区 %d 个（配到编号 %d、按标签表推 %d、没读到 %d），"
                          "编号位置 %d 个"
                          % (st.get("pages", 0),
                             st.get("named", 0) + st.get("auto", 0) + st.get("missed", 0),
                             st.get("named", 0), st.get("auto", 0),
                             st.get("missed", 0), st.get("pos", 0)))
        if sm.get("note"):
            self.on_recog_log(sm["note"])
            self.on_recog_log("→ 到「支架」页把每档的串数填上（例如 9:227.3, 13:329），"
                              "或直接在明细行填「长度FT + 串数」")
        self.on_recog_log("识别结果已填进「识别结果 JSON文件」：%s" % path)
        self._recog_doc = info.get("doc") or None
        self._recog_tmp_path = path
        self._recog_dirty = False
        self._fill_recog_table()
        self._fill_rack_table_from_summary(sm.get("groups") or [])
        self._recog_groups = sm.get("groups") or []
        self._recog_refresh_names()
        if hasattr(self, "recog_export_btn"):
            self.recog_export_btn.setEnabled(bool(self._recog_doc))
        self.auto_fill_rack_types_async(self.cfg(), announce=True)
        # 识别完顺手检查一遍：有没编号的 LBD / 没落档的支架等问题就弹出来反馈（没问题不打扰）
        QTimer.singleShot(900, self.on_recog_check)

    # ---------- 结果表格 / 预览 ----------
    def _recog_pages_of_doc(self):
        doc = getattr(self, "_recog_doc", None) or {}
        dets = {p.get("page_number"): (p.get("data") or {}).get("detections") or []
                for p in doc.get("yolo_tracker_detection_results") or []}
        names = {p.get("page_number"): (p.get("data") or [])
                 for p in doc.get("ocr_node_name_results") or []}
        size = {p.get("page_number"): (p.get("width"), p.get("height"))
                for p in (doc.get("input_data") or {}).get("pages") or []}
        out = []
        for pg in sorted(dets):
            n_node = sum(1 for d in dets[pg] if (d.get("label") or "") == "Node")
            n_trk = sum(1 for d in dets[pg] if (d.get("label") or "") == "Tracker")
            n_box = sum(1 for d in dets[pg] if (d.get("label") or "") == "Box")
            recs = names.get(pg) or []
            n_named = sum(1 for r in recs if (r.get("final_node_name") or "").strip())
            n_pos = sum(1 for r in recs if r.get("label_pos"))
            w, h = size.get(pg, (0, 0))
            out.append((pg, n_node, n_trk, n_box, n_named, n_pos, w, h))
        return out

    def _fill_recog_table(self, select_page=None, reload_preview=True):
        if not hasattr(self, "recog_table"):
            return
        rows = self._recog_pages_of_doc()
        self.recog_table.setRowCount(len(rows))
        for i, (pg, nn, nt, nb, n_named, n_pos, _w, _h) in enumerate(rows):
            # 左表只留三列：页码 / 识别到的 LBD 数 / 配到编号的数
            for j, val in enumerate((pg, nn, n_named)):
                _it = QTableWidgetItem(str(val))
                _it.setTextAlignment(Qt.AlignCenter)
                self.recog_table.setItem(i, j, _it)
        # 列宽由表头的 Stretch 管（三列平分），不再按内容撑宽 —— 撑宽就会顶出横向滚动
        if rows and reload_preview:
            pages = [r[0] for r in rows]
            self._recog_preview_page(select_page if select_page in pages else rows[0][0])

    def on_recog_page_changed(self, *_a):
        """左边表格换行 -> 画布换页（「预览」下拉已删，表格就是唯一的页列表）。"""
        pg = None
        if hasattr(self, "recog_table"):
            sel = self.recog_table.selectionModel().selectedRows()
            if sel:
                try:
                    pg = int(self.recog_table.item(sel[0].row(), 0).text())
                except Exception:
                    pass
        if pg:
            self._recog_preview_page(pg)

    def _recog_preview_page(self, pg):
        """把这一页载进画布（可缩放 / 可编辑；蓝=LBD 区 / 红=支架 / 橙=编号位置）。"""
        doc = getattr(self, "_recog_doc", None)
        pdf = (self.get_text("pdf") or "").strip()
        if not doc or not pdf or not os.path.exists(pdf) or not hasattr(self, "recog_canvas"):
            return
        try:
            self.recog_canvas._pdf = pdf
            # 200dpi 渲染、允许更大像素：缩小看整页也行，放大看框里的字也清楚
            self.recog_canvas.load(doc, pg, pdf, dpi=200, max_w=2600)
            # 锁定状态记在识别结果的 raw.lbd_locked 里（和标注软件一样，重开还在）
            dets_pg = ((next((p for p in doc.get("yolo_tracker_detection_results") or []
                              if p.get("page_number") == pg), None) or {}).get("data") or {}
                       ).get("detections") or []
            nodes_pg = [x for x in dets_pg if (x.get("label") or "") == "Node"]
            lock = bool(nodes_pg) and all(
                (x.get("raw") or {}).get("lbd_locked") for x in nodes_pg)
            self.recog_canvas.set_lbd_locked(lock, persist=False)
            self._sync_lock_btn()
            self._recog_update_page_info(pg)
            self._recog_refresh_names()      # 右栏名字跟着这页一起换
        except Exception as e:
            self.recog_preview_info.setText("这一页画不出来：%s" % e)
            self._recog_write("画布载入第 %s 页失败：%s" % (pg, e))

    def _recog_mark_dirty_light(self):
        """拖框 / 拖控制点的过程中走这条：只标记改动，不重建表格、不重算统计。

        （每动一下鼠标就重建左边那张表 + 遍历整册框重算统计，是最卡的一环；
          松手时 on_changed 会再走一次完整刷新。）
        """
        self._recog_dirty = True
        if hasattr(self, "recog_save_btn"):
            self.recog_save_btn.setEnabled(True)

    def _recog_update_page_info(self, pg=None):
        if pg is None:
            pg = getattr(self, "_recog_page", None)
        self._recog_page = pg
        all_rows = self._recog_pages_of_doc()
        pages = [r[0] for r in all_rows]
        if hasattr(self, "recog_page_label"):
            if pg is not None and pg in pages:
                self.recog_page_label.setText("第 %s 页 / 共 %d 页（画布当前页）"
                                              % (pg, len(pages)))
            else:
                self.recog_page_label.setText("")
        rows = [r for r in all_rows if r[0] == pg]
        if rows and hasattr(self, "recog_preview_info"):
            _pg, nn, nt, nb, n_named, n_pos, _w, _h = rows[0]
            self.recog_preview_info.setText(
                "本页：LBD %d · 支架 %d · 编号 %d" % (nn, nt, n_named))
        self._update_issue_bar(pg)

    def _update_issue_bar(self, pg=None):
        """画布上面那行：显示整册有几页有问题；点一下列出有问题的页、点页直接跳过去。"""
        bar = getattr(self, "recog_issue_bar", None)
        if bar is None:
            return
        pg = pg if pg is not None else getattr(self, "_recog_page", None)
        if pg is None or not getattr(self, "_recog_doc", None):
            bar.setText(T("检查问题"))
            bar.setToolTip("")
            bar.setStyleSheet("")
            return
        try:
            items = self._recog_issue_items()
        except Exception:
            items = []
        cur = [t for p, t in items if p == pg]
        if items:
            bar.setText(T("⚠ %d 页有问题（点一下看哪页）", len(items)))
            bar.setToolTip((cur[0] if cur else T("这一页没问题")) + "\n" +
                           T("（点这里看全部页面的检查结果）"))
            bar.setStyleSheet("color:#F5A800; font-weight:bold;")
        else:
            bar.setText(T("本页问题：没发现"))
            bar.setToolTip(T("这一页没发现明显问题（点这里看全部页面的检查结果）"))
            bar.setStyleSheet("")

    def _on_issue_bar_clicked(self):
        """点「检查问题」：列出所有有问题的页，双击 / 点按钮跳到那一页。"""
        try:
            items = self._recog_issue_items()
        except Exception:
            items = []
        if not getattr(self, "_recog_doc", None):
            QMessageBox.information(self, T("识别结果检查"), T("还没识别，先跑一次「开始识别」。"))
            return
        if not items:
            QMessageBox.information(self, T("识别结果检查"), T("没发现明显问题。"))
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(T("识别结果检查（%d 页有问题）", len(items)))
        dlg.resize(820, 540)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(8)
        v.addWidget(QLabel(T("共 %d 页有问题，双击一条跳到那一页：", len(items))))
        lw = QListWidget()
        lw.setWordWrap(True)
        for _pg, txt in items:
            it = QListWidgetItem(txt)
            it.setData(Qt.UserRole, _pg)
            lw.addItem(it)
        v.addWidget(lw, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        go = QPushButton(T("跳到这一页"))
        close = QPushButton(T("关闭"))
        row.addWidget(go)
        row.addWidget(close)
        v.addLayout(row)
        picked = {"pg": None}

        def _go(*_a):
            it = lw.currentItem()
            if it is not None:
                picked["pg"] = it.data(Qt.UserRole)
                dlg.accept()

        go.clicked.connect(_go)
        lw.itemDoubleClicked.connect(_go)
        close.clicked.connect(dlg.reject)
        dlg.exec()
        if picked["pg"] is not None:
            self._goto_recog_page(picked["pg"])

    def _goto_recog_page(self, pg):
        """跳到指定页（问题条里点的那一页）。"""
        try:
            for i in range(self.recog_table.rowCount()):
                it = self.recog_table.item(i, 0)
                if it is not None and str(it.text()).strip() == str(pg):
                    self.recog_table.selectRow(i)
                    self.recog_table.scrollToItem(it)
                    break
        except Exception:
            pass
        try:
            self._recog_preview_page(int(pg))
        except Exception:
            pass

    # ---------- 画布上的编辑动作 ----------
    def _recog_mark_dirty(self):
        self._recog_dirty = True
        if hasattr(self, "recog_save_btn"):
            self.recog_save_btn.setEnabled(True)
        # 只刷新数字，**不重载画布** —— 否则拖动一次就丢选择、缩放被重置
        self._fill_recog_table(select_page=getattr(self, "_recog_page", None),
                               reload_preview=False)
        self._recog_update_page_info()

    def on_recog_box_selected(self, box):
        info = self.recog_canvas.selected_info() if hasattr(self, "recog_canvas") else None
        if not info:
            return
        # 项目树跟着选中项走：选中 LBD 就高亮它那行，选中支架就高亮它那根
        try:
            w = getattr(self, "recog_names", None)
            if w is not None and box is not None:
                hit = None
                for i in range(w.topLevelItemCount()):
                    top = w.topLevelItem(i)
                    if top.data(0, Qt.UserRole) == box.det_index:
                        hit = top
                        break
                    for j in range(top.childCount()):
                        row = top.child(j)
                        rd = row.data(0, Qt.UserRole) or {}
                        if not isinstance(rd, dict):
                            continue
                        for k in range(row.childCount()):        # 第三层：每根支架
                            ch = row.child(k)
                            d = ch.data(0, Qt.UserRole) or {}
                            if isinstance(d, dict) and d.get("rack") == box.det_index:
                                top.setExpanded(True)
                                row.setExpanded(True)
                                hit = ch
                                break
                        if hit is not None:
                            break
                        if box.det_index in (rd.get("racks") or []):
                            top.setExpanded(True)
                            hit = row
                            break
                    if hit is not None:
                        break
                if hit is not None and w.currentItem() is not hit:
                    w.blockSignals(True)
                    w.setCurrentItem(hit)
                    w.blockSignals(False)
        except Exception:
            pass
        if info["kind"] == "Node":
            self.recog_name_edit.setText(info.get("name") or "")
            self.recog_name_edit.setEnabled(True)
        else:
            self.recog_name_edit.setText("")
            self.recog_name_edit.setEnabled(False)
        cf = info.get("conf")
        self.recog_preview_info.setText("%s　置信度 %s　（改完记得点「保存修改」）"
                                        % (info["kind"], ("%.3f" % cf) if cf else "—"))

    def on_recog_zoom_in(self):
        if hasattr(self, "recog_canvas"):
            self.recog_canvas.zoom(1.25)

    def on_recog_zoom_out(self):
        if hasattr(self, "recog_canvas"):
            self.recog_canvas.zoom(1 / 1.25)

    def on_recog_fit(self):
        if hasattr(self, "recog_canvas"):
            self.recog_canvas.fit_width()

    def on_recog_fit_page(self):
        if hasattr(self, "recog_canvas"):
            self.recog_canvas.fit_page()

    def on_recog_delete(self):
        if not hasattr(self, "recog_canvas"):
            return
        n = self.recog_canvas.delete_selected()
        if not n:
            self._recog_write("先点一个框，再删")

    def on_recog_box_deleted(self, n):
        """画布上删掉框（按钮或 Delete 键）之后：结果一起同步刷新。"""
        if not n:
            return
        self._recog_sync_all("删掉了 %d 个框" % n)
        self._recog_write("记得点「保存修改」写回 JSON")

    def on_recog_rename(self):
        if not hasattr(self, "recog_canvas"):
            return
        name = self.recog_name_edit.text().strip()
        if self.recog_canvas.rename_selected(name):
            self._recog_write("编号改成：%s（记得「保存修改」）" % (name or "（空）"))
        else:
            self._recog_write("先选中一个 LBD 区（蓝框），再改名")

    def on_recog_renamed(self, det_index):
        """改编号之后：右栏名字栏跟着换（顺序也会按新编号重排，LBD-9 排在 LBD-10 前）。

        名字栏里双击直接改的时候不走这里（_recog_names_busy）：那种情况列表项本身
        已经是新名字，而且正在编辑信号的中间，不能把列表清空重建。
        """
        if getattr(self, "_recog_names_busy", False):
            return
        self._recog_refresh_names(select_index=det_index)

    def on_recog_undo(self):
        if hasattr(self, "recog_canvas") and self.recog_canvas.undo():
            self._recog_sync_all("撤销上一步")

    # ---------- 识别页的两个输入（PDF / 标签文件）----------
    def _recog_pick(self, key):
        filt = {"pdf": "PDF 文件 (*.pdf);;所有文件 (*.*)",
                "xlsx": "Excel (*.xlsx *.xls);;所有文件 (*.*)"}.get(key, "所有文件 (*.*)")
        title = "选 PDF 文件" if key == "pdf" else "选标签文件"
        path, _f = QFileDialog.getOpenFileName(self, title, "", filt)
        if not path:
            return
        self.set_text(key, path)
        self._recog_sync_inputs()

    def _recog_sync_inputs(self, to_cfg=False):
        """识别页上的 PDF 与「文件与输出」页共用一份数据。

        标签文件在识别这一步**不需要**：LBD 编号是从 PDF 文字层直接读出来的
        （读到的就是 INV01A01-LBD-04 这种整段编号），只有后续 CAD 生成布局取分表名时才用得上。

        识别页那个输入框只显示文件名（长路径显示不下也没意义），完整路径记在
        self._recog_pdf_full 里，回写时用它，别把界面上的短名字写回去。
        """
        if not hasattr(self, "recog_pdf_edit"):
            return
        if to_cfg:
            p = getattr(self, "_recog_pdf_full", "") or ""
            if p:
                self.set_text("pdf", p)
        else:
            p = self.get_text("pdf")
            self._recog_pdf_full = p
            self.recog_pdf_edit.setText(p)          # 数据载体（界面隐藏）
            self.recog_pdf_edit.setToolTip(p or "")
            if hasattr(self, "recog_pdf_state"):
                self.recog_pdf_state.setText(T("已选择") if p else T("未选择"))
                self.recog_pdf_state.setStyleSheet(
                    "color:%s;" % ("#6fbf73" if p else "#8a8f94"))
                self.recog_pdf_state.setToolTip(p or T("还没选 PDF，点右边「上传 PDF」"))

    def _on_section_shown(self, idx):
        """切到识别页时，把主参数页上的 PDF / 标签文件同步显示过来。"""
        try:
            names = [t for t, _k in SECTIONS]
            if 0 <= idx < len(names) and names[idx] == "识别":
                self._recog_sync_inputs()
            elif 0 <= idx < len(names) and names[idx] == "支架标签":
                # 支架类型：识别结果里有就自动读，没有就留空让用户在这页手填
                if not getattr(self, "rack_rows", None):
                    QTimer.singleShot(0, self.on_refresh_rack_types)
        except Exception:
            pass

    def _fill_rack_table_from_summary(self, groups):
        """把识别出来的支架长度分档填进小表格。

        已经有行的时候（删框 / 加框 / 过滤之后重算）按"长度最接近"把之前填的
        「串数 / 拆不拆」带过来，改完结果不用重填。
        """
        t = getattr(self, "recog_rack_table", None)
        if t is None:
            return
        # 表头跟着「实际跟哪套口径匹配」走：表里填的可能是像素、也可能是英尺，
        # 标题一直写「长度FT」很容易照着一个错单位填（支架页那张明细表同理）
        try:
            unit_px = self._match_unit_px()
            hdr = t.horizontalHeaderItem(1)
            if hdr is not None:
                hdr.setText(T("长度px") if unit_px else T("长度"))
        except Exception:
            pass
        old = []
        for i in range(t.rowCount()):
            try:
                old.append((float((t.item(i, 1).text() or "0").strip()),
                            (t.item(i, 0).text() if t.item(i, 0) else "").strip(),
                            (t.cellWidget(i, 3).text() if t.cellWidget(i, 3) else "")))
            except Exception:
                old.append((None, "", ""))
        t.setRowCount(len(groups))
        for i, g in enumerate(groups):
            L = float(g.get("length") or 0)
            keep_n, keep_s = "", ""
            best = None
            for oL, oN, oS in old:
                if oL is None:
                    continue
                d = abs(oL - L)
                if best is None or d < best[0]:
                    best = (d, oN, oS)
            if best is not None and best[0] <= max(1.0, 0.10 * max(L, 1.0)):
                keep_n, keep_s = best[1], best[2]
            for col, val in ((0, keep_n), (1, "%.1f" % L), (2, str(g.get("count") or 0))):
                _it = QTableWidgetItem(val)
                _it.setTextAlignment(Qt.AlignCenter)
                t.setItem(i, col, _it)
            sp = QLineEdit()
            sp.setPlaceholderText("0")
            sp.setToolTip(T("0 = 不拆；填 2 / 3 … 表示拆几行"))
            _m = re.search(r"\d+", str(keep_s or ""))
            sp.setText(_m.group(0) if _m else "")
            t.setCellWidget(i, 3, sp)
        try:
            t.resizeColumnsToContents()
        except Exception:
            pass

    def _recog_rack_all_filled(self):
        rows = self._recog_rack_rows()
        if not rows:
            return False
        return all((r[0] or "").strip() for r in rows)

    def _recog_sync_all(self, why=""):
        """识别结果被改动（删框 / 加框 / 粘贴 / 撤销 / 过滤）之后，下游一起刷新。

        刷新的东西：结果数字、支架长度分档表（保留已填串数）；
        如果已经「应用到支架页」过，支架页明细也按改后的结果重算。
        """
        if getattr(self, "_recog_syncing", False):      # 防重入：刷新过程里再触发一次就跳过
            return
        self._recog_syncing = True
        try:
            self._recog_mark_dirty()
            self._recog_refresh_names()
            if why:
                self._recog_write("%s：结果数字 / 支架长度分档已刷新" % why)
            # 整册重算分档 + 重新标串数 是「几千根支架」级别的活（1 秒上下），
            # 画框时先别同步跑 —— 最后一次改动之后 0.6 秒再算一次，不然画一个框卡一下
            self._recog_heavy_later()
        finally:
            self._recog_syncing = False

    def _recog_heavy_later(self):
        """把「重算分档 + 重新标串数」延到最后一次改动之后 0.6 秒做一次。"""
        t = getattr(self, "_heavy_timer", None)
        if t is None:
            t = self._heavy_timer = QTimer(self)
            t.setSingleShot(True)
            t.timeout.connect(self._recog_heavy_now)
        t.start(600)

    def _recog_heavy_now(self):
        """延迟到的那次：重算支架长度分档，并把串数按新结果重新标一遍。"""
        try:
            self._recog_regroup()
        except Exception as e:
            self._recog_write("重算支架长度分档失败：%s" % e)
        try:
            if self._rack_types_current() and self._recog_rack_all_filled():
                if self.on_apply_recog_racks():
                    self._recog_write("支架页明细已按改后的结果重新应用")
        except Exception as e:
            self._recog_write("支架页同步失败：%s" % e)

    def _recog_rack_rows(self):
        """读识别页那张小表 -> [(串数, 长度FT, 拆不拆, 数量)]。"""
        out = []
        t = getattr(self, "recog_rack_table", None)
        if t is None:
            return out
        for i in range(t.rowCount()):
            strings = (t.item(i, 0).text().strip() if t.item(i, 0) else "")
            length = (t.item(i, 1).text().strip() if t.item(i, 1) else "")
            count = (t.item(i, 2).text().strip() if t.item(i, 2) else "")
            cb = t.cellWidget(i, 3)
            split = cb.text().strip() if cb is not None else ""
            out.append((strings, length, split, count))
        return out

    def on_recog_filter_pages(self):
        """只保留指定页范围的识别结果 —— 封面 / 说明 / 清单页这种不该画的页丢掉。

        （为什么需要：主程序默认整本都识别，像 HIGHLAND 第 21 页是清单页、能出 900 多个框，
          混进去以后 CAD 侧按「第几张底图」重编号就整体错位。）
        """
        doc = getattr(self, "_recog_doc", None)
        if not doc:
            self._recog_write("还没识别，先跑一次「开始识别」")
            return
        try:
            import detect as _d
            total = max((p.get("page_number") or 0)
                        for p in (doc.get("input_data") or {}).get("pages") or []) or 0
            pages = _d.parse_pages((self.recog_keep_edit.text() or "").strip(), total)
        except Exception as e:
            self._recog_write("页范围读不出来：%s" % e)
            return
        if not pages:
            self._recog_write("先在「只保留」里写页范围，例如 23-108")
            return
        keep = set(pages)
        before = len(doc.get("yolo_tracker_detection_results") or [])
        doc["yolo_tracker_detection_results"] = [
            x for x in (doc.get("yolo_tracker_detection_results") or [])
            if x.get("page_number") in keep]
        if doc.get("ocr_node_name_results"):
            doc["ocr_node_name_results"] = [
                x for x in doc["ocr_node_name_results"] if x.get("page_number") in keep]
        if (doc.get("input_data") or {}).get("pages"):
            doc["input_data"]["pages"] = [
                x for x in doc["input_data"]["pages"] if x.get("page_number") in keep]
        after = len(doc["yolo_tracker_detection_results"])
        self._recog_mark_dirty()
        self._fill_recog_table()
        # 过滤之后：支架长度分档 / 画布 一起刷新，别留着过滤前的旧数
        self._recog_regroup()
        self._recog_refresh_names()
        pg = getattr(self, "_recog_page", None)
        rows = [r for r in self._recog_pages_of_doc() if r[0] == pg]
        if rows and hasattr(self, "recog_canvas"):
            self._recog_preview_page(pg)
        self._recog_write("按页范围过滤：%d 个支架框 -> %d 个（只留 %s）"
                          % (before, after, self.recog_keep_edit.text().strip()))

    def _recog_regroup(self):
        """按当前（可能刚删过框 / 过滤过的）结果重算支架长度分档。

        只用识别结果里已经存好的长度（每根支架的 raw.len_ft / len_px，识别时就写好了），
        **不再去读 PDF 文字层** —— 大图纸集上 pypdf 每题一页要好几秒，删一个框就卡死。
        """
        doc = getattr(self, "_recog_doc", None)
        if not doc:
            return
        try:
            groups = self._groups_from_doc(doc)
            self._recog_groups = groups
            self._fill_rack_table_from_summary(groups)
            self._recog_write("支架长度分档已按过滤后的结果重算：%d 档、%d 根支架"
                              % (len(groups), sum(g.get("count") or 0 for g in groups)))
        except Exception as e:
            self._recog_write("重算支架长度分档失败：%s" % e)

    @staticmethod
    def _groups_from_doc(doc, tol=0.10):
        """从识别结果直接聚类支架长度（就用框长 / 页面像素；老结果没有像素长度再用英寸）。

        返回 [{"length", "unit", "count", "pages"}]，和 detect.rack_length_groups 同一套
        判据（长度差 ≤10% 算同一档），但不碰 PDF，纯内存里算 —— 删框 / 过滤后刷新不卡。
        """
        ft, px, box = [], [], []
        for p in doc.get("yolo_tracker_detection_results") or []:
            pg = p.get("page_number")
            for d in (p.get("data") or {}).get("detections") or []:
                if (d.get("label") or "") != "Tracker":
                    continue
                raw = d.get("raw") or {}
                if raw.get("len_px") is not None:
                    px.append((float(raw["len_px"]), pg))
                elif raw.get("len_ft") is not None:
                    ft.append((float(raw["len_ft"]), pg))
                else:
                    b = d.get("bbox") or {}
                    try:
                        box.append((max(float(b.get("x2", 0)) - float(b.get("x1", 0)),
                                        float(b.get("y2", 0)) - float(b.get("y1", 0))), pg))
                    except Exception:
                        pass
        if px:
            items, unit = px, "像素"
        elif ft:
            items, unit = ft, "英尺"
        else:
            items, unit = box, "框长"
        if not items:
            return []
        items.sort(key=lambda t: t[0])
        groups = []
        for L, pg in items:
            if groups:
                mean = sum(x[0] for x in groups[-1]) / len(groups[-1])
                if mean > 0 and abs(L - mean) <= tol * mean:
                    groups[-1].append((L, pg))
                    continue
            groups.append([(L, pg)])
        out = []
        for g in groups:
            ls = sorted(x[0] for x in g)
            pages = {}
            for _L, pg in g:
                pages[pg] = pages.get(pg, 0) + 1
            out.append({"length": ls[len(ls) // 2], "unit": unit,
                        "count": len(g), "pages": pages})
        return out

    def on_apply_recog_racks(self):
        """把识别页的支架类型表写进「支架」页明细行，并给每根支架标上串数（raw.strings）。"""
        rows = self._recog_rack_rows()
        types, len_pref, split_pref, missing = [], {}, {}, []
        pairs = []                       # [(长度, 串数)] 给支架打标用
        for strings, length, split, count in rows:
            if not strings.strip():
                missing.append(length or "?")
                continue
            try:
                sv = int(float(strings))
                lv = float(length)
            except Exception:
                missing.append(strings or length or "?")
                continue
            try:
                cv = int(float(count))
            except Exception:
                cv = None
            types.append({"strings": sv, "length_ft": lv, "code": None,
                          "total_count": cv, "panel_label": None, "source": "recog"})
            len_pref[str(sv)] = "%g" % lv
            split_pref[str(sv)] = split
            pairs.append((lv, sv))
        if missing:
            self._recog_write("这几档还没填（串数/长度）：%s —— 填上再应用"
                              % "、".join(str(m) for m in missing[:6]))
            return False
        if not types:
            self._recog_write("这张表是空的：先在「串数」里填每档多少串")
            return False
        # 给每根支架标串数：按长度找最近的一档（差 ≤10%）
        doc = getattr(self, "_recog_doc", None) or {}
        # 口径（像素 / 英尺）由 _match_unit_px() 定：表里填的跟识别结果里存的可能不一致
        _g = getattr(self, "_recog_groups", None) or []
        unit_px = self._match_unit_px()
        if unit_px != (bool(_g) and (_g[0].get("unit") == "像素")):
            self._recog_write("「支架类型」表里的长度按%s口径匹配（和识别结果的另一套口径对不上）"
                              % ("像素" if unit_px else "英尺"))

        def _tag(use_px):
            """按给的口径扫一遍整册。返回 (标上几根, {档: 根数}, 几根没长度)。"""
            n, hits, nolen = 0, {}, 0
            for page in doc.get("yolo_tracker_detection_results") or []:
                _pg = page.get("page_number")
                for d in (page.get("data") or {}).get("detections") or []:
                    if (d.get("label") or "") != "Tracker":
                        continue
                    if (d.get("raw") or {}).get("strings_manual"):
                        continue            # 树里手填过串数的：别被长度匹配覆盖掉
                    v = self._rack_len_of(d, _pg, use_px)
                    if v is None:
                        nolen += 1
                        continue
                    best, bd = None, None
                    for lv, sv in pairs:
                        dlt = abs(float(v) - lv)
                        if bd is None or dlt < bd:
                            best, bd = sv, dlt
                    if best is None or bd is None or bd > 0.10 * max(1.0, float(v)):
                        continue
                    raw = dict(d.get("raw") or {})
                    raw["strings"] = best
                    if use_px and raw.get("len_px") is None:
                        raw["len_px"] = round(float(v), 2)      # 框长现算出来的，存一份最保险
                    d["raw"] = raw
                    n += 1
                    hits[best] = hits.get(best, 0) + 1
            return n, hits, nolen

        tagged, hit, nolen = _tag(unit_px)
        self._rack_types = types
        self._rack_len_pref = len_pref
        self._rack_split_pref = split_pref
        try:
            self.refresh_rack_rows(self._rack_types, stash=False)
        except Exception as e:
            self._recog_write("刷新「支架」页明细行失败：%s" % e)
            return False
        _u = "px" if unit_px else "FT"       # 表里那两档到底是像素还是英尺，日志里写清楚
        self._recog_write("支架类型已应用到「支架」页：%s；给 %d 根支架标了串数"
                          % ("；".join("%s串=%g%s/%s" % (t["strings"], t["length_ft"], _u,
                                                        split_pref[str(t["strings"])])
                                      for t in types), tagged)
                          + ("（%s）" % "、".join("%s串 %d 根" % (k, n)
                                                for k, n in sorted(hit.items()))
                             if hit else "")
                          + ("；%d 根没读到长度（这些页没有比例尺）" % nolen if nolen else ""))
        self._recog_refresh_names()     # 项目树里把每个 LBD 区里的支架号显示出来
        return True

    def on_recog_rack_row(self, row, _col=0):
        """点支架类型表里的某一档 -> 画布跳到那档支架的实际位置；再点一次看下一个。"""
        rows = self._recog_rack_rows()
        if not (0 <= row < len(rows)):
            return
        strings, length, _split, _count = rows[row]
        try:
            target = float(length)
        except Exception:
            self._recog_write("这一行的长度读不出来（%r）" % length)
            return
        doc = getattr(self, "_recog_doc", None) or {}
        # 口径跟「应用」/项目树共用同一个判断（表里的长度可能是像素、也可能是英尺）
        unit_px = self._match_unit_px()
        _u = "像素" if unit_px else "英尺"
        matches = []
        near, near_d = None, None          # 找不到时用：整册最接近的那根，告诉用户差多少
        for page in doc.get("yolo_tracker_detection_results") or []:
            pg = page.get("page_number")
            for i, d in enumerate((page.get("data") or {}).get("detections") or []):
                if (d.get("label") or "") != "Tracker":
                    continue
                v = self._rack_len_of(d, pg, unit_px)
                if v is None:
                    continue
                _dlt = abs(float(v) - target)
                if near_d is None or _dlt < near_d:
                    near, near_d = (pg, i, float(v)), _dlt
                if abs(float(v) - target) <= 0.10 * max(target, 1.0):
                    matches.append((pg, i))
        if not matches:
            if near is not None:
                self._recog_write(
                    "没找到长度 %.1f %s 的支架（%s 那一档）；整册最接近的是第 %s 页的 %.1f %s，差 %.1f%%"
                    % (target, _u, strings or "?", near[0], near[2], _u,
                       100.0 * near_d / max(target, 1.0)))
            else:
                self._recog_write("没找到长度 %.1f %s 的支架（%s 那一档）：整册没有可算长度的支架框"
                                  % (target, _u, strings or "?"))
            return
        k = (getattr(self, "_rack_jump_pos", {}) or {}).get(row, -1) + 1
        k %= len(matches)
        if not hasattr(self, "_rack_jump_pos"):
            self._rack_jump_pos = {}
        self._rack_jump_pos[row] = k
        pg, det_i = matches[k]
        # 切到那一页（左边表格也跟着选中），再选中/居中那个框
        self._recog_preview_page(pg)
        self._select_recog_table_page(pg)
        ok = self.recog_canvas.select_det(det_i)
        self._recog_write("跳到第 %s 页（第 %d/%d 个）：%s串 %.1fFT 的支架%s"
                          % (pg, k + 1, len(matches), strings or "?", target,
                             "" if ok else "（画布上没找到那个框）"))

    def on_recog_rack_step(self, d):
        """在本页里前 / 后跳一个支架（按位置顺序，循环），并把标号报出来。

        注意：**没有绑键** —— A/D 是翻页（和标注软件一致，用户指定）。
        支架前后跳目前还是靠点下面支架类型表那一行（再点一次看下一个）。
        要给它配键的话在这里接回去就行。
        """
        if not hasattr(self, "recog_canvas"):
            return
        pg = getattr(self, "_recog_page", None)
        doc = getattr(self, "_recog_doc", None) or {}
        trk = next((p for p in doc.get("yolo_tracker_detection_results") or []
                    if p.get("page_number") == pg), None)
        dets = ((trk or {}).get("data") or {}).get("detections") or []
        boxes = [i for i, x in enumerate(dets) if (x.get("label") or "") == "Tracker"]
        if not boxes:
            self.recog_preview_info.setText("第 %s 页没有支架框" % pg)
            self._recog_write("第 %s 页没有支架框可跳" % pg)
            return
        sel = self.recog_canvas.selected_box()
        if sel is not None and sel.det_index in boxes:
            cur = boxes.index(sel.det_index)
        else:
            cur = -1 if d > 0 else 0
        nxt = (cur + d) % len(boxes)
        di = boxes[nxt]
        ok = self.recog_canvas.select_det(di)
        x = dets[di] if 0 <= di < len(dets) else {}
        raw = (x or {}).get("raw") or {}
        ln, unit = raw.get("len_ft"), "FT"
        if ln is None:
            ln, unit = raw.get("len_px"), "px"
        tag = ("长度 %.1f%s" % (float(ln), unit)) if ln is not None else "长度未记录"
        if raw.get("strings"):
            tag += " · %s 串" % raw.get("strings")
        self.recog_preview_info.setText(
            "第 %s 页 支架 %d/%d：%s（A/D 前后跳）%s"
            % (pg, nxt + 1, len(boxes), tag, "" if ok else "（画布上没找到这个框）"))
        self._recog_write("A/D 跳支架：第 %s 页 第 %d/%d 个（%s）"
                          % (pg, nxt + 1, len(boxes), tag))

    # ---------- 名字栏 / 加框 / 键盘翻页（和标注软件对齐）----------
    def _recog_page_nodes(self, pg=None):
        """当前页的 LBD 区（Node 框）：[(det 下标, 名字)]。"""
        if pg is None:
            pg = getattr(self, "_recog_page", None)
        doc = getattr(self, "_recog_doc", None) or {}
        trk = next((p for p in doc.get("yolo_tracker_detection_results") or []
                    if p.get("page_number") == pg), None)
        ocr = next((p for p in doc.get("ocr_node_name_results") or []
                    if p.get("page_number") == pg), None)
        dets = ((trk or {}).get("data") or {}).get("detections") or []
        recs = (ocr or {}).get("data") or []
        out, k = [], 0
        for i, d in enumerate(dets):
            if (d.get("label") or "") != "Node":
                continue
            nm = (recs[k].get("final_node_name") or "").strip() if k < len(recs) else ""
            out.append((i, nm))
            k += 1
        return out

    def _scale_doc(self):
        """比例尺用的 PDF 句柄：打开一次反复用（一页开一次 134MB 的图集会慢死）。"""
        pdf = (self.get_text("pdf") or "").strip()
        if getattr(self, "_scale_doc_path", None) == pdf:
            return getattr(self, "_scale_doc_cache", None)
        old = getattr(self, "_scale_doc_cache", None)
        if old is not None:
            try:
                old.close()
            except Exception:
                pass
        doc = None
        if pdf and os.path.exists(pdf):
            try:
                import pypdfium2 as _pdfium
                doc = _pdfium.PdfDocument(pdf)
            except Exception:
                doc = None
        self._scale_doc_cache, self._scale_doc_path = doc, pdf
        return doc

    def _scale_map(self):
        """整册比例尺：({页: 1英寸=?英尺}, 最常见的那把)。

        识别时已经写进识别结果（page_scales / scale_dominant）就直接用；老结果没写
        就现读一遍图纸文字层（pdfium，一百多页 5 秒左右），结果缓存起来。
        读取口径和识别时「支架长度分档」完全一样：这页读不到就用整册最常见的那把
        —— 不然同一根支架在这两处算出来的长度不一样，串数当然对不上。
        """
        doc = getattr(self, "_recog_doc", None) or {}
        key = ((self.get_text("pdf") or "").strip(), id(doc))
        cache = getattr(self, "_recog_scalemap", None)
        if cache is not None and cache[0] == key:
            return cache[1], cache[2]
        sc, dom = {}, None
        for k, v in (doc.get("page_scales") or {}).items():
            try:
                sc[int(k)] = float(v)
            except Exception:
                pass
        if doc.get("scale_dominant"):
            try:
                dom = float(doc["scale_dominant"])
            except Exception:
                dom = None
        if not sc:                     # 老结果：现读一遍，按 (pdf, doc) 缓存
            try:
                import detect as _d
                import lbd_naming as _N
                docobj = self._scale_doc()
                if docobj is not None:
                    self._recog_write("读图纸比例尺（算支架长度用，只读这一次）…")
                    for p in doc.get("yolo_tracker_detection_results") or []:
                        pg = p.get("page_number")
                        try:
                            ts = _d.pdf_text_runs(docobj, pg)
                            v, _why = _N.read_page_scale(ts) if ts else (None, "")
                        except Exception:
                            v = None
                        if v:
                            sc[pg] = float(v)
            except Exception:
                pass
            if sc:
                cnt = {}
                for v in sc.values():
                    cnt[round(v, 3)] = cnt.get(round(v, 3), 0) + 1
                dom = max(cnt, key=lambda k: cnt[k])
        self._recog_scalemap = (key, sc, dom)
        return sc, dom

    def _rack_len_of(self, det, pg, unit_px):
        """一根支架的长度（按当前口径：英尺 / 像素）。

        识别结果里存了就用它；老结果没有（内置识别早先没写长度）就现算：
        框长 ÷ 渲染 dpi × 这页比例尺。不算的话「应用到支架页」一根都匹配不上
        （界面上就是「给 0 根支架标了串数」、右栏项目树全是 ?S+?X）。
        """
        raw = det.get("raw") or {}
        if not unit_px and raw.get("len_ft") is not None:
            return float(raw["len_ft"])
        if unit_px and raw.get("len_px") is not None:
            return float(raw["len_px"])
        b = det.get("bbox") or {}
        try:
            L = max(float(b["x2"]) - float(b["x1"]), float(b["y2"]) - float(b["y1"]))
        except Exception:
            return None
        if unit_px:
            return L
        sc_map, dom = self._scale_map()
        sc = sc_map.get(pg) or dom
        if not sc:
            return None
        dpi = float((getattr(self, "_recog_doc", None) or {}).get("render_dpi") or 0) or 150.0
        return (L / dpi) * sc

    def _recog_page_rack_groups(self, pg=None):
        """当前页：每个 LBD 区里各列的「串数」，给右栏项目树用。

        返回 {LBD 框的 det 下标: [{"text": "3S+3X", "dets": [支架框下标, ...],
                                 "tip": "这一列从上到下：3串 + 3串（2 个号）"}]}。

        一「列」= 同一个横向位置上、上下叠着的那些号：一根支架拆成 2/3 行时，
        它的几行也叠在同一列里。显示成 3S+3X —— S = 上面那个、X = 下面那个
        （一列三个就用 M 表示中间那个）；一列只有一个就只写数字（如 9）。
        （画到图上的还是 STR 号，这里只是把串数摆给你看。）

        串数优先用「应用到支架页」写进识别结果的那份；还没应用就按长度跟界面
        「支架类型」表里的「长度FT」对（±10%，和「应用到支架页」同一个算法），
        所以表里填好串数就能直接看到。
        """
        if _lr_assign_parent is None:
            return {}
        pg = pg if pg is not None else getattr(self, "_recog_page", None)
        doc = getattr(self, "_recog_doc", None) or {}
        trk = next((p for p in doc.get("yolo_tracker_detection_results") or []
                    if p.get("page_number") == pg), None)
        dets = ((trk or {}).get("data") or {}).get("detections") or []
        ocr = next((p for p in doc.get("ocr_node_name_results") or []
                    if p.get("page_number") == pg), None)
        recs = (ocr or {}).get("data") or []
        # 串数：识别结果里存了就用它，没有就按长度跟界面这张表对（和「应用」同一套）
        pairs = []
        for strings, length, _split, _count in (self._recog_rack_rows() or []):
            try:
                pairs.append((float(length), int(float(strings))))
            except Exception:
                continue
        # 口径跟「应用」共用同一个结论（表里填的和识别结果里的可能不是一套）
        unit_px = self._match_unit_px()
        nodes, typs, k = [], [], 0
        for i, d in enumerate(dets):
            b = d.get("bbox") or {}
            if not all(t in b for t in ("x1", "y1", "x2", "y2")):
                continue
            lab = (d.get("label") or "").strip().lower()
            if lab == "node":
                nm = ""
                if k < len(recs):
                    nm = (recs[k].get("final_node_name")
                          or recs[k].get("preliminary_node_name") or "").strip()
                nodes.append({"bbox": b, "det": i, "name": nm})
                k += 1
            elif lab in ("tracker", "typical"):
                typs.append({"bbox": b, "det": i, "obj": d})
        if not nodes or not typs:
            return {}
        try:
            cfg = self.cfg()
        except Exception:
            cfg = {}
        order = str((cfg or {}).get("strOrder", "2") or "2").strip() or "2"
        split_map = _lr_parse_split(rack_split_spec(cfg))
        groups = {}
        for t in typs:
            b = t["bbox"]
            p = _lr_assign_parent(b, nodes)
            if p is None:
                continue                    # 不在任何 LBD 区里的支架：本来就不编号
            sv = self._rack_strings_of(t["obj"], pg, pairs, unit_px)
            cx, cy = _lr_center(b)
            groups.setdefault(p["det"], []).append(
                (cx, cy, b, _lr_split_rows(split_map, sv), sv))
        if not groups:
            return {}
        det_of = {}
        for t in typs:
            det_of[id(t["bbox"])] = t["det"]
        out = {}
        for n in nodes:
            items = groups.get(n["det"])
            if not items:
                continue
            # 拆开的几行也要算进这一列（一根支架拆 2 行 = 同一列两个号）
            cells = _lr_expand_racks(items, order)
            widths = sorted(max(1.0, c[2]["x2"] - c[2]["x1"]) for c in cells)
            tol = max(1.0, widths[len(widths) // 2] * 0.5) if widths else 1.0
            bands = _lr_band([c[0] for c in cells], tol)
            cols = {}
            for c in cells:
                bi = min(range(len(bands)), key=lambda i: abs(bands[i] - c[0]))
                cols.setdefault(bi, []).append(c)
            rows = []
            for bi in sorted(cols):                 # 列：从左到右
                col = sorted(cols[bi], key=lambda c: c[1])     # 列内：上 → 下
                ncell = len(col)
                cells = []
                for i, c in enumerate(col):
                    # S=最上面那个、X=最下面那个（n=2 时正好一上一下），中间 M；只有一个就不带字母
                    pos = ("" if ncell == 1
                           else ("S" if i == 0 else ("X" if i == ncell - 1 else "M")))
                    cells.append({"pos": pos, "det": det_of.get(id(c[3])), "sv": c[5]})
                rows.append({"text": self._col_token([c[5] for c in col]),
                             "dets": [det_of.get(id(c[3])) for c in col],
                             "cells": cells,
                             "tip": "这一列从上到下：%s（%d 个号）"
                                    % (" + ".join(self._sv_text(c[5]) for c in col),
                                       ncell)})
            out[n["det"]] = rows
        return out

    @staticmethod
    def _sv_text(v):
        """串数的文字：3 -> "3串"；没配上就 "?串"。"""
        try:
            return "%g串" % float(v)
        except (TypeError, ValueError):
            return "?串"

    @staticmethod
    def _col_token(vals):
        """一列（上→下）的串数 -> 显示文字：3S+3X（S=上、X=下、中间 M）。"""
        def one(v):
            try:
                return "%g" % float(v)
            except (TypeError, ValueError):
                return "?"
        vals = list(vals or [])
        if not vals:
            return ""
        if len(vals) == 1:
            return one(vals[0])
        n = len(vals)
        return "+".join(one(v) + ("S" if i == 0 else ("X" if i == n - 1 else "M"))
                        for i, v in enumerate(vals))

    def _rack_strings_of(self, det, pg, pairs, unit_px):
        """这根支架的串数：识别结果里存了就用它，没有就按长度跟「支架类型」表里的档对。

        口径由 _match_unit_px() 定（表里填的可能是像素、也可能是英尺），不在这儿猜。
        """
        raw = det.get("raw") or {}
        sv = raw.get("strings")
        if sv not in (None, ""):
            return sv
        if not pairs:
            return None
        return self._rack_sv_by_table(det, pg, pairs, unit_px)

    def _rack_sv_by_table(self, det, pg, pairs, use_px):
        """按长度跟「支架类型」表里的档对一根支架（差 ≤10%）。配不上返回 None。"""
        v = self._rack_len_of(det, pg, use_px)
        if v is None:
            return None
        best, bd = None, None
        for lv, s in pairs:
            dlt = abs(float(v) - lv)
            if bd is None or dlt < bd:
                best, bd = s, dlt
        if best is not None and bd is not None and bd <= 0.10 * max(1.0, float(v)):
            return best
        return None

    def _match_unit_px(self):
        """长度口径：现在一律用框长（页面像素），不再读图纸比例尺换算英尺。

        （以前会两套口径都试；用户要求"就用本身长度"，这里固定像素，省掉读比例尺。）
        """
        return True

    def _match_unit_px_legacy(self):
        """老逻辑（像素/英尺自动判定）：留着备用，目前不用。"""
        doc = getattr(self, "_recog_doc", None) or {}
        _g = getattr(self, "_recog_groups", None) or []
        base = bool(_g) and (_g[0].get("unit") == "像素")
        pairs = []
        for strings, length, _split, _count in (self._recog_rack_rows() or []):
            try:
                pairs.append((float(length), int(float(strings))))
            except Exception:
                continue
        # 缓存键必须带上表里填的内容：识别完自动填分档表时「串数」还是空的，那时算出来的
        # 结论是错的；用户填好串数再点应用，不能拿这个过期结论（不然永远 0 根）
        key = (doc, tuple(pairs))
        cache = getattr(self, "_match_unit", None)
        if cache is not None and cache[0] == key:
            return cache[1]
        trks = [(p.get("page_number"), d)
                for p in doc.get("yolo_tracker_detection_results") or []
                for d in (p.get("data") or {}).get("detections") or []
                if (d.get("label") or "") == "Tracker"]
        out = base
        if pairs and trks:
            n0 = sum(1 for pg, d in trks
                     if self._rack_sv_by_table(d, pg, pairs, base) is not None)
            if n0 < max(1, len(trks) // 2):        # 配上不到一半：口径可能反了
                n1 = sum(1 for pg, d in trks
                         if self._rack_sv_by_table(d, pg, pairs, not base) is not None)
                if n1 > n0:
                    out = not base
        self._match_unit = (key, out)
        return out

    def _recog_refresh_names(self, select_index=None):
        """重建右栏项目树：一级 = LBD 编号，展开 = 它里面各列的串数。

        名单按 LBD 编号自然排序（LBD-2 排在 LBD-10 前面，不会按字符码排成 10 → 2），
        没编号的排在最后；画布里的框不受影响（点名字会定位到对应那个框，点串数那行
        会定位到这一列最上面那根支架）。串数见 _recog_page_rack_groups()。
        """
        w = getattr(self, "recog_names", None)
        if w is None:
            return
        rows = self._recog_page_nodes()
        try:
            rack_map = self._recog_page_rack_groups()
        except Exception:
            rack_map = {}

        def _key(it):
            nm = (it[1] or "").strip()
            parts = [int(t) if t.isdigit() else t.lower()
                     for t in re.split(r"(\d+)", nm)]
            return (1 if not nm else 0, parts, it[0])

        try:
            rows.sort(key=_key)
        except Exception:
            pass
        # 先记下当前展开 / 收起状态（LBD 行默认展开、ROW 行默认收起），重建后照原样恢复 ——
        # 不然每加/删一个框、每换一次页，全都又被展开
        pg = getattr(self, "_recog_page", None)
        # 树现在显示的可能是上一页（换页时 _recog_page 先变了），记状态要用树的那一页
        old_pg = getattr(self, "_recog_tree_page", pg)
        collapsed = set(getattr(self, "_recog_collapsed", None) or set())
        opened = set(getattr(self, "_recog_row_open", None) or set())
        for i in range(w.topLevelItemCount()):
            _it = w.topLevelItem(i)
            _k = (old_pg, _it.text(0))
            if _it.childCount():
                if _it.isExpanded():
                    collapsed.discard(_k)
                else:
                    collapsed.add(_k)
            for j in range(_it.childCount()):
                _row = _it.child(j)
                if not _row.childCount():
                    continue
                _kk = (old_pg, _it.text(0), j)
                if _row.isExpanded():
                    opened.add(_kk)
                else:
                    opened.discard(_kk)
        self._recog_collapsed = collapsed
        self._recog_row_open = opened
        w.blockSignals(True)
        w.clear()
        for det_i, nm in rows:
            it = QTreeWidgetItem([nm or "（没编号）", ""])
            it.setData(0, Qt.UserRole, det_i)
            it.setFlags(it.flags() | Qt.ItemIsEditable)
            kids = rack_map.get(det_i) or []
            row_items = []
            for k, r in enumerate(kids, 1):        # 从左往右，第几列写在前面
                sub = QTreeWidgetItem(["ROW%d · %s" % (k, r.get("text") or ""), ""])
                sub.setData(0, Qt.UserRole, {"racks": r.get("dets") or []})
                sub.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)   # 不给改名
                sub.setToolTip(0, "从左往右 ROW%d：%s；点箭头展开看每根支架"
                                  "（展开后双击支架改串数）" % (k, r.get("tip") or ""))
                for cell in r.get("cells") or []:              # 第三层：每根支架
                    pos = cell.get("pos") or ""
                    leaf = QTreeWidgetItem([("%s · %s" % (pos, self._sv_text(cell.get("sv")))
                                             if pos else self._sv_text(cell.get("sv"))), ""])
                    leaf.setData(0, Qt.UserRole, {"rack": cell.get("det")})
                    leaf.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    leaf.setToolTip(0, "双击改这根支架的串数")
                    sub.addChild(leaf)
                it.addChild(sub)
                row_items.append(sub)
            if kids:
                it.setText(1, "%d列" % len(kids))
                it.setToolTip(0, "这个 LBD 区有 %d 列（从左往右）：%s"
                                 % (len(kids), "、".join(x.get("text") or "" for x in kids)))
            w.addTopLevelItem(it)
            # 展开状态要在挂到树上之后再设（提前设会被 QTreeWidget 重置）
            it.setExpanded((pg, it.text(0)) not in collapsed)
            for j, row_it in enumerate(row_items):
                row_it.setExpanded((pg, it.text(0), j) in opened)
            if select_index is not None and det_i == select_index:
                w.setCurrentItem(it)
        self._recog_tree_page = pg
        w.blockSignals(False)

    def on_recog_name_clicked(self, item, _col=0):
        d = item.data(0, Qt.UserRole)
        if isinstance(d, dict) and d.get("rack") is not None:   # 每根支架：跳到那一根
            if hasattr(self, "recog_canvas"):
                self.recog_canvas.select_det(int(d["rack"]))
            return
        if isinstance(d, dict):                 # ROW 行：跳到这一列最上面那根支架
            racks = [x for x in (d.get("racks") or []) if x is not None]
            if racks and hasattr(self, "recog_canvas"):
                self.recog_canvas.select_det(int(racks[0]))
            return
        i = d
        if i is not None and hasattr(self, "recog_canvas"):
            self.recog_canvas.select_det(int(i))

    def on_recog_name_double(self, item, _col=0):
        d = item.data(0, Qt.UserRole)
        if isinstance(d, dict) and d.get("rack") is not None:
            self.on_recog_rack_assign(item)     # 每根支架：双击改它的串数
            return
        if isinstance(d, dict):                 # ROW 行：双击展开/收起
            item.setExpanded(not item.isExpanded())
            return
        self.on_recog_name_clicked(item)
        w = getattr(self, "recog_names", None)
        if w is not None:
            w.editItem(item)

    def on_recog_rack_assign(self, item):
        """改一根支架的串数（匹配不上档的 ? 也能直接定）。

        写进 raw.strings 并打「手填」标记，之后点「应用到支架页」不会覆盖；
        改完这一列的 3S+2X 这种组合也会跟着更新（画图还是原来的 STR 号）。
        """
        d = item.data(0, Qt.UserRole) or {}
        idx = d.get("rack")
        if idx is None:
            return
        doc = getattr(self, "_recog_doc", None) or {}
        pg = getattr(self, "_recog_page", None)
        trk = next((p for p in doc.get("yolo_tracker_detection_results") or []
                    if p.get("page_number") == pg), None)
        dets = ((trk or {}).get("data") or {}).get("detections") or []
        if not (0 <= idx < len(dets)):
            return
        det = dets[idx]
        cur = (det.get("raw") or {}).get("strings")
        names = []
        if cur not in (None, ""):
            names.append(str(cur))
        for strings, _ln, _sp, _ct in (self._recog_rack_rows() or []):
            s = (strings or "").strip()
            if s and s not in names:
                names.append(s)
        val, ok = QInputDialog.getItem(
            self, "改这根支架的串数",
            "这根支架现在 %s，改成几串？（可以直接填）"
            % ("是 %s 串" % cur if cur not in (None, "") else "没匹配到串数"),
            names, 0, True)
        if not ok or not str(val).strip():
            return
        sv = str(val).strip()
        try:
            sv = int(float(sv))
        except Exception:
            pass
        raw = dict(det.get("raw") or {})
        raw["strings"] = sv
        raw["strings_manual"] = True            # 手填的：点「应用到支架页」不覆盖
        det["raw"] = raw
        self._recog_dirty = True
        if hasattr(self, "recog_save_btn"):
            self.recog_save_btn.setEnabled(True)
        # 记住这一行本来是展开的，重画后保持展开，方便接着改旁边的
        row = item.parent()
        if row is not None:
            top = row.parent()
            if top is not None:
                opened = getattr(self, "_recog_row_open", None) or set()
                opened.add((pg, top.text(0), top.indexOfChild(row)))
                self._recog_row_open = opened
        self._recog_refresh_names()
        self._recog_write("这根支架的串数手动改成 %s（记得点「保存修改」写回 JSON）" % sv)

    def on_recog_name_edited(self, item, _col=0):
        """项目树里直接改编号：写回识别结果（和画布上改名同一条路）。"""
        if getattr(self, "_recog_names_busy", False):
            return
        if isinstance(item.data(0, Qt.UserRole), dict):
            return                              # 支架行：不是编号，别写回去
        self._recog_names_busy = True
        i = None
        try:
            i = item.data(0, Qt.UserRole)
            if i is not None and hasattr(self, "recog_canvas"):
                self.recog_canvas.select_det(int(i))
                name = item.text(0).strip()
                if name == "（没编号）":
                    name = ""
                if self.recog_canvas.rename_selected(name):
                    self.recog_name_edit.setText(name)
                    self._recog_write("编号改成：%s（记得「保存修改」）" % (name or "（空）"))
        finally:
            self._recog_names_busy = False
        # 改完按新编号重排一下（名字栏是按编号排的）。等这一轮信号走完再做：
        # 在 itemChanged 里直接把列表清空重建会动到正在编辑的那一项。
        QTimer.singleShot(0, lambda: self._recog_refresh_names(select_index=i))

    def on_recog_regroup_now(self):
        """手动重算「支架长度分档」（画完 / 改完框之后马上要看新分档时点）。"""
        t = getattr(self, "_heavy_timer", None)
        if t is not None:
            t.stop()                 # 别让延后的那次再跑一遍
        self._recog_regroup()

    def _recog_issue_items(self, page=None):
        """扫一遍识别结果，返回 [(页号, '第 X 页：…'), …]。"""
        return self._recog_issue_items_impl(page)

    def _recog_issues(self, page=None):
        """只要文字版（弹窗 / 日志用）。"""
        return [t for _pg, t in self._recog_issue_items_impl(page)]

    def _recog_issue_items_impl(self, page=None):
        """扫一遍识别结果，把可能有问题的地方列成 ['第 X 页：…', …]（给用户反馈）。"""
        from collections import Counter
        doc = getattr(self, "_recog_doc", None) or {}
        pairs = []
        for strings, length, _sp, _ct in (self._recog_rack_rows() or []):
            try:
                pairs.append((float(length), int(float(strings))))
            except Exception:
                continue
        try:
            unit_px = self._match_unit_px()
        except Exception:
            unit_px = False
        out = []
        for p in doc.get("yolo_tracker_detection_results") or []:
            pg = p.get("page_number")
            if page is not None and pg != page:
                continue
            dets = (p.get("data") or {}).get("detections") or []
            nodes = [d for d in dets if (d.get("label") or "") == "Node"]
            trks = [d for d in dets if (d.get("label") or "") == "Tracker"]
            if not nodes and not trks:
                continue
            ocr = next((x for x in doc.get("ocr_node_name_results") or []
                        if x.get("page_number") == pg), None)
            recs = (ocr or {}).get("data") or []
            names = []
            for i in range(len(nodes)):
                nm = ""
                if i < len(recs):
                    nm = (recs[i].get("final_node_name")
                          or recs[i].get("preliminary_node_name") or "").strip()
                names.append(nm)
            _noname = sum(1 for n in names if not n)
            _prefonly = sum(1 for n in names if n and not re.search(r"\d$", n))
            dup = [n for n, c in Counter(n for n in names if n).items() if c > 1]
            orphan = 0
            if _lr_assign_parent is not None and nodes:
                boxes = [{"bbox": n.get("bbox") or {}} for n in nodes]
                for t in trks:
                    if _lr_assign_parent(t.get("bbox") or {}, boxes) is None:
                        orphan += 1
            ungraded = 0
            if pairs:
                for t in trks:
                    if (t.get("raw") or {}).get("strings") in (None, ""):
                        try:
                            if self._rack_sv_by_table(t, pg, pairs, unit_px) is None:
                                ungraded += 1
                        except Exception:
                            pass
            parts = []
            if _noname or _prefonly:
                _t = T("%d 个 LBD 没编号", _noname + _prefonly)
                if _prefonly:
                    _t += T("（其中 %d 个已填前缀，补数字即可）", _prefonly)
                parts.append(_t)
            if dup:
                parts.append(T("重复编号 %s",
                               ("、" if cur_lang() == "zh" else ", ").join(dup[:3])))
            if orphan:
                parts.append(T("%d 根支架不在任何 LBD 区（不会编号）", orphan))
            if ungraded:
                parts.append(T("%d 根支架长度没落档", ungraded))
            if nodes and not trks:
                parts.append(T("有 LBD 区但没有支架框"))
            if parts:
                out.append((pg, T("第 %s 页：%s", pg,
                                  ("；" if cur_lang() == "zh" else "; ").join(parts))))
        return out

    def on_recog_check(self):
        """识别结果检查：把发现的问题弹给用户（没编号 / 没落档 / 不在 LBD 里 / 重复编号）。"""
        if not getattr(self, "_recog_doc", None):
            self._recog_write("还没识别，先跑一次「开始识别」")
            return
        iss = self._recog_issues()
        if not iss:
            QMessageBox.information(self, T("识别结果检查"), T("没发现明显问题。"))
            self._recog_write("识别结果检查：没发现明显问题")
            return
        txt = "\n".join(iss[:20])
        if len(iss) > 20:
            txt += "\n" + T("…（还有 %d 页有问题，看看识别页左表和画布）", len(iss) - 20)
        QMessageBox.warning(self, T("识别结果检查（%d 页有问题）", len(iss)), txt)
        self._recog_write("识别结果检查：%d 页有问题（没编号的 LBD 可在画布选中后改名；"
                          "没落档的支架可在「整册支架长度」表补一档）" % len(iss))

    def on_recog_relabel(self):
        """按 PDF 文字层重新识别本页 LBD 编号（挪过 / 加过 LBD 框之后用）。

        用和识别时同一套规则（框内最近的文字 + 标签表这个分表的号表）；读到就写回，
        读不到的保留原来名字 —— 不会把手工改过的编号抹掉。
        """
        doc = getattr(self, "_recog_doc", None)
        pdf = (self.get_text("pdf") or "").strip()
        pg = getattr(self, "_recog_page", None)
        if not (doc and pdf and os.path.exists(pdf) and pg):
            self._recog_write("重新识别编号：先选 PDF、识别出一页再来")
            return
        trk = next((p for p in doc.get("yolo_tracker_detection_results") or []
                    if p.get("page_number") == pg), None)
        dets = ((trk or {}).get("data") or {}).get("detections") or []
        if not dets:
            self._recog_write("这一页没有识别结果")
            return
        try:
            import detect as _d
            import lbd_naming as _N
            ts = _d.pdf_text_runs(pdf, pg)
            meta = next((p for p in (doc.get("input_data") or {}).get("pages") or []
                         if p.get("page_number") == pg), {})
            W, H = float(meta.get("width") or 0), float(meta.get("height") or 0)
            xlsx = (self.get_text("xlsx") or "").strip()
            sheet_names = read_xlsx_sheet_names(xlsx) if xlsx else []
            labels = read_xlsx_lbd_labels(xlsx) if xlsx else {}
            sheet, _c = _N.page_sheet_by_text(ts, sheet_names) if sheet_names else (None, 0)
            num_set = set((labels.get(sheet) or {}).keys()) if sheet else set()
            shapes = _d._shapes_of(dets)
            _N.autofill_shapes(shapes, ts, sheet, num_set, W, H)
        except Exception as e:
            self._recog_write("重新识别编号失败：%s" % e)
            return
        ocr = next((p for p in doc.get("ocr_node_name_results") or []
                    if p.get("page_number") == pg), None)
        if ocr is None:
            ocr = {"page_number": pg, "data": []}
            doc.setdefault("ocr_node_name_results", []).append(ocr)
        recs = ocr.setdefault("data", [])
        changed = kept = k = 0
        for i, s in enumerate(shapes):
            if (s.get("label") or "") != "Node":
                continue
            while len(recs) <= k:
                recs.append({"node_bbox": {}, "final_node_name": "",
                             "preliminary_node_name": "", "selected": {}})
            rec = recs[k]
            nm = (s.get("name") or "").strip()
            if nm:
                if (rec.get("final_node_name") or "") != nm:
                    changed += 1
                rec["final_node_name"] = nm
                rec["preliminary_node_name"] = nm
            else:
                kept += 1
            b = dets[i].get("bbox") or {}
            if all(t in b for t in ("x1", "y1", "x2", "y2")):
                rec["node_bbox"] = {t: round(float(b[t]), 2) for t in ("x1", "y1", "x2", "y2")}
            dets[i]["raw"] = dict(s.get("raw") or dets[i].get("raw") or {})
            k += 1
        # 读不到具体编号的：填上同页公共前缀（如 INV11A101-LBD-），用户只要补数字
        pref, filled = "", 0
        try:
            import lbd_naming as _N2
            pref = _N2.lbd_prefix_of([r.get("final_node_name") for r in recs[:k]])
        except Exception:
            pref = ""
        if pref:
            for r in recs[:k]:
                if not (r.get("final_node_name") or "").strip():
                    r["final_node_name"] = pref
                    r["preliminary_node_name"] = pref
                    filled += 1
        self._recog_dirty = True
        if hasattr(self, "recog_save_btn"):
            self.recog_save_btn.setEnabled(True)
        self._recog_mark_dirty()
        self._recog_refresh_names()
        self._recog_update_page_info(pg)
        self._recog_write("重新识别 LBD 编号（第 %s 页）：改到 %d 个、%d 个没读到%s"
                          % (pg, changed, kept,
                             ("（%d 个填了前缀 %s，补数字即可）" % (filled, pref))
                             if filled else "（保留原值）"))

    def on_recog_lock_lbd(self, on):
        """锁定 / 解锁本页的 LBD 区（写进识别结果，和标注软件同一套：点不中/拖不动/删不掉）。"""
        pg = getattr(self, "_recog_page", None)
        if pg is None:
            return
        c = getattr(self, "recog_canvas", None)
        if c is not None:
            c.set_lbd_locked(bool(on))
        self._recog_dirty = True
        if hasattr(self, "recog_save_btn"):
            self.recog_save_btn.setEnabled(True)
        self._recog_write(("第 %s 页 LBD 区已锁定：点不中、拖不动、删不掉（支架 / 汇流箱照常），"
                           "记得点「保存修改」" % pg)
                          if on else ("第 %s 页 LBD 区已解锁" % pg))

    def _sync_lock_btn(self):
        """「锁定 LBD」按钮跟着本页实际锁定状态走（Ctrl+ 点单独解锁也会反映出来）。"""
        c = getattr(self, "recog_canvas", None)
        btn = getattr(self, "recog_lock_btn", None)
        if c is None or btn is None:
            return
        nodes = [b for b in c.box_items if b.kind == "Node"]
        lock = bool(nodes) and all(getattr(b, "locked", False) for b in nodes)
        btn.blockSignals(True)
        btn.setChecked(lock)
        btn.blockSignals(False)

    def on_recog_draw_mode(self, kind):
        """画框模式（和标注软件一致）：画 Box / 画支架 / 画 LBD 区；再点一次回到选择。"""
        c = getattr(self, "recog_canvas", None)
        if c is not None:
            c.cancel_draw()          # 换工具/退出时，先丢掉画到一半的那一笔
        btns = getattr(self, "recog_draw_btns", {})
        on = bool(btns.get(kind) and btns[kind].isChecked())
        for k, b in btns.items():
            if k != kind:
                b.setChecked(False)
        mode = kind if on else ""
        if c is not None:
            c.add_mode = mode
            c.setFocus()
            c.setDragMode(QGraphicsView.NoDrag if mode else QGraphicsView.RubberBandDrag)
            c.setCursor(Qt.CrossCursor if mode else Qt.ArrowCursor)
            # 视口自己的光标优先，之前给视口设过箭头，这里要一起换掉，十字才看得到
            c.viewport().setCursor(Qt.CrossCursor if mode else Qt.ArrowCursor)
        name = {"Box": "画 Box（汇流箱）", "Tracker": "画支架", "Node": "画 LBD 区"}.get(kind, kind)
        self._recog_write(("进入「%s」模式：点一下定第一个角、移到对角再点一下成框"
                           "（也可以按住左键直接拖）；再点一下这个按钮退出"
                           % name) if mode else "回到选择模式")

    def on_recog_escape(self):
        """ESC：退出画框模式，回到选择模式。

        画框模式一直挂着的时候，鼠标一动就拖出虚线框、框也点不中 —— 这两个 bug
        都是它引起的；标注软件里 ESC 也是这个语义（先丢这一笔，再退模式）。
        """
        for b in (getattr(self, "recog_draw_btns", {}) or {}).values():
            b.setChecked(False)
        c = getattr(self, "recog_canvas", None)
        if c is not None:
            c.cancel_draw()
            c.add_mode = ""
            c.setDragMode(QGraphicsView.RubberBandDrag)
            c.setCursor(Qt.ArrowCursor)
        self._recog_write("已退出画框模式（回到选择模式）")

    def on_recog_box_added(self, kind, det_index):
        self._recog_sync_all("加了一个%s框" % ("LBD 区" if kind == "Node" else "支架"))
        self._recog_write("记得点「保存修改」写回 JSON")
        self._recog_refresh_names(select_index=det_index)
        self._recog_update_page_info()

    def on_recog_page_step(self, delta):
        """键盘翻页：PgDn/PgUp、Ctrl+←/→（页列表直接用左边那张表）。"""
        rows = self._recog_pages_of_doc()
        if not rows:
            return
        pages = [r[0] for r in rows]
        try:
            i = pages.index(getattr(self, "_recog_page", None))
        except ValueError:
            i = 0
        j = i + int(delta)
        if not (0 <= j < len(pages)):
            return
        pg = pages[j]
        self._recog_preview_page(pg)
        self._select_recog_table_page(pg)
        self._recog_write("第 %s 页（%d/%d，PgUp/PgDn 可翻页）" % (pg, j + 1, len(pages)))

    def _select_recog_table_page(self, pg):
        """把左边表格切到这一页那一行（信号挡住，免得再触发一次画布加载）。"""
        t = getattr(self, "recog_table", None)
        if t is None:
            return
        for i in range(t.rowCount()):
            it = t.item(i, 0)
            if it is not None and it.text() == str(pg):
                t.blockSignals(True)
                t.selectRow(i)
                t.blockSignals(False)
                return

    def on_recog_bottom_toggled(self, on):
        """兼容旧调用：识别页不再显示日志区（日志仍写文件）。"""
        return

    def on_recog_next(self):
        """下一步：保存改动 + 把支架类型带过去 + 切到参数页填其它参数。"""
        if not getattr(self, "_recog_doc", None):
            QMessageBox.information(self, "还没识别", "先点「开始识别」。")
            return
        if getattr(self, "_recog_dirty", False):
            self.on_save_recog_edits()
        self.on_apply_recog_racks()
        self._recog_refresh_names()
        names = [t for t, _k in SECTIONS]
        if "文件与输出" in names:
            self.show_section(names.index("文件与输出"))
        self.log_msg("识别结果已就绪：%s —— 接着填其它参数，然后「执行输出」"
                     % (self.get_text("jsonPath") or "（临时 JSON）"))

    def on_export_recog_json(self):
        """把识别结果导出成 JSON（导出后下游就用这份）。"""
        doc = getattr(self, "_recog_doc", None)
        if not doc:
            QMessageBox.information(self, "还没识别", "先跑一次「开始识别」，再来导出。")
            return
        base = os.path.splitext(os.path.basename(self.get_text("pdf") or "识别结果"))[0]
        path, _f = QFileDialog.getSaveFileName(self, "导出识别结果 JSON",
                                              base + "_识别结果.json", "JSON (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False)
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))
            return
        self.set_text("jsonPath", path)
        self._recog_write("识别结果已导出：%s" % path)

    def on_save_recog_edits(self):
        """把画布上的改动写回 JSON（临时那份 + 你导出过的那份）。

        保存的就是界面上这一份 doc —— 过滤、改框、改名、加框、删框之后
        内存里的 doc 已经是最新的，这里原样落盘，保证「保存出来的 == 过滤/修改后的」。
        """
        doc = getattr(self, "_recog_doc", None)
        if not doc:
            return
        # 存盘前把统计条数记一下，方便和界面上的数字对账（多余/漏存能一眼看出来）
        try:
            _tk = sum(len((p.get("data") or {}).get("detections") or [])
                      for p in doc.get("yolo_tracker_detection_results") or [])
            _pg = len(doc.get("yolo_tracker_detection_results") or [])
        except Exception:
            _tk, _pg = 0, 0
        paths = []
        tmp = getattr(self, "_recog_tmp_path", "")
        if tmp:
            paths.append(tmp)
        cur = (self.get_text("jsonPath") or "").strip()
        if cur and cur not in paths:
            paths.append(cur)
        ok = 0
        for p in paths:
            try:
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(doc, f, ensure_ascii=False)
                ok += 1
            except Exception as e:
                self._recog_write("保存失败 %s：%s" % (p, e))
        if ok:
            self._recog_dirty = False
            if hasattr(self, "recog_save_btn"):
                self.recog_save_btn.setEnabled(False)
            self._recog_write("修改已保存到 JSON（%d 份：%s）；当前内容：%d 页 / %d 个框，"
                              "和过滤、修改后的结果一致" % (ok, "；".join(paths), _pg, _tk))

    def _build_rack_panel(self):
        """支架类型明细：每个支架类型单独一行；类型自动来自识别结果，拆不拆手工选。"""
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 10, 0, 0)
        v.setSpacing(6)
        t = self._reg(QLabel(), "支架类型明细")
        t.setObjectName("Hint")
        t.setWordWrap(True)
        v.addWidget(t)
        self.rack_grid = QGridLayout()
        self.rack_grid.setHorizontalSpacing(16)
        self.rack_grid.setVerticalSpacing(6)
        v.addLayout(self.rack_grid)
        hb = QHBoxLayout()
        hb.setSpacing(8)
        self.rack_refresh_btn = self._reg(QPushButton(), "从识别结果刷新支架类型")
        self.rack_refresh_btn.clicked.connect(self.on_refresh_rack_types)
        hb.addWidget(self.rack_refresh_btn)
        hb.addStretch(1)
        v.addLayout(hb)
        # STR 编号顺序预览（按当前顺序给一个 LBD 组内的支架编号）
        ph = QHBoxLayout()
        ph.setSpacing(8)
        self.str_preview_btn = self._reg(QPushButton(), "刷新 STR 顺序预览")
        self.str_preview_btn.clicked.connect(self.on_refresh_str_preview)
        ph.addWidget(self.str_preview_btn)
        self.str_preview_info = QLabel("")
        self.str_preview_info.setObjectName("Hint")
        self.str_preview_info.setWordWrap(True)       # 同上：说明长了不撑宽整页
        ph.addWidget(self.str_preview_info, 1)
        v.addLayout(ph)
        self.str_preview = StrOrderPreview()
        v.addWidget(self.str_preview)
        self.rack_rows = []          # [(串数, 长度QLineEdit, 拆不拆QComboBox)]
        self._rack_types = []        # 当前明细对应的支架类型(来自识别结果)
        self._rack_len_pref = {}     # 串数 -> 长度文本(用户填过/配置里带的)
        self._rack_split_pref = {}   # 串数 -> 拆不拆
        self.refresh_rack_rows([])
        return box

    def _build_label_panel(self):
        """标签页下面那块：四象限编号规律的示意图（只看四个下拉，不读识别结果）。"""
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 10, 0, 0)
        v.setSpacing(6)
        qh = QHBoxLayout()
        qh.setSpacing(8)
        self.quad_preview_btn = self._reg(QPushButton(), "刷新象限预览")
        self.quad_preview_btn.clicked.connect(self.on_refresh_quad_preview)
        qh.addWidget(self.quad_preview_btn)
        self.quad_preview_info = QLabel("")
        self.quad_preview_info.setObjectName("Hint")
        self.quad_preview_info.setWordWrap(True)      # 说明较长，不换行会把整页撑宽
        qh.addWidget(self.quad_preview_info, 1)
        v.addLayout(qh)
        self.quad_preview = QuadPreview()
        v.addWidget(self.quad_preview)
        # 先按默认值画一次（此时界面还没建完，不能用 cfg()）
        self.quad_preview.set_data(quad_orders_from_cfg(DEFAULTS))
        return box

    def _stash_rack_rows(self):
        """把当前明细行里填的长度/拆分记下来，重建行时不丢。"""
        for key, le, sp in self.rack_rows:
            txt = le.text().strip()
            if txt:
                self._rack_len_pref[key] = txt
            else:
                self._rack_len_pref.pop(key, None)
            self._rack_split_pref[key] = sp.text().strip()

    def refresh_rack_rows(self, types, stash=True):
        """按支架类型列表重建明细行；已填的长度和拆分选择保留。
        stash=False 用于「刚读回配置」的场景，避免用空行覆盖配置里的值。"""
        if stash:
            self._stash_rack_rows()
        self._rack_types = list(types or [])
        while self.rack_grid.count():
            it = self.rack_grid.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self.rack_rows = []
        # 和识别页那张表一样：表头跟着「实际按哪套口径匹配」走
        try:
            _unit_px = self._match_unit_px()
        except Exception:
            _unit_px = False
        for col, head in enumerate(("支架类型", "串数",
                                    "长度px" if _unit_px else "长度", "数量", "拆几行")):
            lb = QLabel(T(head))
            lb.setObjectName("FieldLabel")
            self.rack_grid.addWidget(lb, 0, col)
        if not types:
            empty = QLabel(T("（还没读到识别结果：指定「识别结果 JSON文件」或跑一次「执行输出」后，这里会自动列出）"))
            empty.setObjectName("Hint")
            empty.setWordWrap(True)
            self.rack_grid.addWidget(empty, 1, 0, 1, 5)
            return
        for i, tp in enumerate(types):
            key = str(tp.get("strings"))
            name = QLabel(tp.get("code") or T("%s 串", key))
            self.rack_grid.addWidget(name, i + 1, 0)
            num = QLabel(key)
            self.rack_grid.addWidget(num, i + 1, 1)
            le = QLineEdit()
            le.setObjectName("Field")
            le.setMinimumWidth(110)
            le.setPlaceholderText(T("长度"))
            pref = self._rack_len_pref.get(key)
            if pref:
                le.setText(pref)
            elif tp.get("length_ft"):
                le.setText("%g" % tp["length_ft"])
            self.rack_grid.addWidget(le, i + 1, 2)
            cnt = tp.get("total_count")
            cl = QLabel(str(cnt) if cnt is not None else "—")
            self.rack_grid.addWidget(cl, i + 1, 3)
            sp = QLineEdit()
            sp.setObjectName("Field")
            sp.setMinimumWidth(70)
            sp.setPlaceholderText("0")
            sp.setToolTip(T("0 = 不拆；填 2 / 3 … 表示拆几行"))
            sp.setText(self._rack_split_pref.get(key, ""))
            self.rack_grid.addWidget(sp, i + 1, 4)
            self.rack_rows.append((key, le, sp))

    def _rack_types_current(self):
        return list(self._rack_types or [])

    def rack_row_values(self):
        return [(k, le.text().strip(), sp.text().strip()) for k, le, sp in self.rack_rows]

    def on_rack_types(self, rows):
        """后台线程解析出支架类型后（bus.racks 信号）自动填进明细行。"""
        try:
            self.refresh_rack_rows(rows or [])
            if rows:
                txt = _lr_rack_text(rows) if _lr_rack_text else ""
                self.log_msg("支架类型已自动填入 %d 类：%s（拆不拆请在「支架」页选）"
                             % (len(rows), txt))
        except Exception as e:
            self.log_msg("支架类型填入失败：" + str(e))

    def on_refresh_rack_types(self):
        """手动刷新：从识别结果重新读支架类型。"""
        cfg = self.cfg()
        self.log_msg("正在从识别结果读取支架类型…")
        threading.Thread(target=self._rack_fill_worker, args=(cfg, True), daemon=True).start()

    def _rack_fill_worker(self, cfg, announce=True):
        if _lr_rack_types is None:
            if announce:
                self.bus.prog.emit("支架类型读取失败：缺少 lbd_regions.py")
            return None
        rows, src = [], ""
        for cand in (_lr_candidates(cfg) if _lr_candidates else []):
            try:
                r = _lr_rack_types(cand)
            except Exception:
                r = []
            if r:
                rows, src = r, cand
                break
        if rows:
            self.bus.racks.emit(rows)
            if announce:
                self.bus.prog.emit("支架类型来自 %s" % os.path.basename(src))
        elif announce:
            self.bus.prog.emit("未在识别结果里读到支架类型（支架页保持手填）。")
        return rows

    def auto_fill_rack_types_async(self, cfg, announce=True):
        """能自动填就自动填；解析放在后台线程，不卡界面。"""
        if _lr_rack_types is None or not cfg.get("rackAuto", True):
            return
        threading.Thread(target=self._rack_fill_worker, args=(cfg, announce), daemon=True).start()
        self.on_refresh_str_preview()
        self.on_refresh_quad_preview()

    def on_refresh_str_preview(self):
        """按当前 STR 顺序刷新预览（后台读识别结果，不卡界面）。"""
        if not hasattr(self, "str_preview"):
            return
        try:
            cfg = self.cfg()
        except Exception:
            return
        threading.Thread(target=self._str_preview_worker, args=(cfg,), daemon=True).start()

    def _str_preview_worker(self, cfg):
        if _lr_preview is None or _lr_candidates is None:
            self.bus.strprev.emit({"hint": "缺少 lbd_regions.py，不能预览"})
            return
        try:
            cands = _lr_candidates(cfg)
        except Exception as e:
            self.bus.strprev.emit({"hint": T("查找识别结果出错：%s", e)})
            return
        if not cands:
            self.bus.strprev.emit({"hint": T("没找到识别结果 JSON：请先在上面选「识别结果 JSON文件」")})
            return
        order = str((cfg or {}).get("strOrder", "2") or "2").strip() or "2"
        quad_map = quad_map_spec(cfg)
        apply_rack_len_hints(cfg)          # 明细行的长度FT -> 判支架类型（拆分要用）
        split = rack_split_spec(cfg)
        for jp in cands:
            try:
                d = _lr_preview(jp, order=order, split=split,
                                quad_rule="", quad_map=quad_map)
            except Exception:
                d = None
            if d:
                self.bus.strprev.emit(d)
                return
        self.bus.strprev.emit({"hint": "这份识别结果里没读到 LBD 区域或支架框"})

    def on_str_preview(self, data):
        if not hasattr(self, "str_preview"):
            return
        d = data or {}
        if not d.get("items"):
            self.str_preview.set_data(hint=d.get("hint") or "没有可预览的支架")
        else:
            self.str_preview.set_data(d.get("page"), d.get("group"), d["items"],
                                      d.get("hint", ""), d.get("cols", 1), d.get("rows", 1))
        if hasattr(self, "str_preview_info"):
            self.str_preview_info.setText(d.get("hint") or "")

    def on_refresh_quad_preview(self):
        """按当前四个象限的顺序刷新象限预览（后台读识别结果，不卡界面）。"""
        if not hasattr(self, "quad_preview"):
            return
        try:
            cfg = self.cfg()
        except Exception:
            return
        self.on_quad_preview({"orders": quad_orders_from_cfg(cfg), "hint": self._quad_hint(cfg)})

    @staticmethod
    def _quad_hint(cfg):
        """预览抬头那句话：说清原点、判据，以及总开关是开是关。"""
        g = str((cfg or {}).get("strOrder", "2") or "2").strip() or "2"
        _g = STR_ORDER_TEXT.get(g, "")
        if not quad_on(cfg):
            return "总开关 = 关：四个象限都按「支架」页的全局顺序 %s" % (_g or g)
        return ("原点 = 本页汇流箱(Box)的几何中心，LBD 区域中心落在哪个象限就用那个象限的顺序；"
                "格子里的 01~09 就是这个顺序的走法（某象限选 0 = 用全局顺序 %s）" % (_g or g))

    def on_quad_on_changed(self):
        """总开关动过：四个象限下拉跟着置灰/恢复，两个预览重算。"""
        self._sync_quad_enabled()
        self.on_refresh_str_preview()
        self.on_refresh_quad_preview()

    def _sync_quad_enabled(self):
        """「按汇流箱四象限规律命名」关掉时，四个象限下拉置灰（选值留着，重开还是原来的）。"""
        w = self.combo.get("strQuadOn")
        on = True if w is None else str(w.currentData()) == "1"
        for k, _t in QUAD_FIELDS:
            c = self.combo.get(k)
            if c is not None:
                c.setEnabled(on)
        b = getattr(self, "quad_preview_btn", None)
        if b is not None:
            b.setText("刷新象限预览" if on else "刷新象限预览（开关已关）")

    def on_quad_preview(self, data):
        if not hasattr(self, "quad_preview"):
            return
        d = data or {}
        self.quad_preview.set_data(d.get("orders"), d.get("hint", ""))
        if hasattr(self, "quad_preview_info"):
            self.quad_preview_info.setText(d.get("hint") or "")



    def _build_status_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(30, 28, 30, 28)
        v.setSpacing(20)
        self.status_label = QLabel("准备就绪")
        self.status_label.setObjectName("PageTitle")
        v.addWidget(self.status_label)
        self.count_label = QLabel("已绘制  0 / ？")
        self.count_label.setObjectName("BigCount")
        v.addWidget(self.count_label)
        self.pbar = QProgressBar()
        self.pbar.setRange(0, 100)
        self.pbar.setTextVisible(False)
        self.pbar.setFixedHeight(18)
        v.addWidget(self.pbar)
        # 按页进度（CAD 侧 LBD_PAGE / AI_PAGE 事件）
        self.page_label = QLabel("")
        self.page_label.setObjectName("Hint")
        v.addWidget(self.page_label)
        # 完成区：跑完由用户选保存位置（不再自动保存到输出目录）
        fin = QFrame()
        fin.setObjectName("FinishBox")
        fv = QHBoxLayout(fin)
        fv.setContentsMargins(16, 12, 16, 12)
        fv.setSpacing(12)
        fcol = QVBoxLayout()
        fcol.setSpacing(4)
        self.finish_title = self._reg(QLabel(), "生成完成后，点右下角「下载」选择保存位置")
        self.finish_title.setObjectName("FinishTitle")
        self.finish_hint = self._reg(QLabel(), "不会再自动保存到“默认保存目录”，选完路径才写文件")
        self.finish_hint.setObjectName("Hint")
        self.finish_hint.setWordWrap(True)
        fcol.addWidget(self.finish_title)
        fcol.addWidget(self.finish_hint)
        fv.addLayout(fcol, 1)
        self.save_btn = self._reg(QPushButton(), "下载")
        self.save_btn.setObjectName("Primary")
        self.save_btn.setFixedHeight(38)
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.on_save_dwg)
        self.pdf_btn = self._reg(QPushButton(), "导出 PDF")
        self.pdf_btn.setFixedHeight(38)
        self.pdf_btn.setEnabled(False)
        self.pdf_btn.clicked.connect(self.on_export_pdf)
        if FEATURE_EXPORT_PDF:
            fv.addWidget(self.pdf_btn)
        else:
            self.pdf_btn.setVisible(False)      # 这一版不带导出 PDF（代码留着，改开关就回来）
        fv.addWidget(self.save_btn)
        v.addWidget(fin)
        return page

    def show_section(self, idx):
        self.run_active = False
        self.section_stack.setCurrentIndex(idx)
        self.content_stack.setCurrentIndex(0)
        if hasattr(self, "sidebar"):
            self.sidebar.setVisible(True)
        if hasattr(self, "back_recog_btn"):
            self.back_recog_btn.setVisible(True)
        for b in (getattr(self, "recog_prev_btn", None), getattr(self, "recog_next_btn", None)):
            if b is not None:
                b.setVisible(False)
        if hasattr(self, "log"):
            self.log.setVisible(True)
        self._on_section_shown(idx)

    def show_recog_workspace(self):
        """整个窗口只留识别（和标注软件那样）：侧边栏收起来，识别填完点「下一步」再进流程。"""
        self.run_active = False
        self.content_stack.setCurrentIndex(2)
        if hasattr(self, "sidebar"):
            self.sidebar.setVisible(False)
        if hasattr(self, "back_recog_btn"):
            self.back_recog_btn.setVisible(False)
        for b in (getattr(self, "recog_prev_btn", None), getattr(self, "recog_next_btn", None)):
            if b is not None:
                b.setVisible(True)
        # 识别页不需要底部那条日志，把高度让给画布
        if hasattr(self, "log"):
            self.log.setVisible(False)
        self._recog_sync_inputs()

    def get_text(self, key):
        w = self.edits.get(key)
        return w.text().strip() if w else ""

    def set_text(self, key, value):
        w = self.edits.get(key)
        if w:
            w.setText(value or "")

    # ---------------- 中英文 ----------------
    def _reg(self, w, zh):
        """登记一个"文字跟着语言走"的控件，并按当前语言先填一次。"""
        self._i18n.append((w, zh))
        w.setText(T(zh))
        return w

    def _reg_tip(self, w, zh):
        self._i18n_tip.append((w, zh))
        w.setToolTip(T(zh))
        return w

    @staticmethod
    def _shrinkable(w, minw=60):
        """长中文提示：允许被压窄。

        中文没有空格，wordWrap 的 QLabel 最小宽度会按"最长不可断的一串"算 —— 一句中文
        就能把整页最小宽度顶到 1000+，窗口一窄就冒出左右滚动条。把宽度策略设成 Ignored
        就没这个问题（文字照旧换行显示）。
        """
        w.setWordWrap(True)
        w.setMinimumWidth(minw)
        w.setSizePolicy(QSizePolicy.Ignored, w.sizePolicy().verticalPolicy())
        return w

    def _reg_combo(self, cb, items, en=None):
        """登记下拉框（显示文字可翻译，data 值不动）。en = 逐项对应的英文写法。"""
        self._i18n_combo.append((cb, list(items), list(en) if en else None))
        self._fill_combo_lang(cb, items, en)
        return cb

    def _reg_ph(self, w, zh):
        """登记输入框的占位提示（和 setText 一样跟着语言走）。"""
        self._i18n_ph.append((w, zh))
        w.setPlaceholderText(T(zh))
        return w

    def _fill_combo_lang(self, cb, items, en=None):
        keep = cb.currentData()
        cb.blockSignals(True)
        cb.clear()
        for i, (zh, val) in enumerate(items):
            if cur_lang() == "en" and en and i < len(en):
                cb.addItem(en[i], val)
            else:
                cb.addItem(T(zh), val)
        i = cb.findData(keep) if keep is not None else -1
        cb.setCurrentIndex(i if i >= 0 else 0)
        cb.blockSignals(False)

    def _reg_headers(self, table, headers):
        self._i18n_headers.append((table, list(headers)))
        table.setHorizontalHeaderLabels([T(h) for h in headers])
        return table

    def on_switch_lang(self):
        """顶栏那个地球图标：中文 <-> English。"""
        set_lang("en" if cur_lang() == "zh" else "zh")
        self.retranslate()
        self.log_msg(("已切换语言：%s" % LANG_NAMES[cur_lang()]) if cur_lang() == "zh"
                     else ("Language switched to %s" % LANG_NAMES[cur_lang()]))

    def retranslate(self):
        """把界面上登记过的文字全部按当前语言重刷一遍（不重建控件，状态不丢）。"""
        for w, zh in getattr(self, "_i18n", []):
            try:
                w.setText(T(zh))
            except Exception:
                pass
        for w, zh in getattr(self, "_i18n_tip", []):
            try:
                w.setToolTip(T(zh))
            except Exception:
                pass
        for cb, items, en in getattr(self, "_i18n_combo", []):
            try:
                self._fill_combo_lang(cb, items, en)
            except Exception:
                pass
        for w, zh in getattr(self, "_i18n_ph", []):
            try:
                w.setPlaceholderText(T(zh))
            except Exception:
                pass
        for table, headers in getattr(self, "_i18n_headers", []):
            try:
                table.setHorizontalHeaderLabels([T(h) for h in headers])
            except Exception:
                pass
        # 动态文字（不在登记表里的）
        for w, zh in getattr(self, "_i18n_nav", []):
            try:
                w.setText(T(zh))
            except Exception:
                pass
        self._lang_tip()
        # 兜底：万一某个语言下文字比控件宽（字体不同 / 窗口很窄），悬停至少能看到全文
        for w, _zh in list(getattr(self, "_i18n", [])) + list(getattr(self, "_i18n_nav", [])):
            try:
                if isinstance(w, (QLabel, QPushButton)) and w.text() and not w.toolTip():
                    w.setToolTip(w.text())
            except Exception:
                pass
        try:                       # 支架类型明细行是动态生成的，重建一次就跟着换语言
            self.refresh_rack_rows(self._rack_types_current(), stash=False)
        except Exception:
            pass
        try:
            if hasattr(self, "recog_rack_table"):
                self.recog_rack_table.setHorizontalHeaderLabels(
                    [T(h) for h in ("串数", "长度", "数量", "拆几行")])
        except Exception:
            pass
        # 动态文字：本页问题条 / PDF 选择状态（它们不走 setText 登记表）
        try:
            self._update_issue_bar()
        except Exception:
            pass
        try:
            _p = getattr(self, "_recog_pdf_full", "") or self.get_text("pdf")
            if hasattr(self, "recog_pdf_state"):
                self.recog_pdf_state.setText(T("已选择") if _p else T("未选择"))
        except Exception:
            pass
        # STR 顺序预览的提示语是后台线程发过来的，切语言时重新发一次
        try:
            if hasattr(self, "str_preview_info") and self.str_preview_info.text():
                self.on_refresh_str_preview()
        except Exception:
            pass
        if getattr(self, "run_status", ""):
            self.status_label.setText(self.run_status)
        else:
            try:
                self.status_label.setText(T("准备就绪"))
            except Exception:
                pass

    def _lang_tip(self):
        if hasattr(self, "lang_btn"):
            self.lang_btn.setToolTip(
                "语言：中文（点击切到 English）" if cur_lang() == "zh"
                else "语言：English（点击切到中文）")
        if hasattr(self, "upd_btn"):
            self.upd_btn.setToolTip(T("检查更新"))
        if hasattr(self, "notes_btn"):
            self.notes_btn.setToolTip(T("更新日志"))

    def cfg(self):
        c = {}
        for k, _ in FIELDS:
            c[k] = self.combo[k].currentData() if k in self.combo else self.get_text(k)
        # 模板布局名 / 底图标记名固定用默认值（界面不再给填）：留空 = 自动取第一个带视口的布局
        c["templateLayout"] = DEFAULTS["templateLayout"]
        c["filter"] = DEFAULTS["filter"]
        c["overwrite"] = False                 # 永远生成新布局，不再覆盖同名布局
        c["regionFit"] = self.checkbox["regionFit"].isChecked()
        c["rackAuto"] = True                   # 识别结果里有支架类型就自动读，没有就手填
        c["labelWhere"] = "M"          # 固定模型空间（界面不再给「当前布局」选项）
        # 四个象限的顺序合并成一行存进配置（下游只认这一行，见 quad_map_spec）
        c["strQuadMap"] = quad_map_spec(c)
        # 支架类型明细行(每类一行)优先：类型自动来自识别结果，长度FT/拆不拆按行填。
        # 长度FT 只按比例用（判「哪一列是哪一类」）；没填的类型用串数当比例，
        # 所以不填也能把两类分开。没有明细行时才用上面手填的 rackTypes/rackSplit。
        rows = self.rack_row_values()
        if rows:
            c["rackTypes"] = ", ".join(("%s:%s" % (k, l)) if l else k for k, l, _s in rows)
            c["rackSplitByType"] = "; ".join("%s=%s" % (k, s) for k, _l, s in rows)
        else:
            c["rackSplitByType"] = ""
        hints, proxy = {}, []
        for k, l, _s in rows:
            try:
                key = int(float(k))
            except (TypeError, ValueError):
                continue
            try:
                val = float(str(l).strip())
            except (TypeError, ValueError):
                val = 0.0
            if val <= 0:
                val = float(key)          # 没填长度FT：用串数当比例（只比大小，不看绝对值）
                proxy.append(key)
            if val > 0:
                hints[key] = val
        c["rackLenHints"] = hints
        c["rackLenProxy"] = proxy         # 只为日志：哪几类用的是串数代替
        return c

    def set_cfg(self, c):
        for k, _ in FIELDS:
            if k in self.combo:
                val = str(c.get(k, DEFAULTS.get(k, "1")))
                idx = self.combo[k].findData(val)
                if idx < 0:
                    idx = self.combo[k].findData("1")
                self.combo[k].setCurrentIndex(idx)
            else:
                self.set_text(k, c.get(k, DEFAULTS.get(k, "")))
        self.checkbox["regionFit"].setChecked(bool(c.get("regionFit", True)))
        # 老配置里「拆不拆」存的是 不拆 / 2行 / 3行：统一折成数字，填在「拆几行」输入框里
        if "rackSplit" in getattr(self, "edits", {}):
            _v = str(c.get("rackSplit") or "").strip()
            _m = re.search(r"\d+", _v)
            self.edits["rackSplit"].setText(_m.group(0) if _m else "")
        # 老配置里只有合并那一行 "右上=4;左上=8"（没有四个下拉的值）时，拆回四个下拉
        if not any(str(c.get(k, "") or "").strip() for k, _q in QUAD_FIELDS):
            for q, v in (parse_quad_spec(c.get("strQuadMap")) or {}).items():
                key = {"I": "strQuadI", "II": "strQuadII",
                       "III": "strQuadIII", "IV": "strQuadIV"}.get(q)
                w = self.combo.get(key) if key else None
                if w is not None:
                    i = w.findData(v)
                    if i >= 0:
                        w.setCurrentIndex(i)
        self._sync_quad_enabled()      # 开关状态 -> 四个象限下拉的可用状态
        self.on_refresh_quad_preview()  # 载入配置后把象限示意图按新值重画
        # 记忆每个支架类型的长度/拆分，明细行重建时套用
        self._rack_len_pref = {}
        self._rack_split_pref = {}
        for part in re.split(r"[;,]", str(c.get("rackSplitByType") or "")):
            if "=" in part:
                _k, _v = part.split("=", 1)
                if _k.strip():
                    _m = re.search(r"\d+", _v)
                    self._rack_split_pref[_k.strip()] = _m.group(0) if _m else ""
        for part in re.split(r"[,;]", str(c.get("rackTypes") or "")):
            if ":" in part:
                _k, _v = part.split(":", 1)
                if _k.strip() and _v.strip():
                    self._rack_len_pref[_k.strip()] = _v.strip()
        self.refresh_rack_rows(self._rack_types_current(), stash=False)
        # labelWhere 固定模型空间：老配置里是 "L" 也忽略（界面已无此选项）

    def log_msg(self, text):
        self.log.appendPlainText(text)

    def closeEvent(self, ev):
        """关窗口：不再写 config.json（以前会在 exe 同目录落一个文件）。"""
        super().closeEvent(ev)

    @staticmethod
    def _range_count_from_input(cfg):
        # 纯按输入的起始页~结束页计算（不读 PDF、不卡界面）
        try:
            ps = int(cfg.get("pageStart") or 1)
            pe = int(cfg.get("pageEnd") or 0)
        except Exception:
            return None, None
        if ps < 1:
            ps = 1
        if pe <= 0:
            return None, None          # 结束页未设，交给执行时按“全部”识别
        if pe < ps:
            return None, None          # 结束 < 起始，不填
        return pe - ps + 1, "起始 %d ~ 结束 %d，共 %d 页" % (ps, pe, pe - ps + 1)

    def _recalc_count_from_range(self, *args):
        n, msg = self._range_count_from_input(self.cfg())
        if n is None:
            return
        if self.get_text("count").strip() != str(n):
            self.set_text("count", str(n))
            self.log_msg("复制布局数量（按起始~结束）：%s" % msg)

    def browse(self, key):
        if key in ("outputDir", "regionOut"):
            d = QFileDialog.getExistingDirectory(self, "选择输出目录")
            if d:
                self.set_text(key, d)
            return
        filt = {
            "pdf": "PDF 文件 (*.pdf);;所有文件 (*.*)",
            "dwg": "DWG 文件 (*.dwg);;所有文件 (*.*)",
            "lspPath": "LISP 文件 (*.lsp);;所有文件 (*.*)",
            "xlsx": "Excel (*.xlsx *.xls);;所有文件 (*.*)",
            "jsonPath": "JSON (*.json);;所有文件 (*.*)",
        }.get(key, "所有文件 (*.*)")
        path, _ = QFileDialog.getOpenFileName(self, "选择文件", "", filt)
        if path:
            self.set_text(key, path)
            if key == "jsonPath":
                self.auto_fill_rack_types_async(self.cfg(), announce=True)

    def on_run(self):
        cfg = self.cfg()
        # 自动识别：count 为 0/空 时，优先按输入的起始页~结束页算；结束页未设(0=全部)才读 PDF 总页数
        _cnt = str(cfg.get("count") or "0").strip()
        if _cnt in ("", "0"):
            _n, _msg = self._range_count_from_input(cfg)
            if not _n:
                _n, _msg = pdf_page_range_count(cfg)
            if _n:
                self.set_text("count", str(_n))
                cfg = self.cfg()
                self.log_msg("复制布局数量：%s" % _msg)
        # B2：给了 PDF 或识别/标注结果 JSON，就让 exe 就地生成标签文件（P/L 行），
        # 并把结果路径/开关交给 LSP；LBD 名字/位置从 JSON 里来（不再由主程序翻 PDF 文字层）。
        _pdf = (cfg.get("pdf") or "").strip()
        _jp0 = (cfg.get("jsonPath") or "").strip()
        if (_pdf and os.path.exists(_pdf)) or (_jp0 and os.path.exists(_jp0)):
            cfg["lbdPre"] = "1"
            cfg["lbdOut"] = os.path.join(tempfile.gettempdir(), "pdflbd_extract.txt")
        else:
            cfg["lbdPre"] = "0"
            cfg["lbdOut"] = ""
        # 布局命名：只按 LBD Excel 的分表名（命名规则已取消，没有分表名就不执行）
        _names, _nmsg = plan_names(cfg)
        if not _names:
            self.log_msg("无法开始：%s" % _nmsg)
            return
        self.log_msg("按分表名命名布局：%d 个（%s）" % (len(_names), _nmsg))
        self.log_msg("  " + "  ".join(_names[:20]) + ("  …" if len(_names) > 20 else ""))
        # 保存交给界面：CAD 侧不再自动 SAVEAS（autoSave=0）
        cfg["autoSave"] = "0"
        self._ai_step = ensure_ai_lsp() is not None
        self._finish_ready = False
        self._phase = ""
        self._generated_layouts = list(_names)
        self.save_btn.setEnabled(False)
        self.save_btn.setText("下载")
        self.pdf_btn.setEnabled(False)
        self.pdf_btn.setText("导出 PDF")
        self.finish_title.setText("生成完成后，点右下角「下载」选择保存位置")
        self.finish_hint.setText("不会再自动保存到“默认保存目录”，选完路径才写文件")
        # 读取配置里的 AI 自动识别参数
        try:
            _d = load_config()
            for _k in ("regionOut",):
                cfg[_k] = (_d.get(_k) or "").strip() or DEFAULTS.get(_k, "")
        except Exception:
            pass
        ini = os.path.join(tempfile.gettempdir(), "pdfauto.ini")
        prog = os.path.join(tempfile.gettempdir(), "pdfauto_prog.txt")
        try:
            write_auto_ini(cfg, ini)
            open(prog, "w").close()
        except Exception as e:
            self.log_msg("写入执行配置失败：" + str(e))
            return
        self.run_active = True
        self.total = 0
        self.done_n = 0
        self.run_status = "开始执行：连接 CAD…"
        self.status_label.setText("正在连接 / 启动 CAD…")
        self.count_label.setText("已绘制  0 / ？")
        self.pbar.setValue(0)
        self.content_stack.setCurrentIndex(1)
        self.log_msg("正在调用 ZWCAD 执行（请切到 ZWCAD 等待）…")
        self._prog_path = prog
        self._prog_len = 0
        # 新一轮：各阶段的进度/计时全部清零（阶段在 _poll_prog 里只往前推进）
        self._lay_done = self._lay_total = 0
        self._reg_done = self._reg_total = 0
        self._lbd_done = self._lbd_total = 0
        self._ai_done = self._ai_total = 0
        self._region_seen = 0
        self._region_times = []
        self._region_logged = False
        # 计时：每一步的开始时间 + 总时长；上一轮的记录全部丢掉（重新执行就是新进程）
        self._run_started = time.time()
        self._step_times = {}
        self._step_name = ""
        self._step_t0 = self._run_started
        self._paused = False
        self._stopped = False
        if hasattr(self, "pause_btn"):
            self.pause_btn.setEnabled(True)
            self.pause_btn.setText(T("暂停"))
        if hasattr(self, "stop_btn"):
            self.stop_btn.setEnabled(True)
        for _p in (self._pause_flag_path(), self._stop_flag_path()):
            try:
                os.remove(_p)
            except Exception:
                pass
        if self._poll_timer:
            self._poll_timer.stop()
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_prog)
        self._poll_timer.start(150)
        threading.Thread(target=auto_worker, args=(cfg, ini, prog, self.bus), daemon=True).start()

    # ---------------- 暂停 / 继续 ----------------
    def _pause_flag_path(self):
        return os.path.join(tempfile.gettempdir(), "vcad_pause.flag")

    def _stop_flag_path(self):
        return os.path.join(tempfile.gettempdir(), "vcad_stop.flag")

    def on_stop(self):
        """「停止」：写停止标记 —— CAD 侧插件在每个检查点看到就收尾停下。"""
        if not self.run_active:
            self.log_msg("现在没有在执行")
            return
        try:
            with open(self._stop_flag_path(), "w", encoding="utf-8") as f:
                f.write("stop")
        except Exception as e:
            self.log_msg("写停止标记失败：%s" % e)
        self._stopped = True
        self.run_status = "已停止（等 CAD 侧收尾）"
        self.status_label.setText(self.run_status)
        self.log_msg("已请求停止：CAD 侧会在下一个检查点收尾（不再画剩下的布局 / 不再写标签）；"
                     "要立刻中断当前命令，请在 ZWCAD 里按 ESC")
        if self._poll_timer:
            self._poll_timer.stop()
        if hasattr(self, "stop_btn"):
            self.stop_btn.setEnabled(False)
        self._log_run_times("执行已停止")

    def on_pause(self):
        """「暂停 / 继续」：冻结界面与进度（随时可停），并把暂停标记写出去。

        真正落图的活儿在 ZWCAD 里跑，Python 这侧停不了 CAD 的当前命令；
        这里做的是：停止推进进度、停止读进度文件、写下暂停标记（插件侧后续可接力），
        想立刻停画图就在 CAD 里按 ESC。
        """
        if not self.run_active:
            self.log_msg("现在没有在执行")
            return
        self._paused = not self._paused
        if self._paused:
            self.pause_btn.setText(T("继续"))
            self._step_pause()
            try:
                with open(self._pause_flag_path(), "w", encoding="utf-8") as f:
                    f.write("paused")
            except Exception:
                pass
            self.log_msg("已暂停：进度停在当前这一步，点「继续」接着往下跑"
                         "（CAD 侧正在执行的命令要立刻停，请在 ZWCAD 里按 ESC）")
            if self._poll_timer:
                self._poll_timer.stop()
        else:
            self.pause_btn.setText(T("暂停"))
            try:
                os.remove(self._pause_flag_path())
            except Exception:
                pass
            self.log_msg("继续执行…")
            self._step_t0 = time.time()
            if self._poll_timer:
                self._poll_timer.start(150)
                self._poll_prog()

    def _step_pause(self):
        """把当前这一步的累计耗时记下来（暂停时也要把这一段的账结掉）。"""
        if self._step_name and self._step_t0:
            self._step_times[self._step_name] = \
                self._step_times.get(self._step_name, 0.0) + (time.time() - self._step_t0)

    def _step_switch(self, name):
        """一步做完换下一步：记耗时、写日志（每步都带时间）。"""
        if not name or name == self._step_name:
            return
        now = time.time()
        if self._step_name and self._step_t0:
            dt = now - self._step_t0
            self._step_times[self._step_name] = self._step_times.get(self._step_name, 0.0) + dt
            self.log_msg("  ✓ %s 用时 %.1f 秒" % (self._step_name, dt))
        self._step_name = name
        self._step_t0 = now
        self.log_msg("▶ %s（%s）" % (name, time.strftime("%H:%M:%S")))

    def on_prog(self, msg):
        self.log_msg(msg)
        up = msg.upper()
        if "区域" in msg and "支架范围" in msg:
            self.run_status = "正在导出 LBD 区域 / 支架范围…"
        elif "0/4" in msg:
            self.run_status = "正在生成 LBD / 支架标签…"
        elif "1/4" in msg or "连接" in msg or "启动" in msg:
            self.run_status = "正在连接 / 启动 ZWCAD…（可能需 10-30 秒，请切到 ZWCAD）"
        elif "2/4" in msg:
            self.run_status = "已连接 ZWCAD，正在打开 DWG…"
        elif "3/4" in msg:
            self.run_status = "DWG 就绪，正在加载插件并执行…"
        elif "START" in up:
            self.run_status = "开始执行…"
        elif "LAYOUT:" in up:
            m = re.search(r"count=(\d+)", msg)
            if m and not self.total:
                self.total = int(m.group(1))
            self.run_status = "正在批量布局…"
        elif "SAVED" in up:
            if not self.total:
                self.total = max(self.total, self.done_n + 1)
            self.done_n += 1
            self.run_status = "正在绘制… 已保存 %d 张" % self.done_n
        elif "STEP_SAVE" in up:
            self.run_status = "打印 / 导出…"
        elif "STEP_LBD" in up or "LBD_" in up:
            self.run_status = "识别 LBD 标签…"
        elif "REGION_DONE" in up:
            self.run_status = "区域对准完成，接着写 LBD 标签…"
        elif "REGION_FIT" in up:
            _m = re.search(r"REGION_FIT\s*(\d+)\s*(\d+)", msg)
            self.run_status = ("正在按 LBD 区域上下限对准视口 %s / %s" % (_m.group(1), _m.group(2))
                               if _m else "正在按 LBD 区域上下限对准视口…")
        elif "REGION_TOTAL" in up:
            self.run_status = "正在按 LBD 区域上下限对准视口…"
        elif "STOPPED" in up:
            # 用户点了「停止」：插件在检查点收尾，这里跟着收摊（要排在 DONE 前面，
            # 因为收尾消息是 STOPPED_DONE，也含 DONE）
            self._stopped = True
            self.run_status = "已停止"
            if self._poll_timer:
                self._poll_timer.stop()
        elif "DONE" in up:
            self.run_status = "完成"
            if self.total:
                self.done_n = max(self.done_n, self.total)
            elif self.done_n:
                self.total = self.done_n
        elif "ERROR" in up:
            self.run_status = "出错：" + msg
        self._step_switch(self._step_key_of(self.run_status))
        self.status_label.setText(self.run_status)
        if self.total > 0:
            if self._phase == "REGION":
                self.count_label.setText("已对准  %d / %d" % (self.done_n, self.total))
            else:
                self.count_label.setText("已绘制  %d / %d" % (self.done_n, self.total))
            self.pbar.setValue(int(round(min(1.0, self.done_n / float(self.total)) * 100)))
            pass                      # 进度方块已去掉，只保留进度条

    def on_status(self, msg):
        self.run_status = msg
        self.status_label.setText(msg)

    @staticmethod
    def _step_key_of(status):
        """把状态文字归成"哪一步"，用来计时（状态文字本身会一直变，不能直接当步名）。"""
        s = status or ""
        for k in ("连接 / 启动", "打开 DWG", "加载插件", "批量布局",
                  "区域 / 支架范围", "LBD / 支架标签", "绘制", "打印 / 导出", "完成"):
            if k in s:
                return k
        return s or "执行"

    def _log_run_times(self, title):
        """跑完/出错：把每一步的耗时和总时长写进日志。"""
        self._step_pause()
        if not self._run_started:
            return
        total = time.time() - self._run_started
        parts = ["%s %.1fs" % (k, v) for k, v in self._step_times.items() if v >= 0.05]
        self.log_msg("%s：总时长 %.1f 秒%s" % (title, total,
                                             ("（" + "、".join(parts) + "）") if parts else ""))
        self.log_msg("想调整识别结果（改框 / 改名 / 加框），点左下角「← 返回识别」或按 Ctrl+B，"
                     "改完再「下一步」回来；改过的地方都会保留。")
        if hasattr(self, "pause_btn"):
            self.pause_btn.setEnabled(False)
            self.pause_btn.setText(T("暂停"))
        self._paused = False
        try:
            os.remove(self._pause_flag_path())
        except Exception:
            pass
        try:
            os.remove(self._stop_flag_path())
        except Exception:
            pass
        if hasattr(self, "stop_btn"):
            self.stop_btn.setEnabled(False)

    def on_err(self, msg):
        if self._poll_timer:
            self._poll_timer.stop()
        self.status_label.setText("出错：" + msg)
        self.log_msg("执行出错：" + msg)
        self._log_run_times("执行结束（出错）")

    def on_done(self, msg):
        if self._poll_timer:
            self._poll_timer.stop()
        if not self.total and self.done_n:
            self.total = self.done_n
        if self.total:
            self.done_n = max(self.done_n, self.total)
            self.count_label.setText("已绘制  %d / %d" % (self.done_n, self.total))
            self.pbar.setValue(100)
            pass                      # 进度方块已去掉，只保留进度条
        self.log_msg("完成：" + msg)
        self._log_run_times("执行完成")

    def on_save_dwg(self):
        """跑完后由用户选保存位置，再把当前 CAD 图纸 SAVEAS 过去。"""
        cfg = self.cfg()
        dft_dir = (cfg.get("outputDir") or "").strip()
        if not dft_dir or not os.path.isdir(dft_dir):
            dft_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        name = (cfg.get("newName") or "").strip() or "MAP文件"
        if not name.lower().endswith(".dwg"):
            name += ".dwg"
        path, _ = QFileDialog.getSaveFileName(self, "选择保存位置", os.path.join(dft_dir, name),
                                              "DWG 文件 (*.dwg)")
        if not path:
            return
        if not path.lower().endswith(".dwg"):
            path += ".dwg"
        self.save_btn.setEnabled(False)
        self.save_btn.setText("正在保存…")
        self.finish_hint.setText("正在保存到：%s" % path)
        self.log_msg("正在保存到：%s" % path)
        threading.Thread(target=save_worker, args=(path, self.bus), daemon=True).start()

    def on_save_result(self, ok, msg):
        self.save_btn.setEnabled(True)
        if ok:
            self.save_btn.setText("再次另存…")
            self.finish_title.setText("已保存：%s" % msg)
            self.finish_hint.setText("需要换位置或改名字，点右边按钮再存一次")
            self.log_msg("已保存：" + msg)
        else:
            self.save_btn.setText("下载")
            self.finish_title.setText("保存失败")
            self.finish_hint.setText(msg)
            self.log_msg("保存失败：" + msg)

    # ---------------- 导出 PDF ----------------
    def on_export_pdf(self):
        """点「导出 PDF」：列出当前图纸的布局，勾选后一次打成一份多页 PDF。"""
        cfg = self.cfg()
        acad, msg = cad_connect()
        if not acad:
            QMessageBox.warning(self, "导出 PDF", msg or "连不上 CAD。")
            return
        doc = cad_doc_or_none(acad)
        if doc is None:
            QMessageBox.warning(self, "导出 PDF", "CAD 里没有打开的图纸。")
            return
        # 当前打开的是不是配置里的目标图纸？不是就先问一句，免的导错图
        try:
            cur = str(doc.FullName or "")
            want = (cfg.get("dwg") or "").strip()
            if (want and cur
                    and os.path.basename(cur).lower() != os.path.basename(want).lower()):
                if QMessageBox.question(
                        self, "导出 PDF",
                        "当前 CAD 里打开的是：\n%s\n\n和配置里的目标图纸不同：\n%s\n\n"
                        "仍要继续吗？" % (cur, want)) != QMessageBox.Yes:
                    return
        except Exception:
            pass
        layouts = cad_layout_names(doc)
        if not layouts:
            QMessageBox.warning(self, "导出 PDF", "这张图里没有可打印的布局。")
            return
        devices = cad_plot_devices(doc)
        if not devices:
            QMessageBox.warning(self, "导出 PDF",
                                "没读到 PDF 类打印设备。\n请确认 ZWCAD 里有 PDF 打印配置"
                                "（例如 DWG to PDF.pc5 / ZWPLOT_PDF.pc5）。")
            return
        default_dev = self._print_prefs.get("device")
        if default_dev not in devices:
            default_dev = next((d for d in devices if d.lower().startswith("dwg to pdf")), "")
        if not default_dev:
            default_dev = devices[0]
        out_dir = (self._print_prefs.get("dir") or cfg.get("outputDir")
                   or os.path.join(os.path.expanduser("~"), "Desktop"))
        fname = (cfg.get("newName") or "").strip() or "MAP文件"

        def media_provider(dev):
            return cad_plot_media(doc, dev)

        dlg = PrintDialog(self, layouts, self._generated_layouts, devices, default_dev,
                          media_provider, out_dir, fname, self._print_prefs)
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.data
        self._print_prefs["device"] = data["device"]
        self._print_prefs["dir"] = os.path.dirname(data["out_path"])
        self._print_prefs["quality"] = data["quality"]
        self._print_prefs["raster"] = data["raster"]
        self._print_prefs["open_after"] = data["open_after"]
        self.pdf_btn.setEnabled(False)
        self.pdf_btn.setText("正在导出…")
        self.content_stack.setCurrentIndex(1)
        self.status_label.setText("正在导出 PDF…")
        self.page_label.setText("一次打印全部 %d 个布局（质量 %s）"
                                % (len(data["layouts"]),
                                   quality_text(data["quality"], data["raster"])))
        self.pbar.setValue(0)
        self.log_msg("导出 PDF：设备 %s；质量 %s；布局 %d 个一次打 → %s"
                     % (data["device"], quality_text(data["quality"], data["raster"]),
                        len(data["layouts"]), data["out_path"]))
        threading.Thread(target=plot_worker,
                         args=(data["layouts"], data["device"], data["media"],
                               data["out_path"], self.bus),
                         kwargs={"quality": data["quality"], "raster": data["raster"],
                                 "open_after": data["open_after"]},
                         daemon=True).start()

    def on_plot_prog(self, done_n, total):
        self.status_label.setText("正在导出 PDF %d / %d" % (done_n, total))
        if not total:
            return
        if done_n <= 0 and total > 1:
            self.pbar.setRange(0, 0)              # 一次打一批：先转圈，等 CAD 出结果
            return
        if self.pbar.maximum() == 0:
            self.pbar.setRange(0, 100)
        self.pbar.setValue(int(round(min(1.0, done_n / float(total)) * 100)))

    def on_plot_result(self, ok, msg):
        self.pbar.setRange(0, 100)
        self.pdf_btn.setEnabled(True)
        self.pdf_btn.setText("再次导出…" if ok else "导出 PDF")
        if ok:
            self.pbar.setValue(100)
            self.status_label.setText("PDF 已导出")
            self.page_label.setText(msg)
            self.finish_title.setText("PDF 已导出")
            self.finish_hint.setText(msg)
            self.log_msg("PDF 已导出：" + msg)
        else:
            self.status_label.setText("导出 PDF 失败")
            self.page_label.setText(msg)
            self.log_msg("导出 PDF 失败：" + msg)
            QMessageBox.warning(self, "导出 PDF", msg)

    # ---------------- 在线更新 ----------------
    def on_upd_click(self):
        if self._upd_install:
            self.start_update_download()
        else:
            self.on_check_update()

    def on_check_update(self, silent=False):
        self._upd_silent = bool(silent)
        if not silent:
            self.upd_label.setFixedWidth(190)
            self.upd_label.setText("正在检查更新…")
        self.upd_btn.setEnabled(False)
        self._upd_install = False
        threading.Thread(target=update_check_worker, args=(self.bus,), daemon=True).start()

    def on_show_notes(self):
        self.upd_label.setText("正在读取更新日志…")
        self.notes_btn.setEnabled(False)
        threading.Thread(target=update_notes_worker, args=(self.bus,), daemon=True).start()

    def on_upd_found(self, tag, notes, url, published):
        self.upd_btn.setEnabled(True)
        self._upd_url = url
        self._upd_tag = tag
        self._upd_install = True
        self.upd_btn.setToolTip("下载并安装 %s" % tag)
        self.upd_label.setText("发现新版 %s" % tag)
        self.log_msg("== 发现新版本 %s（当前 v%s%s）==" % (
            tag, APP_VERSION, ("，%s 发布" % published) if published else ""))
        if notes:
            self.log_msg(notes[:2000])
        if not url:
            self.log_msg("该版本没有可下载的 exe 附件，请打开：%s" % UPDATE_PAGE)
        if self._upd_silent:
            # 启动时的自动检查：只在顶部栏提示，不弹窗（避免和手动「检查更新」弹两次）
            self.log_msg("（启动自动检查发现新版，点顶部栏「下载并安装 %s」即可；" 
                         "想看说明点「更新日志」）" % tag)
            return
        dlg = UpdateDialog(tag, notes, published, "update", self)
        dlg.exec()
        if dlg.chosen != "download":
            return
        if not url:
            QMessageBox.information(self, "没有附件",
                                    "这个版本没有 exe 附件，请到发布页下载：\n%s" % UPDATE_PAGE)
            return
        self.start_update_download()

    def on_upd_none(self, tag, notes, published):
        self.upd_btn.setEnabled(True)
        self.upd_btn.setToolTip(T("检查更新"))
        self._upd_install = False
        self.upd_label.setText("已是最新 v%s" % APP_VERSION)
        self.log_msg("检查更新：已是最新（远端 %s%s）" % (
            tag, ("，%s 发布" % published) if published else ""))
        if notes and not self._upd_silent:
            self.log_msg(notes[:2000])
        QTimer.singleShot(4000, lambda: self.upd_label.setText(""))

    def on_upd_notes(self, version, notes, published, newer):
        self.notes_btn.setEnabled(True)
        self.upd_label.setText("")
        if not version:
            QMessageBox.information(self, "更新日志", "仓库里还没有发布过任何版本。")
            return
        self.log_msg("更新日志 %s%s%s" % (
            version, ("（%s 发布）" % published) if published else "",
            "（有新版本）" if newer else "（与当前版本相同或更旧）"))
        dlg = UpdateDialog(version, notes, published, "log", self)
        dlg.exec()

    def on_upd_error(self, msg):
        self.upd_btn.setEnabled(True)
        if not self._upd_install:
            self.upd_btn.setToolTip(T("检查更新"))
        self.upd_label.setFixedWidth(190)
        self.upd_label.setText("检查更新失败")
        self.log_msg(msg)
        QTimer.singleShot(6000, lambda: self.upd_label.setText(""))

    def start_update_download(self):
        if not self._upd_url:
            self.log_msg("没有可下载的更新地址，请到发布页手工下载：%s" % UPDATE_PAGE)
            return
        self.upd_btn.setEnabled(False)
        self.upd_btn.setToolTip(T("正在下载…"))
        self._upd_pct = 0
        self._upd_detail = ""
        self._upd_logged = -1
        self._render_upd_progress()
        self.log_msg("开始下载更新 %s…" % self._upd_tag)
        threading.Thread(target=update_download_worker,
                         args=(self._upd_url, self.bus), daemon=True).start()

    def on_upd_progress(self, pct):
        self._upd_pct = pct
        self._render_upd_progress()
        if pct and pct % 10 == 0 and pct != self._upd_logged:
            self._upd_logged = pct
            self.log_msg("下载更新 %d%%%s"
                         % (pct, ("　" + self._upd_detail) if self._upd_detail else ""))

    def on_upd_detail(self, text):
        self._upd_detail = text or ""
        self._render_upd_progress()

    def on_upd_log(self, text):
        self.log_msg(text)

    def _render_upd_progress(self):
        """头部那行：百分比 + 已下/总大小 + 速度（没有明细时只显示百分比）。"""
        pct = getattr(self, "_upd_pct", 0)
        det = getattr(self, "_upd_detail", "")
        self.upd_label.setFixedWidth(360)      # 下载时放开宽度，放得下大小和速度
        self.upd_label.setText(("正在下载 %3d%%" % pct) + ("　" + det if det else ""))

    def on_upd_ready(self, path):
        self.upd_label.setFixedWidth(190)
        self.upd_label.setText("下载完成")
        self.upd_btn.setEnabled(True)
        ok, msg = apply_update(path)
        if not ok:
            self.upd_btn.setToolTip(T("检查更新"))
            self.log_msg(msg)
            QMessageBox.warning(self, "无法自动更新", msg)
            return
        self.log_msg("更新包已就绪：%s" % path)
        QMessageBox.information(self, "更新就绪",
                                "新版本已下载完成。\n点确定后程序会关闭，几秒内自动替换并重新打开"
                                "（替换过程在后台进行，不会弹黑窗口）。")
        self.log_msg("正在退出以便替换程序…")
        QApplication.quit()

    def _poll_prog(self):
        p = getattr(self, "_prog_path", None)
        if not p or not os.path.exists(p):
            return
        try:
            txt = open(p, encoding="utf-8", errors="replace").read()
        except Exception:
            return
        newpart = txt[getattr(self, "_prog_len", 0):]
        if newpart.strip():
            for line in newpart.splitlines():
                if line.strip():
                    self.log_msg(line)
            self._prog_len = len(txt)
        up = txt.upper()
        # ── 阶段推进 ────────────────────────────────────────────────
        # CAD 侧写完的进度行（创建 k/n、REGION_FIT、LBD_TOTAL…）会一直留在 prog 文件里，
        # 每 150ms 轮询都会重新匹配到，所以：
        #   1) 阶段只往前推进，绝不往回跳（否则界面上会看到进度条被拉回上一阶段、小字乱跳）；
        #   2) 每个阶段各记自己的 done/total，显示时只用当前阶段这两个数；
        #   3) 计时汇总只写一次日志（以前每轮询一次就写一行，日志会被刷屏）。
        _PH = ("LAYOUT", "REGION", "LBD", "AI")

        def _advance(ph):
            try:
                if _PH.index(ph) >= _PH.index(getattr(self, "_phase", "") or "LAYOUT"):
                    self._phase = ph
            except ValueError:
                self._phase = ph

        # 1) 创建布局
        m = re.search(r"LAYOUT:\s*count=(\d+)", txt)
        if m:
            _advance("LAYOUT")
            self._lay_total = max(int(getattr(self, "_lay_total", 0)), int(m.group(1)))
        lay = re.findall(r"创建\s*(\d+)\s*/\s*(\d+)", txt)
        if lay:
            _advance("LAYOUT")
            self._lay_done = int(lay[-1][0])
            self._lay_total = max(int(getattr(self, "_lay_total", 0)), int(lay[-1][1]))
        _saved = len(re.findall(r"SAVED", up))
        if _saved:
            _advance("LAYOUT")
            self._lay_done = _saved
        # 2) 区域对准（按 LBD 区域上下限调底图大小）
        #   REGION_TOTAL n / REGION_FIT k n 对准数 ms=... / REGION_DONE k n
        rg_total = re.findall(r"REGION_TOTAL\s*(\d+)", txt)
        if rg_total:
            _advance("REGION")
            self._reg_total = int(rg_total[-1])
            if not getattr(self, "_region_seen", 0):
                self._region_times = []
        rg_fit = re.findall(r"REGION_FIT\s*(\d+)\s*(\d+)(?:\s+\d+)?(?:\s+ms=(\d+))?", txt)
        if rg_fit:
            _advance("REGION")
            self._reg_done = int(rg_fit[-1][0])
            self._reg_total = max(int(getattr(self, "_reg_total", 0)), int(rg_fit[-1][1]))
            if len(rg_fit) > getattr(self, "_region_seen", 0):     # 计时只收新增的行
                for _row in rg_fit[getattr(self, "_region_seen", 0):]:
                    if _row[2]:
                        try:
                            self._region_times.append(int(_row[2]) / 1000.0)
                        except ValueError:
                            pass
                self._region_seen = len(rg_fit)
        if "REGION_DONE" in up and not getattr(self, "_region_logged", False):
            self._region_logged = True
            _rt = getattr(self, "_region_times", None) or []
            if _rt:
                self.log_msg("区域对准用时：共 %d 个布局、合计 %.1f 秒（平均 %.2f 秒/个）"
                             % (len(_rt), sum(_rt), sum(_rt) / len(_rt)))
        # 3) LBD 标签 / 4) STR 号
        if "STEP_LBD" in up:
            _advance("LBD")
        lbd_total = re.findall(r"LBD_TOTAL\s*(\d+)", txt)
        if lbd_total:
            _advance("LBD")
            self._lbd_total = int(lbd_total[-1])
        lbd_done = re.findall(r"LBD_LABEL\s*(\d+)", txt)
        if lbd_done:
            _advance("LBD")
            self._lbd_done = int(lbd_done[-1])
        ai_total = re.findall(r"AI_TOTAL\s*(\d+)", txt)
        if ai_total:
            _advance("AI")
            self._ai_total = int(ai_total[-1])
        ai_done = re.findall(r"AI_LABEL\s*(\d+)", txt)
        if ai_done:
            _advance("AI")
            self._ai_done = int(ai_done[-1])
        # 按页进度：LBD_PAGE <第几张> <总数> filled=<这一页填了几个> ms=<这一页用了多少毫秒>
        #           AI_PAGE  <第几张> <总数>
        # 每页收尾时记一行日志，并在状态页显示「第 N 页 填了 X 个，用时 Y 秒」。
        for tag in ("LBD", "AI"):
            arr = re.findall(tag + r"_PAGE\s*(\d+)(?:\s+(\d+))?"
                                   r"(?:\s+filled=(\d+))?(?:\s+ms=(\d+))?", txt)
            if not arr:
                continue
            pg_no, pg_tot, pg_filled, pg_ms = arr[-1]
            if getattr(self, "_pg_seen", None) is None:
                self._pg_seen, self._pg_ts, self._pg_times, self._pg_txt = {}, {}, [], {}
            page_key = tag + "_" + pg_no
            if page_key not in self._pg_seen:
                self._pg_seen[page_key] = True
                dt = None
                if pg_ms:
                    try:
                        dt = int(pg_ms) / 1000.0
                    except ValueError:
                        dt = None
                if dt is None:                      # 老插件不给 ms：用两页之间的间隔估
                    prev = self._pg_ts.get(tag)
                    dt = (time.time() - prev) if prev else None
                if dt:
                    self._pg_times.append((tag, pg_no, dt))
                if tag == "LBD":
                    txt_pg = "第 %s%s 页 填了 %s 个%s" % (
                        pg_no, ("/" + pg_tot) if pg_tot else "",
                        pg_filled if pg_filled is not None else "—",
                        ("，用时 %.1f 秒" % dt) if dt else "")
                    self._pg_txt[tag] = "LBD 标签：" + txt_pg
                    self.log_msg("LBD 标签进度：" + txt_pg)
                else:
                    self._pg_txt[tag] = "STR 号：第 %s%s 张图纸" % (
                        pg_no, ("/" + pg_tot) if pg_tot else "")
            self._pg_ts[tag] = time.time()
            if hasattr(self, "page_label"):
                self.page_label.setText("按页进度 ｜ " + " ｜ ".join(
                    t for t in (self._pg_txt.get("LBD"), self._pg_txt.get("AI")) if t))
        # 当前阶段自己的 done/total：只用这两个数画进度条，别的阶段完成到多少都不影响
        # 注意：CAD 还没报任何阶段进度时 _phase 是空的（这时还在连接/打开 DWG），
        # 这种"空阶段"**不能**当成 LAYOUT —— 否则每 150ms 就会把状态文字写成
        # "正在批量布局…"，把"正在连接 / 启动 ZWCAD…"顶掉，界面上看着就是一直跳。
        _ph = getattr(self, "_phase", "")
        if _ph:
            self.done_n, self.total = {
                "REGION": (getattr(self, "_reg_done", 0), getattr(self, "_reg_total", 0)),
                "LBD": (getattr(self, "_lbd_done", 0), getattr(self, "_lbd_total", 0)),
                "AI": (getattr(self, "_ai_done", 0), getattr(self, "_ai_total", 0)),
            }.get(_ph, (getattr(self, "_lay_done", 0), getattr(self, "_lay_total", 0)))
            if self.total:
                self.done_n = min(self.done_n, self.total)
                self.run_status = {
                    "REGION": "正在按 LBD 区域上下限对准视口 %d / %d",
                    "LBD": "正在写 LBD 标签 %d / %d",
                    "AI": "正在画 STR 号 %d / %d",
                }.get(_ph, "正在批量布局… 已创建 %d / %d 个") % (self.done_n, self.total)
            else:
                self.run_status = {
                    "REGION": "正在按 LBD 区域上下限对准视口…",
                    "LBD": "正在写 LBD 标签…",
                    "AI": "正在画 STR 号…",
                }.get(_ph, "正在批量布局…")
                # 这一阶段还没报总数（刚切过来）：别把上一阶段"已对准 12 / 12"留在下面
                if hasattr(self, "count_label"):
                    self.count_label.setText(("已对准  ? / ?" if _ph == "REGION"
                                              else "已绘制  ? / ?"))
        if "STEP_SAVE" in up:
            self.run_status = "打印 / 导出…"
        finished = False
        # 完成标记：CAD 侧在最后一步（AI 画完 STR）之后写 RUN_DONE
        run_done = "RUN_DONE" in up
        hard_err = ("ERROR: SheetNamesMissing" in txt
                    or "ERROR: TemplateLayoutMissing" in txt
                    or "LBD extract failed" in up)
        if run_done:
            self.run_status = "完成"
            if self.total:
                self.done_n = max(self.done_n, self.total)
            finished = True
            if not self._finish_ready:
                self._finish_ready = True
                _times = [(t2, p2, d2) for (t2, p2, d2) in getattr(self, "_pg_times", []) if d2 > 0.2]
                if _times:
                    _slow = sorted(_times, key=lambda x: -x[2])[:5]
                    _nm = {"LBD": "LBD 标签", "AI": "STR 号"}
                    self.log_msg("每页耗时：共记录 %d 页；最慢 5 页 %s"
                                 % (len(_times), "、".join("%s 第%s页 %.1fs" % (_nm.get(t2, t2), p2, d2)
                                                        for t2, p2, d2 in _slow)))
                self.save_btn.setEnabled(True)
                self.save_btn.setText("下载")
                self.pdf_btn.setEnabled(True)
                self.pdf_btn.setText("导出 PDF")
                self.finish_title.setText("执行完成，共 %d 个布局 —— 请选择保存位置"
                                          % (self.total or self.done_n or 0))
                self.finish_hint.setText("「下载」= 连到 CAD 用 SAVEAS 存 DWG；"
                                         "「导出 PDF」= 勾选布局，一次打成一份多页 PDF（质量可调）"
                                         "（此时 STR 号也已画好，会一起进去）")
        elif hard_err:
            self.run_status = "出错：" + (txt.strip()[-200:])
            finished = True
        self.status_label.setText(self.run_status)
        if self.total > 0:
            if self._phase == "REGION":
                self.count_label.setText("已对准  %d / %d" % (self.done_n, self.total))
            else:
                self.count_label.setText("已绘制  %d / %d" % (self.done_n, self.total))
            self.pbar.setValue(int(round(min(1.0, self.done_n / float(self.total)) * 100)))
            pass                      # 进度方块已去掉，只保留进度条
        if finished:
            if self._poll_timer:
                self._poll_timer.stop()


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    ico = find_icon()
    if ico:
        app.setWindowIcon(QIcon(ico))
    w = MainWindow()
    if ico:
        w.setWindowIcon(QIcon(ico))
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
