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
import itertools
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


# 界面「支架」页明细行手填的「长度FT」（没填时编排器会拿串数当比例给一个替代值）：
# 识别结果里没有长度时用它，把「框长分档」对到支架类型上（见 rack_type_indices）。
# 形如 {串数: 长度FT}；只按比例用，绝对值不影响结果。默认空 = 只用识别结果里的长度。
RACK_LEN_HINTS = {}


def set_rack_len_hints(hints):
    """编排器在调用前设置：{串数: 长度FT}（或按串数给的替代比例值）。"""
    global RACK_LEN_HINTS
    out = {}
    for k, v in (hints or {}).items():
        try:
            out[k] = float(v)
        except (TypeError, ValueError):
            continue
    RACK_LEN_HINTS = out
    return out


def _rack_len_hint(key):
    """从 {串数: 长度} 里按串数取值（键可能是 int / float / str）。"""
    if not RACK_LEN_HINTS or key is None:
        return None
    for k in (key, str(key)):
        if k in RACK_LEN_HINTS:
            return RACK_LEN_HINTS[k]
    try:
        return RACK_LEN_HINTS.get(int(key))
    except (TypeError, ValueError):
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
            if not rec["length_ft"]:
                # 识别结果里没有长度FT：用界面「支架」页手填的（或编排器给的替代比例值）。
                # 支架拆分就是靠它把「框长分档」对到支架类型上，不填就分不出哪一列是哪类。
                _hint = _rack_len_hint(key)
                if _hint:
                    rec["length_ft"] = _hint
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


# ------------------------------------------------- 拆开后的格子：自动分排（"自动对齐"）
# 一张支架拆成 2~3 行以后，它的每一格只有整张支架的 1/2、1/3 高。要让一个 LBD 区里的
# STR 号在整片区域里按选的顺序走同一个顺序（而不是同一张支架连号），就得先知道"哪几格
# 属于同一排"—— 这就是自动对齐：容差不再按整张支架算，改成按格子的实际尺寸自动算。


