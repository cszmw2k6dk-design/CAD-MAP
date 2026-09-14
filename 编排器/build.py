# -*- coding: utf-8 -*-
r"""打包 Voltage-CAD MAP.exe。

用 Python 传参数，避免中文路径（PdfLayout插件包）在 cmd 里被控制台代码页搞乱，
这是之前 build_exe.bat 里 `--add-data "..\PdfLayout插件包\PdfLayout.lsp;."` 失败的原因。
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))     # ...\MAP-CAD\编排器
ROOT = os.path.dirname(HERE)                          # ...\MAP-CAD
PY = sys.executable
PYDIR = os.path.dirname(PY)
PYSP = os.path.join(PYDIR, "Lib", "site-packages", "PySide6", "plugins")
DIST = os.path.join(HERE, "dist")
EXE = os.path.join(DIST, "Voltage-CAD MAP.exe")
SEP = os.pathsep


def log(msg):
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "gbk"
        print(msg.encode(enc, "replace").decode(enc, "replace"), flush=True)


def data(src):
    return src + SEP + "."


def main():
    for need in ("app.py", "app.ico", "app_icon.png", "logo_blue.png",
                 "PdfLayout_auto.lsp", "PdfLayout_ai.lsp"):
        if not os.path.exists(os.path.join(HERE, need)):
            raise SystemExit("缺少文件：%s" % os.path.join(HERE, need))
    plugin_lsp = os.path.join(ROOT, "PdfLayout插件包", "PdfLayout.lsp")
    if not os.path.exists(plugin_lsp):
        raise SystemExit("缺少插件：%s" % plugin_lsp)

    log("[1/3] 生成图标 ...")
    subprocess.run([PY, os.path.join(HERE, "make_icon.py")], cwd=HERE, check=False)

    # 旧 exe 先挪走：这样后面只要 exe 存在，就保证是这次新产出的
    old = EXE + ".old"
    if os.path.exists(old):
        os.remove(old)
    if os.path.exists(EXE):
        os.replace(EXE, old)

    log("[2/3] PyInstaller 打包中（约 1 分钟）...")
    args = [PY, "-m", "PyInstaller", "--onefile", "--windowed",
            "--icon", os.path.join(HERE, "app.ico"),
            "--name", "Voltage-CAD MAP",
            "--add-data", data(os.path.join(HERE, "app_icon.png")),
            "--add-data", data(os.path.join(HERE, "logo_blue.png")),
            "--add-data", data(os.path.join(HERE, "PdfLayout_auto.lsp")),
            "--add-data", data(os.path.join(HERE, "PdfLayout_ai.lsp")),
            "--add-data", data(plugin_lsp),
            "--collect-binaries", "PySide6", "--collect-binaries", "shiboken6",
            "--add-data", os.path.join(PYSP, "platforms") + SEP +
            os.path.join("PySide6", "plugins", "platforms"),
            "--add-data", os.path.join(PYSP, "styles") + SEP +
            os.path.join("PySide6", "plugins", "styles"),
            "--add-binary", data(os.path.join(PYDIR, "VCRUNTIME140.dll")),
            "--add-binary", data(os.path.join(PYDIR, "VCRUNTIME140_1.dll")),
            "--add-binary", data(os.path.join(PYDIR, "msvcp140.dll")),
            "--add-binary", data(os.path.join(PYDIR, "concrt140.dll")),
            "--exclude-module", "PIL", "--clean", "--noconfirm",
            os.path.join(HERE, "app.py")]
    p = subprocess.run(args, cwd=HERE, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    log("")
    if p.returncode != 0 or not os.path.exists(EXE):
        log("[失败] 打包没成功（退出码 %s），旧 exe 已保留为 %s" % (p.returncode, old))
        return 1

    log("[3/3] 收尾 ...")
    try:
        shutil.copyfile(os.path.join(HERE, "PdfLayout_auto.lsp"),
                        os.path.join(DIST, "PdfLayout_auto.lsp"))
        shutil.copyfile(os.path.join(HERE, "PdfLayout_ai.lsp"),
                        os.path.join(DIST, "PdfLayout_ai.lsp"))
    except Exception as e:
        log("  复制附属 lsp 失败（不影响 exe）：%s" % e)
    if os.path.exists(old):
        os.remove(old)
    log("打包完成：%s（%.1f MB）" % (EXE, os.path.getsize(EXE) / 1048576.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
