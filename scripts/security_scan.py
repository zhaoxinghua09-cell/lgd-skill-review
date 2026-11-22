#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""确定性技能安全扫描：规则表 + 纯正则，不联网、不调模型、不执行目标代码。

定位（写清楚，避免被当成通用安全扫描器）：
- 它只回答"这些文件里有没有出现已知危险模式"，不判断意图、不看上下文语义；
- 因此它是"已知模式清单 + 可复现"，不是漏洞挖掘，也不是 NVIDIA SkillSpector 那种检测器；
- 误报靠 `# lgd-sec:ignore <RULE_ID> <理由>` 单行抑制，抑制必须写理由，扫描结果会把抑制条数
  一起报出来，避免"用抑制把红灯关掉"。

用法：
  python scripts/security_scan.py . ../summarize-pro --json
  python scripts/security_scan.py .            # 人类可读
退出码：0 = 无阻断项；1 = 有阻断项（blocking）；2 = 参数/路径错误。
"""

import argparse
import json
import os
import re
import sys

SEVERITY_BLOCK = "blocking"
SEVERITY_REVIEW = "review"

RULES = [
    ("SEC001_PROMPT_OVERRIDE", SEVERITY_BLOCK,
     r"(?:ignore|disregard|forget)\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions?|prompts?|rules?)",
     "试图让宿主忽略既有指令（提示注入的典型句式）"),
    ("SEC002_DATA_EXFIL", SEVERITY_BLOCK,
     r"(?:requests|httpx)\.(?:post|put)\(\s*[rf]?[\"']https?://|curl\s+[^\n]*\s(?:-d|--data|-F)\s|webhook\.(?:site|in)\b",
     "把数据发往外部地址（脚本内固定外链或 webhook）"),
    ("SEC003_DESTRUCTIVE", SEVERITY_BLOCK,
     r"\brm\s+-[a-z]*r[a-z]*f|\bRemove-Item[^\n]*-Recurse[^\n]*-Force|\bmkfs\.|\bformat\s+[a-z]:|\bdel\s+/[fsq]",
     "不可逆删除/格式化命令"),
    ("SEC004_SECRET", SEVERITY_BLOCK,
     r"AKIA[0-9A-Z]{16}|\bghp_[A-Za-z0-9]{36}|-----BEGIN\s+(?:RSA |EC |OPENSSH )?PRIVATE KEY|\bsk-[A-Za-z0-9]{20,}",
     "仓库里出现疑似凭证/私钥"),
    ("SEC006_PIPE_SHELL", SEVERITY_BLOCK,
     r"\bcurl[^\n]*\|\s*(?:sudo\s+)?(?:sh|bash|zsh)\b",
     "把网络返回直接喂给 shell（远程执行入口）"),
    ("SEC005_CODE_EXEC", SEVERITY_REVIEW,
     r"\beval\(\s*[^)\n]|\bexec\(\s*[^)\n]|\bos\.system\(\s*[^)\n]|subprocess[^\n]*shell\s*=\s*True",
     "对动态内容求值/起 shell，需人工看输入是否可控"),
    ("SEC007_PATH_TRAVERSAL", SEVERITY_REVIEW,
     r"os\.path\.join\([^)\n]*\.\.[^)\n]*\)",
     "路径拼接里出现 `..`，需确认已做 safe-join 校验"),
]

SUPPRESS_RE = re.compile(
    r"#\s*lgd-sec:ignore\s+((?:[A-Z][A-Z0-9_]*)(?:\s*,\s*[A-Z][A-Z0-9_]*)*)\s*(.*)$")
SCAN_EXT = {".md", ".py", ".sh", ".ps1", ".bash", ".js", ".ts", ".txt", ".yaml", ".yml"}
# 扫描器自身的规则表与它的控制夹具按设计包含这些字符串，必须排除，否则永远自报
DEFAULT_EXCLUDE = ("scripts/security_scan.py", "tests/test_security_scan.py", "tests/secfixtures/",
                   ".git/", "node_modules/")


def iter_files(root):
    if os.path.isfile(root):
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = dirpath.replace("\\", "/")
        dirnames[:] = [d for d in dirnames if not any(
            (rel_dir + "/" + d).lstrip("./").startswith(x.rstrip("/")) or x.rstrip("/") in rel_dir
            for x in DEFAULT_EXCLUDE if not x.endswith(".py"))]
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() in SCAN_EXT:
                yield os.path.join(dirpath, fn)


def scan_file(path, display=None):
    display = display or path
    findings, suppressed = [], 0
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return findings, suppressed
    rules = [(rid, sev, re.compile(pat, re.I), why) for rid, sev, pat, why in RULES]
    for lineno, line in enumerate(text.splitlines(), 1):
        m = SUPPRESS_RE.search(line)
        ignored = set()
        if m:
            ignored = {x.strip() for x in m.group(1).replace(",", " ").split()}
            if not m.group(2).strip():
                findings.append({"rule": "SEC000_SUPPRESSION_NO_REASON", "severity": SEVERITY_BLOCK,
                                 "file": display, "line": lineno,
                                 "why": "抑制注释必须写理由", "excerpt": line.strip()[:120]})
            suppressed += 1
        for rid, sev, rx, why in rules:
            # 抑制可写全 id（SEC006_PIPE_SHELL）或家族前缀（SEC006），两种都认
            if rid in ignored or any(rid == t or rid.startswith(t + "_") for t in ignored):
                continue
            if rx.search(line):
                findings.append({"rule": rid, "severity": sev, "file": display, "line": lineno,
                                 "why": why, "excerpt": line.strip()[:120]})
    return findings, suppressed


def main():
    ap = argparse.ArgumentParser(description="deterministic skill security scan")
    ap.add_argument("roots", nargs="+", help="files or directories to scan")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--max-per-rule", type=int, default=5)
    ap.add_argument("--out", help="write the JSON result to this path (adds checked_at)")
    ap.add_argument("--check", help="recompute and compare with this committed JSON; exit 1 on drift")
    args = ap.parse_args()

    roots = [os.path.abspath(r) for r in args.roots]
    if any(not os.path.exists(r) for r in roots):
        print("path not found: %s" % [r for r in roots if not os.path.exists(r)])
        return 2

    findings, suppressed, scanned = [], 0, 0
    single_dir = len(roots) == 1 and os.path.isdir(roots[0])
    for root in roots:
        for f in iter_files(root):
            if single_dir:
                rel = os.path.relpath(f, root)          # 相对扫描根，跨机器稳定
            elif os.path.isdir(root):
                rel = os.path.join(os.path.basename(root), os.path.relpath(f, root))
            else:
                rel = os.path.basename(f)
            rel = rel.replace("\\", "/")
            if any(rel.find(x.rstrip("/")) >= 0 for x in DEFAULT_EXCLUDE):
                continue
            scanned += 1
            got, sup = scan_file(f, rel)
            findings.extend(got)
            suppressed += sup

    by_rule = {}
    for f in findings:
        by_rule.setdefault(f["rule"], []).append(f)
    blocking = [f for f in findings if f["severity"] == SEVERITY_BLOCK]
    review = [f for f in findings if f["severity"] == SEVERITY_REVIEW]

    result = {
        "schema": "lgd-security-scan-v1",
        "engine": "scripts/security_scan.py (deterministic regex table, no network, no model, no target code executed)",
        "scope": "files scanned: %d | extensions: %s" % (scanned, ",".join(sorted(SCAN_EXT))),
        "limits": [
            "known-pattern list only: no semantic/intent analysis, no vulnerability discovery",
            "catches what the rule table names; a novel phrasing passes",
            "language scope: md/py/sh/ps1/js/ts/txt/yaml — binaries and notebooks are skipped",
        ],
        "rules": [{"id": r[0], "severity": r[1], "why": r[3]} for r in RULES],
        "counts": {"blocking": len(blocking), "review": len(review), "suppressed": suppressed,
                   "files_scanned": scanned},
        "findings": findings,
        "verdict": "FAIL" if blocking else ("REVIEW" if review else "PASS"),
    }

    if args.out:
        import datetime
        result["checked_at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        open(args.out, "w", encoding="utf-8").write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print("written: %s" % args.out)

    if args.check:
        old = json.load(open(args.check, encoding="utf-8"))

        def canon(d):
            # 文件遍历顺序因机器而异，findings 的顺序不是语义；按 (file,line,rule) 归一后再比
            d = {k: v for k, v in d.items() if k != "checked_at"}
            d["findings"] = sorted(d.get("findings", []),
                                   key=lambda f: (f["file"], f["line"], f["rule"], f.get("excerpt", "")))
            return d

        a, b = canon(old), canon(result)
        if a != b:
            diff = [k for k in set(a) | set(b) if a.get(k) != b.get(k)]
            print("SECURITY-SCAN-CHECK: FAIL (drifted fields: %s)" % sorted(diff))
            for k in diff:
                print("  %s: committed=%r fresh=%r" % (k, a.get(k), b.get(k)))
            return 1
        print("SECURITY-SCAN-CHECK: PASS (committed JSON matches a fresh scan, findings normalized)")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("scanned files: %d | blocking=%d review=%d suppressed=%d"
              % (scanned, len(blocking), len(review), suppressed))
        for rid, items in sorted(by_rule.items()):
            print("%-24s %d" % (rid, len(items)))
            for f in items[:args.max_per_rule]:
                print("   %s:%d  %s" % (f["file"], f["line"], f["excerpt"]))
        print("VERDICT: %s" % result["verdict"])
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())

