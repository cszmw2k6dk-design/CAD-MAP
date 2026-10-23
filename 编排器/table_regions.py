# -*- coding: utf-8 -*-
"""识别页底部排布表的可选 OCR。

先用低成本几何规则圈出图纸下半部，再用 RapidOCR 读表格；识别结果保存为：
  tables: [{page, bbox, rows, confidence, ...}]
  page_regions: {页号: {"table_bbox": ..., "fit_bbox": ...}}
不依赖 PDF 文字层，所以栅格化/扫描表格也能处理。
"""
import math
import re
import statistics


LBD_RE = re.compile(r"\b(?:[A-Z0-9]+[-_])*LBD[-_ ]?(\d{1,4})\b", re.I)
STR_RE = re.compile(r"(\d{1,4})\s*(?:[- ]?STR(?:ING)?S?|STRINGS?)", re.I)
TRACKER_RE = re.compile(r"(\d{1,4})\s*(?:TRACKERS?|TRKS?|RACKS?)\b", re.I)
TYPE_STR_RE = re.compile(r"(?:LBD\s*[- ]*)?(\d{1,3})\s*H(?:[-_ ]|$)", re.I)


def _text(line):
    try:
        return str(line[1] or "").strip()
    except Exception:
        return ""


def _box(line, ox=0.0, oy=0.0):
    try:
        pts = line[0]
        xs = [float(p[0]) + ox for p in pts]
        ys = [float(p[1]) + oy for p in pts]
        return min(xs), min(ys), max(xs), max(ys)
    except Exception:
        return 0.0, 0.0, 0.0, 0.0


def _score(line):
    try:
        return float(line[2])
    except Exception:
        return 0.0


try:
    from rapidocr import RapidOCR
except Exception:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception:
        RapidOCR = None


def _result_lines(out):
    """兼容 RapidOCR 3.x 的 RapidOCROutput 和旧版三元组列表。"""
    if hasattr(out, "boxes") and hasattr(out, "txts"):
        boxes = out.boxes if out.boxes is not None else []
        txts = out.txts if out.txts is not None else []
        scores = out.scores if getattr(out, "scores", None) is not None else []
        rows = []
        for i, txt in enumerate(txts):
            if i >= len(boxes):
                continue
            sc = scores[i] if i < len(scores) else 0.0
            rows.append([boxes[i], str(txt), float(sc)])
        return rows
    if isinstance(out, tuple):
        return out[0] or []
    return out or []


def _norm_lbd(name):
    m = LBD_RE.search(str(name or "").upper())
    return ("LBD-%s" % m.group(1)) if m else ""


def _union(boxes):
    boxes = [b for b in boxes if b]
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def _node_bbox_px(dets):
    boxes = []
    for d in dets or []:
        if (d.get("label") or "") != "Node":
            continue
        b = d.get("bbox") or {}
        try:
            boxes.append((float(b["x1"]), float(b["y1"]),
                          float(b["x2"]), float(b["y2"])))
        except Exception:
            pass
    return _union(boxes)


def _group_rows(items, max_height):
    """按 OCR 字的纵向中心分组；表格行通常一行一个 LBD 编号。"""
    if not items:
        return []
    hs = [max(1.0, it["box"][3] - it["box"][1]) for it in items]
    # 表格行距很近；0.75 倍字高会把相邻两行合成一行，0.30 倍足够吸收
    # 同一行里不同字号造成的基线偏差，又不会跨行。
    tol = max(3.0, statistics.median(hs) * 0.30)
    rows = []
    for it in sorted(items, key=lambda x: ((x["box"][1] + x["box"][3]) / 2.0, x["box"][0])):
        cy = (it["box"][1] + it["box"][3]) / 2.0
        hit = None
        for row in reversed(rows[-8:]):
            if abs(cy - row["cy"]) <= tol:
                hit = row
                break
        if hit is None:
            hit = {"cy": cy, "items": []}
            rows.append(hit)
        hit["items"].append(it)
    for row in rows:
        row["items"].sort(key=lambda x: x["box"][0])
        row["text"] = " ".join(x["text"] for x in row["items"])
        row["box"] = _union([x["box"] for x in row["items"]])
    return rows


