# -*- coding: utf-8 -*-
# Voltage-CAD MAP · PDF 半自动流程编排器（PySide6/Qt 界面）
# 业务逻辑（扫描/计划/配置/ZWCAD 自动化）与旧 ctypes 版保持一致。
import os, sys, json, re, glob, hashlib, tempfile, threading, time, subprocess, shutil
import urllib.request, urllib.error, urllib.parse
from PySide6.QtCore import Qt, Signal, QObject, QTimer
from PySide6.QtGui import QColor, QPainter, QIcon, QPixmap
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QProgressBar, QStackedWidget,
                               QScrollArea, QFileDialog, QButtonGroup, QPlainTextEdit,
                               QFrame, QGridLayout, QCheckBox, QRadioButton, QComboBox,
                               QMessageBox, QDialog, QListWidget, QListWidgetItem)
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
                             lbd_label_boxes as _lr_lbd_boxes)
except Exception:                    # 模块缺失时不阻塞主程序
    _lr_candidates = _lr_json_kind = _lr_extract_debug = None
    _lr_write_regions = _lr_write_regions_sheets = None
    _lr_preview = _LR_ORDER_LABELS = None
    _LR_QUAD_DEFAULTS = _lr_quad_preview = _lr_quad_note = None
    _lr_parse_quad_map = None
    _LR_ORDER_TEXT = _lr_demo_cells = None
    _lr_rack_lines = _lr_page_map = None
    _lr_rack_types = _lr_rack_text = _lr_set_hints = None
    _lr_lbd_boxes = None

