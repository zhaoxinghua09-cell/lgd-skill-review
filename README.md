# lgd-skill-review · 技能审计官

Agent 技能六维审计器：每一处扣分都必须给出证据，输出分数、阻断项与整改顺序，作者或 AI 可据此整改、复评、再提高。这是我们做「权威评测」的引擎。

A six-dimension auditor for agent skills: every deduction must cite evidence, and every package gets a score, a blocker list and a remediation order — so an author (or an agent) can fix, re-run and raise the score.

## 快速开始 / Quick start

```bash
git clone https://github.com/zhaoxinghua09-cell/lgd-skill-review.git
cd lgd-skill-review
python scripts/review.py <package-dir> --run
python scripts/review.py <package-dir> --run --focus declared-consistency
python tests/run_golden.py
```

## 为什么可信 / Why it is checkable

- 黄金集 5 cases，`python tests/run_golden.py` 会真实执行并给出退出码（不靠自述）。
- 差异化点：declared-CLI vs implemented-CLI consistency。
- 零依赖、离线、零凭据：仅标准库，不发网络请求。

## AI 发现层 / AI discovery layer

- `llms.txt` — 面向 AI Agent 的能力与触发条件说明（双语）。
- `AI-INDEX.json` — 机器可读索引（schema `lgd.ai-index/1`）。
- 六维审计通过后登记于爆款清单：https://github.com/zhaoxinghua09-cell/lgd-hit-list

## 同族技能 / Family

- [summarize-pro](https://github.com/zhaoxinghua09-cell/summarize-pro) — 会议纪要专家
- [debug-pro](https://github.com/zhaoxinghua09-cell/debug-pro) — 排障专家
- [wechat-viral-topic](https://github.com/zhaoxinghua09-cell/wechat-viral-topic) — 公众号选题专家

---

