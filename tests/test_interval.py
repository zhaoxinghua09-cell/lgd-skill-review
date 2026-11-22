"""Controls for bench/interval.py.

A stub that returns 0..1 for everything would pass a "does it run" test, so each
control pins a value that a wrong implementation cannot produce:
- k=0,n=10: Wilson lower bound is 0, upper is ~0.2775 (normal approx would give 0,0);
- k=10,n=10: upper is 1, lower is ~0.7225;
- k=5,n=10: symmetric around 0.5, ~[0.2366, 0.7634];
- published leaderboard stats must match a fresh recomputation;
- interval must widen as n shrinks for the same share.
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "bench"))

import interval  # noqa: E402


def case(name, condition, detail):
    print(("PASS  " if condition else "FAIL  ") + name + " | " + detail)
    return condition


def close(value, target, tol=5e-4):
    return abs(value - target) <= tol


def main():
    ok = True

    low, high = interval.wilson(0, 10)
    ok &= case("k=0,n=10", close(low, 0.0) and close(high, 0.2775), "%.4f..%.4f" % (low, high))

    low, high = interval.wilson(10, 10)
    ok &= case("k=10,n=10", close(low, 0.7225) and close(high, 1.0), "%.4f..%.4f" % (low, high))

    low, high = interval.wilson(5, 10)
    ok &= case("k=5,n=10", close(low, 0.2366) and close(high, 0.7634), "%.4f..%.4f" % (low, high))

    small = interval.wilson(2, 4)
    big = interval.wilson(20, 40)
    width_small = small[1] - small[0]
    width_big = big[1] - big[0]
    ok &= case("interval narrows with n", width_big < width_small,
               "w(4)=%.3f w(40)=%.3f" % (width_small, width_big))

    proc = subprocess.run([sys.executable, os.path.join(REPO, "bench", "interval.py")],
                          capture_output=True, text=True, cwd=REPO)
    out = json.loads(proc.stdout)
    with open(os.path.join(REPO, "bench", "leaderboard.json"), encoding="utf-8") as fh:
        published = json.load(fh)["summary"].get("stats", {})
    ok &= case("published stats match a fresh recompute", published == out,
               "exit=%s buckets=%s" % (proc.returncode, len(out.get("buckets", []))))

    tp = [b for b in out["buckets"] if b["bucket"] == "third-party"][0]
    ok &= case("third-party bucket carries n and an interval",
               tp["n"] > 0 and 0.0 <= tp["wilson95"][0] < tp["wilson95"][1] <= 1.0,
               "n=%s share=%s ci=%s" % (tp["n"], tp["share"], tp["wilson95"]))

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
