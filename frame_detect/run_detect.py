import os, sys, subprocess, tempfile, argparse, json

os.environ.setdefault("YOLO_CONFIG_DIR", r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\yolo_config")
from PIL import Image
from pypdf import PdfReader
from ultralytics import YOLO

# 找 pdftoppm（poppler）
PDFTOPPM = None
for c in (
    r"C:\Users\szk\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin\pdftoppm.exe",
    r"C:\Program Files\poppler\Library\bin\pdftoppm.exe",
    "pdftoppm",
):
    try:
        subprocess.run([c, "-v"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=20)
        PDFTOPPM = c
        break
    except Exception:
        continue


def render(pdf, pages_dir, dpi=32, start=1, end=0):
    os.makedirs(pages_dir, exist_ok=True)
    if PDFTOPPM:
        cmd = [PDFTOPPM, "-png", "-r", str(dpi), "-f", str(start), "-l", str(end), pdf,
               os.path.join(pages_dir, "pg")]
        subprocess.run(cmd, check=True, timeout=600)
        return lambda p: os.path.join(pages_dir, "pg-%03d.png" % p)
    # 兜底：pymupdf
    import fitz  # noqa
    doc = fitz.open(pdf)
    for p in range(start, end + 1):
        pix = doc[p - 1].get_pixmap(dpi=96)
        pix.save(os.path.join(pages_dir, "pg-%03d.png" % p))
    return lambda p: os.path.join(pages_dir, "pg-%03d.png" % p)


def bands(vals, tol):
    vals = sorted(vals)
    if not vals:
        return []
    b = []
    cur = [vals[0]]
    for v in vals[1:]:
        if v - cur[-1] <= tol:
            cur.append(v)
        else:
            b.append(sum(cur) / len(cur))
            cur = [v]
    b.append(sum(cur) / len(cur))
    return b


def iou(a, b):
    xa1, ya1, xa2, ya2 = a
    xb1, yb1, xb2, yb2 = b
    ix1, iy1 = max(xa1, xb1), max(ya1, yb1)
    ix2, iy2 = min(xa2, xb2), min(ya2, yb2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    aa = (xa2 - xa1) * (ya2 - ya1)
    ab = (xb2 - xb1) * (yb2 - yb1)
    return inter / min(aa, ab) if min(aa, ab) > 0 else 0.0


def merge(boxes, iou_t=0.85):
    # 轻量去重：只去掉与已保留的更大框高度重叠的重复框，保留每个独立竖条
    keep = []
    for b in sorted(boxes, key=lambda x: -(x[2] - x[0]) * (x[3] - x[1])):
        if all(iou(b, k) <= iou_t for k in keep):
            keep.append(b)
    return keep


def process_page(model, img_path):
    img = Image.open(img_path).convert("RGB")
    W, H = img.size
    res = model.predict(img_path, conf=0.25, imgsz=640, verbose=False)[0]
    boxes = []
    for b in res.boxes:
        if int(b.cls) != 0:
            continue
        x1, y1, x2, y2 = [float(v) for v in b.xyxy[0]]
        boxes.append((min(x1, x2) / W, min(y1, y2) / H, max(x1, x2) / W, max(y1, y2) / H))
    merged = merge(boxes)
    xs = [(b[0] + b[2]) / 2 for b in merged]
    ys = [(b[1] + b[3]) / 2 for b in merged]
    colb = bands(xs, 0.028)
    rowb = bands(ys, 0.05)
    cols = len(colb)
    rows = len(rowb)
    # 给每个框赋 (row, col) 并按行优先排序编号
    cidx = lambda x: min(range(len(colb)), key=lambda i: abs(colb[i] - x))
    ridx = lambda y: min(range(len(rowb)), key=lambda i: abs(rowb[i] - y))
    cells = sorted([(ridx((b[1] + b[3]) / 2), cidx((b[0] + b[2]) / 2), b) for b in merged],
                   key=lambda c: (c[0], c[1]))
    numbered = [(i + 1, r, c, b) for i, (r, c, b) in enumerate(cells)]
    if merged:
        x1 = min(b[0] for b in merged)
        y1 = min(b[1] for b in merged)
        x2 = max(b[2] for b in merged)
        y2 = max(b[3] for b in merged)
        extent = [x1, y1, x2, y2]
    else:
        extent = None
    return numbered, rows, cols, extent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--model", default=r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\runs\frames\weights\best.pt")
    ap.add_argument("--outdir", default=r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\output_run")
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=0)
    ap.add_argument("--dpi", type=int, default=32)
    ap.add_argument("--draw", action="store_true")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    pages_dir = os.path.join(args.outdir, "pages")
    reader = PdfReader(args.pdf)
    total = len(reader.pages)
    end = args.end if args.end > 0 else total
    getpage = render(args.pdf, pages_dir, args.dpi, args.start, end)
    model = YOLO(args.model)
    lines = []
    grids = []
    for p in range(args.start, end + 1):
        imgp = getpage(p)
        if not os.path.exists(imgp):
            continue
        numbered, rows, cols, extent = process_page(model, imgp)
        # 页信息
        try:
            cb = reader.pages[p - 1].cropbox
            pw = float(cb.right) - float(cb.left)
            ph = float(cb.top) - float(cb.bottom)
        except Exception:
            pw = ph = 1.0
        lines.append("P\t%d\t%.2f\t%.2f\tpage %d" % (p, pw, ph, p))
        if extent is not None:
            lines.append("G\t%d\t%d\t%d\t%.6f\t%.6f\t%.6f\t%.6f"
                         % (p, rows, cols, extent[0], extent[1], extent[2], extent[3]))
        if args.draw:
            from PIL import ImageDraw
            img = Image.open(imgp).convert("RGB")
            dr = ImageDraw.Draw(img)
        for (idx, r, c, (x1, y1, x2, y2)) in numbered:
            fcx = (x1 + x2) / 2
            fcy = (y1 + y2) / 2
            lines.append("L\t%d\t%.6f\t%.6f\tNODE-%d" % (p, fcx, fcy, idx))
            if args.draw:
                dr.rectangle([x1 * img.width, y1 * img.height, x2 * img.width, y2 * img.height],
                             outline=(255, 0, 0), width=2)
                dr.text((x1 * img.width + 2, y1 * img.height + 2), str(idx), fill=(0, 0, 255))
        if args.draw:
            vis = os.path.join(args.outdir, "vis_pg%03d.png" % p)
            img.save(vis)
        grids.append({"page": p, "rows": rows, "cols": cols, "count": len(numbered),
                      "extent": [round(v, 5) for v in extent] if extent else None})
        print("page %d: frames=%d rows=%d cols=%d extent=%s" % (p, len(numbered), rows, cols, extent))
    with open(os.path.join(args.outdir, "pdflbd_extract.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    with open(os.path.join(args.outdir, "grid.json"), "w", encoding="utf-8") as f:
        json.dump(grids, f, ensure_ascii=False, indent=2)
    print("wrote", os.path.join(args.outdir, "pdflbd_extract.txt"), "and grid.json")


if __name__ == "__main__":
    main()
