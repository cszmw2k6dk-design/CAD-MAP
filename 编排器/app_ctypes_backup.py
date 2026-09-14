# -*- coding: utf-8 -*-
# Voltage-CAD MAP · 本地桌面版 · Win32 原生窗口
# 用 ctypes 直接调用 Windows 控件，避免 tkinter/Tcl 在中文路径和 PyInstaller 下不可用的问题。
# 打包：pyinstaller --onefile --windowed --name PdfLayoutOrchestrator app.py
import ctypes
import json
import os
import re
import sys
import tempfile
import threading
import queue
from ctypes import wintypes as w

from pypdf import PdfReader

APP_TITLE = "Voltage-CAD MAP"
FIELDS = [
    ("dwg", "目标 DWG 文件"),
    ("lspPath", "ZWCAD 插件路径(.lsp)"),
    ("pdf", "PDF 文件路径"),
    ("xlsx", "LBD 名称 Excel"),
    ("outputDir", "输出目录"),
    ("newName", "新文件名(可空)"),
    ("pageStart", "起始页"),
    ("pageEnd", "结束页(0=全部)"),
    ("importPages", "导入页数(0=全部)"),
    ("templateLayout", "模板布局名(留空=自动)"),
    ("filter", "标记块名(竖线)"),
    ("count", "复制数量(0=按识别)"),
    ("pythonPath", "随包 Python(.exe)"),
    ("textHeight", "标签高度(0=自动)"),
    ("margin", "视口边距(mm)"),
    ("rule", "命名规则"),
    ("letters", "字母列表"),
    ("perGroup", "每组张数"),
    ("groupStart", "编号起始"),
    ("gridRows", "网格行数"),
    ("gridCols", "网格列数"),
    ("gridRowSp", "网格行距"),
    ("gridColSp", "网格列距"),
    ("gridPrefix", "网格前缀"),
    ("gridStartN", "网格起始号"),
    ("gridDigits", "网格位数"),
]
BROWSE_KEYS = ("dwg", "lspPath", "pdf", "xlsx", "outputDir", "pythonPath")
DEFAULTS = {
    "dwg": "",
    "lspPath": r"C:\Users\szk\Desktop\PdfLayout插件包 (2)\PdfLayout插件包\PdfLayout.lsp",
    "pdf": "", "xlsx": "", "outputDir": "",
    "newName": "MAP文件",
    "pageStart": "1", "pageEnd": "0", "importPages": "0", "templateLayout": "", "count": "0",
    "filter": "pdf", "margin": "5", "rule": "INV{G2}{L}{N2}", "letters": "AB", "perGroup": "6",
    "pythonPath": r"C:\Users\szk\Desktop\PdfLayout插件包 (2)\PdfLayout插件包\python\python.exe",
    "textHeight": "0", "groupStart": "1", "gridRows": "4", "gridCols": "5", "gridRowSp": "10",
    "gridColSp": "20", "gridPrefix": "CIR", "gridStartN": "1", "gridDigits": "2",
    "lockViewport": False, "overwrite": False, "labelWhere": "M", "filterCluster": True,
}

# ---- 界面分区（对应左侧导航，覆盖全部 25 个参数，不影响逻辑键名）----
SECTIONS = [
    ("文件与输出", [("dwg", "目标 DWG 文件"), ("lspPath", "ZWCAD 插件路径(.lsp)"),
                  ("pdf", "PDF 文件路径"), ("xlsx", "LBD 名称 Excel"),
                  ("outputDir", "输出目录"), ("pythonPath", "随包 Python(.exe)"),
                  ("newName", "新文件名(可空)")]),
    ("PDF 与标签", [("pageStart", "起始页"), ("pageEnd", "结束页(0=全部)"),
                  ("importPages", "导入页码(0=全部)"),
                  ("templateLayout", "模板布局名(留空=自动)"), ("count", "复制数量(0=按识别)"),
                  ("filter", "标记块名(竖线)"), ("textHeight", "标签高度(0=自动)"),
                  ("margin", "视口边距(mm)")]),
    ("命名规则", [("rule", "命名规则"), ("letters", "字母列表"),
                ("perGroup", "每组张数"), ("groupStart", "编号起始")]),
    ("网格编号", [("gridRows", "网格行数"), ("gridCols", "网格列数"),
                ("gridRowSp", "网格行距"), ("gridColSp", "网格列距"),
                ("gridPrefix", "网格前缀"), ("gridStartN", "网格起始号"),
                ("gridDigits", "网格位数")]),
    ("选项", []),
]
FIELDS_INDEX = {k: i for i, (k, _) in enumerate(FIELDS)}

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
comdlg32 = ctypes.windll.comdlg32
comctl32 = ctypes.windll.comctl32
kernel32 = ctypes.windll.kernel32

WM_COMMAND = 0x0111
WM_DESTROY = 0x0002
WM_APP = 0x8000
WM_SETTEXT = 0x000C
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
BN_CLICKED = 0
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_BORDER = 0x00800000
WS_TABSTOP = 0x00010000
WS_VSCROLL = 0x00200000
ES_MULTILINE = 0x0004
ES_AUTOVSCROLL = 0x0040
ES_READONLY = 0x0800
ES_LEFT = 0x0000
BS_AUTOCHECKBOX = 0x0003
ID_SCAN, ID_PLAN, ID_SAVE, ID_LOAD = 3001, 3002, 3003, 3004
ID_EXEC = 3000
ID_LOCK, ID_OVER = 4001, 4002
ID_FLT = 4003


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


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
                    dx = cm[0] * tm[4] + cm[2] * tm[5] + cm[4]
                    dy = cm[1] * tm[4] + cm[3] * tm[5] + cm[5]
                except Exception:
                    dx, dy = tm[4], tm[5]
                items.append([text, dx, dy])

        try:
            page.extract_text(visitor_text=visit)
        except Exception:
            items = []
        for it in items:
            if "LBD" not in it[0].upper():
                continue
            dx, dy = it[1], it[2]
            if dx < x0 or dy < y0 or dx > x0 + pw or dy > y0 + ph:
                continue
            fx = (dx - x0) / pw
            fy = (dy - y0) / ph
            labels.append((idx + 1, fx, fy, it[0]))
    per_page = {}
    for pg, *_ in labels:
        per_page[str(pg)] = per_page.get(str(pg), 0) + 1
    return {"ok": True, "totalPages": total, "pagesScanned": pe - ps + 1,
            "labelTotal": len(labels), "perPage": per_page}


