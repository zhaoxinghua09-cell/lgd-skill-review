# S7 独立复跑包（outsider pack）

**这份东西是给一个与本项目无关的人用的。** 我们的内部审查已经做过一轮，但内部的人跑出来的结果按证据纪律只能算"同操作者干跑"，不能记作外部实测。所以这里只做一件事：把复跑成本压到 10 分钟以内，让外部的人能自己跑、自己出回执，不需要我们提供任何帮助。

## 你不需要相信我们

包里钉死了四个 40 位 commit。你拉的是那四个状态，不是 `main`。任何一行文件内容变了，你算出的 sha256 就会和 `pins.json` 对不上，脚本会直接判 FAIL。

## 你要做的事（三条命令）

```bash
git clone https://github.com/zhaoxinghua09-cell/lgd-skill-review
cd lgd-skill-review/outsider

# 1. 先看每个包钉的是哪个 commit（不下载，只读清单）
cat pins.json

# 2. 跑（Python 3.9+，只用标准库，不装依赖，不需要 GitHub token）
python s7_run.py --runner "你的姓名" --affiliation "你的单位" \
  --gh-user "你的 GitHub 用户名" --relationship "与本项目无利益关系" \
  --out my_receipt.json

# 3. 看结果（PASS 才会 exit 0）
cat my_receipt.json
```

**耗时**：四个仓库合计约 4 MB，克隆 1–2 分钟；四次 demo 各不到 1 秒；链接探测约 1 分钟（首次超时会自动重试一次）。合计 5–10 分钟。

**它会做什么**：按 commit 拉四个包 → 记录 `SKILL.md` / `README.md` 的字节数与 sha256 → 跑各包 `demo/` 下的自证脚本并记退出码 → 探测 `SKILL.md` 与 `README.md` 里每条链接的 HTTP 状态。

**它不会做什么**：不写任何仓库、不推 commit、不读你的凭据、不发网络请求到我们这边（除 GitHub 与链接本身）。

## 回执里有什么（`receipt_schema`）

| 字段 | 含义 | 怎么判 |
|---|---|---|
| `runner` / `affiliation` / `github_username` | 你自报的身份 | 须可核验；与仓库协作者列表对不上才算外人 |
| `runner_collaborator` | 你是不是仓库协作者 | **必须 `false`**；是协作者就不算外人 |
| `owner_self_run` | 是否 owner 一方干跑 | 必须 `false`；`true` 的回执我们不会当外部实测 |
| `items[].commit` | 40 位 sha | 必须等于 `pins.json` 里的值 |
| `items[].head_matches` | 拉下来的 HEAD 是否等于钉死值 | 必须 `true` |
| `items[].files[].sha256` | 关键文件哈希 | 与 `pins.json` 对照，不一致即判 FAIL |
| `items[].demo.rc` | 自证脚本退出码 | 必须 `0` |
| `links[].status` / `content_matched` | 每条链接的实测结果 | 必须 `200` 且内容命中 |
| `verdict` | 脚本自动判 | `PASS` 才往下走 |

## 我们希望你怎么用这份回执

1. **可以公开**：回执里没有你的账户信息，只有你自己填的名字与单位；公布与否由你决定。
2. **可以骂**：如果某项 FAIL，请把 FAIL 的那一行原样贴出来。我们要的是能改的东西，不是好评。
3. **不要替我们改**：发现包有问题请开 issue 或写信告诉我们，不要直接改代码——我们不想让"外部实测"变成"外部编写"。

## 我们不会拿你的回执说什么

- 不会说"已获第三方认证"——这是你自己跑的一次复现，不是认证。
- 不会说"社区认可"——一个人跑通不等于社区认可。
- 不会把你的名字放进任何对外主张里，除非你书面同意。

## 已知的缺口（先告诉你，省得你替我们发现）

- 四个包的 demo 只验证包自身的自证逻辑，**不验证它们的模型输出质量**；后者需要真实调用模型，不在本包范围内。
- 安装量为个位数，`skills.sh` 的 sitemap 尚未收录；这是分发问题，不是质量问题，本包不做解释。
- 本包不含任何红队用例；红队是我们内部跑的，外部若想复跑请向我们要用例清单。

---

维护：zhaoxinghua09-cell · 本文件与 `s7_run.py`、`pins.json` 同批提交，改任一文件须三者同批。
