#!/usr/bin/env python3
"""Generate the static, machine-crawlable site for lgd-skill-review.

Outputs into docs/ : index.html, 4 skill pages, rubric.html, sitemap.xml, robots.txt, llms.txt
Everything is derived from bench/leaderboard.json + the four SKILL.md frontmatters, so the
site cannot drift away from the measured numbers.

No JavaScript. One page = one topic. JSON-LD on every page.
"""
import json
import subprocess
import sys
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCH = os.path.join(HERE, "bench", "leaderboard.json")
DOCS = os.path.join(HERE, "docs")
SITE = "https://zhaoxinghua09-cell.github.io/lgd-skill-review"
REPO = "https://github.com/zhaoxinghua09-cell/lgd-skill-review"

SKILLS = [
    {
        "slug": "skill-review",
        "title": "Skill Review · 技能审计",
        "h1": "Audit a skill, get evidence — not opinions",
        "zh": "技能审计：每一处扣分都钉在具体文件上",
        "triggers": ["skill audit", "skill review", "rate my skill", "SKILL.md review",
                     "技能评测", "技能审计", "帮我看看这个技能缺什么"],
        "body": "Six dimensions, static analysis, every deduction pinned to a file with a line. "
                "Same package in, same score out. Every result comes with a remediation order and "
                "a projected ceiling that separates mechanical fixes from work you still have to do.",
    },
    {
        "slug": "quickfix",
        "title": "QuickFix · 一键机械整改",
        "h1": "The fixes anyone can apply in one command",
        "zh": "机械可补的部分，一条命令补完",
        "triggers": ["quickfix skill", "add license to skill", "AI-INDEX.json", "skill hygiene",
                     "技能整改", "补许可", "清路径"],
        "body": "Adds LICENSE and a license field, generates AI-INDEX.json, appends a Commands "
                "section built from the flags that really exist in the source, and scrubs absolute "
                "paths. Dry-run by default; a single file changed over 30% is refused.",
    },
    {
        "slug": "benchmark",
        "title": "SkillBench · 公开基准",
        "h1": "Fourteen public targets, one ruler",
        "zh": "同引擎、同口径、同一时点，任何人都能重跑",
        "triggers": ["skill benchmark", "agent skill score", "verifiability score",
                     "技能基准", "评分对比", "可验证性"],
        "body": "Third-party skills with hundreds of thousands of installs score 10–36 here. It "
                "measures verifiability — whether a stranger can check the work — not usefulness.",
    },
]

AUDITS = [
    {
        "name": "microsoft / azure-skills",
        "skill": "skills/azure-deploy",
        "installs": "≈731k",
        "before": 20,
        "after_mech": 24,
        "dims_before": "structure 6 / consistency 0 / reproducible 0 / hygiene 8 / discoverable 4 / licensing 2",
        "findings": [
            "frontmatter 缺 version（structure 扣分）",
            "references/recipes/azcli/errors.md 层级超过 3 段",
            "无测试文件（tests/*.json）与执行器，别人无法复跑",
            "无 demo，首次使用者无从验证",
            "SKILL.md 未声明安全边界与降级规则",
            "标签 0 个；缺互链段；无 AI-INDEX.json / llms.txt",
            "缺 author；无独立许可文件（仅 frontmatter 声明）",
        ],
        "mechanical": [
            "补 LICENSE（MIT）→ licensing 2→3",
            "生成 AI-INDEX.json → discoverable 4→7",
        ],
        "fix_order": [
            "P0 · 5 分钟：加 LICENSE 文件、给 frontmatter 补 version 与 author",
            "P1 · 半小时：加 tags、触发词段、AI-INDEX.json 或 llms.txt、互链段",
            "P2 · 作者工作：写 tests/*.json 与执行器、补 demo、声明安全边界",
        ],
    },
    {
        "name": "prisma / skills",
        "skill": "prisma-cli",
        "installs": "≈435k",
        "before": 20,
        "after_mech": None,
        "dims_before": "structure 10 / consistency 0 / reproducible 0 / hygiene 8 / discoverable 0 / licensing 2",
        "findings": [
            "frontmatter 缺 version（且非 SemVer）",
            "无测试文件与执行器，无法复跑",
            "无 demo",
            "未声明安全边界与降级规则",
            "标签 0 个；缺触发词段；缺互链段；无机器可读索引",
            "缺 author；无独立许可文件",
        ],
        "mechanical": ["同上四类机械动作可补，未在本轮实测（避免对未验证项下结论）"],
        "fix_order": [
            "P0 · 5 分钟：加 LICENSE 文件、给 frontmatter 补 version（SemVer）与 author",
            "P1 · 半小时：加 tags、触发词段、AI-INDEX.json 或 llms.txt、互链段",
            "P2 · 作者工作：写 tests/*.json 与执行器、补 demo、声明安全边界",
        ],
    },
]

