import os, json, glob, random, shutil
from PIL import Image

SRC = [r"C:\Users\szk\Desktop\batch_004\batch_004",
       r"C:\Users\szk\Desktop\batch_005\batch_005",
       r"C:\Users\szk\Desktop\batch_006\batch_006",
       r"C:\Users\szk\Desktop\batch_007\batch_007",
       r"C:\Users\szk\Desktop\batch_003\batch_003",
       r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\feedback"]
OUT = r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\tiles"
NAMES = ["Node", "Typical"]
TILE = 2000      # 原图切块尺寸
SAVE = 1280      # 保存尺寸(缩小, 省空间)
VAL_RATIO = 0.15
random.seed(42)


def collect():
    pairs = []
    for d in SRC:
        for jp in sorted(glob.glob(os.path.join(d, "*.json"))):
            stem = os.path.splitext(os.path.basename(jp))[0]
            png = os.path.join(d, stem + ".png")
            if os.path.isfile(png):
                pairs.append((png, jp))
    return pairs


def tile_image(png, jp, out_img_dir, out_lbl_dir, tag):
    o = json.load(open(jp, encoding="utf-8"))
    im = Image.open(png).convert("RGB")
    W, H = im.size
    shapes = []
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
        shapes.append((NAMES.index(lab), min(xs), min(ys), max(xs), max(ys)))
    base = os.path.splitext(os.path.basename(png))[0]
    n = 0
    for ty in range(0, H, TILE):
        for tx in range(0, W, TILE):
            tw = min(TILE, W - tx)
            th = min(TILE, H - ty)
            if tw < TILE // 2 or th < TILE // 2:
                continue
            lines = []
            for (ci, x1, y1, x2, y2) in shapes:
                cx = (x1 + x2) / 2.0
                cy = (y1 + y2) / 2.0
                if cx < tx or cx >= tx + tw or cy < ty or cy >= ty + th:
                    continue
                bx1 = max(0.0, (x1 - tx) / tw)
                by1 = max(0.0, (y1 - ty) / th)
                bx2 = min(1.0, (x2 - tx) / tw)
                by2 = min(1.0, (y2 - ty) / th)
                if bx2 <= bx1 or by2 <= by1:
                    continue
                lines.append("%d %.6f %.6f %.6f %.6f" % (
                    ci, (bx1 + bx2) / 2, (by1 + by2) / 2, bx2 - bx1, by2 - by1))
            if not lines:
                continue
            crop = im.crop((tx, ty, tx + tw, ty + th)).resize((SAVE, SAVE))
            name = "%s_%d_%d" % (base, tx, ty)
            crop.save(os.path.join(out_img_dir, name + ".jpg"), quality=85)
            with open(os.path.join(out_lbl_dir, name + ".txt"), "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            n += 1
    return n


def main():
    os.makedirs(OUT, exist_ok=True)
    for sub in ("images", "labels"):
        p = os.path.join(OUT, "dataset", sub)
        if os.path.isdir(p):
            shutil.rmtree(p)
    for split in ("train", "val"):
        os.makedirs(os.path.join(OUT, "dataset", "images", split), exist_ok=True)
        os.makedirs(os.path.join(OUT, "dataset", "labels", split), exist_ok=True)
    pairs = collect()
    random.shuffle(pairs)
    nval = max(1, int(round(len(pairs) * VAL_RATIO)))
    val, train = pairs[:nval], pairs[nval:]
    for split, items in (("train", train), ("val", val)):
        idir = os.path.join(OUT, "dataset", "images", split)
        ldir = os.path.join(OUT, "dataset", "labels", split)
        tot = 0
        for i, (png, jp) in enumerate(items):
            tot += tile_image(png, jp, idir, ldir, split)
            if (i + 1) % 20 == 0:
                print("%s %d/%d imgs, tiles=%d" % (split, i + 1, len(items), tot), flush=True)
        print("%s done: imgs=%d tiles=%d" % (split, len(items), tot), flush=True)
    with open(os.path.join(OUT, "data.yaml"), "w", encoding="utf-8") as f:
        f.write("path: %s\n" % (os.path.join(OUT, "dataset").replace("\\", "/")))
        f.write("train: images/train\nval: images/val\n")
        f.write("nc: %d\nnames: %s\n" % (len(NAMES), repr(NAMES).replace("'", '"')))
    print("data.yaml ->", os.path.join(OUT, "data.yaml"))


if __name__ == "__main__":
    main()
