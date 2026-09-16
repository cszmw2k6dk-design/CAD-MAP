# -*- coding: utf-8 -*-
"""从识别结果 debug JSON 导出 LBD 区域范围 + Typical(支架)范围。

字段对应关系(已按几何验证):
  - LBD 区域  = yolo_tracker_detection_results -> label == "Node" 的大框
                (与 ocr_node_name_results 的 node_bbox 完全一致, 每页 18~20 个)
  - Typical   = yolo_tracker_detection_results -> label == "Tracker" 的细长框(支架)
                (每页 144~174 个, 基本都落在某个 Node 区域内)
  - LBD 符号  = yolo_box_detection_results -> label == "Box" 的 16x16 小框
                (断开点符号位置, 不是区域, 单独输出)

detections 坐标已是原图像素(original_page_pixels); bbox_norm = 像素 / 页面宽高。

被 编排器/app.py 在「执行/输出」流程里自动调用; 也可单独当命令行用:
  python lbd_regions.py --json "C:\\...\\agent3-debug.json" --out 输出目录
"""
import argparse
import csv
import json
import os
import re

DEBUG_KEYS = (b'"yolo_tracker_detection_results"', b'"ocr_node_name_results"',
              b'"claude_node_name_review_results"', b'"table_recognition_results"')
SCHEMA_MARK = b"agent3-debug"

# 支架类型: 各流程/版本里可能出现的键名都认一下, 有长度就带上, 没有就留空等人工补
_RACK_LIST_KEYS = ("tracker_definitions", "rack_types", "rack_definitions",
                   "support_types", "tracker_types")
_RACK_STR_KEYS = ("strings_per_tracker", "stringsPerTracker", "strings", "string_count",
                  "n_strings", "combine_strings")
_RACK_LEN_KEYS = ("length_ft", "lengthFt", "length_feet", "lengthFeet", "length",
                  "ft", "rack_length", "rack_length_ft", "string_length",
                  "row_length", "row_length_ft")
_RACK_CODE_KEYS = ("code", "name", "type", "label", "code_name")
_RACK_COUNT_KEYS = ("total_count", "tracker_count", "count", "qty", "quantity")
_RACK_PANEL_KEYS = ("panel_label", "panel", "module", "module_label")


def _first_num(src, keys):
    for k in keys:
        if k in src and src[k] is not None and src[k] != "":
            try:
                return float(src[k])
            except Exception:
                continue
    return None


def _first_str(src, keys):
    for k in keys:
        v = src.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def rack_types_from_doc(doc):
    """从识别 JSON 里取支架类型列表。

    认 input_data.tracker_definitions(以及若干同义键), 每项尽量取出:
      串数 strings_per_tracker / 长度 length_ft / 数量 total_count / 代号 code / 面板 panel_label
    同一个串数只留一条。有长度就填, 没有就 length_ft=None(交给界面手填)。
    """
    src_lists = []
    inp = doc.get("input_data") if isinstance(doc.get("input_data"), dict) else {}
    for container in (inp, doc):
        for key in _RACK_LIST_KEYS:
            v = container.get(key)
            if isinstance(v, list):
                src_lists.append((key, v))

    out, by_str = {}, []
    for src_key, items in src_lists:
        for it in items:
            if not isinstance(it, dict):
                continue
            strings = _first_num(it, _RACK_STR_KEYS)
            if strings is None:
                # 有些写法把串数藏在 code 里, 如 "13-string" / "13串"
                code = _first_str(it, _RACK_CODE_KEYS) or ""
                m = re.search(r"(\d+)", code)
                strings = float(m.group(1)) if m else None
            if strings is None:
                continue
            key = int(strings) if float(strings).is_integer() else strings
            rec = {
                "strings": key,
                "code": _first_str(it, _RACK_CODE_KEYS),
                "length_ft": _first_num(it, _RACK_LEN_KEYS),
                "total_count": _first_num(it, _RACK_COUNT_KEYS),
                "panel_label": _first_str(it, _RACK_PANEL_KEYS),
                "source": "%s.%s" % (src_key, _first_str(it, _RACK_CODE_KEYS) or key),
            }
            if rec["total_count"] is not None:
                rec["total_count"] = int(rec["total_count"])
            if key in out:
                old = out[key]
                for f in ("code", "length_ft", "panel_label"):
                    if old.get(f) in (None, "") and rec.get(f) not in (None, ""):
                        old[f] = rec[f]
                if rec.get("total_count"):
                    old["total_count"] = max(old.get("total_count") or 0, rec["total_count"])
            else:
                out[key] = rec
                by_str.append(key)

    rows = []
    for i, key in enumerate(sorted(by_str)):
        r = out[key]
        r["index"] = i + 1
        rows.append(r)
    return rows


def rack_types_text(rows):
    """转成界面「支架类型」那格用的写法: 串数:长度FT，逗号分隔(没长度的只写串数)。"""
    parts = []
    for r in rows:
        if r.get("length_ft"):
            parts.append("%s:%s" % (r["strings"], ("%g" % r["length_ft"])))
        else:
            parts.append("%s" % r["strings"])
    return ", ".join(parts)


def rack_types_from_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except Exception:
        return []
    return rack_types_from_doc(doc)


def looks_like_debug(path):
    """廉价判断: 只看文件开头一段, 不整体解析(debug JSON 常有几十 MB)。

    页面 base64 图片排在 yolo_*/ocr_* 结果前面, 那些键常在前 8KB 之外,
    所以主要靠 schema_version 里的 agent3-debug 标记来识别。
    """
    try:
        if not path or not os.path.isfile(path):
            return False
        with open(path, "rb") as f:
            head = f.read(65536)
        if any(k in head for k in DEBUG_KEYS):
            return True
        return SCHEMA_MARK in head and b'"schema_version"' in head
    except Exception:
        return False


def _scan_dir_for_debug(d, depth=1, found=None):
    """在目录里找最新的 debug JSON(按修改时间)。depth 限制递归层数。"""
    if found is None:
        found = []
    try:
        items = os.listdir(d)
    except Exception:
        return found
    for name in items:
        p = os.path.join(d, name)
        try:
            if os.path.isfile(p) and name.lower().endswith(".json") and looks_like_debug(p):
                found.append((os.path.getmtime(p), p))
            elif os.path.isdir(p) and depth > 0:
                _scan_dir_for_debug(p, depth - 1, found)
        except Exception:
            continue
    return found


def candidate_debug_jsons(cfg, extra_paths=()):
    """按优先级列出可能的识别 debug JSON(用户指定的排第一, 其余按新旧)。"""
    ordered, seen = [], set()

    def add(p):
        if p and p not in seen and os.path.isfile(p):
            seen.add(p)
            ordered.append(p)

    # 1) 用户显式指定的 JSON: 永远先试, 出错时能给出更明确的提示
    add((cfg.get("jsonPath") or "").strip())

    dirs = []
    for key in ("aiOutdir", "outputDir", "regionOut"):
        v = (cfg.get(key) or "").strip()
        if v:
            dirs.append(v if os.path.isdir(v) else os.path.dirname(v))
    for key in ("lbdOut", "pdf"):
        v = (cfg.get(key) or "").strip()
        if v:
            dirs.append(os.path.dirname(v))
    for p in extra_paths:
        dirs.append(p if os.path.isdir(p) else os.path.dirname(p))

    dirs_seen = set()
    for d in dirs:
        if not d or d in dirs_seen or not os.path.isdir(d):
            continue
        dirs_seen.add(d)
        for _mt, p in sorted(_scan_dir_for_debug(d, depth=1), reverse=True):
            add(p)
    return ordered