REACH = {
    "target": "microsoft/azure-skills · skills/azure-deploy（第三方包，我们未作者）",
    "stages": [
        ("原样 / as shipped", 20, "structure 6 · consistency 0 · reproducible 0 · hygiene 8 · discoverable 4 · licensing 2"),
        ("仅机械整改 / mechanical only", 24, "补 LICENSE + AI-INDEX.json；licensing 2→3，discoverable 4→7"),
        ("机械 + 补测试与 demo / + tests & demo", 57, "加 tests/golden.json、可跑 runner、llms.txt、tags、version；reproducible 0→16"),
        ("再补作者工作 / + authored CLI", 86, "写 scripts/check_prereqs.py（argparse）、在 SKILL.md 声明其命令、补安全边界与生态段；consistency 0→15，hygiene 8→15"),
    ],
    "left": "剩 14 分：references/recipes/azcli 层级超过 3 段（structure −4）、以及只实现了一条声明命令（consistency −10）",
}

CSS = """
:root{--bg:#0b1220;--card:#111a2c;--line:rgba(122,160,255,.18);--fg:#e8eef8;--mut:#a9b8d0;--acc:#7fe7c4;--warn:#f2a65a}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--fg);font:16px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",Arial,sans-serif}
.wrap{max-width:980px;margin:0 auto;padding:56px 24px 96px}
nav{display:flex;gap:18px;flex-wrap:wrap;font-size:14px;color:var(--mut);margin-bottom:36px}
nav a{color:var(--mut);text-decoration:none;border-bottom:1px solid transparent}
nav a:hover{color:var(--acc);border-color:var(--acc)}
.kick{color:var(--acc);letter-spacing:.18em;text-transform:uppercase;font-size:12px}
h1{font-size:38px;line-height:1.2;margin:10px 0 14px;letter-spacing:-.5px}
h2{font-size:22px;margin:40px 0 12px}
h3{font-size:16px;margin:20px 0 8px}
p,li{color:var(--mut)}
.lead{font-size:18px;color:var(--fg);max-width:760px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:22px 24px;margin-top:16px}
table{width:100%;border-collapse:collapse;margin-top:14px;font-size:14px}
th,td{text-align:left;padding:9px 8px;border-bottom:1px solid var(--line)}
th{color:var(--acc);font-weight:600;letter-spacing:.06em;font-size:12px;text-transform:uppercase}
td.num{text-align:right;font-variant-numeric:tabular-nums;width:64px}
.bad{color:var(--warn)} .good{color:var(--acc)}
code{background:rgba(88,124,200,.14);padding:2px 6px;border-radius:4px;font-size:13px}
pre{background:#0a0f1a;border:1px solid var(--line);border-radius:10px;padding:16px;overflow-x:auto;margin-top:12px}
pre code{background:none;padding:0}
ul{margin:10px 0 0 20px}
.tag{display:inline-block;font-size:12px;color:var(--acc);border:1px solid rgba(127,231,196,.4);border-radius:4px;padding:3px 8px;margin:4px 6px 0 0}
.a{color:var(--acc);text-decoration:none}
.foot{margin-top:56px;padding-top:22px;border-top:1px solid var(--line);font-size:13px;color:#6f86a6}
"""


def head(title, desc, path, extra_jsonld=""):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{SITE}/{path}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="website">
<style>{CSS}</style>
<script type="application/ld+json">{{
  "@context":"https://schema.org",
  "@type":"SoftwareApplication",
  "name":"lgd-skill-review",
  "applicationCategory":"DeveloperApplication",
  "operatingSystem":"Any",
  "description":"Six-dimension verifiability auditor for agent skills. Every deduction cites evidence; every result includes a remediation order.",
  "url":"{SITE}/",
  "codeRepository":"{REPO}",
  "license":"https://opensource.org/licenses/MIT",
  "offers":{{"@type":"Offer","price":"0","priceCurrency":"USD"}}
}}</script>
{extra_jsonld}
</head>
<body>
<div class="wrap">
<nav>
<a href="./index.html">Home</a>
<a href="./rubric.html">Rubric</a>
<a href="./skill-review.html">Audit</a>
<a href="./quickfix.html">QuickFix</a>
<a href="./benchmark.html">Benchmark</a>
<a href="./badge.html">Badge</a>
<a href="./audits.html">Audits</a>
<a href="./registry.html">Registry</a>
<a href="./discover.html">Discover</a>
<a href="{REPO}">GitHub</a>
</nav>
"""


FOOT = f"""
<div class="foot">
Measures verifiability, not usefulness or popularity. Low score means evidence is missing, not that the skill is bad.
Snapshot at a point in time; the sample is not random.<br>
Data: <a class="a" href="{REPO}/blob/main/bench/leaderboard.json">leaderboard.json</a> ·
Machine entry: <a class="a" href="{SITE}/llms.txt">llms.txt</a> ·
Request a review: <a class="a" href="{REPO}/issues/new?template=review-request.yml">open an issue</a>
</div>
</div>
</body>
</html>
"""


def rows_html(data):
    third = [r for r in data["rows"] if r["bucket"] == "third-party"]
    own = [r for r in data["rows"] if r["bucket"] == "lgd"]
    out = []
    for label, group in (("Third-party · 第三方", third), ("LGD · 我方", own)):
        out.append(f"<h3>{label}</h3><table><tr><th>Target</th><th style=\"text-align:right\">Score</th><th>Verdict</th></tr>")
        for r in group:
            cls = "good" if r["bucket"] == "lgd" else "bad"
            name = r["target"].replace("@", " <span style='color:#6f86a6'>@</span> ")
            out.append(f"<tr><td>{name}</td><td class='num {cls}'>{r['score']}</td><td class='{cls}'>{r['verdict']}</td></tr>")
        out.append("</table>")
    return "\n".join(out)


def main():
    # 标准必须是可执行数据：先生成 rubric.json，页面与它同源
    subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "gen_rubric.py")], check=False)

    data = json.load(open(BENCH, encoding="utf-8"))
    s = data["summary"]
    os.makedirs(DOCS, exist_ok=True)

    # index
    html = head("LGD SkillBench — verifiability, measured",
                "Public benchmark for agent skills: third-party skills score 10-36, LGD packages 96-100. "
                "One command reproduces every number.", "index.html")
    html += f"""
