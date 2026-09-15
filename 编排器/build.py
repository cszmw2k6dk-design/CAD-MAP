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
DIST = os.path.join(HERE, "dist")
EXE = os.path.join(DIST, "Voltage-CAD MAP.exe")
SEP = os.pathsep


def pyside_plugins():
    """PySide6 的 plugins 目录：按实际安装位置找，兼容虚拟环境和 C:\\pybuild\\python。"""
    import importlib.util
    spec = importlib.util.find_spec("PySide6")
    if not spec or not spec.submodule_search_locations:
        raise SystemExit("找不到 PySide6，请先在打包用的 Python 里装好 PySide6")
    return os.path.join(list(spec.submodule_search_locations)[0], "plugins")


def find_dll(name):
    """VC 运行库 DLL：必须整套同源，不能新老混用。

    PySide6 自带一套配套的 VC 运行库（版本比 Python 目录里的新），Qt6 就是按它编译的，
    所以优先用 PySide6 里那一套；混用会报「DLL load failed while importing QtCore:
    找不到指定的程序」。找不到才回退到 Python 目录 / 系统目录。
    """
    import importlib.util
    cands = []
    pys = importlib.util.find_spec("PySide6")
    if pys and pys.submodule_search_locations:
        cands.append(list(pys.submodule_search_locations)[0])
    cands += [PYDIR, sys.base_prefix, os.path.join(sys.base_prefix, "DLLs")]
    windir = os.environ.get("WINDIR") or r"C:\Windows"
    cands += [os.path.join(windir, "System32"), os.path.join(windir, "SysWOW64")]
    for d in cands:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None


PYSP = pyside_plugins()


def log(msg):
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "gbk"
        print(msg.encode(enc, "replace").decode(enc, "replace"), flush=True)


def data(src):
    return src + SEP + "."


def build_env():
    """打包用的环境：临时剔除 PATH 里带第三方 icuuc.dll 的目录。

    Qt（PySide6）在 Windows 上用系统 ICU（System32\\icuuc.dll，符号带 _72 之类版本后缀）。
    如果 PATH 里另有别的 ICU（例如 poppler / 其它 Qt 运行时的 icuuc.dll 78），
    PyInstaller 会把它打进包里，运行时 Qt6Core 找不到自己需要的符号，导入就报
    「DLL load failed while importing QtCore: 找不到指定的程序」。所以这里避开它。
    """
    windir = (os.environ.get("WINDIR") or r"C:\Windows").lower()
    keep, dropped = [], []
    for d in (os.environ.get("PATH") or "").split(SEP):
        if not d:
            continue
        if os.path.exists(os.path.join(d, "icuuc.dll")) and not d.lower().startswith(windir):
            dropped.append(d)
        else:
            keep.append(d)
    if dropped:
        log("  已临时从 PATH 剔除带第三方 ICU 的目录：%s" % "; ".join(dropped))
    return dict(os.environ, PYTHONIOENCODING="utf-8", PATH=SEP.join(keep))


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
            os.path.join("PySide6", "plugins", "styles")]
    for dll in ("VCRUNTIME140.dll", "VCRUNTIME140_1.dll", "msvcp140.dll", "concrt140.dll"):
        p = find_dll(dll)
        if p:
            args += ["--add-binary", data(p)]
        else:
            log("  提示：没找到 %s，跳过（系统一般自带）" % dll)
    # 生成的 .spec 丢到 build\ 里：PyInstaller 默认会按 exe 名在 cwd 生成 spec，
    # 仓库里正好有同名的 Voltage-CAD MAP.spec，会被它覆盖成本机绝对路径（提交上去就是噪音）。
    spec_dir = os.path.join(HERE, "build")
    try:
        os.makedirs(spec_dir, exist_ok=True)
    except Exception:
        spec_dir = HERE
    args += ["--exclude-module", "PIL", "--clean", "--noconfirm",
             "--specpath", spec_dir,
             os.path.join(HERE, "app.py")]
    p = subprocess.run(args, cwd=HERE, env=build_env())
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
