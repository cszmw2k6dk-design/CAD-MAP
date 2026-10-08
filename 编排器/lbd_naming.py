# -*- coding: utf-8 -*-
"""按 PDF 文字层给识别出来的 LBD 区域配编号（从标注工具 lbd_annotator.py 原样搬过来）。

为什么搬：主程序现在自己做识别（detect.py），框出来之后要靠这套逻辑把「编号」写上去 ——
每条文字只归给离它最近的框、整段编号（INV01A01-LBD-01）优先、图例/引线名单滤掉、
标签表顺序兜底，并把编号印在哪儿（label_pos / label_bbox）一起记下来给避让用。

标注工具那边改动时，这份也要跟着同步（搬运源头：LBD-BIAOZHU/lbd_annotator.py）。
"""
import re


def _has_read_name(s):
    """框里真的读到过编号文字（排除"按标签表位置补的号"——那个是猜的）。"""
    return bool((s.get("name") or "").strip()) and not s.get("_auto")


def _pdf_rotate(page):
    try:
        return int(page.get("/Rotate") or 0) % 360
    except Exception:
        return 0


def _pdf_norm_pt(page, x, y):
    """PDF 用户坐标 -> 底图（渲染图）归一化坐标 (fx, fy)，fy 从下往上。

    PDF 带 /Rotate 时文字层坐标是没转过的，而底图是按转过的样子渲染的，
    不换算整片文字会跑到错位置。
    """
    try:
        cb = page.cropbox
        x0, y0 = float(cb.left), float(cb.bottom)
        pw = float(cb.right) - x0
        ph = float(cb.top) - y0
    except Exception:
        x0, y0, pw, ph = 0.0, 0.0, 1.0, 1.0
    pw = pw or 1.0
    ph = ph or 1.0
    x = float(x) - x0
    y = float(y) - y0
    rot = _pdf_rotate(page)
    if rot == 90:
        return (y / ph, (pw - x) / pw)
    if rot == 180:
        return ((pw - x) / pw, (ph - y) / ph)
    if rot == 270:
        return ((ph - y) / ph, x / pw)
    return (x / pw, y / ph)


# Helvetica / Arial 标准字宽表（单位 1/1000 em，来自 PDF 规范里那套内置字体度量）。
# CAD 图纸上的文字基本都是 Arial/Helvetica 系的，有这张表就能算出**真实字宽**，
# 不用再按"0.5×字号×字数"估 —— 实测那套估算会把编号框压短 ~10%。


# Helvetica / Arial 标准字宽表（单位 1/1000 em，来自 PDF 规范里那套内置字体度量）。
# CAD 图纸上的文字基本都是 Arial/Helvetica 系的，有这张表就能算出**真实字宽**，
# 不用再按"0.5×字号×字数"估 —— 实测那套估算会把编号框压短 ~10%。
_HELV_W = {}
for _ch, _w in ((" ", 278), ("!", 278), ('"', 355), ("#", 556), ("$", 556),
                ("%", 889), ("&", 667), ("'", 191), ("(", 333), (")", 333),
                ("*", 389), ("+", 584), (",", 278), ("-", 333), (".", 278),
                ("/", 278), (":", 278), (";", 278), ("<", 584), ("=", 584),
                (">", 584), ("?", 556), ("@", 1015), ("[", 278), ("\\", 278),
                ("]", 278), ("^", 469), ("_", 556), ("`", 333), ("{", 334),
                ("|", 260), ("}", 334), ("~", 584)):
    _HELV_W[_ch] = _w
for _d in "0123456789":
    _HELV_W[_d] = 556
for _c, _w in (("A", 667), ("B", 667), ("C", 722), ("D", 722), ("E", 667),
               ("F", 611), ("G", 778), ("H", 722), ("I", 278), ("J", 500),
               ("K", 667), ("L", 556), ("M", 833), ("N", 722), ("O", 778),
               ("P", 667), ("Q", 778), ("R", 722), ("S", 667), ("T", 611),
               ("U", 722), ("V", 667), ("W", 944), ("X", 667), ("Y", 667),
               ("Z", 611), ("a", 556), ("b", 556), ("c", 500), ("d", 556),
               ("e", 556), ("f", 278), ("g", 556), ("h", 556), ("i", 222),
               ("j", 222), ("k", 500), ("l", 222), ("m", 833), ("n", 556),
               ("o", 556), ("p", 556), ("q", 556), ("r", 333), ("s", 500),
               ("t", 278), ("u", 556), ("v", 500), ("w", 722), ("x", 500),
               ("y", 500), ("z", 500)):
    _HELV_W[_c] = _w


def text_advance(text, size, font_name=""):
    """这段文字在**文本空间**里有多长（还没乘矩阵）。返回 (宽度, 是不是按真字宽算的)。

    字体是 Arial / Helvetica / Liberation / Nimbus 这类标准字时，用标准字宽表算真值；
    其它字体（或表里没有的字符）退回"0.5×字号×字数"的估算。CAD 图纸基本都是前一类。
    """
    try:
        cs = float(size)
    except Exception:
        cs = 0.0
    nm = re.sub(r"^[A-Z]{6}\+", "", str(font_name or "")).lower()
    known = ("arial" in nm or "helvetica" in nm or "liberation" in nm
             or "nimbus" in nm or "helv" in nm)
    if known and cs > 0 and text:
        total = 0.0
        for ch in text:
            u = _HELV_W.get(ch)
            if u is None:
                return 0.5 * cs * len(text), False     # 有表里没有的字 -> 退回估算
            total += u
        return total / 1000.0 * cs, True
    return 0.5 * cs * len(text), False


