import os, sys, io, json, base64, tempfile, subprocess, argparse, re

os.environ.setdefault("YOLO_CONFIG_DIR", r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\yolo_config")
from PIL import Image
from pypdf import PdfReader
from ultralytics import YOLO

PDFTOPPM = r"C:\Users\szk\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin\pdftoppm.exe"
TILE, STRIDE, IMGSZ = 2000, 1600, 768
NAMES = ["Node", "Typical"]


def iou(a, b):
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    aa = (a[2] - a[0]) * (a[3] - a[1])
    ab = (b[2] - b[0]) * (b[3] - b[1])
    return inter / min(aa, ab) if min(aa, ab) > 0 else 0.0


def nms(boxes, t=0.4):
    keep = []
    for b in sorted(boxes, key=lambda x: -x["conf"]):
        if all(iou(b["bbox"], k["bbox"]) <= t or b["cls"] != k["cls"] for k in keep):
            keep.append(b)
    return keep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--page", type=int, default=1)
    ap.add_argument("--rot", type=int, default=0)
    ap.add_argument("--dpi", type=int, default=250)
    ap.add_argument("--conf", type=float, default=0.4)
    ap.add_argument("--model", default=r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\runs\tiles\weights\best.pt")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    tmpdir = tempfile.mkdtemp(prefix="exp_")
    subprocess.run([PDFTOPPM, "-png", "-r", str(a.dpi), "-f", str(a.page), "-l", str(a.page),
                    a.pdf, os.path.join(tmpdir, "p")],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    f = [x for x in os.listdir(tmpdir) if x.lower().endswith(".png")][0]
    img = Image.open(os.path.join(tmpdir, f)).convert("RGB")
    if a.rot:
        img = img.rotate(a.rot, expand=True)
    model = YOLO(a.model)
    W, H = img.size
    raw = []
    t = os.path.join(tmpdir, "_t.jpg")
    for y in range(0, H, STRIDE):
        for x in range(0, W, STRIDE):
            x2, y2 = min(x + TILE, W), min(y + TILE, H)
            if x2 - x < 400 or y2 - y < 400:
                continue
            img.crop((x, y, x2, y2)).save(t, quality=90)
            res = model.predict(t, conf=a.conf, imgsz=IMGSZ, verbose=False)[0]
            for b in res.boxes:
                bx1, by1, bx2, by2 = [float(v) for v in b.xyxy[0]]
                raw.append({"bbox": [bx1 + x, by1 + y, bx2 + x, by2 + y],
                            "cls": int(b.cls), "conf": float(b.conf[0])})
    boxes = nms(raw, 0.4)
    base = os.path.splitext(os.path.basename(a.pdf))[0]
    base = re.sub(r"[^A-Za-z0-9_\-]+", "_", base)[:40]
    stem = base + "_p%03d" % a.page
    img.save(os.path.join(a.out, stem + ".png"))
    shapes = []
    for b in boxes:
        x1, y1, x2, y2 = b["bbox"]
        shapes.append({"label": NAMES[b["cls"]], "score": None,
                       "points": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
                       "group_id": None, "description": "", "difficult": False,
                       "shape_type": "rectangle", "flags": {}, "attributes": {},
                       "kie_linking": []})
    with open(os.path.join(a.out, stem + ".json"), "w", encoding="utf-8") as fh:
        json.dump({"version": "4.0.0-beta.11", "flags": {}, "checked": False,
                   "shapes": shapes, "imagePath": stem + ".png", "imageData": None,
                   "imageHeight": H, "imageWidth": W}, fh, ensure_ascii=False, indent=2)
    nn = sum(1 for b in boxes if b["cls"] == 0)
    nt = sum(1 for b in boxes if b["cls"] == 1)
    print("page", a.page, "size", (W, H), "Node", nn, "Typical", nt)
    print("out:", os.path.join(a.out, stem + ".png"), "&", os.path.join(a.out, stem + ".json"))


if __name__ == "__main__":
    main()
