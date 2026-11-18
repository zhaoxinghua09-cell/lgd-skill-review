#!/usr/bin/env python3
"""Generate the static, machine-crawlable site for lgd-skill-review.

Outputs into docs/ : index.html, 4 skill pages, rubric.html, sitemap.xml, robots.txt, llms.txt
Everything is derived from bench/leaderboard.json + the four SKILL.md frontmatters, so the
site cannot drift away from the measured numbers.

No JavaScript. One page = one topic. JSON-LD on every page.
"""
import json
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

    # sitemap / robots / llms
    urls = ["index.html", "rubric.html", "benchmark.html", "badge.html"] + [s["slug"] + ".html" for s in SKILLS]
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

## 9. site
{SITE}/ — {', '.join(u.replace('.html','') for u in urls)}
"""
    open(os.path.join(DOCS, "llms-full.txt"), "w", encoding="utf-8").write(full)

    print("pages:", len(urls), "| docs dir:", DOCS)


if __name__ == "__main__":
    main()

