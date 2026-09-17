# -*- coding: utf-8 -*-
# Voltage-CAD MAP · PDF 半自动流程编排器（PySide6/Qt 界面）
# 业务逻辑（扫描/计划/配置/ZWCAD 自动化）与旧 ctypes 版保持一致。
import os, sys, json, re, tempfile, threading, time, subprocess, shutil
import urllib.request, urllib.error
from PySide6.QtCore import Qt, Signal, QObject, QTimer
from PySide6.QtGui import QColor, QPainter, QIcon, QPixmap
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QProgressBar, QStackedWidget,
                               QScrollArea, QFileDialog, QButtonGroup, QPlainTextEdit,
                               QFrame, QGridLayout, QCheckBox, QRadioButton, QComboBox,
                               QMessageBox, QDialog)
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
                             rack_types_text as _lr_rack_text,
                             set_rack_len_hints as _lr_set_hints)
except Exception:                    # 模块缺失时不阻塞主程序
    _lr_candidates = _lr_json_kind = _lr_extract_debug = None
    _lr_write_regions = _lr_write_regions_sheets = None
    _lr_preview = _LR_ORDER_LABELS = None
    _lr_rack_lines = _lr_page_map = None
    _lr_rack_types = _lr_rack_text = _lr_set_hints = None

APP_TITLE = "Voltage-CAD MAP"
APP_VERSION = "2.20"
UPDATE_REPO = "cszmw2k6dk-design/CAD-MAP"
UPDATE_ASSET = "Voltage-CAD MAP.exe"
UPDATE_API = "https://api.github.com/repos/%s/releases/latest" % UPDATE_REPO
UPDATE_PAGE = "https://github.com/%s/releases" % UPDATE_REPO
FIELDS = [
    ("dwg", "目标 DWG 文件"),
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
    ("rackAlign", "STR 号自动对齐"),
    ("rackAvoid", "避开底图 LBD 标号"),
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
    "rackAlign": "1",
    "rackAvoid": "1",
    "rackTypes": "", "rackSplit": "不拆", "rackStringLen": "",
    "rackAuto": True, "rackSplitByType": "",
    "strBgOn": "1", "strBgColor": "2", "strTextColor": "7", "strBgGap": "1.0",
    "lockViewport": False, "overwrite": False, "labelWhere": "M", "filterCluster": True,
    "regionFit": True,
    "lbdFromRegion": True,
    "useAI": False,
    "aiPython": r"C:\Users\szk\Desktop\MAP-CAD\_pyinstaller_tool\python\python.exe",
    "aiScript": r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\run_detect.py",
    "aiModel": r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\runs\frames\weights\best.pt",
    "aiOutdir": r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\output_run",
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

COLOR_CHOICES = [("红", "1"), ("黄", "2"), ("绿", "3"), ("青", "4"),
                 ("蓝", "5"), ("洋红", "6"), ("白", "7"), ("灰", "8")]
SECTIONS = [
    ("文件与输出", [("dwg", "目标 DWG 文件"),
                  ("pdf", "PDF 文件路径"), ("xlsx", "LBD 名称 Excel"),
                  ("jsonPath", "识别结果 JSON文件"),
                  ("newName", "新文件名(可空)")]),
    ("PDF 与标签", [("pageStart", "起始页"), ("pageEnd", "结束页(0=全部)"),
                  ("importPages", "导入页码(0=全部)"),
                  ("count", "复制数量(0=按识别)"),
                  ("textHeight", "标签高度(模型单位, 0=自动)"), ("labelBgColor", "标签背景色"),
                  ("labelTextColor", "LBD 标签字色"),
                  ("labelBgGap", "背景遮挡间隙(倍)"),
                  ("margin", "视口边距(mm)"),
                  ("regionInset", "区域对准留白(%)")]),
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
    cand = os.path.join(app_dir(), "config.json")
    try:
        open(cand, "a").close()
        return cand
    except Exception:
        home = os.path.join(os.path.expanduser("~"), ".pdflayout_编排器")
        os.makedirs(home, exist_ok=True)
        return os.path.join(home, "config.json")


def load_config():
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = {}
    out = dict(DEFAULTS)
    out.update({k: v for k, v in d.items() if k in DEFAULTS})
    return out


def save_config(c):
    with open(config_path(), "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=2)


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


def _pdf_text_items(page):
    """一页 PDF -> (文字块列表, 整页文字)。文字块 = (文字, cx, cy中心, cy下沿, x1,y1,x2,y2)。

    坐标系是 PDF 自己的（原点左下、y 向上）。cy下沿 是老口径（框下沿再往上 15%），
    LBD 标签原来就画在那儿；x1..y2 是整个文字框，避让算碰撞用。
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
        cyb = min(ys) - (max(ys) - min(ys)) * 0.15
        items.append((text, cx, cy, cyb, min(xs), min(ys), max(xs), max(ys)))

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
            cx, cy = it[1], it[3]
            if cx < x0 or cy < y0 or cx > x0 + pw or cy > y0 + ph:
                continue
            fx = (cx - x0) / pw
            fy = (cy - y0) / ph
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
    for idx in range(p0 - 1, p1):
        page = reader.pages[idx]
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
        pg_out = idx + 1 if page_map is None else page_map.get(idx + 1)
        if pg_out is None:
            continue                     # 不在识别到的图纸页里（封面/说明页）
        try:
            items, _t = _pdf_text_items(page)
        except Exception:
            continue
        boxes = []
        for (text, _cx, _cy, _cyb, x1, y1, x2, y2) in items:
            if want.upper() not in text.upper():
                continue
            boxes.append(((x1 - x0) / pw, (y1 - y0) / ph,
                          (x2 - x0) / pw, (y2 - y0) / ph))
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

    # 底图上原有的 LBD 标号位置（PDF 文字层）：STR 号要避开它们，别用背景框盖住底图文字。
    avoid = None
    if (kind == "debug" and pdf and os.path.exists(pdf)
            and str(cfg.get("rackAvoid", "1")).strip() not in ("0", "", "关", "否", "off", "false", "False")):
        try:
            avoid = pdf_lbd_boxes(pdf, p0, p1, pgmap)
        except Exception:
            avoid = None
        detail["avoid"] = sum(len(v) for v in (avoid or {}).values())
    else:
        detail["avoid"] = 0

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
                                  order=order, split=split, align=align, avoid=avoid)
        except Exception as e:
            r = {"ok": False, "error": str(e)}
        if r.get("ok") and r["lbd"]:
            detail.update(lbd=r["lbd"], str=r["str"], pos="region")
            detail["split"] = r.get("split") or ""
            _tip = ""
            if pgmap:
                _pgs = sorted(pgmap)
                _tip = ("；识别到 %d 页图纸（PDF 第 %d~%d 页），已按底图顺序重编号 1~%d"
                        % (len(pgmap), _pgs[0], _pgs[-1], len(pgmap)))
            if detail["split"]:
                _tip += "；" + detail["split"]
            if detail.get("avoid"):
                _tip += "；已避开底图 LBD 标号 %d 处（PDF 文字层）" % detail["avoid"]
            return True, ("识别结果：LBD %d 个（位置=识别到的 LBD 区域框中心）"
                          " + 支架号 %d 个（按 LBD 分组行优先编号）%s"
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
                                           split=split, info=_sinfo, align=align, avoid=avoid)
            detail["split"] = _sinfo.get("split") or ""
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
        r = _lr_extract_debug(jp, out_path, prefix=pre, order=order, split=split,
                              align=align, avoid=avoid)
        detail["split"] = r.get("split") or detail.get("split") or ""
        if r.get("ok"):
            detail["lbd"], detail["str"] = r["lbd"], r["str"]
            _stip = ("；" + detail["split"]) if detail.get("split") else ""
            if detail.get("avoid"):
                _stip += "；已避开底图 LBD 标号 %d 处" % detail["avoid"]
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
    if detail.get("avoid"):
        tip += "；已避开底图 LBD 标号 %d 处" % detail["avoid"]
    return True, ("标签 %d 行：LBD %d 个（Python 从 PDF 文字层识别）"
                  " + 支架号 %d 个（按 LBD 分组行优先编号）%s"
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
            elif str(cfg.get("useAI", "0")) in ("1", "True", "true"):
                ai_py = (cfg.get("aiPython") or "").strip()
                ai_script = (cfg.get("aiScript") or "").strip()
                ai_model = (cfg.get("aiModel") or "").strip()
                ai_out = (cfg.get("aiOutdir") or tempfile.gettempdir()).strip()
                if ai_py and ai_script and os.path.exists(ai_script):
                    cmd = [ai_py, ai_script, "--pdf", pdf, "--model", ai_model,
                           "--outdir", ai_out, "--start", str(p0), "--end", str(pg_end)]
                    try:
                        bus.prog.emit("0/4 正在AI自动识别(无需手动框)…")
                        subprocess.run(cmd, check=True, timeout=3600)
                        res = os.path.join(ai_out, "pdflbd_extract.txt")
                        if os.path.exists(res) and res != lbd_out:
                            shutil.copyfile(res, lbd_out)
                        ok, err = True, ""
                    except Exception as e:
                        ok, err = False, "AI识别失败:" + str(e)
                else:
                    ok, err = extract_lbd(pdf, lbd_out, p0, pg_end, prog=progx)
            else:
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
                   % (L(lsp), L(auto), L(ai), _vinsnip, L(_lbdout), _pg, _strbg, L(ini), L(prog)))
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


def download_file(url, dest, progress=None):
    """下载到 dest，progress(百分比) 回调可选。"""
    with http_get(url, timeout=120) as r:
        try:
            total = int(r.headers.get("Content-Length") or 0)
        except Exception:
            total = 0
        got = 0
        with open(dest, "wb") as f:
            while True:
                chunk = r.read(262144)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if progress and total:
                    progress(int(got * 100 / total))
    return dest


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
        if os.path.exists(dest):
            os.remove(dest)
        download_file(url, dest, progress=lambda p: bus.upd_progress.emit(p))
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
"""


class Bus(QObject):
    prog = Signal(str)
    err = Signal(str)
    done = Signal(str)
    status = Signal(str)
    racks = Signal(list)          # 支架类型明细（后台线程解析完推给界面）
    strprev = Signal(object)        # STR 顺序预览（后台线程 -> 界面）
    save_result = Signal(bool, str)
    upd_found = Signal(str, str, str, str)
    upd_none = Signal(str, str, str)
    upd_notes = Signal(str, str, str, bool)
    upd_error = Signal(str)
    upd_progress = Signal(int)
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
        cw = max(28, min(96, int(w / self.cols)))
        chh = max(20, min(44, int(h / self.rows)))
        ox = pad + max(0, int((w - cw * self.cols) / 2.0))
        oy = pad + head + max(0, int((h - chh * self.rows) / 2.0))
        p.setPen(QColor("#39424e"))
        p.drawText(pad, 2, self.width() - 2 * pad, head, Qt.AlignLeft | Qt.AlignVCenter,
                   "STR 顺序预览：%s" % self.hint)

        def cell(i):
            it = self.items[i]
            return (ox + it[1] * cw, oy + it[2] * chh, cw - gap, chh - gap)

        pts = []
        for i in range(len(self.items)):
            x, y, w2, h2 = cell(i)
            pts.append((x + w2 // 2, y + h2 // 2))
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
            p.drawRect(x, y, w2, h2)
            p.setPen(QColor("#33414f"))
            p.drawText(x, y, w2, h2, Qt.AlignCenter, it[0])



class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.bus = Bus()
        self.bus.prog.connect(self.on_prog)
        self.bus.racks.connect(self.on_rack_types)
        self.bus.strprev.connect(self.on_str_preview)
        self.bus.err.connect(self.on_err)
        self.bus.done.connect(self.on_done)
        self.bus.status.connect(self.on_status)
        self.bus.save_result.connect(self.on_save_result)
        self.bus.upd_found.connect(self.on_upd_found)
        self.bus.upd_none.connect(self.on_upd_none)
        self.bus.upd_notes.connect(self.on_upd_notes)
        self.bus.upd_error.connect(self.on_upd_error)
        self.bus.upd_progress.connect(self.on_upd_progress)
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
        self.total = 0
        self.done_n = 0
        self.run_status = ""
        self._prog_path = None
        self._prog_len = 0
        self._poll_timer = None
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
        b = QPushButton("执行输出")
        b.setObjectName("Primary")
        b.clicked.connect(self.on_run)
        actions.addWidget(b)
        actions.addStretch(1)
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
        if sec_title == "选项":
            r = 0
            for key, txt, init in [("lockViewport", "锁定视口显示", False),
                                   ("overwrite", "覆盖同名布局", False),
                                   ("filterCluster", "排除集中干扰标号", True),
                                   ("useAI", "使用AI自动识别(无需手动框)", False),
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
        elif sec_title == "支架":
            # 支架类型 + 拆不拆：每类支架可以选 不拆 / 2行 / 3行；
            # 选了几行，这个支架框就沿长边均分成几行，每行各一个 STR 号；
            # 号按上面的「STR 编号顺序」在整个 LBD 区域里走一个顺序，不是同一张支架连号。
            # 哪一列属于哪一类，按框长比例对「长度FT」（见 lbd_regions.rack_type_indices）。
            r = 0
            for key, label in keys:
                lb = QLabel(label)
                lb.setObjectName("FieldLabel")
                form.addWidget(lb, r, 0)
                if key in ("strBgColor", "strTextColor"):
                    cb = NoWheelCombo()
                    cb.setObjectName("Field")
                    cb.setMinimumWidth(320)
                    for cname, aci in COLOR_CHOICES:
                        cb.addItem(cname, aci)
                    self.combo[key] = cb
                    form.addWidget(cb, r, 1)
                elif key == "strOrder":
                    cb = NoWheelCombo()
                    cb.setObjectName("Field")
                    cb.setMinimumWidth(320)
                    for label, val in STR_ORDER_CHOICES:
                        cb.addItem(label, val)
                    self.combo[key] = cb
                    cb.currentIndexChanged.connect(lambda *_: self.on_refresh_str_preview())
                    form.addWidget(cb, r, 1)

                elif key in ("strBgOn", "rackAlign", "rackAvoid"):
                    cb = NoWheelCombo()
                    cb.setObjectName("Field")
                    cb.setMinimumWidth(320)
                    cb.addItem("开", "1")
                    cb.addItem("关", "0")
                    self.combo[key] = cb
                    form.addWidget(cb, r, 1)
                else:
                    edit = QLineEdit()
                    edit.setObjectName("Field")
                    edit.setMinimumWidth(320)
                    self.edits[key] = edit
                    form.addWidget(edit, r, 1)
                r += 1
            rack_panel = self._build_rack_panel()
        else:
            for row, (key, label) in enumerate(keys):
                lb = QLabel(label)
                lb.setObjectName("FieldLabel")
                form.addWidget(lb, row, 0)
                if key in ("labelBgColor", "labelTextColor"):
                    cb = NoWheelCombo()
                    cb.setObjectName("Field")
                    cb.setMinimumWidth(320)
                    for name, aci in COLOR_CHOICES:
                        cb.addItem(name, aci)
                    self.combo[key] = cb
                    form.addWidget(cb, row, 1)
                    continue
                edit = QLineEdit()
                edit.setObjectName("Field")
                edit.setMinimumWidth(320)
                self.edits[key] = edit
                form.addWidget(edit, row, 1)
                if key in BROWSE_KEYS:
                    bb = QPushButton("选择")
                    bb.clicked.connect(lambda _=False, k=key: self.browse(k))
                    form.addWidget(bb, row, 2)
        outer.addLayout(form)
        if rack_panel is not None:
            outer.addWidget(rack_panel)
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
        apply_rack_len_hints(cfg)          # 明细行的长度FT -> 判支架类型（拆分要用）
        split = rack_split_spec(cfg)
        for jp in cands:
            try:
                d = _lr_preview(jp, order=order, split=split)
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
        c["lockViewport"] = self.checkbox["lockViewport"].isChecked()
        c["overwrite"] = self.checkbox["overwrite"].isChecked()
        c["filterCluster"] = self.checkbox["filterCluster"].isChecked()
        c["useAI"] = self.checkbox["useAI"].isChecked()
        c["regionFit"] = self.checkbox["regionFit"].isChecked()
        c["lbdFromRegion"] = self.checkbox["lbdFromRegion"].isChecked()
        c["rackAuto"] = self.checkbox["rackAuto"].isChecked()
        c["labelWhere"] = "M"          # 固定模型空间（界面不再给「当前布局」选项）
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
        self.checkbox["lockViewport"].setChecked(bool(c.get("lockViewport")))
        self.checkbox["overwrite"].setChecked(bool(c.get("overwrite")))
        self.checkbox["filterCluster"].setChecked(bool(c.get("filterCluster")))
        self.checkbox["useAI"].setChecked(bool(c.get("useAI")))
        self.checkbox["regionFit"].setChecked(bool(c.get("regionFit", True)))
        self.checkbox["lbdFromRegion"].setChecked(bool(c.get("lbdFromRegion", True)))
        self.checkbox["rackAuto"].setChecked(bool(c.get("rackAuto", True)))
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
        """关窗口时把界面上的配置存下来（原来靠底部「保存配置」按钮，按钮已去掉）。"""
        try:
            save_config(self.cfg())
        except Exception:
            pass
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
        self.save_btn.setEnabled(False)
        self.save_btn.setText("下载")
        self.finish_title.setText("生成完成后，点右下角「下载」选择保存位置")
        self.finish_hint.setText("不会再自动保存到“默认保存目录”，选完路径才写文件")
        # 读取配置里的 AI 自动识别参数
        try:
            _d = load_config()
            for _k in ("aiPython", "aiScript", "aiModel", "aiOutdir", "regionOut"):
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

    # ---------------- 在线更新 ----------------
    def on_upd_click(self):
        if self._upd_install:
            self.start_update_download()
        else:
            self.on_check_update()

    def on_check_update(self, silent=False):
        self._upd_silent = bool(silent)
        if not silent:
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
        self.upd_label.setText("检查更新失败")
        self.log_msg(msg)
        QTimer.singleShot(6000, lambda: self.upd_label.setText(""))

    def start_update_download(self):
        if not self._upd_url:
            self.log_msg("没有可下载的更新地址，请到发布页手工下载：%s" % UPDATE_PAGE)
            return
        self.upd_btn.setEnabled(False)
        self.upd_btn.setText("正在下载…")
        self.upd_label.setText("正在下载 0%")
        self.log_msg("开始下载更新 %s…" % self._upd_tag)
        threading.Thread(target=update_download_worker,
                         args=(self._upd_url, self.bus), daemon=True).start()

    def on_upd_progress(self, pct):
        self.upd_label.setText("正在下载 %3d%%" % pct)   # 补空格，位数固定，不会左右跳
        if pct and pct % 10 == 0:
            self.log_msg("下载更新 %d%%" % pct)

    def on_upd_ready(self, path):
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
        m = re.search(r"LAYOUT:\s*count=(\d+)", txt)
        if m:
            self.total = int(m.group(1))
        m2 = re.search(r"创建\s*(\d+)\s*/\s*(\d+)", txt)
        if m2:
            self.done_n = int(m2.group(1))
            self.total = max(self.total, int(m2.group(2)))
        saved = len(re.findall(r"SAVED", up))
        if saved:
            self.done_n = saved
        if "STEP_LAYOUT" in up or "LAYOUT:" in up:
            self.run_status = "正在批量布局…"
        if m2 and "SAVED" not in up:
            self.run_status = "正在批量布局… 已创建 %d / %d 个" % (self.done_n, self.total)
        elif "SAVED" in up:
            self.run_status = "正在绘制… 已保存 %d 张" % self.done_n
        if "STEP_LBD" in up or "LBD_" in up:
            self.run_status = "识别 LBD 标签…"
        if "STEP_SAVE" in up:
            self.run_status = "打印 / 导出…"
        # 阶段进度：创建布局 -> 写 LBD 标签 -> 画 STR 号（CAD 侧写进 prog 文件）
        lay = re.findall(r"创建\s*(\d+)\s*/\s*(\d+)", txt)
        if lay:
            self._phase = "LAYOUT"
            self.done_n, self.total = int(lay[-1][0]), int(lay[-1][1])
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
        lbd_total = re.findall(r"LBD_TOTAL\s*(\d+)", txt)
        if lbd_total:
            self._phase = "LBD"
            self.total = int(lbd_total[-1])
            self.done_n = 0
        lbd_done = re.findall(r"LBD_LABEL\s*(\d+)", txt)
        if lbd_done:
            self.done_n = int(lbd_done[-1])
        ai_total = re.findall(r"AI_TOTAL\s*(\d+)", txt)
        if ai_total:
            self._phase = "AI"
            self.total = int(ai_total[-1])
            self.done_n = 0
        ai_done = re.findall(r"AI_LABEL\s*(\d+)", txt)
        if ai_done:
            self.done_n = int(ai_done[-1])
        if self.total:
            self.done_n = min(self.done_n, self.total)
            if self._phase == "LAYOUT":
                self.run_status = "正在创建布局 %d / %d" % (self.done_n, self.total)
            elif self._phase == "LBD":
                self.run_status = "正在写 LBD 标签 %d / %d" % (self.done_n, self.total)
            elif self._phase == "AI":
                self.run_status = "正在画 STR 号 %d / %d" % (self.done_n, self.total)
        # 布局建完后会按 LBD 区域上下限再对准一次视口（CAD 侧写 REGION_FIT n）
        if "REGION_FIT" in up and "STEP_LBD" not in up:
            self.run_status = "正在按 LBD 区域上下限对准视口…"
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
                self.finish_title.setText("执行完成，共 %d 个布局 —— 请选择保存位置"
                                          % (self.total or self.done_n or 0))
                self.finish_hint.setText("点右边按钮选路径，会连到 CAD 用 SAVEAS 写成你选的文件"
                                         "（此时 STR 号也已画好，会一起存进去）")
        elif hard_err:
            self.run_status = "出错：" + (txt.strip()[-200:])
            finished = True
        self.status_label.setText(self.run_status)
        if self.total > 0:
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