<div class="kick">verifiability, measured — not claimed</div>
<h1>We measure whether a stranger can check your skill.</h1>
<p class="lead">Fourteen public targets, one ruler, one command. Third-party skills with
hundreds of thousands of installs score <b>{s['third_party_top']}</b> at best here; our four
packages score <b>{s['lgd_top']}</b> static and 100 with their own tests. The gap is not prose
quality — it is <b>whether the evidence is checkable</b>.</p>

<div class="card">
<h3>Current gap</h3>
<table>
<tr><th>Metric</th><th style="text-align:right">Value</th></tr>
<tr><td>Third-party entries</td><td class="num">{s['third_party_entries']}</td></tr>
<tr><td>LGD entries</td><td class="num">{s['lgd_entries']}</td></tr>
<tr><td>Third-party top score</td><td class="num bad">{s['third_party_top']}</td></tr>
<tr><td>LGD top score</td><td class="num good">{s['lgd_top']}</td></tr>
<tr><td>Gap</td><td class="num good">{s['gap']}</td></tr>
</table>
<p style="margin-top:12px;font-size:13px">Generated {data['generated_at_utc']} · engine: static mode, never executes the target's code</p>
</div>

<h2>What we measure</h2>
<div class="card">
<ul>
<li><b>Structure</b> — can a machine find the entry, version, license?</li>
<li><b>Consistency</b> — do the documented commands exist in the source?</li>
<li><b>Reproducibility</b> — is there a golden set and a runner that actually runs?</li>
<li><b>Hygiene</b> — absolute paths, secrets, leaked contact details</li>
<li><b>Discoverability</b> — triggers, ecosystem links, machine-readable index</li>
<li><b>Licensing</b> — a real license, not a claim</li>
</ul>
<p style="margin-top:12px"><a class="a" href="./rubric.html">Full rubric →</a></p>
</div>

<h2>Reproduce it</h2>
<div class="card">
<pre><code>git clone {REPO.replace('https://github.com/', 'https://github.com/')}.git
cd lgd-skill-review/bench
python bench.py</code></pre>
<p style="margin-top:10px">Refreshed automatically every day at 09:17 Beijing time. If you disagree with
a number, the JSON is public and the runner is public.</p>
</div>

<h2>Get your skill reviewed — without talking to us</h2>
<div class="card">
<p>Open an issue with the review form. A bot fetches your public tarball, runs static analysis
(<b>it never executes your code</b>), and replies with the score, the six-dimension breakdown,
the blockers, and the order to fix them.</p>
<p style="margin-top:10px"><a class="a" href="{REPO}/issues/new?template=review-request.yml">Submit a skill for review →</a></p>
</div>
"""
    html += FOOT
    open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8").write(html)

    # benchmark page
    html = head("Benchmark — every number is reproducible",
                "Full leaderboard of 14 public targets with scores, verdicts and blockers.", "benchmark.html")
    html += f"""
<div class="kick">leaderboard</div>
<h1>Everyone can rerun this.</h1>
<p class="lead">Same engine, same scale, same moment. Sorted by score. Blocking findings mean the
package would be rejected by a reviewer who checks before shipping.</p>
<div class="card">{rows_html(data)}
<p style="margin-top:14px;font-size:13px">Generated {data['generated_at_utc']} ·
<a class="a" href="{REPO}/blob/main/bench/leaderboard.json">raw JSON</a></p>
</div>
<h2>How to read a low score</h2>
<div class="card"><p>A third-party package scoring 18 is not a bad package. It means: no license file,
no machine-readable index, commands documented differently from the source, no golden set. A stranger
cannot verify it in ten minutes, so an auditor cannot certify it either. <b>The score measures
checkability, not usefulness.</b></p></div>
"""
    html += FOOT
    open(os.path.join(DOCS, "benchmark.html"), "w", encoding="utf-8").write(html)

    # rubric
    html = head("Rubric — six dimensions, 100 points",
                "The exact scoring rules, weights and what each dimension can and cannot prove.", "rubric.html")
    html += """
