# -*- coding: utf-8 -*-
"""一键发版：版本号 +1 -> 打包 -> 提交推送 -> 建 GitHub Release -> 传 exe 附件。

用法（双击 发版.bat 等价于不带参数运行）：
    python 发版.py            正常发版（版本号最后一位自动 +1）
    python 发版.py 2.18.0     指定版本号
    python 发版.py --dry      只预演：算版本号 + 生成更新说明，不改文件不推不发
"""
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
APP_PY = os.path.join(ROOT, "编排器", "app.py")
BUILD_BAT = os.path.join(ROOT, "编排器", "build_exe.bat")
EXE = os.path.join(ROOT, "编排器", "dist", "Voltage-CAD MAP.exe")
NOTES_MD = os.path.join(ROOT, "更新日志.md")

REPO = "cszmw2k6dk-design/CAD-MAP"
BRANCH = "main"
ASSET_NAME = "Voltage-CAD MAP.exe"
UA = "vcadmap-release"

DRY = "--dry" in sys.argv
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
WANT_VER = ARGS[0].lstrip("v") if ARGS else ""

PROXY_PORTS = (7890, 7897, 10809, 10808, 1080, 2080, 33210, 8889)


def find_git():
    """git 不一定在 PATH 里（安装时选了 Git Bash only 就会这样），逐个常见位置找。"""
    cands = ["git"]
    home = os.path.expanduser("~")
    local = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
    pfs = [os.environ.get("ProgramFiles") or r"C:\Program Files",
           os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)"]
    for base in pfs:
        cands += [os.path.join(base, "Git", "cmd", "git.exe"),
                  os.path.join(base, "Git", "bin", "git.exe")]
    cands.append(os.path.join(local, "Programs", "Git", "cmd", "git.exe"))
    import glob
    cands += sorted(glob.glob(os.path.join(local, "GitHubDesktop", "app-*",
                                           "resources", "app", "git", "cmd", "git.exe")),
                    reverse=True)
    # Codex 自带的 git（没装 Git for Windows 时用它兜底）
    cands += sorted(glob.glob(os.path.join(home, ".cache", "codex-runtimes", "*",
                                           "dependencies", "native", "git", "cmd", "git.exe")),
                    reverse=True)
    for c in cands:
        try:
            p = subprocess.run([c, "--version"], capture_output=True, timeout=30)
            if p.returncode == 0:
                return c
        except Exception:
            continue
    raise SystemExit("找不到 git.exe。\n"
                     "请确认装了 Git for Windows；或把 git 的 cmd 目录加到系统 PATH 后重开窗口。\n"
                     "常见位置：C:\\Program Files\\Git\\cmd\\git.exe")


GIT = [find_git(), "-c", "safe.directory=" + ROOT.replace("\\", "/")]


def log(msg):
    """GBK 控制台下也不会因为生僻字符崩掉。"""
    enc = getattr(sys.stdout, "encoding", None) or "gbk"
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode(enc, "replace").decode(enc, "replace"), flush=True)


def dec(raw):
    """git 输出可能是 UTF-8 也可能是 GBK（取决于提交时控制台的代码页）。"""
    if isinstance(raw, str):
        return raw
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def run(cmd, cwd=ROOT, env=None, check=True):
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True)
    if check and p.returncode != 0:
        raise SystemExit("命令失败：%s\n%s\n%s" % (" ".join(cmd), dec(p.stdout), dec(p.stderr)))
    p.out = dec(p.stdout)
    p.err = dec(p.stderr)
    return p


def detect_proxy():
    for port in PROXY_PORTS:
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=0.4)
            s.close()
            return "http://127.0.0.1:%d" % port
        except Exception:
            continue
    return ""


def git_env():
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    proxy = detect_proxy()
    if proxy:
        env["HTTPS_PROXY"] = proxy
        env["HTTP_PROXY"] = proxy
        log("  走代理 %s" % proxy)
    return env


def read_version():
    text = open(APP_PY, "rb").read().decode("utf-8")
    m = re.search(r'^APP_VERSION = "([^"]+)"', text, re.M)
    if not m:
        raise SystemExit("在 app.py 里找不到 APP_VERSION")
    return text, m.group(1)


def bump(ver):
    parts = [int(x) for x in re.findall(r"\d+", ver)[:3]]
    while len(parts) < 3:
        parts.append(0)
    parts[2] += 1
    return ".".join(str(x) for x in parts)