def _parse_row(row):
    text = row["text"]
    lm = LBD_RE.search(text.upper())
    if not lm:
        return None
    strings = sorted(set(int(x) for x in STR_RE.findall(text)))
    trackers = [int(x) for x in TRACKER_RE.findall(text)]
    type_strings = sorted(set(int(x) for x in TYPE_STR_RE.findall(text)))
    total = strings[0] if strings else None
    count = trackers[0] if trackers else None
    per_tracker = None
    if total and count and count > 0 and total % count == 0:
        per_tracker = total // count
    if len(type_strings) == 1:
        per_tracker = type_strings[0]
    full_m = re.search(r"(?:[A-Z0-9]+[-_])*LBD[-_ ]?\d{1,4}", text.upper())
    confidence = 0.90 if (total or type_strings) else 0.55
    return {
        "lbd": "LBD-%s" % lm.group(1),
        "full_name": full_m.group(0) if full_m else "",
        "full_text": text,
        "bbox": [round(x, 2) for x in row["box"]],
        "total_strings": total,
        "total_strings_list": strings,
        "type_strings": type_strings,
        "tracker_count": count,
        "strings_per_tracker": per_tracker,
        "confidence": confidence,
    }


def extract_table(image, page_no, detections=None, ocr=None, max_width=1300):
    """OCR 图纸下部表格，返回结构化表格；RapidOCR 不可用时返回 error。"""
    if RapidOCR is None:
        return {"page": page_no, "error": "rapidocr_missing"}

    image = image.convert("RGB")
    W, H = image.size
    nb = _node_bbox_px(detections)
    # 表格通常在主体阵列下方；有 Node 框时从阵列底部附近开始，避免整页 OCR。
    y0 = int(H * 0.50)
    if nb:
        y0 = max(y0, min(int(H * 0.72), int(nb[3] + H * 0.03)))
    x0, x1 = int(W * 0.01), int(W * 0.78)
    y1 = int(H * 0.995)
    if y1 - y0 < 80:
        return {"page": page_no, "error": "table_band_too_small"}

    try:
        engine = ocr or RapidOCR()
    except Exception as e:
        return {"page": page_no, "error": "ocr_failed", "detail": str(e)}

    def _cy(it):
        return (it["box"][1] + it["box"][3]) / 2.0

    items, parsed, header, data_items = [], [], [], []
    fast_mode = False
    # 第一轮只扫表格左半部（LBD 编号、LBD GROUP TYPE、STRINGS 等关键列）。
    # 读不到 LBD 行时再回退完整表宽，避免格式变化导致漏读。
    attempts = [
        (True, x0 + int((x1 - x0) * 0.40), min(1000, max_width)),
        (False, x1, max_width),
    ]
    for fast, cx1, attempt_width in attempts:
        crop = image.crop((x0, y0, cx1, y1))
        if crop.width > attempt_width:
            nh = max(1, int(round(crop.height * attempt_width / float(crop.width))))
            crop = crop.resize((int(attempt_width), nh))
        try:
            try:
                result = _result_lines(engine(crop, use_cls=False))
            except TypeError:
                result = _result_lines(engine(crop))
        except Exception as e:
            if not fast:
                return {"page": page_no, "error": "ocr_failed", "detail": str(e)}
            continue

        sx = (cx1 - x0) / float(max(1, crop.width))
        sy = (y1 - y0) / float(max(1, crop.height))
        items = []
        for line in result or []:
            txt = _text(line)
            if not txt:
                continue
            bx = _box(line, x0, y0)
            # crop 曾缩放时要把 OCR 坐标换回页面像素
            bx = (x0 + (bx[0] - x0) * sx, y0 + (bx[1] - y0) * sy,
                  x0 + (bx[2] - x0) * sx, y0 + (bx[3] - y0) * sy)
            items.append({"text": txt, "box": bx, "score": _score(line)})

        header_items = [it for it in items
                        if re.search(r"(?:LBD\s*GROUP|STRINGS?|TRACKERS?|TRKS?|QTY|COUNT)",
                                     it["text"], re.I)]
        header = []
        if header_items:
            h_top = min(_cy(it) for it in header_items)
            h_bottom = max(it["box"][3] for it in header_items) + 8.0
            header = [it for it in items if h_top - 14.0 <= _cy(it) <= h_bottom]
            hx1 = min(it["box"][0] for it in header) - W * 0.01
            hx2 = max(it["box"][2] for it in header) + W * 0.04
            data_items = [it for it in items
                          if _cy(it) > h_bottom and hx1 <= it["box"][0] <= hx2]
        else:
            data_items = items

        rows = _group_rows(data_items, H)
        parsed = []
        for row in rows:
            rec = _parse_row(row)
            if rec:
                parsed.append(rec)
        if len(parsed) >= 2:
            fast_mode = fast
            break
    if not parsed:
        return {"page": page_no, "error": "lbd_rows_not_found",
                "items": [{"text": x["text"], "bbox": [round(v, 2) for v in x["box"]]}
                          for x in items]}

    selected = header + data_items
    table_box = _union([it["box"] for it in selected]) or _union(
        [(r["bbox"][0], r["bbox"][1], r["bbox"][2], r["bbox"][3]) for r in parsed])
    if table_box:
        table_box = (max(0, table_box[0] - W * 0.005),
                     max(0, table_box[1] - H * 0.005),
                     min(W, (x1 if fast_mode else table_box[2] + W * 0.02)),
                     min(H, table_box[3] + H * 0.012))
    norm = None
    if table_box:
        norm = [round(table_box[0] / W, 6), round(table_box[1] / H, 6),
                round(table_box[2] / W, 6), round(table_box[3] / H, 6)]
    return {
        "page": page_no,
        "bbox": [round(v, 2) for v in table_box] if table_box else None,
        "bbox_normalized": norm,
        "rows": parsed,
        "row_count": len(parsed),
        "confidence": round(sum(r["confidence"] for r in parsed) / len(parsed), 3),
        "coordinate_system": "original_page_pixels",
        "fast_mode": fast_mode,
    }


