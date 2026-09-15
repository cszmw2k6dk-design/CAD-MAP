# -*- coding: utf-8 -*-
"""命令行入口：导出 LBD 区域范围 + Typical(支架)范围。

实现只有一份，在 编排器/lbd_regions.py —— 那份会被打进 Voltage-CAD MAP.exe，
UI 的「执行输出」流程会自动调用它。这个脚本只是命令行壳子，方便单独跑。

用法:
  python extract_lbd_typical.py --json "C:\\...\\agent3-debug.json" --out 输出目录
输出(输出目录里):
  lbd_regions.csv   LBD 区域范围(含名字、所属逆变器、支架数)
  typicals.csv      Typical(支架)范围(含所属 LBD 区域)
  lbd_symbols.csv   LBD 断开点符号位置
  pages.csv         每页尺寸与统计
  lbd_typical.json  以上数据的合并版(不带图片)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CANDIDATES = (os.path.join(os.path.dirname(HERE), "编排器"),   # CAD-MAP-main/编排器
              os.path.dirname(HERE))                            # 同目录备用

for cand in CANDIDATES:
    if os.path.exists(os.path.join(cand, "lbd_regions.py")):
        sys.path.insert(0, cand)
        break

try:
    import lbd_regions
except ImportError:
    raise SystemExit("找不到 编排器/lbd_regions.py（提取实现放在那里，UI 也共用它）")

if __name__ == "__main__":
    raise SystemExit(lbd_regions.main())
