import os, sys, argparse, json

os.environ.setdefault("YOLO_CONFIG_DIR", r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\yolo_config")
from PIL import Image
from pypdf import PdfReader
from ultralytics import YOLO


def extract_lbd(page, cb):
    """返回 [(fx, fy, text)]，归一化页面坐标."""
    x0, y0 = float(cb.left), float(cb.bottom)
    pw = float(cb.right) - x0
    ph = float(cb.top) - y0
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
                m0, m1, m2, m3, m4, m5 = 1, 0, 0, 1, 0, 0
            try:
                cs = float(size)
            except Exception:
                cs = 0.0
            w = cs * 0.5 * len(text)
            h = cs
            xs = []
            ys = []
            for tx, ty in ((0, 0), (w, 0), (0, h), (w, h)):
                xs.append(m0 * tx + m2 * ty + m4)
                ys.append(m1 * tx + m3 * ty + m5)
            cx = (min(xs) + max(xs)) * 0.5
            cy = min(ys) - (max(ys) - min(ys)) * 0.15
            items.append([text, cx, cy])

    try:
        page.extract_text(visitor_text=visit)
    except Exception:
        items = []
    out = []
    for it in items:
        if "LBD" not in it[0].upper():
            continue
        cx, cy = it[1], it[2]
        if cx < x0 or cy < y0 or cx > x0 + pw or cy > y0 + ph:
            continue
        out.append(((cx - x0) / pw, (cy - y0) / ph, it[0]))
    return out


def match_labels(frames, labels):
    """为每个框(归一化 bbox)匹配最近的 LBD 标签."""
    # 过滤图例类标签
    def is_legend(t):
        u = t.upper()
        return ("XXXYY" in u) or ("TYP" in u) or ("OUTLINE" in u) or ("SEQUENCING" in u)

    labels = [l for l in labels if not is_legend(l[2])]
    out = []
    for fr in frames:
        fx1, fy1, fx2, fy2 = fr["bbox"]
        fcx = (fx1 + fx2) / 2.0
        fcy = (fy1 + fy2) / 2.0
        best = None
        best_d = 1e9
        for (lx, ly, lt) in labels:
            # 框内: 标签中心落在框bbox内
            inside = (fx1 <= lx <= fx2) and (fy1 <= ly <= fy2)
            d = ((lx - fcx) ** 2 + (ly - fcy) ** 2) ** 0.5
            if inside:
                d *= 0.2  # 优先命中框内
            if d < best_d:
                best_d = d
                best = (lx, ly, lt, inside)
        out.append({"frame": fr, "match": best})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--pages-dir", required=True, help="渲好的页图目录 (pg-000.png)")
    ap.add_argument("--model", default=r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\runs\frames\weights\best.pt")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=0)
    ap.add_argument("--out", default=r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\pdflbd_extract.txt")
    ap.add_argument("--json", default=None, help="额外写一份 JSON 便于核对")
    args = ap.parse_args()

    model = YOLO(args.model)
    reader = PdfReader(args.pdf)
    total = len(reader.pages)
    p0 = max(1, args.start)
    p1 = args.end if args.end > 0 else total
    lines = []
    allrec = []
    for pi in range(p0, p1 + 1):
        page = reader.pages[pi - 1]
        try:
            cb = page.cropbox
            pw = float(cb.right) - float(cb.left)
            ph = float(cb.top) - float(cb.bottom)
        except Exception:
            cb = None
            pw = ph = 1.0
        imgp = os.path.join(args.pages_dir, "pg-%03d.png" % pi)
        if not os.path.exists(imgp):
            continue
        img = Image.open(imgp).convert("RGB")
        W, H = img.size
        res = model.predict(imgp, conf=args.conf, imgsz=640, verbose=False)[0]
        frames = []
        for b in res.boxes:
            if int(b.cls) != 0:
                continue
            x1, y1, x2, y2 = [float(v) for v in b.xyxy[0]]
            frames.append({"bbox": (x1 / W, y1 / H, x2 / W, y2 / H), "conf": float(b.conf[0])})
        labels = extract_lbd(page, cb) if cb else []
        matched = match_labels(frames, labels)
        title = ""
        try:
            title = "".join(page.extract_text() or "")[:120].replace("\t", " ").replace("\n", " ")
        except Exception:
            title = ""
        lines.append("P\t%d\t%.2f\t%.2f\t%s" % (pi, pw, ph, title))
        rec = {"page": pi, "w": W, "h": H, "nodes": []}
        for m in matched:
            fr = m["frame"]
            mt = m["match"]
            fcx = (fr["bbox"][0] + fr["bbox"][2]) / 2.0
            fcy = (fr["bbox"][1] + fr["bbox"][3]) / 2.0
            text = mt[2] if mt else ""
            lines.append("L\t%d\t%.6f\t%.6f\t%s" % (pi, fcx, fcy, text.replace("\t", " ")))
            rec["nodes"].append({"bbox": [round(v, 5) for v in fr["bbox"]],
                                 "conf": round(fr["conf"], 3),
                                 "lbd": text})
        allrec.append(rec)
        print("page %d: %d frames, %d LBD labels, matched %d" % (pi, len(frames), len(labels), len(matched)))

    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("wrote", args.out)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(allrec, f, ensure_ascii=False, indent=2)
        print("wrote", args.json)


if __name__ == "__main__":
    main()
