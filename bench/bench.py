#!/usr/bin/env python3
"""Build the LGD SkillBench: score public skill repos with the same static dual-ruler engine.

Read-only: each target is downloaded as a public tarball and reviewed statically.
Nothing from the target repository is executed.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import intake_review as intake  # noqa: E402

REVIEW = os.path.join(ROOT, "scripts", "review.py")

# The benchmark walks large monorepos, so it raises the intake guard rails.
intake.MAX_FILES = 6000
intake.MAX_BYTES = 700 * 1024 * 1024

TARGETS = [
    ("vercel-labs", "agent-skills", "skills/react-best-practices"),
    ("mattpocock", "skills", "skills/engineering/code-review"),
    ("microsoft", "azure-skills", "skills/azure-deploy"),
    ("prisma", "skills", "prisma-cli"),
    ("leonxlnx", "taste-skill", "skills/taste-skill"),
    ("juliusbrussee", "caveman", "skills/caveman"),
    ("google", "agents-cli", "skills/google-agents-cli-adk-code"),
    ("anthropics", "skills", "skills/pdf"),
    ("anthropics", "skills", "skills/pptx"),
    ("anthropics", "skills", "skills/docx"),
]

# Optional: score our own packages too. Set LGD_BENCH_OWN_DIR to the folder that
# contains them; no absolute path is ever written into bench.json.
OWN_NAMES = ["summarize-pro", "debug-pro", "wechat-viral-topic", "lgd-skill-review"]
OWN_DIR = os.environ.get("LGD_BENCH_OWN_DIR")


def score_dir(path):
    r = subprocess.run([sys.executable, REVIEW, path, "--json"], capture_output=True, text=True)
    if r.returncode not in (0, 1):
        return {"error": (r.stderr or "")[-300:]}
    d = json.loads(r.stdout)
    data = d.get("data", d)
    dims = data.get("dimensions", {}) or {}
    return {
        "score": data.get("structure_score", data.get("total")),
        "verdict": data.get("verdict"),
        "blocking": data.get("blocking", []),
        "dims": {k: (v.get("score") if isinstance(v, dict) else v) for k, v in dims.items()},
    }


def run_remote(owner, repo, hint):
    try:
        blob = intake.fetch(owner, repo)
    except Exception as e:
        return {"error": "fetch failed: %s" % e}
    tmp = tempfile.mkdtemp(prefix="bench-")
    try:
        try:
            intake.extract(blob, tmp)
            skill_dir = intake.find_skill_dir(tmp, hint)
        except SystemExit as e:
            return {"error": str(e)}
        rel = os.path.relpath(skill_dir, tmp).replace(os.sep, "/")
        out = score_dir(skill_dir)
        out["dir"] = rel
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    rows = []
    for owner, repo, hint in TARGETS:
        label = "%s/%s%s" % (owner, repo, ("@" + hint) if hint else "")
        print("... " + label, file=sys.stderr)
        res = run_remote(owner, repo, hint)
        res["target"] = label
        res["bucket"] = "third-party"
        rows.append(res)

    for name in OWN_NAMES:
        if not OWN_DIR:
            break
        row = score_dir(os.path.join(OWN_DIR, name))
        row["target"] = name
        row["bucket"] = "lgd"
        rows.append(row)

    out = os.path.join(HERE, "bench.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print("written: %s (%d rows)" % (out, len(rows)))


if __name__ == "__main__":
    main()

