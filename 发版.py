# -*- coding: utf-8 -*-
r"""MAP-CAD 一键发版。

版本号 +1 -> 用 PyInstaller 打包 -> 提交推送 -> 建 GitHub Release 并传附件。

用法（一般直接双击 发版.bat 就行，参数会原样传进来）：
    python 发版.py                     正常发版
    python 发版.py --dry               只预演：把要做的事打出来，一个文件都不改
    python 发版.py --version 2.18.0    指定版本号（默认当前 patch + 1）
    python 发版.py --skip-build        不打包（只改版本号 / 推送 / 建 Release）
    python 发版.py --no-push           不提交推送
    python 发版.py --no-release        不建 Release
    python 发版.py --note "补充说明"    追加到 Release 说明末尾

为什么逻辑放 .py 不写在 .bat 里：中文路径、代码页、JSON / HTTP 在 cmd 里很容易被代码页
搞乱（见 编排器/build.py 里的说明），放 Python 里稳。

建 Release 需要 GitHub 凭据，二选一：
  - 装了 GitHub CLI（gh）并且 gh auth login 过；
  - 设了环境变量 GITHUB_TOKEN（或 GH_TOKEN），有 repo 权限。
两者都没有时会跳过建 Release，并把手动发的手顺打出来。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
ORCH = os.path.join(ROOT, "编排器")
APP_PY = os.path.join(ORCH, "app.py")
BUILD_PY = os.path.join(ORCH, "build.py")
DIST_DIR = os.path.join(ORCH, "dist")
NOTES_MD = os.path.join(ROOT, "更新日志.md")

VER_RE = re.compile(r'^APP_VERSION\s*=\s*"([^"]+)"', re.M)
REPO_RE = re.compile(r'^UPDATE_REPO\s*=\s*"([^"]+)"', re.M)
ASSET_RE = re.compile(r'^UPDATE_ASSET\s*=\s*"([^"]+)"', re.M)


def asset_key(name):
    """附件名归一化：GitHub 会把空格换成点（Voltage-CAD MAP.exe -> Voltage-CAD.MAP.exe），
    比较时忽略所有非字母数字，否则旧附件删不掉、再传同名会 422 Validation Failed。"""
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


def log(msg=""):
    """打印中文；控制台代码页不认时退化成可打印字符，不炸掉。"""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "gbk"
        print(str(msg).encode(enc, "replace").decode(enc, "replace"), flush=True)


def read_text(path):
    with open(path, "r", encoding="utf-8", newline="") as f:   # newline="" 保住原有换行
        return f.read()


def write_text(path, s):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(s)


# ---------------- 版本号 ----------------
def parse_ver(s):
    nums = [int(x) for x in re.findall(r"\d+", str(s or ""))][:3]
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums)


def fmt_ver(t):
    return "%d.%d.%d" % t


def bump_ver(s):
    a, b, c = parse_ver(s)
    return fmt_ver((a, b, c + 1))


def read_app_consts():
    txt = read_text(APP_PY)
    m = VER_RE.search(txt)
    if not m:
        raise SystemExit("在 %s 里找不到 APP_VERSION" % APP_PY)
    ver = m.group(1)
    r = REPO_RE.search(txt)
    a = ASSET_RE.search(txt)
    return txt, ver, (r.group(1) if r else ""), (a.group(1) if a else "Voltage-CAD MAP.exe")


def set_app_version(txt, new_ver):
    return VER_RE.sub('APP_VERSION = "%s"' % new_ver, txt, count=1)


# ---------------- 找 Python / git ----------------
def pack_python_candidates():
    here = [
        r"C:\pybuild\python\python.exe",
        os.path.join(ROOT, "_pyinstaller_tool", "python", "python.exe"),
        os.path.join(ORCH, "_pyinstaller_tool", "python", "python.exe"),
        os.path.join(os.path.dirname(ROOT), ".build-venv", "Scripts", "python.exe"),
        os.path.join(ROOT, ".build-venv", "Scripts", "python.exe"),
        sys.executable,
    ]
    out, seen = [], set()
    for p in here:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def find_pack_python():
    """挑一个能 import PyInstaller + PySide6 的解释器；返回 (路径, 试过但没用的清单)。"""
    tried = []
    for p in pack_python_candidates():
        if not os.path.exists(p):
            continue
        try:
            r = subprocess.run([p, "-c", "import PyInstaller, PySide6"],
                               capture_output=True, timeout=180)
        except Exception as e:
            tried.append("%s（启动失败：%s）" % (p, e))
            continue
        if r.returncode == 0:
            return p, tried
        tried.append("%s（缺 PyInstaller / PySide6）" % p)
    return None, tried


def find_git():
    for g in (shutil.which("git"),
              r"C:\Program Files\Git\cmd\git.exe",
              r"C:\Program Files (x86)\Git\cmd\git.exe"):
        if g and os.path.exists(g):
            return g
    return None


def git(git_exe, args, timeout=600):
    cmd = [git_exe] + git_identity(git_exe) + ["-c", "safe.directory=%s" % ROOT] + args
    env = git_env(git_exe)
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, timeout=timeout,
                          text=True, encoding="utf-8", errors="replace", env=env)


def git_identity(git_exe):
    """机器上没配 git 身份时给个占位身份（以前的提交就是 MAP-CAD sync <sync@local>）。

    没配 user.email 时 `git commit` 会直接失败「Please tell me who you are」，
    表现是 git add 做完了却没提交，所以这里必须兜一下。
    """
    for k in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        if (os.environ.get(k) or "").strip():
            return []
    try:
        r = subprocess.run([git_exe, "config", "user.email"], capture_output=True,
                           timeout=30, text=True, encoding="utf-8", errors="replace",
                           env=git_env(git_exe))
        if r.returncode == 0 and (r.stdout or "").strip():
            return []
    except Exception:
        pass
    return ["-c", "user.name=MAP-CAD sync", "-c", "user.email=sync@local"]


def git_env(git_exe):
    """给 git 补上 https 远程助手（git-remote-https）所在目录。

    Codex 自带的 git 是精简版：git-remote-https.exe / libcurl 都在 mingw64\\bin 里，
    默认 PATH 和 exec-path 都没带上，直接跑会报「git: 'remote-https' is not a git command」。
    这里把同级目录补进 PATH，并把 GIT_EXEC_PATH 指过去。
    """
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"          # 别卡在交互式账号密码上
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(git_exe)))
        for sub in ("mingw64\\bin", "usr\\bin", "bin", "mingw64\\libexec\\git-core"):
            d = os.path.join(root, sub)
            if os.path.isdir(d):
                env["PATH"] = d + os.pathsep + env.get("PATH", "")
                if not env.get("GIT_EXEC_PATH"):
                    env["GIT_EXEC_PATH"] = d
    except Exception:
        pass
    return env


# ---------------- 打包 ----------------
def do_build(py):
    log("[打包] %s 编排器/build.py" % py)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([py, BUILD_PY], cwd=ORCH, env=env)
    if r.returncode != 0:
        return None
    exe = os.path.join(DIST_DIR, "Voltage-CAD MAP.exe")
    if not os.path.exists(exe):
        log("  提示：%s 不存在" % exe)
        return None
    log("[打包] 完成：%s（%.1f MB）" % (exe, os.path.getsize(exe) / 1048576.0))
    return exe


# ---------------- 提交推送 ----------------
def do_git(git_exe, version):
    r = git(git_exe, ["rev-parse", "--is-inside-work-tree"])
    if r.returncode != 0 or "true" not in (r.stdout or "").lower():
        log("[推送] 这里不是 git 仓库（没有 .git），跳过提交推送。")
        log("       要发版请先把仓库 clone 下来，或先跑 同步.bat 把改动推上去。")
        return False
    log("[推送] git add -A")
    git(git_exe, ["add", "-A"])
    d = git(git_exe, ["diff", "--cached", "--quiet"])
    if d.returncode == 0:
        log("[推送] 没有需要提交的改动。")
    else:
        stamp = time.strftime("%Y-%m-%d %H:%M")
        c = git(git_exe, ["commit", "-q", "-m", "发版 v%s %s" % (version, stamp)])
        if c.returncode != 0:
            log("[推送] 提交失败：%s" % ((c.stderr or c.stdout or "").strip() or "未知原因"))
            return False
        log("[推送] 已提交：发版 v%s %s" % (version, stamp))
    for i in range(1, 4):
        log("[推送] push 第 %d 次…" % i)
        p = git(git_exe, ["-c", "http.version=HTTP/1.1", "push"])
        if p.returncode == 0:
            log("[推送] 推送完成。")
            return True
        log("       失败：%s" % ((p.stderr or p.stdout or "").strip().splitlines() or [""])[-1])
        if i < 3:
            time.sleep(8)
    log("[推送] 三次都没推上去（网络/代理问题），改动已经在本地提交，不会丢。")
    return False


# ---------------- 建 Release ----------------
def release_notes(note):
    parts = []
    if os.path.exists(NOTES_MD):
        try:
            parts.append(read_text(NOTES_MD).strip())
        except Exception as e:
            log("  读更新日志失败：%s" % e)
    if note:
        parts.append(note.strip())
    return "\n\n".join([p for p in parts if p])


def do_release_gh(gh_exe, repo, tag, exe, notes):
    tmp = os.path.join(os.environ.get("TEMP") or ".", "mapcad_release_notes.md")
    write_text(tmp, notes)
    args = ["release", "create", tag, exe, "--repo", repo, "--title", tag, "--notes-file", tmp]
    r = subprocess.run([gh_exe] + args, cwd=ROOT, capture_output=True, timeout=1800,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode == 0:
        log("[Release] 已用 gh 建好 %s 并传上 %s" % (tag, os.path.basename(exe)))
        return True
    err = (r.stderr or r.stdout or "").strip()
    if "already exists" in err.lower():
        log("[Release] %s 已存在，改成覆盖附件。" % tag)
        up = subprocess.run([gh_exe, "release", "upload", tag, exe, "--repo", repo, "--clobber"],
                            cwd=ROOT, capture_output=True, timeout=1800,
                            text=True, encoding="utf-8", errors="replace")
        if up.returncode == 0:
            log("[Release] 附件已覆盖。")
            return True
        log("[Release] 传附件失败：%s" % ((up.stderr or up.stdout or "").strip()))
        return False
    log("[Release] gh 失败：%s" % err)
    return False


def api(token, method, url, data=None, headers=None, raw=None):
    h = {"Authorization": "Bearer %s" % token, "Accept": "application/vnd.github+json",
         "User-Agent": "MAP-CAD-release"}
    if headers:
        h.update(headers)
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        h["Content-Type"] = "application/json"
    elif raw is not None:
        body = raw
        h["Content-Type"] = "application/octet-stream"
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=1800) as resp:
            txt = resp.read().decode("utf-8", "replace")
            return resp.status, (json.loads(txt) if txt.strip() else {})
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(txt)
        except Exception:
            return e.code, {"message": txt}


def do_release_api(repo, tag, exe, notes, token):
    api_root = "https://api.github.com/repos/%s" % repo
    log("[Release] 用 GitHub API 建 %s …" % tag)
    st, js = api(token, "GET", "%s/releases/tags/%s" % (api_root, urllib.parse.quote(tag)))
    if st == 404:
        st, js = api(token, "POST", "%s/releases" % api_root,
                     data={"tag_name": tag, "name": tag, "body": notes,
                           "draft": False, "prerelease": False})
    if st not in (200, 201):
        log("[Release] 建 Release 失败（HTTP %s）：%s" % (st, js.get("message")))
        return False
    rid = js.get("id")
    name = os.path.basename(exe)
    # GitHub 会把附件名里的空格换成点（"Voltage-CAD MAP.exe" -> "Voltage-CAD.MAP.exe"），
    # 按原名比会漏掉旧附件，再传同名就 422 Validation Failed，所以按归一化后的名字比。
    for a in js.get("assets") or []:
        if asset_key(a.get("name")) == asset_key(name):
            api(token, "DELETE", "%s/releases/assets/%s" % (api_root, a.get("id")))
    with open(exe, "rb") as f:
        blob = f.read()
    up = "https://uploads.github.com/repos/%s/releases/%s/assets?name=%s" % (
        repo, rid, urllib.parse.quote(name))
    st, js = api(token, "POST", up, raw=blob)
    if st == 422:                          # 可能还有残留同名附件，再清一次重试
        st2, js2 = api(token, "GET", "%s/releases/%s" % (api_root, rid))
        for a in (js2.get("assets") or []):
            if asset_key(a.get("name")) == asset_key(name):
                api(token, "DELETE", "%s/releases/assets/%s" % (api_root, a.get("id")))
        st, js = api(token, "POST", up, raw=blob)
    if st in (200, 201):
        log("[Release] 已建 %s 并传上 %s" % (tag, name))
        return True
    log("[Release] 传附件失败（HTTP %s）：%s" % (st, js.get("message")))
    return False


def do_release(repo, tag, exe, notes):
    if not repo:
        log("[Release] 读不到 UPDATE_REPO，跳过。")
        return False
    if not exe:
        log("[Release] 没有 exe（没打包），跳过。")
        return False
    token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    gh_exe = shutil.which("gh")
    if gh_exe:
        return do_release_gh(gh_exe, repo, tag, exe, notes)
    if token:
        try:
            return do_release_api(repo, tag, exe, notes, token)
        except Exception as e:
            log("[Release] API 出错：%s" % e)
            return False
    log("[Release] 没装 gh、也没有 GITHUB_TOKEN / GH_TOKEN，跳过建 Release。")
    log("          手动发：https://github.com/%s/releases/new?tag=%s" % (repo, tag))
    log("          附件名要叫「%s」（程序里的检查更新按这个名字找）。" % os.path.basename(exe))
    return False


# ---------------- 主流程 ----------------
def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True, description="MAP-CAD 一键发版")
    ap.add_argument("--dry", "-n", action="store_true", help="只预演，不改任何东西")
    ap.add_argument("--version", default="", help="指定版本号，默认当前 patch + 1")
    ap.add_argument("--note", default="", help="追加到 Release 说明")
    ap.add_argument("--skip-build", action="store_true", help="跳过打包")
    ap.add_argument("--no-push", action="store_true", help="跳过提交推送")
    ap.add_argument("--no-release", action="store_true", help="跳过建 Release")
    a = ap.parse_args(argv)

    log("============================================")
    log("  MAP-CAD 一键发版%s" % ("（预演 --dry）" if a.dry else ""))
    log("  目录: %s" % ROOT)
    log("============================================")

    for need in (APP_PY, BUILD_PY):
        if not os.path.exists(need):
            log("[错误] 找不到 %s" % need)
            return 1

    txt, cur, repo, asset = read_app_consts()
    new = a.version.strip() or bump_ver(cur)
    log("版本：v%s  ->  v%s" % (cur, new))
    log("仓库：%s（附件名 %s）" % (repo or "（读不到）", asset))

    py, tried = find_pack_python()
    if py:
        log("打包用 Python：%s" % py)
    else:
        log("打包用 Python：没找到能用的（要有 PyInstaller + PySide6）")
        for t in tried:
            log("  试过：%s" % t)

    if a.dry:
        log("")
        log("预演：接下来会做的事")
        log("  1. 把 编排器/app.py 的 APP_VERSION 改成 %s" % new)
        log("  2. %s" % ("跳过打包" if a.skip_build else "跑 编排器/build.py 打包出 编排器/dist/%s" % asset))
        log("  3. %s" % ("跳过提交推送" if a.no_push else "git add/commit/push（不在 git 仓库里会自动跳过）"))
        log("  4. %s" % ("跳过建 Release" if a.no_release else "建 GitHub Release %s 并把 %s 当附件传上去" % ("v" + new, asset)))
        log("  预演结束，什么都没改。")
        return 0

    # 1. 版本号
    if new != cur:
        write_text(APP_PY, set_app_version(txt, new))
        log("[1/4] 版本号已写入 编排器/app.py：%s" % new)
    else:
        log("[1/4] 版本号没变（%s）" % cur)

    # 2. 打包
    exe = None
    if a.skip_build:
        log("[2/4] 跳过打包。")
        cand = os.path.join(DIST_DIR, asset)
        if os.path.exists(cand):
            exe = cand
            log("       用现成的 %s" % cand)
    else:
        if not py:
            log("[2/4] [失败] 没找到能打包的 Python（要装 PyInstaller + PySide6，"
                "或放到 C:\\pybuild\\python）。")
            return 1
        exe = do_build(py)
        if not exe:
            log("[2/4] [失败] 打包没成功，后面步骤不再执行。")
            return 1

    # 3. 提交推送
    pushed = None
    if a.no_push:
        log("[3/4] 跳过提交推送。")
    else:
        g = find_git()
        if not g:
            log("[3/4] 没找到 git，跳过提交推送。")
            pushed = False
        else:
            pushed = do_git(g, new)

    # 4. Release
    if a.no_release:
        log("[4/4] 跳过建 Release。")
        ok = False
    else:
        ok = do_release(repo, "v" + new, exe, release_notes(a.note))

    log("")
    log("============================================")
    log("  版本 %s | 打包 %s | 推送 %s | Release %s" % (
        new, "OK" if exe else "跳过", "OK" if pushed else "跳过/失败", "OK" if ok else "跳过/失败"))
    log("  exe：%s" % (exe or "（没产出）"))
    log("============================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
