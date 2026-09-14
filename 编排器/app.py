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

APP_TITLE = "Voltage-CAD MAP"
APP_VERSION = "2.17.1"
UPDATE_REPO = "cszmw2k6dk-design/CAD-MAP"
UPDATE_ASSET = "Voltage-CAD MAP.exe"
UPDATE_API = "https://api.github.com/repos/%s/releases/latest" % UPDATE_REPO
UPDATE_PAGE = "https://github.com/%s/releases" % UPDATE_REPO
FIELDS = [
    ("dwg", "目标 DWG 文件"), ("lspPath", "ZWCAD 插件路径(.lsp)"),
    ("pdf", "PDF 文件路径"), ("xlsx", "LBD 名称 Excel"), ("jsonPath", "识别结果 JSON文件"),
    ("outputDir", "默认保存目录(可空)"),
    ("newName", "新文件名(可空)"), ("pageStart", "起始页"), ("pageEnd", "结束页(0=全部)"),
    ("importPages", "导入页码(0=全部)"), ("templateLayout", "模板布局名(留空=自动)"),
    ("filter", "标记块名(竖线)"), ("count", "复制数量(0=按识别)"),
    ("textHeight", "标签高度(0=自动)"), ("labelBgColor", "标签背景色"),
    ("labelBgGap", "背景遮挡间隙(倍)"),
    ("rackTypes", "支架类型"), ("rackSplit", "拆不拆"), ("rackStringLen", "单串长度(FT)"),
    ("strBgOn", "STR背景填充"), ("strBgColor", "STR背景色"), ("strBgGap", "STR遮挡间隙"),
    ("margin", "视口边距(mm)"),
    ("gridRows", "网格行数"), ("gridCols", "网格列数"), ("gridRowSp", "网格行距"),
    ("gridColSp", "网格列距"), ("gridPrefix", "网格前缀"), ("gridStartN", "网格起始号"),
    ("gridDigits", "网格位数"),
]
BROWSE_KEYS = ("dwg", "lspPath", "pdf", "xlsx", "jsonPath", "outputDir")
DEFAULTS = {
    "dwg": "", "lspPath": "",
    "pdf": "", "xlsx": "", "jsonPath": "", "outputDir": "", "newName": "MAP文件",
    "pageStart": "1", "pageEnd": "0", "templateLayout": "", "count": "0", "filter": "pdf",
    "margin": "5",
    "textHeight": "0.15", "labelBgColor": "1", "labelBgGap": "1.0",
    "rackTypes": "", "rackSplit": "不拆", "rackStringLen": "",
    "strBgOn": "1", "strBgColor": "1", "strBgGap": "1.0",
    "gridRows": "4", "gridCols": "5", "gridRowSp": "10",
    "gridColSp": "20", "gridPrefix": "CIR", "gridStartN": "1", "gridDigits": "2",
    "lockViewport": False, "overwrite": False, "labelWhere": "M", "filterCluster": True,
    "useAI": False,
    "aiPython": r"C:\Users\szk\Desktop\MAP-CAD\_pyinstaller_tool\python\python.exe",
    "aiScript": r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\run_detect.py",
    "aiModel": r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\runs\frames\weights\best.pt",
    "aiOutdir": r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\output_run",
}
COLOR_CHOICES = [("红", "1"), ("黄", "2"), ("绿", "3"), ("青", "4"),
                 ("蓝", "5"), ("洋红", "6"), ("白", "7"), ("灰", "8")]
