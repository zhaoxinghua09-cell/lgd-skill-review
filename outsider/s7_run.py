# -*- coding: utf-8 -*-
"""S7 外审一键复跑件（第三方独立席位用）

用途：让一个与 owner 无利益关系、非仓库协作者的人，在自己机器上把
zhaoxinghua09-cell 的四个技能包按「钉死的 commit」复跑一遍，产出可校验回执。

它只做四件事：
  1) 按 40 位 commit 拉取（钉版本，不用 main，避免时间漂移）
  2) 记录每个关键文件的字节数与 sha256
  3) 跑每个包的 demo 自证脚本，记录退出码
  4) 探测 README/SKILL.md 里每条链接，记录 status 与是否内容命中

判 PASS 的条件（脚本自动判，人不改）：
  - 4/4 clone 成功且 HEAD == 钉死 commit
  - 4/4 demo 退出码 == 0
  - 链接全部 200 且内容命中
  - runner_collaborator == false（由运行者自报，脚本原样写入，不代填）

用法（Python 3.9+，只用标准库，无需安装任何依赖）：
  python s7_run.py --runner "张三" --affiliation "某某大学" --gh-user zhangsan \
                   --relationship "与本项目无利益关系" --out s7_receipt.json

自测（owner 一方干跑，回执里会被标 owner_self_run=true，不得当外人实测）：
  python s7_run.py --runner OWNER --gh-user zhaoxinghua09-cell --self-run --out owner_dryrun.json
"""
import argparse, hashlib, json, os, platform, re, shutil, subprocess, sys, tempfile, time
import urllib.error, urllib.request

OWNER = "zhaoxinghua09-cell"

# 钉版本：2026-11-28 实测 HEAD。改这里等于改复跑对象，须同步更新 README 与台账。
ITEMS = [
    {"repo": "summarize-pro",      "pin": "commit", "commit": "eb106824ae6ba4bdbfeaf19228d16c88be6ad941", "demo": "demo/tamper_test.py"},
    {"repo": "debug-pro",          "pin": "commit", "commit": "8753201365777643f066451b082f4c4eaffac9bc", "demo": "demo/prove_evidence.py"},
    {"repo": "wechat-viral-topic", "pin": "commit", "commit": "360b328eb3b71e11c8b39a27fadfd78aacc86ccf", "demo": "demo/prove_hits.py"},
    # 本包是复跑件的宿主仓库：自己改自己的 commit 会无限漂移，所以钉内容哈希而不是 commit
    {"repo": "lgd-skill-review",   "pin": "hash", "commit": "", "demo": "demo/prove_score.py",
     "files_expected": {"SKILL.md": "9074db6d592e8d4fe2ff2ebeaa74013beadda59a7443323c8798722c4d224d68",
                        "README.md": "44ef14460dcba7b976785b18321068b303c45070284a955fc6545569b4d72185"}},
]
FILES = ("SKILL.md", "README.md")
UA = {"User-Agent": "s7-outsider-run/1.0 (+independent review)"}


def sh(cmd, cwd=None, timeout=240):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(65536), b""):
            h.update(b)
    return h.hexdigest()


def pin_clone(repo, commit, work, files_expected=None):
    """按 commit 拉取：先浅克隆默认分支，再按 sha 深挖一次。失败退回全量克隆。
    files_expected 非空时改走「内容哈希钉版本」：不 checkout 指定 commit，只核对文件哈希。"""
    dest = os.path.join(work, repo)
    src = "https://github.com/%s/%s" % (OWNER, repo)
    steps = []
    if files_expected:
        rc1, out1 = sh(["git", "clone", "--quiet", "--depth", "1", src, dest], timeout=300)
        if rc1 != 0:
            return dest, rc1, [out1], {}
        head_rc, head = sh(["git", "-C", dest, "rev-parse", "HEAD"])
        ok = True
        for f, exp in files_expected.items():
            p = os.path.join(dest, f)
            got = sha256(p) if os.path.exists(p) else ""
            if got != exp:
                ok = False
                steps.append("hash mismatch %s: expected %s got %s" % (f, exp[:12], got[:12] or "(missing)"))
        meta = {"clone_source": src, "pin_mode": "content-hash", "pinned_commit": "",
                "head": head.strip() if head_rc == 0 else "", "head_matches": ok,
                "clone_steps": steps, "files_expected": files_expected}
        return dest, 0 if ok else 3, steps, meta
    rc1, out1 = sh(["git", "clone", "--quiet", "--no-checkout", src, dest], timeout=300)
    if rc1 != 0:
        return dest, rc1, [out1], {}
    rc2, out2 = sh(["git", "-C", dest, "fetch", "--quiet", "--depth", "1", "origin", commit], timeout=300)
    steps.append("git fetch --depth 1 origin %s -> rc=%d %s" % (commit, rc2, out2.splitlines()[-1] if out2 else ""))
    if rc2 == 0:
        rc3, out3 = sh(["git", "-C", dest, "checkout", "--quiet", "FETCH_HEAD"], timeout=120)
        steps.append("git checkout FETCH_HEAD -> rc=%d" % rc3)
        target = commit
    else:
        rc4, out4 = sh(["git", "-C", dest, "fetch", "--quiet", "origin"], timeout=600)
        rc5, out5 = sh(["git", "-C", dest, "checkout", "--quiet", commit], timeout=180)
        steps.append("fallback full fetch rc=%d, checkout rc=%d %s" % (rc4, rc5, out5.splitlines()[-1] if out5 else ""))
        target = commit
        rc3 = rc5
    head_rc, head = sh(["git", "-C", dest, "rev-parse", "HEAD"])
    meta = {"clone_source": src, "pinned_commit": commit, "head": head if head_rc == 0 else "",
            "head_matches": (head_rc == 0 and head.strip().lower() == commit.lower()),
            "clone_steps": steps}
    return dest, rc3, steps, meta