def build_plan(cfg):
    def g(k, d=""):
        return str(cfg.get(k, d))
    rows = int(g("gridRows", "4") or 4)
    cols = int(g("gridCols", "5") or 5)
    gp = g("gridPrefix", "CIR")
    gsn = g("gridStartN", "1")
    gd = g("gridDigits", "2")
    # 可视化：行优先的名字网格
    try:
        rows = max(1, int(g("gridRows", "4")))
        cols = max(1, int(g("gridCols", "5")))
    except Exception:
        rows, cols = 4, 5
    per = max(1, int(g("perGroup", "6") or 1))
    letters = [x for x in g("letters", "AB") if x.strip()]
    lenl = max(1, len(letters))
    gstart = int(g("groupStart", "1") or 1)
    cnt = int(g("count", "0") or 0)
    total = cnt if cnt > 0 else rows * cols
    pad = lambda n, w: str(n).zfill(w)
    names = []
    for i in range(total):
        gn = gstart + i // (per * lenl)
        li = (i // per) % lenl
        nn = (i % per) + 1
        nm = g("rule", "INV{G2}{L}{N2}")
        nm = (nm.replace("{G2}", pad(gn, 2)).replace("{G}", str(gn))
                .replace("{L}", letters[li] if li < len(letters) else "")
                .replace("{N2}", pad(nn, 2)).replace("{N}", str(nn)))
        names.append(nm)
    grid = []
    grid.append("可视化(行优先, 每行 %d 个):" % cols)
    for rr in range(0, len(names), cols):
        grid.append("  " + "  ".join(names[rr:rr + cols]))
    return [
        "1. 打开目标 DWG：%s；模板布局（用于复制）：%s" % (g("dwg", "(未选择)"), g("templateLayout", "(未选择)")),
        "2. 导入/附着 PDF：%s（页码范围 %s–%s）" % (g("pdf", "(未选择)"), g("pageStart", "1"), g("pageEnd") or "末尾"),
        "3. LBD 标签识别：%s" % g("xlsx", "(未使用)"),
        "4. PDFGRID 网格编号：%s 行 × %s 列，行距 %s、列距 %s；前缀 %s、起始 %s、%s 位（共 %d 格）"
        % (g("gridRows", "4"), g("gridCols", "5"), g("gridRowSp", "10"), g("gridColSp", "20"), gp, gsn, gd, rows * cols),
        '5. PDFLAYOUT 批量布局：复制 %s 个，规则 "%s"，字母 %s，每 %s 张一组，编号从 %s 起'
        % (g("count", "0"), g("rule", "-"), g("letters", "-"), g("perGroup", "6"), g("groupStart", "1")),
        "6. 视口自动对准每张图（显示锁定：%s）" % ("是" if cfg.get("lockViewport") else "否"),
        "7. 批量打印/导出到：%s" % g("outputDir", "(未设置)"),
    ] + grid


# ---------------- Win32 GUI ----------------
WNDPROC = ctypes.WINFUNCTYPE(w.LPARAM, w.HWND, w.UINT, w.WPARAM, w.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", w.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", w.HINSTANCE), ("hIcon", w.HICON),
                ("hCursor", w.HANDLE), ("hbrBackground", w.HBRUSH), ("lpszMenuName", w.LPCWSTR),
                ("lpszClassName", w.LPCWSTR)]


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", w.HWND), ("message", w.UINT), ("wParam", w.WPARAM),
                ("lParam", w.LPARAM), ("time", w.DWORD), ("pt", w.POINT)]


class OPENFILENAMEW(ctypes.Structure):
    _fields_ = [("lStructSize", w.DWORD), ("hwndOwner", w.HWND), ("hInstance", w.HINSTANCE),
                ("lpstrFilter", w.LPCWSTR), ("lpstrCustomFilter", w.LPWSTR), ("nMaxCustFilter", w.DWORD),
                ("nFilterIndex", w.DWORD), ("lpstrFile", w.LPWSTR), ("nMaxFile", w.DWORD),
                ("lpstrFileTitle", w.LPWSTR), ("nMaxFileTitle", w.DWORD), ("lpstrInitialDir", w.LPCWSTR),
                ("lpstrTitle", w.LPCWSTR), ("Flags", w.DWORD), ("nFileOffset", w.WORD),
                ("nFileExtension", w.WORD), ("lpstrDefExt", w.LPCWSTR), ("lCustData", w.LPARAM),
                ("lpfnHook", w.LPVOID), ("lpTemplateName", w.LPCWSTR)]


class BROWSEINFOW(ctypes.Structure):
    _fields_ = [("hwndOwner", w.HWND), ("pidlRoot", w.LPVOID), ("pszDisplayName", w.LPWSTR),
                ("lpszTitle", w.LPCWSTR), ("ulFlags", w.UINT), ("lpfn", w.LPVOID),
                ("lParam", w.LPARAM), ("iImage", ctypes.c_int)]


class INITCOMMONCONTROLSEX(ctypes.Structure):
    _fields_ = [("dwSize", w.DWORD), ("dwICC", w.DWORD)]


CLASS = "PdfLayoutOrchWnd"
shell32 = ctypes.windll.shell32

