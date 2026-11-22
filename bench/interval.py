"""Wilson 95% intervals for the static bench proportions.

Why this is here and what it is not: NVIDIA SkillEvaluator reports pass@k
intervals from *live* paired runs. We do not run models, so we cannot produce a
live interval and will not fake one. What we can report honestly is the
uncertainty of our own static sample: given 16 third-party targets, what share
clears the pass bar, and how wide is that share at 95%.

Wilson (not normal-approx) because the share is near the boundary and n is
small: the normal approximation gives a negative lower bound at p=0.
"""

import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LEADERBOARD = os.path.join(HERE, "leaderboard.json")
PASS_AT = 60
Z = 1.96


def wilson(successes, n, z=Z):
    """Wilson score interval for a binomial proportion. Returns (low, high)."""
    if n <= 0:
        return 0.0, 0.0
    p = successes / float(n)
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2.0 * n)) / denom
    spread = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * n)) / n) / denom
    low = max(0.0, centre - spread)
    high = min(1.0, centre + spread)
    return low, high


def describe(rows, bucket):
    subset = [r for r in rows if r.get("bucket") == bucket]
    n = len(subset)
    if n == 0:
        return {"bucket": bucket, "n": 0}
    passed = sum(1 for r in subset if r.get("score", 0) >= PASS_AT)
    low, high = wilson(passed, n)
    return {
        "bucket": bucket,
        "n": n,
        "pass_bar": PASS_AT,
        "passed": passed,
        "share": round(passed / float(n), 4),
        "wilson95": [round(low, 4), round(high, 4)],
    }


def recompute(path=LEADERBOARD):
    with open(path, encoding="utf-8") as fh:
        board = json.load(fh)
    board["summary"]["stats"] = {
        "method": "Wilson score interval, 95%, on the static bench (not a live-run interval)",
        "pass_bar": PASS_AT,
        "buckets": [describe(board["rows"], "third-party"), describe(board["rows"], "lgd")],
    }
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(board, fh, ensure_ascii=False, indent=2)
    return board["summary"]["stats"]


if __name__ == "__main__":
    stats = recompute()
    print(json.dumps(stats, ensure_ascii=False, indent=1))