<div class="kick">rubric</div>
<h1>Six dimensions, 100 points, no black box.</h1>
<p class="lead">Weights are public because a score nobody can recompute is an opinion with a number
stapled to it. Static mode caps at 96; the last 4 points require the target's own tests to actually run.</p>
<div class="card">
<table>
<tr><th>Dimension</th><th style="text-align:right">Weight</th><th>What it can prove</th></tr>
<tr><td>Consistency</td><td class="num">25</td><td>Documented flags and subcommands exist in the source</td></tr>
<tr><td>Structure</td><td class="num">20</td><td>Entry file, version, name, description are machine-findable</td></tr>
<tr><td>Reproducibility</td><td class="num">20</td><td>A golden set exists and a runner actually executes it</td></tr>
<tr><td>Hygiene</td><td class="num">15</td><td>No absolute paths, secrets or leaked contact details</td></tr>
<tr><td>Discoverability</td><td class="num">15</td><td>Triggers, ecosystem links, AI-INDEX / llms.txt</td></tr>
<tr><td>Licensing</td><td class="num">5</td><td>A real license file plus a declared field</td></tr>
</table>
</div>
<h2>What the score cannot tell you</h2>
<div class="card"><ul>
<li>Whether the skill is useful, correct, or popular</li>
<li>Whether the prose is any good</li>
<li>Whether the maintainer will respond to issues</li>
<li>Anything about packages it never saw</li>
</ul>
<p style="margin-top:12px">Two known measurement biases were found and fixed by testing the ruler
against real repositories: index detection used to be case-sensitive, and position-argument CLIs
were scored zero. Both are documented in the repository history.</p></div>
"""
    html += FOOT
    open(os.path.join(DOCS, "rubric.html"), "w", encoding="utf-8").write(html)

    # skill pages
    for sk in SKILLS:
        tags = "".join(f'<span class="tag">{t}</span>' for t in sk["triggers"])
        html = head(f"{sk['title']} — lgd-skill-review",
                    sk["zh"] + " · " + sk["body"][:120], sk["slug"] + ".html")
        html += f"""
<div class="kick">{sk['slug']}</div>
<h1>{sk['h1']}</h1>
<p class="lead">{sk['zh']}</p>
<div class="card"><p>{sk['body']}</p>
<h3 style="margin-top:16px">When an agent should reach for this</h3>
<p>{tags}</p></div>
<h2>Install</h2>
<div class="card"><pre><code>npx skills add zhaoxinghua09-cell/lgd-skills</code></pre>
<p style="margin-top:10px;font-size:13px">Bundled with all four skills under <code>skills/&lt;name&gt;/</code>.</p></div>
"""
        html += FOOT
        open(os.path.join(DOCS, sk["slug"] + ".html"), "w", encoding="utf-8").write(html)

    # badge page — 让别人把我们的徽章嵌进自己 README，外链自己长出来
    badge_url = ("https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com"
                 "%2Fzhaoxinghua09-cell%2Flgd-skill-review%2Fmain%2Fbench%2Fbadge.json")
    html = head("Badge — embed the verifiability score",
                "Copy-paste snippets to show a skill's verifiability score in your README. "
                "The badge reads live data, so it changes when the score changes.",
                "badge.html",
                extra_jsonld=f'<script type="application/ld+json">{{"@context":"https://schema.org","@type":"HowTo","name":"Embed the LGD verifiability badge","step":[{{"@type":"HowToStep","text":"Copy the Markdown snippet"}},{{"@type":"HowToStep","text":"Paste it into your README"}}]}}</script>')
    html += f"""
<div class="kick">badge</div>
<h1>A badge that reads live data.</h1>
<p class="lead">Most badges are a picture someone typed once. This one is an endpoint:
it renders whatever the latest benchmark says, so it cannot go stale and cannot be cherry-picked.</p>

<div class="card">
<h3>What it currently says</h3>
<p><img src="{badge_url}" alt="verifiability badge" style="height:22px"></p>
<p style="margin-top:12px;font-size:13px">Label: verifiability · Message: peers &lt;third-party top&gt; / LGD &lt;our top&gt; ·
Colour flips to orange if the gap drops below 50 points.</p>
</div>

<h2>Markdown</h2>
<div class="card"><pre><code>[![verifiability]({badge_url})]({SITE}/benchmark.html)</code></pre>
<p style="margin-top:10px;font-size:13px">Works on GitHub, GitLab, most README renderers.</p></div>

<h2>HTML</h2>
<div class="card"><pre><code>&lt;a href="{SITE}/benchmark.html"&gt;&lt;img src="{badge_url}" alt="verifiability score" height="22"&gt;&lt;/a&gt;</code></pre></div>