def _pdf_text_items(page):
    """一页 -> [(文字, fx中心, fy中心, fx1, fy1, fx2, fy2)]（底图归一化坐标）。"""
    items = []

    def visit_text(text, cm, tm, font, size):
        if not text or not text.strip():
            return
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
        try:
            fname = str(font.get("/BaseFont") or "") if font else ""
        except Exception:
            fname = ""
        w, exact = text_advance(text, cs, fname)
        h = cs
        xs, ys = [], []
        for tx, ty in ((0.0, 0.0), (w, 0.0), (0.0, h), (w, h)):
            xs.append(m0 * tx + m2 * ty + m4)
            ys.append(m1 * tx + m3 * ty + m5)
        pts = [_pdf_norm_pt(page, px, py)
               for px, py in ((min(xs), min(ys)), (max(xs), min(ys)),
                              (min(xs), max(ys)), (max(xs), max(ys)))]
        fx1, fx2 = min(p[0] for p in pts), max(p[0] for p in pts)
        fy1, fy2 = min(p[1] for p in pts), max(p[1] for p in pts)
        items.append((text.strip(), (fx1 + fx2) * 0.5, (fy1 + fy2) * 0.5,
                      fx1, fy1, fx2, fy2, exact))

    page.extract_text(visitor_text=visit_text)
    return items


class PdfText:
    """按页取 PDF 文字块（复用同一个 reader + 缓存：整册跑才不至于太慢）。"""

    def __init__(self, pdf):
        from pypdf import PdfReader
        self.pdf = pdf
        self.reader = PdfReader(pdf)
        self._cache = {}

    def count(self):
        return len(self.reader.pages)

    def items(self, page_number):
        if page_number not in self._cache:
            try:
                self._cache[page_number] = _pdf_text_items(
                    self.reader.pages[int(page_number) - 1])
            except Exception:
                self._cache[page_number] = []
        return self._cache[page_number]


LBD_NUM_RE = re.compile(r"LBD\s*[_\-–—]?\s*0*(\d+)", re.I)
# 有些图里框内只印一个裸编号（"07" / "#7"），文字层里并没有 "LBD" 三个字母。
# 只认"整条就是数字"的，别把 3.5、1:100 这种尺寸/比例当编号。


BARE_NUM_RE = re.compile(r"^#?\s*0*(\d{1,3})\.?$")
# 兜底：框里任何文字里的第一个数字（"1.C.1"、"LBD-07"、"07" 都行）


INV_RE = re.compile(r"INV\s*0*(\d+)\s*([A-Za-z])\s*0*(\d+)", re.I)


SHEET_CLEAN_RE = re.compile(r"[^0-9A-Za-z.]")


def _clean_key(s):
    return SHEET_CLEAN_RE.sub("", str(s or "")).upper()


def _lbd_num_in(text):
    m = LBD_NUM_RE.search(str(text or ""))
    return int(m.group(1)) if m else None


def _clean_lbd_label(txt):
    """框里那串编号：去掉分表名和 LBD 标记，**保留前面的序号段**。

    '1.01.1.C.5'        -> '1.01.1.C.5'
    'INV31B102_LBD_07'  -> '07'
    'LBD 1.01.1.C.5'    -> '1.01.1.C.5'
    """
    t = re.sub(r"\s+", "", str(txt or ""))
    t = re.sub(r"INV\s*\d+\s*[A-Za-z]\s*\d+", "", t, flags=re.I)
    m = re.search(r"LBD[\s_\-–—:]*([0-9][0-9A-Za-z._\-]*)", t, re.I)
    if m:
        t = m.group(1)
    t = re.split(r"[()\[\]{}]", t)[0]          # 后面跟的 "(2)" 这种注解不要
    return t.strip("-_ .|()[]#")


def ocr_text_to_name(txt):
    """OCR 读到的一行字 -> 要不要写成名字。返回 (名字, 状态)。

    状态：'ok'    框里就是标准编号（INV..-LBD-..）
          'check' 像编号但不是标准写法（少了前缀、被截断…）-> 写成名字，标紫让人核
          'noise' 读出来的是别的字（旁注、比例尺、图号…）-> **不写名字**，标红等人填
          'miss'  什么都没读到

    为什么要分 noise：OCR 读错时最容易吐出来的就是框边上那些旁注（"LBD CLUSTER, TYP."、
    "MV1A"、"TCH, TYP."）。以前一律写进名字，用户看到的就是"识别到的和里面的内容完全
    没有关系"。
    """
    t = str(txt or "").strip()
    if not t:
        return "", "miss"
    up = t.upper().replace(" ", "")
    if LBD_LABEL_RE.search(up):
        # 名字用原文（保留 1.01.1.C.5 这种整段），只砍掉尾巴上的 "(2)" 之类注解
        return re.split(r"[()\[\]{}]", t)[0].strip().replace(" ", "").upper(), "ok"
    if LBDISH_RE.search(up):
        return t[:40], "check"
    return "", "noise"