SECTIONS = [
    ("文件与输出", [("dwg", "目标 DWG 文件"), ("lspPath", "ZWCAD 插件路径(.lsp)"),
                  ("pdf", "PDF 文件路径"), ("xlsx", "LBD 名称 Excel"),
                  ("jsonPath", "识别结果 JSON文件"),
                  ("outputDir", "默认保存目录(可空)"),
                  ("newName", "新文件名(可空)")]),
    ("PDF 与标签", [("pageStart", "起始页"), ("pageEnd", "结束页(0=全部)"),
                  ("importPages", "导入页码(0=全部)"), ("templateLayout", "模板布局名(留空=自动)"),
                  ("count", "复制数量(0=按识别)"), ("filter", "标记块名(竖线)"),
                  ("textHeight", "标签高度(0=自动)"), ("labelBgColor", "标签背景色"),
                  ("labelBgGap", "背景遮挡间隙(倍)"),
                  ("margin", "视口边距(mm)")]),
    ("支架", [("rackTypes", "支架类型(串数:长度FT)"),
            ("rackSplit", "拆不拆"),
            ("rackStringLen", "单串长度(FT,可空)"),
            ("strBgOn", "STR背景填充"),
            ("strBgColor", "STR背景色"),
            ("strBgGap", "STR遮挡间隙(倍)")]),
    ("网格编号", [("gridRows", "网格行数"), ("gridCols", "网格列数"),
                ("gridRowSp", "网格行距"), ("gridColSp", "网格列距"),
                ("gridPrefix", "网格前缀"), ("gridStartN", "网格起始号"),
                ("gridDigits", "网格位数")]),
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


def scan_pdf(cfg):
    pdf = (cfg.get("pdf") or "").strip()
    if not pdf or not os.path.exists(pdf):
        return {"ok": False, "error": "PDF 文件不存在：%s" % pdf}
    try:
        ps = int(cfg.get("pageStart") or 1)
        pe = int(cfg.get("pageEnd") or 0)
    except Exception:
        ps, pe = 1, 0
    try:
        reader = PdfReader(pdf)
        total = len(reader.pages)
    except Exception as e:
        return {"ok": False, "error": "打开 PDF 失败：%s" % e}
    if ps < 1:
        ps = 1
    if pe <= 0 or pe > total:
        pe = total
    labels = []
    for idx in range(ps - 1, pe):
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
        items = []

        def visit(text, cm, tm, font, size):
            if text:
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
                xs = []
                ys = []
                for tx, ty in ((0.0, 0.0), (w, 0.0), (0.0, h), (w, h)):
                    xs.append(m0 * tx + m2 * ty + m4)
                    ys.append(m1 * tx + m3 * ty + m5)
                cx = (min(xs) + max(xs)) * 0.5
                cy = min(ys) - (max(ys) - min(ys)) * 0.15
                items.append([text, cx, cy])

        try:
            page.extract_text(visitor_text=visit)
        except Exception:
            items = []
        for it in items:
            if "LBD" not in it[0].upper():
                continue
            cx, cy = it[1], it[2]
            if cx < x0 or cy < y0 or cx > x0 + pw or cy > y0 + ph:
                continue
            fx = (cx - x0) / pw
            fy = (cy - y0) / ph
            labels.append((idx + 1, fx, fy, it[0]))
    per_page = {}
    for pg, *_ in labels:
        per_page[str(pg)] = per_page.get(str(pg), 0) + 1
    return {"ok": True, "totalPages": total, "pagesScanned": pe - ps + 1,
            "labelTotal": len(labels), "perPage": per_page}


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


def extract_lbd(pdf, out, pageStart, pageEnd, prog=None):
    # 等价于 pdf_extract.py：就地用已打包的 pypdf 提取 LBD 标签坐标，
    # 写出的 P/L 制表符格式与 LSP 的 PdfLayout_ReadExtractFile 期望一致。
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
        items = []
        all_text = []

        def visit_text(text, cm, tm, font, size):
            if text:
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
                xs = []
                ys = []
                for tx, ty in ((0.0, 0.0), (w, 0.0), (0.0, h), (w, h)):
                    xs.append(m0 * tx + m2 * ty + m4)
                    ys.append(m1 * tx + m3 * ty + m5)
                cx = (min(xs) + max(xs)) * 0.5
                cy = min(ys) - (max(ys) - min(ys)) * 0.15
                items.append([text, cx, cy])

        try:
            page.extract_text(visitor_text=visit_text)
        except Exception:
            items = []
        title = "".join(all_text[:100])
        lines.append("P\t%d\t%.2f\t%.2f\t%s"
                     % (idx + 1, pw, ph, title[:150].replace("\t", " ").replace("\n", " ")))
        for it in items:
            if "LBD" not in it[0].upper():
                continue
            cx, cy = it[1], it[2]
            if cx < x0 or cy < y0 or cx > x0 + pw or cy > y0 + ph:
                continue
            fx = (cx - x0) / pw
            fy = (cy - y0) / ph
            lines.append("L\t%d\t%.6f\t%.6f\t%s"
                         % (idx + 1, fx, fy, it[0].replace("\t", " ").replace("\n", " ")))
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


def json_to_extract(json_path, out_path):
    """读取识别结果 JSON(X-AnyLabeling 格式) -> 输出 L 行(页号 fx fy 标签) 供 CAD 读取。
    Node 框= LBD 区域, Typical 框= 支架(STR号)。页号取文件名里的 _pNNN。"""
    import re as _re
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
        fx = ((bx1 + bx2) / 2.0) / W
        fy = 1.0 - (((by1 + by2) / 2.0) / H)
        # STR 号: 角度按支架框长宽比自动(竖条=90,横条=0); 字高按框短边(占页高比例,
        # CAD 端再乘 *PdfLayout_AiStrScale*)。其它标签(LBD)角度 0、字高用默认值。
        bw, bh = bx2 - bx1, by2 - by1
        if up.startswith("STR"):
            ang = 90 if bh > bw else 0
            hgt = min(bw, bh) / float(H)
        else:
            ang = 0
            hgt = 0.0
        lines.append("L\t%d\t%.6f\t%.6f\t%s\t%d\t%.6f" % (page, fx, fy, lab, ang, hgt))
        if "-LBD-" in up:
            nodes += 1
        elif up.startswith("STR"):
            typs += 1
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return len(lines), nodes, typs


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


def build_plan(cfg):
    def g(k, d=""):
        return str(cfg.get(k, d))
    try:
        rows = max(1, int(g("gridRows", "4")))
        cols = max(1, int(g("gridCols", "5")))
    except Exception:
        rows, cols = 4, 5
    gp = g("gridPrefix", "CIR")
    gsn = g("gridStartN", "1")
    gd = g("gridDigits", "2")
    names, name_msg = plan_names(cfg)
    total = len(names)
    grid = ["布局名(Excel 分表名, 行优先, 每行 %d 个):" % cols]
    if name_msg:
        grid.append("  " + name_msg)
    for rr in range(0, len(names), cols):
        grid.append("  " + "  ".join(names[rr:rr + cols]))
    return [
        "1. 打开目标 DWG：%s；模板布局（用于复制）：%s" % (g("dwg", "(未选择)"), g("templateLayout", "(未选择)")),
        "2. 导入/附着 PDF：%s（页码范围 %s–%s）" % (g("pdf", "(未选择)"), g("pageStart", "1"), g("pageEnd") or "末尾"),
        "3. LBD 标签识别：%s" % g("xlsx", "(未使用)"),
        "4. 支架类型：%s；拆不拆：%s；单串长度：%s；STR背景填充：%s 色号%s 间隙%s" % (
            g("rackTypes", "(未填)"), g("rackSplit", "不拆"), g("rackStringLen", "(未填)"),
            ("开" if g("strBgOn", "1").strip() not in ("0", "", "关", "否") else "关"),
            g("strBgColor", "1"), g("strBgGap", "1.0")),
        "5. PDFGRID 网格编号：%s 行 × %s 列，行距 %s、列距 %s；前缀 %s、起始 %s、%s 位（共 %d 格）"
        % (g("gridRows", "4"), g("gridCols", "5"), g("gridRowSp", "10"), g("gridColSp", "20"), gp, gsn, gd, rows * cols),
        "6. PDFLAYOUT 批量布局：按 LBD Excel 分表名命名，布局 %d 个（%s）" % (total, name_msg or "—"),
        "7. 视口自动对准每张图（显示锁定：%s）" % ("是" if cfg.get("lockViewport") else "否"),
        "8. 执行完成后在界面选择保存位置（不再自动保存；默认目录：%s）" % g("outputDir", "(未设置)"),
    ] + grid


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
                    _n, _nn, _nt = json_to_extract(_jp, lbd_out)
                    ok, err = True, ""
                    bus.prog.emit("0/4 JSON标签 %d 个 (LBD %d / STR %d)" % (_n, _nn, _nt))
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
        import pythoncom
        import win32com.client as win32
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
        _pg = str(cfg.get("pageStart") or "1").strip() or "1"
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
            _strbg = ("(setq *PdfLayout_AiStrBgOn* %s)\n"
                      "(setq *PdfLayout_AiStrBgColor* %s)\n"
                      "(setq *PdfLayout_AiStrBgGap* %s)\n" % (_sbg_on, _sbg_c, _sbg_g))
            cmd = ("(load %s)\n(load %s)\n(load %s)\n"
                   "(setq *PdfLayout_GridAutoFile* %s)\n(setq *PdfLayout_AiPage* %s)\n"
                   "%s"
                   "(PdfLayout_AutoRun %s %s)\n(c:pdfgridai)\n(PdfLayout_Prog \"RUN_DONE\")\n"
                   % (L(lsp), L(auto), L(ai), L(_lbdout), _pg, _strbg, L(ini), L(prog)))
        else:
            cmd = ("(load %s)\n(load %s)\n(PdfLayout_AutoRun %s %s)\n(PdfLayout_Prog \"RUN_DONE\")\n"
                   % (L(lsp), L(auto), L(ini), L(prog)))
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
        "ping -n 3 127.0.0.1 >nul",
        "set /a N=0",
        ":retry",
        "set /a N+=1",
        'copy /y "%NEW%" "%TARGET%" >nul 2>&1',
        "if not errorlevel 1 goto ok",
        "if %N% GEQ 60 goto fail",
        "timeout /t 1 /nobreak >nul",
        "goto retry",
        ":ok",
        'start "" "%TARGET%"',
        "goto end",
        ":fail",
        'echo [update] failed, new exe kept at: "%NEW%"',
        "pause",
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
                         creationflags=0x00000008 | 0x00000200, close_fds=True)
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
        bus.save_result.emit(False, str(e))
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
    save_result = Signal(bool, str)
    upd_found = Signal(str, str, str, str)
    upd_none = Signal(str, str, str)
    upd_notes = Signal(str, str, str, bool)
    upd_error = Signal(str)
    upd_progress = Signal(int)
    upd_ready = Signal(str)


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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.bus = Bus()
        self.bus.prog.connect(self.on_prog)
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
        self.rbM = None
        self.rbL = None
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
        hl.addWidget(self.upd_label)
        ver = QLabel("v%s" % APP_VERSION)
        ver.setObjectName("VerLabel")
        hl.addWidget(ver)
        hl.addSpacing(8)
        self.upd_btn = QPushButton("检查更新")
        self.upd_btn.setObjectName("UpdBtn")
        self.upd_btn.setFixedHeight(28)
        self.upd_btn.clicked.connect(self.on_upd_click)
        hl.addWidget(self.upd_btn)
        self.notes_btn = QPushButton("更新日志")
        self.notes_btn.setObjectName("UpdBtn")
        self.notes_btn.setFixedHeight(28)
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
        for t, cb in [("载入配置", self.on_load), ("保存配置", self.on_save),
                      ("扫描", self.on_scan), ("生成计划", self.on_plan),
                      ("执行输出", self.on_run)]:
            b = QPushButton(t)
            if t == "执行输出":
                b.setObjectName("Primary")
            b.clicked.connect(cb)
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
        if sec_title == "选项":
            r = 0
            for key, txt, init in [("lockViewport", "锁定视口显示", False),
                                   ("overwrite", "覆盖同名布局", False),
                                   ("filterCluster", "排除集中干扰标号", True),
                                   ("useAI", "使用AI自动识别(无需手动框)", False)]:
                cb = QCheckBox(txt)
                cb.setChecked(init)
                self.checkbox[key] = cb
                form.addWidget(cb, r, 0, 1, 2)
                r += 1
            form.addWidget(QLabel("标签位置:"), r, 0)
            self.rbM = QRadioButton("模型空间")
            self.rbL = QRadioButton("当前布局")
            self.rbM.setChecked(True)
            hb = QHBoxLayout()
            hb.setSpacing(10)
            hb.addWidget(self.rbM)
            hb.addWidget(self.rbL)
            form.addLayout(hb, r, 1)
        elif sec_title == "支架":
            # 支架类型 + 拆不拆：程序按 行长度÷单串长度 得每行串数，
            # 再按"拆成几行"把相邻各行归成一张支架，串数取和。
            HINTS = {
                "rackTypes": "每类写成 串数:长度FT，逗号分隔。例：1:100.3, 2:214.3, 3:320.0",
                "rackSplit": "填 不拆 / 2行 / 3行；也可按 LBD 写：LBD-01..12=3行, 其余=不拆",
                "rackStringLen": "可留空。填了按 行长度÷单串长度 反推串数，再和支架类型核对",
                "strBgOn": "STR 号是否加背景填充（遮掉底图线条）。默认开",
                "strBgColor": "背景填充颜色，下拉选择 ACI 色号",
                "strBgGap": "背景相对文字的外扩倍数，默认 1.0（越大遮得越宽）",
            }
            r = 0
            for key, label in keys:
                lb = QLabel(label)
                lb.setObjectName("FieldLabel")
                form.addWidget(lb, r, 0)
                if key == "strBgColor":
                    cb = QComboBox()
                    cb.setObjectName("Field")
                    cb.setMinimumWidth(320)
                    for cname, aci in COLOR_CHOICES:
                        cb.addItem(cname, aci)
                    self.combo[key] = cb
                    form.addWidget(cb, r, 1)
                elif key == "strBgOn":
                    cb = QComboBox()
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
                    edit.setPlaceholderText(HINTS.get(key, ""))
                    self.edits[key] = edit
                    form.addWidget(edit, r, 1)
                r += 1
                hint = QLabel(HINTS.get(key, ""))
                hint.setObjectName("Hint")
                hint.setWordWrap(True)
                form.addWidget(hint, r, 1)
                r += 1
        else:
            for row, (key, label) in enumerate(keys):
                lb = QLabel(label)
                lb.setObjectName("FieldLabel")
                form.addWidget(lb, row, 0)
                if key == "labelBgColor":
                    cb = QComboBox()
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
        outer.addStretch(1)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setWidget(page)
        return sc

    def _build_status_page(self):
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
        self.grid = DrawGrid()
        v.addWidget(self.grid, 1)
        # 完成区：跑完由用户选保存位置（不再自动保存到输出目录）
        fin = QFrame()
        fin.setObjectName("FinishBox")
        fv = QHBoxLayout(fin)
        fv.setContentsMargins(16, 12, 16, 12)
        fv.setSpacing(12)
        fcol = QVBoxLayout()
        fcol.setSpacing(4)
        self.finish_title = QLabel("执行完成后，在这里选择保存位置")
        self.finish_title.setObjectName("FinishTitle")
        self.finish_hint = QLabel("不会再自动保存到“默认保存目录”，选完路径才写文件")
        self.finish_hint.setObjectName("Hint")
        self.finish_hint.setWordWrap(True)
        fcol.addWidget(self.finish_title)
        fcol.addWidget(self.finish_hint)
        fv.addLayout(fcol, 1)
        self.save_btn = QPushButton("选择保存位置并保存…")
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
        c["lockViewport"] = self.checkbox["lockViewport"].isChecked()
        c["overwrite"] = self.checkbox["overwrite"].isChecked()
        c["filterCluster"] = self.checkbox["filterCluster"].isChecked()
        c["useAI"] = self.checkbox["useAI"].isChecked()
        c["labelWhere"] = "M" if self.rbM.isChecked() else "L"
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
        m = c.get("labelWhere", "M") != "L"
        self.rbM.setChecked(m)
        self.rbL.setChecked(not m)

    def log_msg(self, text):
        self.log.appendPlainText(text)

    def on_scan(self):
        self.log_msg("正在扫描 PDF…")
        threading.Thread(target=self._scan_worker, args=(self.cfg(),), daemon=True).start()

    def _scan_worker(self, cfg):
        try:
            r = scan_pdf(cfg)
        except Exception as e:
            r = {"ok": False, "error": str(e)}
        if r.get("ok"):
            pp = "  ".join("页%s:%s" % (k, v) for k, v in (r.get("perPage") or {}).items())
            self.log_msg("扫描完成：共 %s 页，找到 %s 个 LBD 标签。%s"
                         % (r.get("totalPages"), r.get("labelTotal"),
                            pp or "\n（未发现 LBD 文字）"))
        else:
            self.log_msg("扫描失败：" + r.get("error", "未知错误"))

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

    def on_plan(self):
        try:
            self.log_msg("=== 执行计划 ===\n" + "\n".join(build_plan(self.cfg())))
        except Exception as e:
            self.log_msg("生成计划出错：" + str(e))

    def on_save(self):
        try:
            save_config(self.cfg())
            self.log_msg("配置已保存到：\n" + config_path())
        except Exception as e:
            self.log_msg("保存失败：" + str(e))

    def on_load(self):
        self.set_cfg(load_config())
        self.log_msg("已载入配置。")

    def browse(self, key):
        if key == "outputDir":
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
        self.save_btn.setText("选择保存位置并保存…")
        self.finish_title.setText("执行完成后，在这里选择保存位置")
        self.finish_hint.setText("不会再自动保存到“默认保存目录”，选完路径才写文件")
        # 读取配置里的 AI 自动识别参数
        try:
            _d = load_config()
            for _k in ("aiPython", "aiScript", "aiModel", "aiOutdir"):
                cfg[_k] = (_d.get(_k) or "").strip() or DEFAULTS.get(_k, "")
        except Exception:
            pass
        ini = os.path.join(tempfile.gettempdir(), "pdfauto.ini")
        prog = os.path.join(tempfile.gettempdir(), "pdfauto_prog.txt")
        try:
            with open(ini, "w", encoding="gbk") as f:
                for k, v in cfg.items():
                    f.write("%s=%s\n" % (k, 1 if v is True else (0 if v is False else v)))
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
        self.grid.set_value(0, 0)
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
        if "0/4" in msg:
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
            self.grid.set_value(self.done_n, self.total)

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
            self.grid.set_value(self.done_n, self.total)
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
            self.save_btn.setText("选择保存位置并保存…")
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
        self.upd_label.setText("正在下载 %d%%" % pct)
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
                                "新版本已下载完成。\n点确定后程序会关闭，几秒内自动替换并重新打开。")
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
                self.save_btn.setEnabled(True)
                self.save_btn.setText("选择保存位置并保存…")
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
            self.grid.set_value(self.done_n, self.total)
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
