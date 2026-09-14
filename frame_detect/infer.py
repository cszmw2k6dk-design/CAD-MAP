import os, sys, argparse, json
from PIL import Image, ImageDraw

os.environ.setdefault("YOLO_CONFIG_DIR", r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\yolo_config")
from ultralytics import YOLO


def sort_boxes(results, image_size):
    """把检测框按 行优先(上->下, 同排左->右) 排序，并返回带序号列表."""
    W, H = image_size
    boxes = []
    for b in results.boxes:
        if int(b.cls) != 0:
            continue
        x1, y1, x2, y2 = [float(v) for v in b.xyxy[0]]
        conf = float(b.conf[0])
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        boxes.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2, "cx": cx, "cy": cy,
                      "w": x2 - x1, "h": y2 - y1, "conf": conf,
                      "xc_norm": cx / W, "yc_norm": cy / H})
    # 行优先：先用 y 中心分排（允许同排有少量抖动），排内按 x 排序
    boxes.sort(key=lambda b: b["cy"])
    rows = []
    for b in boxes:
        placed = False
        for row in rows:
            row_y = sum(x["cy"] for x in row) / len(row)
            if abs(b["cy"] - row_y) < max(20, b["h"] * 0.3):
                row.append(b)
                placed = True
                break
        if not placed:
            rows.append([b])
    for row in rows:
        row.sort(key=lambda b: b["cx"])
    rows.sort(key=lambda row: sum(x["cy"] for x in row) / len(row))
    ordered = []
    idx = 1
    for row in rows:
        for b in row:
            b["index"] = idx
            ordered.append(b)
            idx += 1
    return ordered


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\runs\frames\weights\best.pt")
    ap.add_argument("--source", required=True, help="图片文件或目录")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--out", default=r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\output")
    ap.add_argument("--draw", action="store_true", help="同时画出带序号的框")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    model = YOLO(args.model)
    src = args.source
    files = []
    if os.path.isdir(src):
        for f in os.listdir(src):
            if f.lower().endswith((".png", ".jpg", ".jpeg")):
                files.append(os.path.join(src, f))
    else:
        files = [src]

    for f in files:
        img = Image.open(f).convert("RGB")
        res = model.predict(f, conf=args.conf, imgsz=640, verbose=False)[0]
        ordered = sort_boxes(res, img.size)
        stem = os.path.splitext(os.path.basename(f))[0]
        rec = {"image": os.path.basename(f), "width": img.size[0], "height": img.size[1],
               "count": len(ordered), "nodes": ordered}
        with open(os.path.join(args.out, stem + ".json"), "w", encoding="utf-8") as fh:
            json.dump(rec, fh, ensure_ascii=False, indent=2)
        print(f"{stem}: {len(ordered)} nodes")
        if args.draw:
            dr = ImageDraw.Draw(img)
            for b in ordered:
                dr.rectangle([b["x1"], b["y1"], b["x2"], b["y2"]], outline=(255, 0, 0), width=3)
                dr.text((b["x1"] + 4, b["y1"] + 2), str(b["index"]), fill=(0, 0, 255))
            img.save(os.path.join(args.out, stem + "_draw.png"))


if __name__ == "__main__":
    main()