def apply_hints(shapes, table):
    """把表格里的 strings 写回 Node 内的 Tracker（只在可确定时写 strings）。"""
    rows = (table or {}).get("rows") or []
    if not rows:
        return 0
    nodes = [s for s in shapes if (s.get("label") or "") == "Node"]
    trackers = [s for s in shapes if (s.get("label") or "") == "Tracker"]
    if not nodes or not trackers:
        return 0
    by_name = {}
    for s in nodes:
        key = _norm_lbd(s.get("name"))
        if key:
            by_name[key] = s
    used, applied = set(), 0
    for i, rec in enumerate(rows):
        node = by_name.get(rec.get("lbd"))
        if node is None and len(rows) == len(nodes):
            node = nodes[i]
        if node is None:
            continue
        nb = node.get("bbox") or []
        if len(nb) < 4:
            continue
        inside = []
        for tr in trackers:
            b = tr.get("bbox") or []
            if len(b) < 4:
                continue
            cx, cy = (float(b[0]) + float(b[2])) / 2.0, (float(b[1]) + float(b[3])) / 2.0
            if float(nb[0]) <= cx <= float(nb[2]) and float(nb[1]) <= cy <= float(nb[3]):
                inside.append(tr)
        total = rec.get("total_strings")
        per = rec.get("strings_per_tracker")
        options = sorted(set(rec.get("type_strings") or []))
        groups = {}
        for tr in inside:
            b = tr.get("bbox") or []
            if len(b) < 4:
                continue
            length = max(float(b[2]) - float(b[0]), float(b[3]) - float(b[1]))
            key = next((k for k in groups if abs(length - k) <= 0.10 * max(k, 1.0)), length)
            groups.setdefault(key, []).append(tr)
        ordered_groups = sorted(groups.items(), key=lambda kv: kv[0])
        if len(options) == len(ordered_groups) and len(options) > 1:
            assignments = {id(tr): options[i]
                           for i, (_ln, arr) in enumerate(ordered_groups)
                           for tr in arr}
        else:
            assignments = {}
            if not per and total and inside and int(total) % len(inside) == 0:
                per = int(total) // len(inside)
            if per:
                assignments = {id(tr): int(per) for tr in inside}
        for tr in inside:
            raw = dict(tr.get("raw") or {})
            raw["table_strings_total"] = total
            raw["table_strings_options"] = options
            raw["table_confidence"] = rec.get("confidence")
            raw["table_lbd"] = rec.get("lbd")
            if id(tr) in assignments:
                raw["strings"] = int(assignments[id(tr)])
                raw["strings_source"] = "table"
            tr["raw"] = raw
            used.add(id(tr))
        if inside:
            applied += len(inside)
    return applied