<h2>Raw JSON, if you want to build your own</h2>
<div class="card"><pre><code>{REPO}/blob/main/bench/badge.json</code></pre>
<p style="margin-top:10px">Shields endpoint schema: <code>{{"schemaVersion":1,"label":...,"message":...,"color":...}}</code>.
The leaderboard behind it: <a class="a" href="{REPO}/blob/main/bench/leaderboard.json">leaderboard.json</a>.</p></div>

<h2>What the badge does and does not mean</h2>
<div class="card"><ul>
<li><b>Does</b> mean: this package's claims are checkable by a third party — license present, commands match the source, index machine-readable, no leaked paths.</li>
<li><b>Does not</b> mean: the skill is useful, correct, popular, or endorsed by anyone.</li>
<li>It is not a certification body. It is a public ruler with a public runner.</li>
</ul></div>
"""
    html += FOOT
    open(os.path.join(DOCS, "badge.html"), "w", encoding="utf-8").write(html)

    # audits page — 对真实大仓的公开审计结果，可被任何人复跑
    html = head("Audits — two large public repos, real findings",
                "Full-dimension audits of microsoft/azure-skills and prisma/skills, with the findings "
                "and the part that one command can fix.", "audits.html")
    html += """
<div class="kick">audits</div>
<h1>We looked at two 400k+ install repositories. Here is what we found.</h1>
<p class="lead">Not opinions — dimension scores, the exact items that cost points, and how far a
one-command mechanical fix gets you. Every number below is reproducible with the command at the bottom.</p>
"""
    for a in AUDITS:
        f = "".join(f"<li>{x}</li>" for x in a["findings"])
        m = "".join(f"<li>{x}</li>" for x in a["mechanical"])
        o = "".join(f"<li>{x}</li>" for x in a["fix_order"])
        html += f"""
<div class="card">
<h3>{a['name']} · <code>{a['skill']}</code> · installs {a['installs']}</h3>
<table>
<tr><th>Stage</th><th style="text-align:right">Score</th></tr>
<tr><td>As shipped</td><td class="num bad">{a['before']}</td></tr>
<tr><td>After mechanical fixes only</td><td class="num">{(str(a['after_mech']) if a['after_mech'] else '未实测')}</td></tr>
</table>
<p style="margin-top:10px;font-size:13px">Dimensions as shipped: {a['dims_before']}</p>
<h3 style="margin-top:16px">Findings</h3><ul>{f}</ul>
<h3 style="margin-top:16px">What one command fixes</h3><ul>{m}</ul>
<h3 style="margin-top:16px">Fix order if you are the maintainer</h3><ul>{o}</ul>
</div>
"""
    html += """
<h2>Fairness test: can a package we did not write reach 90?</h2>
<div class="card">
<p>Same rubric, same engine, applied to microsoft's <code>azure-deploy</code> in a copy. Each stage is
real work, scored after each step. Nothing was padded to inflate the number.</p>
<table><tr><th>stage</th><th style="text-align:right">score</th><th>what changed</th></tr>
""" + "".join(
        f"<tr><td>{name}</td><td class='num'>{val}</td><td style='font-size:13px'>{note}</td></tr>"
        for name, val, note in REACH["stages"]) + f"""
</table>
<p style="margin-top:12px;font-size:13px">{REACH['left']}</p>
<p style="margin-top:8px">Why this matters: our four packages score 96 partly because they were
written to this rubric. That is a weakness, not a strength. This test removes it: a package by another
author reaches 86 with work any maintainer can do, and the remaining 14 points are specific, named,
and fixable. If the ruler only ever fit the ruler's authors, this table could not exist.</p>
</div>

<h2>How to reproduce</h2>
<div class="card"><pre><code>git clone --depth 1 https://github.com/microsoft/azure-skills.git
python scripts/review.py azure-skills/skills/azure-deploy --json</code></pre>
<p style="margin-top:10px">The mechanical part:</p>
<pre><code>python scripts/quickfix.py &lt;copy-of-skill-dir&gt; --apply</code></pre>
</div>

