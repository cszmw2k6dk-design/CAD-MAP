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


def _row_major(items, med_h):
    """行优先排序：先按 y 分带，带内按 x 从左到右（和 frame_detect/map_lbd_str.py 同一套）。"""
    if not items:
        return []

    def band(vals, tol):
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

    yb = band([it[1] for it in items], max(1.0, med_h * 0.6))
    ri = lambda y: min(range(len(yb)), key=lambda i: abs(yb[i] - y))     # noqa: E731
    return sorted(items, key=lambda it: (ri(it[1]), it[0]))


def rack_lines_from_debug(json_path, prefix="STR", digits=2):
    """识别结果 debug JSON -> 支架号行（L 行：页号 fx fy STRxx 角度 字高占页比）。

    按所属 LBD 区域(Node 框) 分组、组内行优先（上→下、左→右）编号，每组从 01 起；
    竖条 90°、横条 0°，字高按框短边。没落在任何 LBD 区域里的支架不编号 ——
    和 frame_detect/map_lbd_str.py 的规则一致（那种框视为干扰）。

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

    lines, n_str, n_pages = [], 0, 0
    for pg in sorted(p for p in trk if isinstance(p, int)):
        W, H = page_size.get(pg, (0, 0))
        if not W or not H:
            continue
        nodes, typs = [], []
        for d in (trk.get(pg) or {}).get("detections") or []:
            b = d.get("bbox") or {}
            if not all(k in b for k in ("x1", "y1", "x2", "y2")):
                continue
            lab = (d.get("label") or "").strip().lower()
            if lab == "node":
                nodes.append({"bbox": b})
            elif lab in ("tracker", "typical"):
                typs.append({"bbox": b})
        if not typs or not nodes:
            continue
        n_pages += 1

        groups, heights = {}, []
        for t in typs:
            b = t["bbox"]
            heights.append(b["y2"] - b["y1"])
            p = _assign_parent(b, nodes)
            if p is None:
                continue                      # 不在任何 LBD 区域内：不编号
            cx, cy = _center(b)
            groups.setdefault(nodes.index(p), []).append((cx, cy, b))
        heights.sort()
        med_h = heights[len(heights) // 2] if heights else 1.0
        for _key, items in groups.items():
            for k, (cx, cy, b) in enumerate(_row_major(items, med_h), 1):
                nm = "%s%s" % (prefix, str(k).zfill(digits))
                bw, bh = b["x2"] - b["x1"], b["y2"] - b["y1"]
                ang = 90 if bh > bw else 0
                lines.append("L\t%d\t%.6f\t%.6f\t%s\t%d\t%.6f"
                             % (pg, cx / float(W), 1.0 - cy / float(H), nm, ang,
                                min(bw, bh) / float(H)))
                n_str += 1
    return lines, n_str, n_pages


def extract_lines_from_debug(json_path, out_path, prefix="STR", digits=2):
    """识别结果 debug JSON -> CAD 读的 L 行（和 X-AnyLabeling 那条路输出同一套格式）。

        L <页号> <fx> <fy> <名称> <角度> <字高占页比>      fx/fy 归一化、y 从下往上

    - LBD 区域(Node 框)：名称取 OCR 的最终名（如 INV11A101-LBD-05），角度 0、字高 0；
      CAD 侧拿这个名字去 Excel 分表里找要填的正式名称。
    - 支架(Tracker 框)：按所属 LBD 分组、组内行优先编号 STR01、STR02…（和
      frame_detect/map_lbd_str.py 的规则一致）；竖条 90°、横条 0°，字高按框短边。
      没落在任何 LBD 区域里的支架视为干扰，不编号（和 map_lbd_str.py 一样）。

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
    lines, n_lbd, n_str, n_pages = [], 0, 0, 0
    for pg in sorted(p for p in trk if isinstance(p, int)):
        W, H = page_size.get(pg, (0, 0))
        if not W or not H:
            continue
        dets = (trk.get(pg) or {}).get("detections") or []
        nodes, typs = [], []
        for d in dets:
            b = d.get("bbox") or {}
            if not all(k in b for k in ("x1", "y1", "x2", "y2")):
                continue
            lab = (d.get("label") or "").strip().lower()
            if lab == "node":
                nodes.append({"bbox": b})
            elif lab in ("tracker", "typical"):
                typs.append({"bbox": b})
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
            lines.append("L\t%d\t%.6f\t%.6f\t%s\t0\t0.000000"
                         % (pg, cx / float(W), 1.0 - cy / float(H), n["name"]))
            n_lbd += 1

        groups, heights = {}, []
        for t in typs:
            b = t["bbox"]
            heights.append(b["y2"] - b["y1"])
            p = _assign_parent(b, nodes)
            if p is None or not p.get("name"):
                continue
            cx, cy = _center(b)
            groups.setdefault(p["name"], []).append((cx, cy, b))
        heights.sort()
        med_h = heights[len(heights) // 2] if heights else 1.0
        for _grp, items in groups.items():
            for k, (cx, cy, b) in enumerate(_row_major(items, med_h), 1):
                nm = "%s%s" % (prefix, str(k).zfill(digits))
                bw, bh = b["x2"] - b["x1"], b["y2"] - b["y1"]
                ang = 90 if bh > bw else 0
                lines.append("L\t%d\t%.6f\t%.6f\t%s\t%d\t%.6f"
                             % (pg, cx / float(W), 1.0 - cy / float(H), nm, ang,
                                min(bw, bh) / float(H)))
                n_str += 1

    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + ("\n" if lines else ""))
    except Exception as e:
        return {"ok": False, "error": "写提取文件失败：%s" % e}
    return {"ok": True, "lines": len(lines), "lbd": n_lbd, "str": n_str,
            "pages": n_pages, "path": os.path.abspath(out_path)}


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
