"""Lexical near-duplicate detection across skill packages.

Why this exists: NVIDIA SkillEvaluator ships semantic deduplication (Tier 2).
We have no embeddings and will not pretend to, so this ships the deterministic
subset we can defend on the spot — character 3-gram shingles over
name + description + when-to-use, Jaccard similarity, fixed thresholds.

What it does not do: it cannot tell you two skills *mean* the same thing. A
paraphrase with different vocabulary scores low here. That limitation is stated
in the site's "capabilities they ship that we still do not" table.

Exit codes: 0 = every pair DISTINCT, 1 = at least one NEAR/SAME pair,
2 = bad input. JSON on stdout in all cases.
"""

import argparse
import json
import os
import sys

import safeio

SAME_AT = 0.85
NEAR_AT = 0.65
FIELDS = ("name", "description", "when-to-use", "when_to_use")


def load_text(path):
    """Read one SKILL.md, rooted at its own directory so nothing else is reachable."""
    real = os.path.realpath(path)
    if not os.path.isfile(real):
        raise SystemExit(json.dumps(
            {"ok": False, "error_id": "D001", "error": "not a file: %s" % path},
            ensure_ascii=False))
    safeio.set_root(os.path.dirname(real) or ".")
    return safeio.read_text(real, errors="replace")


def front_matter(text):
    """Return the raw front-matter block, or '' when the file has none."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return "\n".join(lines[1:idx])
    return ""


def declared_text(text):
    """name + description + trigger lines from front matter, or the body when absent."""
    block = front_matter(text)
    if not block:
        return text
    picked = []
    for line in block.splitlines():
        key = line.split(":", 1)[0].strip().lower() if ":" in line else ""
        if key in FIELDS:
            picked.append(line.split(":", 1)[1].strip().strip('"').strip("'"))
    return "\n".join(picked) if picked else block


def shingles(text, size=3):
    """Character 3-grams over whitespace-collapsed, lower-cased text."""
    flat = " ".join(text.lower().split())
    if len(flat) < size:
        return {flat} if flat else set()
    return {flat[i:i + size] for i in range(len(flat) - size + 1)}


def jaccard(left, right):
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / float(len(left | right))


def verdict_for(score):
    if score >= SAME_AT:
        return "SAME"
    if score >= NEAR_AT:
        return "NEAR"
    return "DISTINCT"


def compare(paths):
    texts = [(p, shingles(declared_text(load_text(p)))) for p in paths]
    pairs = []
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            score = jaccard(texts[i][1], texts[j][1])
            pairs.append({
                "left": paths[i],
                "right": paths[j],
                "similarity": round(score, 4),
                "verdict": verdict_for(score),
            })
    return pairs


def main(argv=None):
    ap = argparse.ArgumentParser(description="lexical near-duplicate check (no embeddings)")
    ap.add_argument("paths", nargs="+", help="two or more SKILL.md files")
    args = ap.parse_args(argv)
    if len(args.paths) < 2:
        print(json.dumps({"ok": False, "error_id": "D002", "error": "need at least two paths"},
                         ensure_ascii=False))
        return 2
    try:
        pairs = compare(args.paths)
    except SystemExit as exc:
        print(str(exc))
        return 2
    except safeio.PathOutside as exc:
        print(json.dumps({"ok": False, "error_id": "D003", "error": str(exc)}, ensure_ascii=False))
        return 2
    worst = max((p["verdict"] for p in pairs), key=lambda v: ("DISTINCT", "NEAR", "SAME").index(v))
    top = max(p["similarity"] for p in pairs)
    print(json.dumps({
        "ok": True,
        "thresholds": {"same_at": SAME_AT, "near_at": NEAR_AT},
        "max_similarity": top,
        "verdict": worst,
        "method": "character 3-gram jaccard over name + description + when-to-use",
        "pairs": pairs,
    }, ensure_ascii=False, indent=1))
    return 0 if worst == "DISTINCT" else 1


if __name__ == "__main__":
    sys.exit(main())
