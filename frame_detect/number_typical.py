import os, sys, json, argparse


def boxes_of(shapes, label):
    out = []
    for i, s in enumerate(shapes):
        if (s.get("label") or "") != label:
            continue
        pts = s.get("points") or []
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        out.append((i, min(xs), min(ys), max(xs), max(ys)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    ap.add_argument("--label", default="Typical", help="要编号的类别")
    ap.add_argument("--prefix", default="STR")
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--digits", type=int, default=2)
    ap.add_argument("--order", default="row", choices=["row", "col"],
                    help="row=上到下再左到右; col=左到右再上到下")
    a = ap.parse_args()

    doc = json.load(open(a.json, encoding="utf-8"))
    shapes = doc.get("shapes", [])
    bx = boxes_of(shapes, a.label)
    if not bx:
        print("no", a.label); return
    hs = sorted(b[4] - b[2] for b in bx)
    ws = sorted(b[3] - b[1] for b in bx)
    med_h = hs[len(hs) // 2]
    med_w = ws[len(ws) // 2]
    tol_h = max(1.0, med_h * 0.6)
    tol_w = max(1.0, med_w * 0.6)

    def band(vals, tol):
        vals = sorted(vals)
        out = []
        cur = [vals[0]]
        for v in vals[1:]:
            if v - cur[-1] <= tol:
                cur.append(v)
            else:
                out.append(sum(cur) / len(cur)); cur = [v]
        out.append(sum(cur) / len(cur))
        return out

    if a.order == "row":
        yb = band([(b[2] + b[4]) / 2 for b in bx], tol_h)
        ri = lambda y: min(range(len(yb)), key=lambda i: abs(yb[i] - y))
        bx.sort(key=lambda b: (ri((b[2] + b[4]) / 2), (b[1] + b[3]) / 2))
    else:
        xb = band([(b[1] + b[3]) / 2 for b in bx], tol_w)
        ci = lambda x: min(range(len(xb)), key=lambda i: abs(xb[i] - x))
        bx.sort(key=lambda b: (ci((b[1] + b[3]) / 2), (b[2] + b[4]) / 2))

    names = []
    for k, (i, x1, y1, x2, y2) in enumerate(bx):
        n = a.start + k
        s = a.prefix + str(n).zfill(a.digits)
        shapes[i]["label"] = s
        shapes[i]["description"] = s
        names.append(s)
    out = a.json.replace(".json", "_STR.json")
    json.dump(doc, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("Typical编号:", names[0], "...", names[-1], " 共", len(names))
    print("wrote", out)


if __name__ == "__main__":
    main()
