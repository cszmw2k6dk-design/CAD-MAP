# -*- coding: utf-8 -*-
"""LBD 标注工具 v0.1（内嵌标注页原型）

直接读写 agent3-debug 识别结果 JSON：改框、改 LBD 名字，另存出一份完整 JSON 给下游程序用。

用法:
    python lbd_annotator.py                 # 打开对话框选 JSON
    python lbd_annotator.py 识别结果.json
    python lbd_annotator.py --selftest      # 无界面自检（改一页 -> 另存 -> 用下游代码验证）

设计要点:
  * 不动原文件。默认「另存为」xxx_annotated.json；「覆盖保存」会先备份 .bak-时间戳。
  * 图片直接从 JSON 里内嵌的 png_base64 解出来，不落地 PNG。
  * 246MB 的 JSON 按字节流式读写：只替换改过的页所在的三个顶层数组，
    其它段落（含没改过的页）逐字节保留原样。
  * Node 框与 ocr_node_name_results 记录一一对应（按 node_bbox 对齐），
    改名写进 final_node_name —— 这正是下游 extract_lines_from_debug 读的字段。
"""
import argparse
import copy
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

CLASSES = ("Node", "Tracker", "Box")
# 调外部程序（pdftoppm / pdfinfo）时别弹那个黑窗口：Windows 下加 CREATE_NO_WINDOW
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
# Qt 默认单张图片解码上限 256MB：6000x4000(96MB) 没问题，但 333dpi 的
# 11988x7992 要 383MB，会被拒（表现就是"渲染结果读不出来"）。放宽到 1GB。
os.environ.setdefault("QT_IMAGEIO_MAXALLOC", "1024")
TRACKER_SECTION = "yolo_tracker_detection_results"
BOX_SECTION = "yolo_box_detection_results"
OCR_SECTION = "ocr_node_name_results"
SECTION_ORDER = (TRACKER_SECTION, BOX_SECTION, OCR_SECTION)
DEFAULT_CLASS_ID = {"Node": 1, "Tracker": 0, "Box": 0}
WS = b" \t\r\n"
DEFAULT_JSON = r"C:\Users\ZhaokeShi\OneDrive - Voltage, LLC\桌面\little-debug.json"

# ------------------------------------------------------- 高分辨率底图（重新渲染 PDF）
POPPLER_HINTS = (
    # 便携位置：放个 poppler 文件夹，或直接把 pdftoppm.exe 放程序旁边，都认
    r"poppler\pdftoppm.exe",
    r"pdftoppm.exe",
    r"poppler\Library\bin\pdftoppm.exe",
    r"%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies"
    r"\native\poppler\Library\bin\pdftoppm.exe",
    r"C:\Program Files\poppler\Library\bin\pdftoppm.exe",
    r"C:\Program Files (x86)\poppler\Library\bin\pdftoppm.exe",
    r"C:\poppler\Library\bin\pdftoppm.exe",
)