def filter_primary_array(dets, width, height):
    """去掉图例/表格里零散框：Node 内必须有一定数量的 Tracker 才作为主体阵列。"""
    nodes = [d for d in dets if (d.get("label") or "") == "Node"]
    trackers = [d for d in dets if (d.get("label") or "") == "Tracker"]
    if len(nodes) < 2 or len(trackers) < 2:
        return dets, {"removed": 0}, nodes

    def inside(b, q):
        try:
            cx = (float(q["x1"]) + float(q["x2"])) / 2.0
            cy = (float(q["y1"]) + float(q["y2"])) / 2.0
            return (float(b["x1"]) <= cx <= float(b["x2"]) and
                    float(b["y1"]) <= cy <= float(b["y2"]))
        except Exception:
            return False

    counts = []
    for n in nodes:
        counts.append(sum(1 for t in trackers if inside(n.get("bbox") or {}, t.get("bbox") or {})))
    med = statistics.median(counts) if counts else 0
    threshold = max(2, min(5, int(round(med * 0.50))))
    good = [n for n, c in zip(nodes, counts) if c >= threshold]
    if len(good) < 2 or len(good) < len(nodes) * 0.50:
        return dets, {"removed": 0}, good

    mx, my = float(width or 0) * 0.015, float(height or 0) * 0.015
    keep_nodes = set(id(n) for n in good)
    keep_tr = set()
    for t in trackers:
        b = t.get("bbox") or {}
        try:
            cx = (float(b["x1"]) + float(b["x2"])) / 2.0
            cy = (float(b["y1"]) + float(b["y2"])) / 2.0
        except Exception:
            continue
        if any(float(n["bbox"]["x1"]) - mx <= cx <= float(n["bbox"]["x2"]) + mx and
               float(n["bbox"]["y1"]) - my <= cy <= float(n["bbox"]["y2"]) + my
               for n in good):
            keep_tr.add(id(t))
    out = []
    removed = {"Node": 0, "Tracker": 0}
    for d in dets:
        lab = d.get("label") or ""
        if lab == "Node" and id(d) not in keep_nodes:
            removed["Node"] += 1
            continue
        if lab == "Tracker" and id(d) not in keep_tr:
            removed["Tracker"] += 1
            continue
        out.append(d)
    removed["removed"] = removed["Node"] + removed["Tracker"]
    return out, removed, good


def assign_names_from_table(nodes, table):
    """表格数量与主体 Node 数接近时，按图纸空间顺序补 LBD 名。"""
    rows = sorted((table or {}).get("rows") or [],
                  key=lambda r: int((_norm_lbd(r.get("lbd")) or "LBD-0").split("-")[-1]))
    if not nodes or not rows:
        return 0
    if len(nodes) < len(rows) or len(nodes) > len(rows) + max(3, int(len(rows) * 0.20)):
        return 0
    if sum(1 for r in rows if r.get("full_name")) < len(rows) * 0.70:
        return 0

    def center(d):
        b = d.get("bbox") or {}
        return ((float(b["x1"]) + float(b["x2"])) / 2.0,
                (float(b["y1"]) + float(b["y2"])) / 2.0)
    ordered = sorted(nodes, key=lambda d: (round(center(d)[1] / 100.0), center(d)[0]))
    filled = 0
    for node, row in zip(ordered, rows):
        name = (row.get("full_name") or row.get("lbd") or "").strip()
        if not name:
            continue
        node["name"] = name
        raw = dict(node.get("raw") or {})
        raw["name_source"] = "table"
        raw["table_confidence"] = row.get("confidence")
        node["raw"] = raw
        filled += 1
    return filled
