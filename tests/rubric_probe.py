#!/usr/bin/env python3
"""Rubric conformance test: for every published check, break it on purpose and assert the score drops.

This is the test the project was missing. The 23 checks are published as a promise to strangers; until
now nothing verified that the engine actually enforces them. A check that is documented but not
implemented is worse than no check -- it manufactures trust.

Each case gets a fresh copy of a known-good package, applies ONE violation, and records the delta.
Run: python tests/rubric_probe.py            (uses lgd-skill-review itself as the specimen)
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(HERE, "scripts", "review.py")
SPECIMEN = HERE


def score(root, run=False):
    cmd = [sys.executable, ENGINE, root, "--json"] + (["--run"] if run else [])
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 and not r.stdout.strip():
        raise RuntimeError("engine failed: %s" % (r.stderr or "")[:200])
    return json.loads(r.stdout)["data"]


def fresh():
    tmp = tempfile.mkdtemp(prefix="lgd_probe_")
    dst = os.path.join(tmp, "pkg")
    shutil.copytree(SPECIMEN, dst, ignore=shutil.ignore_patterns(
        "docs", "bench", ".git", "__pycache__", "*_probe*"))
    return tmp, dst


def patch_skill(md_dir, fn):
    p = os.path.join(md_dir, "SKILL.md")
    body = open(p, encoding="utf-8").read()
    open(p, "w", encoding="utf-8", newline="\n").write(fn(body))


# ---- 每个 case：名字 / 期望扣分 / 施害动作 ----

def c_no_version(tmp, pkg):
    patch_skill(pkg, lambda b: re.sub(r"\nversion:\s*\S+", "\nversion:", b, count=1))


def c_bad_semver(tmp, pkg):
    patch_skill(pkg, lambda b: re.sub(r"version:\s*\S+", "version: 1.0", b, count=1))


def c_deep_path(tmp, pkg):
    d = os.path.join(pkg, "references", "a", "b")
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "c.md"), "w", encoding="utf-8").write("deep\n")


def c_junk(tmp, pkg):
    os.makedirs(os.path.join(pkg, "__pycache__"), exist_ok=True)
    open(os.path.join(pkg, "__pycache__", "x.pyc"), "wb").write(b"\x00")


def c_flag_missing(tmp, pkg):
    patch_skill(pkg, lambda b: b + "\n\n```bash\npython scripts/review.py --probe-never-implemented\n```\n")


def c_subcmd_missing(tmp, pkg):
    patch_skill(pkg, lambda b: b + "\n\n```bash\npython scripts/review.py probeGhost\n```\n")


def c_no_faithful(tmp, pkg):
    def f(b):
        b = b.replace("不编", "处理").replace("Faithful", "Neutral").replace("faithful", "neutral")
        return b
    patch_skill(pkg, f)


def c_no_golden(tmp, pkg):
    t = os.path.join(pkg, "tests")
    for f in os.listdir(t):
        if f.endswith(".json"):
            os.remove(os.path.join(t, f))


def c_no_demo(tmp, pkg):
    shutil.rmtree(os.path.join(pkg, "demo"), ignore_errors=True)


def c_secret(tmp, pkg):
    # 拼出来再写：本文件自身不能含这个字面量，否则 hygiene 扫到探针源码，基线就被污染了。
    fake = "sk-" + "AbCdEfGhIjKlMnOpQrSt"
    open(os.path.join(pkg, "NOTE.md"), "w", encoding="utf-8").write(
        "fake key for probing: %s\n" % fake)


def c_no_boundary(tmp, pkg):
    def f(b):
        for w in ("安全边界", "边界与异常", "降级", "脱敏", "不输出"):
            b = b.replace(w, "说明")
        return b
    patch_skill(pkg, f)


def c_no_tags(tmp, pkg):
    patch_skill(pkg, lambda b: re.sub(r"\ntags:.*?(?=\n\w|\n---)", "\ntags: []", b, count=1, flags=re.S))


def c_no_license_file(tmp, pkg):
    for f in ("LICENSE", "LICENSE.md", "LICENSE.txt"):
        p = os.path.join(pkg, f)
        if os.path.isfile(p):
            os.remove(p)


CASES = [
    ("structure · 缺 version", 6, c_no_version, "structure"),
    ("structure · version 非 SemVer", 4, c_bad_semver, "structure"),
    ("structure · 深层路径", 4, c_deep_path, "structure"),
    ("structure · junk 文件", 3, c_junk, "structure"),
    ("consistency · 声明了未实现的 flag", 5, c_flag_missing, "consistency"),
    ("consistency · 声明了不存在的子命令", 5, c_subcmd_missing, "consistency"),
    ("consistency · 无保真约束", 5, c_no_faithful, "consistency"),
    ("reproducible · 删 golden 集", 6, c_no_golden, "reproducible"),
    ("reproducible · 删 demo", 4, c_no_demo, "reproducible"),
    ("hygiene · 明文密钥", 8, c_secret, "hygiene"),
    ("hygiene · 无安全边界", 7, c_no_boundary, "hygiene"),
    ("discoverable · tags 清空", 5, c_no_tags, "discoverable"),
    ("licensing · 删许可文件", 1, c_no_license_file, "licensing"),
]


def main():
    base = score(SPECIMEN)
    print("baseline %s %s" % (base["total"], base["verdict"]))
    for k, v in base.get("dimensions", {}).items():
        print("  %-14s %s/%s" % (k, v.get("score"), v.get("max")))
    fails = 0
    print("\n%-42s %6s %6s %8s %s" % ("case", "expect", "delta", "dim", "result"))
    for name, expect, fn, dim in CASES:
        tmp, pkg = fresh()
        try:
            fn(tmp, pkg)
            got = score(pkg)
            dims = base.get("dimensions", {})
            delta = (dims[dim]["score"] - got.get("dimensions", {}).get(dim, {}).get("score", 0)) \
                if dim in dims else None
            drop = base["total"] - got["total"]
            ok = delta is not None and delta >= expect - 0.01
            if not ok:
                fails += 1
            print("%-42s %6s %6s %8s %s"
                  % (name, expect, drop, dim, "OK" if ok else "NOT ENFORCED (dim delta %s)" % delta))
        except Exception as e:
            fails += 1
            print("%-42s %6s %6s %8s ERROR %s" % (name, expect, "-", dim, str(e)[:40]))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print("\n%d/%d enforced" % (len(CASES) - fails, len(CASES)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