# -------- Win32 函数原型（避免 ctypes 默认按 32 位 int 传参导致溢出）--------
user32.CreateWindowExW.restype = w.HWND
user32.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID]
user32.DefWindowProcW.restype = w.LPARAM
user32.DefWindowProcW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
user32.SendMessageW.restype = w.LPARAM
user32.SendMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
user32.PostMessageW.restype = w.BOOL
user32.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
user32.RegisterClassW.restype = w.WORD
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.ShowWindow.restype = w.BOOL
user32.ShowWindow.argtypes = [w.HWND, ctypes.c_int]
user32.UpdateWindow.restype = w.BOOL
user32.UpdateWindow.argtypes = [w.HWND]
user32.GetMessageW.restype = ctypes.c_int
user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), w.HWND, w.UINT, w.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.SetWindowTextW.restype = w.BOOL
user32.SetWindowTextW.argtypes = [w.HWND, w.LPCWSTR]
user32.LoadCursorW.restype = w.HANDLE
user32.LoadCursorW.argtypes = [w.HINSTANCE, ctypes.c_void_p]
kernel32.GetModuleHandleW.restype = w.HMODULE
kernel32.GetModuleHandleW.argtypes = [w.LPCWSTR]
gdi32.CreateFontW.restype = w.HANDLE
comdlg32.GetOpenFileNameW.restype = w.BOOL
comdlg32.GetOpenFileNameW.argtypes = [ctypes.POINTER(OPENFILENAMEW)]
comctl32.InitCommonControlsEx.restype = w.BOOL
comctl32.InitCommonControlsEx.argtypes = [ctypes.POINTER(INITCOMMONCONTROLSEX)]
shell32.SHBrowseForFolderW.restype = w.LPVOID
shell32.SHBrowseForFolderW.argtypes = [ctypes.POINTER(BROWSEINFOW)]
shell32.SHGetPathFromIDListW.restype = w.BOOL
shell32.SHGetPathFromIDListW.argtypes = [w.LPVOID, w.LPWSTR]
shell32.ILFree.restype = None
shell32.ILFree.argtypes = [w.LPVOID]
user32.GetDC.restype = w.HDC
user32.GetDC.argtypes = [w.HWND]
user32.ReleaseDC.restype = ctypes.c_int
user32.ReleaseDC.argtypes = [w.HWND, w.HDC]
gdi32.GetDeviceCaps.restype = ctypes.c_int
gdi32.GetDeviceCaps.argtypes = [w.HDC, ctypes.c_int]
user32.GetDpiForSystem.restype = ctypes.c_uint
user32.GetDpiForWindow.restype = ctypes.c_uint
user32.GetDpiForWindow.argtypes = [w.HWND]
kernel32.MulDiv.restype = ctypes.c_int
kernel32.MulDiv.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
_g_app = None
_wnd_class = None
_wndproc_ref = None


def set_dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def get_dpi():
    hdc = user32.GetDC(None)
    dpi = gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
    user32.ReleaseDC(None, hdc)
    return dpi or 96


# ---- 深色现代主题相关消息/样式 ----
WM_ERASEBKGND = 0x0014
WM_PAINT = 0x000F
WM_CTLCOLORSTATIC = 0x0138
WM_CTLCOLOREDIT = 0x0133
WM_CTLCOLORBTN = 0x0135
WM_DRAWITEM = 0x002B
BS_OWNERDRAW = 0x0000000B
WS_CLIPCHILDREN = 0x02000000
TRANSPARENT = 1


class DRAWITEMSTRUCT(ctypes.Structure):
    _fields_ = [("CtlType", w.UINT), ("CtlID", w.UINT), ("itemID", w.UINT),
                ("itemAction", w.UINT), ("itemState", w.UINT), ("hwndItem", w.HWND),
                ("hDC", w.HDC), ("rcItem", w.RECT), ("itemData", w.ULONG)]


