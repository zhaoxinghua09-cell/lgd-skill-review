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
    pm = re.search(r"(?:^|\n)\s*`?(skills?/[A-Za-z0-9_./-]+)`?\s*(?:\n|$)", body or "")
    if pm:
        path = pm.group(1).strip()
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
        candidate = os.path.join(root, hint)
        if os.path.isfile(os.path.join(candidate, "SKILL.md")):
            return candidate
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
