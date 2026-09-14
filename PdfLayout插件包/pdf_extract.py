# -*- coding: utf-8 -*-
# MAP文件工具箱 - PDF 文字与坐标提取（供 LBD 识别使用）
# 输出格式（制表符分隔，UTF-8）:
#   P\t页号\t页标题文本(前150字)
#   L\t页号\tfx\tfy\t文字片段   （fx/fy 为页内相对位置 0~1，LBD片段包围盒水平中心x+最低点y）
# 进度文件（第5参数，可选）: READY / TOTAL n / PAGE m / DONE n / ERR:... / CANCELLED
# 用法: pdf_extract.py <pdf> <out.txt> [pageStart] [pageEnd] [prog.txt]
import sys, os

PROG = None
def prog(msg):
    if PROG:
        try:
            with open(PROG, "w", encoding="utf-8") as f:
                f.write(msg)
        except Exception:
            pass

def main():
    if len(sys.argv) < 3:
        print("usage: pdf_extract.py <pdf> <out.txt> [pageStart] [pageEnd] [prog.txt]")
        sys.exit(1)
    pdf, out = sys.argv[1], sys.argv[2]
    global PROG
    if len(sys.argv) > 5:
        PROG = sys.argv[5]
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            print("ERR:pypdf missing, run: python -m pip install pypdf")
            prog("ERR:pypdf missing")
            sys.exit(2)
    prog("READY")
    try:
        reader = PdfReader(pdf)
        n = len(reader.pages)
    except Exception as e:
        print("ERR:open pdf failed: %s" % e)
        prog("ERR:open pdf failed")
        sys.exit(3)
    prog("TOTAL %d" % n)
    p0 = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    p1 = int(sys.argv[4]) if len(sys.argv) > 4 else n
    if p0 < 1: p0 = 1
    if p1 <= 0: p1 = n
    if p1 > n: p1 = n
    lines = []
    for idx in range(p0 - 1, p1):
        if PROG and os.path.exists(PROG + ".cancel"):
            prog("CANCELLED")
            print("CANCELLED at page %d" % (idx + 1), flush=True)
            sys.exit(0)
        page = reader.pages[idx]
        try:
            cb = page.cropbox
            x0, y0 = float(cb.left), float(cb.bottom)
            pw = float(cb.right) - x0
            ph = float(cb.top) - y0
        except Exception:
            x0, y0, pw, ph = 0.0, 0.0, 1.0, 1.0
        if pw <= 0: pw = 1.0
        if ph <= 0: ph = 1.0
        items = []
        all_text = []
        def visit_text(text, cm, tm, font, size):
            if text:
                all_text.append(text)
                try:
                    m0 = cm[0]*tm[0] + cm[2]*tm[1]
                    m1 = cm[1]*tm[0] + cm[3]*tm[1]
                    m2 = cm[0]*tm[2] + cm[2]*tm[3]
                    m3 = cm[1]*tm[2] + cm[3]*tm[3]
                    m4 = cm[0]*tm[4] + cm[2]*tm[5] + cm[4]
                    m5 = cm[1]*tm[4] + cm[3]*tm[5] + cm[5]
                except Exception:
                    m0, m1, m2, m3, m4, m5 = 1.0, 0.0, 0.0, 1.0, 0.0, 0.0
                try:
                    cs = float(size)
                except Exception:
                    cs = 0.0
                # 文字空间近似包围盒 (0,0)-(w,h) 的四个角，经 cm·tm 变换到页面坐标；
                # 标签放在 LBD 标记“正下方、左右居中” → 取水平中心 x 与最低点 y
                w = cs * 0.5 * len(text)
                h = cs
                xs = []
                ys = []
                for tx, ty in ((0.0, 0.0), (w, 0.0), (0.0, h), (w, h)):
                    xs.append(m0*tx + m2*ty + m4)
                    ys.append(m1*tx + m3*ty + m5)
                cx = (min(xs) + max(xs)) * 0.5
                cy = min(ys) - (max(ys) - min(ys)) * 0.15
                items.append([text, cx, cy])
        try:
            page.extract_text(visitor_text=visit_text)
        except Exception:
            items = []
        title = "".join(all_text[:100])
        lines.append("P\t%d\t%.2f\t%.2f\t%s" % (idx + 1, pw, ph, title[:150].replace("\t", " ").replace("\n", " ")))
        for it in items:
            if "LBD" not in it[0].upper():
                continue
            cx, cy = it[1], it[2]
            if cx < x0 or cy < y0 or cx > x0 + pw or cy > y0 + ph:
                continue
            fx = (cx - x0) / pw
            fy = (cy - y0) / ph
            lines.append("L\t%d\t%.6f\t%.6f\t%s" % (idx + 1, fx, fy, it[0].replace("\t", " ").replace("\n", " ")))
        prog("PAGE %d/%d" % (idx + 1, n))
        print("page %d/%d" % (idx + 1, n), flush=True)
    try:
        with open(out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception as e:
        print("ERR:write out failed: %s" % e)
        prog("ERR:write out failed")
        sys.exit(4)
    prog("DONE %d" % (p1 - p0 + 1))
    print("DONE %d" % (p1 - p0 + 1))

main()
