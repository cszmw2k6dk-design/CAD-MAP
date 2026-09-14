import os, sys, argparse

os.environ.setdefault("YOLO_CONFIG_DIR", r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\yolo_config")
from PIL import Image, ImageDraw
from ultralytics import YOLO

TILE = 2000
STRIDE = 1600


def iou(a, b):
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    aa = (a[2] - a[0]) * (a[3] - a[1])
    ab = (b[2] - b[0]) * (b[3] - b[1])
    return inter / min(aa, ab) if min(aa, ab) > 0 else 0.0


def nms(boxes, t=0.5):
    keep = []
    for b in sorted(boxes, key=lambda x: -x[4]):
        if all(iou(b, k) <= t or b[5] != k[5] for k in keep):
            keep.append(b)
    return keep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--img", required=True)
    ap.add_argument("--model", default=r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\runs\tiles\weights\best.pt")
    ap.add_argument("--rot", type=int, default=0)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    model = YOLO(args.model)
    img = Image.open(args.img).convert("RGB")
    if args.rot:
        img = img.rotate(args.rot, expand=True)
    W, H = img.size
    boxes = []
    for y in range(0, H, STRIDE):
        for x in range(0, W, STRIDE):
            x2 = min(x + TILE, W)
            y2 = min(y + TILE, H)
            if x2 - x < 400 or y2 - y < 400:
                continue
            crop = img.crop((x, y, x2, y2))
            tmp = os.path.join(os.environ.get("TEMP", "."), "_tile_tmp.jpg")
            crop.save(tmp, quality=90)
            res = model.predict(tmp, conf=args.conf, imgsz=768, verbose=False)[0]
            for b in res.boxes:
                gx1, gy1, gx2, gy2 = [float(v) for v in b.xyxy[0]]
                boxes.append([gx1 + x, gy1 + y, gx2 + x, gy2 + y,
                              float(b.conf[0]), int(b.cls)])
    boxes = nms(boxes, 0.5)
    dr = ImageDraw.Draw(img)
    cnt = {0: 0, 1: 0}
    for b in boxes:
        cnt[b[5]] = cnt.get(b[5], 0) + 1
        col = (255, 0, 0) if b[5] == 0 else (0, 120, 255)
        dr.rectangle(b[:4], outline=col, width=4)
    img.save(args.out)
    print("rot", args.rot, "Node", cnt.get(0, 0), "Typical", cnt.get(1, 0), "->", args.out)


if __name__ == "__main__":
    main()
