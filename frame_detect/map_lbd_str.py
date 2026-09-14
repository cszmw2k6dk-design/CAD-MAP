"""识别结果 JSON + 你的 LBD 提取(pdf_extract) -> 生成 CAD 可读的标签文件。

规则:
  - Node 框 = LBD 区域; 取"落在该框内的 LBD 文字"作为它的 LBD。
  - Typical 框 = 支架; 按"所属 LBD(Node)"分组, 组内 左->右 上->下 编 STR01,02...
  - 输出 L 行: 页号, fx, fy(自下), 标签 —— 坐标取框中心(支架中心)。
"""
import os, sys, json, argparse, re


def read_lbd_extract(path, page):
    """读 pdf_extract.py 输出: L<TAB>页号<TAB>fx<TAB>fy<TAB>文字 (fy 自下, 归一化)。"""
    out = []
    if not path or not os.path.exists(path):
        return out
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) >= 5 and p[0] == "L" and p[1].strip() == str(page):
                m = re.search(r"[A-Za-z0-9]+-LBD-\d+", p[4])
                if m:
                    out.append((float(p[2]), float(p[3]), m.group(0)))
    return out


def center_of(s):
    xs = [p[0] for p in s["points"]]; ys = [p[1] for p in s["points"]]
    return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0), (min(xs), min(ys), max(xs), max(ys))


def row_major(items, med_h):
    def band(vals, tol):
        vals = sorted(vals); out = []; cur = [vals[0]]
        for v in vals[1:]:
            if v - cur[-1] <= tol:
                cur.append(v)
            else:
                out.append(sum(cur) / len(cur)); cur = [v]
        out.append(sum(cur) / len(cur)); return out
    yb = band([it[1] for it in items], max(1.0, med_h * 0.6))
    ri = lambda y: min(range(len(yb)), key=lambda i: abs(yb[i] - y))
    return sorted(items, key=lambda it: (ri(it[1]), it[0]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    ap.add_argument("--extract", required=True, help="pdf_extract.py 的输出txt")
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--prefix", default="STR")
    ap.add_argument("--digits", type=int, default=2)
    ap.add_argument("--emit", default="", help="输出供CAD读的 L 行文件")
    a = ap.parse_args()

    doc = json.load(open(a.json, encoding="utf-8"))
    W = doc.get("imageWidth") or 1
    H = doc.get("imageHeight") or 1
    shapes = doc["shapes"]
    lbds = read_lbd_extract(a.extract, a.page)
    lbds_px = [(fx * W, (1.0 - fy) * H, name) for (fx, fy, name) in lbds]

    nodes = []; typs = []
    for i, s in enumerate(shapes):
        lab = (s.get("label") or "").strip().lower()
        if lab.startswith("node"):
            nodes.append(i)
        elif lab.startswith("typical"):
            typs.append(i)

    # Node 区域内取 LBD
    node_boxes = []
    for i in nodes:
        (cx, cy), (x1, y1, x2, y2) = center_of(shapes[i])
        best = None; bd = 1e18
        for (lx, ly, name) in lbds_px:
            if not (x1 - 5 <= lx <= x2 + 5 and y1 - 5 <= ly <= y2 + 5):
                continue
            d = (lx - cx) ** 2 + (ly - cy) ** 2
            if d < bd:
                bd = d; best = name
        if best:
            shapes[i]["label"] = best
            shapes[i]["description"] = best
            node_boxes.append((x1, y1, x2, y2, best))

    def owner(cx, cy):
        best = None; best_a = None
        for (x1, y1, x2, y2, lab) in node_boxes:
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                area = (x2 - x1) * (y2 - y1)
                if best_a is None or area < best_a:
                    best = lab; best_a = area
        return best

    # Typical(支架) 按所属 LBD 分组, 组内编号
    groups = {}
    tc = {}
    heights = []
    for i in typs:
        (cx, cy), box = center_of(shapes[i])
        tc[i] = (cx, cy)
        heights.append(box[3] - box[1])
        groups.setdefault(owner(cx, cy), []).append(i)
    heights.sort()
    med_h = heights[len(heights) // 2] if heights else 1

    str_count = 0
    group_info = []
    for grp, idxs in groups.items():
        if not grp:
            continue  # 未归属(不在任何 LBD 内)的支架: 视为干扰, 不编号
        items = []
        for i in idxs:
            cx, cy = tc[i]
            items.append((cx, cy, i))
        items = row_major(items, med_h)
        names = []
        for k, (cx, cy, i) in enumerate(items):
            s = a.prefix + str(k + 1).zfill(a.digits)
            shapes[i]["label"] = s
            shapes[i]["description"] = ((grp + " " + s) if grp else s)
            names.append(s)
            str_count += 1
        group_info.append((grp, names))

    out = a.json.replace(".json", "_mapped.json")
    json.dump(doc, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    if a.emit:
        lines = []
        for s in shapes:
            lab = (s.get("label") or "").strip()
            if not lab:
                continue
            (cx, cy), (x1, y1, x2, y2) = center_of(s)
            # STR 号: 角度按支架框长宽比自动(竖条=90,横条=0); 字高按框短边(占页高比例)
            bw, bh = x2 - x1, y2 - y1
            if lab.upper().startswith("STR"):
                ang = 90 if bh > bw else 0
                hgt = min(bw, bh) / float(H)
            else:
                ang = 0
                hgt = 0.0
            lines.append("L\t%d\t%.6f\t%.6f\t%s\t%d\t%.6f"
                         % (a.page, cx / W, 1.0 - cy / H, lab, ang, hgt))
        open(a.emit, "w", encoding="utf-8").write("\n".join(lines) + "\n")

    print("Node(LBD区域):", len(node_boxes), " 支架(STR):", str_count)
    for grp, names in group_info:
        print("  %-22s -> %s" % (grp if grp else "(未归属)", (names[0] + ".." + names[-1]) if names else "-"))
    print("wrote", out)
    if a.emit:
        print("emit", a.emit)


if __name__ == "__main__":
    main()