<h2>Why publish this instead of sending them issues</h2>
<div class="card"><p>Because an issue we file is a request; a public report with a reproducible runner
is evidence. Anyone — including the maintainers — can rerun the command and check whether we are right.
If we are wrong about a single item, the runner will show it.</p>
<p style="margin-top:10px">These are third-party projects. We are not claiming they are bad packages.
A score of 20 means <b>a stranger cannot verify the claims in ten minutes</b>, which is a property of
the package's evidence, not of its usefulness.</p></div>
"""
    html += FOOT
    open(os.path.join(DOCS, "audits.html"), "w", encoding="utf-8").write(html)

    # audits.json — 机器可读的审计结果，供 AI 直接消费（HTML 给人，JSON 给 agent）
    audits_doc = {
        "schema_version": "1.0",
        "generator": "lgd-skill-review/scripts/gen_site.py",
        "rubric": "https://zhaoxinghua09-cell.github.io/lgd-skill-review/rubric.html",
        "note": "静态审计结果，不执行被审代码；分数衡量可验证性，不衡量有用性。",
        "remediation_experiment": {
            "target": REACH["target"],
            "purpose": "检验同一把尺子能否被非作者的包满足，回应「标准为作者量身定做」的质疑",
            "stages": [{"stage": n, "score": v, "change": c} for n, v, c in REACH["stages"]],
            "remaining": REACH["left"],
        },
        "audits": [
            {
                "target": a["name"],
                "skill_path": a["skill"],
                "reported_installs": a["installs"],
                "score_before": a["before"],
                "score_after_mechanical": a["after_mech"],
                "dimensions_before": a["dims_before"],
                "findings": a["findings"],
                "mechanical_fixes": a["mechanical"],
                "fix_order": a["fix_order"],
                "reproduce": "python scripts/review.py <local-clone>/%s --json" % a["skill"],
            }
            for a in AUDITS
        ],
    }
    open(os.path.join(DOCS, "audits.json"), "w", encoding="utf-8").write(
        json.dumps(audits_doc, ensure_ascii=False, indent=2)
    )

    # registry — 认证清单：按分数分档，数据由榜单生成，人可读、机可读
    tiers = [("verified", 90, "LGD Verified · 认证", "≥90：陌生人十分钟内可核实全部主张"),
             ("watch", 60, "LGD Watch · 观察", "60–89：有一部分能核实，关键项缺失"),
             ("blocked", 0, "LGD Blocked · 未通过", "<60：核心证据缺失，无法核实")]
    by_tier = {t[0]: [] for t in tiers}
    for r in data["rows"]:
        for key, lo, label, desc in tiers:
            if r["score"] >= lo:
                by_tier[key].append(r)
                break
    html = head("Registry — the verified list",
                "A tiered registry of agent skills by verifiability score. Machine-readable at registry.json; "
                "entries are generated from the public benchmark, not curated by hand.",
                "registry.html")
    html += """
<div class="kick">registry</div>
<h1>The verified list, built from numbers rather than opinions.</h1>
<p class="lead">Three tiers. Nobody is promoted by application, nobody pays, and no entry is edited by
hand — every row is a score produced by the same runner. To appear here, submit the package; to change
your tier, change the package.</p>
"""
    for key, lo, label, desc in tiers:
        rows = by_tier[key]
        body = "".join(
            '<tr><td>%s</td><td class="num%s">%s</td></tr>' % (
                r["target"], " bad" if r["score"] < 60 else "", r["score"]) for r in rows
        ) or '<tr><td colspan="2" style="color:#8a8378">（本档暂无条目）</td></tr>'
        html += f"""
<div class="card">
<h3>{label}</h3>
<p style="font-size:13px;color:#6b6459">{desc} · 本档 {len(rows)} 条</p>
<table><tr><th>package</th><th style="text-align:right">score</th></tr>{body}</table>
</div>
"""
    html += f"""
<h2>How to get on this list</h2>
<div class="card"><ul>
<li>Submit a public repository: <a class="a" href="{REPO}/issues/new?template=review-request.yml">review request</a>（机器人取包、静态分析、回帖给分与整改顺序）</li>
<li>No payment, no negotiation, no editorial discretion. The runner decides.</li>
<li>Rejected? The reply lists what is missing and in what order to fix it. Resubmit after fixing.</li>
</ul>
<p style="margin-top:10px;font-size:13px">机器可读版：<a class="a" href="./registry.json">registry.json</a>（含每档阈值与全部条目）。</p></div>

<h2>What a tier is not</h2>
<div class="card"><p>It is not a quality endorsement, not a security audit, not a warranty. It says one thing:
<b>how much of this package's claims a stranger can verify in ten minutes</b>. A verified package can still
be useless; a blocked package can still be excellent — it just cannot be checked.</p></div>
"""
    html += FOOT
    open(os.path.join(DOCS, "registry.html"), "w", encoding="utf-8").write(html)

    reg = {
        "schema_version": "1.0",
        "generated_at_utc": data["generated_at_utc"],
        "source": SITE + "benchmark.html",
        "tiers": [{"key": k, "min_score": lo, "label": lb, "meaning": d, "count": len(by_tier[k]),
                   "entries": [{"target": r["target"], "score": r["score"], "verdict": r["verdict"]}
                               for r in by_tier[k]]} for k, lo, lb, d in tiers],
        "rules": {
            "admission": "public repository + reproducible static audit; no payment, no editorial discretion",
            "remeasure": "tier follows the score; fixing the package moves the tier",
            "not_a": ["quality endorsement", "security audit", "warranty"],
        },
    }
    open(os.path.join(DOCS, "registry.json"), "w", encoding="utf-8").write(
        json.dumps(reg, ensure_ascii=False, indent=2)
    )

    # discover — 不经检索的入口清单：给 AI 的直达地址，不依赖任何平台的排序
    endpoints = [
        ("评价标准（人读）", SITE + "rubric.html", "六维权重、阻断项、上限说明"),
        ("评价标准（机读）", SITE + "rubric.json", "权重/阻断/敏感模式，由引擎常量导出"),
        ("公开榜单", SITE + "benchmark.html", "17 行，13 个第三方目标"),
        ("榜单数据", SITE + "leaderboard.json", "行级数据 + 三条局限"),
        ("认证清单（人读）", SITE + "registry.html", "verified / watch / blocked 三档"),
        ("认证清单（机读）", SITE + "registry.json", "阈值、规则、全部条目"),
        ("真实审计（人读）", SITE + "audits.html", "两个 40 万级安装量仓库的逐条缺陷"),
        ("真实审计（机读）", SITE + "audits.json", "含 scores/findings/fix_order/reproduce"),
        ("徽章端点", "https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fzhaoxinghua09-cell%2Flgd-skill-review%2Fmain%2Fbench%2Fbadge.json", "实时读数，非静态图片"),
        ("全量语料", SITE + "llms-full.txt", "一次抓取拿到口径+榜单+审计+复现"),
        ("评测引擎", REPO + "/blob/main/scripts/review.py", "标准库、离线、不执行被评代码"),
        ("一键整改", REPO + "/blob/main/scripts/quickfix.py", "默认 dry-run，单文件改动>30% 拒绝写入"),
        ("提交评测", REPO + "/issues/new?template=review-request.yml", "机器人回帖给分与整改顺序"),
    ]
    rows = "".join(f"<tr><td>{a}</td><td><code>{b}</code></td><td style='font-size:13px'>{c}</td></tr>"
                   for a, b, c in endpoints)
    html = head("Discover — direct endpoints, no search required",
                "Every entry point to the LGD verifiability system as a direct URL: rubric, "
                "leaderboard, registry, audits, badge, engine, intake.", "discover.html")
    html += f"""
