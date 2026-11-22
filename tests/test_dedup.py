"""Adversarial check for scripts/dedup_check.py.

Each case is a control that would pass if the tool were a stub:
1. identical front matter must be SAME;
2. the same intent in different words must NOT be flagged (honest limitation);
3. unrelated skills must score low;
4. a missing file must exit 2 with JSON, not crash;
5. our own four packages must stay DISTINCT from each other.
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
FX = os.path.join(HERE, "fixtures", "dedup")
TOOL = os.path.join(REPO, "scripts", "dedup_check.py")


def run(*paths):
    proc = subprocess.run([sys.executable, TOOL] + list(paths),
                          capture_output=True, text=True, cwd=REPO)
    return proc.returncode, proc.stdout


def case(name, condition, detail):
    print(("PASS  " if condition else "FAIL  ") + name + " | " + detail)
    return condition


def main():
    ok = True

    code, out = run(os.path.join(FX, "alpha.md"), os.path.join(FX, "alpha-copy.md"))
    data = json.loads(out)
    ok &= case("identical front matter is SAME", data["verdict"] == "SAME" and code == 1,
               "verdict=%s exit=%s sim=%s" % (data["verdict"], code, data["max_similarity"]))

    code, out = run(os.path.join(FX, "alpha.md"), os.path.join(FX, "reworded.md"))
    data = json.loads(out)
    ok &= case("same intent in other words is not flagged (stated limitation)",
               data["verdict"] != "SAME" and code == 0,
               "verdict=%s sim=%s" % (data["verdict"], data["max_similarity"]))

    code, out = run(os.path.join(FX, "alpha.md"), os.path.join(FX, "unrelated.md"))
    data = json.loads(out)
    ok &= case("unrelated skills score low", data["max_similarity"] < 0.2 and code == 0,
               "sim=%s" % data["max_similarity"])

    code, out = run(os.path.join(FX, "missing-file.md"), os.path.join(FX, "alpha.md"))
    ok &= case("missing input exits 2 with JSON", code == 2 and '"D001"' in out,
               "exit=%s out=%s" % (code, out.strip()[:60]))

    packages = [os.path.join(REPO, "..", "summarize-pro", "SKILL.md"),
                os.path.join(REPO, "..", "debug-pro", "SKILL.md"),
                os.path.join(REPO, "..", "wechat-viral-topic", "SKILL.md"),
                os.path.join(REPO, "SKILL.md")]
    if all(os.path.isfile(p) for p in packages):
        code, out = run(*packages)
        data = json.loads(out)
        ok &= case("our four packages stay DISTINCT", data["verdict"] == "DISTINCT" and code == 0,
                   "max=%s" % data["max_similarity"])
    else:
        ok &= case("our four packages stay DISTINCT", False, "sibling packages not present")

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
