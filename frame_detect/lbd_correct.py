"""用 PDF 抽出的 LBD 标签校正模型输出的 LBD(Node)区域。

思路:
  1. pdf_extract.py 已经抽到每页的 LBD 文字及其坐标(fx/fy, 自下往上, 未旋转坐标系);
  2. 按页面的 /Rotate 把文字坐标换算到渲染图的像素坐标;
  3. 每个唯一的 LBD 编号, 找一个包含它的模型 Node 框 -> 该框就是它的 LBD 区域;
  4. 没有任何标签命中的 Node 框 = 重复/碎片, 丢掉;
  5. 标签没落到任何框里 = 模型漏检, 单独列出来人工看。

结果: LBD 数量 == PDF 里的 LBD 标签数量。
"""
import os
import json
import argparse

os.environ.setdefault("YOLO_CONFIG_DIR", r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\yolo_config")

from PIL import Image, ImageDraw
from pypdf import PdfReader
from ultralytics import YOLO

TILE = 2000
STRIDE = 1200
CONF = 0.25


def to_px(fx, fy, W, H, rotation):
    """PDF 文字坐标(未旋转, fy 自下) -> 渲染图像素坐标。"""
    r = int(rotation or 0) % 360
    if r == 90:
        return fy * W, fx * H
    if r == 180:
        return (1.0 - fx) * W, fy * H
    if r == 270:
        return (1.0 - fy) * W, (1.0 - fx) * H
    return fx * W, (1.0 - fy) * H


def iou(a, b):
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    aa = (a[2] - a[0]) * (a[3] - a[1])
    ab = (b[2] - b[0]) * (b[3] - b[1])
    return inter / min(aa, ab) if min(aa, ab) > 0 else 0.0


def detect(model, img_path):
    """切块推理 + 轻量去重, 返回 (boxes, W, H)。box = [x1,y1,x2,y2,conf,cls]"""
    im = Image.open(img_path).convert("RGB")
    W, H = im.size
    tmp = os.path.join(os.environ.get("TEMP", "."), "_lbd_correct_tile.jpg")
    boxes = []
    for y in range(0, H, STRIDE):
        for x in range(0, W, STRIDE):
            x2, y2 = min(x + TILE, W), min(y + TILE, H)
            if x2 - x < 400 or y2 - y < 400:
                continue
            im.crop((x, y, x2, y2)).save(tmp, quality=90)
            res = model.predict(tmp, conf=CONF, imgsz=768, verbose=False)[0]
            for b in res.boxes:
                g = [float(v) for v in b.xyxy[0]]
                boxes.append([g[0] + x, g[1] + y, g[2] + x, g[3] + y, float(b.conf[0]), int(b.cls)])
    keep = []
    for b in sorted(boxes, key=lambda z: -z[4]):
        if all(iou(b, k) <= 0.5 or b[5] != k[5] for k in keep):
            keep.append(b)
    return keep, W, H


def read_labels(extract_path, page):
    """读 pdf_extract.py 输出, 只取本页含 LBD- 的条目 -> [(名称, fx, fy)]"""
    out = []
    if not extract_path or not os.path.exists(extract_path):
        return out
    with open(extract_path, encoding="utf-8") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) >= 5 and p[0] == "L" and p[1].strip() == str(page) and "LBD-" in p[4].upper():
                out.append((p[4].strip(), float(p[2]), float(p[3])))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--img", required=True, help="渲染后的整页 PNG")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--extract", required=True, help="pdf_extract.py 的输出")
    ap.add_argument("--model", default=r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\runs\tiles\weights\best.pt")
    ap.add_argument("--out-json", default="")
    ap.add_argument("--out-png", default="")
    ap.add_argument("--assign-cap", type=float, default=0.25,
                    help="支架归属的最大距离, 按页高的比例(默认 0.25 = 1590px@6360)")
    a = ap.parse_args()

    model = YOLO(a.model)
    boxes, W, H = detect(model, a.img)
    nodes = [b for b in boxes if b[5] == 0]
    typs = [b for b in boxes if b[5] == 1]

    rot = PdfReader(a.pdf).pages[a.page - 1].get("/Rotate") or 0
    labels = read_labels(a.extract, a.page)
    pts = [(n, *to_px(fx, fy, W, H, rot)) for (n, fx, fy) in labels]

    # 标签 -> 框 的匹配:
    #   模型的 Node 框常常比真实行"小一点/偏一点", 所以不能只判"点在框内",
    #   而是: x 方向有重叠 + y 方向距离最近, 再做一对一贪心; 命中后把框撑到包含标签。
    #   同一个编号出现多次(图上标注 + 表格/引出列表)时, 只会用最合适的那个位置。
    cand = []
    for li, (name, px, py) in enumerate(pts):
        for bi, b in enumerate(nodes):
            if px < b[0] - 0.15 * (b[2] - b[0]) or px > b[2] + 0.15 * (b[2] - b[0]):
                continue
            dy = max(b[1] - py, 0.0, py - b[3])
            dx = 0.0 if b[0] <= px <= b[2] else min(abs(px - b[0]), abs(px - b[2]))
            scale = max(b[3] - b[1], 1.0)
            cand.append((dy / scale + dx / scale, li, bi, name, px, py))
    cand.sort()
    box_of = {}
    used_label = set()
    used_name = set()
    for score, li, bi, name, px, py in cand:
        if li in used_label or bi in box_of or name in used_name:
            continue
        if score > 0.5:      # 离得太远就不认
            continue
        used_label.add(li)
        used_name.add(name)
        box_of[bi] = (name, px, py, score)

    regions = []
    for bi, (name, px, py, score) in sorted(box_of.items()):
        regions.append({"lbd": name, "seed": (px, py), "node_conf": nodes[bi][4],
                        "match_score": score, "model_box": list(nodes[bi][:4])})

    # 第二阶段: 支架按"离哪个标签最近"归属(距离上限按页高比例),
    #           区域范围 = 标签锚点 + 名下支架的包围盒(不再受模型框大小限制)
    cap = a.assign_cap * H
    for r in regions:
        r["items"] = []
    for t in typs:
        cx, cy = (t[0] + t[2]) / 2, (t[1] + t[3]) / 2
        best_r, best_d = None, None
        for r in regions:
            d = ((cx - r["seed"][0]) ** 2 + (cy - r["seed"][1]) ** 2) ** 0.5
            if best_d is None or d < best_d:
                best_d, best_r = d, r
        if best_r is not None and best_d <= cap:
            best_r["items"].append((cx, cy, t))

    out_regions = []
    for r in regions:
        ips = list(r["items"])
        if ips:
            x1 = min(min(p[0] for p in ips), r["seed"][0])
            x2 = max(max(p[0] for p in ips), r["seed"][0])
            y1 = min(min(p[1] for p in ips), r["seed"][1])
            y2 = max(max(p[1] for p in ips), r["seed"][1])
        else:
            x1, y1, x2, y2 = r["model_box"]
        box = [round(x1 - 40, 1), round(y1 - 60, 1), round(x2 + 40, 1), round(y2 + 60, 1)]
        out_regions.append({"lbd": [r["lbd"]], "box": box, "typicals": len(ips),
                            "conf": round(r["node_conf"], 3),
                            "match_score": round(r["match_score"], 3),
                            "model_box": [round(v, 1) for v in r["model_box"]],
                            "seed": [round(r["seed"][0], 1), round(r["seed"][1], 1)],
                            "_items": ips})
    assigned_ids = {id(p[2]) for r in regions for p in r["items"]}
    free_typs = [t for t in typs if id(t) not in assigned_ids]
    regions = out_regions
    regions.sort(key=lambda r: r["lbd"][0])
    dropped = [{"box": [round(v, 1) for v in b[:4]], "conf": round(b[4], 3),
                "size": int((b[2] - b[0]) * (b[3] - b[1]))}
               for i, b in enumerate(nodes) if i not in box_of]
    assigned = {v[0] for v in box_of.values()}
    miss = sorted({n for n, _, _ in pts} - assigned)

    # str 编号: 每个 LBD 名下(BFS 归属)的支架按 上->下 左->右 排
    for r in regions:
        inner = sorted(r["_items"], key=lambda p: (round(p[1] / (0.06 * H)), p[0]))
        r["strs"] = [{"name": "STR%02d" % (k + 1), "cx": round(p[0], 1), "cy": round(p[1], 1)}
                     for k, p in enumerate(inner)]
        del r["_items"]

    result = {"page": a.page, "imageW": W, "imageH": H, "rotate": rot,
              "model_nodes": len(nodes), "model_typicals": len(typs),
              "pdf_lbd_labels": len({n for n, _, _ in pts}),
              "regions": regions, "dropped_nodes": dropped, "labels_without_box": miss,
              "typicals_outside_regions": len(free_typs),
              "outside_boxes": [[round(v, 1) for v in t[:4]] for t in free_typs]}
    if a.out_json:
        json.dump(result, open(a.out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    if a.out_png:
        im = Image.open(a.img).convert("RGB")
        ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        for b in dropped:
            d.rectangle(b["box"], outline=(255, 0, 0, 200), width=6)
        free_ids = {id(t) for t in free_typs}
        for t in typs:
            d.rectangle(t[:4], outline=(255, 0, 0, 220) if id(t) in free_ids else (0, 160, 0, 200), width=8 if id(t) in free_ids else 5)
        for r in regions:
            d.rectangle(r["box"], outline=(255, 0, 255, 255), width=14)
            d.text((r["box"][0] + 10, r["box"][1] + 10), "+".join(x.split("-")[-1] for x in r["lbd"]),
                   fill=(255, 0, 255, 255))
        im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")
        im.save(a.out_png)

    print("模型 Node=%d(校正后 %d) Typical=%d | PDF LBD 标签=%d | 丢弃重复框=%d | 缺框标签=%s"
          % (len(nodes), len(regions), len(typs), result["pdf_lbd_labels"], len(dropped),
             ",".join(x.split("-")[-1] for x in miss) if miss else "无"))


if __name__ == "__main__":
    main()