def collect_notes():
    if os.path.exists(NOTES_MD):
        body = open(NOTES_MD, "rb").read().decode("utf-8").strip()
        if body:
            log("  更新说明来自 更新日志.md")
            return body
    last = run(GIT + ["describe", "--tags", "--abbrev=0"], check=False).out.strip()
    rng = "%s..HEAD" % last if last else "HEAD"
    out = run(GIT + ["log", "--pretty=format:%s", rng], check=False).out.splitlines()
    items = []
    for line in out:
        s = line.strip()
        if not s:
            continue
        # 过滤掉脚本自动生成的提交（同步/发版），提交信息被控制台代码页搞乱时也认得出来
        if re.match(r"^(同步|发版)", s) or re.match(r"^\S*\s*\d{4}-\d{2}-\d{2} \d{2}:\d{2} \(v[\d.]+\)", s):
            continue
        if "\ufffd" in s:
            continue
        items.append("- " + s)
    if not items:
        items = ["- 本版为常规维护更新"]
    return ("## 更新内容\n\n" + "\n".join(items) +
            "\n\n## 附件\n\n- `Voltage-CAD MAP.exe`（Windows 单文件版，直接替换旧 exe 即可）")


def get_token():
    env = git_env()
    p = subprocess.run(GIT + ["credential", "fill"],
                       input="protocol=https\nhost=github.com\n\n",
                       capture_output=True, text=True, timeout=120, env=env)
    for line in (p.stdout or "").splitlines():
        if line.startswith("password="):
            return line[len("password="):]
    return ""


def api(url, token, data=None, method="GET", ctype="application/json"):
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", UA)
    if data is not None:
        req.add_header("Content-Type", ctype)
        req.add_header("Content-Length", str(len(data)))
    return urllib.request.urlopen(req, timeout=900)


def main():
    text, cur = read_version()
    new = WANT_VER or bump(cur)
    tag = "v" + new
    log("当前版本 v%s  ->  新版本 %s" % (cur, tag))

    log("[1/5] 生成更新说明...")
    notes = collect_notes()
    log(notes)

    if DRY:
        log("[--dry] 预演结束：没有改文件、没有打包、没有推送、没有发版。")
        return 0

    if new == cur:
        raise SystemExit("新版本号和当前一样（%s），请指定别的版本号。" % cur)

    log("[2/5] 写入新版本号到 app.py ...")
    text2 = re.sub(r'^APP_VERSION = "[^"]+"', 'APP_VERSION = "%s"' % new, text, count=1, flags=re.M)
    with open(APP_PY, "wb") as f:
        f.write(text2.encode("utf-8"))

    log("[3/5] 打包（build_exe.bat，约 1 分钟）...")
    p = run(["cmd", "/c", BUILD_BAT], cwd=os.path.dirname(BUILD_BAT), check=False)
    if p.returncode != 0 or not os.path.exists(EXE):
        raise SystemExit("打包失败：\n%s\n%s" % (p.out[-2000:], p.err[-2000:]))
    log("  产出：%s（%.1f MB）" % (EXE, os.path.getsize(EXE) / 1048576.0))

    log("[4/5] 提交并推送源码...")
    env = git_env()
    run(GIT + ["add", "-A"], env=env)
    run(GIT + ["commit", "-q", "-m", "发版 %s" % tag], env=env)
    last_err = ""
    for i in range(1, 4):
        log("  推送第 %d 次..." % i)
        pr = run(GIT + ["-c", "http.version=HTTP/1.1", "push"], env=env, check=False)
        if pr.returncode == 0:
            break
        last_err = (pr.out + pr.err).strip()
        if i < 3:
            log("  失败，8 秒后重试")
            time.sleep(8)
    else:
        raise SystemExit("推送失败（改动已在本地提交）：\n%s" % last_err)

    log("[5/5] 建 Release 并上传附件...")
    token = get_token()
    if not token:
        raise SystemExit("拿不到 GitHub 凭据，无法发版（源码已推送，可稍后重跑）")
    payload = json.dumps({
        "tag_name": tag,
        "target_commitish": BRANCH,
        "name": tag,
        "body": notes,
        "draft": False,
        "prerelease": False,
    }).encode("utf-8")
    try:
        with api("https://api.github.com/repos/%s/releases" % REPO, token,
                 data=payload, method="POST") as r:
            rel = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raise SystemExit("建 Release 失败：HTTP %s\n%s" % (e.code, e.read()[:400].decode("utf-8", "replace")))
    log("  Release: %s" % rel.get("html_url"))

    upload = (rel.get("upload_url") or "").split("{")[0] + "?name=" + urllib.parse.quote(ASSET_NAME)
    blob = open(EXE, "rb").read()
    with api(upload, token, data=blob, method="POST", ctype="application/octet-stream") as r:
        asset = json.loads(r.read().decode("utf-8", "replace"))
    log("  附件: %s (%.1f MB)" % (asset.get("name"), (asset.get("size") or 0) / 1048576.0))
    log("")
    log("发版完成：%s" % rel.get("html_url"))
    log("用户端打开程序 -> 顶部栏「检查更新」即可看到 %s" % tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
