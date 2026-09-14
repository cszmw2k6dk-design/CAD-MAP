import os, json, glob, random, shutil
from PIL import Image

SRC = [r"C:\Users\szk\Desktop\batch_005\batch_005",
       r"C:\Users\szk\Desktop\batch_006\batch_006",
       r"C:\Users\szk\Desktop\batch_007\batch_007"]
OUT = r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\batch007"
NAMES = ["Node", "Typical"]
NEW_W = 1920
random.seed(42)


def main():
    os.makedirs(OUT, exist_ok=True)
    # 清空旧数据集，避免残留
    for sub in ("images", "labels"):
        p = os.path.join(OUT, "dataset", sub)
        if os.path.isdir(p):
            shutil.rmtree(p)
    jsons = []
    for d in SRC:
        jsons += sorted(glob.glob(os.path.join(d, "*.json")))
    recs = []
    for jp in jsons:
        stem = os.path.splitext(os.path.basename(jp))[0]
        png = os.path.join(os.path.dirname(jp), stem + ".png")
        if not os.path.isfile(png):
            continue
        o = json.load(open(jp, encoding="utf-8"))
        W = o.get("imageWidth")
        H = o.get("imageHeight")
        with Image.open(png) as im:
            iw, ih = im.size
        W = W or iw
        H = H or ih
        boxes = []
        for s in o.get("shapes", []):
            if s.get("shape_type") != "rectangle":
                continue
            lab = (s.get("label") or "").strip()
            if lab not in NAMES:
                continue
            pts = s.get("points") or []
            if len(pts) < 2:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            x1, x2 = min(xs), max(xs)
            y1, y2 = min(ys), max(ys)
            if x2 <= x1 or y2 <= y1:
                continue
            cx = (x1 + x2) / 2.0 / W
            cy = (y1 + y2) / 2.0 / H
            w = (x2 - x1) / W
            h = (y2 - y1) / H
            boxes.append((NAMES.index(lab), cx, cy, w, h))
        if boxes:
            recs.append((png, stem, boxes))
    print("records", len(recs))
    random.shuffle(recs)
    nval = max(1, int(round(len(recs) * 0.15)))
    val = recs[:nval]
    train = recs[nval:]

    def write_split(items, split):
        idir = os.path.join(OUT, "dataset", "images", split)
        ldir = os.path.join(OUT, "dataset", "labels", split)
        os.makedirs(idir, exist_ok=True)
        os.makedirs(ldir, exist_ok=True)
        for png, stem, boxes in items:
            im = Image.open(png).convert("RGB")
            nw = NEW_W
            nh = int(round(im.height * NEW_W / im.width))
            im = im.resize((nw, nh))
            im.save(os.path.join(idir, stem + ".png"))
            with open(os.path.join(ldir, stem + ".txt"), "w", encoding="utf-8") as f:
                for (ci, cx, cy, w, h) in boxes:
                    f.write("%d %.6f %.6f %.6f %.6f\n" % (ci, cx, cy, w, h))

    write_split(train, "train")
    write_split(val, "val")
    with open(os.path.join(OUT, "data.yaml"), "w", encoding="utf-8") as f:
        f.write("path: %s\n" % (os.path.join(OUT, "dataset").replace("\\", "/")))
        f.write("train: images/train\nval: images/val\n")
        f.write("nc: %d\nnames: %s\n" % (len(NAMES), repr(NAMES).replace("'", '"')))
    print("train", len(train), "val", len(val))
    print("data.yaml ->", os.path.join(OUT, "data.yaml"))


if __name__ == "__main__":
    main()
