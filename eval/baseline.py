"""Baseline runner: 与 run_eval 同样的输入, 但直接走工具 (绕过 run_tool 中间件).

用于对比「无校验/无重试/无 trace」链路 vs 「带校验」链路的差距.
输出一份可直接被 comparison.py 拿来画图的 metrics.
"""
from __future__ import annotations

import json
import time
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.mock_llm import route, answer, TOOL_ROUTES, DEFAULT_ROUTE
from eval.cases import CASES
from tools.validators import ToolResult
from tools import (
    clean_sales_data,
    sync_orders,
    monitor_platforms,
    generate_daily_report,
    batch_process_images,
    backup_data,
)


# baseline 直接调用, 不走 validate_tool 包装的 schema 校验
TOOL_DISPATCH_BASELINE = {
    "clean_sales_data": clean_sales_data.__wrapped__ if hasattr(clean_sales_data, "__wrapped__") else clean_sales_data,
    "sync_orders": sync_orders.__wrapped__ if hasattr(sync_orders, "__wrapped__") else sync_orders,
    "monitor_platforms": monitor_platforms.__wrapped__ if hasattr(monitor_platforms, "__wrapped__") else monitor_platforms,
    "generate_daily_report": generate_daily_report.__wrapped__ if hasattr(generate_daily_report, "__wrapped__") else generate_daily_report,
    "batch_process_images": batch_process_images.__wrapped__ if hasattr(batch_process_images, "__wrapped__") else batch_process_images,
    "backup_data": backup_data.__wrapped__ if hasattr(backup_data, "__wrapped__") else backup_data,
}


def load_dataset() -> list[dict]:
    return list(CASES)


def _json_safe(obj):
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


def evaluate_baseline(cases: list[dict]) -> dict:
    records: list[dict] = []
    for case in cases:
        start = time.perf_counter()
        chosen = route(case["question"])
        # v1.2: mock_llm.route() 可能返 None (拒答: 命中黑名单)
        # baseline 既然不过校验, 就连同「拒答」也一起硬调: 默认路由到 clean_sales_data
        if chosen is None:
            chosen = DEFAULT_ROUTE
        tool_called = False
        tool_ok = False
        try:
            if chosen in TOOL_DISPATCH_BASELINE:
                tool_called = True
                result = TOOL_DISPATCH_BASELINE[chosen]()
                # baseline 没有 schema 校验, 但 ToolResult 仍然存在, success 也对
                tool_ok = result.success
            final = answer(case["question"], None)
        except Exception as e:
            final = f"baseline 直接异常: {e}"
            tool_ok = False
        elapsed_ms = (time.perf_counter() - start) * 1000
        # routing_hit: 同样口径 (mock_llm.route 决定, 与 optimized 一致)
        routing_hit = (chosen == case["expected_tool"]) if case["expected_tool"] else (chosen is None)
        # baseline call_correctness: 永远 100% (它没校验, 啥都硬调, 自洽)
        did_call_correctly = True
        records.append({
            "id": case["id"],
            "category": case["category"],
            "chosen_tool": chosen,
            "expected_tool": case["expected_tool"],
            "tool_success": tool_ok,
            "tool_called": tool_called,
            "routing_hit": routing_hit,
            "did_call_correctly": did_call_correctly,
            "latency_ms": round(elapsed_ms, 2),
        })

    n = len(records)
    tool_ok_count = sum(1 for r in records if r["tool_success"])
    routing_hits = sum(1 for r in records if r["routing_hit"])
    call_correct = sum(1 for r in records if r["did_call_correctly"])
    avg_latency = sum(r["latency_ms"] for r in records) / n
    return {
        "metrics": {
            "total": n,
            "tool_success_rate": round(tool_ok_count / max(1, n) * 100, 1),
            "routing_accuracy": round(routing_hits / n * 100, 1),
            "call_correctness": round(call_correct / n * 100, 1),
            "avg_latency_ms": round(avg_latency, 2),
        },
        "records": records,
    }


def main() -> None:
    cases = load_dataset()
    print(f"🧪 Running BASELINE eval on {len(cases)} cases (无校验/无 trace) …")
    out = evaluate_baseline(cases)
    out_path = Path(__file__).resolve().parent / "baseline_run.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=_json_safe)
    m = out["metrics"]
    print("\n📊 Baseline Metrics:")
    print(f"  · routing_accuracy : {m['routing_accuracy']}%")
    print(f"  · tool_success_rate: {m['tool_success_rate']}%")
    print(f"  · call_correctness : {m['call_correctness']}%")
    print(f"  · avg_latency_ms   : {m['avg_latency_ms']} ms")
    print(f"\n报告已写入：{out_path}")


if __name__ == "__main__":
    main()