def find_debug_json(cfg, extra_paths=()):
    """返回优先级最高的识别 debug JSON, 没有则 None。"""
    cands = candidate_debug_jsons(cfg, extra_paths)
    return cands[0] if cands else None


def region_out_dir(cfg, json_path):
    """输出目录: 界面「区域范围输出目录」优先, 否则放识别 JSON 旁边。"""
    v = (cfg.get("regionOut") or "").strip()
    if v:
        return v
    base = os.path.dirname((cfg.get("outputDir") or "").strip() or json_path)
    return os.path.join(base, "LBD区域_支架范围")


def _area(b):
    return max(0.0, b["x2"] - b["x1"]) * max(0.0, b["y2"] - b["y1"])


def _inter(a, b):
    w = max(0.0, min(a["x2"], b["x2"]) - max(a["x1"], b["x1"]))
    h = max(0.0, min(a["y2"], b["y2"]) - max(a["y1"], b["y1"]))
    return w * h


def _center(b):
    return (b["x1"] + b["x2"]) / 2.0, (b["y1"] + b["y2"]) / 2.0


def _norm_box(b, W, H):
    return [b["x1"] / W, b["y1"] / H, b["x2"] / W, b["y2"] / H]


def _assign_parent(tb, nodes):
    """支架 -> 所属 LBD 区域: 先看中心点包含, 否则取重叠面积最大的区域。"""
    cx, cy = _center(tb)
    for n in nodes:
        nb = n["bbox"]
        if nb["x1"] <= cx <= nb["x2"] and nb["y1"] <= cy <= nb["y2"]:
            return n
    best, best_ratio = None, 0.0
    a = _area(tb)
    for n in nodes:
        r = _inter(tb, n["bbox"]) / a if a > 0 else 0.0
        if r > best_ratio:
            best, best_ratio = n, r
    return best if best_ratio > 0.02 else None