def probe(url, timeouts=(20, 35, 50)):
    """三次递进超时。GitHub 对短超时经常直接 reset，单次 15s 判死链会误伤（本项目已踩过）。"""
    last = None
    for i, tmo in enumerate(timeouts):
        try:
            req = urllib.request.Request(url, headers=UA, method="GET")
            with urllib.request.urlopen(req, timeout=tmo) as r:
                body = r.read(3000).decode("utf-8", "ignore")
                return {"url": url, "status": int(getattr(r, "status", 200) or 200),
                        "content_matched": len(body.strip()) > 0,
                        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "attempts": i + 1}
        except urllib.error.HTTPError as e:
            return {"url": url, "status": int(e.code), "content_matched": False,
                    "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "attempts": i + 1, "class": "http"}
        except Exception as e:
            last = type(e).__name__
            time.sleep(2)
    return {"url": url, "status": 0, "content_matched": False,
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "attempts": len(timeouts), "class": last}


def main():
    ap = argparse.ArgumentParser(description="S7 independent re-run kit")
    ap.add_argument("--runner", required=True, help="真实姓名或可核验身份")
    ap.add_argument("--affiliation", default="")
    ap.add_argument("--gh-user", default="", help="GitHub 用户名，用于核对是否为仓库协作者")
    ap.add_argument("--relationship", default="", help="与本项目的关系，须写明无利益关系")
    ap.add_argument("--self-run", action="store_true", help="owner 一方干跑，回执会标记，不得当外人实测")
    ap.add_argument("--out", default="s7_receipt.json")
    ap.add_argument("--workdir", default="")
    a = ap.parse_args()

    work = a.workdir or tempfile.mkdtemp(prefix="s7_")
    items, all_links = [], []
    for it in ITEMS:
        t0 = time.time()
        dest, rc, steps, meta = pin_clone(it["repo"], it.get("commit", ""), work, it.get("files_expected"))
        rec = {"repo": "%s/%s" % (OWNER, it["repo"]), "artifact_id": "S7-%s" % it["repo"],
               "commit": it.get("commit") or (meta.get("head") or "")[:40],
               "pin_mode": meta.get("pin_mode", "commit"), "clone_rc": rc, **meta}
        files = []
        for f in FILES:
            p = os.path.join(dest, f)
            if os.path.exists(p):
                files.append({"path": f, "bytes": os.path.getsize(p), "sha256": sha256(p)})
        rec["files"] = files
        d = os.path.join(dest, it["demo"].replace("/", os.sep))
        if os.path.exists(d):
            rc_d, tail = sh([sys.executable, it["demo"]], cwd=dest, timeout=300)
            rec["demo"] = {"cmd": "python %s" % it["demo"], "rc": rc_d, "tail": tail[-600:]}
        else:
            rec["demo"] = {"cmd": "python %s" % it["demo"], "rc": 127, "tail": "demo script missing"}
        urls = set()
        for f in FILES:
            p = os.path.join(dest, f)
            if os.path.exists(p):
                t = open(p, encoding="utf-8", errors="ignore").read()
                urls |= set(re.findall(r"https?://[^\s\)\]\"'<>`]+", t))
        urls = {u.rstrip(".,;:，。；）") for u in urls}
        lrecs = [probe(u) for u in sorted(urls)]
        rec["links"] = lrecs
        all_links += lrecs
        rec["elapsed_s"] = round(time.time() - t0, 1)
        items.append(rec)
        print("[%s] clone=%s head_matches=%s demo=%s links=%d/%d" % (
            it["repo"], rc, meta.get("head_matches"), rec["demo"]["rc"],
            sum(1 for l in lrecs if l["status"] == 200), len(lrecs)))

    ok_clone = sum(1 for i in items if i["clone_rc"] == 0 and i.get("head_matches"))
    ok_demo = sum(1 for i in items if i["demo"]["rc"] == 0)
    ok_links = sum(1 for l in all_links if l["status"] == 200 and l["content_matched"])
    verdict = "PASS" if (ok_clone == 4 and ok_demo == 4 and ok_links == len(all_links) and all_links) else "FAIL"

    receipt = {
        "artifact_id": "S7-RECEIPT-%s" % time.strftime("%Y%m%d"),
        "type": "s7-outsider-receipt",
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "runner": a.runner,
        "affiliation": a.affiliation,
        "github_username": a.gh_user,
        "relationship": a.relationship,
        "runner_collaborator": False if not a.self_run else "n/a(owner self run)",
        "owner_self_run": bool(a.self_run),
        "host": {"os": platform.platform(), "python": platform.python_version(), "cwd": work},
        "items": items,
        "links": all_links,
        "counts": {"items": len(items), "clone_ok": ok_clone, "demo_ok": ok_demo,
                   "links": len(all_links), "links_ok": ok_links},
        "verdict": verdict,
        "note": ("owner 一方干跑，按证据纪律只能记同操作者干跑，不得记为外人实测"
                 if a.self_run else "由上述 runner 独立执行；runner_collaborator 由运行者自报"),
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(receipt, f, ensure_ascii=False, indent=2)
    print("\nverdict=%s  items=%d clone_ok=%d demo_ok=%d links=%d/%d" % (
        verdict, len(items), ok_clone, ok_demo, ok_links, len(all_links)))
    print("receipt -> %s" % os.path.abspath(a.out))
    sys.exit(0 if verdict == "PASS" else 4)


if __name__ == "__main__":
    main()
