#!/usr/bin/env python3
"""Generate docs/rubric.json straight from the engine's own constants.

Why generated rather than hand-written: a hand-written rubric drifts from the runner the
first time someone edits a weight. This imports review.py, so weights, blocking rules and
the static cap in the JSON are the ones the engine actually uses.
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(HERE, "review.py")
OUT = os.path.join(HERE, "..", "docs", "rubric.json")

MEANING = {
    "structure": "元数据与目录结构是否机器可读：name/version/description/author、层级深度、体积上限",
    "consistency": "SKILL.md 里声明的命令与参数，是否真的存在于源码（本体系权重最高）",
    "reproducible": "是否有 golden 集与可执行 runner，让陌生人能复跑你的结论",
    "hygiene": "无明文密钥、无真实手机号/邮箱、无本机绝对路径",
    "discoverable": "触发词、生态互链、AI-INDEX.json 或 llms.txt，让 AI 能找到入口",
    "licensing": "有独立许可文件且有声明字段",
}


def load_engine():
    spec = importlib.util.spec_from_file_location("lgd_review_engine", ENGINE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["lgd_review_engine"] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    m = load_engine()
    weights = dict(m.WEIGHTS)
    doc = {
        "schema_version": "1.0",
        "engine": "scripts/review.py",
        "generated_by": "scripts/gen_rubric.py",
        "note": "数值由引擎常量导出；改引擎则此文件随之改变，不接受手改。",
        "scale": {"max_static": 96, "max_with_run": 100,
                  "explanation": "静态模式上限 96；其余 4 分需被评包自带测试真实跑通"},
        "dimensions": [
            {"key": k, "weight": w, "meaning": MEANING.get(k, "")} for k, w in weights.items()
        ],
        "blocking_rules": [
            {"key": k, "meaning": v, "effect": "命中任意一条即整包不通过，总分不作数"}
            for k, v in dict(m.BLOCKING).items()
        ],
        "sensitive_patterns": [{"pattern": p, "label": lb} for p, lb in m.SENSITIVE],
        "verdicts": ["PASS", "FAIL", "BLOCK"],
        "how_to_use": {
            "for_a_human": "python scripts/review.py <package-dir> --json",
            "for_an_agent": "读本文件拿到权重与阻断项；逐维核对；按 findings 顺序整改；整改后重跑同一引擎复评",
            "appeal": "每条扣分可申诉：提交方给路径与检查，引擎裁定 OVERTURNED / UPHELD 并记账",
        },
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print("written:", os.path.abspath(OUT), "| dims:", len(doc["dimensions"]),
          "| sum:", sum(weights.values()))


if __name__ == "__main__":
    main()