def app_dir():
    """程序所在目录：打包成 exe 后是 exe 的目录，源码运行时是脚本目录。

    设置文件、渲染缓存都放这儿，打包后才是「跟着程序走」的便携目录 ——
    不会写进 exe 解包出来的临时目录（那里面一关就没了）。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def find_pdftoppm():
    for h in POPPLER_HINTS:
        p = os.path.expandvars(h)
        if not os.path.isabs(p):
            p = os.path.join(app_dir(), p)          # 相对路径按程序目录找
        if os.path.exists(p):
            return p
    return shutil.which("pdftoppm") or ""


def find_poppler(exe):
    """同一个 poppler 目录下的其它工具（pdfinfo 等）。"""
    for h in POPPLER_HINTS:
        p = os.path.expandvars(h)
        if not os.path.isabs(p):
            p = os.path.join(app_dir(), p)
        cand = os.path.join(os.path.dirname(p), exe)
        if os.path.exists(cand):
            return cand
    return shutil.which(exe) or ""


def pdf_page_sizes(pdf):
    """{页号: (宽pt, 高pt, 旋转角)}：一次 pdfinfo 读完整册页尺寸。

    注意 pdfinfo 报的是**未旋转**的 mediabox，而 pdftoppm 渲染时会应用 /Rotate，
    所以这里把旋转角一并带出来，让调用方决定要不要把宽高对调。
    """
    exe = find_poppler("pdfinfo.exe")
    if not exe:
        return {}
    try:
        out = subprocess.run([exe, pdf], capture_output=True, text=True,
                             errors="replace", timeout=120,
                             creationflags=_NO_WINDOW).stdout
        m = re.search(r"^Pages:\s+(\d+)", out, re.M)
        if not m:
            return {}
        n = int(m.group(1))
        out = subprocess.run([exe, "-f", "1", "-l", str(n), pdf], capture_output=True,
                             text=True, errors="replace", timeout=600,
                             creationflags=_NO_WINDOW).stdout
    except Exception:
        return {}
    sizes = {}
    for m in re.finditer(r"^Page\s+(\d+)\s+size:\s+([\d.]+)\s+x\s+([\d.]+)\s+pts", out, re.M):
        sizes[int(m.group(1))] = [float(m.group(2)), float(m.group(3)), 0]
    for m in re.finditer(r"^Page\s+(\d+)\s+rot:\s+(-?\d+)", out, re.M):
        n = int(m.group(1))
        if n in sizes:
            sizes[n][2] = int(m.group(2)) % 360
    sizes = {n: tuple(v) for n, v in sizes.items()}
    return sizes


def rss_mb():
    """当前进程占用的物理内存（MB）：Windows 用 psapi，其它平台尽力而为。"""
    try:
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]
        p = PMC()
        p.cb = ctypes.sizeof(PMC)
        h = ctypes.windll.kernel32.GetCurrentProcess()
        ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(p), p.cb)
        return p.WorkingSetSize / 1048576.0
    except Exception:
        return 0.0


class BlankDoc:
    """没有识别结果、直接拿 PDF 标注时用的空文档：页数/尺寸来自 PDF，标注从零开始。

    坐标空间 = 按 self.dpi 渲染出来的像素（和底图渲染分辨率一致，框不会飘）。
    保存时生成一份和识别结果同格式的 JSON，可以直接喂给下游。
    """

    is_blank = True

    def __init__(self, pdf, dpi=250.0):
        self.path = pdf
        self.dpi = float(dpi)
        self.project = os.path.splitext(os.path.basename(pdf))[0]
        self.pages = {}
        for n, (w_pt, h_pt, rot) in sorted(pdf_page_sizes(pdf).items()):
            if rot in (90, 270):                 # 渲染时会旋转，宽高对调
                w_pt, h_pt = h_pt, w_pt
            self.pages[n] = {"page_number": n,
                             "width": max(1, int(round(w_pt * self.dpi / 72.0))),
                             "height": max(1, int(round(h_pt * self.dpi / 72.0))),
                             "png_span": None}

    def page_numbers(self):
        return sorted(self.pages)

    def page_data(self, key, page_number):
        return None

    def save(self, dest, modified):
        doc = {"schema_version": "agent3-debug-v1",
               "generator": "lbd_annotator（直接标注 PDF，无识别结果）",
               "source_pdf": os.path.basename(self.path),
               "render_dpi": self.dpi,
               "input_data": {"project_name": self.project,
                              "pages": [{"page_number": n, "media_type": "image/png",
                                         "width": self.pages[n]["width"],
                                         "height": self.pages[n]["height"]}
                                        for n in self.page_numbers()]},
               "yolo_tracker_detection_results": [],
               "yolo_box_detection_results": [],
               "ocr_node_name_results": []}
        for n in self.page_numbers():
            m = modified.get(n)
            if not m:
                # 没标注的页不写记录：下游是按"有东西的页"给底图排页号的，
                # 给每页都写一条空记录会让页号映射退化成 1:1，底图就对不上了。
                continue
            doc["yolo_tracker_detection_results"].append({"page_number": n, "data": m["tracker"]})
            doc["yolo_box_detection_results"].append({"page_number": n, "data": m["box"]})
            doc["ocr_node_name_results"].append({"page_number": n, "data": m["ocr"]})
        tmp = dest + ".part"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)
        os.replace(tmp, dest)
        return sorted(modified)


def project_name(json_path):
    """从 JSON 开头取 project_name（只读头 4KB，不整份解析）。"""
    try:
        with open(json_path, "rb") as f:
            head = f.read(4096).decode("utf-8", "ignore")
        m = re.search(r'"project_name"\s*:\s*"([^"]+)"', head)
        return m.group(1).strip() if m else ""
    except Exception:
        return ""


def guess_pdf(json_path, exact_only=False):
    """按 JSON 里的 project_name 猜 PDF（同目录优先，其次 Downloads / 桌面）。
    exact_only=True 时只认文件名完全对得上的，不用兜底。"""
    name = project_name(json_path)
    home = os.path.expanduser("~")
    dirs = [os.path.dirname(os.path.abspath(json_path)),
            os.path.join(home, "Downloads"), os.path.join(home, "Desktop")]
    if name:
        want = (name + ".pdf").lower()
        for d in dirs:
            p = os.path.join(d, name + ".pdf")
            if os.path.exists(p):
                return p
        for d in dirs:
            if not os.path.isdir(d):
                continue
            base_depth = d.rstrip(os.sep).count(os.sep)
            for root, subdirs, files in os.walk(d):
                if root.count(os.sep) - base_depth > 3:
                    subdirs[:] = []
                    continue
                for f in files:
                    if f.lower() == want:
                        return os.path.join(root, f)
    if exact_only:
        return ""
    d = dirs[0]
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if f.lower().endswith(".pdf"):
                return os.path.join(d, f)
    return ""


class Renderer:
    """用 poppler 按更高 DPI 重渲染某一页，结果缓存到磁盘。"""

    def __init__(self, exe, cache_root):
        self.exe = exe
        self.cache_root = cache_root
        self.sweep()

    def sweep(self):
        """清掉上次被中断留下的临时文件（渲染到一半被杀会残留）。"""
        try:
            for p in glob.glob(os.path.join(self.cache_root, "*", "_tmp_*.png")):
                if time.time() - os.path.getmtime(p) > 1800:
                    os.remove(p)
        except Exception:
            pass

    @staticmethod
    def pdf_tag(pdf):
        """把 PDF 的身份揉进缓存路径：换一份 PDF 必须换一套缓存，否则会拿到别人的图。"""
        try:
            st = os.stat(pdf)
            key = "%s|%d|%d" % (os.path.abspath(pdf).lower(), st.st_size, int(st.st_mtime))
        except OSError:
            key = os.path.abspath(pdf).lower()
        return hashlib.md5(key.encode("utf-8")).hexdigest()[:8]

    def target(self, pdf, page, dpi):
        return os.path.join(self.cache_root, "%ddpi_%s" % (dpi, self.pdf_tag(pdf)),
                            "p%03d.png" % page)

    def render(self, pdf, page, dpi):
        out = self.target(pdf, page, dpi)
        if os.path.exists(out) and os.path.getsize(out) > 1000:
            return out
        os.makedirs(os.path.dirname(out), exist_ok=True)
        # 每个线程用各自的临时前缀，避免预取和当前页撞车（os.replace 是原子的）
        tmp_prefix = os.path.join(os.path.dirname(out),
                                  "_tmp_p%03d_%d" % (page, threading.get_ident()))
        for old in glob.glob(tmp_prefix + "*.png"):
            try:
                os.remove(old)
            except OSError:
                pass
        subprocess.run([self.exe, "-png", "-r", str(dpi), "-f", str(page),
                        "-l", str(page), pdf, tmp_prefix],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=300, creationflags=_NO_WINDOW)
        made = sorted(glob.glob(tmp_prefix + "*.png"))
        if not made:
            raise RuntimeError("渲染没有产出文件")
        os.replace(made[0], out)
        for extra in made[1:]:
            try:
                os.remove(extra)
            except OSError:
                pass
        return out


def settings_path():
    return os.path.join(app_dir(), "annotator_settings.json")


def load_settings():
    try:
        with open(settings_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(d):
    try:
        with open(settings_path(), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ------------------------------------------------------- 字节级 JSON 定位
def skip_ws(b, i):
    while i < len(b) and b[i] in WS:
        i += 1
    return i


def skip_str(b, i):
    """b[i] 是开引号，返回闭引号之后的下标。"""
    i += 1
    while i < len(b):
        c = b[i]
        if c == 0x5C:
            i += 2
            continue
        if c == 0x22:
            return i + 1
        i += 1
    raise ValueError("字符串没有收尾")


def skip_val(b, i):
    """返回值的结束下标（不含）。"""
    i = skip_ws(b, i)
    c = b[i]
    if c == 0x22:
        return skip_str(b, i)
    if c in b"{[":
        depth = 0
        while i < len(b):
            c = b[i]
            if c == 0x22:
                i = skip_str(b, i)
                continue
            if c in b"{[":
                depth += 1
            elif c in b"}]":
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1
        raise ValueError("容器没有收尾")
    j = i
    while j < len(b) and b[j] not in b",}] \t\r\n":
        j += 1
    return j


def top_spans(b):
    """对象 -> {键: (值起, 值止)}，只扫一层。"""
    out = {}
    i = skip_ws(b, 0)
    if b[i] != 0x7B:
        raise ValueError("不是对象")
    i += 1
    while True:
        i = skip_ws(b, i)
        if b[i] == 0x7D:
            return out
        ke = skip_str(b, i)
        key = json.loads(b[i:ke])
        i = skip_ws(b, ke)
        if b[i] != 0x3A:
            raise ValueError("缺少冒号")
        vs = skip_ws(b, i + 1)
        ve = skip_val(b, vs)
        out[key] = (vs, ve)
        i = skip_ws(b, ve)
        if b[i] == 0x2C:
            i += 1
            continue
        return out


def round_box_key(b):
    """和 lbd_regions.py 一样按 0.1 像素取整对齐 node_bbox。"""
    return (round(float(b["x1"]), 1), round(float(b["y1"]), 1),
            round(float(b["x2"]), 1), round(float(b["y2"]), 1))


class DebugJson:
    """识别结果 JSON 的字节级索引：图片按需取，段落按需解析，保存时定点替换。"""

    def __init__(self, path):
        self.path = path
        t0 = time.time()
        with open(path, "rb") as f:
            self.raw = f.read()
        self.load_seconds = time.time() - t0
        self.size = len(self.raw)
        self.sections = {}
        for key in SECTION_ORDER:
            span = self._find_array_span(key)
            if span:
                self.sections[key] = {"span": span, "elements": None}
        self.pages = {}
        self._index_pages()

    def _find_key(self, key):
        pat = ('"%s"' % key).encode()
        i = self.raw.find(pat)
        return None if i < 0 else i + len(pat)

    def _find_array_span(self, key):
        """返回 (数组 '[' 下标, ']' 之后下标)。用后一个顶层键兜底找收尾方括号。"""
        d = self.raw
        at = self._find_key(key)
        if at is None:
            return None
        i = skip_ws(d, at)
        if d[i] != 0x3A:
            return None
        i = skip_ws(d, i + 1)
        if d[i] != 0x5B:
            return None
        start = i
        limit = len(d)
        for other in ("yolo_tracker_detection_results", "yolo_box_detection_results",
                      "ocr_node_name_results", "claude_node_name_review_results"):
            if other == key:
                continue
            o = self._find_key(other)
            if o is not None and o > at:
                limit = min(limit, o)
        end = d.rfind(b"]", start, limit)
        if end < 0:
            end = skip_val(d, start) - 1
        return (start, end + 1)

    def _index_pages(self):
        """用 media_type 当锚点找每页元素（纯 C 速度的 find，不整份扫）。"""
        d = self.raw
        pos = 0
        while True:
            mt = d.find(b'"media_type"', pos)
            if mt < 0:
                break
            pos = mt + 1
            pn_at = d.rfind(b'"page_number"', max(0, mt - 400), mt)
            if pn_at < 0:
                continue
            colon = d.find(b":", pn_at, mt)
            m = re.match(rb"\s*(\d+)", d[colon + 1:colon + 32])
            if not m:
                continue
            number = int(m.group(1))
            width = height = 0
            for key, which in ((b'"width"', "w"), (b'"height"', "h")):
                at = d.find(key, mt, mt + 600)
                if at < 0:
                    continue
                c2 = d.find(b":", at, at + 20)
                m2 = re.match(rb"\s*(\d+)", d[c2 + 1:c2 + 32])
                if m2:
                    if which == "w":
                        width = int(m2.group(1))
                    else:
                        height = int(m2.group(1))
            pk = d.find(b'"png_base64"', mt, mt + 4000)
            q1 = q2 = -1
            if pk >= 0:
                q1 = d.find(b'"', pk + 12)
                q2 = d.find(b'"', q1 + 1)
            # 没有内嵌图片也要登记这一页（只存检测结果的 JSON 就是这样），
            # 底图到时候用 PDF 现渲染。
            self.pages[number] = {"page_number": number, "width": width,
                                  "height": height,
                                  "png_span": ((q1 + 1, q2) if 0 <= q1 < q2 else None)}

    def page_numbers(self):
        return sorted(self.pages)

    def png_bytes(self, number):
        import base64
        span = self.pages[number].get("png_span")
        if not span:
            raise RuntimeError("第 %s 页没有内嵌图片" % number)
        return base64.b64decode(self.raw[span[0]:span[1]])

    def _elements(self, key):
        """[{page, span, data_span}]，第一次用到才建。"""
        sec = self.sections.get(key)
        if sec is None:
            return []
        if sec["elements"] is None:
            d = self.raw
            start, end = sec["span"]
            out = []
            i = start + 1
            while True:
                i = skip_ws(d, i)
                if i >= end or d[i] == 0x5D:
                    break
                s = i
                e = skip_val(d, i)
                sub = d[s:e]
                try:
                    spans = top_spans(sub)
                    pn = int(json.loads(sub[spans["page_number"][0]:spans["page_number"][1]]))
                    ds, de = spans["data"]
                    out.append({"page": pn, "span": (s, e),
                                "data_span": (s + ds, s + de)})
                except Exception:
                    pass
                i = skip_ws(d, e)
                if i < len(d) and d[i] == 0x2C:
                    i += 1
            sec["elements"] = out
        return sec["elements"]

    def element_for(self, key, page_number):
        for el in self._elements(key):
            if el["page"] == page_number:
                return el
        return None

    def page_data(self, key, page_number):
        el = self.element_for(key, page_number)
        if not el:
            return None
        a, b = el["data_span"]
        return json.loads(self.raw[a:b])

    @staticmethod
    def _field_of(section):
        return {TRACKER_SECTION: "tracker", BOX_SECTION: "box",
                OCR_SECTION: "ocr"}[section]

    def save(self, dest, modified):
        """modified: {页号: {"tracker": dict, "box": dict, "ocr": list}}
        只替换这些页所在的段落，其余逐字节照搬。"""
        jobs = []
        for key in SECTION_ORDER:
            field = self._field_of(key)
            pages = {p: m for p, m in modified.items() if m.get(field) is not None}
            sec = self.sections.get(key)
            if not pages or not sec:
                continue
            jobs.append((sec["span"][0], key, field, pages, sec))
        # 必须从后往前替换：前面的数组一变长，后面记录的偏移量就作废了。
        jobs.sort(key=lambda j: -j[0])
        out = self.raw
        for a, key, field, pages, sec in jobs:
            parts = []
            seen = set()
            for el in self._elements(key):
                seen.add(el["page"])
                if el["page"] in pages:
                    elem = {"page_number": el["page"], "data": pages[el["page"]][field]}
                    parts.append(json.dumps(elem, ensure_ascii=False).encode("utf-8"))
                else:
                    s, e = el["span"]
                    parts.append(self.raw[s:e])
            # 原文件里没有这一页的记录（比如原来没检测到东西的页，现在手工画了框）：
            # 补一条，否则新画的框存不进去。
            for p in sorted(p for p in pages if p not in seen):
                elem = {"page_number": p, "data": pages[p][field]}
                parts.append(json.dumps(elem, ensure_ascii=False).encode("utf-8"))
            new_arr = b"[\n    " + b",\n    ".join(parts) + b"\n  ]"
            b = sec["span"][1]
            out = out[:a] + new_arr + out[b:]
        tmp = dest + ".part"
        with open(tmp, "wb") as f:
            f.write(out)
        os.replace(tmp, dest)


class PageModel:
    """一页的框 + 名字。shapes 是纯 dict，界面和自检共用。"""

    def __init__(self, dbg, page_number):
        self.dbg = dbg
        self.page = page_number
        info = dbg.pages[page_number]
        self.width = info["width"] or 6000
        self.height = info["height"] or 4000
        self.shapes = []
        self.dirty = False
        self._orig_tracker = None
        self._orig_box = None
        self._orig_ocr = None
        self.load()

    def load(self):
        dbg = self.dbg
        self._orig_tracker = dbg.page_data(TRACKER_SECTION, self.page) or {}
        self._orig_box = dbg.page_data(BOX_SECTION, self.page) or {}
        self._orig_ocr = dbg.page_data(OCR_SECTION, self.page) or []

        ocr_by_key = {}
        for idx, rec in enumerate(self._orig_ocr):
            nb = rec.get("node_bbox") or {}
            if all(k in nb for k in ("x1", "y1", "x2", "y2")):
                ocr_by_key[round_box_key(nb)] = idx

        self.shapes = []
        for det in (self._orig_tracker.get("detections") or []):
            b = det.get("bbox") or {}
            if not all(k in b for k in ("x1", "y1", "x2", "y2")):
                continue
            label = (det.get("label") or "").strip() or "Tracker"
            ocr_index, name = None, ""
            if label.lower() == "node":
                ocr_index = ocr_by_key.get(round_box_key(b))
                if ocr_index is not None:
                    rec = self._orig_ocr[ocr_index]
                    name = (rec.get("final_node_name")
                            or rec.get("preliminary_node_name") or "").strip()
            self.shapes.append({
                "label": label, "name": name,
                "bbox": [float(b["x1"]), float(b["y1"]), float(b["x2"]), float(b["y2"])],
                "confidence": det.get("confidence"),
                "class_id": det.get("class_id"),
                "source": det.get("source") or "manual",
                "raw": det.get("raw") or {},
                "ocr_index": ocr_index,
            })
        for det in (self._orig_box.get("detections") or []):
            b = det.get("bbox") or {}
            if not all(k in b for k in ("x1", "y1", "x2", "y2")):
                continue
            self.shapes.append({
                "label": (det.get("label") or "Box").strip(),
                "name": (det.get("description") or "").strip(),
                "bbox": [float(b["x1"]), float(b["y1"]), float(b["x2"]), float(b["y2"])],
                "confidence": det.get("confidence"),
                "class_id": det.get("class_id"),
                "source": det.get("source") or "manual",
                "raw": det.get("raw") or {},
                "ocr_index": None,
            })

    def counts(self):
        c = {k: 0 for k in CLASSES}
        for s in self.shapes:
            c[s["label"]] = c.get(s["label"], 0) + 1
        return c

    def _det(self, s):
        cid = s.get("class_id")
        return {
            "label": s["label"],
            "confidence": s.get("confidence"),
            "class_id": cid if cid is not None else DEFAULT_CLASS_ID.get(s["label"], 0),
            "bbox": {"x1": s["bbox"][0], "y1": s["bbox"][1],
                     "x2": s["bbox"][2], "y2": s["bbox"][3]},
            "source": s.get("source") or "manual",
            "raw": s.get("raw") or {},
        }

    def tracker_data(self):
        data = copy.deepcopy(self._orig_tracker) if self._orig_tracker else {
            "model_type": "tracker", "coordinates": "original_page_pixels",
            "detections": [], "error": None}
        data["detections"] = [self._det(s) for s in self.shapes
                              if s["label"] in ("Node", "Tracker")]
        return data

    def box_data(self):
        data = copy.deepcopy(self._orig_box) if self._orig_box else {
            "model_type": "box", "detections": [], "error": None}
        data["detections"] = [self._det(s) for s in self.shapes if s["label"] == "Box"]
        return data

    def ocr_data(self):
        """Node 框 -> ocr 记录一一对应；人改的名字写进 final_node_name。"""
        orig = self._orig_ocr or []
        used = set()
        for rec in orig:
            try:
                used.add(int(rec.get("node_index")))
            except Exception:
                pass
        nxt = 1
        out = []
        for s in self.shapes:
            if s["label"] != "Node":
                continue
            idx = s.get("ocr_index")
            if idx is not None and 0 <= idx < len(orig):
                rec = copy.deepcopy(orig[idx])
            else:
                while nxt in used:
                    nxt += 1
                used.add(nxt)
                rec = {
                    "node_index": nxt,
                    "entity_id": "p%d:node:%d" % (self.page, nxt),
                    "readings": [],
                    "selected": {"text": s["name"], "angle_deg": 0, "confidence": None},
                    "matched_table_name": None,
                    "preliminary_node_name": s["name"],
                    "error": None,
                }
            rec["node_bbox"] = {"x1": s["bbox"][0], "y1": s["bbox"][1],
                                "x2": s["bbox"][2], "y2": s["bbox"][3]}
            rec["final_node_name"] = s["name"]
            out.append(rec)
        return out

    def result(self):
        return {"tracker": self.tracker_data(), "box": self.box_data(),
                "ocr": self.ocr_data()}


def selftest(src, out=None):
    """无界面走一遍：载入 -> 改框改名 -> 另存 -> 用下游代码验证。"""
    here = os.path.dirname(os.path.abspath(__file__))
    out = out or os.path.join(app_dir(), "selftest_annotated.json")
    print("源文件:", src)
    dbg = DebugJson(src)
    pgs = dbg.page_numbers()
    print("页数 %d（%d..%d），读入 %.2fs，%.1f MB"
          % (len(pgs), pgs[0], pgs[-1], dbg.load_seconds, dbg.size / 1048576))

    page = pgs[0]
    t0 = time.time()
    pm = PageModel(dbg, page)
    c0 = pm.counts()
    print("第 %d 页解析 %.2fs：Node %d / Tracker %d / Box %d"
          % (page, time.time() - t0, c0["Node"], c0["Tracker"], c0["Box"]))

    nodes = [s for s in pm.shapes if s["label"] == "Node"]
    trks = [s for s in pm.shapes if s["label"] == "Tracker"]
    if nodes:
        n0 = nodes[0]
        print("  原名字:", n0["name"], "原位置: %.0f,%.0f" % (n0["bbox"][0], n0["bbox"][1]))
        n0["bbox"] = [n0["bbox"][0] + 12, n0["bbox"][1] + 12,
                      n0["bbox"][2] + 12, n0["bbox"][3] + 12]
        n0["name"] = "SELFTEST-LBD-99"
    if len(trks) > 1:
        t = trks[-1]
        pm.shapes.append({"label": "Tracker", "name": "", "confidence": None,
                          "class_id": 0, "source": "manual", "raw": {},
                          "ocr_index": None,
                          "bbox": [t["bbox"][0], t["bbox"][1] + 5,
                                   t["bbox"][2], t["bbox"][3] + 5]})
        pm.shapes.remove(trks[0])
    c1 = pm.counts()
    print("改动：Node %d->%d（首框平移 12px 并改名），Tracker %d->%d（末尾加一个、删首一个）"
          % (c0["Node"], c1["Node"], c0["Tracker"], c1["Tracker"]))

    t0 = time.time()
    dbg.save(out, {page: pm.result()})
    print("另存 %.2fs -> %s（%.1f MB）"
          % (time.time() - t0, out, os.path.getsize(out) / 1048576))

    sys.path.insert(0, os.path.join(os.path.dirname(here), "CAD-MAP-main", "编排器"))
    import lbd_regions as lr
    lines_path = os.path.join(here, "selftest_lines.txt")
    r = lr.extract_lines_from_debug(out, lines_path, prefix="STR")
    rows = open(lines_path, encoding="utf-8").read().splitlines()
    names = [ln.split("\t")[4] for ln in rows if "-LBD-" in ln.upper()]
    # 下游是按「名字以 STR 开头」认支架号的，LBD 行就是其余那些
    pcols = [ln.split("\t") for ln in rows if ln.split("\t")[1] == str(page)]
    page_str = [c[4] for c in pcols if c[4].upper().startswith("STR")]
    page_lbd = [c[4] for c in pcols if not c[4].upper().startswith("STR")]
    print("下游 extract_lines_from_debug：ok=%s lines=%s lbd=%s str=%s pages=%s"
          % (r.get("ok"), r.get("lines"), r.get("lbd"), r.get("str"), r.get("pages")))
    ok_name = "SELFTEST-LBD-99" in names
    ok_lbd = len(page_lbd) == c1["Node"]
    ok_str = len(page_str) == c1["Tracker"]
    print("改的名字被下游读到:", ok_name)
    print("第 %d 页 LBD 行数 == 该页 Node 数: %s (%d vs %d)"
          % (page, ok_lbd, len(page_lbd), c1["Node"]))
    print("第 %d 页 支架行数 == 该页 Tracker 数: %s (%d vs %d)"
          % (page, ok_str, len(page_str), c1["Tracker"]))
    print("名字示例:", names[:3])
    good = bool(r.get("ok")) and ok_name and ok_lbd and ok_str
    print("自检:", "通过" if good else "失败")
    return 0 if good else 1


def make_gui_classes():
    """延迟导入 Qt（自检模式不需要 Qt）。"""
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import (QAction, QBrush, QColor, QFont, QImage, QKeySequence,
                               QPainter, QPen, QPixmap)
    from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFormLayout,
                                   QGraphicsItem, QGraphicsRectItem, QGraphicsScene,
                                   QGraphicsView, QHBoxLayout, QLabel, QLineEdit,
                                   QMainWindow, QMessageBox, QPushButton, QStatusBar,
                                   QToolBar, QVBoxLayout, QWidget)

    COLORS = {"Node": QColor(255, 40, 40), "Tracker": QColor(0, 120, 255),
              "Box": QColor(0, 200, 0)}
    HANDLE_CURSORS = [Qt.CursorShape.SizeFDiagCursor,
                      Qt.CursorShape.SizeVerCursor,
                      Qt.CursorShape.SizeBDiagCursor,
                      Qt.CursorShape.SizeHorCursor,
                      Qt.CursorShape.SizeHorCursor,
                      Qt.CursorShape.SizeBDiagCursor,
                      Qt.CursorShape.SizeVerCursor,
                      Qt.CursorShape.SizeFDiagCursor]

    class BoxItem(QGraphicsRectItem):
        def __init__(self, shape):
            super().__init__(0, 0, shape["bbox"][2] - shape["bbox"][0],
                             shape["bbox"][3] - shape["bbox"][1])
            self.shape_data = shape          # 不能叫 self.shape：会盖掉 Qt 的虚函数 shape()
            self.setPos(shape["bbox"][0], shape["bbox"][1])
            self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                          | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
            self.setZValue(10)
            self.apply_pen()

        def apply_pen(self):
            c = COLORS.get(self.shape_data["label"], QColor(255, 0, 255))
            pen = QPen(c)
            pen.setCosmetic(True)
            pen.setWidthF(2.0)
            self.setPen(pen)
            self.setBrush(QBrush(QColor(c.red(), c.green(), c.blue(), 26)))

        def scene_box(self):
            r, p = self.rect(), self.pos()
            return [p.x(), p.y(), p.x() + r.width(), p.y() + r.height()]

        def sync_shape(self):
            self.shape_data["bbox"] = self.scene_box()

        def itemChange(self, change, value):
            if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
                self.sync_shape()
            return super().itemChange(change, value)

        def view_scale(self):
            views = self.scene().views() if self.scene() else []
            return views[0].transform().m11() if views else 1.0

        def paint(self, painter, option, widget=None):
            super().paint(painter, option, widget)
            sc = self.view_scale()
            name = self.shape_data.get("name") or ""
            if name and sc > 0.06:
                f = QFont()
                f.setPixelSize(46)
                f.setBold(True)
                painter.setFont(f)
                painter.setPen(QPen(QColor(0, 150, 0)))
                painter.drawText(QPointF(4, -8), name)
            if self.isSelected():
                h = 9.0 / max(sc, 1e-6)
                r = self.rect()
                pts = [(r.left(), r.top()), (r.center().x(), r.top()),
                       (r.right(), r.top()), (r.left(), r.center().y()),
                       (r.right(), r.center().y()), (r.left(), r.bottom()),
                       (r.center().x(), r.bottom()), (r.right(), r.bottom())]
                painter.setBrush(QBrush(QColor(255, 255, 255)))
                pen = QPen(QColor(0, 0, 0))
                pen.setCosmetic(True)
                painter.setPen(pen)
                for x, y in pts:
                    painter.drawRect(QRectF(x - h / 2, y - h / 2, h, h))

    class Canvas(QGraphicsView):
        def __init__(self, win):
            super().__init__()
            self.win = win
            self.mode = "select"
            self._pan = False
            self._pan_pt = None
            self._rubber = None
            self._origin = None
            self._resize = None
            self.setRenderHints(QPainter.RenderHint.Antialiasing
                                | QPainter.RenderHint.SmoothPixmapTransform)
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self.setBackgroundBrush(QBrush(QColor(30, 30, 30)))
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        def set_mode(self, mode):
            self.mode = mode
            if mode == "select":
                self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
                self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            else:
                self.setDragMode(QGraphicsView.DragMode.NoDrag)
                self.viewport().setCursor(Qt.CursorShape.CrossCursor)

        def cancel_draw(self):
            """画到一半按 ESC：把临时框丢掉。返回是不是真的取消了。"""
            if self._rubber is not None:
                self.scene().removeItem(self._rubber)
                self._rubber = None
                self._origin = None
                return True
            return False

        def keyPressEvent(self, ev):
            # 键盘统一交给主窗口处理（ESC/Delete/A/D…），避免两处各一套
            self.win.keyPressEvent(ev)

        def wheelEvent(self, ev):
            f = 1.18 if ev.angleDelta().y() > 0 else 1 / 1.18
            cur = self.transform().m11()
            if 0.01 < cur * f < 40:
                self.scale(f, f)

        def mousePressEvent(self, ev):
            if ev.button() == Qt.MouseButton.MiddleButton:
                self._pan = True
                self._pan_pt = ev.position()
                self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
                return
            if ev.button() == Qt.MouseButton.LeftButton and self.mode == "select":
                it = self.win.current_item()
                if it is not None:
                    sp = self.mapToScene(ev.position().toPoint())
                    idx = self.handle_at(it, sp)
                    if idx is not None:
                        self._resize = {"item": it, "idx": idx, "start": sp,
                                        "box": it.scene_box()}
                        self.win.begin_change()
                        return
            if ev.button() == Qt.MouseButton.LeftButton and self.mode != "select":
                sp = self.mapToScene(ev.position().toPoint())
                self._origin = sp
                c = COLORS.get(self.mode, QColor(255, 0, 255))
                pen = QPen(c)
                pen.setCosmetic(True)
                pen.setWidthF(2.0)
                self._rubber = self.scene().addRect(
                    QRectF(sp, sp), pen,
                    QBrush(QColor(c.red(), c.green(), c.blue(), 40)))
                self._rubber.setZValue(50)
                return
            self.win.begin_change()
            super().mousePressEvent(ev)

        def mouseMoveEvent(self, ev):
            if self._pan and self._pan_pt is not None:
                d = ev.position() - self._pan_pt
                self._pan_pt = ev.position()
                self.horizontalScrollBar().setValue(
                    int(self.horizontalScrollBar().value() - d.x()))
                self.verticalScrollBar().setValue(
                    int(self.verticalScrollBar().value() - d.y()))
                return
            if self._rubber is not None and self._origin is not None:
                sp = self.mapToScene(ev.position().toPoint())
                self._rubber.setRect(QRectF(self._origin, sp).normalized())
                return
            if self._resize is not None:
                d = self._resize
                p = self.mapToScene(ev.position().toPoint())
                box = self.apply_handle(d["box"], d["idx"],
                                        p.x() - d["start"].x(), p.y() - d["start"].y())
                it = d["item"]
                it.setPos(box[0], box[1])
                it.setRect(QRectF(0, 0, box[2] - box[0], box[3] - box[1]))
                it.sync_shape()
                it.update()
                return
            if not self._pan and self.mode == "select":
                it = self.win.current_item()
                if it is not None:
                    sp = self.mapToScene(ev.position().toPoint())
                    i = self.handle_at(it, sp)
                    self.viewport().setCursor(HANDLE_CURSORS[i] if i is not None
                                              else Qt.CursorShape.ArrowCursor)
            super().mouseMoveEvent(ev)

        def mouseReleaseEvent(self, ev):
            if ev.button() == Qt.MouseButton.MiddleButton:
                self._pan = False
                self.viewport().setCursor(
                    Qt.CursorShape.CrossCursor if self.mode != "select"
                    else Qt.CursorShape.ArrowCursor)
                return
            if self._rubber is not None and ev.button() == Qt.MouseButton.LeftButton:
                r = self._rubber.rect()
                self.scene().removeItem(self._rubber)
                self._rubber = None
                self._origin = None
                if r.width() >= 3 and r.height() >= 3:
                    self.win.add_shape(self.mode,
                                       [r.left(), r.top(), r.right(), r.bottom()])
                return
            if self._resize is not None and ev.button() == Qt.MouseButton.LeftButton:
                self._resize = None
                self.win.end_change()
                self.win.on_selection()
                return
            super().mouseReleaseEvent(ev)
            self.win.end_change()

        @staticmethod
        def handle_points(box):
            x1, y1, x2, y2 = box
            cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            return [(x1, y1), (cx, y1), (x2, y1), (x1, cy),
                    (x2, cy), (x1, y2), (cx, y2), (x2, y2)]

        @staticmethod
        def apply_handle(box, idx, dx, dy):
            """按第 idx 个控制点拖动 (dx,dy)，返回新的 [x1,y1,x2,y2]（允许拖过头翻转）。"""
            x1, y1, x2, y2 = box
            if idx in (0, 3, 5):
                x1 += dx
            if idx in (2, 4, 7):
                x2 += dx
            if idx in (0, 1, 2):
                y1 += dy
            if idx in (5, 6, 7):
                y2 += dy
            nx1, nx2 = (x1, x2) if x1 <= x2 else (x2, x1)
            ny1, ny2 = (y1, y2) if y1 <= y2 else (y2, y1)
            return [nx1, ny1, nx2, ny2]

        def handle_at(self, item, scene_pos):
            """鼠标是不是落在选中框的控制点上，返回控制点序号。"""
            sc = max(self.transform().m11(), 1e-6)
            tol = 9.0 / sc * 0.8
            for i, (x, y) in enumerate(self.handle_points(item.scene_box())):
                if abs(scene_pos.x() - x) <= tol and abs(scene_pos.y() - y) <= tol:
                    return i
            return None

    return BoxItem, Canvas, COLORS


def run_gui(path=None, smoke=False, memtest=0.0):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QAction, QImage, QKeySequence, QPixmap
    from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFormLayout,
                                   QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                                   QMessageBox, QPushButton, QStatusBar, QToolBar,
                                   QVBoxLayout, QWidget)

    BoxItem, Canvas, COLORS = make_gui_classes()
    MODE_TEXT = {"select": "选择", "Node": "画 Node", "Tracker": "画 Tracker",
                 "Box": "画 Box"}

    class Win(QMainWindow):
        def __init__(self, src=None):
            super().__init__()
            self.setWindowTitle("LBD 标注工具 v0.1")
            self.resize(1500, 950)
            self.dbg = None
            self.page = None
            self.pm = None
            self.items = []
            self.undo = []
            self.redo = []
            self._pending = None
            self.edited = {}
            self._pixmap = None
            self.clip = []                 # 复制/粘贴框用的内部剪贴板
            self._paste_n = 0
            self.settings = load_settings()
            self.pdf = self.settings.get("pdf") or ""
            self.dpi = int(self.settings.get("dpi") or 0)
            self.poppler = find_pdftoppm()
            self.renderer = Renderer(self.poppler,
                                     os.path.join(app_dir(), "render_cache"))
            self._img_note = ""

            self.scene = self._make_scene()
            self.canvas = Canvas(self)
            self.canvas.setScene(self.scene)

            tb = QToolBar("工具栏")
            tb.setMovable(False)
            self.addToolBar(tb)

            act = QAction("打开 JSON", self)
            act.triggered.connect(self.on_open)
            tb.addAction(act)
            act = QAction("打开 PDF（无 JSON，直接标注）", self)
            act.triggered.connect(self.on_open_pdf)
            tb.addAction(act)
            tb.addSeparator()
            for m in ("select",) + CLASSES:
                a = QAction(MODE_TEXT[m], self)
                a.setCheckable(True)
                a.triggered.connect(lambda _c=False, mm=m: self.set_mode(mm))
                tb.addAction(a)
                setattr(self, "act_" + m, a)
            tb.addSeparator()
            a = QAction("撤销", self)
            a.setShortcut(QKeySequence("Ctrl+Z"))
            a.triggered.connect(self.on_undo)
            tb.addAction(a)
            a = QAction("重做", self)
            a.setShortcuts([QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")])
            a.setToolTip("重做刚撤销的操作（Ctrl+Y 或 Ctrl+Shift+Z）")
            a.triggered.connect(self.on_redo)
            tb.addAction(a)
            a = QAction("复制框", self)
            a.setToolTip("把选中的框复制到剪贴板（Ctrl+C），可以粘到别的页")
            a.triggered.connect(self.on_copy)
            tb.addAction(a)
            a = QAction("粘贴框", self)
            a.setToolTip("粘贴刚复制的框（Ctrl+V），每贴一次自动错开一点")
            a.triggered.connect(self.on_paste)
            tb.addAction(a)
            a = QAction("适应窗口", self)
            a.setShortcut(QKeySequence("Ctrl+0"))
            a.triggered.connect(self.fit)
            tb.addAction(a)
            a = QAction("100%", self)
            a.triggered.connect(self.zoom_reset)
            tb.addAction(a)
            tb.addSeparator()
            a = QAction("另存为…", self)
            a.setShortcut(QKeySequence("Ctrl+S"))
            a.triggered.connect(self.on_save_as)
            tb.addAction(a)
            a = QAction("覆盖原文件", self)
            a.triggered.connect(self.on_save_over)
            tb.addAction(a)

            tb.addSeparator()
            tb.addWidget(QLabel("  底图 "))
            self.cmb_dpi = QComboBox()
            for text, val in (("内嵌图（快）", 0), ("250 DPI", 250),
                              ("333 DPI", 333), ("400 DPI", 400)):
                self.cmb_dpi.addItem(text, val)
            i = self.cmb_dpi.findData(self.dpi)
            self.cmb_dpi.setCurrentIndex(i if i >= 0 else 0)
            self.cmb_dpi.currentIndexChanged.connect(self.on_dpi_changed)
            tb.addWidget(self.cmb_dpi)
            self.btn_pdf = QPushButton("选 PDF…")
            self.btn_pdf.clicked.connect(self.on_pick_pdf)
            tb.addWidget(self.btn_pdf)
            self.update_pdf_button()

            side = QWidget()
            sl = QVBoxLayout(side)
            self.lbl_info = QLabel("用「打开 JSON」载入识别结果")
            self.lbl_info.setWordWrap(True)
            sl.addWidget(self.lbl_info)
            nav = QHBoxLayout()
            b = QPushButton("◀ 上一页")
            b.clicked.connect(lambda: self.goto_offset(-1))
            nav.addWidget(b)
            self.cmb_page = QComboBox()
            self.cmb_page.currentIndexChanged.connect(self.on_page_combo)
            nav.addWidget(self.cmb_page, 1)
            b = QPushButton("下一页 ▶")
            b.clicked.connect(lambda: self.goto_offset(1))
            nav.addWidget(b)
            sl.addLayout(nav)
            sl.addWidget(QLabel("———— 选中的框 ————"))
            form = QFormLayout()
            self.cmb_label = QComboBox()
            self.cmb_label.addItems(list(CLASSES))
            self.cmb_label.currentIndexChanged.connect(self.on_label_changed)
            form.addRow("类别", self.cmb_label)
            self.ed_name = QLineEdit()
            self.ed_name.editingFinished.connect(self.on_name_changed)
            form.addRow("LBD 名字", self.ed_name)
            self.lbl_bbox = QLabel("-")
            form.addRow("位置", self.lbl_bbox)
            sl.addLayout(form)
            self.btn_del = QPushButton("删除这个框（Delete）")
            self.btn_del.clicked.connect(self.on_delete)
            sl.addWidget(self.btn_del)
            sl.addStretch(1)
            side.setMaximumWidth(330)

            central = QWidget()
            cl = QHBoxLayout(central)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.addWidget(self.canvas, 1)
            cl.addWidget(side)
            self.setCentralWidget(central)

            self.setStatusBar(QStatusBar())
            self.scene.selectionChanged.connect(self.on_selection)
            self.set_mode("select")
            self.refresh_info()
            if src:
                self.load_file(src)

        def _make_scene(self):
            from PySide6.QtWidgets import QGraphicsScene
            return QGraphicsScene(self)

        # ---------------- 载入与翻页
        def on_open(self):
            p, _ = QFileDialog.getOpenFileName(self, "选择识别结果 JSON", "",
                                               "JSON (*.json)")
            if p:
                self.load_file(p)

        def on_open_pdf(self):
            """没有识别结果时，直接打开一份 PDF 从零标注。"""
            p, _ = QFileDialog.getOpenFileName(self, "选择要直接标注的 PDF", "",
                                               "PDF (*.pdf)")
            if not p:
                return
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                doc = BlankDoc(p, dpi=float(self.dpi or 0) or 250.0)
            except Exception as e:
                QApplication.restoreOverrideCursor()
                QMessageBox.critical(self, "读不了这份 PDF", "%s" % e)
                return
            QApplication.restoreOverrideCursor()
            if not doc.page_numbers():
                QMessageBox.warning(
                    self, "读不出页数",
                    "没能从这份 PDF 读出页码/页尺寸。\n\n"
                    "这条路径要用 poppler 的 pdfinfo.exe（和渲染底图用的 pdftoppm 在一起）。")
                return
            self.dbg = doc
            self.pdf = p
            self.settings["pdf"] = p
            save_settings(self.settings)
            self.update_pdf_button()
            self.edited.clear()
            self.undo.clear()
            self.redo.clear()
            self.cmb_page.blockSignals(True)
            self.cmb_page.clear()
            for n in doc.page_numbers():
                self.cmb_page.addItem(str(n), n)
            self.cmb_page.blockSignals(False)
            self.setWindowTitle("LBD 标注工具 v0.1 — %s（直接标注，无识别结果）"
                                % os.path.basename(p))
            self.statusBar().showMessage("空白文档：%d 页，框从零开始画；保存会生成识别结果 JSON"
                                         % len(doc.page_numbers()), 8000)
            self.goto_page(doc.page_numbers()[0])

        def load_file(self, path):
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                self.dbg = DebugJson(path)
            except Exception as e:
                QApplication.restoreOverrideCursor()
                QMessageBox.critical(self, "读不了", "%s" % e)
                return
            QApplication.restoreOverrideCursor()
            self.undo.clear()
            # 记住这份 JSON：打包成 exe 后双击就能接着打开上次那份
            self.settings["json"] = os.path.abspath(path)
            save_settings(self.settings)
            pgs = self.dbg.page_numbers()
            if not pgs:
                raw = getattr(self.dbg, "raw", b"") or b""
                marks = []
                for key, desc in ((b'"input_data"', "input_data（但没有 pages）"),
                                  (b'"pages"', "pages 字段"),
                                  (b'"yolo_tracker_detection_results"', "yolo_tracker_detection_results（识别结果的框）"),
                                  (b'"ocr_node_name_results"', "ocr_node_name_results（编号名字）"),
                                  (b'"shapes"', "shapes（X-AnyLabeling / labelme 标注文件）"),
                                  (b'"imagePath"', "imagePath（标注文件里的图片名）"),
                                  (b'"lbd_regions"', "lbd_regions（区域范围导出）"),
                                  (b'"config"', "config（配置文件）")):
                    if key in raw:
                        marks.append(desc)
                QMessageBox.warning(
                    self, "这份 JSON 里没有页面",
                    "没找到 input_data.pages（每页的页号和尺寸）——"
                    "标注工具靠它把标注定位到页面上。\n\n"
                    "这份文件里看到：\n  %s\n\n"
                    "要标注请打开完整的「识别结果」JSON（agent3-debug 那份，"
                    "input_data.pages 里带每页宽高）。" % ("\n  ".join(marks) or "（没有认出来的内容）"))
                return
            # PDF 对不上就纠正：文件名里没有 project_name 的，说明是别的项目的图纸
            if self.pdf and not os.path.exists(self.pdf):
                self.pdf = ""
            pname = project_name(path)
            if self.pdf and pname and pname.lower() not in os.path.basename(self.pdf).lower():
                better = guess_pdf(path, exact_only=True)
                if better:
                    self.pdf = better
            if not self.pdf:
                self.pdf = guess_pdf(path)
            if self.pdf:
                self.settings["pdf"] = self.pdf
                save_settings(self.settings)
                self.update_pdf_button()
            self.cmb_page.blockSignals(True)
            self.cmb_page.clear()
            for n in self.dbg.page_numbers():
                self.cmb_page.addItem(str(n), n)
            self.cmb_page.blockSignals(False)
            self.setWindowTitle("LBD 标注工具 v0.1 — %s" % os.path.basename(path))
            self.goto_page(pgs[0])

        def goto_page(self, number):
            if not self.dbg or number not in self.dbg.pages:
                return
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                self._stash_dirty()
                # 这一页改过就还用内存里那份，别重新从文件读（否则改动会没）
                self.pm = self.edited.get(number) or PageModel(self.dbg, number)
                self._img_note = ""
                img = None
                try:
                    img, self._img_note = self.load_image(number)
                except Exception as e:
                    self._img_note = "底图没出来：%s" % e
                if img is None or img.isNull():
                    img = QImage(600, 400, QImage.Format.Format_RGB32)
                    img.fill(0x303030)
                self._pixmap = QPixmap.fromImage(img)
            finally:
                QApplication.restoreOverrideCursor()
            self.page = number
            self._rebuild_items()
            i = self.cmb_page.findData(number)
            if i >= 0:
                self.cmb_page.blockSignals(True)
                self.cmb_page.setCurrentIndex(i)
                self.cmb_page.blockSignals(False)
            self.fit()
            self.refresh_info()
            self.on_selection()
            self.prefetch_next()

        def prefetch_next(self):
            """后台把下一页渲染好，翻页就不用等。"""
            if self.dpi <= 0 or not self.pdf or not self.poppler:
                return
            pgs = self.dbg.page_numbers()
            i = pgs.index(self.page) + 1
            if i >= len(pgs):
                return
            page, dpi, pdf = pgs[i], self.dpi, self.pdf
            if os.path.exists(self.renderer.target(pdf, page, dpi)):
                return

            def work():
                try:
                    self.renderer.render(pdf, page, dpi)
                except Exception:
                    pass

            threading.Thread(target=work, daemon=True).start()

        def _stash_dirty(self):
            """离开一页前，把改过的页留下来，保存时一起写。"""
            if self.pm is not None and self.pm.dirty:
                self.edited[self.pm.page] = self.pm

        def _rebuild_items(self):
            self.scene.clear()
            self.items = []
            self.scene.setSceneRect(0, 0, self.pm.width, self.pm.height)
            item = self.scene.addPixmap(self._pixmap)
            # 场景坐标始终用 JSON 里的原始坐标（6000×4000）；
            # 高分辨率底图按比例缩回来放，放大看时 Qt 会用它的原始像素。
            item.setScale(self.pm.width / float(self._pixmap.width() or self.pm.width))
            item.setZValue(0)
            for s in self.pm.shapes:
                it = BoxItem(s)
                self.scene.addItem(it)
                self.items.append(it)

        def load_image(self, page):
            """返回 (QImage, 说明文字)。dpi=0 用 JSON 内嵌图，否则重渲染 PDF。"""
            info = self.dbg.pages.get(page) or {}
            if self.dpi <= 0 and info.get("png_span"):
                img = QImage.fromData(self.dbg.png_bytes(page))
                return img, "内嵌图 %d×%d（约 167 dpi）" % (img.width(), img.height())
            if not self.poppler:
                raise RuntimeError("找不到 pdftoppm/poppler")
            if not self.pdf or not os.path.exists(self.pdf):
                raise RuntimeError("这份 JSON 没有内嵌图，需要点「选 PDF…」指定对应的 PDF")
            dpi = self.dpi if self.dpi > 0 else 250      # 没内嵌图时用 250 DPI 渲染
            t0 = time.time()
            self.statusBar().showMessage(
                "正在用 %s 重渲染第 %d 页（%d DPI）…"
                % (os.path.basename(self.pdf), page, dpi))
            QApplication.processEvents()
            path = self.renderer.render(self.pdf, page, dpi)
            img = QImage(path)
            if img.isNull():
                raise RuntimeError("渲染结果读不出来")
            k = img.width() / float(self.dbg.pages[page]["width"] or img.width())
            return img, "%d DPI 重渲染 %d×%d（%.2f 倍，%.1fs）" % (
                dpi, img.width(), img.height(), k, time.time() - t0)

        def on_dpi_changed(self, _i):
            want = int(self.cmb_dpi.currentData() or 0)
            if want >= 400 and self.dbg:
                mem = self.pm.width * 400 // 167 * self.pm.height * 400 // 167 * 4 / 1048576.0
                if QMessageBox.question(
                        self, "内存提醒",
                        "400 DPI 时每页底图约占 %.0f MB 内存，机器不够会卡甚至崩。\n"
                        "日常建议 250 或 333 DPI。要继续吗？" % mem
                ) != QMessageBox.StandardButton.Yes:
                    self.cmb_dpi.blockSignals(True)
                    i = self.cmb_dpi.findData(self.dpi)
                    self.cmb_dpi.setCurrentIndex(i if i >= 0 else 0)
                    self.cmb_dpi.blockSignals(False)
                    return
            self.dpi = want
            self.settings["dpi"] = self.dpi
            save_settings(self.settings)
            if self.dbg:
                self.goto_page(self.page)

        def on_pick_pdf(self):
            p, _ = QFileDialog.getOpenFileName(self, "选择这份识别结果对应的 PDF", "",
                                               "PDF (*.pdf)")
            if not p:
                return
            self.pdf = p
            self.settings["pdf"] = p
            if self.dpi <= 0:
                # 底图还停在内嵌图的话，换 PDF 看不出任何变化，直接切到 250 DPI
                self.dpi = 250
                self.settings["dpi"] = 250
                i = self.cmb_dpi.findData(250)
                if i >= 0:
                    self.cmb_dpi.blockSignals(True)
                    self.cmb_dpi.setCurrentIndex(i)
                    self.cmb_dpi.blockSignals(False)
            save_settings(self.settings)
            self.update_pdf_button()
            if self.dbg:
                self.goto_page(self.page)

        def update_pdf_button(self):
            if self.pdf:
                self.btn_pdf.setText("PDF：%s…" % os.path.basename(self.pdf)[:18])
            else:
                self.btn_pdf.setText("选 PDF…")
            self.btn_pdf.setToolTip(self.pdf or
                                    "选一份 PDF，再用 250/333/400 DPI 重渲染更清晰的底图")

        def goto_offset(self, d):
            if not self.dbg:
                return
            pgs = self.dbg.page_numbers()
            i = pgs.index(self.page) + d
            if 0 <= i < len(pgs):
                self.goto_page(pgs[i])

        def on_page_combo(self, _i):
            n = self.cmb_page.currentData()
            if n is not None and n != self.page:
                self.goto_page(n)

        def fit(self):
            if self.pm:
                self.canvas.fitInView(self.scene.sceneRect(),
                                      Qt.AspectRatioMode.KeepAspectRatio)

        def zoom_reset(self):
            self.canvas.resetTransform()

        # ---------------- 改动
        def begin_change(self):
            if self.pm:
                self._pending = [(i, dict(s)) for i, s in enumerate(self.pm.shapes)]

        def end_change(self):
            if not self.pm or self._pending is None:
                return
            now = [(i, dict(s)) for i, s in enumerate(self.pm.shapes)]
            if now != self._pending:
                self.undo.append((self.page, self._pending))
                del self.undo[:-50]        # 只留最近 50 步，别无限涨
                self.redo.clear()          # 有了新改动，"重做"就失效了（和常见编辑器一致）
                self.mark_dirty()
            self._pending = None

        def mark_dirty(self):
            if self.pm:
                self.pm.dirty = True
            self.refresh_info()

        def add_shape(self, label, bbox):
            if not self.pm:
                return
            s = {"label": label, "name": "", "bbox": bbox, "confidence": None,
                 "class_id": DEFAULT_CLASS_ID.get(label, 0), "source": "manual",
                 "raw": {}, "ocr_index": None}
            self.begin_change()
            self.pm.shapes.append(s)
            it = BoxItem(s)
            self.scene.addItem(it)
            self.items.append(it)
            self.scene.clearSelection()
            it.setSelected(True)
            self.end_change()
            if label == "Node":
                self.statusBar().showMessage("新加的 Node 请填 LBD 名字", 6000)

        def on_delete(self):
            if not self.pm:
                return
            sel = [i for i in self.scene.selectedItems() if isinstance(i, BoxItem)]
            if not sel:
                return
            self.begin_change()
            for it in sel:
                if it.shape_data in self.pm.shapes:
                    self.pm.shapes.remove(it.shape_data)
                if it in self.items:
                    self.items.remove(it)
                self.scene.removeItem(it)
            self.end_change()
            self.on_selection()

        def current_item(self):
            sel = [i for i in self.scene.selectedItems() if isinstance(i, BoxItem)]
            return sel[0] if sel else None

        def on_selection(self):
            it = self.current_item()
            self.cmb_label.blockSignals(True)
            self.ed_name.blockSignals(True)
            if it is None:
                self.ed_name.setText("")
                self.lbl_bbox.setText("-")
                self.ed_name.setEnabled(False)
                self.cmb_label.setEnabled(False)
                self.btn_del.setEnabled(False)
            else:
                self.ed_name.setEnabled(True)
                self.cmb_label.setEnabled(True)
                self.btn_del.setEnabled(True)
                self.ed_name.setText(it.shape_data.get("name") or "")
                i = self.cmb_label.findText(it.shape_data["label"])
                if i >= 0:
                    self.cmb_label.setCurrentIndex(i)
                b = it.scene_box()
                self.lbl_bbox.setText("%.0f, %.0f → %.0f, %.0f" % (b[0], b[1], b[2], b[3]))
            self.cmb_label.blockSignals(False)
            self.ed_name.blockSignals(False)

        def on_label_changed(self, _i):
            it = self.current_item()
            if it is None:
                return
            it.shape_data["label"] = self.cmb_label.currentText()
            it.shape_data["class_id"] = DEFAULT_CLASS_ID.get(it.shape_data["label"], 0)
            if it.shape_data["label"] != "Node":
                it.shape_data["name"] = ""
                self.ed_name.setText("")
            it.apply_pen()
            it.update()
            self.mark_dirty()

        def on_name_changed(self):
            it = self.current_item()
            if it is None:
                return
            txt = self.ed_name.text().strip()
            if txt == (it.shape_data.get("name") or ""):
                return
            it.shape_data["name"] = txt
            it.update()
            self.mark_dirty()

        def set_mode(self, mode):
            for m in ("select",) + CLASSES:
                getattr(self, "act_" + m).setChecked(m == mode)
            self.canvas.set_mode(mode)
            self.refresh_info()

        def refresh_info(self):
            if not (self.pm and self.dbg):
                self.statusBar().showMessage(
                    "点「打开 JSON」载入识别结果（默认不改原文件）")
                return
            c = self.pm.counts()
            src = ("底图 %d DPI" % self.dpi) if self.dpi > 0 else "底图 内嵌图"
            self.setWindowTitle("LBD 标注工具 v0.1 — %s ｜ %s"
                                % (os.path.basename(self.dbg.path), src))
            self.lbl_info.setText(
                "第 %d 页 / 共 %d 页\n坐标尺寸 %d × %d\n底图：%s\n"
                "Node %d　Tracker %d　Box %d%s"
                % (self.page, len(self.dbg.page_numbers()), self.pm.width,
                   self.pm.height, self._img_note or "（载入中）",
                   c["Node"], c["Tracker"], c.get("Box", 0),
                   "\n\n● 已修改，记得保存" if self.pm.dirty else ""))
            self.statusBar().showMessage(
                "模式：%s　拖框内=移动，拖白点=改大小，方向键=微调(Shift 加速)，"
                "Delete=删除，Ctrl+Z=撤销，中键拖动=平移，滚轮=缩放，A/D=翻页"
                % MODE_TEXT.get(self.canvas.mode, self.canvas.mode))

        def keyPressEvent(self, ev):
            k = ev.key()
            ctrl = bool(ev.modifiers() & Qt.KeyboardModifier.ControlModifier)
            if ctrl and k == Qt.Key.Key_C:
                self.on_copy()
                return
            if ctrl and k == Qt.Key.Key_V:
                self.on_paste()
                return
            if k == Qt.Key.Key_Escape:
                self.on_escape()
                return
            if k == Qt.Key.Key_Delete:
                self.on_delete()
                return
            if k in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
                it = self.current_item()
                if it is not None:
                    step = 10 if ev.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
                    dx = {Qt.Key.Key_Left: -step, Qt.Key.Key_Right: step}.get(k, 0)
                    dy = {Qt.Key.Key_Up: -step, Qt.Key.Key_Down: step}.get(k, 0)
                    self.begin_change()
                    b = it.scene_box()
                    it.setPos(b[0] + dx, b[1] + dy)
                    it.sync_shape()
                    self.end_change()
                    self.on_selection()
                    return
            if k == Qt.Key.Key_A:
                self.goto_offset(-1)
                return
            if k == Qt.Key.Key_D:
                self.goto_offset(1)
                return
            super().keyPressEvent(ev)

        def on_escape(self):
            """ESC：画到一半就丢掉当前这一笔；否则从画框模式退回选择模式。"""
            if self.canvas.cancel_draw():
                self.statusBar().showMessage("已取消这一笔", 3000)
                return
            if self.canvas.mode != "select":
                self.set_mode("select")
                self.statusBar().showMessage("已退出画框模式", 3000)

        def on_copy(self):
            sel = [i for i in self.scene.selectedItems() if isinstance(i, BoxItem)]
            if not sel:
                self.statusBar().showMessage("先选中要复制的框（可以框选多个）", 4000)
                return
            self.clip = [copy.deepcopy(it.shape_data) for it in sel]
            for s in self.clip:
                # 复制出来的是"新框"：不能再认原来那条编号记录，否则回写时两个框抢一条记录
                s["ocr_index"] = None
            self._paste_n = 0
            self.statusBar().showMessage(
                "已复制 %d 个框；切到目标页按 Ctrl+V 粘贴（每贴一次自动错开）" % len(self.clip), 6000)

        def on_paste(self):
            if not self.pm:
                return
            if not self.clip:
                self.statusBar().showMessage("剪贴板里还没有框：先选中再按 Ctrl+C", 4000)
                return
            self._paste_n += 1
            step = 24 * self._paste_n
            self.begin_change()
            self.scene.clearSelection()
            made = 0
            for s in self.clip:
                b = list(s["bbox"])
                x1 = min(max(0.0, b[0] + step), max(0.0, self.pm.width - 2.0))
                y1 = min(max(0.0, b[1] + step), max(0.0, self.pm.height - 2.0))
                x2 = min(max(x1 + 1.0, b[2] + step), float(self.pm.width))
                y2 = min(max(y1 + 1.0, b[3] + step), float(self.pm.height))
                ns = copy.deepcopy(s)
                ns["bbox"] = [x1, y1, x2, y2]
                ns["ocr_index"] = None
                self.pm.shapes.append(ns)
                it = BoxItem(ns)
                self.scene.addItem(it)
                self.items.append(it)
                it.setSelected(True)
                made += 1
            self.end_change()
            self.on_selection()
            self.statusBar().showMessage(
                "已粘贴 %d 个框（错开 %d 像素；再按 Ctrl+V 再贴一份）" % (made, step), 6000)

        def on_undo(self):
            if not self.undo:
                self.statusBar().showMessage("没有可撤销的操作（Ctrl+Y 可以重做）", 3000)
                return
            page, snap = self.undo.pop()
            self.redo.append((self.page, [(i, dict(s)) for i, s in enumerate(self.pm.shapes)]))
            self._restore(page, snap)
            self.statusBar().showMessage("已撤销；想还原按 Ctrl+Y", 4000)

        def on_redo(self):
            if not self.redo:
                self.statusBar().showMessage("没有可重做的操作", 3000)
                return
            page, snap = self.redo.pop()
            self.undo.append((self.page, [(i, dict(s)) for i, s in enumerate(self.pm.shapes)]))
            self._restore(page, snap)
            self.statusBar().showMessage("已重做", 3000)

        def _restore(self, page, snap):
            """把某一页恢复成快照的样子（撤销/重做共用）。"""
            if page != self.page:
                self.goto_page(page)
            self.pm.shapes = [dict(s) for _i, s in snap]
            self._rebuild_items()
            self.pm.dirty = True
            self.refresh_info()
            self.on_selection()

        # ---------------- 保存
        def do_save(self, dest, quiet=False):
            if not self.dbg:
                return 0
            self._stash_dirty()
            mod = {p: pm.result() for p, pm in self.edited.items()}
            pages = sorted(mod)
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                self.dbg.save(dest, mod)
                self.dbg = DebugJson(dest)
            finally:
                QApplication.restoreOverrideCursor()
            self.edited.clear()
            self.undo.clear()
            self.cmb_page.blockSignals(True)
            self.cmb_page.clear()
            for n in self.dbg.page_numbers():
                self.cmb_page.addItem(str(n), n)
            self.cmb_page.blockSignals(False)
            self.setWindowTitle("LBD 标注工具 v0.1 — %s" % os.path.basename(dest))
            keep = self.page if self.page in self.dbg.pages else self.dbg.page_numbers()[0]
            self.pm = None
            self.goto_page(keep)
            if not quiet:
                QMessageBox.information(
                    self, "已保存",
                    "写好了：\n%s\n\n写入的页：%s\n（没改过的页和段落是逐字节照搬的）"
                    % (dest, "、".join(str(p) for p in pages) if pages else "（没有改动）"))
            return len(mod)

        def on_save_as(self):
            if not self.dbg:
                return
            base = os.path.splitext(self.dbg.path)[0] + "_annotated.json"
            p, _ = QFileDialog.getSaveFileName(self, "另存标注结果", base,
                                               "JSON (*.json)")
            if p:
                self.do_save(p)

        def on_save_over(self):
            if not self.dbg:
                return
            src = self.dbg.path
            if QMessageBox.question(
                    self, "覆盖原文件",
                    "直接覆盖：\n%s\n\n（不留备份文件，覆盖后原内容就没了）\n继续吗？" % src
            ) != QMessageBox.StandardButton.Yes:
                return
            self.do_save(src)
            self.statusBar().showMessage("已覆盖原文件：%s" % src, 8000)

    app = QApplication.instance() or QApplication(sys.argv)
    win = Win(path)
    win.show()
    if memtest:
        print("READY dpi=%s 页=%s 框=%d 底图=%s"
              % (win.dpi, win.page, len(win.items), win._img_note), flush=True)
        time.sleep(float(memtest))
        return 0
    if smoke:
        if not path:
            print("smoke：没给 JSON 路径")
            return 2
        win.load_file(path)
        print("载入 OK：共 %d 页，第 %d 页 %d 个框"
              % (len(win.dbg.page_numbers()), win.page, len(win.items)))
        print("内存：载入后 %.0f MB（%s）"
              % (rss_mb(), win._img_note or "底图来源见下"))
        first = win.page
        win.add_shape("Node", [120, 120, 420, 900])
        it = win.current_item()
        it.shape_data["name"] = "SMOKE-LBD-001"
        it.update()
        win.on_selection()
        print("画框 OK：本页 %d 个框，选中类别 %s"
              % (len(win.items), it.shape_data["label"]))
        win.goto_offset(1)
        print("翻页 OK：第 %d 页 %d 个框" % (win.page, len(win.items)))
        win.goto_page(first)
        for i in list(win.items):
            if i.shape_data.get("name") == "SMOKE-LBD-001":
                win.scene.clearSelection()
                i.setSelected(True)
        win.on_delete()
        print("删除 OK：本页剩 %d 个框" % len(win.items))
        from PySide6.QtCore import QPointF
        from PySide6.QtTest import QTest
        from PySide6.QtCore import Qt as _Qt
        print("控制点计算检查:", Canvas.apply_handle([0, 0, 100, 100], 7, 50, 50),
              Canvas.apply_handle([0, 0, 100, 100], 0, -20, -20))
        win.scene.clearSelection()
        it0 = win.items[0]
        it0.setSelected(True)
        win.on_selection()
        before = it0.scene_box()
        hx, hy = Canvas.handle_points(before)[7]
        p0 = win.canvas.mapFromScene(QPointF(hx, hy))
        p1 = win.canvas.mapFromScene(QPointF(hx + 60, hy + 40))
        QTest.mousePress(win.canvas.viewport(), _Qt.MouseButton.LeftButton,
                         _Qt.KeyboardModifier.NoModifier, p0)
        QTest.mouseMove(win.canvas.viewport(), p1)
        QTest.mouseRelease(win.canvas.viewport(), _Qt.MouseButton.LeftButton,
                           _Qt.KeyboardModifier.NoModifier, p1)
        after = it0.scene_box()
        print("拉边改大小：%s -> %s"
              % (["%.0f" % v for v in before], ["%.0f" % v for v in after]))
        grew = after[2] > before[2] and after[3] > before[3]
        print("拉右下角变大:", grew)
        # 点在框内部：会走 Qt 的命中测试（就是刚才报 shape() 错的那条路径）
        win.scene.clearSelection()
        it1 = win.items[1]
        b = it1.scene_box()
        mid = win.canvas.mapFromScene(QPointF((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0))
        QTest.mousePress(win.canvas.viewport(), _Qt.MouseButton.LeftButton,
                         _Qt.KeyboardModifier.NoModifier, mid)
        QTest.mouseRelease(win.canvas.viewport(), _Qt.MouseButton.LeftButton,
                           _Qt.KeyboardModifier.NoModifier, mid)
        print("点框内部 OK：选中 %d 个框" % len(win.canvas.scene().selectedItems()))
        dest = os.path.join(app_dir(), "smoke_out.json")
        n = win.do_save(dest, quiet=True)
        print("另存 OK：%s（写了 %d 页）" % (dest, n))
        # 删框同步验证：删掉 3 个 Tracker + 1 个 Node，另存后重新读一遍，看是不是真少了
        win.goto_page(first)
        base = PageModel(DebugJson(path), first).counts()
        before = len(win.items)
        victims = [it for it in win.items if it.shape_data["label"] == "Tracker"][:3]
        victims += [it for it in win.items if it.shape_data["label"] == "Node"][:1]
        win.scene.clearSelection()
        for v in victims:
            v.setSelected(True)
        print("   诊断：选中 %d 个；删除前 dirty=%s shapes=%d edited=%d pending=%s"
              % (len(win.scene.selectedItems()), win.pm.dirty, len(win.pm.shapes),
                 len(win.edited), win._pending is not None))
        it_dbg = win.scene.selectedItems()[0]
        print("   诊断：item.shape_data 是 pm.shapes 里的对象？ %s；in 判定？ %s；类型 %s"
              % (any(it_dbg.shape_data is s for s in win.pm.shapes),
                 it_dbg.shape_data in win.pm.shapes,
                 type(it_dbg.shape_data).__name__))
        win.on_delete()
        print("   诊断：删除后 dirty=%s shapes=%d" % (win.pm.dirty, len(win.pm.shapes)))
        after = len(win.items)
        dest2 = os.path.join(app_dir(), "smoke_del.json")
        win.do_save(dest2, quiet=True)
        print("   诊断：保存后 edited=%d" % len(win.edited))
        c2 = PageModel(DebugJson(dest2), first).counts()
        print("删框同步：界面 %d -> %d，另存后重新读 Node %d / Tracker %d"
              % (before, after, c2["Node"], c2["Tracker"]))
        ok_del = (c2["Node"] == base["Node"] - 1 and c2["Tracker"] == base["Tracker"] - 3)
        print("   期望 Node %d / Tracker %d -> %s"
              % (base["Node"] - 1, base["Tracker"] - 3, "通过" if ok_del else "不一致！"))
        # ESC：画到一半取消；再按回到选择模式
        from PySide6.QtCore import QRectF
        win.set_mode("Tracker")
        win.canvas._origin = QPointF(500, 500)
        win.canvas._rubber = win.canvas.scene().addRect(QRectF(500, 500, 100, 100))
        nb = len(win.items)
        win.on_escape()
        e1 = (win.canvas._rubber is None and len(win.items) == nb)
        win.on_escape()
        e2 = (win.canvas.mode == "select")
        print("ESC：画到一半取消 %s；再按回到选择模式 %s" % (e1, e2))
        # 复制粘贴：选中两个框 -> 复制 -> 粘贴两次，看数量与错开量
        win.scene.clearSelection()
        for it in win.items[:2]:
            it.setSelected(True)
        win.on_copy()
        n_before = len(win.items)
        win.on_paste()
        n_mid = len(win.items)
        win.on_paste()
        n_after = len(win.items)
        pasted = win.scene.selectedItems()
        print("复制粘贴：选中 2 个 -> 复制 -> 粘贴两次 %d -> %d -> %d（每次 +2）"
              % (n_before, n_mid, n_after))
        print("   粘贴后选中 %d 个，新增框的 ocr_index 都是 None: %s"
              % (len(pasted), all(p.shape_data.get("ocr_index") is None for p in pasted)))
        # 跨页粘贴：复制 -> 翻到下一页 -> 粘贴
        win.scene.clearSelection()
        win.items[0].setSelected(True)
        win.on_copy()
        win.goto_offset(1)
        n_page2 = len(win.items)
        win.on_paste()
        print("跨页粘贴：第 %d 页 %d -> %d 个框"
              % (win.page, n_page2, len(win.items)))
        # 撤销 / 重做
        n0 = len(win.items)
        win.on_undo()
        n_undo = len(win.items)
        win.on_redo()
        n_redo = len(win.items)
        win.on_undo()
        n_undo2 = len(win.items)
        print("撤销/重做：%d ->(撤销) %d ->(重做) %d ->(再撤销) %d  重做栈 %d"
              % (n0, n_undo, n_redo, n_undo2, len(win.redo)))
        print("   期望 粘贴前/撤销后一致、重做后回到粘贴后: %s"
              % ("通过" if (n_redo == n0 and n_undo == n_page2 and n_undo2 == n_page2) else "不一致！"))
        return 0
    return app.exec()


def fix_std_streams():
    """打包成不带控制台的 exe 后 sys.stdout/stderr 是 None，print 会直接抛异常。"""
    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is None:
            try:
                setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
            except Exception:
                pass


def last_json():
    """上次打开过的那份识别结果（存在设置文件里，双击 exe 接着用）。"""
    p = str(load_settings().get("json") or "")
    return p if p and os.path.exists(p) else ""


def main():
    fix_std_streams()
    ap = argparse.ArgumentParser(description="LBD 标注工具 v0.1")
    ap.add_argument("json", nargs="?", default=None,
                    help="识别结果 debug JSON（不填就打开对话框）")
    ap.add_argument("--selftest", action="store_true", help="无界面自检")
    ap.add_argument("--smoke", action="store_true", help="无显示界面自检（画框/翻页/另存）")
    ap.add_argument("--memtest", action="store_true",
                    help="只载入并显示第一页，然后挂着（外部采样内存用）")
    ap.add_argument("--hold", type=float, default=20.0, help="--memtest 挂多久（秒）")
    ap.add_argument("--out", default=None, help="自检时的输出文件")
    a = ap.parse_args()
    if a.selftest:
        src = a.json or DEFAULT_JSON
        if not os.path.exists(src):
            print("找不到文件：%s" % src)
            return 2
        return selftest(src, a.out)
    if a.smoke:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        return run_gui(a.json or DEFAULT_JSON, smoke=True)
    if a.memtest:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        return run_gui(a.json or DEFAULT_JSON, memtest=a.hold)
    if a.json and not os.path.exists(a.json):
        print("找不到文件：%s" % a.json)
        return 2
    src = a.json
    if not src:
        # 双击 exe：先接着打开上次那份，其次看作者本机那份，都没有就弹选择框
        src = last_json() or (DEFAULT_JSON if os.path.exists(DEFAULT_JSON) else None)
        if src:
            print("打开上次的识别结果：%s" % src)
    return run_gui(src)


if __name__ == "__main__":
    sys.exit(main())
