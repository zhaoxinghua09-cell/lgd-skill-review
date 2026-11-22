"""反向验证：喂坏数据，test_endpoint_consistency.py 必须真的报错。

一个永远 PASS 的检查等于没有检查。这里把 docs 复制到临时目录，逐个注入一种"两个端点互相矛盾"
的坏值，断言检查器返回非零；最后把未改动的副本跑一遍，断言返回 0。
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
CHECKER = os.path.join(HERE, "test_endpoint_consistency.py")


def run(docs):
    env = dict(os.environ, LGD_DOCS=docs)
    p = subprocess.run([sys.executable, CHECKER], capture_output=True, text=True, env=env)
    return p.returncode, [l for l in p.stdout.splitlines() if l.startswith("FAIL")]


def mutate(docs, name, fn):
    p = os.path.join(docs, name)
    d = json.load(open(p, encoding="utf-8"))
    fn(d)
    open(p, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=2))


MUTATIONS = [
    ("leaderboard gap 与顶分不符", "leaderboard.json",
     lambda d: d["summary"].update({"gap": d["summary"]["lgd_top"] - d["summary"]["third_party_top"] + 7}),
     lambda fails: any("gap" in f for f in fails)),
    ("wilson share 与计数不符", "leaderboard.json",
     lambda d: d["summary"]["stats"]["buckets"][0].update({"passed": 3, "share": 0.0}),
     lambda fails: any("Wilson" in f for f in fails)),
    ("drift result 与 rows 不符", "drift-check.json",
     lambda d: d["result"].update({"checked": d["result"]["checked"] + 1}),
     lambda fails: any("drift-check" in f for f in fails)),
    ("漂移样本漏掉一个第三方目标", "drift-check.json",
     lambda d: d["rows"].pop(),
     lambda fails: any("covers exactly" in f for f in fails)),
    ("run-proof 分数与维度之和不符", "run-proof.json",
     lambda d: d["packages"][0].update({"score": d["packages"][0]["score"] - 3}),
     lambda fails: any("run-proof" in f for f in fails)),
    ("landscape 项目缺 https 链接", "landscape.json",
     lambda d: d["projects"][0].update({"url": "http://example.com/x"}),
     lambda fails: any("landscape" in f for f in fails)),
    ("rubric 权重和不再等于 100", "rubric.json",
     lambda d: d["dimensions"][0].update({"weight": d["dimensions"][0]["weight"] + 5}),
     lambda fails: any("rubric" in f for f in fails)),
]

ok = 0
tmp_root = tempfile.mkdtemp(prefix="lgd-epc-")
try:
    for label, fname, fn, matches in MUTATIONS:
        docs = os.path.join(tmp_root, "docs")
        shutil.rmtree(docs, ignore_errors=True)
        shutil.copytree(os.path.join(REPO, "docs"), docs)
        mutate(docs, fname, fn)
        code, fails = run(docs)
        good = code != 0 and matches(fails)
        print(("PASS  " if good else "FAIL  ") + "注入坏值被抓：" + label
              + " | exit=%d matched=%s" % (code, bool(matches(fails))))
        ok += 1 if good else 0

    docs = os.path.join(tmp_root, "docs-clean")
    shutil.rmtree(docs, ignore_errors=True)
    shutil.copytree(os.path.join(REPO, "docs"), docs)
    code, fails = run(docs)
    good = code == 0
    print(("PASS  " if good else "FAIL  ") + "未改动副本仍 PASS | exit=%d fails=%d" % (code, len(fails)))
    ok += 1 if good else 0
finally:
    shutil.rmtree(tmp_root, ignore_errors=True)

total = len(MUTATIONS) + 1
print("\nENDPOINT-CONSISTENCY-SELFTEST: %d/%d" % (ok, total))
sys.exit(0 if ok == total else 1)
