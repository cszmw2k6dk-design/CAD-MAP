# -*- coding: utf-8 -*-
"""主程序自带的识别（不再外挂 Python / ultralytics）。

流程：PDF 页 → pypdfium2 渲染 → 长边平滑缩到 2560（训练口径）→ letterbox 到 2560x2560
      → onnxruntime CPU 推理 → 解码 + 每类 NMS → 页像素坐标的框。

依赖都打进主程序：onnxruntime（推理）、pypdfium2（渲染）、numpy、Pillow。
模型：编排器\\models\\v4c.onnx（classes.txt = Node,Tracker）。

命令行自测：
    python detect.py --png 某页.png              # 只跑一张图，打印框数
    python detect.py --pdf 图纸.pdf --pages 1-2  # 按页跑，打印框数
"""
import argparse
import json
import os
import sys
import time

import numpy as np

MODEL_SIDE = 2560            # 训练/推理输入边长（v4c meta：imgsz=2560）
CONF_THRES = 0.25            # 低于这个置信度不要
IOU_THRES = 0.7              # NMS 阈值（和 ultralytics 默认一致）
STRIDE = 32
PAD_VALUE = 114
RENDER_DPI = 250             # 渲染底图用的 dpi（标注工具也是 250）


def app_dir():
    """打包后是 exe 所在目录，源码跑是这个文件所在目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def model_path():
    """找模型：先找 exe 同级的 models\\v4c.onnx，再找打包进 exe 的那份。"""
    cands = [os.path.join(app_dir(), "models", "v4c.onnx")]
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        cands.append(os.path.join(meipass, "models", "v4c.onnx"))
        cands.append(os.path.join(meipass, "v4c.onnx"))
    for p in cands:
        if os.path.exists(p):
            return p
    return cands[0]


def class_names(path=None):
    """classes.txt -> ["Node", "Tracker"]；读不到给个默认。"""
    cands = []
    if path:
        cands.append(path)
    cands.append(os.path.join(app_dir(), "models", "classes.txt"))
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        cands.append(os.path.join(meipass, "models", "classes.txt"))
        cands.append(os.path.join(meipass, "classes.txt"))
    for p in cands:
        try:
            with open(p, encoding="utf-8") as f:
                names = [ln.strip() for ln in f if ln.strip()]
            if names:
                return names
        except Exception:
            continue
    return ["Node", "Tracker"]


def load_session(path=None, threads=None):
    """建 onnxruntime 会话（CPU）。"""
    import onnxruntime as ort
    p = path or model_path()
    if not os.path.exists(p):
        raise FileNotFoundError("找不到识别模型：%s" % p)
    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    if threads:
        so.intra_op_num_threads = int(threads)
    return ort.InferenceSession(p, so, providers=["CPUExecutionProvider"])


def prep_image(pil_img, side=MODEL_SIDE):
    """长边先平滑缩到 side（训练时就是这么喂的），再 letterbox。

    返回 (NCHW float32, 原图→letterbox 的总缩放比 s, 左右 pad dw, 上下 pad dh)。
    换算回页像素：x = (框x - dw) / s，y = (框y - dh) / s。
    """
    from PIL import Image
    im = pil_img.convert("RGB")
    w, h = im.size
    long_side = max(w, h)
    pre = 1.0
    if long_side > side:
        sc = float(side) / float(long_side)
        im = im.resize((max(1, int(round(w * sc))), max(1, int(round(h * sc)))), Image.LANCZOS)
        w, h = im.size
        pre = sc
    r = min(float(side) / float(w), float(side) / float(h))
    nw, nh = max(1, int(round(w * r))), max(1, int(round(h * r)))
    if (nw, nh) != (w, h):
        im = im.resize((nw, nh), Image.BILINEAR)
    canvas = Image.new("RGB", (side, side), (PAD_VALUE, PAD_VALUE, PAD_VALUE))
    dw, dh = (side - nw) // 2, (side - nh) // 2
    canvas.paste(im, (dw, dh))
    arr = np.asarray(canvas, dtype=np.float32) / 255.0
    arr = np.transpose(arr, (2, 0, 1))[None, ...]
    return np.ascontiguousarray(arr), r * pre, dw, dh


def _nms(boxes, scores, iou_thres=IOU_THRES):
    """标准 NMS，boxes = [[x1,y1,x2,y2], ...]，返回保留的下标。"""
    order = scores.argsort()[::-1]
    keep = []
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    while order.size:
        i = order[0]
        keep.append(int(i))
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(x1[i], x1[rest])
        yy1 = np.maximum(y1[i], y1[rest])
        xx2 = np.minimum(x2[i], x2[rest])
        yy2 = np.minimum(y2[i], y2[rest])
        inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
        union = areas[i] + areas[rest] - inter
        iou = np.where(union > 0, inter / np.maximum(union, 1e-9), 0.0)
        order = rest[iou <= iou_thres]
    return keep


def detect_pil(session, pil_img, conf=CONF_THRES, iou=IOU_THRES, names=None, side=MODEL_SIDE):
    """一张图 -> [{"label","confidence","class_id","bbox":{x1,y1,x2,y2}}]（页像素）。"""
    names = names or class_names()
    x, r, dw, dh = prep_image(pil_img, side)
    inp = session.get_inputs()[0].name
    out = session.run(None, {inp: x})[0]
    pred = np.asarray(out)
    if pred.ndim == 3:
        pred = pred[0]
    if pred.shape[0] < pred.shape[1]:        # (4+nc, N) -> (N, 4+nc)
        pred = pred.T
    boxes_xywh = pred[:, :4]
    cls_scores = pred[:, 4:]
    if cls_scores.shape[1] == 0:
        return []
    cls_id = cls_scores.argmax(axis=1)
    score = cls_scores[np.arange(cls_scores.shape[0]), cls_id]
    m = score >= float(conf)
    if not np.any(m):
        return []
    boxes_xywh = boxes_xywh[m]
    cls_id = cls_id[m]
    score = score[m]
    # cx,cy,w,h -> x1,y1,x2,y2（letterbox 坐标）
    cx, cy, bw, bh = boxes_xywh[:, 0], boxes_xywh[:, 1], boxes_xywh[:, 2], boxes_xywh[:, 3]
    boxes = np.stack([cx - bw / 2.0, cy - bh / 2.0, cx + bw / 2.0, cy + bh / 2.0], axis=1)
    keep = []
    for c in np.unique(cls_id):
        sel = np.where(cls_id == c)[0]
        sub = _nms(boxes[sel], score[sel], iou)
        keep.extend(sel[sub].tolist())
    dets = []
    for i in sorted(keep, key=lambda k: -float(score[k])):
        b = boxes[i]
        x1 = (float(b[0]) - dw) / r
        y1 = (float(b[1]) - dh) / r
        x2 = (float(b[2]) - dw) / r
        y2 = (float(b[3]) - dh) / r
        ci = int(cls_id[i])
        dets.append({"label": names[ci] if ci < len(names) else str(ci),
                     "confidence": round(float(score[i]), 6),
                     "class_id": ci,
                     "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2}})
    return dets


def render_page(pdf_path, page_no, dpi=RENDER_DPI):
    """PDF 第 page_no 页（1 起）-> PIL RGB 图，按 dpi 渲染。"""
    import pypdfium2 as pdfium
    from PIL import Image
    pdf = pdfium.PdfDocument(pdf_path)
    try:
        page = pdf[page_no - 1]
        bitmap = page.render(scale=dpi / 72.0)
        return bitmap.to_pil().convert("RGB")
    finally:
        try:
            pdf.close()
        except Exception:
            pass


def pdf_page_count(pdf_path):
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(pdf_path)
    try:
        return len(pdf)
    finally:
        try:
            pdf.close()
        except Exception:
            pass


def pdf_text_runs(pdf, page_no, gap_scale=1.2):
    """用 pdfium（pypdfium2）取一页的文字条 —— 比 pypdf 快几百倍。

    pdf 可以是路径，也可以是已打开的 PdfDocument（整册跑时传同一个，省得反复开）。
    返回 [(文字, fx中心, fy中心, fx1, fy1, fx2, fy2, True)]：归一化坐标，fy 从下往上，
    和标注工具那套 text_items 完全一致（最后那个 True = 框是实测的字框，不是估的）。
    """
    import pypdfium2 as pdfium
    close = isinstance(pdf, (str, bytes, os.PathLike))
    doc = pdfium.PdfDocument(pdf) if close else pdf
    try:
        page = doc[page_no - 1]
        tp = page.get_textpage()
        # 注意：get_charbox() 给的是「未旋转」页面坐标系里的字框，而底图是
        # 按显示方向渲染的（/Rotate 270 的图纸会转 90°）。以前直接拿
        # page.get_size()（旋转后的尺寸）去除，旋转页的文字坐标就会算飞
        # （HIGHLAND 那本 y 归一化后到 1.44），编号自然一个都配不上。
        # 这里统一换算到「显示画面」的归一化坐标，fy 自下往上。
        mb = page.get_mediabox()
        ox, oy = float(mb[0]), float(mb[1])
        W0 = float(mb[2] - mb[0]) or 1.0
        H0 = float(mb[3] - mb[1]) or 1.0
        rot = int(page.get_rotation() or 0) % 360

        def norm_pt(x, y):
            u = (float(x) - ox) / W0
            v = (float(y) - oy) / H0          # 自下往上
            if rot == 90:
                return (v, 1.0 - u)
            if rot == 180:
                return (1.0 - u, v)
            if rot == 270:
                return (1.0 - v, u)
            return (u, v)

        n = tp.count_chars()
        chars = []
        for i in range(n):
            ch = tp.get_text_range(i, 1)
            if not ch:
                continue
            x1, y1, x2, y2 = tp.get_charbox(i)
            chars.append((ch, float(x1), float(y1), float(x2), float(y2)))
        if not chars:
            return []
        hs = sorted(max(0.5, c[4] - c[2]) for c in chars)
        med_h = hs[len(hs) // 2]
        tol = max(1.5, gap_scale * med_h)
        runs, cur = [], []
        for ch, x1, y1, x2, y2 in chars:
            if ch.strip() == "":                 # 空格/换行 -> 断开
                if cur:
                    runs.append(cur)
                    cur = []
                continue
            if cur:
                px1, py1, px2, py2 = cur[-1][1:]
                gx = max(x1 - px2, px1 - x2, 0.0)
                gy = max(y1 - py2, py1 - y2, 0.0)
                if max(gx, gy) > tol:
                    runs.append(cur)
                    cur = []
            cur.append((ch, x1, y1, x2, y2))
        if cur:
            runs.append(cur)
        items = []
        for run in runs:
            txt = "".join(c[0] for c in run).strip()
            if not txt:
                continue
            x1 = min(c[1] for c in run)
            x2 = max(c[3] for c in run)
            y1 = min(c[2] for c in run)
            y2 = max(c[4] for c in run)
            # 换算到显示画面（旋转页要跟着转），fy 自下往上 —— 命名那套就是这么用的
            fx1, fy1 = norm_pt(x1, y1)
            fx2, fy2 = norm_pt(x2, y2)
            items.append((txt, (fx1 + fx2) / 2.0, (fy1 + fy2) / 2.0,
                          min(fx1, fx2), min(fy1, fy2),
                          max(fx1, fx2), max(fy1, fy2), True))
        return items
    finally:
        if close:
            try:
                doc.close()
            except Exception:
                pass


def detect_pdf(pdf_path, pages=None, dpi=RENDER_DPI, session=None, conf=CONF_THRES,
               iou=IOU_THRES, progress=None):
    """整册识别 -> {页号: {"width","height","detections":[...]}}。

    pages = None 表示全部；progress(done, total, page_no) 回调用来更新进度条。
    """
    import pypdfium2 as pdfium
    sess = session or load_session()
    names = class_names()
    pdf = pdfium.PdfDocument(pdf_path)
    try:
        total = len(pdf)
        todo = list(pages) if pages else list(range(1, total + 1))
        out = {}
        for n, pg in enumerate(todo):
            if not (1 <= pg <= total):
                continue
            page = pdf[pg - 1]
            bitmap = page.render(scale=dpi / 72.0)
            im = bitmap.to_pil().convert("RGB")
            dets = detect_pil(sess, im, conf=conf, iou=iou, names=names)
            out[pg] = {"width": im.width, "height": im.height, "detections": dets}
            if progress:
                try:
                    progress(n + 1, len(todo), pg)
                except Exception:
                    pass
        return out
    finally:
        try:
            pdf.close()
        except Exception:
            pass


def debug_json(pdf_path, results, pages_meta=None):
    """识别结果 -> 标注工具同款 agent3-debug-v1 JSON（下游标签流程直接吃）。"""
    pages = []
    for pg, r in sorted(results.items()):
        pages.append({"page_number": pg, "media_type": "image/png",
                      "width": r["width"], "height": r["height"]})
    trk = []
    for pg, r in sorted(results.items()):
        dets = []
        for d in r["detections"]:
            dets.append({"label": d["label"], "confidence": d["confidence"],
                         "class_id": d["class_id"],
                         "bbox": {"x1": round(d["bbox"]["x1"], 2), "y1": round(d["bbox"]["y1"], 2),
                                  "x2": round(d["bbox"]["x2"], 2), "y2": round(d["bbox"]["y2"], 2)},
                         "source": d.get("source") or "v4c-onnx",
                         "raw": dict(d.get("raw") or {})})
        trk.append({"page_number": pg,
                    "data": {"model_type": "tracker",
                             "coordinates": "original_page_pixels",
                             "scale_to_original_page": {"sx": 1.0, "sy": 1.0},
                             "detections": dets, "error": None}})
    return {"schema_version": "agent3-debug-v1",
            "generator": "Voltage-CAD MAP 内置识别（v4c.onnx / onnxruntime）",
            "source_pdf": os.path.basename(pdf_path or ""),
            "render_dpi": float(RENDER_DPI),
            "input_data": {"project_name": os.path.splitext(os.path.basename(pdf_path or ""))[0],
                           "pages": pages},
            "yolo_tracker_detection_results": trk,
            "yolo_box_detection_results": [],
            "ocr_node_name_results": []}


def _shapes_of(dets):
    """检测结果 -> 标注工具那套 shapes（dict）：label / bbox(列表) / confidence / raw。"""
    out = []
    for d in dets:
        b = d["bbox"]
        out.append({"label": d["label"], "bbox": [b["x1"], b["y1"], b["x2"], b["y2"]],
                    "confidence": d.get("confidence"), "name": d.get("name") or "",
                    "raw": dict(d.get("raw") or {})})
    return out


def dedup_dets(dets):
    """去掉画重了的框（同类、重叠 ≥30%），返回 (保留的检测, 统计)。

    判重用标注工具那套 lbd_naming.clean_shapes：同类框之间
      · 交并比 ≥ 30%，或
      · 交叠面积占「较小那个框」≥ 30%
    就算同一个东西，留置信度高的那个。

    注意这里只开「高重叠」这一条：
      use_number=False —— 这会儿还没配编号，按编号去重没意义；
      use_shape=False  —— 那条规则（Tracker 宽高比）是给标注工具的数据写的，
                          主程序识别出来的支架框是正常矩形，套上去会全被删。
    """
    import lbd_naming as N
    if not dets:
        return dets, {}
    shapes = []
    for d in dets:
        b = d.get("bbox") or {}
        shapes.append({"label": d.get("label"),
                       "bbox": [b.get("x1", 0), b.get("y1", 0), b.get("x2", 0), b.get("y2", 0)],
                       "confidence": d.get("confidence"),
                       "raw": {},
                       "source": d.get("source") or "v4c-onnx"})
    try:
        kept, stats = N.clean_shapes(shapes, keep_manual=True, use_number=False,
                                     use_shape=False, clean_manual=False)
    except Exception:
        return dets, {}
    keep_ids = set(id(s) for s in kept)
    out = [d for d, s in zip(dets, shapes) if id(s) in keep_ids]
    return out, stats


def filter_extra_rack_rows(dets, ratio=0.65):
    """删除夹在两条正常 row 之间的多余 Tracker 行。

    正常 row 距取本页相邻 row 距的中位数。若某行到上下两行的距离都异常小，
    且两段距离之和约等于一个正常 row 距，就只删除中间这一行。
    Node 和正常 Tracker 不受影响。
    """
    trackers = [(i, d) for i, d in enumerate(dets)
                if (d.get("label") or "") in ("Tracker", "Typical")]
    if len(trackers) < 3:
        return dets, {"removed": 0}
    shorts = []
    for _i, d in trackers:
        b = d.get("bbox") or {}
        try:
            shorts.append(min(float(b["x2"]) - float(b["x1"]),
                              float(b["y2"]) - float(b["y1"])))
        except Exception:
            pass
    if not shorts:
        return dets, {"removed": 0}
    shorts.sort()
    tol = max(3.0, shorts[len(shorts) // 2] * 0.35)
    pts = []
    for i, d in trackers:
        b = d.get("bbox") or {}
        try:
            cy = (float(b["y1"]) + float(b["y2"])) / 2.0
        except Exception:
            continue
        pts.append((cy, i))
    if len(pts) < 3:
        return dets, {"removed": 0}
    pts.sort()
    rows, cur = [], [(pts[0][0], pts[0][1])]
    for cy, i in pts[1:]:
        mean = sum(v[0] for v in cur) / len(cur)
        if abs(cy - mean) <= tol:
            cur.append((cy, i))
        else:
            rows.append(cur)
            cur = [(cy, i)]
    rows.append(cur)
    if len(rows) < 3:
        return dets, {"removed": 0}
    centers = [sum(v[0] for v in row) / len(row) for row in rows]
    gaps = [centers[i + 1] - centers[i] for i in range(len(centers) - 1)]
    positive = sorted(g for g in gaps if g > 0)
    if len(positive) < 2:
        return dets, {"removed": 0}
    normal = positive[len(positive) // 2]
    if normal <= 0:
        return dets, {"removed": 0}
    drop_rows = set()
    for i in range(1, len(rows) - 1):
        a, b = gaps[i - 1], gaps[i]
        if (a < ratio * normal and b < ratio * normal
                and 0.80 * normal <= a + b <= 1.20 * normal):
            drop_rows.add(i)
    if not drop_rows:
        return dets, {"removed": 0}
    drop_idx = {idx for i in drop_rows for _cy, idx in rows[i]}
    kept = [d for i, d in enumerate(dets) if i not in drop_idx]
    return kept, {
        "removed": len(drop_idx),
        "rows_removed": len(drop_rows),
        "normal_gap": round(normal, 2),
        "threshold": round(normal * ratio, 2),
    }


def drop_outliers(dets, width, height, min_count=8, gap_ratio=0.10):
    """【暂未启用】去掉离「主体」很远的框（同一张图上的细节图 / 角落误检）。

    注意：实测这套判据删得太多（阵列边缘 / 细节图会被误删），
    detect_and_name 里已经不去调它了；等阈值和判据调稳再启用。

    做法：按类别把中心点连成一簇簇 —— 两个框中心相距 ≤ gap_ratio × 页面长边就算同一簇
    （单链接，图纸阵列里支架挨得近，整片阵列是一簇；角落里单独的细节图是另一簇）。
    只保留**框最多的那一簇**，其余全删（"离大部分位置很远的一律删掉"）。
    该类框少于 min_count 个时不动（样本太少，分不出主体）。
    返回 (保留的检测, {"removed": n, "by_label": {类: n}})。
    """
    if not dets:
        return dets, {"removed": 0, "by_label": {}}
    W, H = float(width or 0), float(height or 0)
    if not W or not H:
        return dets, {"removed": 0, "by_label": {}}
    tol = gap_ratio * max(W, H)
    by_label = {}
    for d in dets:
        by_label.setdefault((d.get("label") or "").strip(), []).append(d)
    kill = set()
    by = {}
    for lab, arr in by_label.items():
        if len(arr) < min_count:
            continue
        cs = []
        for d in arr:
            b = d.get("bbox") or {}
            cs.append(((b.get("x1", 0) + b.get("x2", 0)) / 2.0,
                       (b.get("y1", 0) + b.get("y2", 0)) / 2.0))
        # 并查集（单链接聚类）
        par = list(range(len(cs)))

        def find(i):
            while par[i] != i:
                par[i] = par[par[i]]
                i = par[i]
            return i

        for i in range(len(cs)):
            for j in range(i + 1, len(cs)):
                dx = cs[i][0] - cs[j][0]
                dy = cs[i][1] - cs[j][1]
                if dx * dx + dy * dy <= tol * tol:
                    a, b_ = find(i), find(j)
                    if a != b_:
                        par[a] = b_
        cnt = {}
        for i in range(len(cs)):
            r = find(i)
            cnt[r] = cnt.get(r, 0) + 1
        main = max(cnt, key=lambda k2: cnt[k2]) if cnt else None
        if main is None:
            continue
        for d, i in zip(arr, range(len(cs))):
            if find(i) != main:
                kill.add(id(d))
                by[lab] = by.get(lab, 0) + 1
    if not kill:
        return dets, {"removed": 0, "by_label": {}}
    return [d for d in dets if id(d) not in kill], {"removed": len(kill), "by_label": by}


def rack_length_groups(per_page, text_items_of, dpi=RENDER_DPI, tol=0.10):
    """整册支架按长度聚类，长度直接用框长（页面像素）。

    不再读图纸比例尺换算英尺（用户要求：就用本身长度）。按长度差 ≤tol 分档，
    同一档的框长本身一致（同分辨率渲染），不需要比例尺也分得对。
    返回 (分组列表, 说明)。每组 = {"length": 中位长度, "unit": "像素",
                                    "count": 根数, "pages": {页号: 根数}}
    """
    items = []
    for pg, res in sorted(per_page.items()):
        for d in res["detections"]:
            if d["label"] != "Tracker":
                continue
            b = d["bbox"]
            L = max(b["x2"] - b["x1"], b["y2"] - b["y1"])
            items.append((L, pg))
    if not items:
        return [], ""
    items.sort(key=lambda t: t[0])
    groups = []
    for L, pg in items:
        if groups:
            m = sum(x[0] for x in groups[-1]) / len(groups[-1])
            if abs(L - m) <= tol * m:
                groups[-1].append((L, pg))
                continue
        groups.append([(L, pg)])
    out = []
    for g in groups:
        ls = sorted(x[0] for x in g)
        pages = {}
        for _L, pg in g:
            pages[pg] = pages.get(pg, 0) + 1
        out.append({"length": ls[len(ls) // 2], "unit": "像素",
                    "count": len(g), "pages": pages})
    note = "整册 %d 根支架，按长度差≤10%% 分成 %d 档：%s" % (
        len(items), len(out),
        "；".join("%.1f%s %d 根" % (g["length"], g["unit"], g["count"]) for g in out))
    return out, note


def detect_and_name(pdf_path, pages=None, sheets=None, sheet_names=None, dpi=RENDER_DPI,
                    session=None, conf=CONF_THRES, iou=IOU_THRES, progress=None,
                    log=None, rack_strings=None, keep_tables=False,
                    filter_interference=False):
    """识别整册（或指定页）+ 配 LBD 编号 + 支架长度分档 -> (agent3-debug dict, 摘要)。

    sheets     : {分表名: {LBD编号: 名称长度}}（来自标签文件；没有就传 None）
    rack_strings: {档位中位长度四舍五入值: 串数}（界面「支架类型」给的），给了才写 raw.strings
    """
    import lbd_naming as N
    sess = session or load_session()
    if log:
        log("模型会话就绪（%s）" % os.path.basename(model_path()))
    names = class_names()
    # 文字层：默认走 pdfium（快几百倍）；万一取不到再退回 pypdf 那套
    text_cache = {}

    def _text_of(pg):
        if pg not in text_cache:
            try:
                text_cache[pg] = pdf_text_runs(pdf_path, pg)
            except Exception:
                text_cache[pg] = None
        if text_cache[pg] is None:
            if not hasattr(detect_and_name, "_pypdf_cache"):
                detect_and_name._pypdf_cache = N.PdfText(pdf_path)
            text_cache[pg] = detect_and_name._pypdf_cache.items(pg)
        return text_cache[pg]
    sheets = sheets or {}
    sheet_names = list(sheet_names or (sheets or {}))
    total = pdf_page_count(pdf_path) if pdf_path else 0
    todo = list(pages) if pages else list(range(1, total + 1))

    per_page, text_of = {}, {}
    table_by_page = {}
    table_engine = None
    table_module = None
    filtered_total = 0
    rack_row_filtered = 0
    if keep_tables or filter_interference:
        try:
            import table_regions as table_module
            if keep_tables:
                table_engine = table_module.RapidOCR()
        except Exception as e:
            if log:
                log("表格 OCR 未启用：%s" % e)
            table_module = None
    for n, pg in enumerate(todo):
        if log:
            log("第 %s 页：渲染 + 推理…" % pg)
        im = render_page(pdf_path, pg, dpi)
        dets = detect_pil(sess, im, conf=conf, iou=iou, names=names)
        # 去重叠：同类框重叠 ≥30% 只留一个（模型解码自带的 NMS 阈值 0.7 太松，
        # 同一根支架被画成两个框的情况要在这里收掉）
        dets, _dd = dedup_dets(dets)
        if _dd.get("by_overlap"):
            if log:
                log("第 %s 页：去掉 %d 个重叠框（%d -> %d）"
                    % (pg, _dd.get("by_overlap"), _dd.get("total", 0), len(dets)))
        # 离群框过滤先停用：实测删得太多（细节图/阵列边缘会被误删）。
        # drop_outliers() 留着，等判据调好再在这里接回来。
        if filter_interference and table_module is not None:
            dets, _filt, good_nodes = table_module.filter_primary_array(
                dets, im.width, im.height)
            filtered_total += int((_filt or {}).get("removed") or 0)
            if _filt.get("removed") and log:
                log("第 %s 页：过滤图例/表格干扰框 %d 个（Node %d、Tracker %d）"
                    % (pg, _filt.get("removed"), _filt.get("Node", 0),
                       _filt.get("Tracker", 0)))
        else:
            good_nodes = [d for d in dets if d.get("label") == "Node"]
        dets, _rowf = filter_extra_rack_rows(dets)
        rack_row_filtered += int(_rowf.get("removed") or 0)
        if _rowf.get("removed") and log:
            log("第 %s 页：过滤两条正常 row 之间的多余支架 %d 根"
                "（正常 row 距 %.1f，判定阈值 %.1f）"
                % (pg, _rowf.get("removed"), _rowf.get("normal_gap") or 0,
                   _rowf.get("threshold") or 0))
        per_page[pg] = {"width": im.width, "height": im.height, "detections": dets}
        if table_module is not None:
            if log:
                log("第 %s 页：读取底部表格（OCR）…" % pg)
            tinfo = table_module.extract_table(im, pg, dets, ocr=table_engine)
            if tinfo.get("rows"):
                table_by_page[pg] = tinfo
                if filter_interference:
                    named = table_module.assign_names_from_table(good_nodes, tinfo)
                    if named:
                        # 名字写到检测框后，_shapes_of 会原样交给命名流程。
                        for d in good_nodes:
                            d["name"] = d.get("name") or ""
                        if log:
                            log("第 %s 页：按表格顺序补了 %d 个 LBD 名" % (pg, named))
                if log:
                    log("第 %s 页：表格 %d 行，可信度 %.2f"
                        % (pg, tinfo.get("row_count") or 0,
                           tinfo.get("confidence") or 0.0))
            elif log:
                log("第 %s 页：没读到表格 LBD 行（%s）"
                    % (pg, tinfo.get("error") or "empty"))
        text_of[pg] = _text_of(pg) if pdf_path else []
        if progress:
            try:
                progress(n + 1, len(todo), pg, "识别")
            except TypeError:
                progress(n + 1, len(todo), pg)

    # 图纸页顺序：有 Node 的页按页号排（= 标签表分表的顺序）
    drawing = sorted(pg for pg, r in per_page.items()
                     if any(d["label"] == "Node" for d in r["detections"]))
    by_order = {}
    for i, pg in enumerate(drawing):
        if i < len(sheet_names):
            by_order[pg] = sheet_names[i]

    stat = {"pages": len(per_page), "named": 0, "auto": 0, "missed": 0, "pos": 0}
    for pg, r in per_page.items():
        ts = text_of.get(pg) or []
        sheet = None
        if sheet_names:
            sheet, _c = N.page_sheet_by_text(ts, sheet_names)
            sheet = sheet or by_order.get(pg)
        num_set = set((sheets.get(sheet) or {}).keys()) if sheet else set()
        shapes = _shapes_of(r["detections"])
        st = N.autofill_shapes(shapes, ts, sheet, num_set, r["width"], r["height"])
        # 表格补出的 LBD 名优先保留：autofill_shapes 在文字层读不到时会重置 name。
        for d, s in zip(r["detections"], shapes):
            if d.get("label") == "Node" and (d.get("name") or "").strip() \
                    and not (s.get("name") or "").strip():
                s["name"] = d.get("name")
                if (d.get("raw") or {}).get("name_source") == "table":
                    raw = dict(s.get("raw") or {})
                    raw["name_source"] = "table"
                    raw["table_confidence"] = (d.get("raw") or {}).get("table_confidence")
                    s["raw"] = raw
        # 读不到具体编号的：先把同页公共前缀（如 INV11A101-LBD-）填上，
        # 用户只要补后面的数字（生成 L 行时前缀-only 的仍算"没名字"，不会画出半截标签）
        _pref = N.lbd_prefix_of([s.get("name") for s in shapes
                                 if s.get("label") == "Node"])
        if _pref:
            for s in shapes:
                if s.get("label") == "Node" and not (s.get("name") or "").strip():
                    s["name"] = _pref
        table_info = table_by_page.get(pg)
        if table_module is not None and table_info:
            table_module.apply_hints(shapes, table_info)
        # 写回：名字 + 位置（label_pos / label_bbox）挂回检测框
        for d, s in zip(r["detections"], shapes):
            d["raw"] = s.get("raw") or {}
            if s["label"] == "Node":
                d["name"] = (s.get("name") or "").strip()
                d["_auto"] = bool(s.get("_auto"))
                d["_miss"] = bool(s.get("_miss"))
                d["_check"] = bool(s.get("_check"))
        stat["named"] += st.get("filled", 0)
        stat["auto"] += st.get("auto", 0)
        stat["missed"] += st.get("missed", 0)
        stat["pos"] += st.get("pos_added", 0)
        if log:
            log("第 %s 页：%s" % (pg, "识别完" if not st.get("total")
                                else "LBD %d 个（读到编号 %d、按标签表推 %d、没读到 %d）"
                                % (st.get("total"), st.get("filled"), st.get("auto"),
                                   st.get("missed"))))

    groups, gnote = rack_length_groups(per_page, lambda pg: text_of.get(pg) or [], dpi=dpi)
    # 每根支架的长度也写进 raw —— 「支架类型」的应用 / 点档位跳转 / 右栏项目树都按长度
    # 匹配，以前这里不写，这三处全都对不上（界面上表现为 0 根支架标上串数、树里全是 ?）。
    # 长度就用框长（页面像素），不再读图纸比例尺换算英尺（用户要求）
    for pg, r in per_page.items():
        for d in r["detections"]:
            if d["label"] != "Tracker":
                continue
            b = d["bbox"]
            L = max(b["x2"] - b["x1"], b["y2"] - b["y1"])
            raw = dict(d.get("raw") or {})
            raw["len_px"] = round(L, 2)
            d["raw"] = raw
    if rack_strings and groups:
        for pg, r in per_page.items():
            for d in r["detections"]:
                if d["label"] != "Tracker":
                    continue
                if (d.get("raw") or {}).get("strings_source") == "table":
                    continue
                b = d["bbox"]
                L = max(b["x2"] - b["x1"], b["y2"] - b["y1"])
                best, bd = None, None
                for g in groups:
                    dlt = abs(L - g["length"])
                    if bd is None or dlt < bd:
                        best, bd = g, dlt
                if best is None or bd is None or bd > 0.10 * best["length"]:
                    continue
                key = round(best["length"], 3)
                if key in rack_strings:
                    d["raw"] = dict(d.get("raw") or {})
                    d["raw"]["strings"] = rack_strings[key]

    doc = debug_json(pdf_path, per_page)
    # 不再读图纸比例尺：长度直接是框长（像素）。这两个键保留成空值，老下游读到也不会出错
    doc["page_scales"] = {}
    doc["scale_dominant"] = None
    # 名字记录（下游按 node_bbox 对名字、按 label_pos/label_bbox 避让）
    ocr = []
    for pg, r in sorted(per_page.items()):
        recs, i = [], 0
        for d in r["detections"]:
            if d["label"] != "Node":
                continue
            i += 1
            b = d["bbox"]
            raw = d.get("raw") or {}
            rec = {"node_index": i, "entity_id": "p%d:node:%d" % (pg, i),
                   "readings": [],
                   "selected": {"text": d.get("name") or "", "angle_deg": 0,
                                "confidence": None},
                   "matched_table_name": None,
                   "preliminary_node_name": d.get("name") or "",
                   "error": None,
                   # 和 debug_json 里检测框一样取 2 位小数：两边坐标必须完全一致，
                   # 不然差 0.1 像素下游就按 bbox 找不到名字（LBD 标签会整行丢掉）
                   "node_bbox": {k: round(float(b[k]), 2) for k in ("x1", "y1", "x2", "y2")},
                   "final_node_name": d.get("name") or ""}
            rec["recognized_text"] = (raw.get("recognized_text")
                                      or raw.get("label_text") or d.get("name") or "")
            if raw.get("label_pos"):
                rec["label_pos"] = list(raw["label_pos"])
                rec["label_src"] = raw.get("label_src") or "text_layer"
            if raw.get("label_bbox"):
                rec["label_bbox"] = list(raw["label_bbox"])
            recs.append(rec)
        ocr.append({"page_number": pg, "data": recs})
    doc["ocr_node_name_results"] = ocr
    if table_by_page:
        doc["table_recognition_results"] = [
            {"page_number": pg, "data": {"result": table_by_page[pg]}}
            for pg in sorted(table_by_page)
        ]
        doc["page_regions"] = {
            str(pg): {
                "table_bbox": table_by_page[pg].get("bbox"),
                "table_bbox_normalized": table_by_page[pg].get("bbox_normalized"),
            }
            for pg in sorted(table_by_page)
        }
    table_tagged = sum(
        1
        for _pg, _r in per_page.items()
        for _d in _r.get("detections") or []
        if ((_d.get("raw") or {}).get("strings_source") == "table")
    )
    summary = {"stat": stat, "groups": groups, "note": gnote,
               "drawing_pages": drawing, "table_pages": len(table_by_page),
               "filtered_frames": filtered_total,
               "rack_row_filtered": rack_row_filtered,
               "table_tagged": table_tagged}
    return doc, summary


def parse_pages(spec, total=0):
    """页码写法 "3-8,12" -> [3,4,5,6,7,8,12]；空 = 全部。"""
    if not spec:
        return None
    out = []
    for part in str(spec).replace("，", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, _b, b = part.partition("-")
            try:
                a, b = int(a), int(b)
            except ValueError:
                continue
            out.extend(range(a, b + 1))
        else:
            try:
                out.append(int(part))
            except ValueError:
                pass
    seen, uniq = set(), []
    for p in out:
        if p not in seen and (not total or 1 <= p <= total):
            seen.add(p)
            uniq.append(p)
    return uniq


def main(argv=None):
    ap = argparse.ArgumentParser(description="主程序自带识别（v4c.onnx）自测")
    ap.add_argument("--png", default="", help="单张图（已渲染好的页面 PNG）")
    ap.add_argument("--pdf", default="", help="PDF 文件")
    ap.add_argument("--pages", default="", help='页码，如 "1-3,8"（默认全部）')
    ap.add_argument("--conf", type=float, default=CONF_THRES)
    ap.add_argument("--iou", type=float, default=IOU_THRES)
    ap.add_argument("--out", default="", help="把识别结果写成 agent3-debug JSON")
    ap.add_argument("--dpi", type=int, default=RENDER_DPI)
    a = ap.parse_args(argv)

    t0 = time.time()
    sess = load_session()
    print("模型：%s（%.1fs 建会话）" % (model_path(), time.time() - t0))
    print("类别：%s" % ", ".join(class_names()))
    if a.png:
        from PIL import Image
        im = Image.open(a.png)
        t1 = time.time()
        dets = detect_pil(sess, im, conf=a.conf, iou=a.iou)
        n_node = sum(1 for d in dets if d["label"] == "Node")
        n_trk = sum(1 for d in dets if d["label"] == "Tracker")
        print("%s  %dx%d  用时 %.1fs -> Node %d / Tracker %d"
              % (os.path.basename(a.png), im.width, im.height, time.time() - t1, n_node, n_trk))
    if a.pdf:
        total = pdf_page_count(a.pdf)
        pages = parse_pages(a.pages, total)
        print("PDF %s：%d 页，识别 %s 页" % (os.path.basename(a.pdf), total,
                                        "全部" if not pages else len(pages)))

        def prog(done, alln, pg):
            print("  [%d/%d] 第 %s 页" % (done, alln, pg))

        t1 = time.time()
        res = detect_pdf(a.pdf, pages=pages, dpi=a.dpi, session=sess,
                         conf=a.conf, iou=a.iou, progress=prog)
        n_node = sum(1 for r in res.values() for d in r["detections"] if d["label"] == "Node")
        n_trk = sum(1 for r in res.values() for d in r["detections"] if d["label"] == "Tracker")
        print("识别完：%d 页，Node %d / Tracker %d，用时 %.1fs"
              % (len(res), n_node, n_trk, time.time() - t1))
        if a.out:
            with open(a.out, "w", encoding="utf-8") as f:
                json.dump(debug_json(a.pdf, res), f, ensure_ascii=False)
            print("-> %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