def extract_lbd_typical(json_path, out_dir, csv_encoding="utf-8-sig", want_symbols=True):
    """读 debug JSON -> 写 lbd_regions.csv / typicals.csv / lbd_symbols.csv /
    pages.csv / lbd_typical.json。返回结果摘要 dict(不抛异常)。"""
    try:
        with open(json_path, encoding="utf-8") as f:
            doc = json.load(f)
    except Exception as e:
        return {"ok": False, "error": "读取/解析 JSON 失败：%s" % e}
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception as e:
        return {"ok": False, "error": "创建输出目录失败：%s" % e}

    page_size = {}
    for pg in doc.get("input_data", {}).get("pages", []):
        page_size[pg.get("page_number")] = (pg.get("width") or 0, pg.get("height") or 0)

    tracker_pages = {p.get("page_number"): (p.get("data") or {})
                     for p in doc.get("yolo_tracker_detection_results", [])}
    box_pages = {p.get("page_number"): (p.get("data") or {})
                 for p in doc.get("yolo_box_detection_results", [])}
    ocr_pages = {p.get("page_number"): (p.get("data") or [])
                 for p in doc.get("ocr_node_name_results", [])}
    claude_pages = {p.get("page_number"): (p.get("data") or {})
                    for p in doc.get("claude_node_name_review_results", [])}
    table_pages = {p.get("page_number"): ((p.get("data") or {}).get("result") or {})
                   for p in doc.get("table_recognition_results", [])}

    if not tracker_pages:
        return {"ok": False, "error": "这份 JSON 里没有 yolo_tracker_detection_results，"
                                      "不是识别流程的 debug 结果"}

    region_rows, typical_rows, symbol_rows, page_rows = [], [], [], []
    rack_rows = rack_types_from_doc(doc)

    for page in sorted(p for p in tracker_pages if isinstance(p, int)):
        W, H = page_size.get(page, (0, 0))
        dets = tracker_pages[page].get("detections") or []
        nodes, typs = [], []
        for i, det in enumerate(dets):
            b = det.get("bbox") or {}
            if not all(k in b for k in ("x1", "y1", "x2", "y2")):
                continue
            lab = (det.get("label") or "").strip().lower()
            if lab == "node":
                nodes.append({"bbox": b, "conf": det.get("confidence")})
            elif lab in ("tracker", "typical"):
                typs.append({"bbox": b, "conf": det.get("confidence"), "idx": i})

        name_by_box = {}
        for r in ocr_pages.get(page) or []:
            nb = r.get("node_bbox") or {}
            if not all(k in nb for k in ("x1", "y1", "x2", "y2")):
                continue
            key = (round(nb["x1"], 1), round(nb["y1"], 1),
                   round(nb["x2"], 1), round(nb["y2"], 1))
            name_by_box[key] = r

        inv_name = (claude_pages.get(page) or {}).get("inv_name")
        string_by_node = {}
        for it in (table_pages.get(page) or {}).get("string_info") or []:
            if isinstance(it, dict) and it.get("node"):
                string_by_node[it["node"]] = it.get("string_number")

        regions = []
        for i, n in enumerate(nodes):
            b = n["bbox"]
            key = (round(b["x1"], 1), round(b["y1"], 1), round(b["x2"], 1), round(b["y2"], 1))
            rec = name_by_box.get(key) or {}
            name = rec.get("final_node_name") or rec.get("preliminary_node_name")
            regions.append({
                "page": page,
                "lbd_index": i + 1,
                "lbd_name": name,
                "entity_id": rec.get("entity_id"),
                "inv_name": inv_name,
                "bbox_px": [b["x1"], b["y1"], b["x2"], b["y2"]],
                "bbox_norm": _norm_box(b, W, H) if W and H else None,
                "center_px": list(_center(b)),
                "width_px": b["x2"] - b["x1"],
                "height_px": b["y2"] - b["y1"],
                "confidence": n["conf"],
                "typical_count": 0,
                "table_string_number": string_by_node.get(name) if name else None,
                "page_width": W,
                "page_height": H,
            })

        for t in typs:
            parent = _assign_parent(t["bbox"], nodes)
            pi = nodes.index(parent) if parent is not None else None
            if pi is not None:
                regions[pi]["typical_count"] += 1
            b = t["bbox"]
            typical_rows.append({
                "page": page,
                "typical_index": t["idx"] + 1,
                "lbd_index": (pi + 1) if pi is not None else None,
                "lbd_name": regions[pi]["lbd_name"] if pi is not None else None,
                "inv_name": inv_name,
                "bbox_px": [b["x1"], b["y1"], b["x2"], b["y2"]],
                "bbox_norm": _norm_box(b, W, H) if W and H else None,
                "center_px": list(_center(b)),
                "width_px": b["x2"] - b["x1"],
                "height_px": b["y2"] - b["y1"],
                "confidence": t["conf"],
                "page_width": W,
                "page_height": H,
            })

        region_rows.extend(regions)

        bdets = (box_pages.get(page) or {}).get("detections") or []
        if want_symbols:
            for j, det in enumerate(bdets):
                b = det.get("bbox") or {}
                if not all(k in b for k in ("x1", "y1", "x2", "y2")):
                    continue
                cx, cy = _center(b)
                near, best_d = None, None
                for r in regions:
                    rb = r["bbox_px"]
                    dx = max(rb[0] - cx, 0.0, cx - rb[2])
                    dy = max(rb[1] - cy, 0.0, cy - rb[3])
                    d = (dx * dx + dy * dy) ** 0.5
                    if best_d is None or d < best_d:
                        near, best_d = r, d
                symbol_rows.append({
                    "page": page,
                    "symbol_index": j + 1,
                    "nearest_lbd_index": near["lbd_index"] if near else None,
                    "nearest_lbd_name": near["lbd_name"] if near else None,
                    "distance_px": best_d,
                    "bbox_px": [b["x1"], b["y1"], b["x2"], b["y2"]],
                    "bbox_norm": _norm_box(b, W, H) if W and H else None,
                    "center_px": list(_center(b)),
                    "confidence": det.get("confidence"),
                })

        page_rows.append({
            "page": page,
            "page_width": W,
            "page_height": H,
            "lbd_region_count": len(regions),
            "typical_count": len(typs),
            "lbd_symbol_count": len(bdets),
            "inv_name": inv_name,
        })

    def write_csv(name, rows, cols):
        path = os.path.join(out_dir, name)
        with open(path, "w", newline="", encoding=csv_encoding) as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)
        return path

    region_cols = ["page", "lbd_index", "lbd_name", "inv_name", "entity_id",
                   "bbox_px", "bbox_norm", "center_px", "width_px", "height_px",
                   "typical_count", "confidence", "table_string_number",
                   "page_width", "page_height"]
    typical_cols = ["page", "typical_index", "lbd_index", "lbd_name", "inv_name",
                    "bbox_px", "bbox_norm", "center_px", "width_px", "height_px",
                    "confidence", "page_width", "page_height"]
    symbol_cols = ["page", "symbol_index", "nearest_lbd_index", "nearest_lbd_name",
                   "distance_px", "bbox_px", "bbox_norm", "center_px", "confidence"]
    page_cols = ["page", "page_width", "page_height", "lbd_region_count",
                 "typical_count", "lbd_symbol_count", "inv_name"]
    rack_cols = ["index", "strings", "code", "length_ft", "total_count",
                 "panel_label", "source"]

    files = ["lbd_regions.csv"]
    write_csv("lbd_regions.csv", region_rows, region_cols)
    files.append("typicals.csv")
    write_csv("typicals.csv", typical_rows, typical_cols)
    if want_symbols:
        files.append("lbd_symbols.csv")
        write_csv("lbd_symbols.csv", symbol_rows, symbol_cols)
    files.append("pages.csv")
    write_csv("pages.csv", page_rows, page_cols)
    if rack_rows:
        files.append("rack_types.csv")
        write_csv("rack_types.csv", rack_rows, rack_cols)

    payload = {
        "source": os.path.abspath(json_path),
        "schema_version": doc.get("schema_version"),
        "coordinate_note": "bbox_px 为原图像素; bbox_norm 为 [x1,y1,x2,y2]/页面宽高",
        "rack_types": rack_rows,
        "rack_types_text": rack_types_text(rack_rows),
        "pages": page_rows,
        "lbd_regions": region_rows,
        "typicals": typical_rows,
        "lbd_symbols": symbol_rows,
    }
    files.append("lbd_typical.json")
    with open(os.path.join(out_dir, "lbd_typical.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return {
        "ok": True,
        "source": os.path.abspath(json_path),
        "out_dir": os.path.abspath(out_dir),
        "files": files,
        "pages": len(page_rows),
        "lbd_regions": len(region_rows),
        "typicals": len(typical_rows),
        "symbols": len(symbol_rows),
        "rack_types": rack_rows,
        "rack_types_text": rack_types_text(rack_rows),
        "typicals_without_region": sum(1 for r in typical_rows if r["lbd_index"] is None),
        "unnamed_regions": sum(1 for r in region_rows if not r["lbd_name"]),
    }


def sniff_json_kind(path):
    """看这份 JSON 是哪种：'debug'(识别结果) / 'anylabeling'(标注结果) / ''(认不出)。

    逐块扫文件找关键键名，不整份 load —— 识别结果 debug JSON 动辄几百 MB。
    """
    debug_key = b'"yolo_tracker_detection_results"'
    anno_key = b'"shapes"'
    found = set()
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(4 << 20)
                if not chunk:
                    break
                if debug_key in chunk:
                    found.add("debug")
                if anno_key in chunk:
                    found.add("anylabeling")
                if found:
                    break
    except Exception:
        return ""
    if "debug" in found:
        return "debug"
    if "anylabeling" in found:
        return "anylabeling"
    return ""


# ---------------------------------------------------------------- STR 编号顺序
# 和插件 PDFGRID 的 8 种顺序一致（值就是界面上的序号）：
#   1 列优先: 左→右列、列内上→下     2 行优先: 上→下行、行内左→右
#   3 列优先: 右→左列、列内上→下     4 行优先: 下→上行、行内左→右
#   5 列优先: 左→右列、列内下→上     6 列优先: 右→左列、列内下→上
#   7 行优先: 上→下行、行内右→左     8 行优先: 下→上行、行内右→左
# 值 = (主轴, 主轴方向, 带内方向)。这里的坐标是识别 JSON 的图像坐标(y 向下)，
# 方向已按"模型空间"的语义翻译：上→下 = 图像 y 递增，下→上 = 递减。
STR_ORDERS = {
    "1": ("X", +1, +1),
    "2": ("Y", +1, +1),
    "3": ("X", -1, +1),
    "4": ("Y", -1, +1),
    "5": ("X", +1, -1),
    "6": ("X", -1, -1),
    "7": ("Y", +1, -1),
    "8": ("Y", -1, -1),
}
STR_ORDER_LABELS = [
    ("1 列优先: 左→右列、列内上→下", "1"),
    ("2 行优先: 上→下行、行内左→右", "2"),
    ("3 列优先: 右→左列、列内上→下", "3"),
    ("4 行优先: 下→上行、行内左→右", "4"),
    ("5 列优先: 左→右列、列内下→上", "5"),
    ("6 列优先: 右→左列、列内下→上", "6"),
    ("7 行优先: 上→下行、行内右→左", "7"),
    ("8 行优先: 下→上行、行内右→左", "8"),
]
DEFAULT_STR_ORDER = "2"


def norm_order(order):
    """把界面传来的顺序值归一到 "1".."8"（不合法就用默认 "2"）。"""
    key = str(order if order is not None else "").strip()
    return key if key in STR_ORDERS else DEFAULT_STR_ORDER


def _band(vals, tol):
    """把一串坐标按容差分带，返回每带的中心（升序）。"""
    if not vals:
        return []
    vals = sorted(vals)
    out, cur = [], [vals[0]]
    for v in vals[1:]:
        if v - cur[-1] <= tol:
            cur.append(v)
        else:
            out.append(sum(cur) / len(cur))
            cur = [v]
    out.append(sum(cur) / len(cur))
    return out


def _band_auto(vals):
    """同 _band()，但容差按这串坐标自己的正常间距定（相邻值中位间距的一半）。

    预览用：支架拆成几行后，同一列里的小格子间距远小于支架本身的高度，
    固定用支架高度当容差会把几行并成一行（格子叠在一起）。
    """
    if not vals:
        return []
    uniq = sorted(set(round(float(v), 3) for v in vals))
    gaps = [uniq[i + 1] - uniq[i] for i in range(len(uniq) - 1)]
    gaps = [g for g in gaps if g > 0]
    tol = 0.5 * _vals_median(gaps) if gaps else 1.0
    return _band(vals, max(1.0, tol))



def sort_items_by_order(items, med_h, order=DEFAULT_STR_ORDER, med_w=None):
    """按 8 种顺序排 items=[(cx, cy, bbox), ...]；默认 "2" 与原来的行优先一致。

    主轴是"带"的方向（X=按列分带，Y=按行分带），带内再按次方向排。
    容差取典型尺寸的 0.6 倍，避免同一行/列被拆开。
    """
    if not items:
        return []
    axis, main_dir, sec_dir = STR_ORDERS[norm_order(order)]
    med = med_w if (axis == "X" and med_w) else med_h
    tol = max(1.0, float(med or 0.0) * 0.6)
    pm = (lambda it: it[0]) if axis == "X" else (lambda it: it[1])
    ps = (lambda it: it[1]) if axis == "X" else (lambda it: it[0])
    bands = _band([pm(it) for it in items], tol)

    def bidx(v):
        return min(range(len(bands)), key=lambda i: abs(bands[i] - v))

    return sorted(items, key=lambda it: (main_dir * bidx(pm(it)), sec_dir * ps(it)))


def _row_major(items, med_h):
    """兼容老调用：等价于顺序 "2"（上→下行、行内左→右）。"""
    return sort_items_by_order(items, med_h, DEFAULT_STR_ORDER)


# ---------------------------------------------------------------- 支架拆分（一列拆成几行）
# 界面「支架」页每一类支架可以选 不拆 / 2行 / 3行：选了几行，这个支架框就沿长边均分成几段，
# 每段各给一个 STR 号（同一张支架连号，见 rack_lines_from_debug()）。
# 框属于哪一类按框长认：支架框长边 ÷ 页高 分档，档之间的比例对上支架类型「长度FT」的比例
# （本项目 13 串 214.3FT 比 9 串 100.3FT 长一倍多，两档分得很开）。


def parse_rack_split(spec):
    """界面「拆不拆」的文字 -> ({串数: 行数}, 所有类型同一规则的行数)；1 = 不拆。

    认明细行写的 "9=不拆; 13=3行"，也认 "13=2" / "13:3行"；只写 "3行" 时对所有类型生效。
    """
    by_type, all_rows = {}, 1
    for part in re.split(r"[;,\r\n]+", str(spec or "")):
        part = part.strip()
        if not part:
            continue
        key, val = None, part
        for sep in ("=", ":"):
            if sep in part:
                a, b = [x.strip() for x in part.split(sep, 1)]
                if re.fullmatch(r"\d+", a):
                    key, val = int(a), b
                else:
                    val = b or a            # 形如 "3行" / "不拆"
                break
        m = re.search(r"\d+", val)
        n = max(1, min(6, int(m.group(0)) if m else 1))
        if key is None:
            all_rows = n
        else:
            by_type[key] = n
    return by_type, all_rows


def rack_split_rows(split, strings):
    """某个支架类型（按串数）要拆成几行；1 = 不拆。split 见 parse_rack_split()。"""
    if not split:
        return 1
    by_type, all_rows = split
    try:
        s = int(float(strings))
    except (TypeError, ValueError):
        s = None
    if s is not None and s in (by_type or {}):
        return by_type[s]
    return all_rows


def split_enabled(split):
    """这套配置里有没有要拆的（全是 1 就等于没开）。"""
    by_type, all_rows = split or ({}, 1)
    return all_rows > 1 or any(int(v or 1) > 1 for v in (by_type or {}).values())


def _long_side(b):
    return max(b["x2"] - b["x1"], b["y2"] - b["y1"])


def _vals_median(vals):
    vals = sorted(vals)
    return vals[len(vals) // 2] if vals else 0.0


def _cluster_levels(vals, k, gap_ratio=0.35):
    """一串长度值 -> 最多 k 个"档"的中心（升序）。

    只在相邻值差得够开（> 35%）的地方切；切不出来就少几档（返回 1 档）。
    """
    vals = sorted(v for v in (vals or []) if v > 0)
    if not vals:
        return []
    groups = [vals]
    while len(groups) < max(1, int(k or 1)):
        best = None
        for gi, g in enumerate(groups):
            gap, cut = 0.0, None
            for i in range(len(g) - 1):
                d = g[i + 1] - g[i]
                if d > gap:
                    gap, cut = d, i
            if cut is not None and g[cut] > 0 and gap > gap_ratio * g[cut]:
                if best is None or gap > best[0]:
                    best = (gap, gi, cut)
        if best is None:
            break
        _gap, gi, cut = best
        g = groups.pop(gi)
        groups[gi:gi] = [g[:cut + 1], g[cut + 1:]]
        groups.sort(key=lambda gg: gg[0])
    return [_vals_median(g) for g in groups]


def _match_levels_to_types(levels, types, tol=0.35):
    """长度档 -> 支架类型下标（按长度FT 的比例对，不做绝对换算）；判不出返回 None。"""
    lens = [float(t.get("length_ft") or 0.0) for t in (types or [])]
    if not levels or not lens or not all(lens):
        return None
    if len(types) == 1:
        return [0] * len(levels)
    if len(levels) != len(types):
        return None
    base_l, base_t = levels[0], min(lens)
    out, used = [], set()
    for lv in levels:
        best, err = None, None
        for i, ln in enumerate(lens):
            if i in used:
                continue
            r = ln / base_t
            e = abs((lv / base_l) - r) / max(1e-9, r)
            if err is None or e < err:
                best, err = i, e
        if best is None or err is None or err > tol:
            return None
        used.add(best)
        out.append(best)
    return out


def _page_boxes(dets):
    """一页 detections -> (nodes, typs)，只留坐标齐全的框。"""
    nodes, typs = [], []
    for d in dets or []:
        b = d.get("bbox") or {}
        if not all(k in b for k in ("x1", "y1", "x2", "y2")):
            continue
        lab = (d.get("label") or "").strip().lower()
        if lab == "node":
            nodes.append({"bbox": b})
        elif lab in ("tracker", "typical"):
            typs.append({"bbox": b})
    return nodes, typs


def rack_type_indices(trk, page_size, types, split=None):
    """每一列支架框属于哪个支架类型 -> ({页号: [类型下标或 None]}, 说明文字)。

    按框长认类型：长边 ÷ 页高 分档，档的比例对上支架类型的长度FT 比例。
    整册只分出一档、而只有一类要拆时，就按那一类拆（说明里会写清楚）；
    分不出且不止一类要拆时返回空 dict（= 这次不拆，保持原样）。
    """
    types = list(types or [])
    per_page = {}
    for pg, data in (trk or {}).items():
        _W, H = page_size.get(pg, (0, 0))
        if not H:
            continue
        _n, typs = _page_boxes((data or {}).get("detections"))
        if typs:
            per_page[pg] = [_long_side(t["bbox"]) / float(H) for t in typs]
    if not per_page:
        return {}, ""
    if len(types) <= 1:
        return {pg: [0] * len(v) for pg, v in per_page.items()}, ""

    levels = _cluster_levels([v for vs in per_page.values() for v in vs], len(types))
    lvl_ty = _match_levels_to_types(levels, types)
    if lvl_ty:
        out = {}
        for pg, vals in per_page.items():
            idx = []
            for v in vals:
                bi, be = None, None
                for li, lv in enumerate(levels):
                    e = abs(v - lv) / max(1e-9, lv)
                    if be is None or e < be:
                        bi, be = li, e
                idx.append(lvl_ty[bi] if (bi is not None and be is not None and be <= 0.35) else None)
            out[pg] = idx
        return out, ""

    # 分不出档：只有一类要拆时按它拆（框都差不多长，说明这一册基本就是这一种）
    todo = [i for i, t in enumerate(types) if rack_split_rows(split, t.get("strings")) > 1]
    if len(todo) == 1:
        i = todo[0]
        return ({pg: [i] * len(v) for pg, v in per_page.items()},
                "支架框长分不出档，按要拆的那一类（%s 串）拆" % types[i].get("strings"))
    return {}, "支架框长分不出档，这次没拆（请核对支架类型的「长度FT」）"


def split_dir(order, vertical):
    """同一张支架拆出来的几段，先画哪一段：按当前编号顺序的行内/列内方向。"""
    axis, main_dir, sec_dir = STR_ORDERS[norm_order(order)]
    return main_dir if axis == ("Y" if vertical else "X") else sec_dir


def split_box(b, n, vertical, forward=True):
    """把一个支架框沿长边均分成 n 段（n 就是界面上选的行数），返回 n 个框。"""
    n = max(1, int(n or 1))
    if n <= 1:
        return [dict(b)]
    out = []
    if vertical:
        step = (b["y2"] - b["y1"]) / float(n)
        for i in range(n):
            out.append({"x1": b["x1"], "x2": b["x2"],
                        "y1": b["y1"] + i * step, "y2": b["y1"] + (i + 1) * step})
    else:
        step = (b["x2"] - b["x1"]) / float(n)
        for i in range(n):
            out.append({"x1": b["x1"] + i * step, "x2": b["x1"] + (i + 1) * step,
                        "y1": b["y1"], "y2": b["y2"]})
    if not forward:
        out.reverse()
    return out


def expand_racks(racks, order):
    """[(cx, cy, bbox, 拆几行, 类型串数), ...]（已排好序）
    -> [(cx, cy, 小框, 原框, 拆几行, 类型串数), ...]。

    同一张支架的几行连在一起、连号；不拆的框原样返回。
    原框一起带出去：角度/字高按整张支架算，不按拆出来的小段算。
    """
    out = []
    for cx, cy, b, n, key in racks:
        n = max(1, int(n or 1))
        if n <= 1:
            out.append((cx, cy, dict(b), b, n, key))
            continue
        vertical = (b["y2"] - b["y1"]) >= (b["x2"] - b["x1"])   # 竖条=竖着拆成几行
        for sb in split_box(b, n, vertical, split_dir(order, vertical) >= 0):
            sx, sy = _center(sb)
            out.append((sx, sy, sb, b, n, key))
    return out


def count_splits(racks):
    """[(cx, cy, bbox, 拆几行, 类型串数), ...] -> {类型串数: [行数, 支架张数]}（只为日志/提示）。"""
    counts = {}
    for it in racks or []:
        try:
            n, key = int(it[3] or 1), it[4]
        except (IndexError, TypeError, ValueError):
            continue
        if n > 1:
            c = counts.setdefault(key, [n, 0])
            c[0] = n
            c[1] += 1
    return counts


def merge_counts(dst, add):
    for key, (rows, n) in (add or {}).items():
        c = dst.setdefault(key, [rows, 0])
        c[0] = rows
        c[1] += n


def split_note(counts):
    """{支架类型串数: [行数, 支架张数]} -> 给界面看的说明（没拆就返回空串）。"""
    if not counts or not any(v[0] > 1 for v in counts.values()):
        return ""
    parts = []
    for s, (rows, n) in sorted(counts.items(), key=lambda kv: str(kv[0])):
        parts.append("%s串%s %d 张" % (s, ("拆%d行" % rows) if rows > 1 else "不拆", n))
    return "支架拆分：" + "；".join(parts)




def debug_page_map(json_path):
    """识别结果 debug JSON 里有图纸的页号 -> {真实页号: 图纸顺序号(1..N)}。

    CAD 侧是按「第几张底图」当页号的，而 PDF 常有封面/说明页，真实页码和底图顺序对不上，
    所以统一按"识别到的图纸页、页码升序"重编号。
    """
    with open(json_path, encoding="utf-8") as f:
        doc = json.load(f)
    pages = set()
    for key in ("yolo_tracker_detection_results", "yolo_box_detection_results",
                "ocr_node_name_results"):
        for p in doc.get(key) or []:
            pg = p.get("page_number")
            if isinstance(pg, int):
                pages.add(pg)
    return {pg: i + 1 for i, pg in enumerate(sorted(pages))}


def rack_lines_from_debug(json_path, prefix="STR", digits=2, page_map=None,
                           order=DEFAULT_STR_ORDER, split=None, info=None):
    """识别结果 debug JSON -> 支架号行（L 行：页号 fx fy STRxx 角度 字高占页比）。

    按所属 LBD 区域(Node 框) 分组、组内行优先（上→下、左→右）编号，每组从 01 起；
    竖条 90°、横条 0°，字高按框短边。没落在任何 LBD 区域里的支架不编号 ——
    和 frame_detect/map_lbd_str.py 的规则一致（那种框视为干扰）。

    split: 界面「支架」页每类的「拆不拆」（例 "13=3行; 9=不拆"，见 parse_rack_split()）。
           选了 N 行的支架框会沿长边均分成 N 行，每行各一个号、同一张支架连号。
    info:  可选 dict；算完把这次拆分的情况写进 info["split"]（给界面日志用）。
    page_map: {真实页号: 图纸顺序号}，给了就重编号并跳过不在里面的页（CAD 侧按底图顺序认页号）。
    返回 (行列表, 支架数, 有支架的页数)。
    """
    with open(json_path, encoding="utf-8") as f:
        doc = json.load(f)
    page_size = {}
    for pg in (doc.get("input_data") or {}).get("pages") or []:
        page_size[pg.get("page_number")] = (pg.get("width") or 0, pg.get("height") or 0)
    trk = {p.get("page_number"): (p.get("data") or {})
           for p in doc.get("yolo_tracker_detection_results") or []}
    digits = max(1, int(digits or 2))
    split_map = parse_rack_split(split)
    types = rack_types_from_doc(doc) if split_enabled(split_map) else []
    tmap, note = (rack_type_indices(trk, page_size, types, split_map) if types else ({}, ""))
    counts = {}                       # 类型下标 -> [拆几行, 列数]（只为日志）

    lines, n_str, n_pages = [], 0, 0
    # 全册统一 STR 字高：用全册支架短边中位比例，避免个别框宽窄不一致导致大小不一
    gratio = _global_short_ratio(page_size, trk)
    for pg in sorted(p for p in trk if isinstance(p, int)):
        W, H = page_size.get(pg, (0, 0))
        if not W or not H:
            continue
        pg_out = pg if page_map is None else page_map.get(pg)
        if pg_out is None:
            continue
        nodes, typs = _page_boxes((trk.get(pg) or {}).get("detections"))
        if not typs or not nodes:
            continue
        n_pages += 1

        groups, heights = {}, []
        for ti, t in enumerate(typs):
            b = t["bbox"]
            heights.append(b["y2"] - b["y1"])
            p = _assign_parent(b, nodes)
            if p is None:
                continue                      # 不在任何 LBD 区域内：不编号
            cx, cy = _center(b)
            # 这一类支架要拆几行（认不出类型就 1 = 不拆，保持原样）
            rows, tkey = 1, None
            idx = (tmap.get(pg) or [])[ti] if ti < len(tmap.get(pg) or []) else None
            if idx is not None and idx < len(types):
                tkey = types[idx].get("strings")
                rows = rack_split_rows(split_map, tkey)
            groups.setdefault(nodes.index(p), []).append((cx, cy, b, rows, tkey))
        heights.sort()
        med_h = heights[len(heights) // 2] if heights else 1.0
        med_w = _med_width(typs)
        for _key, items in groups.items():
            racks = sort_items_by_order(items, med_h, order, med_w)
            ordered = expand_racks(racks, order)
            merge_counts(counts, count_splits(racks))
            for k, (cx, cy, b, ob, _n, _t) in enumerate(ordered, 1):
                nm = "%s%s" % (prefix, str(k).zfill(digits))
                bw, bh = ob["x2"] - ob["x1"], ob["y2"] - ob["y1"]
                ang = 90 if bh > bw else 0
                lines.append("L\t%d\t%.6f\t%.6f\t%s\t%d\t%.6f"
                             % (pg_out, cx / float(W), 1.0 - cy / float(H), nm, ang,
                                gratio if gratio > 0 else min(bw, bh) / float(H)))
                n_str += 1
    if info is not None:
        info["split"] = note or split_note(counts)
    return lines, n_str, n_pages


def extract_lines_from_debug(json_path, out_path, prefix="STR", digits=2, page_map=None,
                             order=DEFAULT_STR_ORDER, split=None):
    """识别结果 debug JSON -> CAD 读的 L 行（和 X-AnyLabeling 那条路输出同一套格式）。

        L <页号> <fx> <fy> <名称> <角度> <字高占页比>      fx/fy 归一化、y 从下往上

    - LBD 区域(Node 框)：名称取 OCR 的最终名（如 INV11A101-LBD-05），角度 0、字高 0；
      CAD 侧拿这个名字去 Excel 分表里找要填的正式名称。
    - 支架(Tracker 框)：按所属 LBD 分组、组内行优先编号 STR01、STR02…（和
      frame_detect/map_lbd_str.py 的规则一致）；竖条 90°、横条 0°，字高按框短边。
      没落在任何 LBD 区域里的支架视为干扰，不编号（和 map_lbd_str.py 一样）。

    split: 界面「支架」页每类的「拆不拆」（例 "13=3行; 9=不拆"）：选了 N 行的支架框
           沿长边均分成 N 行，每行各一个号（同一张支架连号）。
    返回 dict：{ok, lines, lbd, str, pages} 或 {ok: False, error}。
    """
    try:
        with open(json_path, encoding="utf-8") as f:
            doc = json.load(f)
    except Exception as e:
        return {"ok": False, "error": "读取识别结果失败：%s" % e}

    page_size = {}
    for pg in (doc.get("input_data") or {}).get("pages") or []:
        page_size[pg.get("page_number")] = (pg.get("width") or 0, pg.get("height") or 0)
    ocr = {p.get("page_number"): (p.get("data") or [])
           for p in doc.get("ocr_node_name_results") or []}
    trk = {p.get("page_number"): (p.get("data") or {})
           for p in doc.get("yolo_tracker_detection_results") or []}
    if not trk:
        return {"ok": False, "error": "这份 JSON 里没有 yolo_tracker_detection_results，"
                                      "不是识别结果 debug JSON"}

    digits = max(1, int(digits or 2))
    split_map = parse_rack_split(split)
    types = rack_types_from_doc(doc) if split_enabled(split_map) else []
    tmap, note = (rack_type_indices(trk, page_size, types, split_map) if types else ({}, ""))
    counts = {}                       # 类型下标 -> [拆几行, 列数]（只为日志）
    lines, n_lbd, n_str, n_pages = [], 0, 0, 0
    # 全册统一 STR 字高（同 rack_lines_from_debug）
    gratio = _global_short_ratio(page_size, trk)
    for pg in sorted(p for p in trk if isinstance(p, int)):
        W, H = page_size.get(pg, (0, 0))
        if not W or not H:
            continue
        pg_out = pg if page_map is None else page_map.get(pg)
        if pg_out is None:
            continue
        nodes, typs = _page_boxes((trk.get(pg) or {}).get("detections"))
        if not nodes and not typs:
            continue
        n_pages += 1

        # Node 名称：OCR 结果按 node_bbox 对上（坐标一致，做了 0.1 像素取整）
        name_by_key = {}
        for r in ocr.get(pg) or []:
            nb = r.get("node_bbox") or {}
            if not all(k in nb for k in ("x1", "y1", "x2", "y2")):
                continue
            key = (round(nb["x1"], 1), round(nb["y1"], 1),
                   round(nb["x2"], 1), round(nb["y2"], 1))
            name_by_key[key] = (r.get("final_node_name")
                                or r.get("preliminary_node_name") or "").strip()
        for n in nodes:
            b = n["bbox"]
            key = (round(b["x1"], 1), round(b["y1"], 1),
                   round(b["x2"], 1), round(b["y2"], 1))
            n["name"] = name_by_key.get(key, "")
            if not n["name"]:
                continue
            cx, cy = _center(b)
            # 第 7 列 = LBD 区域(Node)宽 / 页高：CAD 端字高 = 该比例 x 底图高 x 倍数(1.4)
            lines.append("L\t%d\t%.6f\t%.6f\t%s\t0\t%.6f"
                         % (pg_out, cx / float(W), 1.0 - cy / float(H), n["name"],
                            max(1.0, b["x2"] - b["x1"]) / float(H)))
            n_lbd += 1

        groups, heights = {}, []
        for ti, t in enumerate(typs):
            b = t["bbox"]
            heights.append(b["y2"] - b["y1"])
            p = _assign_parent(b, nodes)
            if p is None or not p.get("name"):
                continue
            cx, cy = _center(b)
            # 这一类支架要拆几行（认不出类型就 1 = 不拆，保持原样）
            rows, tkey = 1, None
            idx = (tmap.get(pg) or [])[ti] if ti < len(tmap.get(pg) or []) else None
            if idx is not None and idx < len(types):
                tkey = types[idx].get("strings")
                rows = rack_split_rows(split_map, tkey)
            groups.setdefault(p["name"], []).append((cx, cy, b, rows, tkey))
        heights.sort()
        med_h = heights[len(heights) // 2] if heights else 1.0
        med_w = _med_width(typs)
        for _grp, items in groups.items():
            racks = sort_items_by_order(items, med_h, order, med_w)
            ordered = expand_racks(racks, order)
            merge_counts(counts, count_splits(racks))
            for k, (cx, cy, b, ob, _n, _t) in enumerate(ordered, 1):
                nm = "%s%s" % (prefix, str(k).zfill(digits))
                bw, bh = ob["x2"] - ob["x1"], ob["y2"] - ob["y1"]
                ang = 90 if bh > bw else 0
                lines.append("L\t%d\t%.6f\t%.6f\t%s\t%d\t%.6f"
                             % (pg_out, cx / float(W), 1.0 - cy / float(H), nm, ang,
                                gratio if gratio > 0 else min(bw, bh) / float(H)))
                n_str += 1

    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + ("\n" if lines else ""))
    except Exception as e:
        return {"ok": False, "error": "写提取文件失败：%s" % e}
    return {"ok": True, "lines": len(lines), "lbd": n_lbd, "str": n_str,
            "pages": n_pages, "path": os.path.abspath(out_path),
            "split": note or split_note(counts)}


def page_region_bounds(json_path):
    """JSON -> 每页 LBD 区域(Node 大框) 的合并范围。

    返回 [(page, fx1, fy1, fx2, fy2), ...]，按页码升序：
    归一化 0~1，x 从左往右、y 从下往上（和提取文件 L 行的 fx/fy 同一套坐标系）。
    页面尺寸取 input_data.pages；没有 LBD 区域的页不会出现在结果里。
    """
    with open(json_path, encoding="utf-8") as f:
        doc = json.load(f)
    page_size = {}
    for pg in (doc.get("input_data") or {}).get("pages") or []:
        page_size[pg.get("page_number")] = (pg.get("width") or 0, pg.get("height") or 0)

    box = {}                      # page -> [x1, y1, x2, y2] (原图像素)
    for p in doc.get("yolo_tracker_detection_results") or []:
        pg = p.get("page_number")
        dets = (p.get("data") or {}).get("detections") or []
        for det in dets:
            if (det.get("label") or "").strip().lower() != "node":
                continue
            b = det.get("bbox") or {}
            if not all(k in b for k in ("x1", "y1", "x2", "y2")):
                continue
            try:
                x1, y1, x2, y2 = (float(b["x1"]), float(b["y1"]),
                                  float(b["x2"]), float(b["y2"]))
            except Exception:
                continue
            cur = box.get(pg)
            if cur is None:
                box[pg] = [x1, y1, x2, y2]
            else:
                cur[0] = min(cur[0], x1)
                cur[1] = min(cur[1], y1)
                cur[2] = max(cur[2], x2)
                cur[3] = max(cur[3], y2)

    rows = []
    for pg in sorted(p for p in box if isinstance(p, int)):
        W, H = page_size.get(pg, (0, 0))
        if not W or not H:
            continue
        x1, y1, x2, y2 = box[pg]
        rows.append((pg, x1 / float(W), 1.0 - y2 / float(H),
                     x2 / float(W), 1.0 - y1 / float(H)))
    return rows


def write_region_file(json_path, out_path, page_start=1, count=0):
    """按识别结果写「每页 LBD 区域上下限」文件，给 CAD 侧对准视口用。

    每行 `R <序号> <fx1> <fy1> <fx2> <fy2>`（归一化，y 从下往上），序号从 1 开始、
    与布局/图纸的先后顺序一一对应；某页没有区域数据就写整页(0,0,1,1)，等于不缩放。
    """
    try:
        by_page = {pg: (a, b, c, d) for (pg, a, b, c, d) in page_region_bounds(json_path)}
    except Exception as e:
        return {"ok": False, "error": "读取识别结果失败：%s" % e}
    if not by_page:
        return {"ok": False, "error": "识别结果里没有 LBD 区域（Node 框）"}

    try:
        count = int(count or 0)
    except Exception:
        count = 0
    try:
        page_start = int(page_start or 1)
    except Exception:
        page_start = 1
    want = list(range(page_start, page_start + count)) if count > 0 else sorted(by_page)

    lines, hit = [], 0
    for i, pg in enumerate(want, 1):
        v = by_page.get(pg)
        if v is None:
            lines.append("R\t%d\t0.000000\t0.000000\t1.000000\t1.000000" % i)
        else:
            hit += 1
            lines.append("R\t%d\t%.6f\t%.6f\t%.6f\t%.6f" % ((i,) + v))
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except Exception as e:
        return {"ok": False, "error": "写区域范围文件失败：%s" % e}
    return {"ok": True, "path": os.path.abspath(out_path),
            "pages": len(lines), "with_region": hit}


def summary_text(r):
    """把 extract_lbd_typical 的结果转成一行给人看的说明。"""
    if not r.get("ok"):
        return "区域范围导出失败：" + str(r.get("error"))
    msg = ("区域范围已导出：LBD 区域 %d 个 / 支架(Typical) %d 个 / 页 %d"
           % (r["lbd_regions"], r["typicals"], r["pages"]))
    if r.get("rack_types_text"):
        msg += "\n  支架类型：%s" % r["rack_types_text"]
    if r.get("typicals_without_region"):
        msg += "（%d 个支架未落入任何区域）" % r["typicals_without_region"]
    return msg + "\n  → " + r["out_dir"]


def main():
    ap = argparse.ArgumentParser(description="LBD 区域范围 / Typical(支架)范围提取")
    ap.add_argument("--json", required=True, help="识别结果 debug JSON 路径")
    ap.add_argument("--out", default="", help="输出目录(默认放 JSON 旁边)")
    ap.add_argument("--no-symbols", action="store_true", help="不导出 LBD 符号小框")
    a = ap.parse_args()
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.json)), "LBD区域_支架范围")
    r = extract_lbd_typical(a.json, out, want_symbols=not a.no_symbols)
    print(summary_text(r))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())