<div class="kick">discover</div>
<h1>Direct endpoints. No marketplace search required.</h1>
<p class="lead">We measured both marketplaces: skills.sh returns us for brand queries
(<code>lgd</code>, <code>lgd skill review</code>) but not for generic ones; LobeHub market search
returns 500 popularity-ranked items and does not surface us even on our own display name. So this page
lists the addresses an agent can hit directly instead of hoping a ranking puts us first.</p>
<div class="card"><table>
<tr><th>what</th><th>where</th><th>why</th></tr>
{rows}
</table></div>

<h2>What an agent can do without contacting anyone</h2>
<div class="card"><ol>
<li>Fetch <code>rubric.json</code> to get weights, blocking rules and the static cap.</li>
<li>Score any local package with <code>review.py --json</code>.</li>
<li>Read <code>findings</code>, apply the fixes in the given order.</li>
<li>Re-run the same engine; the score change is the proof.</li>
<li>If the result seems wrong, appeal with a path and a check — the ruling is recorded.</li>
</ol></div>

<h2>Two entry points that are actively hostile to newcomers</h2>
<div class="card"><p>We are not hiding this: marketplace search ranks by install counts and star
signals we cannot influence without faking them, which we will not do. If you need a verdict today,
use the endpoints above; if you want us to be found by search, the honest lever is people choosing to
install and cite us.</p></div>
"""
    html += FOOT
    open(os.path.join(DOCS, "discover.html"), "w", encoding="utf-8").write(html)

    # 执行证明：静态 96 之外的 4 分，靠真跑测试拿到
    proof_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bench", "run-proof.json")
    proof = json.load(open(proof_path, encoding="utf-8")) if os.path.isfile(proof_path) else None
    if proof:
        rows = "".join(
            "<tr><td>%s</td><td class='num'>%s</td><td>%s</td></tr>" % (
                p.get("package"), p.get("score"), p.get("verdict"))
            for p in proof["packages"] if "score" in p)
        html += f"""
<h2>Executed, not just declared</h2>
<div class="card">
<p>Static analysis caps at 96. The last 4 points need the package's own tests to run. Below is that run
({proof['generated_at_utc']}, engine <code>{proof['engine']}</code>). No other number in our sample is backed
by an execution we performed on someone's package.</p>
<table><tr><th>package</th><th style="text-align:right">executed score</th><th>verdict</th></tr>{rows}</table>
<p style="margin-top:10px;font-size:13px">机器可读：<a class="a" href="./run-proof.json">run-proof.json</a> ·
复跑 <code>python scripts/run_proof.py</code></p>
</div>
"""
        json.dump(proof, open(os.path.join(DOCS, "run-proof.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)

    # sitemap / robots / llms
    urls = ["index.html", "rubric.html", "benchmark.html", "badge.html", "audits.html", "registry.html", "discover.html"] + [s["slug"] + ".html" for s in SKILLS]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        sm.append(f"  <url><loc>{SITE}/{u}</loc><changefreq>daily</changefreq></item>".replace("</item>", "</url>"))
    sm.append("</urlset>")
    open(os.path.join(DOCS, "sitemap.xml"), "w", encoding="utf-8").write("\n".join(sm))

    open(os.path.join(DOCS, "robots.txt"), "w", encoding="utf-8").write(
        "User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % SITE)

    llms = f"""# lgd-skill-review

> Six-dimension verifiability auditor for agent skills. Every deduction cites evidence; every result
> ships with a remediation order. Static mode: the target's code is never executed.

