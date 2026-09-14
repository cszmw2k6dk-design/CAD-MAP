import os, json, random, shutil
from PIL import Image, ImageDraw, ImageFont

SRC_DIRS = [
    r"C:\Users\szk\Desktop\A-F\A-F\A-F",
    r"C:\Users\szk\Desktop\G-Mhalf\G-Mhalf\G-Mhalf",
]
OUT = r"C:\Users\szk\Desktop\MAP-CAD\frame_detect"
LABEL = "Node"
random.seed(42)


def find_images():
    pairs = []
    for d in SRC_DIRS:
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.lower().endswith(".json"):
                continue
            jp = os.path.join(d, f)
            stem = os.path.splitext(f)[0]
            png = os.path.join(d, stem + ".png")
            if os.path.isfile(png):
                pairs.append((png, jp))
    return pairs


def build_records(pairs):
    records = []
    skipped = 0
    for png, jp in pairs:
        with open(jp, "r", encoding="utf-8") as fh:
            j = json.load(fh)
        W = j.get("imageWidth")
        H = j.get("imageHeight")
        try:
            with Image.open(png) as im:
                iw, ih = im.size
            W = W or iw
            H = H or ih
        except Exception:
            pass
        if not W or not H:
            skipped += 1
            continue
        boxes = []
        for sh in j.get("shapes", []):
            if sh.get("shape_type") != "rectangle":
                continue
            if (sh.get("label") or "").strip() != LABEL:
                continue
            pts = sh.get("points") or []
            if len(pts) < 2:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            x1, x2 = min(xs), max(xs)
            y1, y2 = min(ys), max(ys)
            if x2 <= x1 or y2 <= y1:
                continue
            xc = (x1 + x2) / 2.0 / W
            yc = (y1 + y2) / 2.0 / H
            w = (x2 - x1) / W
            h = (y2 - y1) / H
            boxes.append((xc, yc, w, h))
        if boxes:
            records.append((png, os.path.splitext(os.path.basename(png))[0], W, H, boxes))
    print("skipped (no W/H or empty):", skipped)
    return records


def write_split(items, split):
    imgdir = os.path.join(OUT, "dataset", "images", split)
    lbldir = os.path.join(OUT, "dataset", "labels", split)
    os.makedirs(imgdir, exist_ok=True)
    os.makedirs(lbldir, exist_ok=True)
    for png, stem, W, H, boxes in items:
        shutil.copy2(png, os.path.join(imgdir, stem + ".png"))
        with open(os.path.join(lbldir, stem + ".txt"), "w", encoding="utf-8") as f:
            for (xc, yc, w, h) in boxes:
                f.write("0 {:.6f} {:.6f} {:.6f} {:.6f}\n".format(xc, yc, w, h))


def draw_verification(items, outdir, count=4):
    os.makedirs(outdir, exist_ok=True)
    sel = random.sample(items, min(count, len(items)))
    for i, (png, stem, W, H, boxes) in enumerate(sel):
        im = Image.open(png).convert("RGB")
        dr = ImageDraw.Draw(im)
        # scale to a fixed width for review
        scale = 1080 / im.width
        im = im.resize((1080, int(im.height * scale)))
        W2, H2 = im.size
        dr = ImageDraw.Draw(im)
        for (xc, yc, w, h) in boxes:
            x1 = (xc - w / 2.0) * W2
            y1 = (yc - h / 2.0) * H2
            x2 = (xc + w / 2.0) * W2
            y2 = (yc + h / 2.0) * H2
            dr.rectangle([x1, y1, x2, y2], outline=(255, 0, 0), width=3)
        out = os.path.join(outdir, "verify_{}_{}.png".format(i, stem[:20]))
        im.save(out)
        print("verify ->", out)


def main():
    pairs = find_images()
    print("json+png pairs:", len(pairs))
    records = build_records(pairs)
    print("annotated records:", len(records))
    random.shuffle(records)
    n = len(records)
    nval = max(1, int(round(n * 0.15)))
    val = records[:nval]
    train = records[nval:]
    print("train:", len(train), "val:", len(val))
    write_split(train, "train")
    write_split(val, "val")
    data_yaml = (
        "path: {}\n".format(OUT.replace("\\", "/") + "/dataset")
        + "train: images/train\nval: images/val\nnc: 1\nnames: ['{}']\n".format(LABEL)
    )
    with open(os.path.join(OUT, "data.yaml"), "w", encoding="utf-8") as f:
        f.write(data_yaml)
    print("data.yaml written")
    draw_verification(val, os.path.join(OUT, "verify"))
    # stats
    import collections
    cnt = collections.Counter(len(r[4]) for r in records)
    print("boxes-per-image histogram:", dict(sorted(cnt.items())))


if __name__ == "__main__":
    main()