gdi32.SetBkMode.restype = ctypes.c_int
gdi32.SetBkMode.argtypes = [w.HDC, ctypes.c_int]
gdi32.SetTextColor.restype = w.DWORD
gdi32.SetTextColor.argtypes = [w.HDC, w.DWORD]
gdi32.SetBkColor.restype = w.DWORD
gdi32.SetBkColor.argtypes = [w.HDC, w.DWORD]
gdi32.CreateSolidBrush.restype = w.HBRUSH
gdi32.CreateSolidBrush.argtypes = [w.DWORD]
gdi32.CreateCompatibleDC.restype = w.HDC
gdi32.CreateCompatibleDC.argtypes = [w.HDC]
gdi32.DeleteDC.restype = ctypes.c_int
gdi32.DeleteDC.argtypes = [w.HDC]
gdi32.SelectObject.restype = w.HGDIOBJ
gdi32.SelectObject.argtypes = [w.HDC, w.HGDIOBJ]
gdi32.CreatePen.restype = w.HPEN
gdi32.CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, w.DWORD]
gdi32.DeleteObject.restype = w.BOOL
gdi32.DeleteObject.argtypes = [w.HGDIOBJ]
gdi32.RoundRect.restype = w.BOOL
gdi32.RoundRect.argtypes = [w.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
user32.FillRect.restype = ctypes.c_int
user32.FillRect.argtypes = [w.HDC, ctypes.POINTER(w.RECT), w.HBRUSH]
gdi32.TextOutW.restype = w.BOOL
gdi32.TextOutW.argtypes = [w.HDC, ctypes.c_int, ctypes.c_int, w.LPCWSTR, ctypes.c_int]
gdi32.GetTextExtentPoint32W.restype = w.BOOL
gdi32.GetTextExtentPoint32W.argtypes = [w.HDC, w.LPCWSTR, ctypes.c_int, ctypes.POINTER(w.SIZE)]
user32.BeginPaint.restype = w.HDC
user32.BeginPaint.argtypes = [w.HWND, ctypes.c_void_p]
user32.EndPaint.argtypes = [w.HWND, ctypes.c_void_p]
user32.InvalidateRect.restype = w.BOOL
user32.InvalidateRect.argtypes = [w.HWND, ctypes.c_void_p, w.BOOL]
user32.MoveWindow.restype = w.BOOL
user32.MoveWindow.argtypes = [w.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.BOOL]
user32.SetForegroundWindow.restype = w.BOOL
user32.SetForegroundWindow.argtypes = [w.HWND]
user32.SetActiveWindow.restype = w.HWND
user32.SetActiveWindow.argtypes = [w.HWND]
user32.GetSystemMetrics.restype = ctypes.c_int
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.SystemParametersInfoW.restype = w.BOOL
user32.SystemParametersInfoW.argtypes = [w.UINT, w.UINT, ctypes.c_void_p, w.UINT]
gdi32.GetStockObject.restype = w.HGDIOBJ
gdi32.GetStockObject.argtypes = [ctypes.c_int]
gdi32.MoveToEx.restype = w.BOOL
gdi32.MoveToEx.argtypes = [w.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
gdi32.LineTo.restype = w.BOOL
gdi32.LineTo.argtypes = [w.HDC, ctypes.c_int, ctypes.c_int]


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [("hdc", w.HDC), ("fErase", w.BOOL), ("rcPaint", w.RECT),
                ("fRestore", w.BOOL), ("fIncUpdate", w.BOOL),
                ("rgbReserved", ctypes.c_byte * 32)]


def _W(hwnd, msg, wp, lp):
    global _g_app
    if hwnd != _g_app.hwnd:
        return user32.DefWindowProcW(hwnd, msg, wp, lp)
    if msg == WM_COMMAND:
        cid = wp & 0xFFFF
        code = (wp >> 16) & 0xFFFF
        if code == BN_CLICKED:
            _g_app.on_command(cid)
        return 0
    if msg == WM_APP:
        _g_app.on_async()
        return 0
    if msg == WM_ERASEBKGND:
        return 1
    if msg == WM_PAINT:
        _g_app.paint()
        return 0
    if msg == WM_CTLCOLORSTATIC:
        _g_app.color_static(wp)
        return _g_app.hbr["card"]
    if msg == WM_CTLCOLOREDIT or msg == WM_CTLCOLORBTN:
        return _g_app.color_edit(wp)
    if msg == WM_DRAWITEM:
        _g_app.draw_item(lp)
        return 1
    if msg == WM_DESTROY:
        user32.PostQuitMessage(0)
        return 0
    return user32.DefWindowProcW(hwnd, msg, wp, lp)


class App:
    def __init__(self):
        self.hwnd = None
        self.edits = {}       # key -> hwnd
        self.checks = {}      # key -> hwnd
        self.out = None       # output edit hwnd
        self.prefix = None
        self.font = None
        self.q = queue.Queue()
        self.result = None
        self.current_section = 0
        self.nav_btns = []      # list of (hwnd, section_index)
        self.btn_text = {}      # hwnd -> label
        self.field_edits = {}   # key -> (label_hwnd, edit_hwnd)
        self.field_sec = {}     # key -> section_index
        self.progress_pct = 0
        self.progress_msg = "就绪"
        self.run_active = False
        self.total_draws = 0
        self.done_draws = 0
        self.run_status = ""
        self.run_error = ""
        self.S = 1
        self.hbr = {}
        self.colors = {}
        self.layout = {}

    def _mkctrl(self, cls, text, x, y, ww, hh, hwnd_parent, style, cid=0):
        h = user32.CreateWindowExW(0, cls, text, style | WS_CHILD | WS_VISIBLE,
                                   x, y, ww, hh, hwnd_parent, cid, self.hinst, None)
        if self.font:
            user32.SendMessageW(h, 0x0030, 0, self.font)  # WM_SETFONT
        return h

    def create(self, hinst):
        self.hinst = hinst
        icc = INITCOMMONCONTROLSEX()
        icc.dwSize = ctypes.sizeof(INITCOMMONCONTROLSEX)
        icc.dwICC = 0x20
        comctl32.InitCommonControlsEx(ctypes.byref(icc))
        dpi = get_dpi()
        self.scale = max(1.0, dpi / 96.0)
        s = self.S = lambda v: int(round(v * self.scale))
        fh = -kernel32.MulDiv(11, dpi, 72)
        self.font = gdi32.CreateFontW(fh, 0, 0, 0, 400, 0, 0, 0, 0x86, 0, 0, 0, 0, 0, "Microsoft YaHei")
        bfh = -kernel32.MulDiv(9, dpi, 72)
        self.btn_font = gdi32.CreateFontW(bfh, 0, 0, 0, 600, 0, 0, 0, 0x86, 0, 0, 0, 0, 0, "Microsoft YaHei")
        bigfh = -kernel32.MulDiv(30, dpi, 72)
        self.big_font = gdi32.CreateFontW(bigfh, 0, 0, 0, 700, 0, 0, 0, 0x86, 0, 0, 0, 0, 0, "Microsoft YaHei")
        self._init_colors()
        wa = w.RECT()
        user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(wa), 0)  # SPI_GETWORKAREA
        aw = max(wa.right - wa.left, 100)
        ah = max(wa.bottom - wa.top, 100)
        ww = min(s(1000), aw - 30)
        wh = min(s(560), ah - 20)
        xp = wa.left + (aw - ww) // 2
        yp = wa.top + (ah - wh) // 2
        hwnd = user32.CreateWindowExW(0, CLASS, APP_TITLE,
                                      0x00CA0000, xp, yp, ww, wh,
                                      None, None, hinst, None)
        self.hwnd = hwnd
        self.win_w = ww
        self.win_h = wh
        self._build_ui()
        return hwnd

    def _init_colors(self):
        # 深色现代配色
        self.colors = {
            "bg": (43, 43, 43), "titlebar": (30, 30, 30), "sidebar": (35, 35, 35),
            "card": (26, 26, 26), "input": (58, 58, 58), "inputborder": (74, 74, 74),
            "label": (154, 154, 154), "text": (235, 235, 235), "accent": (45, 127, 249),
            "selbg": (58, 58, 58), "orange": (245, 166, 35),
        }
        c = self.colors
        self.hbr = {
            "bg": gdi32.CreateSolidBrush(self.RGB(*c["bg"])),
            "input": gdi32.CreateSolidBrush(self.RGB(*c["input"])),
            "card": gdi32.CreateSolidBrush(self.RGB(*c["card"])),
        }

    @staticmethod
    def RGB(r, g, b):
        return r | (g << 8) | (b << 16)

    def _build_ui(self):
        S = self.S
        W = self.win_w
        H = self.win_h
        SB = self.SB_W = S(240)
        self.field_widgets = {}
        self.btn_accent = set()
        # 侧边栏导航按钮（owner-draw）
        for i, (title, keys) in enumerate(SECTIONS):
            h = self._mkctrl("BUTTON", "", S(14), S(100 + i * 60), S(212), S(52),
                             self.hwnd, WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_OWNERDRAW, 6000 + i)
            self.nav_btns.append((h, i))
            self.btn_text[h] = title
        # 字段控件（一次创建，按分区显示）
        for sec_idx, (title, keys) in enumerate(SECTIONS):
            for key, label in keys:
                self.field_sec[key] = sec_idx
                lh = self._mkctrl("STATIC", label, S(0), S(0), S(150), S(24), self.hwnd, 0)
                eh = self._mkctrl("EDIT", "", S(0), S(0), S(420), S(34), self.hwnd, WS_BORDER | WS_TABSTOP)
                self.edits[key] = eh
                bh = None
                if key in BROWSE_KEYS:
                    bh = self._mkctrl("BUTTON", "", S(0), S(0), S(70), S(34), self.hwnd,
                                      WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_OWNERDRAW,
                                      2500 + FIELDS_INDEX[key])
                    self.btn_text[bh] = "选择"
                self.field_widgets[key] = (lh, eh, bh)
        # 选项分区（复选框 / 单选，保持标准控件以便 cfg/set_cfg 兼容）
        self.opt_widgets = []
        for key, txt, cid in [("lockViewport", "锁定视口显示", ID_LOCK),
                              ("overwrite", "覆盖同名布局", ID_OVER),
                              ("filterCluster", "排除集中干扰标号", ID_FLT)]:
            hchk = self._mkctrl("BUTTON", txt, S(0), S(0), S(200), S(30), self.hwnd,
                                BS_AUTOCHECKBOX | WS_TABSTOP, cid)
            self.checks[key] = hchk
            self.opt_widgets.append(hchk)
        self.rbM = self._mkctrl("BUTTON", "模型空间", S(0), S(0), S(120), S(30), self.hwnd,
                                0x0009 | WS_TABSTOP | 0x00020000, 5001)
        self.rbL = self._mkctrl("BUTTON", "当前布局", S(0), S(0), S(120), S(30), self.hwnd,
                                0x0009 | WS_TABSTOP, 5002)
        self.opt_widgets.extend([self.rbM, self.rbL])
        # 结果 / 日志框
        log_y = S(H - 80)
        self.out = self._mkctrl("EDIT", "", S(SB + 24), log_y, S(W - SB - 48), S(72), self.hwnd,
                                WS_BORDER | ES_MULTILINE | ES_AUTOVSCROLL | ES_READONLY | WS_VSCROLL)
        self.prog = None
        self.progLabel = None
        # 顶部操作按钮（owner-draw，从内容区左侧起排，保证“执行/输出”可见）
        by = S(8)
        bh = S(36)
        x = S(SB + 24)
        for txt, cid in [("载入配置", ID_LOAD), ("保存配置", ID_SAVE),
                         ("扫描", ID_SCAN), ("生成计划", ID_PLAN),
                         ("执行输出", ID_EXEC)]:
            wbtn = self._btn_w(txt)
            bb = self._mkctrl("BUTTON", "", x, by, wbtn, bh, self.hwnd,
                              WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_OWNERDRAW, cid)
            self.btn_text[bb] = txt
            if cid == ID_EXEC:
                self.btn_accent.add(bb)
            x += wbtn + S(10)
        self._show_section(0)

    def _btn_w(self, txt):
        hdc = user32.GetDC(None)
        old = gdi32.SelectObject(hdc, self.btn_font)
        sz = w.SIZE()
        gdi32.GetTextExtentPoint32W(hdc, txt, len(txt), ctypes.byref(sz))
        gdi32.SelectObject(hdc, old)
        user32.ReleaseDC(None, hdc)
        return self.S(int(sz.cx) + 22)

    def _measure(self, hdc, txt, font=None):
        font = font or self.font
        old = gdi32.SelectObject(hdc, font)
        sz = w.SIZE()
        gdi32.GetTextExtentPoint32W(hdc, txt, len(txt), ctypes.byref(sz))
        gdi32.SelectObject(hdc, old)
        return int(sz.cx)

    def _show_section(self, idx):
        S = self.S
        W = self.win_w
        H = self.win_h
        SB = self.SB_W
        self.run_active = False
        card_y = S(66)
        # 先隐藏全部
        for key, (lh, eh, bh) in self.field_widgets.items():
            user32.ShowWindow(lh, 0)
            user32.ShowWindow(eh, 0)
            if bh:
                user32.ShowWindow(bh, 0)
        for hw in getattr(self, "opt_widgets", []):
            user32.ShowWindow(hw, 0)
        # 显示当前分区字段
        y = card_y + S(52)
        for key, label in SECTIONS[idx][1]:
            lh, eh, bh = self.field_widgets[key]
            user32.MoveWindow(lh, S(288), y, S(150), S(24), 1)
            user32.MoveWindow(eh, S(430), y - S(6), S(420), S(34), 1)
            user32.ShowWindow(lh, 1)
            user32.ShowWindow(eh, 1)
            if bh:
                user32.MoveWindow(bh, S(858), y - S(6), S(70), S(34), 1)
                user32.ShowWindow(bh, 1)
            y += S(38)
        if idx == len(SECTIONS) - 1:
            oy = card_y + S(56)
            for hw in self.opt_widgets:
                user32.MoveWindow(hw, S(300), oy, S(220), S(30), 1)
                user32.ShowWindow(hw, 1)
                oy += S(34)
        self.current_section = idx
        user32.InvalidateRect(self.hwnd, None, 1)

    def color_static(self, wp):
        hdc = wp
        gdi32.SetTextColor(hdc, self.RGB(*self.colors["label"]))
        gdi32.SetBkMode(hdc, TRANSPARENT)

    def color_edit(self, wp):
        hdc = wp
        gdi32.SetTextColor(hdc, self.RGB(*self.colors["text"]))
        gdi32.SetBkMode(hdc, 0)
        gdi32.SetBkColor(hdc, self.RGB(*self.colors["input"]))
        return self.hbr["input"]

    def _fill_rect(self, hdc, x, y, ww, hh, color):
        r = w.RECT(x, y, x + ww, y + hh)
        br = gdi32.CreateSolidBrush(self.RGB(*color))
        user32.FillRect(hdc, ctypes.byref(r), br)
        gdi32.DeleteObject(br)

    def _fill_round(self, hdc, x, y, ww, hh, rr, color):
        br = gdi32.CreateSolidBrush(self.RGB(*color))
        old = gdi32.SelectObject(hdc, br)
        pen = gdi32.SelectObject(hdc, gdi32.GetStockObject(8))  # NULL_PEN
        gdi32.RoundRect(hdc, x, y, x + ww, y + hh, 2 * rr, 2 * rr)
        gdi32.SelectObject(hdc, pen)
        gdi32.SelectObject(hdc, old)
        gdi32.DeleteObject(br)

    def _text(self, hdc, x, y, txt, color, align=0, font=None):
        font = font or self.font
        old = gdi32.SelectObject(hdc, font)
        gdi32.SetTextColor(hdc, self.RGB(*color))
        gdi32.SetBkMode(hdc, TRANSPARENT)
        if align == 1:
            x -= self._measure(hdc, txt) // 2
        gdi32.TextOutW(hdc, x, y, txt, len(txt))
        gdi32.SelectObject(hdc, old)

    def paint(self):
        ps = PAINTSTRUCT()
        hdc = user32.BeginPaint(self.hwnd, ctypes.addressof(ps))
        S = self.S
        W = self.win_w
        H = self.win_h
        SB = self.SB_W
        c = self.colors
        # 背景
        self._fill_rect(hdc, 0, 0, W, H, c["bg"])
        # 侧边栏
        self._fill_rect(hdc, 0, 0, SB, H, c["sidebar"])
        # 顶部 V logo（浅蓝）
        lpen = gdi32.CreatePen(0, max(2, S(13)), self.RGB(*c["accent"]))
        lop = gdi32.SelectObject(hdc, lpen)
        lx, ly = S(24), S(22)
        gdi32.MoveToEx(hdc, lx, ly, None); gdi32.LineTo(hdc, lx + S(15), ly + S(32), None)
        gdi32.MoveToEx(hdc, lx + S(30), ly, None); gdi32.LineTo(hdc, lx + S(15), ly + S(32), None)
        gdi32.SelectObject(hdc, lop)
        gdi32.DeleteObject(lpen)
        # 进度条 + 状态文字
        ptx, pty = SB + S(24), S(50)
        ptw, pth = W - SB - S(48), S(7)
        self._fill_round(hdc, ptx, pty, ptw, pth, pth // 2, c["input"])
        fill = int(ptw * max(0.0, min(1.0, self.progress_pct / 100.0)))
        if fill > 0:
            self._fill_round(hdc, ptx, pty, fill, pth, pth // 2, c["accent"])
        self._text(hdc, ptx, S(58), self.progress_msg, c["label"])
        # 大卡片
        card_y = S(66)
        card_x = SB + S(24)
        card_w = W - SB - S(48)
        card_h = S(H - 88) - card_y - S(6)
        self._fill_round(hdc, card_x, card_y, card_w, card_h, S(14), c["card"])
        if self.run_active:
            self._draw_status(hdc, card_x, card_y, card_w, card_h)
        else:
            title = SECTIONS[self.current_section][0]
            self._fill_round(hdc, card_x + S(24), card_y + S(16), S(14), S(14), S(7), c["orange"])
            self._text(hdc, card_x + S(52), card_y + S(8), title, c["text"])
        user32.EndPaint(self.hwnd, ctypes.addressof(ps))

    def draw_item(self, lp):
        dis = ctypes.cast(lp, ctypes.POINTER(DRAWITEMSTRUCT)).contents
        hdc = dis.hDC
        rc = dis.rcItem
        x, y = rc.left, rc.top
        ww = rc.right - rc.left
        hh = rc.bottom - rc.top
        cid = dis.CtlID
        hwnd = dis.hwndItem
        text = self.btn_text.get(hwnd, "")
        c = self.colors
        if cid >= 6000:  # 侧边导航
            idx = cid - 6000
            sel = (idx == self.current_section)
            self._fill_round(hdc, x, y, ww, hh, 10, c["selbg"] if sel else c["sidebar"])
            if sel:
                self._fill_rect(hdc, x, y + 8, 4, hh - 16, c["accent"])
            self._fill_round(hdc, x + 22, y + (hh - 22) // 2, 22, 22, 5, c["accent"])
            self._text(hdc, x + 54, y + (hh - 15) // 2, text,
                       c["text"] if sel else c["label"], font=self.btn_font)
            return
        is_accent = hwnd in self.btn_accent
        self._fill_round(hdc, x, y, ww, hh, hh // 2, c["accent"] if is_accent else c["selbg"])
        fg = (255, 255, 255) if is_accent else c["label"]
        self._text(hdc, x + (ww - self._measure(hdc, text, self.btn_font)) // 2,
                   y + (hh - 15) // 2, text, fg, font=self.btn_font)

    def _draw_status(self, hdc, cx, cy, cw, ch):
        S = self.S
        c = self.colors
        total = self.total_draws
        done = self.done_draws
        if self.run_error:
            dot = (200, 60, 60)
        elif total and done >= total:
            dot = (90, 200, 120)
        else:
            dot = c["accent"]
        # 状态行
        self._fill_round(hdc, cx + S(24), cy + S(20), S(14), S(14), S(7), dot)
        self._text(hdc, cx + S(48), cy + S(12), self.run_status or "准备中", c["text"])
        # 大号数字
        self._text(hdc, cx + S(24), cy + S(74), "已绘制", c["text"], font=self.big_font)
        num = ("%d / %d" % (done, total)) if total else ("0 / ?")
        self._text(hdc, cx + S(200), cy + S(62), num, c["text"], font=self.big_font)
        # 进度条
        pbx = cx + S(24)
        pby = cy + S(140)
        pbw = cw - S(48)
        pbh = S(12)
        self._fill_round(hdc, pbx, pby, pbw, pbh, pbh // 2, c["input"])
        frac = min(1.0, done / float(total)) if total else 0.0
        fill = int(pbw * frac)
        if fill > 0:
            self._fill_round(hdc, pbx, pby, fill, pbh, pbh // 2, c["accent"])
        # 小方格网格（每格 = 一张图）
        if total and total < 2000:
            cols = 8
            gap = S(8)
            avail = cw - S(48)
            cell = int((avail - (cols - 1) * gap) // cols)
            gx = cx + S(24)
            gy = cy + S(176)
            for i in range(total):
                ri = i // cols
                ci = i % cols
                x = gx + ci * (cell + gap)
                y = gy + ri * (cell + gap)
                if y + cell > cy + ch - S(12):
                    break
                col = c["accent"] if i < done else (c["orange"] if i == done else c["selbg"])
                self._fill_round(hdc, x, y, cell, cell, S(5), col)

    def get_text(self, key):
        hwnd = self.edits[key]
        n = user32.SendMessageW(hwnd, WM_GETTEXTLENGTH, 0, 0)
        buf = ctypes.create_unicode_buffer(n + 2)
        user32.SendMessageW(hwnd, WM_GETTEXT, n + 2, ctypes.addressof(buf))
        return buf.value

    def set_text(self, key, value):
        user32.SetWindowTextW(self.edits[key], value or "")

    def log(self, text):
        user32.SetWindowTextW(self.out, text)

    def set_progress(self, pct, text=""):
        self.progress_pct = int(pct)
        self.progress_msg = text or ""
        if self.hwnd:
            user32.InvalidateRect(self.hwnd, None, 1)

    def cfg(self):
        c = {k: self.get_text(k) for k, _ in FIELDS}
        c["lockViewport"] = bool(user32.SendMessageW(self.checks["lockViewport"], 0x00F0, 0, 0))  # BM_GETCHECK
        c["overwrite"] = bool(user32.SendMessageW(self.checks["overwrite"], 0x00F0, 0, 0))
        c["filterCluster"] = bool(user32.SendMessageW(self.checks["filterCluster"], 0x00F0, 0, 0))
        c["labelWhere"] = "M" if user32.SendMessageW(self.rbM, 0x00F0, 0, 0) else "L"
        return c

    def set_cfg(self, c):
        for k, _ in FIELDS:
            self.set_text(k, c.get(k, DEFAULTS.get(k, "")))
        for k in ("lockViewport", "overwrite", "filterCluster"):
            user32.SendMessageW(self.checks[k], 0x00F1, 1 if c.get(k) else 0, 0)  # BM_SETCHECK
        m = 1 if (c.get("labelWhere", "M") != "L") else 0
        user32.SendMessageW(self.rbM, 0x00F1, m, 0)
        user32.SendMessageW(self.rbL, 0x00F1, 1 - m, 0)

    def on_command(self, cid):
        if cid >= 6000:
            self._show_section(cid - 6000)
        elif cid == ID_EXEC:
            self.run_auto()
        elif cid == ID_SCAN:
            self.log("正在扫描 PDF…")
            cfg = self.cfg()
            threading.Thread(target=self._scan_worker, args=(cfg,), daemon=True).start()
        elif cid == ID_PLAN:
            try:
                self.log("=== 执行计划 ===\n" + "\n".join(build_plan(self.cfg())))
            except Exception as e:
                self.log("生成计划出错：" + str(e))
        elif cid == ID_SAVE:
            try:
                save_config(self.cfg())
                self.log("配置已保存到：\n" + config_path())
            except Exception as e:
                self.log("保存失败：" + str(e))
        elif cid == ID_LOAD:
            self.set_cfg(load_config())
            self.log("已载入配置。")
        elif 2500 <= cid < 2600:
            idx = cid - 2500
            key = FIELDS[idx][0]
            self._browse(key)

    def _scan_worker(self, cfg):
        try:
            r = scan_pdf(cfg)
        except Exception as e:
            r = {"ok": False, "error": str(e)}
        self.q.put({"type": "scan", "data": r})
        user32.PostMessageW(self.hwnd, WM_APP, 0, 0)

    def on_async(self):
        try:
            r = self.q.get_nowait()
        except queue.Empty:
            return
        if r.get("type") == "scan":
            self._show_scan(r.get("data"))
        elif r.get("type") == "auto":
            self._show_auto(r.get("data"))

    def _show_scan(self, r):
        if not r.get("ok"):
            self.log("扫描失败：" + r.get("error", "未知错误"))
            return
        pp = "  ".join("页%s:%s" % (k, v) for k, v in (r.get("perPage") or {}).items())
        self.log("扫描完成：共 %s 页，找到 %s 个 LBD 标签。%s"
                 % (r.get("totalPages"), r.get("labelTotal"),
                    pp or "\n（未发现 LBD 文字）"))

    def _show_auto(self, r):
        msg = r.get("prog") or ""
        if msg:
            up = msg.upper()
            if "DONE" in up:
                self.run_status = "完成"
                if self.total_draws:
                    self.done_draws = max(self.done_draws, self.total_draws)
                self.run_active = True
            elif "ERROR" in up:
                self.run_status = "出错：" + msg
                self.run_error = msg
                self.run_active = True
            elif "START" in up:
                self.run_status = "正在启动 CAD…"
                self.run_active = True
            elif "LAYOUT:" in up:
                m = re.search(r"count=(\d+)", msg)
                if m and not self.total_draws:
                    self.total_draws = int(m.group(1))
                self.run_status = "正在批量布局…"
                self.run_active = True
            elif "SAVED" in up:
                if not self.total_draws:
                    self.total_draws = max(self.total_draws, self.done_draws + 1)
                self.done_draws += 1
                self.run_status = "正在绘制… 已保存 %d 张" % self.done_draws
                self.run_active = True
            elif "STEP_SAVE" in up:
                self.run_status = "打印 / 导出…"
                self.run_active = True
            elif "STEP_LBD" in up or "LBD_" in up:
                self.run_status = "识别 LBD 标签…"
                self.run_active = True
            # 计算进度
            if self.total_draws > 0:
                pct = int(round(min(1.0, self.done_draws / float(self.total_draws)) * 100))
            elif "DONE" in up:
                pct = 100
            elif "ERROR" in up:
                pct = 0
            elif "STEP_SAVE" in up or "SAVED" in up:
                pct = 90
            elif "STEP_LBD" in up or "LBD_" in up:
                pct = 55
            elif "LAYOUT:" in up or "STEP_LAYOUT" in up:
                pct = 25
            else:
                pct = 5
            self.progress_pct = pct
            self.progress_msg = self.run_status
            self.log(msg)
            if self.hwnd:
                user32.InvalidateRect(self.hwnd, None, 1)
        elif not r.get("ok"):
            self.run_status = "出错：" + r.get("error", "未知错误")
            self.run_error = self.run_status
            self.run_active = True
            self.set_progress(0, "出错")
            self.log("执行出错：" + r.get("error", "未知错误"))

    def run_auto(self):
        cfg = self.cfg()
        ini = os.path.join(tempfile.gettempdir(), "pdfauto.ini")
        prog = os.path.join(tempfile.gettempdir(), "pdfauto_prog.txt")
        try:
            self._write_ini(ini, cfg)
            open(prog, "w").close()
        except Exception as e:
            self.log("写入执行配置失败：" + str(e))
            return
        self.run_active = True
        self.run_error = ""
        self.run_status = "正在连接 / 启动 CAD…"
        self.total_draws = 0
        self.done_draws = 0
        self._apply_run_view()
        self.set_progress(0, "开始执行：连接 CAD…")
        self.log("正在调用 ZWCAD 执行（请切到 ZWCAD 等待）…")
        threading.Thread(target=self._auto_worker, args=(cfg, ini, prog), daemon=True).start()

    def _apply_run_view(self):
        # 执行时隐藏字段，显示执行状态可视化
        for key, (lh, eh, bh) in self.field_widgets.items():
            user32.ShowWindow(lh, 0)
            user32.ShowWindow(eh, 0)
            if bh:
                user32.ShowWindow(bh, 0)
        for hw in getattr(self, "opt_widgets", []):
            user32.ShowWindow(hw, 0)
        user32.InvalidateRect(self.hwnd, None, 1)

    def _write_ini(self, ini, cfg):
        with open(ini, "w", encoding="gbk") as f:
            for k, v in cfg.items():
                if v is True:
                    v2 = "1"
                elif v is False:
                    v2 = "0"
                else:
                    v2 = str(v)
                f.write("%s=%s\n" % (k, v2))

    def _ensure_auto_lsp(self):
        """找到 PdfLayout_auto.lsp（优先打包内 _MEIPASS，其次 exe 旁），复制到临时目录返回路径。"""
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

    def _ensure_plugin_lsp(self, lspPath):
        """始终返回纯英文临时路径：优先复制用户路径，否则用打包内置的 PdfLayout.lsp。"""
        cand = None
        if lspPath and os.path.exists(lspPath):
            cand = lspPath
        elif getattr(sys, "frozen", False):
            cand = os.path.join(getattr(sys, "_MEIPASS", ""), "PdfLayout.lsp")
        if not cand or not os.path.exists(cand):
            return lspPath if lspPath else cand
        tmp = os.path.join(tempfile.gettempdir(), "PdfLayout.lsp")
        try:
            with open(cand, "rb") as f:
                data = f.read()
            with open(tmp, "wb") as f:
                f.write(data)
            return tmp
        except Exception:
            return cand

    def _auto_worker(self, cfg, ini, prog):
        try:
            import time
            import pythoncom
            import win32com.client as win32
            pythoncom.CoInitialize()
            self._say("1/4 连接/启动 CAD（未启动会自动启动 ZWCAD，可能需 10-30 秒）…")
            acad = None
            conn_err = ""
            try:
                acad = win32.GetActiveObject("ZWCAD.Application")
            except Exception:
                try:
                    acad = win32.DispatchEx("ZWCAD.Application")
                except Exception:
                    try:
                        acad = win32.DispatchEx("AutoCAD.Application")
                    except Exception as e:
                        acad = None
                        conn_err = repr(e)
            if not acad:
                self._say("连接 CAD 失败：请确认已安装 ZWCAD/AutoCAD 并注册 COM。" + ((" 错误：" + conn_err) if conn_err else ""))
                return
            try:
                acad.Visible = True
            except Exception:
                pass
            self._say("2/4 已连接，准备打开 DWG…")
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
                self._say("无活动文档或无法打开 DWG")
                return
            self._say("3/4 DWG 就绪，加载插件并执行…")
            lsp = self._ensure_plugin_lsp((cfg.get("lspPath") or "").strip())
            auto = self._ensure_auto_lsp()
            if not auto:
                self._say("找不到 PdfLayout_auto.lsp")
                return

            def L(p):
                return '"' + p.replace("\\", "/") + '"'

            cmd = "(load %s)\n(load %s)\n(PdfLayout_AutoRun %s %s)\n" % (L(lsp), L(auto), L(ini), L(prog))
            self._say("发送命令：\n" + cmd.replace("\n", " "))
            doc.SendCommand(cmd)
            last = ""
            for _ in range(240):
                try:
                    txt = open(prog, encoding="utf-8", errors="replace").read().strip()
                except Exception:
                        txt = ""
                if txt and txt != last:
                    last = txt
                    self._say("ZWCAD: " + txt)
                if "DONE" in txt.upper() or "ERROR" in txt.upper():
                    break
                time.sleep(0.5)
            if not last:
                self._say("ZWCAD 无进度输出，请检查：目标 DWG、模板布局名、插件路径")
            else:
                self._say("完成：\n" + last)
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
        except Exception as e:
            self._say("执行出错：" + str(e))

    def _say(self, msg):
        self.q.put({"type": "auto", "data": {"ok": True, "prog": msg}})
        user32.PostMessageW(self.hwnd, WM_APP, 0, 0)

    def _browse(self, key):
        try:
            if key == "outputDir":
                self._browse_dir()
                return
            buf = ctypes.create_unicode_buffer(512)
            ofn = OPENFILENAMEW()
            ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
            ofn.hwndOwner = self.hwnd
            ofn.lpstrFile = ctypes.cast(buf, w.LPWSTR)
            ofn.nMaxFile = 512
            ofn.lpstrTitle = "选择文件"
            if key == "pdf":
                ofn.lpstrFilter = "PDF 文件\0*.pdf\0所有文件\0*.*\0"
            elif key == "dwg":
                ofn.lpstrFilter = "DWG 文件\0*.dwg\0所有文件\0*.*\0"
            elif key == "lspPath":
                ofn.lpstrFilter = "LISP 文件\0*.lsp\0所有文件\0*.*\0"
            elif key == "pythonPath":
                ofn.lpstrFilter = "Python 程序\0python.exe\0所有文件\0*.*\0"
            else:
                ofn.lpstrFilter = "Excel\0*.xlsx;*.xls\0所有文件\0*.*\0"
            if comdlg32.GetOpenFileNameW(ctypes.byref(ofn)):
                self.set_text(key, buf.value)
        except Exception as e:
            self.log("选择文件出错：%s" % e)

    def _browse_dir(self):
        try:
            disp = ctypes.create_unicode_buffer(512)
            path = ctypes.create_unicode_buffer(512)
            bi = BROWSEINFOW()
            bi.hwndOwner = self.hwnd
            bi.pszDisplayName = ctypes.cast(disp, w.LPWSTR)
            bi.lpszTitle = "选择输出目录"
            bi.ulFlags = 0x41  # BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE
            pidl = shell32.SHBrowseForFolderW(ctypes.byref(bi))
            if pidl:
                if shell32.SHGetPathFromIDListW(pidl, path):
                    self.set_text("outputDir", path.value)
                shell32.ILFree(pidl)
        except Exception as e:
            self.log("选择目录出错：%s" % e)


def main():
    global _g_app, _wnd_class, _wndproc_ref
    set_dpi_aware()
    hinst = kernel32.GetModuleHandleW(None)
    _wndproc_ref = WNDPROC(_W)
    wc = WNDCLASSW()
    wc.lpfnWndProc = _wndproc_ref
    wc.hInstance = hinst
    wc.lpszClassName = CLASS
    wc.hbrBackground = 6  # COLOR_WINDOW+1
    wc.hCursor = user32.LoadCursorW(0, 32512)  # IDC_ARROW
    _wnd_class = wc
    if not user32.RegisterClassW(ctypes.byref(wc)):
        return
    a = App()
    _g_app = a
    hwnd = a.create(hinst)
    user32.ShowWindow(hwnd, 1)
    user32.UpdateWindow(hwnd)
    user32.SetActiveWindow(hwnd)
    user32.SetForegroundWindow(hwnd)
    a.set_cfg(load_config())
    a.log("就绪。请设置参数后点击「扫描 PDF(LBD)」或「生成执行计划」。")
    msg = MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))


if __name__ == "__main__":
    main()
