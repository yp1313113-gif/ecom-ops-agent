"""Eval runner: 跑一遍测试集, 收集指标, 输出 JSON 报告。

指标定义：
    - routing_accuracy  路由命中: mock LLM 选的工具 == expected_tool
    - tool_success_rate  工具成功: selected tool 调用后 result.success == True
    - rejection_accuracy 拒答准确: ambiguous/missing 时不调用任何工具或显式告知用户
    - avg_latency_ms     平均往返耗时

跑法：
    python eval/run_eval.py               # 默认 dataset
    python eval/run_eval.py --no-circuit  # 关闭熔断器
"""
from __future__ import annotations

import json
import time
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent_core import run_tool, breaker_status
from tools.validators import ToolResult
from tools.trace import summarize_traces
from tools import (
    clean_sales_data,
    sync_orders,
    monitor_platforms,
    generate_daily_report,
    batch_process_images,
    backup_data,
)
from eval.mock_llm import route, answer, TOOL_ROUTES, DEFAULT_ROUTE
from eval.cases import CASES


TOOL_DISPATCH = {
    "clean_sales_data": clean_sales_data,
    "sync_orders": sync_orders,
    "monitor_platforms": monitor_platforms,
    "generate_daily_report": generate_daily_report,
    "batch_process_images": batch_process_images,
    "backup_data": backup_data,
}


def load_dataset() -> list[dict]:
    return list(CASES)


def _json_safe(obj):
    """numpy / 非原生类型 → JSON 可序列化."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if hasattr(obj, "item"):
        try:
            return obj.item()
        except (ValueError, AttributeError):
            pass
    if hasattr(obj, "tolist"):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(o) for o in obj]
    if hasattr(obj, "to_dict"):
        return _json_safe(obj.to_dict())
    return str(obj)


def evaluate(cases: list[dict]) -> dict:
    records: list[dict] = []
    for case in cases:
        start = time.perf_counter()
        chosen = route(case["question"])
        # v1.2: route() 可能返回 None（拒答: 命中黑名单）
        should_call_tool = (chosen is not None) and (
            chosen != DEFAULT_ROUTE or case["expected_tool"] is not None
        )
        tool_called = False
        tool_ok = False
        tool_result: ToolResult | None = None
        final = ""
        if chosen is None:
            # 拒答: Agent 给出兜底话术, 不调用工具
            final = (
                f"这个问题我暂时回答不了, 请你说清楚要「清洗/订单/监控/日报/图片/备份」"
                f"哪一项? (原始问句:「{case['question']}」)"
            )
        elif should_call_tool and chosen in TOOL_DISPATCH:
            tool_called = True
            tool_result = run_tool(TOOL_DISPATCH[chosen])
            tool_ok = tool_result.success if tool_result else False
            final = answer(case["question"], tool_result)
        else:
            # 兜底: 不调用工具, 给一句澄清
            final = f"这个问题我需要更多信息, 请你说清楚要清洗/订单/监控/日报/图片/备份 哪一项?"

        elapsed_ms = (time.perf_counter() - start) * 1000

        records.append({
            "id": case["id"],
            "category": case["category"],
            "question": case["question"],
            "chosen_tool": chosen or "<reject>",
            "expected_tool": case["expected_tool"],
            "tool_called": tool_called,
            "tool_success": tool_ok,
            "routing_hit": (chosen == case["expected_tool"]) if case["expected_tool"] else (chosen is None),
            "should_have_called": case["expect_success"],
            "did_call_correctly": (tool_called == case["expect_success"]),
            "latency_ms": round(elapsed_ms, 2),
            "final": final,
        })

    # 汇总
    n = len(records)
    routing_hits = sum(1 for r in records if r["routing_hit"])
    tool_ok_count = sum(1 for r in records if r["tool_success"])
    call_correct = sum(1 for r in records if r["did_call_correctly"])
    avg_latency = sum(r["latency_ms"] for r in records) / n
    by_category: dict[str, dict] = {}
    for r in records:
        c = r["category"]
        slot = by_category.setdefault(c, {"count": 0, "routing_hit": 0, "tool_ok": 0, "call_correct": 0})
        slot["count"] += 1
        slot["routing_hit"] += int(r["routing_hit"])
        slot["tool_ok"] += int(r["tool_success"])
        slot["call_correct"] += int(r["did_call_correctly"])

    metrics = {
        "total": n,
        "routing_accuracy": round(routing_hits / n * 100, 1),
        "tool_success_rate": round(tool_ok_count / max(1, sum(1 for r in records if r["tool_called"])) * 100, 1),
        "call_correctness": round(call_correct / n * 100, 1),
        "avg_latency_ms": round(avg_latency, 2),
        "by_category": by_category,
        "trace": summarize_traces(),
        "breaker": breaker_status(),
    }
    return {"metrics": metrics, "records": records}


def main() -> None:
    cases = load_dataset()
    print(f"🧪 Running eval on {len(cases)} cases …")
    out = evaluate(cases)
    out_path = Path(__file__).resolve().parent / "last_run.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=_json_safe)
    m = out["metrics"]
    print("\n📊 Metrics:")
    print(f"  · routing_accuracy : {m['routing_accuracy']}%")
    print(f"  · tool_success_rate: {m['tool_success_rate']}%")
    print(f"  · call_correctness : {m['call_correctness']}%")
    print(f"  · avg_latency_ms   : {m['avg_latency_ms']} ms")
    print(f"  · trace 调用次数    : {m['trace']['total']}")
    print(f"\n详细分类统计:")
    for c, s in m["by_category"].items():
        print(f"  · {c:18s}: count={s['count']}, routing_hit={s['routing_hit']}, tool_ok={s['tool_ok']}, call_correct={s['call_correct']}")
    print(f"\n报告已写入：{out_path}")


if __name__ == "__main__":
    main()