def _global_short_ratio(page_size, trk):
    """全册 tracker 短边(占页高)的中位数；取不到返回 0（退回按每个框各算）。"""
    vals = []
    for pg, data in (trk or {}).items():
        H = (page_size.get(pg) or (0, 0))[1]
        if not H:
            continue
        for d in (data or {}).get("detections") or []:
            b = d.get("bbox") or {}
            if not all(k in b for k in ("x1", "y1", "x2", "y2")):
                continue
            if (d.get("label") or "").strip().lower() not in ("tracker", "typical"):
                continue
            vals.append(min(b["x2"] - b["x1"], b["y2"] - b["y1"]) / float(H))
    if not vals:
        return 0.0
    vals.sort()
    return vals[len(vals) // 2]


def _med_width(typs):
    """Tracker 框宽的中位数（按列排序时定容差用）。"""
    ws = sorted((t["bbox"]["x2"] - t["bbox"]["x1"]) for t in typs)
    return ws[len(ws) // 2] if ws else 1.0


def preview_group(json_path, order=DEFAULT_STR_ORDER, prefix="STR", digits=2, split=None):
    """给界面预览用：取第一张有 Tracker 的图里"支架最多的那个 LBD 组"。

    返回 {"page": 页号, "group": 组名, "cols": 列数, "rows": 行数,
          "items": [(编号, 列号, 行号), ...], "count": n, "hint": 说明}；
    读不到返回 None。items 已按 order 排好，编号就是最终画到图上的 STR 号。
    列/行号由支架中心按 X/Y 分带得到（左上角为 (0, 0)）。

    split: 界面「支架」页每类的「拆不拆」；选了行的支架在预览里也按拆后的格子画，
           编号和实际画到图上的一致（同一张支架连号）。
    """
    try:
        with open(json_path, encoding="utf-8") as f:
            doc = json.load(f)
    except Exception:
        return None
    ocr = {p.get("page_number"): (p.get("data") or [])
           for p in doc.get("ocr_node_name_results") or []}
    trk = {p.get("page_number"): (p.get("data") or {})
           for p in doc.get("yolo_tracker_detection_results") or []}
    order = norm_order(order)
    digits = max(1, int(digits or 2))
    page_size = {}
    for pgd in (doc.get("input_data") or {}).get("pages") or []:
        page_size[pgd.get("page_number")] = (pgd.get("width") or 0, pgd.get("height") or 0)
    split_map = parse_rack_split(split)
    types = rack_types_from_doc(doc) if split_enabled(split_map) else []
    tmap, note = (rack_type_indices(trk, page_size, types, split_map) if types else ({}, ""))
    counts = {}

    for pg in sorted(p for p in trk if isinstance(p, int)):
        nodes, typs = _page_boxes((trk.get(pg) or {}).get("detections"))
        if not typs or not nodes:
            continue
        for r in ocr.get(pg) or []:
            nb = r.get("node_bbox") or {}
            if not all(k in nb for k in ("x1", "y1", "x2", "y2")):
                continue
            key = (round(nb["x1"], 1), round(nb["y1"], 1), round(nb["x2"], 1), round(nb["y2"], 1))
            nm = (r.get("final_node_name") or r.get("preliminary_node_name") or "").strip()
            for n in nodes:
                b = n["bbox"]
                if key == (round(b["x1"], 1), round(b["y1"], 1),
                           round(b["x2"], 1), round(b["y2"], 1)):
                    n["name"] = nm
        groups, heights = {}, []
        for ti, t in enumerate(typs):
            b = t["bbox"]
            heights.append(b["y2"] - b["y1"])
            p = _assign_parent(b, nodes)
            if p is None or not p.get("name"):
                continue
            cx, cy = _center(b)
            rows, tkey = 1, None
            idx = (tmap.get(pg) or [])[ti] if ti < len(tmap.get(pg) or []) else None
            if idx is not None and idx < len(types):
                tkey = types[idx].get("strings")
                rows = rack_split_rows(split_map, tkey)
            groups.setdefault(p["name"], []).append((cx, cy, b, rows, tkey))
        if not groups:
            continue
        heights.sort()
        med_h = heights[len(heights) // 2] if heights else 1.0
        med_w = _med_width(typs)
        gname = max(groups, key=lambda k: len(groups[k]))       # 支架最多的那个组
        racks = sort_items_by_order(groups[gname], med_h, order, med_w)
        items = expand_racks(racks, order)                      # 拆成几行的按拆后画
        merge_counts(counts, count_splits(racks))

        # 按 X / Y 分带得到列号 / 行号（左上角为 (0,0)）；
        # 容差按格子间距自己定，拆成几行的小格子才不会被并回一行。
        xb = _band_auto([it[0] for it in items])
        yb = _band_auto([it[1] for it in items])

        def cidx(v, bands):
            return min(range(len(bands)), key=lambda i: abs(bands[i] - v))

        data = [(("%s%s" % (prefix, str(i).zfill(digits))),
                 cidx(it[0], xb), cidx(it[1], yb))
                for i, it in enumerate(items, 1)]
        hint = "第 %s 页 · %s · %d 个号（%s ~ %s）" % (pg, gname, len(data),
                                                        data[0][0], data[-1][0])
        extra = note or split_note(counts)
        if extra:
            hint += "；" + extra
        return {"page": pg, "group": gname, "items": data, "count": len(data),
                "cols": len(xb), "rows": len(yb), "order": order,
                "hint": hint}
    return None


def write_region_file_for_sheets(json_path, out_path, sheets):
    """按"布局顺序"（= Excel 分表顺序）写区域文件：R 行序号与布局/图纸一一对应。

    布局名来自 Excel 分表名，而区域数据在识别结果里；用 OCR 认出的 LBD 名
    （如 INV11A101-LBD-15）反查属于哪个分表、在哪一页，再取那一页 LBD 区域的合并范围。
    反查不到的分表写整页 (0,0,1,1)，CAD 侧按整页对准，不会对错图。
    """
    try:
        by_page = {pg: (a, b, c, d) for (pg, a, b, c, d) in page_region_bounds(json_path)}
    except Exception as e:
        return {"ok": False, "error": "读取识别结果失败：%s" % e}
    sheet_page = {}
    try:
        with open(json_path, encoding="utf-8") as f:
            doc = json.load(f)
        for p in doc.get("ocr_node_name_results") or []:
            pg = p.get("page_number")
            if pg not in by_page:
                continue
            for r in (p.get("data") or []):
                nm = (r.get("final_node_name") or r.get("preliminary_node_name") or "").strip().upper()
                i = nm.find("-LBD-")
                if i > 0:
                    sheet_page.setdefault(nm[:i], pg)
    except Exception:
        pass

    lines, hit, miss = [], 0, []
    for i, name in enumerate(sheets or [], 1):
        pg = sheet_page.get(str(name or "").strip().upper())
        v = by_page.get(pg) if pg is not None else None
        if v is None:
            miss.append(str(name))
            lines.append("R\t%d\t0.000000\t0.000000\t1.000000\t1.000000" % i)
        else:
            hit += 1
            lines.append("R\t%d\t%.6f\t%.6f\t%.6f\t%.6f" % ((i,) + v))
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + ("\n" if lines else ""))
    except Exception as e:
        return {"ok": False, "error": "写区域文件失败：%s" % e}
    return {"ok": True, "path": out_path, "pages": len(sheets or []),
            "with_region": hit, "miss": miss}
