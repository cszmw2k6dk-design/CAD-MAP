# -*- coding: utf-8 -*-
# 生成应用图标 app.ico（透明底 · Voltage-CAD MAP 的 V 标志）
# 复用 icon_out\v_crop.png（抠好、去白边的 V 透明图），输出多尺寸 ICO。
import os
import sys
from PIL import Image


def find_v():
    base = os.path.dirname(os.path.abspath(__file__))
    cands = [
        os.path.join(base, "..", "icon_out", "v_crop.png"),
        os.path.join(base, "icon_out", "v_crop.png"),
        os.path.join(base, "v_crop.png"),
        os.path.join(base, "..", "icon_out", "app_icon_v_1024.png"),
    ]
    for c in cands:
        if os.path.exists(c):
            return c
    return None


def main():
    src = find_v()
    if not src:
        print("[错误] 找不到 V 图标资源 v_crop.png / app_icon_v_1024.png", file=sys.stderr)
        sys.exit(1)
    img = Image.open(src).convert("RGBA")
    # 256 透明画布，V 放大到约 80% 并居中
    canvas = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    maxs = 208
    scale = maxs / max(img.size)
    nw, nh = int(img.width * scale), int(img.height * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    canvas.paste(img, ((256 - nw) // 2, (256 - nh) // 2), img)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico")
    canvas.save(out, format="ICO",
                sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("icon written:", out)


if __name__ == "__main__":
    main()