def _full_lbd_name(txt):
    """文字里带整段编号（INV01A01-LBD-01）就把它原样当名字用；没有返回 None。

    文字层里这条文字本身就是"分表+编号"的完整写法，比事后拿分表名拼一遍更靠得住。
    """
    nm, kind = ocr_text_to_name(txt)
    return nm if kind == "ok" else None


SCALE_ONE_RE = re.compile(
    r"1\s*(?:\"|''|IN\b|INCH(?:ES)?)\s*[=:]\s*(\d+(?:\.\d+)?)\s*(?:FT\b|FEET|')", re.I)


SCALE_FT_PER_IN_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:FT\b|FEET|')\s*(?:PER|/|每)\s*(?:\"|IN\b|INCH)", re.I)


SHEET_SIZE_RE = re.compile(r'(\d+(?:\.\d+)?)\s*"\s*[xX×]\s*(\d+(?:\.\d+)?)\s*"')


def read_page_scale(items):
    """从一页的文字层里读出「1 IN = ? FT」。返回 (每英寸英尺数, 说明)。

    读不到返回 (None, 原因)。图纸上比例尺就两种写法，都认：
      ① 一句话：SCALE: 1" = 100'-0" / 1 IN = 100 FT
      ② 标尺表格（Steel River 这种）：标题栏里一行 "1  2  IN"、下一行 "100  200  FT"，
         数字上下对齐 —— 按 x 对齐把 1↔100、2↔200 配成对，用它们的比值（防止只看一行取错）。
    """
    txt = [((it[0] or "").strip(), float(it[1]), float(it[2])) for it in items]
    txt = [t for t in txt if t[0]]
    for s, _x, _y in txt:                       # ① 一句话
        m = SCALE_ONE_RE.search(s) or SCALE_FT_PER_IN_RE.search(s)
        if m:
            v = float(m.group(1))
            if 0 < v < 100000:
                return v, "文字里写着 1 IN = %g FT" % v
    # ② 标尺表格
    inch_lbl = [t for t in txt if re.fullmatch(r"IN|INCH(?:ES)?|\"", t[0], re.I)]
    ft_lbl = [t for t in txt if re.fullmatch(r"FT|FEET|'", t[0], re.I)]
    ratios = []
    for _s, ix, iy in inch_lbl:
        for _s2, fx, fy in ft_lbl:
            if abs(fy - iy) > 0.06 or fx < ix:
                continue                        # FT 得在同一块表里偏下/偏右
            nums_i = [t for t in txt
                      if abs(t[2] - iy) <= 0.012 and t[1] < ix + 0.02
                      and re.fullmatch(r"\d+(?:\.\d+)?", t[0])]
            nums_f = [t for t in txt
                      if abs(t[2] - fy) <= 0.012 and t[1] < fx + 0.02
                      and re.fullmatch(r"\d+(?:\.\d+)?", t[0])]
            for s3, x3, _y3 in nums_i:
                v_i = float(s3)
                if v_i <= 0:
                    continue
                near = min(nums_f, key=lambda t: abs(t[1] - x3), default=None)
                if near is None or abs(near[1] - x3) > 0.02:
                    continue
                v_f = float(near[0])
                if v_f > v_i:
                    ratios.append(v_f / v_i)
    if ratios:
        ratios.sort()
        v = ratios[len(ratios) // 2]
        return v, "标题栏标尺表（%d 对数字）" % len(ratios)
    return None, "这页文字层里没找到比例尺"


def read_sheet_width_in(items):
    """从"22\" x 34\" SHEETS"这种说明里读出图纸幅面（取大的一边，单位英寸）。"""
    for it in items:
        m = SHEET_SIZE_RE.search(str(it[0] or ""))
        if m:
            try:
                a, b = float(m.group(1)), float(m.group(2))
            except ValueError:
                continue
            if a > 1 and b > 1:
                return max(a, b)
    return None


def _name_num(name):
    """名字里的"号"：取最后一段数字。'…-LBD-1.01.1.C.5' -> 5，'…-LBD-07' -> 7。"""
    segs = re.findall(r"\d+", str(name or ""))
    return int(segs[-1]) if segs else None


def _lbd_name(sheet, label, num):
    """拼 LBD 名字：<分表名>-LBD-<编号>。

    整段编号原样用（1.01.1.C.5）；只有一段数字就补成两位（07）。
    """
    lab = str(label or "").strip("-_ .|()[]#")
    if not lab and num is not None:
        lab = "%02d" % int(num)
    elif re.fullmatch(r"0*\d{1,3}", lab):
        lab = "%02d" % int(lab)
    return ("%s-LBD-%s" % (sheet, lab)) if sheet else ("LBD-%s" % lab)


def _inv_in(text):
    """文字里自带的 INV 分表名（如 INV31B102_LBD_07 -> INV31B102），没有返回 None。"""
    m = INV_RE.search(str(text or ""))
    if not m:
        return None
    return ("INV%s%s%s" % (m.group(1), m.group(2).upper(), m.group(3))).upper()


def sheet_in_text(text, sheet_names):
    """文字里命中的分表名（取最长的那个，避免 "1.0" 抢 "1.01"）。"""
    key = _clean_key(text)
    if not key:
        return None
    best = None
    for nm in sheet_names:
        k = _clean_key(nm)
        if k and k in key and (best is None or len(k) > len(_clean_key(best))):
            best = nm
    return best


def page_sheet_by_text(text_items, sheet_names):
    """页面文字里出现次数最多的分表名 + 次数（用来校验"按顺序"推断的对不对）。"""
    counts = {}
    for it in text_items:
        nm = sheet_in_text(it[0], sheet_names)
        if nm:
            counts[nm] = counts.get(nm, 0) + 1
    if not counts:
        return None, 0
    nm = max(counts, key=lambda k: counts[k])
    return nm, counts[nm]


def _box_dist(b, x, y):
    dx = max(b[0] - x, 0.0, x - b[2])
    dy = max(b[1] - y, 0.0, y - b[3])
    return (dx * dx + dy * dy) ** 0.5


def _box_center(b):
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def _flag_suspicious(shapes):
    """同一行里相邻两个框的号不连续（比如 3、7）-> 标 _check，返回清单。

    自动补号最常见的错法就是"这一排的号跳了"，拿它当"位置可能错"的提示。
    返回 [(名字, x, y), ...]，坐标是底图像素（人照着这个去图上找）。
    """
    nodes = []
    for s in shapes:
        if s.get("label") != "Node":
            continue
        # 名字里的"号"= 最后一段数字：既能认 "…-LBD-07"（7），
        # 也能认 "…-LBD-1.01.1.C.5"（5）—— 跳号检查就靠它
        n = _name_num(s.get("name") or "")
        if n is None:
            continue
        cx, cy = _box_center(s["bbox"])
        nodes.append((cy, cx, n, s))
    if len(nodes) < 2:
        return []
    rows = _rows_of(nodes, _row_tol(shapes))
    out = []
    for row in rows:
        for k in range(len(row) - 1):
            if abs(row[k][2] - row[k + 1][2]) != 1:
                for it in (row[k], row[k + 1]):
                    if not it[3].get("_check"):
                        it[3]["_check"] = True
                        out.append((it[3].get("name"), round(it[1]), round(it[0])))
    return out


def _row_tol(shapes):
    """分行容差：按 Node 框高度的中位数取 60%（条带框长、中心点浮动大，容差得放宽）。"""
    hs = sorted(abs(s["bbox"][3] - s["bbox"][1])
                for s in shapes if s.get("label") == "Node")
    med = hs[len(hs) // 2] if hs else 1.0
    return max(2.0, med * 0.6)


def _rows_of(items, tol):
    """[(y中点, x中点, ...)] -> 按 y 分成一排排（行内从左到右排好）。

    注意不能直接按 (y, x) 排序：同一条带排里的框高度不一样，y 中点能差好几百像素，
    直接排会把同一排的号打乱（补号顺序就错了）。
    """
    ps = sorted(items, key=lambda t: t[0])
    rows, cur = [], []
    for it in ps:
        if not cur or abs(it[0] - cur[-1][0]) <= tol:
            cur.append(it)
        else:
            rows.append(cur)
            cur = [it]
    if cur:
        rows.append(cur)
    for r in rows:
        r.sort(key=lambda t: t[1])
    return rows


def _page_candidates(text_items, sheet, num_set, width, height):
    """这一页可用的编号文字 -> (强候选, 裸数字候选, 分表名对不上的条数)。

    强候选：文字里有 LBD+数字（如 INV31B102_LBD_07），且号码在本分表号码表里，
            再把"图例/引线名单"（同列密排）滤掉。
    裸数字候选：整条文字就是个号（"07"），有些图框里只印这个，没有 "LBD" 字样 —
            这条通道以前没有，所以"每个框里都有号、有的却取不到"。
    """
    raw, full, bare, wrong = [], [], [], 0
    for it in text_items:
        num = _lbd_num_in(it[0])
        inv = _inv_in(it[0])
        if inv and _clean_key(sheet) and _clean_key(inv) != _clean_key(sheet):
            wrong += 1
            continue
        px = it[1] * width
        py = (1.0 - it[2]) * height
        # 整段编号（INV01A01-LBD-01）单独归一类：这种文字本身就把分表和号写全了，
        # 绝不能当"图例/引线名单"丢掉 —— 用户那本 Steel River 上，全页 20 个编号
        # 就是被 _drop_legend 当图例清掉，然后兜底抓了旁边的 "MV1A" 当编号。
        if _full_lbd_name(it[0]):
            full.append((px, py, num, it[0]))
            continue
        if num is not None:
            if sheet and num_set and num not in num_set:
                continue
            raw.append((px, py, num, it[0]))
        else:
            m = BARE_NUM_RE.match(it[0].strip())
            if m:
                bare.append((px, py, int(m.group(1)), it[0]))
    return full + _drop_legend(raw, height), bare, wrong


def _box_texts(shapes, text_items, width, height, tol_ratio=0.006):
    """框里 / 框边上找到的**所有文字**（先全拿出来，谁是什么号后面再判断）。

    返回 {框下标: [(距离, 文字, x, y)]}；每条文字只归给离它最近的那个框。
    x/y 是这条文字的中心（页面像素），补编号时拿它当"编号印在哪儿"。
    """
    nodes = [(i, s) for i, s in enumerate(shapes) if s.get("label") == "Node"]
    tol = max(6.0, float(tol_ratio) * max(width, height))
    out = {}
    for it in text_items:
        txt = (it[0] or "").strip()
        if not txt:
            continue
        px, py = it[1] * width, (1.0 - it[2]) * height
        best, bd = None, None
        for i, s in nodes:
            d = _box_dist(s["bbox"], px, py)
            if bd is None or d < bd:
                best, bd = i, d
        if best is not None and bd is not None and bd <= tol:
            out.setdefault(best, []).append((round(bd), txt, px, py))
    for k in out:
        out[k].sort()
    return out


def _drop_legend(cands, page_h):
    """滤掉"引线名单/图例"：同一列上密集挤着 ≥3 条编号的那种。

    图纸上每个区域自己的号是孤零零一条；名单是十几条一列排下来 —— 靠这个区分。
    """
    if len(cands) < 4:
        return list(cands)
    gx = max(4.0, page_h * 0.004)
    gy = max(8.0, page_h * 0.02)
    out = []
    for i, (px, py, num, txt) in enumerate(cands):
        n = 0
        for j, (qx, qy, _n, _t) in enumerate(cands):
            if i != j and abs(qx - px) <= gx and abs(qy - py) <= gy:
                n += 1
        if n < 3:
            out.append((px, py, num, txt))
    return out


def check_rows(shapes, text_items, sheet, num_set, width, height):
    """核对表：每个 Node 框一行 —— 现有名字 + 框内找到的候选 + 按现在规则重算的建议。

    返回 (rows, dry_stat)。rows 里每个 dict：
      ix 框序号 / cx,cy 框中心（底图像素）/ now 现有名字 / sug 建议名字
      cand 框内候选（"号@距离"）/ src 建议来源（框内 / 推 / 缺）
    """
    cands, bare, _wrong = _page_candidates(text_items, sheet, num_set, width, height)
    alltext = _box_texts(shapes, text_items, width, height)
    tol = max(6.0, 0.006 * max(width, height))
    nodes = [(i, s) for i, s in enumerate(shapes) if s.get("label") == "Node"]
    got = {}
    for px, py, num, txt in cands:
        best, bd = None, None
        for i, s in nodes:
            d = _box_dist(s["bbox"], px, py)
            if bd is None or d < bd:
                best, bd = i, d
        if best is not None and bd is not None and bd <= tol:
            got.setdefault(best, []).append((bd, num, txt))
    # 只印裸编号的（文字层里没有 "LBD" 字样）也一起列出来，标个 (裸)
    for px, py, val, txt in bare:
        best, bd = None, None
        for i, s in nodes:
            d = _box_dist(s["bbox"], px, py)
            if bd is None or d < bd:
                best, bd = i, d
        if best is not None and bd is not None and bd <= tol:
            got.setdefault(best, []).append((bd, val, txt + "(裸)"))
    tmp = [dict(s) for s in shapes]
    for s in tmp:
        s.pop("_auto", None)
        s.pop("_miss", None)
        s.pop("_check", None)
        if s.get("label") == "Node":
            s["name"] = ""
    dry = autofill_shapes(tmp, text_items, sheet, num_set, width, height)
    rows = []
    for i, s in nodes:
        cx, cy = _box_center(s["bbox"])
        cand = sorted(got.get(i) or [])[:3]
        raw = []
        for d, txt, _tx, _ty in (alltext.get(i) or [])[:6]:
            mark = ""
            # 标 × 的：这条文字被过滤掉了（号不在本分表号码表里 / 结尾像是被截断）
            mm = ANY_NUM_RE.search(re.sub(r"INV\s*\d+\s*[A-Za-z]\s*\d+", " ", txt, flags=re.I))
            if (txt.rstrip().endswith(("-", "_", ".", "(", "#"))
                    or (mm and sheet and num_set and int(mm.group(1)) not in num_set)):
                mark = "×"
            raw.append((d, txt + mark))
        t = tmp[i]
        src = ("框内" if raw else ("推" if t.get("_auto") else
                                    ("缺" if t.get("_miss") else "已有")))
        rows.append({"ix": i, "cx": round(cx), "cy": round(cy),
                     "now": s.get("name") or "", "sug": t.get("name") or "",
                     "src": src,
                     "cand": " | ".join("%s@%d" % (txt, d) for d, txt in raw)
                             or " / ".join("%02d@%d" % (n, round(d)) for d, n, _t in cand)})
    return rows, dry


def autofill_shapes(shapes, text_items, sheet, num_set, width, height,
                    tol_ratio=0.006):
    """给一页的 Node 框补 LBD 名字。返回统计 dict。

    shapes: 这一页的框（就地改 name / _auto / _miss 标记，只动 label == "Node"）
    text_items: [(文字, fx中心, fy中心, fx1, fy1, fx2, fy2)]（底图归一化坐标）
    sheet: 本页分表名（来自标签表）
    num_set: 这个分表可用的 LBD 编号集合（用来滤掉框里的干扰文字）
    规则：
      1) 每条文字只归给离它最近的那个框（不是一个框把周围文字全拿走）
      2) 文字里的编号必须在这个分表的号码表里
      3) 文字自带 INV 分表名、且和本页分表不一致 -> 当干扰丢掉
      4) 框里没有可用文字的，按标签表的号（还没被用掉的）按位置顺序补，标黄
      5) 连标签表的号都没有了 -> 标红，等人手填
    """
    # 锁上的 Node **也补编号**：锁是防"误拖/误删/框选到"的，不是不让补号
    # （用户反馈：锁定 Node 之后跑「识别框内文字」编号写不进去 —— 就是这里被跳过了）
    locked_n = sum(1 for s in shapes
                   if s.get("label") == "Node" and s.get("locked"))
    nodes = [(i, s) for i, s in enumerate(shapes) if s.get("label") == "Node"]
    tol = max(6.0, float(tol_ratio) * max(width, height))
    stat = {"total": len(nodes), "filled": 0, "auto": 0, "missed": 0,
            "wrong_sheet": 0, "kept": 0, "locked": locked_n, "pos_added": 0}
    if not nodes:
        return stat

    def _find_label_mark(s):
        """框里那条编号文字印在哪儿：(中心, 小框) —— 都是页面像素坐标。

        优先"整段文字和名字一样"的，其次"号一样"的。名字已经有了（以前跑过、或者
        人填的）时也要能拿到 —— 用户反馈的"导出 JSON 里没有 lbd 编号位置"就是因为
        老逻辑见到已有名字就整框跳过。
        """
        name = (s.get("name") or "").strip()
        if not name:
            return None
        want = _name_num(name)
        nm = re.sub(r"\s+", "", name).upper()
        hit = None
        b = s["bbox"]
        for it in text_items:
            px, py = it[1] * width, (1.0 - it[2]) * height
            if not (b[0] <= px <= b[2] and b[1] <= py <= b[3]):
                continue
            up = re.sub(r"\s+", "", str(it[0] or "")).upper()
            same = (up == nm)
            if not same and (want is None or _lbd_num_in(it[0]) != want):
                continue
            # 文字项的框：x1,x2 直接换算；y 是自下而上的，要翻过来
            bb = (it[3] * width, (1.0 - it[6]) * height,
                  it[5] * width, (1.0 - it[4]) * height)
            if same:
                return (px, py), bb, (it[7] if len(it) > 7 else False)
            if hit is None:
                hit = ((px, py), bb, (it[7] if len(it) > 7 else False))
        return hit

    def _mark_positions():
        """给已经定了名字的框补上"编号印在哪儿"：label_pos（中心）+ label_bbox（小框）。

        已经有名字、只有中心没框的（老文件）也在这里补齐。按标签表顺序推出来的名字
        没有对应文字，给不出框，跳过。
        """
        for _i, s in nodes:
            nm = (s.get("name") or "").strip()
            if not nm or s.get("_auto"):
                continue
            raw = s.get("raw") if isinstance(s.get("raw"), dict) else {}
            if raw.get("label_pos") and raw.get("label_bbox"):
                continue
            mk = _find_label_mark(s)
            if not mk:
                continue
            (cx, cy), bb, exact = mk
            raw["label_pos"] = [int(round(cx)), int(round(cy))]
            raw["label_bbox"] = [int(round(v)) for v in bb]
            raw["label_src"] = raw.get("label_src") or "text_layer"
            raw["label_box_kind"] = "metrics" if exact else "estimated"
            s["raw"] = raw
            stat["pos_added"] = stat.get("pos_added", 0) + 1

    # 已经有人写过的名字：不动（免得把手工改的冲掉）
    todo = []
    for i, s in nodes:
        if (s.get("name") or "").strip() and not s.get("_auto"):
            stat["kept"] += 1
            s["_miss"] = False
        else:
            s["name"] = ""
            s["_miss"] = False
            s["_check"] = False
            todo.append((i, s))
    if not todo:
        _mark_positions()       # 名字都齐了，但可能缺位置/小框 -> 补上再返回
        return stat

    # 1) 候选文字：编号 + 分表名过滤 + 去掉图例/引线名单
    cands, bare, n_wrong = _page_candidates(text_items, sheet, num_set, width, height)
    stat["wrong_sheet"] = n_wrong

    # 2) 归属：① 文字中心落在哪个框里，就归那个框（谁的框谁拿字）
    #          ② 落在框外的，才按"最近 + 那个框还没拿到字"分给别人
    #    （老写法是"每条文字只给最近的框"，两个框抢同一条字时多的那条直接被丢掉，
    #      结果本该拿到它的框就空了 —— 表现就是"4 个框只读到 2 个"。）
    got = {}
    left_c = []
    pos_of = {}                       # 框下标 -> 那条编号文字的中心（页面像素）
    for px, py, num, _txt in cands:
        inside = None
        for i, s in todo:
            b = s["bbox"]
            if b[0] <= px <= b[2] and b[1] <= py <= b[3]:
                inside = i
                break
        if inside is None:
            left_c.append((px, py, num, _txt))   # 文字带上，别丢
            continue
        old = got.get(inside)
        if old is None or 0.0 < old[0]:
            got[inside] = (0.0, num, _txt)
            pos_of[inside] = (px, py)
    for px, py, num, _ltxt in left_c:
        best, bd = None, None
        for i, s in todo:
            if i in got:                 # 已经有字了，别再抢
                continue
            d = _box_dist(s["bbox"], px, py)
            if bd is None or d < bd:
                best, bd = i, d
        if best is None or bd is None or bd > tol:
            continue
        # 这里原来用的是外层循环残留的 txt（早就不在作用域了）——一走到这条路就崩
        got[best] = (bd, num, _ltxt)
        pos_of[best] = (px, py)

    # 3) 抢号：同一个号只留最近的那个框
    keep, keep_lab, full_name = {}, {}, {}
    for i, (d, num, txt) in sorted(got.items(), key=lambda kv: kv[1][0]):
        if num in keep:
            continue
        keep[i] = num
        keep_lab[i] = _clean_lbd_label(txt)
        nm = _full_lbd_name(txt)          # 整段编号（INV01A01-LBD-01）就原样用
        if nm:
            full_name[i] = nm

    used = set(keep.values())
    for i, s in todo:
        if i in keep:
            # 文字层里本身就是整段编号（INV01A01-LBD-01）-> 原样用，别拿分表名重拼
            # 编号整段带上（框里印的是 1.01.1.C.5 就写 1.01.1.C.5，不是只留 5）
            s["name"] = (full_name.get(i)
                         or _lbd_name(sheet, keep_lab.get(i, ""), keep[i]))
            # 把"这个编号印在图上的哪儿"一起记下来（主程序/核对都用得上）
            bb = pos_of.get(i)
            if bb:
                raw = s.get("raw") if isinstance(s.get("raw"), dict) else {}
                raw["label_pos"] = [int(round(bb[0])), int(round(bb[1]))]
                raw["label_src"] = "text_layer"
                s["raw"] = raw
            s["_auto"] = False
            stat["filled"] += 1

    # 3b) 框里只印裸编号的（文字层里没有 "LBD" 字样）：按"离框最近 + 号在号码表里优先"补。
    #     这正是"每个框里都有号、有的却取不到"那批 —— 以前只认带 LBD 字样的文字。
    if bare and len(keep) < len(todo):
        left = [t for t in todo if t[0] not in keep]
        bare_got = {}
        for px, py, val, txt in bare:
            best, bd = None, None
            for i, s in left:
                d = _box_dist(s["bbox"], px, py)
                if bd is None or d < bd:
                    best, bd = i, d
            if best is None or bd is None or bd > tol or best in bare_got:
                continue
            if val in used and any(v == val for _d, v, _t in [bare_got.get(best) or (0, -1, "")]):
                continue
            bare_got[best] = (bd, val, txt)
        # 同一号码只留一个框
        seen_num = set()
        for i in sorted(bare_got, key=lambda k: bare_got[k][0]):
            _d, val, _t = bare_got[i]
            if val in seen_num or val in used:
                continue
            # 号码不在这个分表号码表里 -> 当"文字不全/被截断"过滤掉，不填
            if sheet and num_set and val not in num_set:
                stat["dropped"] = stat.get("dropped", 0) + 1
                continue
            seen_num.add(val)
            s = dict(todo)[i]
            s["name"] = _lbd_name(sheet, "", val)
            s["_auto"] = False
            s["_check"] = False
            keep[i] = val
            used.add(val)
            stat["bare"] = stat.get("bare", 0) + 1
            stat["filled"] += 1

    # 3c) 最后兜底：框里的文字先全拿出来，只要里面带数字就试一把
    #     （"1.C.1"、"LBD-07"、"07" 都行；号码不在本分表表里的标紫，让人核）
    if len(keep) < len(todo):
        bt = _box_texts(shapes, text_items, width, height, tol_ratio)
        left = [t for t in todo if t[0] not in keep]
        picks = {}
        for i, _s in left:
            for d, txt, _tx, _ty in (bt.get(i) or []):
                # ★ 先把分表名（INV31B101 这种）从文字里剔掉再找数字，
                #   不然"任意数字"会抓到分表名里的 31，填出 INV31B101-LBD-31 这种鬼东西
                if txt.rstrip().endswith(("-", "_", ".", "(", "#", "|")):
                    continue           # 结尾是分隔符 -> 文字被截断了，不拿它猜号
                t2 = re.sub(r"INV\s*\d+\s*[A-Za-z]\s*\d+", " ", txt, flags=re.I)
                # "1.01.1.C.5" 这种：把所有数字段都拆出来，从**最后往前**找，
                # 只要有一个能在本分表号码表里对上就用它（不再要求带 "LBD" 字样）
                segs = [int(g) for g in re.findall(r"\d{1,3}", t2)]
                if not segs:
                    continue
                # 旁边那些旁注（"MV1A"、"TCH, TYP."、"LBD CLUSTER, TYP."）不是编号：
                # 以前会拿它们里的数字硬凑一个名字（用户看到 "LBD-MV1A" 就是这么来的）
                nm_ok, kind = ocr_text_to_name(txt)
                if kind == "noise" and not BARE_NUM_RE.match(txt.strip()):
                    stat["dropped"] = stat.get("dropped", 0) + 1
                    continue
                val = None
                for v in reversed(segs):
                    if not sheet or not num_set or v in num_set:
                        val = v
                        break
                if val is None:
                    stat["dropped"] = stat.get("dropped", 0) + 1
                    continue
                in_set = (not sheet or not num_set or val in num_set)
                picks.setdefault(i, []).append((0 if in_set else 1, d, val, txt, _tx, _ty))
        for i, lst in picks.items():
            if i in keep:
                continue
            lst.sort()
            pref = [t for t in lst if t[0] == 0]
            if not pref:
                # 框里那些字里的数字都不在本分表号码表里（多半是被拆开/截断的文字）
                # -> 过滤掉，不猜号
                stat["dropped"] = stat.get("dropped", 0) + 1
                continue
            flag, _d, val, pick_txt, pick_x, pick_y = pref[0]
            if val in used:
                continue
            s = dict(todo)[i]
            # 注意：只能用"挑中的那条文字"（pick_txt）拼名字。
            # 原来这里用的是外层循环残留的 txt，于是框里明明写着 INV01A01-LBD-06，
            # 名字却被拼成框边那条旁注（"LBD-MV1A"）—— 用户看到的就是这个。
            s["name"] = (_full_lbd_name(pick_txt)
                         or _lbd_name(sheet, _clean_lbd_label(pick_txt), val))
            raw = s.get("raw") if isinstance(s.get("raw"), dict) else {}
            raw["label_pos"] = [int(round(pick_x)), int(round(pick_y))]
            raw["label_src"] = "text_layer"
            s["raw"] = raw
            s["_auto"] = False
            s["_check"] = False
            keep[i] = val
            used.add(val)
            stat["any"] = stat.get("any", 0) + 1
            stat["filled"] += 1

    # 4) 框里没取到号的：按标签表的号顺序补（标黄，提示人工核）
    rest = [t for t in todo if t[0] not in keep]
    if rest and sheet and num_set:
        free = [n for n in sorted(num_set) if n not in used]
        # 位置顺序 = 一排排（先分行，行内从左到右）——和图纸上读的顺序一致
        pairs = [(round(_box_center(s["bbox"])[1], 3), round(_box_center(s["bbox"])[0], 3), i, s)
                 for i, s in rest]
        k = 0
        for row in _rows_of(pairs, _row_tol(shapes)):
            for _cy, _cx, i, s in row:
                if k >= len(free):
                    break
                s["name"] = _lbd_name(sheet, "", free[k])
                s["_auto"] = True
                stat["auto"] += 1
                k += 1
    for i, s in rest:
        if not (s.get("name") or "").strip():
            s["_miss"] = True
            stat["missed"] += 1
    # 4b) 把"编号印在哪儿"补全：位置 + 小框（画在图上给人核对用）
    _mark_positions()
    # 5) 位置可疑：同一行里号码跳号 -> 标紫（紫 = 从框内取到号了，但和同排的号对不上，
    #    也可能是框画错/取到了隔壁）；黄 = 按标签表顺序推的，同样要人核一眼。
    stat["sus"] = _flag_suspicious(shapes)
    stat["auto_list"] = [(s.get("name") or "") for _i, s in todo if s.get("_auto")]
    stat["sus_list"] = [(s.get("name") or "", round(_box_center(s["bbox"])[0]),
                         round(_box_center(s["bbox"])[1]))
                        for _i, s in todo if s.get("_check")]
    return stat


def _kmeans_cuts(values, k, iters=80):
    """把一堆长度分成 k 档，返回 k-1 个切点（切在长度间隙大的地方）。

    支架分档用：不能用"等分位"硬切 —— 那样长度几乎一样的支架，只要一个落在切线
    左边、一个落在右边，就会被分到两类（用户看到的就是"明明一样长却分了两种"）。
    这里做一维 k-means，切点落在两类中心之间，长度接近的必然是同一类。
    """
    vals = sorted(float(v) for v in values)
    n = len(vals)
    if k <= 1 or n <= k:
        return []
    cent = [vals[min(n - 1, int(n * (i + 0.5) / k))] for i in range(k)]
    for _ in range(iters):
        groups = [[] for _ in range(k)]
        for v in vals:
            groups[min(range(k), key=lambda i: abs(v - cent[i]))].append(v)
        new = [sum(g) / len(g) if g else cent[i] for i, g in enumerate(groups)]
        if new == cent:
            break
        cent = new
    cent = sorted(cent)
    return [(cent[i] + cent[i + 1]) / 2.0 for i in range(k - 1)]


LBD_LABEL_RE = re.compile(r"INV\s*\d+\s*[A-Z]\s*\d+\s*[-_ ]?LBD[-_ ]?\s*\d+", re.I)
# "像编号"的：LBD 后面跟着数字（LBD-8 / LBD 1.01.1.C.5），或者只有 INV 前缀没 LBD 字样。
# 注意不能写成"只要出现 LBD 就算" —— 图纸上到处都是 "LBD CLUSTER, TYP." 这种旁注。


LBDISH_RE = re.compile(r"LBD\s*[-_.#]?\s*\d|INV\s*\d+\s*[A-Z]\s*\d+", re.I)
