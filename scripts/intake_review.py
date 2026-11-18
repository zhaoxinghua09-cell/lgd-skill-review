#!/usr/bin/env python3
"""Review-request intake: fetch a public skill repo and run the static dual-ruler review.

Safety contract
- Static only: review.py is invoked WITHOUT --run, so nothing from the target repo is executed.
- Download uses the public codeload tarball endpoint; no credentials of the submitter are used.
- Extraction rejects absolute paths and '..' traversal.
- Hard limits: 2000 files, 200 MB unpacked, single repo per issue.
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

MAX_FILES = 2000
MAX_BYTES = 200 * 1024 * 1024
HERE = os.path.dirname(os.path.abspath(__file__))
REVIEW = os.path.join(HERE, "review.py")

URL_RE = re.compile(r"https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)")


def parse_target(body):
    m = URL_RE.search(body or "")
    if not m:
        raise SystemExit("找不到 GitHub 仓库地址 / No GitHub repository URL found in the issue body")
    owner, repo = m.group(1), m.group(2).replace(".git", "")
    path = None
    pm = re.search(r"Path:\s*([A-Za-z0-9_./-]+)", body or "")
    if pm:
        value = pm.group(1).strip().strip("/")
        if value and value.lower() not in ("auto", "none", "empty"):
            path = value
    return owner, repo, path


def fetch(owner, repo):
    url = "https://codeload.github.com/%s/%s/tar.gz/HEAD" % (owner, repo)
    req = urllib.request.Request(url, headers={"User-Agent": "lgd-review-intake"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def extract(blob, dest):
    count = 0
    total = 0
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
        for member in tf.getmembers():
            name = member.name
            if not member.isfile():
                continue
            if name.startswith("/") or ".." in name.split("/"):
                raise SystemExit("不安全路径，已中止 / unsafe path in archive: %s" % name)
            total += member.size
            count += 1
            if count > MAX_FILES or total > MAX_BYTES:
                raise SystemExit("超出体积/文件数上限 / archive exceeds limits")
            target = os.path.join(dest, name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with tf.extractfile(member) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def find_skill_dir(root, hint=None):
    if hint:
        normalized = hint.strip("/")
        for dirpath, _dirs, files in os.walk(root):
            if "SKILL.md" not in files:
                continue
            rel = os.path.relpath(dirpath, root).replace(os.sep, "/")
            if rel == normalized or rel.endswith("/" + normalized):
                return dirpath
        raise SystemExit("指定目录里没有 SKILL.md / no SKILL.md at %s" % hint)
    best = None
    for dirpath, _dirs, files in os.walk(root):
        if "SKILL.md" in files:
            depth = dirpath[len(root):].count(os.sep)
            if best is None or depth < best[0]:
                best = (depth, dirpath)
    if not best:
        raise SystemExit("仓库里找不到 SKILL.md / no SKILL.md anywhere in the repository")
    return best[1]


def render(data, owner, repo, skill_rel):
    d = data.get("data", data)
    dims = d.get("dimensions", {})
    blocking = d.get("blocking", [])
    findings = d.get("findings", []) or []
    lines = []
    lines.append("### LGD Dual-Ruler Review — `%s/%s`" % (owner, repo))
    lines.append("")
    lines.append("| 项 / Item | 值 / Value |")
    lines.append("|---|---|")
    lines.append("| Structure score / 结构分 | **%s / 100** |" % d.get("structure_score", d.get("total", "-")))
    if d.get("semantics_score") is not None:
        lines.append("| Semantics score / 语义分 | **%s / 120** |" % d.get("semantics_score"))
    lines.append("| Verdict / 结论 | **%s** |" % d.get("verdict", "-"))
    lines.append("| Skill directory | `%s` |" % skill_rel)
    lines.append("| Mode | static only, no code executed / 仅静态，不执行代码 |")
    lines.append("")
    score = d.get("structure_score", d.get("total", 0))
    try:
        low = float(score) < 60
    except (TypeError, ValueError):
        low = False
    if low:
        lines.append("> 口径提醒 / What this score means：本引擎量的是**可验证性**（测试、声明与实现一致、可复跑、机器可读索引、许可），"
                     "**不是流行度或内容好坏**。一个装量很高的技能也可能因为缺 tests/ 与许可文件而得低分——"
                     "这说明它目前无法被第三方独立验证，不代表它不可用。")
        lines.append("")
        lines.append("> This engine measures **verifiability** — tests, declared-vs-implemented consistency, reproducibility, "
                     "a machine-readable index and licensing — **not popularity or usefulness**. A widely installed skill "
                     "can score low here simply because it ships no tests or license, which means others cannot verify it independently. "
                     "It does not mean the skill is unusable.")
        lines.append("")
    if blocking:
        lines.append("**Blocking / 阻断项**")
        for b in blocking[:12]:
            lines.append("- `%s`" % b)
        lines.append("")
    if dims:
        lines.append("**Dimensions / 各维度**")
        lines.append("")
        lines.append("| Dimension | Score |")
        lines.append("|---|---|")
        for k, v in (dims.items() if isinstance(dims, dict) else []):
            if isinstance(v, dict):
                lines.append("| %s | %s |" % (k, v.get("score", "-")))
            else:
                lines.append("| %s | %s |" % (k, v))
        lines.append("")
    if findings:
        lines.append("**Remediation list / 整改清单**")
        for f in findings[:20]:
            if isinstance(f, dict):
                lines.append("- `%s` %s — %s" % (f.get("id", "-"), f.get("title") or f.get("rule", ""), f.get("fix") or f.get("message", "")))
            else:
                lines.append("- %s" % f)
        lines.append("")

    # Gap decomposition + mechanical projection (projection, not a promise)
    if isinstance(dims, dict) and dims:
        mechanical = {"licensing": "加 LICENSE 文件 / add a LICENSE file",
                      "discoverable": "加机器可读索引 AI-INDEX.json 或 llms.txt / add a machine-readable index",
                      "consistency": "让声明的命令与脚本 argparse 一致 / align declared commands with the scripts",
                      "hygiene": "清掉绝对路径与临时文件 / scrub absolute paths and temp files"}
        rows = []
        gain = 0
        for k, v in dims.items():
            if not isinstance(v, dict):
                continue
            got, mx = v.get("score", 0), v.get("max", 0)
            gap = mx - got
            if gap <= 0:
                continue
            fix = mechanical.get(k, "需真写测试并离线跑通 / requires real tests that run offline")
            can = k in mechanical
            if can:
                gain += gap
            rows.append((k, got, mx, gap, fix, can))
        if rows:
            lines.append("**缺在哪、补什么 / Where the points went, and what closes it**")
            lines.append("")
            lines.append("| Dimension | Got | Max | Gap | What closes it | Mechanical? |")
            lines.append("|---|---|---|---|---|---|")
            for k, got, mx, gap, fix, can in rows:
                lines.append("| %s | %s | %s | %s | %s | %s |" % (k, got, mx, gap, fix, "是 / yes" if can else "否 / no"))
            lines.append("")
            try:
                base = float(d.get("structure_score", d.get("total", 0)))
            except (TypeError, ValueError):
                base = 0
            projected = min(100, int(base + gain))
            lines.append("**机械可补上限 / Projected ceiling from mechanical fixes only: %d / 100**" % projected)
            lines.append("")
            lines.append("> 这是**预测**，不是承诺：只把「加许可、加索引、对齐命令、清路径」这类确定性动作计入，"
                         "**不含写测试**。要把可复跑维度拿满，必须真的交付能离线跑通的 tests。")
            lines.append(">")
            lines.append("> This is a **projection, not a promise**: it counts only deterministic fixes (license, machine-readable index, "
                         "aligned commands, path hygiene). It **does not include writing tests** — the reproducibility dimension "
                         "only fills when real offline tests exist.")
            lines.append("")
    # 机器可读块：让 agent 直接反序列化，不用解析上面的散文
    machine = {
        "schema_version": "1.0",
        "engine": "review.py (static)",
        "repo": "%s/%s" % (owner, repo),
        "skill_path": skill_rel,
        "score": d.get("structure_score", d.get("total")),
        "semantics": d.get("semantics_score"),
        "verdict": d.get("verdict"),
        "blocking": blocking,
        "dimensions": {k: (v.get("score") if isinstance(v, dict) else v)
                       for k, v in (dims.items() if isinstance(dims, dict) else [])},
        "rubric": "https://zhaoxinghua09-cell.github.io/lgd-skill-review/rubric.json",
        "registry": "https://zhaoxinghua09-cell.github.io/lgd-skill-review/registry.json",
        "reproduce": "python scripts/review.py <local-clone-of-this-repo> --json",
    }
    lines.append("")
    lines.append("<details><summary>机器可读结果 / machine-readable result（供 agent 直接消费）</summary>")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(machine, ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("</details>")
    lines.append("")
    lines.append("---")
    lines.append("*Static analysis only; nothing in your repository was executed. "
                 "Appeals take evidence: name a path and a check, and we open it and rule OVERTURNED / UPHELD.*")
    lines.append("*仅静态分析，未执行你仓库里的任何内容。申诉需带证据：给出路径与检验方法，我们复核后裁定 推翻 / 维持。*")
    return "\n".join(lines)


def main():
    body = sys.argv[1] if len(sys.argv) > 1 else ""
    owner, repo, hint = parse_target(body)
    blob = fetch(owner, repo)
    tmp = tempfile.mkdtemp(prefix="lgd-intake-")
    extract(blob, tmp)
    skill_dir = find_skill_dir(tmp, hint)
    rel = os.path.relpath(skill_dir, tmp).replace(os.sep, "/")
    outer = subprocess.run([sys.executable, REVIEW, skill_dir, "--json"],
                           capture_output=True, text=True)
    if outer.returncode not in (0, 1):
        sys.stderr.write(outer.stderr)
        raise SystemExit("评审引擎执行失败 / review engine failed")
    payload = json.loads(outer.stdout)
    print(render(payload, owner, repo, rel))


if __name__ == "__main__":
    main()