def _cell_extent_ref(cells, axis):
    """拆开后的格子在该轴上的参考尺寸（自动分排容差用）。

    取偏低的分位（1/4 位）而不是中位数：一组里混着"拆开的格子"和"没拆的整张支架"
    时，中位数会偏大，容差跟着变大会把一张支架的几行并成一排；取偏低的那一档，
    容差永远小于最小那批格子的高度，宁可分得细一点，也不会把几排并回去。
    个别识别错的小框也不会带偏（偏低的分位不是最小值）。
    """
    vals = []
    for it in cells:
        b = it[2]
        vals.append(float((b["x2"] - b["x1"]) if axis == "X" else (b["y2"] - b["y1"])))
    vals = sorted(v for v in vals if v > 0)
    return vals[len(vals) // 4] if vals else 0.0


def cell_band_tol(cells, axis, med_h=None, med_w=None):
    """分带容差（自动分排就靠这个数）。

    这一组没拆过（每格都是整张支架）：沿用老规则 —— 整张支架尺寸 × 0.6，结果和以前一样；
    拆过：按格子的实际尺寸自动定 —— 偏低分位格子尺寸 × 0.5（见 _cell_extent_ref()）。
    拆开后一格只有整张支架的 1/2、1/3，容差要是还按整张支架算，几排格子会被并成一排、
    号就串了。

    cells: expand_racks() 出来的 (cx, cy, 小框, 原框, 拆几行, 类型串数)。
    """
    if not any(int(it[4] or 1) > 1 for it in cells):
        med = med_w if (axis == "X" and med_w) else med_h
        if med:
            return max(1.0, float(med) * 0.6)
    return max(1.0, _cell_extent_ref(cells, axis) * 0.5)


def sort_cells_by_order(cells, order=DEFAULT_STR_ORDER, med_h=None, med_w=None):
    """拆开后的每一格按 8 种顺序排：一个 LBD 里的 STR 号在整片区域里走同一个顺序。

    和 sort_items_by_order() 的区别：那个按"整张支架"排，同一张支架的几格连号；
    这个按格子排，同一张支架的几格**不再连号**。例：3 张支架各拆 3 行、顺序选
    "2 行优先：上→下行、行内左→右"，编号就是第 1 排 STR01/02/03、第 2 排 04/05/06、
    第 3 排 07/08/09；顺序选列优先时就是第 1 列 01/02/03、第 2 列 04/05/06…

    行优先（顺序 2/4/7/8）按 cell_row_keys() 的 (排号, 第几格, 横向位置) 排：
    行的判据是支架框结构，不看号的像素高度，拆开后号高矮不一致也不会分错排；
    列优先（顺序 1/3/5/6）按横向位置分带、列内按高度，和以前一样。
    """
    if not cells:
        return []
    axis, main_dir, sec_dir = STR_ORDERS[norm_order(order)]
    if axis == "Y":
        keys = cell_row_keys(cells, med_h)
        idx = sorted(range(len(cells)),
                     key=lambda i: (main_dir * keys[i][0], main_dir * keys[i][1],
                                    sec_dir * keys[i][2]))
        return [cells[i] for i in idx]
    xb = _band([it[0] for it in cells], cell_band_tol(cells, "X", med_h, med_w))
    if not xb:
        return list(cells)

    def bidx(v):
        return min(range(len(xb)), key=lambda i: abs(xb[i] - v))

    return sorted(cells, key=lambda it: (main_dir * bidx(it[0]), sec_dir * it[1]))


def _cell_ordinal(it):
    """这个格子是它那张支架的第几格（0 起；竖条沿高度拆、横条沿宽度拆）。"""
    cx, cy, b, ob = it[0], it[1], it[2], it[3]
    if (ob["y2"] - ob["y1"]) >= (ob["x2"] - ob["x1"]):          # 竖条：竖着拆成几行
        step = b["y2"] - b["y1"]
        return int(round((cy - ob["y1"]) / step - 0.5)) if step > 0 else 0
    step = b["x2"] - b["x1"]
    return int(round((cx - ob["x1"]) / step - 0.5)) if step > 0 else 0


def cell_row_keys(cells, med_h=None):
    """拆开后的格子 -> 每格的 (排号, 第几格, 横向位置)。

    排号：**整张支架框**按 y 中心分带（容差 0.6 x 支架高，和支架排序同一套规则）——
    一排里支架上下错开、长短不一、各自拆几行不同，都算同一排；
    第几格：这张支架拆出来的第几段（0 起，见 _cell_ordinal()）；
    横向位置：格子的 x 中心（竖条支架就是支架中心线，横条就是那一段的中心）。

    行优先编号用这组键排序：**完全不看号的像素高度**，所以"拆开后号的高度不一致
    导致不归类为同一行"这种情况不会再出现 —— 同一排、同一格号就是同一条排线。
    """
    if not cells:
        return []
    tol = max(1.0, float(med_h or 0.0) * 0.6)
    bands = _band([(it[3]["y1"] + it[3]["y2"]) / 2.0 for it in cells], tol)

    def ridx(it):
        v = (it[3]["y1"] + it[3]["y2"]) / 2.0
        return min(range(len(bands)), key=lambda i: abs(bands[i] - v)) if bands else 0

    return [(ridx(it), _cell_ordinal(it), it[0]) for it in cells]


def align_cell_anchors(cells, med_h=None, med_w=None, label_ratio=0.0, page_h=0.0):
    """把同一排的 STR 号拉到同一条排线上（只动高度，横向不动）。

    cells: expand_racks() 出来、已按顺序排好的格子。
    返回:  和 cells 等长的 [(ax, ay), ...]；ay 就是要写进 L 行的锚点高度。

    "同一排" = **同一排支架里、第几格一样**的那些格子：
    - "排"和编号用同一套判据（cell_row_keys()）：一排支架 + 这张支架的第几格，
      不看号的像素高度，所以拆开后格子高矮不一、支架上下错开都是同一排；
    - 锚点 = 这一排这一格所有格子中心 y 的中位数（个别偏的格子带不偏整排）；
    - 夹取：把锚点夹在**自己那一格**内，保证字和背景框不出格；格子太矮放不下字时
      退回格子中心；
    - 一对一（这一排这一格只有它自己）时不动。全部都在同一个 LBD 区域内算，不跨区域。

    为什么要对齐：CAD 端是"中点对齐 + 插入点=目标点"画 STR 号的，所以一排里几个号的
    锚点高度一致时，画出来才是齐平的（见 PdfLayout_ai.lsp 的 PdfLayout_AiDrawLabels）。
    """
    out = []
    if not cells:
        return out
    keys = cell_row_keys(cells, med_h)
    groups = {}
    for i, it in enumerate(cells):
        groups.setdefault((keys[i][0], keys[i][1]), []).append(it)
    for i, it in enumerate(cells):
        cx, cy, b, ob = it[0], it[1], it[2], it[3]
        h = b["y2"] - b["y1"]
        arr = groups.get((keys[i][0], keys[i][1])) or []
        ay = cy
        if len(arr) > 1:                                   # 这一排这一格不止一个号：对齐
            ay = _vals_median([a[1] for a in arr])
        if h > 0:
            # 字高按插件同一套换算：字高占页比(第 7 列) x 底图高 x 1.4；
            # 没有全册字高时按支架框短边（和 rack_lines_from_debug 的兜底一致）。
            lh = ((float(label_ratio) * float(page_h)) if label_ratio > 0
                  else min(ob["x2"] - ob["x1"], ob["y2"] - ob["y1"])) * 1.4
            if 0 < lh < h:                                 # 夹在自己那一格内，背景框不出格
                ay = min(max(ay, b["y1"] + lh / 2.0), b["y2"] - lh / 2.0)
            elif lh > 0:                                   # 格子比字还矮：只好放回格子中心
                ay = cy
        out.append((cx, ay))
    return out


# ------------------------------------------------- 避开底图里原有的 LBD 标号（文字避让）
# 底图（PDF）上本来就印着 LBD 标号，我们画的 STR 号带背景填充会把它盖掉。避让规则：
#   1) 一排的号**一起**上下挪，挪完这一排仍然同高（各挪各的，排就散了）；
#   2) 每个号只能在**它自己那根 Typical（支架框）那一列**里上下动，不横移、不跳支架；
#   3) 取所有号都满足的公共区间，找离原位最近、又不压到底图文字的位置；
#   4) 挪不开（整列都被文字压住、或支架比号还矮）就保持原位。
_STR_CHAR_W = 0.65      # 估算：一个字宽 ≈ 0.65 x 字高（算背景框够用；竖条 90° 时框又窄又高）


def str_label_box(angle, text_len, lh):
    """STR 号在图上占的框 (宽, 高)，像素。angle=90 时文字竖排，框又窄又高。"""
    lh = max(1.0, float(lh or 0.0))
    tw = max(lh, _STR_CHAR_W * lh * max(1, int(text_len or 1)))
    if int(angle or 0) % 180 == 90:
        return lh, tw
    return tw, lh


def row_avoid_offsets(cells, anchor_y, obstacles, box_sizes, soft_boxes=(),
                      soft_zero=False, gap=0.15):
    """一排的号统一上下挪多少：返回偏移像素（+ = 往下）；没有任何可行位置返回 None。

    cells:     这一排的格子 [(cx, cy, 小框, 原框, 拆几行, 类型串数), ...]
    anchor_y:  这一排现在的公共高度（像素）
    obstacles: [(x1, y1, x2, y2), ...] 底图文字框（页像素，y 从上往下）
    box_sizes: 每个号在图上占的 (宽, 高)（像素，见 str_label_box()）
    soft_boxes: [(x1, y1, x2, y2), ...] 别的号的框（**原位**）。对这些只要求
                "不比原来压得更厉害"，免得把号挪到隔壁排的号上、两排叠在一起。
    soft_zero: True = 对别的号要求"一点都不压"（第一轮没位置时的退让方案）。
    """
    if not cells or not obstacles or not box_sizes:
        return 0.0
    # 公共可动区间：每个号都得留在自己那根 Typical 列里
    lo = hi = None
    for it, (_bw, bh) in zip(cells, box_sizes):
        ob = it[3]
        h = float(bh)
        a = float(ob["y1"]) + h / 2.0 - float(anchor_y)
        b = float(ob["y2"]) - h / 2.0 - float(anchor_y)
        if b < a:                                   # 支架比号还矮：这根挪不了
            return None
        lo = a if lo is None else max(lo, a)
        hi = b if hi is None else min(hi, b)
    if lo is None or hi < lo - 1e-9:
        return None
    g = max(1.0, float(gap) * max(float(s[1]) for s in box_sizes))
    bad = []
    for it, (bwid, bh) in zip(cells, box_sizes):
        lx1, lx2 = it[0] - float(bwid) / 2.0, it[0] + float(bwid) / 2.0
        for ox1, oy1, ox2, oy2 in obstacles:
            if ox2 < lx1 - g or ox1 > lx2 + g:      # 横向不重叠：不挡路
                continue
            ocy = (float(oy1) + float(oy2)) / 2.0
            half = (float(bh) + (float(oy2) - float(oy1))) / 2.0 + g
            bad.append((ocy - half - float(anchor_y), ocy + half - float(anchor_y)))
    # 别的号（原位）：不能比自己原来压得更厉害
    for it, (bwid, bh) in zip(cells, box_sizes):
        bx1, bx2 = it[0] - float(bwid) / 2.0, it[0] + float(bwid) / 2.0
        own1, own2 = float(anchor_y) - float(bh) / 2.0, float(anchor_y) + float(bh) / 2.0
        for sx1, sy1, sx2, sy2 in soft_boxes:
            if sx2 < bx1 - g or sx1 > bx2 + g:      # 横向不重叠：不挡
                continue
            b0 = 0.0 if soft_zero else max(0.0, min(own2, float(sy2)) - max(own1, float(sy1)))
            r = (float(bh) + (float(sy2) - float(sy1))) / 2.0 - b0 - 1.0
            if r <= 0:
                continue
            scy = (float(sy1) + float(sy2)) / 2.0
            bad.append((scy - r - float(anchor_y), scy + r - float(anchor_y)))
    # 候选：原位、可动区间两端、每个禁区两侧各让开一点
    cands = [0.0, lo, hi]
    for a, b in bad:
        cands += [a - 0.5, b + 0.5]
    ok = []
    for d in cands:
        if d < lo - 1e-9 or d > hi + 1e-9:
            continue
        if any(a - 1e-9 < d < b + 1e-9 for a, b in bad):
            continue
        ok.append(d)
    if not ok:
        return None
    ok.sort(key=lambda d: (abs(d), -d))             # 动得最少优先；一样近就往下
    return ok[0]


def avoid_cells_offsets(ordered, ys, obstacles, label_ratio=0.0, page_h=0.0,
                        text_len=5, med_h=None):
    """按排算出每个号的避让偏移（像素，和 ordered 等长）。

    ordered 已按顺序排好；ys 是每个号当前的高度（对齐后同一排相同）。
    obstacles 是这一页的底图文字框（页像素、y 从上往下）；传空就不挪。
    """
    n = len(ordered)
    off = [0.0] * n
    if not n or not obstacles:
        return off
    boxes = []
    for (_cx, _cy, _b, ob, _nn, _tt) in ordered:
        bw, bh = ob["x2"] - ob["x1"], ob["y2"] - ob["y1"]
        ang = 90 if bh > bw else 0
        lh = ((float(label_ratio) * float(page_h)) if label_ratio > 0
              else min(bw, bh)) * 1.4
        boxes.append(str_label_box(ang, text_len, lh))
    keys = cell_row_keys(ordered, med_h)
    rows = {}
    for i in range(n):
        rows.setdefault((keys[i][0], keys[i][1]), []).append(i)
    # 每个号原位占的框：给"别的号"当软障碍（防两排叠在一起）
    where = []
    for i, (_cx, _cy, _b, _ob, _nn, _tt) in enumerate(ordered):
        bwid, bh = boxes[i]
        where.append((_cx - bwid / 2.0, ys[i] - bh / 2.0,
                      _cx + bwid / 2.0, ys[i] + bh / 2.0))
    for _key, idxs in rows.items():
        sel = set(idxs)
        row_cells = [ordered[i] for i in idxs]
        row_boxes = [boxes[i] for i in idxs]
        ay = _vals_median([ys[i] for i in idxs])
        # 先找"既避开底图文字、又不比原来更压到别的号"的位置；再退一步要求"一点都不压别的号"
        d = row_avoid_offsets(row_cells, ay, obstacles, row_boxes,
                              [where[j] for j in range(n) if j not in sel])
        if d is None:
            d = row_avoid_offsets(row_cells, ay, obstacles, row_boxes,
                                  [where[j] for j in range(n) if j not in sel], soft_zero=True)
        if d is None:
            d = 0.0
        if d:
            for i in idxs:
                off[i] = d
    return off


# ---------------------------------------------------------------- 支架拆分（一列拆成几行）
# 界面「支架」页每一类支架可以选 不拆 / 2行 / 3行：选了几行，这个支架框就沿长边均分成几段，
# 每段各给一个 STR 号；一个 LBD 区里的号在整片区域里按选的顺序走同一个顺序，不是同一张
# 支架连号（见 sort_cells_by_order()）。
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


def _split_levels(vals, k, gap_ratio):
    """按 gap_ratio 切档（内部用）：每次挑"最开的那道缝"切一刀，切不满 k 档就少几档。"""
    groups = [list(vals)]
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


def _cluster_levels(vals, k, gap_ratio=0.35, relaxed_ratio=0.08):
    """一串长度值 -> 最多 k 个"档"的中心（升序）。

    先按"差得够开（> 35%）"切；切不满 k 档时，放宽到 8% 再切一次 —— 相邻支架类型
    长度只差一两成（例如 2 串/3 串）时，老阈值切不开，会退化成"整册当一类"。
    """
    vals = sorted(v for v in (vals or []) if v > 0)
    if not vals:
        return []
    out = _split_levels(vals, k, gap_ratio)
    if len(out) < max(1, int(k or 1)) and relaxed_ratio < gap_ratio:
        out2 = _split_levels(vals, k, relaxed_ratio)
        if len(out2) > len(out):
            out = out2
    return out


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


def _levels_to_types(vals, levels, types):
    """没填「长度FT」时，把长度档和支架类型对上：返回 (档 -> 类型下标, 说明文字)。

    优先按**数量**对：每档里有多少根框，和 types 里的 total_count 比，挑误差最小的
    那一种配法（本项目 3 串 6894 / 2 串 801，框数分档后 6822 / 698，一眼就对上了）。
    数量对不上（或 JSON 没给数量）时，退一步按**长度升序**对应**串数升序** ——
    串数多的支架本来就长。对不上返回 (None, "")。
    """
    if not levels or len(levels) != len(types):
        return None, ""
    sizes = [0] * len(levels)
    for v in vals:
        bi = min(range(len(levels)), key=lambda i: abs(levels[i] - v))
        sizes[bi] += 1
    counts = [int(t.get("total_count") or 0) for t in types]
    best = None
    if all(c > 0 for c in counts):
        for perm in itertools.permutations(range(len(types))):
            err = max(abs(sizes[i] - counts[perm[i]]) / float(counts[perm[i]])
                      for i in range(len(levels)))
            if best is None or err < best[0]:
                best = (err, list(perm))
    if best is not None and best[0] <= 0.35:
        note = "按框长分档 + 按数量对上类型：" + "；".join(
            "%s串 %d 张（档内 %d）" % (types[best[1][i]].get("strings"),
                                       counts[best[1][i]], sizes[i])
            for i in range(len(levels)))
        return best[1], note
    note = "按框长分档 + 按长度升序对应类型（数量对不上，建议把每类的长度FT填上）：" + "；".join(
        "%s串 %d 张" % (types[i].get("strings"), sizes[i]) for i in range(len(types)))
    return list(range(len(types))), note


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


def _type_length_ratios(types):
    """支架类型的长度FT -> 相对比例（最短的一类 = 1.0）。有缺长度就算不出，返回 None。"""
    lens = [float(t.get("length_ft") or 0.0) for t in (types or [])]
    if not lens or not all(lens):
        return None
    base = min(lens)
    if base <= 0:
        return None
    return [ln / base for ln in lens]


def _short_base(vals):
    """最短那一档的代表长度：取 [最小, 最小x1.25] 里的中位数。

    个别被切短的框（图边、识别毛刺）不会把基准带偏。
    """
    vals = sorted(v for v in (vals or []) if v > 0)
    if not vals:
        return 0.0
    grp = [v for v in vals if v <= vals[0] * 1.25]
    return _vals_median(grp) or vals[0]


def rack_type_indices(trk, page_size, types, split=None):
    """每一列支架框属于哪个支架类型 -> ({页号: [类型下标或 None]}, 说明文字)。

    按框长认类型：长边 ÷ 页高，和支架类型的长度FT 比例对。
    先按「每个框长 ÷ 最短框长」找比例最接近的一类（真实数据里 3 串支架的框长自己
    也分好几档，硬按「档数 = 类型数」对不上，会整册都不拆）；这一步分不出两类的
    才退回老办法：长边分档、档对类型。
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

    vals_all = [v for vs in per_page.values() for v in vs]

    # ① 每个框按「框长 / 最短框长」找比例最接近的支架类型
    ratios = _type_length_ratios(types)
    base = _short_base(vals_all) if ratios else 0.0
    if ratios and base > 0:
        out, hit = {}, {}
        for pg, vals in per_page.items():
            idx = []
            for v in vals:
                r = v / base
                bi, be = None, None
                for i, rr in enumerate(ratios):
                    e = abs(r - rr) / max(1e-9, rr)
                    if be is None or e < be:
                        bi, be = i, e
                if bi is not None and be is not None and be <= 0.35:
                    idx.append(bi)
                    hit[bi] = hit.get(bi, 0) + 1
                else:
                    idx.append(None)
            out[pg] = idx
        if len(hit) > 1:                     # 分出不止一类才算数
            note = "按框长比例分：" + "；".join(
                "%s串 %d 张" % (types[i].get("strings"), hit[i]) for i in sorted(hit))
            return out, note

    # ② 老办法：长边分档、档对类型
    levels = _cluster_levels(vals_all, len(types))
    lvl_ty = _match_levels_to_types(levels, types)
    note2 = ""
    if lvl_ty is None and len(levels) == len(types):
        # 没填长度FT：按 JSON 里的数量把档和类型对上（对不上再按长度升序）；对不出来就不拆
        lvl_ty, note2 = _levels_to_types(vals_all, levels, types)
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
        if note2:
            return out, note2 + "；没匹配上的框不拆"
        return out, ""

    # 分不出档：只有一类要拆时按它拆（框都差不多长，说明这一册基本就是这一种）
    todo = [i for i, t in enumerate(types) if rack_split_rows(split, t.get("strings")) > 1]
    spread = (max(vals_all) - min(vals_all)) / max(1e-9, _vals_median(vals_all))
    if len(todo) == 1 and len(levels) <= 1 and spread <= 0.25:
        i = todo[0]
        return ({pg: [i] * len(v) for pg, v in per_page.items()},
                "支架框长分不出档，按要拆的那一类（%s 串）拆" % types[i].get("strings"))
    return {}, ("支架框长分不出档（框长跨度 %.0f%%，不止一类），这次没拆 —— "
                "请把每类的「长度FT」填上，或确认识别结果里的支架类型/数量" % (spread * 100.0))


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
                           order=DEFAULT_STR_ORDER, split=None, info=None,
                           align=False, avoid=None):
    """识别结果 debug JSON -> 支架号行（L 行：页号 fx fy STRxx 角度 字高占页比）。

    按所属 LBD 区域(Node 框) 分组、组内行优先（上→下、左→右）编号，每组从 01 起；
    竖条 90°、横条 0°，字高按框短边。没落在任何 LBD 区域里的支架不编号 ——
    和 frame_detect/map_lbd_str.py 的规则一致（那种框视为干扰）。

    split: 界面「支架」页每类的「拆不拆」（例 "13=3行; 9=不拆"，见 parse_rack_split()）。
           选了 N 行的支架框会沿长边均分成 N 行、每行各一个号；号按界面上选的顺序在
           整个 LBD 区域里走同一个顺序（同一张支架的几格不再连号，见 sort_cells_by_order()）。
    info:  可选 dict；算完把这次拆分的情况写进 info["split"]（给界面日志用）。
    align: T = STR 号自动对齐（同一排的号放到同一条排线上，只动高度）；
           nil = 每个号画在自己格子的中心（老行为）。
    avoid: {图纸页号: [(fx1,fy1,fx2,fy2), ...]} 底图上原有文字（归一化，fy 从下往上）——
           给了就让 STR 号避开它：整排一起上下挪，每个号只在自己那根 Typical 列里动，
           挪完这一排仍然同高。没给就不避让。
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
            # 拆开后按"格子"重排：一个 LBD 里的 STR 号在整片区域里走同一个顺序
            ordered = sort_cells_by_order(expand_racks(racks, order), order, med_h, med_w)
            merge_counts(counts, count_splits(racks))
            # 自动对齐：同一排的号统一到一条排线上（只动高度，横向不动）
            anchors = (align_cell_anchors(ordered, med_h, med_w,
                                          label_ratio=gratio, page_h=H) if align else None)
            # 避让底图里原有的 LBD 标号：整排一起挪（各自只在自己那列 Typical 里动）
            _obs = [(_a * W, (1.0 - _d) * H, _c * W, (1.0 - _b) * H)
                    for (_a, _b, _c, _d) in ((avoid or {}).get(pg_out) or [])]
            offs = (avoid_cells_offsets(
                        ordered,
                        [a[1] for a in anchors] if anchors else [it[1] for it in ordered],
                        _obs, label_ratio=gratio, page_h=H, med_h=med_h,
                        text_len=len(prefix) + max(digits, len(str(len(ordered)))))
                    if _obs else None)
            for k, (cx, cy, b, ob, _n, _t) in enumerate(ordered, 1):
                ax, ay = anchors[k - 1] if anchors else (cx, cy)
                if offs:
                    ay += offs[k - 1]
                nm = "%s%s" % (prefix, str(k).zfill(digits))
                bw, bh = ob["x2"] - ob["x1"], ob["y2"] - ob["y1"]
                ang = 90 if bh > bw else 0
                lines.append("L\t%d\t%.6f\t%.6f\t%s\t%d\t%.6f"
                             % (pg_out, ax / float(W), 1.0 - ay / float(H), nm, ang,
                                gratio if gratio > 0 else min(bw, bh) / float(H)))
                n_str += 1
    if info is not None:
        info["split"] = note or split_note(counts)
    return lines, n_str, n_pages


def extract_lines_from_debug(json_path, out_path, prefix="STR", digits=2, page_map=None,
                             order=DEFAULT_STR_ORDER, split=None, align=False, avoid=None):
    """识别结果 debug JSON -> CAD 读的 L 行（和 X-AnyLabeling 那条路输出同一套格式）。

        L <页号> <fx> <fy> <名称> <角度> <字高占页比>      fx/fy 归一化、y 从下往上

    - LBD 区域(Node 框)：名称取 OCR 的最终名（如 INV11A101-LBD-05），角度 0、字高 0；
      CAD 侧拿这个名字去 Excel 分表里找要填的正式名称。
    - 支架(Tracker 框)：按所属 LBD 分组、组内行优先编号 STR01、STR02…（和
      frame_detect/map_lbd_str.py 的规则一致）；竖条 90°、横条 0°，字高按框短边。
      没落在任何 LBD 区域里的支架视为干扰，不编号（和 map_lbd_str.py 一样）。

    split: 界面「支架」页每类的「拆不拆」（例 "13=3行; 9=不拆"）：选了 N 行的支架框
           沿长边均分成 N 行、每行各一个号；号按界面上选的顺序在整个 LBD 区域里走
           同一个顺序（同一张支架的几格不再连号）。
    align: True = STR 号自动对齐（同一排的号放到同一条排线上，只动高度）；
           False = 每个号画在自己格子的中心（老行为）。
    avoid: {图纸页号: [(fx1,fy1,fx2,fy2), ...]} 底图上原有文字（归一化，fy 从下往上）——
           给了就让 STR 号避开它：整排一起上下挪、每个号只在自己那根 Typical 列里动，
           挪完这一排仍然同高。没给就不避让。
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
            # 拆开后按"格子"重排：一个 LBD 里的 STR 号在整片区域里走同一个顺序
            ordered = sort_cells_by_order(expand_racks(racks, order), order, med_h, med_w)
            merge_counts(counts, count_splits(racks))
            # 自动对齐：同一排的号统一到一条排线上（只动高度，横向不动）
            anchors = (align_cell_anchors(ordered, med_h, med_w,
                                          label_ratio=gratio, page_h=H) if align else None)
            # 避让底图里原有的 LBD 标号：整排一起挪（各自只在自己那列 Typical 里动）
            _obs = [(_a * W, (1.0 - _d) * H, _c * W, (1.0 - _b) * H)
                    for (_a, _b, _c, _d) in ((avoid or {}).get(pg_out) or [])]
            offs = (avoid_cells_offsets(
                        ordered,
                        [a[1] for a in anchors] if anchors else [it[1] for it in ordered],
                        _obs, label_ratio=gratio, page_h=H, med_h=med_h,
                        text_len=len(prefix) + max(digits, len(str(len(ordered)))))
                    if _obs else None)
            for k, (cx, cy, b, ob, _n, _t) in enumerate(ordered, 1):
                ax, ay = anchors[k - 1] if anchors else (cx, cy)
                if offs:
                    ay += offs[k - 1]
                nm = "%s%s" % (prefix, str(k).zfill(digits))
                bw, bh = ob["x2"] - ob["x1"], ob["y2"] - ob["y1"]
                ang = 90 if bh > bw else 0
                lines.append("L\t%d\t%.6f\t%.6f\t%s\t%d\t%.6f"
                             % (pg_out, ax / float(W), 1.0 - ay / float(H), nm, ang,
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
            编号和实际画到图上的一致（一个 LBD 走同一个顺序，同一张支架的几格不再连号）。
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
        # 拆成几行的按拆后的格子画、按格子排号（一个 LBD 走同一个顺序）
        items = sort_cells_by_order(expand_racks(racks, order), order, med_h, med_w)
        merge_counts(counts, count_splits(racks))

        # 行 = (排号, 第几格) —— 和编号、自动对齐同一套判据（不看号的像素高度）；
        # 列 = 同一排里从左到右。左上角为 (0,0)，预览画的格子就是画到图上的。
        keys = cell_row_keys(items, med_h)
        row_ids = sorted(set((k[0], k[1]) for k in keys))
        rpos = {k: i for i, k in enumerate(row_ids)}
        byrow = {}
        for i, it in enumerate(items):
            byrow.setdefault((keys[i][0], keys[i][1]), []).append((it[0], i))
        cpos, ncols = {}, 0
        for _rk, arr in byrow.items():
            for c, (_x, i) in enumerate(sorted(arr)):
                cpos[i] = c
            ncols = max(ncols, len(arr))
        data = [(("%s%s" % (prefix, str(i + 1).zfill(digits))), cpos.get(i, 0),
                 rpos[(keys[i][0], keys[i][1])]) for i in range(len(items))]
        hint = "第 %s 页 · %s · %d 个号（%s ~ %s）" % (pg, gname, len(data),
                                                        data[0][0], data[-1][0])
        extra = note or split_note(counts)
        if extra:
            hint += "；" + extra
        return {"page": pg, "group": gname, "items": data, "count": len(data),
                "cols": ncols, "rows": len(row_ids), "order": order,
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