APP_TITLE = "Voltage-CAD MAP"
APP_VERSION = "2.51"
UPDATE_REPO = "cszmw2k6dk-design/CAD-MAP"
UPDATE_ASSET = "Voltage-CAD MAP.exe"
UPDATE_API = "https://api.github.com/repos/%s/releases/latest" % UPDATE_REPO
UPDATE_PAGE = "https://github.com/%s/releases" % UPDATE_REPO
FIELDS = [
    ("dwg", "模板 DWG 文件"),
    ("pdf", "PDF 文件路径"), ("xlsx", "LBD 名称 Excel"), ("jsonPath", "识别结果 JSON文件"),
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
    ("rackAvoid", "避开 LBD 标签(底图+CAD)"),
    ("rackTypes", "支架类型"), ("rackSplit", "拆不拆"), ("rackStringLen", "单串长度(FT)"),
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
    "rackTypes": "", "rackSplit": "不拆", "rackStringLen": "",
    "rackAuto": True, "rackSplitByType": "",
    "strBgOn": "1", "strBgColor": "2", "strTextColor": "7", "strBgGap": "1.0",
    "overwrite": False, "labelWhere": "M", "filterCluster": True,
    "regionFit": True,
    "lbdFromRegion": True,
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
SECTIONS = [
    ("文件与输出", [("dwg", "模板 DWG 文件"),
                  ("pdf", "PDF 文件路径"), ("xlsx", "LBD 名称 Excel"),
                  ("jsonPath", "识别结果 JSON文件"),
                  ("newName", "新文件名(可空)")]),
    # PDF：底图从哪几页来、怎么对准视口
    ("PDF", [("pageStart", "起始页"), ("pageEnd", "结束页(0=全部)"),
             ("importPages", "导入页码(0=全部)"),
             ("count", "复制数量(0=按识别)"),
             ("margin", "视口边距(mm)"),
             ("regionInset", "区域对准留白(%)")]),
    # 标签：LBD 标签长什么样 + STR 号按哪个方向填（四象限规则原来在「支架」页，挪到这里）
    ("标签", [("textHeight", "标签高度(模型单位, 0=自动)"), ("labelBgColor", "标签背景色"),
             ("labelTextColor", "LBD 标签字色"),
             ("labelBgGap", "背景遮挡间隙(倍)"),
             ("strQuadOn", "按汇流箱(Box)四象限规律命名"),
             ("strQuadI", "象限 I 右上 的顺序"),
             ("strQuadII", "象限 II 左上 的顺序"),
             ("strQuadIII", "象限 III 左下 的顺序"),
             ("strQuadIV", "象限 IV 右下 的顺序")]),
    ("支架", [("rackPrefix", "命名前缀(支架号)"),
            ("rackTypes", "支架类型(串数:长度FT)"),
            ("rackSplit", "拆不拆"),
            ("rackStringLen", "单串长度(FT,可空)"),
            ("strHeight", "STR 字高(typical宽倍数)"),
            ("strOrder", "STR 编号顺序(8 种)"),
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


def _pdf_rotate(page):
    """页面的 /Rotate（度，取 0/90/180/270）。"""
    try:
        return int(page.get("/Rotate", 0) or 0) % 360
    except Exception:
        return 0


def _pdf_page_size(page):
    """这一页「渲染出来」的宽高（带 /Rotate 时和 MediaBox 是反的）。"""
    try:
        mb = page.mediabox
        pw = abs(float(mb.right) - float(mb.left))
        ph = abs(float(mb.top) - float(mb.bottom))
    except Exception:
        pw, ph = 1.0, 1.0
    if _pdf_rotate(page) % 180 == 90:
        pw, ph = ph, pw
    return (pw or 1.0), (ph or 1.0)


def _pdf_norm_pt(page, x, y):
    """PDF 用户坐标 -> 底图（渲染图）上的归一化坐标 (fx, fy)，fy 从下往上。

    ★ 关键：PDF 带 /Rotate 时，文字层坐标是「没转过的」用户空间，而 CAD 里的 PDF
    底图是「转过之后」渲染出来的，两者差 90°/270°。不换算的话避让框会整片跑到
    错误位置（实测 HIGHLAND 那套图纸是 /Rotate=270：不换算命中 10/34，换算后 34/34）。
    """
    try:
        cb = page.cropbox
        x0, y0 = float(cb.left), float(cb.bottom)
        pw = float(cb.right) - x0
        ph = float(cb.top) - y0
    except Exception:
        x0, y0, pw, ph = 0.0, 0.0, 1.0, 1.0
    if pw <= 0:
        pw = 1.0
    if ph <= 0:
        ph = 1.0
    x = float(x) - x0
    y = float(y) - y0
    rot = _pdf_rotate(page)
    if rot == 90:                       # 顺时针转 90° 显示
        return (y / ph, (pw - x) / pw)
    if rot == 180:
        return ((pw - x) / pw, (ph - y) / ph)
    if rot == 270:                      # 逆时针转 90° 显示
        return ((ph - y) / ph, x / pw)
    return (x / pw, y / ph)


def _pdf_text_items(page):
    """一页 PDF -> (文字块列表, 整页文字)。

    文字块 = (文字, fx中心, fy中心, fy标签下沿, fx1, fy1, fx2, fy2)，已经是
    **底图（渲染图）上的归一化坐标**：fx 从左往右、fy 从下往上。
    fy标签下沿 = 文字框下沿再往下 15%（LBD 标签原来就画在那儿）；
    fx1..fy2 是整个文字框，避让算碰撞用。
    """
    items = []
    all_text = []

    def visit_text(text, cm, tm, font, size):
        if not text:
            return
        all_text.append(text)
        try:
            m0 = cm[0] * tm[0] + cm[2] * tm[1]
            m1 = cm[1] * tm[0] + cm[3] * tm[1]
            m2 = cm[0] * tm[2] + cm[2] * tm[3]
            m3 = cm[1] * tm[2] + cm[3] * tm[3]
            m4 = cm[0] * tm[4] + cm[2] * tm[5] + cm[4]
            m5 = cm[1] * tm[4] + cm[3] * tm[5] + cm[5]
        except Exception:
            m0, m1, m2, m3, m4, m5 = 1.0, 0.0, 0.0, 1.0, 0.0, 0.0
        try:
            cs = float(size)
        except Exception:
            cs = 0.0
        w = cs * 0.5 * len(text)
        h = cs
        xs, ys = [], []
        for tx, ty in ((0.0, 0.0), (w, 0.0), (0.0, h), (w, h)):
            xs.append(m0 * tx + m2 * ty + m4)
            ys.append(m1 * tx + m3 * ty + m5)
        cx = (min(xs) + max(xs)) * 0.5
        cy = (min(ys) + max(ys)) * 0.5
        # 四个角都换算成底图坐标再取包围盒（转过 90° 的页，框的宽高会互换）
        pts = [_pdf_norm_pt(page, px, py)
               for px, py in ((min(xs), min(ys)), (max(xs), min(ys)),
                              (min(xs), max(ys)), (max(xs), max(ys)))]
        fx1, fx2 = min(p[0] for p in pts), max(p[0] for p in pts)
        fy1, fy2 = min(p[1] for p in pts), max(p[1] for p in pts)
        fc = _pdf_norm_pt(page, cx, cy)
        # 「标签下沿」按底图方向往下 15%（转过 90° 时不能再用 PDF 的 y 下沿）
        items.append((text, fc[0], fc[1], fy1 - (fy2 - fy1) * 0.15,
                      fx1, fy1, fx2, fy2))

    page.extract_text(visitor_text=visit_text)
    return items, all_text


def extract_lbd(pdf, out, pageStart, pageEnd, prog=None, page_map=None):
    # 等价于 pdf_extract.py：就地用已打包的 pypdf 提取 LBD 标签坐标，
    # 写出的 P/L 制表符格式与 LSP 的 PdfLayout_ReadExtractFile 期望一致。
    # page_map: {PDF 真实页号: 图纸顺序号}；给了就按它重编号，映射里没有的页整页跳过
    #           （CAD 侧是按「第几张底图」当页号的，不是 PDF 页码）。
    # 返回 (ok, err)。
    try:
        from pypdf import PdfReader
    except Exception as e:
        return False, "pypdf 不可用：%s" % e
    if not pdf or not os.path.exists(pdf):
        return False, "PDF 文件不存在：%s" % pdf
    try:
        reader = PdfReader(pdf)
        n = len(reader.pages)
    except Exception as e:
        return False, "打开 PDF 失败：%s" % e
    try:
        p0 = int(pageStart or 1)
        p1 = int(pageEnd or 0)
    except Exception:
        p0, p1 = 1, 0
    if p0 < 1:
        p0 = 1
    if p1 <= 0:
        p1 = n
    if p1 > n:
        p1 = n
    lines = []
    for idx in range(p0 - 1, p1):
        page = reader.pages[idx]
        pw, ph = _pdf_page_size(page)
        try:
            items, all_text = _pdf_text_items(page)
        except Exception:
            items, all_text = [], []
        pg_out = idx + 1 if page_map is None else page_map.get(idx + 1)
        if pg_out is None:
            continue                       # 这一页不在识别到的图纸页里（封面/说明页等）
        title = "".join(all_text[:100])
        lines.append("P\t%d\t%.2f\t%.2f\t%s"
                     % (pg_out, pw, ph, title[:150].replace("\t", " ").replace("\n", " ")))
        for it in items:
            if "LBD" not in it[0].upper():
                continue
            # it[1] = 文字中心 fx，it[3] = 标签下沿 fy（底图坐标，已按 /Rotate 换算）
            fx, fy = it[1], it[3]
            if not (-0.05 <= fx <= 1.05 and -0.05 <= fy <= 1.05):
                continue                   # 跑到页面外的杂项文字
            fx = min(max(fx, 0.0), 1.0)
            fy = min(max(fy, 0.0), 1.0)
            lines.append("L\t%d\t%.6f\t%.6f\t%s"
                         % (pg_out, fx, fy, it[0].replace("\t", " ").replace("\n", " ")))
        if prog:
            try:
                with open(prog, "w", encoding="utf-8") as f:
                    f.write("PAGE %d/%d" % (idx + 1, n))
            except Exception:
                pass
    try:
        with open(out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception as e:
        return False, "写提取文件失败：%s" % e
    return True, ""


def pdf_lbd_boxes(pdf, pageStart, pageEnd, page_map=None, want="LBD"):
    """PDF 文字层里含 want 的文字框 -> {图纸页号: [(fx1, fy1, fx2, fy2), ...]}。

    归一化坐标（fx 从左、fy 从下往上，和 L 行的 fx/fy 同一套）。用来让生成的 STR 号
    避开底图上本来就印着的 LBD 标号（文字盖文字）。没有 PDF 或没有文字层就返回 {}。
    """
    out = {}
    if not pdf or not os.path.exists(pdf):
        return out
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf)
        n = len(reader.pages)
    except Exception:
        return out
    try:
        p0 = int(pageStart or 1)
        p1 = int(pageEnd or 0)
    except Exception:
        p0, p1 = 1, 0
    if p0 < 1:
        p0 = 1
    if p1 <= 0 or p1 > n:
        p1 = n
    # 有 page_map 时只翻"识别到的图纸页"：整份 PDF 可能上百页，全翻一遍要等很久
    if page_map:
        todo = sorted(p for p in page_map if p0 <= p <= p1)
    else:
        todo = list(range(p0, p1 + 1))
    for pgno in todo:
        page = reader.pages[pgno - 1]
        pg_out = pgno if page_map is None else page_map.get(pgno)
        if pg_out is None:
            continue                     # 不在识别到的图纸页里（封面/说明页）
        try:
            items, _t = _pdf_text_items(page)
        except Exception:
            continue
        boxes = []
        for (text, _fx, _fy, _fyl, fx1, fy1, fx2, fy2) in items:
            if want.upper() not in text.upper():
                continue
            if fx2 < 0.0 or fx1 > 1.0 or fy2 < 0.0 or fy1 > 1.0:
                continue
            boxes.append((max(0.0, fx1), max(0.0, fy1),
                          min(1.0, fx2), min(1.0, fy2)))
        if boxes:
            out.setdefault(pg_out, []).extend(boxes)
    return out


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
    """日志里那句"避开了多少处 LBD 标签"（分底图文字 / CAD 里画的）。"""
    if not detail:
        return ""
    n = int(detail.get("avoid") or 0)
    nc = int(detail.get("avoid_cad") or 0)
    if not n:
        return ""
    s = "；已避开 LBD 标签 %d 处" % n
    if nc:
        s += "（其中 CAD 里画的 %d 处）" % nc
    return s


def build_extract_file(cfg, out_path, prog_path=None):
    """生成 CAD 读的标签提取文件（P/L 行）。返回 (ok, 说明, 明细)。

    按手上有什么自动选：
      1) 标注/编号结果 JSON（X-AnyLabeling，有 shapes）：LBD 名称和支架号都在里面，直接转；
      2) 识别结果 debug JSON（有 Node/Tracker 框，但没有 LBD 文字的坐标）：
         LBD 行仍由 Python 从 **PDF 文字层**提取（老流程 pdf_extract.py 那套，exe 里内置），
         支架号 STRxx 由 debug JSON 按 LBD 分组现编，追加到同一个文件里；
      3) 没给 JSON / 给的不顶用：退回纯 PDF 文字层提取（只有 LBD 行）。
    """
    jp = (cfg.get("jsonPath") or "").strip()
    pdf = (cfg.get("pdf") or "").strip()
    try:
        p0 = int(cfg.get("pageStart") or 1)
    except Exception:
        p0 = 1
    try:
        p1 = int(cfg.get("importPages") or 0) or int(cfg.get("pageEnd") or 0)
    except Exception:
        p1 = 0
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
    detail = {"kind": "", "lbd": 0, "str": 0, "pdf_lbd": False}

    def _count(prefix):
        try:
            with open(out_path, "r", encoding="utf-8") as f:
                return sum(1 for ln in f if ln.startswith(prefix))
        except Exception:
            return 0

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

    # STR 号要避开的障碍（带背景填充的号压上去会把名字盖掉）：
    # 底图上本来就印着的 LBD 标号 —— 直接用 PDF 文字层的框（位置是实测的，准）。
    # 我们自己画的 LBD 标签不在这里预估了：它的字高在模型单位里是「标签高度」，
    # 换算成页像素要底图模型尺寸（这里没有），而且 CAD 画的时候还有"上下错行"，
    # 预估出来的框不准（老代码 scale=0 时甚至塌成 0 尺寸的一个点）。
    # 改成：CAD 画完 STR 号之后，由标签自己上下让位（真实包围盒判定），
    # 见 PdfLayout_auto.lsp 的 PdfLayout_LbdPlace。
    avoid = None
    _avoid_pad = 0.0        # 关掉避让时也要有值：下面几条输出路径都会用到它
    detail["avoid"] = 0
    detail["avoid_cad"] = 0
    if (kind == "debug"
            and str(cfg.get("rackAvoid", "1")).strip() not in ("0", "", "关", "否", "off", "false", "False")):
        boxes = {}
        if pdf and os.path.exists(pdf):
            try:
                boxes = pdf_lbd_boxes(pdf, p0, p1, pgmap)
            except Exception:
                boxes = {}
        avoid = boxes or None
        detail["avoid"] = sum(len(v) for v in (boxes or {}).values())
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
    if (kind == "debug" and cfg.get("lbdFromRegion", True)
            and _lr_extract_debug is not None):
        try:
            r = _lr_extract_debug(jp, out_path, prefix=pre, page_map=pgmap,
                                  order=order, split=split, align=align, avoid=avoid,
                                  avoid_pad=_avoid_pad,
                                  quad_rule=quad_rule, quad_map=quad_map)
        except Exception as e:
            r = {"ok": False, "error": str(e)}
        if r.get("ok") and r["lbd"]:
            detail.update(lbd=r["lbd"], str=r["str"], pos="region")
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

    # 3) LBD 行：Python 从 PDF 文字层提（位置=图纸上 LBD 文字的正下方）—— 老行为 / 关掉开关时走这条
    pdf_err = ""
    if pdf and os.path.exists(pdf):
        ok, err = extract_lbd(pdf, out_path, p0, p1, prog=prog_path, page_map=pgmap)
        if ok:
            detail["pdf_lbd"] = True
            detail["lbd"] = _count("L\t")
        else:
            pdf_err = err

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

    # 兜底：PDF 文字层没给出 LBD 行（无文字层的扫描件等），用 debug JSON 的区域中心
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
            _stip = ("；" + detail["split"]) if detail.get("split") else ""
            if _lr_quad_note:
                _stip += _lr_quad_note(detail["quad"])
            _stip += avoid_note(detail)
            return True, ("识别结果 JSON：%d 页、LBD %d 个（按区域中心）、支架号 %d 个"
                          "（PDF 文字层没读到 LBD 文字，位置按区域中心放）%s"
                          % (r["pages"], r["lbd"], r["str"], _stip)), detail
        pdf_err = pdf_err or (r.get("error") or "")

    if detail["lbd"] == 0 and detail["str"] == 0:
        why = pdf_err or rack_err or ("这份 JSON 不是识别结果，也不是标注结果（没有 Node/Tracker 也没有 shapes）"
                                      if jp else "没有 PDF、也没有识别结果 JSON")
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
    return True, ("标签 %d 行：LBD %d 个（Python 从 PDF 文字层识别）"
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
            return out, ("区域对准：按分表顺序 %d 个布局，%d 个匹配到 LBD 区域%s"
                         " → 生成布局后按区域上下限调视口大小"
                         % (r["pages"], r["with_region"],
                            ("（%d 个分表没匹配到，按整页对准）" % len(r.get("miss") or []))
                            if r.get("miss") else ""))
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
    返回 (布局名列表, 说明文字)。读不到分表名时返回空列表。"""
    sheets = read_xlsx_sheet_names(cfg.get("xlsx"))
    if not sheets:
        return [], "读不到分表名：请先在“文件与输出”里选择 LBD 名称 Excel(xlsx)"
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
        # B2：PDF 提取在 exe 内就地完成（复用已打包的 pypdf），不再外挂 Python。
        lbd_pre = str(cfg.get("lbdPre", "0"))
        lbd_out = (cfg.get("lbdOut") or "").strip()
        if lbd_pre == "1" and lbd_out:
            bus.prog.emit("0/4 正在提取 PDF LBD 标签…")
            pdf = (cfg.get("pdf") or "").strip()
            logp = os.path.join(tempfile.gettempdir(), "pdflbd_log.txt")
            try:
                p0 = int(cfg.get("pageStart") or 1)
                ipp = int(cfg.get("importPages") or 0)
                p1 = int(cfg.get("pageEnd") or 0)
            except Exception:
                p0, ipp, p1 = 1, 0, 0
            pg_end = ipp if ipp > 0 else p1
            progx = os.path.join(tempfile.gettempdir(), "pdflbd_progress.txt")
            _jp = (cfg.get("jsonPath") or "").strip()
            if _jp and os.path.exists(_jp):
                try:
                    bus.prog.emit("0/4 读取识别结果 JSON…")
                    _hn = rack_len_hint_note(cfg)
                    if _hn:
                        bus.prog.emit("0/4 支架类型长度FT：" + _hn)
                    bus.prog.emit("0/4 正在生成标签（LBD 文字从 PDF 里识别，支架号按 LBD 分组编号）…")
                    ok, _emsg, _edet = build_extract_file(cfg, lbd_out, progx)
                    bus.prog.emit("0/4 " + _emsg)
                    err = "" if ok else _emsg
                except Exception as e:
                    ok, err = False, "JSON解析失败:" + str(e)
            else:
                # 没有识别结果 JSON：退回 PDF 文字层提取（「使用AI自动识别」那个选项已删掉，
                # 识别现在统一在外部工具里做，结果以 debug JSON 的形式给进来）
                ok, err = extract_lbd(pdf, lbd_out, p0, pg_end, prog=progx)
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


def plot_worker(layouts, device, media_canon, out_path, bus):
    """把勾选的布局逐张打印成 PDF，再合并成一个多页 PDF；中间文件用完就删。"""
    pythoncom = None
    tmpdir = None
    notes = []
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
            old_tab = doc.GetVariable("CTAB")
        except Exception:
            old_tab = None
        # 该设备的纸型清单（"随布局页面设置" 时用来找同规格纸型）
        dev_media = [canon for _lab, canon in cad_plot_media(doc, device)]

        tmpdir = tempfile.mkdtemp(prefix="vcad_pdf_")
        total = len(layouts)
        outs = []
        for i, name in enumerate(layouts, 1):
            bus.plot_prog.emit(i - 1, total)
            doc.SetVariable("CTAB", name)
            lay = doc.ActiveLayout
            try:
                old_media = str(lay.CanonicalMediaName or "")
            except Exception:
                old_media = ""
            try:
                lay.ConfigName = device
            except Exception as e:
                raise RuntimeError("切换到打印设备「%s」失败：%s" % (device, e))
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
            out_i = os.path.join(tmpdir, "%04d.pdf" % i)
            plot_one_to_file(plot, device, out_i)
            if not os.path.exists(out_i) or os.path.getsize(out_i) <= 0:
                raise RuntimeError("布局「%s」没有生成 PDF（设备 %s）。" % (name, device))
            outs.append(out_i)
            bus.plot_prog.emit(i, total)

        writer = PdfWriter()
        for p in outs:
            writer.append(p)
        part = out_path + ".part"
        with open(part, "wb") as f:
            writer.write(f)
        os.replace(part, out_path)
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
        bus.plot_result.emit(False, msg)
        return
    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)
        if pythoncom is not None:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
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
            later = QPushButton("稍后")
            later.clicked.connect(self.reject)
            row.addWidget(later)
            go = QPushButton("下载并安装")
            go.setObjectName("Primary")
            go.clicked.connect(self._on_go)
            row.addWidget(go)
        else:
            close = QPushButton("关闭")
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
        # 格子尺寸按可用面积算，能缩就缩：格子多的时候整片都画得下（以前是固定下限，
        # 行/列一多就顶出控件、下半截看不见）
        cw = max(9.0, min(96.0, float(w) / self.cols))
        chh = max(9.0, min(44.0, float(h) / self.rows))
        ox = pad + max(0, int((w - cw * self.cols) / 2.0))
        oy = pad + head + max(0, int((h - chh * self.rows) / 2.0))
        p.setPen(QColor("#39424e"))
        p.drawText(pad, 2, self.width() - 2 * pad, head, Qt.AlignLeft | Qt.AlignVCenter,
                   "STR 顺序预览：%s" % self.hint)

        def cell(i):
            it = self.items[i]
            return (ox + it[1] * cw, oy + it[2] * chh, max(6.0, cw - gap),
                    max(6.0, chh - gap))

        pts = []
        for i in range(len(self.items)):
            x, y, w2, h2 = cell(i)
            pts.append((int(x + w2 / 2.0), int(y + h2 / 2.0)))
        p.setPen(QColor("#b9c6d6"))
        for i in range(1, len(pts)):
            p.drawLine(pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1])
        for i, it in enumerate(self.items):
            x, y, w2, h2 = cell(i)
            if i == 0:
                p.setBrush(QColor("#d6f5d6"))
                p.setPen(QColor("#2e8b57"))
            elif i == len(self.items) - 1:
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
    """导出 PDF：勾选要打印的布局 + 选打印设备 / 纸型 + 选输出位置。"""

    def __init__(self, parent, layouts, prechecked, devices, default_device,
                 media_provider, out_dir, file_name):
        super().__init__(parent)
        self.setWindowTitle("导出 PDF")
        self.setMinimumWidth(580)
        self._media_provider = media_provider
        self._media_cache = {}
        self.data = {}

        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 16)
        v.setSpacing(12)

        title = QLabel("导出 PDF")
        title.setObjectName("PageTitle")
        v.addWidget(title)
        sub = QLabel("勾选要打印的布局；会按列表顺序逐张打印，最后合成一个多页 PDF。")
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
        self._reload_media()
        self._sync_hint()

    # ---- 内部 ----
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
        self.hint.setText("输出：%s（先逐张打印到临时文件，合并成功后临时文件自动删掉）" % where)
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
        if self.media.count() <= 1:
            self.hint.setText(self.hint.text() +
                              "\n（没读到这个设备的纸型清单，将按图纸原来的纸型打印）")

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
        self._build_ui()
        self.set_cfg(load_config())
        # 起始页/结束页 失焦或按回车时，按范围自动算出“复制数量”（不逐字触发，避免卡输入）
        for _k in ("pageStart", "pageEnd"):
            _w = self.edits.get(_k)
            if _w:
                _w.editingFinished.connect(self._recalc_count_from_range)
        self.setWindowTitle("%s v%s" % (APP_TITLE, APP_VERSION))
        self.resize(1120, 720)
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
        ver.setFixedWidth(58)
        ver.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        hl.addWidget(ver)
        hl.addSpacing(8)
        self.upd_btn = QPushButton("检查更新")
        self.upd_btn.setObjectName("UpdBtn")
        self.upd_btn.setFixedHeight(28)
        self.upd_btn.setFixedWidth(160)            # 「检查更新 / 下载并安装 v2.17.1 / 正在下载…」宽度一致
        self.upd_btn.clicked.connect(self.on_upd_click)
        hl.addWidget(self.upd_btn)
        self.notes_btn = QPushButton("更新日志")
        self.notes_btn.setObjectName("UpdBtn")
        self.notes_btn.setFixedHeight(28)
        self.notes_btn.setFixedWidth(88)
        self.notes_btn.clicked.connect(self.on_show_notes)
        hl.addWidget(self.notes_btn)
        root.addWidget(header)
        # 主体：侧边栏 + 内容
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())
        self.content_stack = QStackedWidget()
        self.section_stack = QStackedWidget()
        for s_i, (sec_title, keys) in enumerate(SECTIONS):
            self.section_stack.addWidget(self._build_section_page(s_i, sec_title, keys))
        self.content_stack.addWidget(self.section_stack)   # 0 = 表单
        self.content_stack.addWidget(self._build_status_page())  # 1 = 执行状态
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
        actions.addStretch(1)
        b = QPushButton("执行输出")
        b.setObjectName("Primary")
        b.clicked.connect(self.on_run)
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
        sb.setFixedWidth(230)
        v = QVBoxLayout(sb)
        v.setContentsMargins(14, 18, 14, 18)
        v.setSpacing(6)
        logo = self._logo_label(72)
        v.addWidget(logo)
        v.addSpacing(20)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        for i, (sec_title, _) in enumerate(SECTIONS):
            b = QPushButton(sec_title)
            b.setObjectName("Nav")
            b.setCheckable(True)
            b.setFixedHeight(44)
            b.clicked.connect(lambda _=False, idx=i: self.show_section(idx))
            self.nav_group.addButton(b, i)
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
        h = QLabel(sec_title)
        h.setObjectName("PageTitle")
        outer.addWidget(h)
        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        rack_panel = None
        label_panel = None
        if sec_title == "选项":
            r = 0
            for key, txt, init in [("overwrite", "覆盖同名布局", False),
                                   ("filterCluster", "排除集中干扰标号", True),
                                   ("regionFit", "生成布局后按 LBD 区域上下限对准视口", True),
                                   ("lbdFromRegion", "LBD 标签按识别到的区域位置填（不勾=按 PDF 里的 LBD 文字位置）", True),
                                   ("rackAuto", "支架类型自动读识别结果(免手填)", True)]:
                cb = QCheckBox(txt)
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
                    sub = QLabel("STR 编号方向 · 按汇流箱(Box)四象限规矩")
                    sub.setObjectName("FieldLabel")
                    form.addWidget(sub, r, 0, 1, 2)
                    r += 1
                lb = QLabel(label)
                lb.setObjectName("FieldLabel")
                form.addWidget(lb, r, 0)
                if key in ("strBgColor", "strTextColor", "labelBgColor", "labelTextColor"):
                    cb = NoWheelCombo()
                    cb.setObjectName("Field")
                    cb.setMinimumWidth(320)
                    for cname, aci in COLOR_CHOICES:
                        cb.addItem(cname, aci)
                    self.combo[key] = cb
                    form.addWidget(cb, r, 1)
                elif key in ("strOrder",) + tuple(k for k, _t in QUAD_FIELDS):
                    cb = NoWheelCombo()
                    cb.setObjectName("Field")
                    cb.setMinimumWidth(320)
                    if key == "strOrder":
                        for label, val in STR_ORDER_CHOICES:
                            cb.addItem(label, val)
                    else:
                        # 象限下拉：第一项是「0 = 这个象限不改」，其余就是 8 种顺序
                        cb.addItem("0 用全局顺序（该象限不改）", "0")
                        for label, val in STR_ORDER_CHOICES:
                            cb.addItem(label, val)
                    self.combo[key] = cb
                    cb.currentIndexChanged.connect(lambda *_: self.on_refresh_str_preview())
                    cb.currentIndexChanged.connect(lambda *_: self.on_refresh_quad_preview())
                    form.addWidget(cb, r, 1)

                elif key in ("strBgOn", "rackAlign", "rackAvoid"):
                    cb = NoWheelCombo()
                    cb.setObjectName("Field")
                    cb.setMinimumWidth(320)
                    cb.addItem("开", "1")
                    cb.addItem("关", "0")
                    self.combo[key] = cb
                    form.addWidget(cb, r, 1)
                elif key == "strQuadOn":
                    cb = NoWheelCombo()
                    cb.setObjectName("Field")
                    cb.setMinimumWidth(320)
                    cb.addItem("开：按四象限规律命名", "1")
                    cb.addItem("关：一律按「支架」页的全局顺序", "0")
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
                        bb = QPushButton("选择")
                        bb.clicked.connect(lambda _=False, k=key: self.browse(k))
                        form.addWidget(bb, r, 2)
                r += 1
                if key == "strQuadIV":
                    _qh = QLabel(
                        "开关关掉时四个下拉全部不生效（一律按「支架」页的全局顺序）；开着时判据是："
                        "原点 = 本页汇流箱(Box)的几何中心，看这个 LBD 区域中心的方位"
                        "（u 右为正、v 上为正）——I 右上 / II 左上 / III 左下 / IV 右下；"
                        "离原点太近（死区）、或这页没有汇流箱时，用全局顺序。"
                        "改完看下面的「象限预览」——四个小图就是四个象限里的真实样例，"
                        "换一个顺序，号立刻就换位置。")
                    _qh.setObjectName("Hint")
                    _qh.setWordWrap(True)
                    form.addWidget(_qh, r, 0, 1, 2)
                    r += 1
            if sec_title == "标签":
                label_panel = self._build_label_panel()
            elif sec_title == "支架":
                rack_panel = self._build_rack_panel()
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

    def _build_rack_panel(self):
        """支架类型明细：每个支架类型单独一行；类型自动来自识别结果，拆不拆手工选。"""
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 10, 0, 0)
        v.setSpacing(6)
        t = QLabel("支架类型明细")
        t.setObjectName("Hint")
        t.setWordWrap(True)
        v.addWidget(t)
        self.rack_grid = QGridLayout()
        self.rack_grid.setHorizontalSpacing(16)
        self.rack_grid.setVerticalSpacing(6)
        v.addLayout(self.rack_grid)
        hb = QHBoxLayout()
        hb.setSpacing(8)
        self.rack_refresh_btn = QPushButton("从识别结果刷新支架类型")
        self.rack_refresh_btn.clicked.connect(self.on_refresh_rack_types)
        hb.addWidget(self.rack_refresh_btn)
        hb.addStretch(1)
        v.addLayout(hb)
        # STR 编号顺序预览（按当前顺序给一个 LBD 组内的支架编号）
        ph = QHBoxLayout()
        ph.setSpacing(8)
        self.str_preview_btn = QPushButton("刷新 STR 顺序预览")
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
        self.quad_preview_btn = QPushButton("刷新象限预览")
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
        for key, le, cb in self.rack_rows:
            txt = le.text().strip()
            if txt:
                self._rack_len_pref[key] = txt
            else:
                self._rack_len_pref.pop(key, None)
            self._rack_split_pref[key] = cb.currentText()

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
        for col, head in enumerate(("支架类型", "串数", "长度FT", "数量", "拆不拆")):
            lb = QLabel(head)
            lb.setObjectName("FieldLabel")
            self.rack_grid.addWidget(lb, 0, col)
        if not types:
            empty = QLabel("（还没读到识别结果：指定「识别结果 JSON文件」或跑一次「执行输出」后，这里会自动列出）")
            empty.setObjectName("Hint")
            empty.setWordWrap(True)
            self.rack_grid.addWidget(empty, 1, 0, 1, 5)
            return
        for i, tp in enumerate(types):
            key = str(tp.get("strings"))
            name = QLabel(tp.get("code") or ("%s 串" % key))
            self.rack_grid.addWidget(name, i + 1, 0)
            num = QLabel(key)
            self.rack_grid.addWidget(num, i + 1, 1)
            le = QLineEdit()
            le.setObjectName("Field")
            le.setMinimumWidth(110)
            le.setPlaceholderText("长度FT")
            pref = self._rack_len_pref.get(key)
            if pref:
                le.setText(pref)
            elif tp.get("length_ft"):
                le.setText("%g" % tp["length_ft"])
            self.rack_grid.addWidget(le, i + 1, 2)
            cnt = tp.get("total_count")
            cl = QLabel(str(cnt) if cnt is not None else "—")
            self.rack_grid.addWidget(cl, i + 1, 3)
            cb = NoWheelCombo()
            cb.setObjectName("Field")
            cb.setMinimumWidth(90)
            for opt in ("不拆", "2行", "3行"):
                cb.addItem(opt, opt)
            want = self._rack_split_pref.get(key, "不拆")
            idx = cb.findData(want)
            cb.setCurrentIndex(idx if idx >= 0 else 0)
            self.rack_grid.addWidget(cb, i + 1, 4)
            self.rack_rows.append((key, le, cb))

    def _rack_types_current(self):
        return list(self._rack_types or [])

    def rack_row_values(self):
        return [(k, le.text().strip(), cb.currentText()) for k, le, cb in self.rack_rows]

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
            self.bus.strprev.emit({"hint": "查找识别结果出错：%s" % e})
            return
        if not cands:
            self.bus.strprev.emit({"hint": "没找到识别结果 JSON：请先在上面选「识别结果 JSON文件」"})
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
        self.finish_title = QLabel("生成完成后，点右下角「下载」选择保存位置")
        self.finish_title.setObjectName("FinishTitle")
        self.finish_hint = QLabel("不会再自动保存到“默认保存目录”，选完路径才写文件")
        self.finish_hint.setObjectName("Hint")
        self.finish_hint.setWordWrap(True)
        fcol.addWidget(self.finish_title)
        fcol.addWidget(self.finish_hint)
        fv.addLayout(fcol, 1)
        self.save_btn = QPushButton("下载")
        self.save_btn.setObjectName("Primary")
        self.save_btn.setFixedHeight(38)
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.on_save_dwg)
        self.pdf_btn = QPushButton("导出 PDF")
        self.pdf_btn.setFixedHeight(38)
        self.pdf_btn.setEnabled(False)
        self.pdf_btn.clicked.connect(self.on_export_pdf)
        fv.addWidget(self.pdf_btn)
        fv.addWidget(self.save_btn)
        v.addWidget(fin)
        return page

    def show_section(self, idx):
        self.run_active = False
        self.section_stack.setCurrentIndex(idx)
        self.content_stack.setCurrentIndex(0)

    def get_text(self, key):
        w = self.edits.get(key)
        return w.text().strip() if w else ""

    def set_text(self, key, value):
        w = self.edits.get(key)
        if w:
            w.setText(value or "")

    def cfg(self):
        c = {}
        for k, _ in FIELDS:
            c[k] = self.combo[k].currentData() if k in self.combo else self.get_text(k)
        # 模板布局名 / 底图标记名固定用默认值（界面不再给填）：留空 = 自动取第一个带视口的布局
        c["templateLayout"] = DEFAULTS["templateLayout"]
        c["filter"] = DEFAULTS["filter"]
        c["overwrite"] = self.checkbox["overwrite"].isChecked()
        c["filterCluster"] = self.checkbox["filterCluster"].isChecked()
        c["regionFit"] = self.checkbox["regionFit"].isChecked()
        c["lbdFromRegion"] = self.checkbox["lbdFromRegion"].isChecked()
        c["rackAuto"] = self.checkbox["rackAuto"].isChecked()
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
        self.checkbox["overwrite"].setChecked(bool(c.get("overwrite")))
        self.checkbox["filterCluster"].setChecked(bool(c.get("filterCluster")))
        self.checkbox["regionFit"].setChecked(bool(c.get("regionFit", True)))
        self.checkbox["lbdFromRegion"].setChecked(bool(c.get("lbdFromRegion", True)))
        self.checkbox["rackAuto"].setChecked(bool(c.get("rackAuto", True)))
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
                    self._rack_split_pref[_k.strip()] = _v.strip()
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
        # B2：若配置了 PDF，让 exe 就地提取 LBD 标签，并把结果路径/开关交给 LSP。
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
        if self._poll_timer:
            self._poll_timer.stop()
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_prog)
        self._poll_timer.start(150)
        threading.Thread(target=auto_worker, args=(cfg, ini, prog, self.bus), daemon=True).start()

    def on_prog(self, msg):
        self.log_msg(msg)
        up = msg.upper()
        if "区域" in msg and "支架范围" in msg:
            self.run_status = "正在导出 LBD 区域 / 支架范围…"
        elif "0/4" in msg:
            self.run_status = "正在提取 PDF LBD 标签…"
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
        elif "DONE" in up:
            self.run_status = "完成"
            if self.total:
                self.done_n = max(self.done_n, self.total)
            elif self.done_n:
                self.total = self.done_n
        elif "ERROR" in up:
            self.run_status = "出错：" + msg
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

    def on_err(self, msg):
        if self._poll_timer:
            self._poll_timer.stop()
        self.status_label.setText("出错：" + msg)
        self.log_msg("执行出错：" + msg)

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
        """点「导出 PDF」：列出当前图纸的布局，勾选后逐张打印并合并成一个 PDF。"""
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
                          media_provider, out_dir, fname)
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.data
        self._print_prefs["device"] = data["device"]
        self._print_prefs["dir"] = os.path.dirname(data["out_path"])
        self.pdf_btn.setEnabled(False)
        self.pdf_btn.setText("正在导出…")
        self.content_stack.setCurrentIndex(1)
        self.status_label.setText("正在导出 PDF…")
        self.page_label.setText("逐张打印布局，全部打完再合并成一个 PDF")
        self.pbar.setValue(0)
        self.log_msg("导出 PDF：设备 %s；布局 %d 个 → %s"
                     % (data["device"], len(data["layouts"]), data["out_path"]))
        threading.Thread(target=plot_worker,
                         args=(data["layouts"], data["device"], data["media"],
                               data["out_path"], self.bus), daemon=True).start()

    def on_plot_prog(self, done_n, total):
        self.status_label.setText("正在导出 PDF %d / %d" % (done_n, total))
        self.page_label.setText("正在打印布局 %d / %d（打完再合并）" % (done_n, total))
        if total:
            self.pbar.setValue(int(round(min(1.0, done_n / float(total)) * 100)))

    def on_plot_result(self, ok, msg):
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
        self.upd_btn.setText("下载并安装 %s" % tag)
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
        self.upd_btn.setText("检查更新")
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
            self.upd_btn.setText("检查更新")
        self.upd_label.setFixedWidth(190)
        self.upd_label.setText("检查更新失败")
        self.log_msg(msg)
        QTimer.singleShot(6000, lambda: self.upd_label.setText(""))

    def start_update_download(self):
        if not self._upd_url:
            self.log_msg("没有可下载的更新地址，请到发布页手工下载：%s" % UPDATE_PAGE)
            return
        self.upd_btn.setEnabled(False)
        self.upd_btn.setText("正在下载…")
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
            self.upd_btn.setText("检查更新")
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
                                         "「导出 PDF」= 勾选布局打印成 PDF 并合并成一个文件"
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