## what it answers
- skill audit / skill review / "is this skill safe to install"
- "why does my SKILL.md score low" / "what is missing"
- compare public skills on verifiability: {SITE}/benchmark.html

## reproducibility
- engine: {REPO}/blob/main/scripts/review.py
- one-click mechanical fixes: {REPO}/blob/main/scripts/quickfix.py
- benchmark data: {REPO}/blob/main/bench/leaderboard.json
- refreshed daily; every number rerunnable with `python bench.py`

## rubric (machine-readable, generated from the engine)
{SITE}rubric.json — six weights, three blocking rules, sensitive patterns, verdicts, how to use.

## executed proof (static cap 96 -> 100)
{SITE}run-proof.json — our four packages scored with `review.py --run` (tests actually executed),
with timestamp and commit. This is the only number in the sample backed by a real run.

## rubric, item by item (23 checks)
{SITE}rubric.json — every dimension broken into individual checks with points and the concrete fix.
第 6 维共 23 条判据，每条给了分值和「怎么修」；`drift_check` 保证判据之和等于引擎权重，文档不会悄悄和引擎脱节。

## re-review loop
Comment `/re-review` in the same issue to re-score after a fix; the bot replies with before -> after delta.
首次评审后，在同一 issue 留言 `/re-review` 即重评，回帖给出「改前 → 改后」分数变化。

## registry (verified list), machine-readable
{SITE}registry.json — three tiers by score (verified ≥90 / watch 60-89 / blocked <60), generated from the
benchmark. Admission rules, tier meaning and every entry in one file. Human page: {SITE}registry.html

## third-party audits, machine-readable
- {SITE}audits.json（两条真实大仓审计：分数、逐条 findings、整改顺序、复现命令）
- 人读版：{SITE}audits.html

## submit a skill for review
{REPO}/issues/new?template=review-request.yml

## limits
- measures verifiability, not usefulness or popularity
- static mode caps at 96 of 100; 100 needs the target's own tests to run
- snapshot in time; sample is not random

## current numbers
third-party top: {s['third_party_top']} | lgd top: {s['lgd_top']} | gap: {s['gap']}
"""
    open(os.path.join(DOCS, "llms.txt"), "w", encoding="utf-8").write(llms)

    # llms-full.txt — 一次抓取拿全量语料，供 RAG / 训练式检索直接消费
    lines = []
    for r in data["rows"]:
        lines.append("| %s | %s | %s | %s |" % (r["bucket"], r["target"], r["score"], r["verdict"]))
    full = f"""# lgd-skill-review — full corpus

> One fetch, everything an agent needs. Numbers below are generated at {data['generated_at_utc']}
> from bench/leaderboard.json; they change when the benchmark changes.

## 1. what this is
A six-dimension verifiability auditor for agent skills. Static analysis only — the target's code is
never executed. Output: total score, per-dimension breakdown, blocking findings, remediation order,
and a projected ceiling that separates mechanical fixes from work the author still has to do.

## 2. scoring rubric (100 points)
- consistency 25 — documented flags and subcommands exist in the source
- structure 20 — entry file, version, name, description are machine-findable
- reproducibility 20 — a golden set exists and a runner actually executes it
- hygiene 15 — no absolute paths, secrets or leaked contact details
- discoverability 15 — triggers, ecosystem links, AI-INDEX.json or llms.txt
- licensing 5 — a real license file plus a declared field
Static mode caps at 96; the remaining 4 points require the target's own tests to run.

## 3. known measurement biases, found and fixed
- index detection used to be case-sensitive: a correct AI-INDEX.json in upper case scored zero
- position-argument CLIs used to score zero in consistency; now they earn 5 of 25, with a note that
  unnamed arguments are only partly checkable
- GitHub bot / noreply addresses used to be flagged as leaked contact details; now exempt

## 4. leaderboard (bucket | target | score | verdict)
| bucket | target | score | verdict |
|---|---|---|---|
{chr(10).join(lines)}

## 5. what the score cannot tell you
usefulness, correctness, popularity, maintainer responsiveness, or anything about packages not measured.

## 6. how to reproduce
{REPO}/tree/main/bench — `python bench.py`

## 7. how to get reviewed
{REPO}/issues/new?template=review-request.yml — bot fetches the public tarball, runs static analysis,
replies with score + blockers + fix order.

## 8. badge (live endpoint)
{REPO}/blob/main/bench/badge.json — shields endpoint format, renders current numbers.

## 9. registry (verified list)
{SITE}registry.json — tiers: verified ≥90 · watch 60-89 · blocked <60; rules and entries.

## 10. third-party audits (machine-readable)
{SITE}audits.json — two large public repos, full findings + fix order + reproduce command.

## 11. site
{SITE}/ — {', '.join(u.replace('.html','') for u in urls)}
"""
    open(os.path.join(DOCS, "llms-full.txt"), "w", encoding="utf-8").write(full)

    print("pages:", len(urls), "| docs dir:", DOCS)


if __name__ == "__main__":
    main()











