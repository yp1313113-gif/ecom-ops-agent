"""轻量 JSONL trace：记录每次工具调用的输入输出与耗时。

面试口径：
    "用最小依赖记录可观测的 trace，问题排查不再靠 print。"
"""
from __future__ import annotations

import json
import os
import time
from functools import wraps
from typing import Any

TRACE_LOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "trace.jsonl"
)


def _ensure_log() -> None:
    os.makedirs(os.path.dirname(TRACE_LOG_PATH), exist_ok=True)


def trace_call(tool_name: str, args: tuple, kwargs: dict, result: Any, duration_ms: float) -> None:
    """显式写入一条 trace。"""
    _ensure_log()
    record = {
        "ts": time.time(),
        "tool": tool_name,
        "args": _safe(args),
        "kwargs": _safe(kwargs),
        "duration_ms": round(duration_ms, 2),
        "success": bool(getattr(result, "success", True)),
        "result_summary": _summarize(result),
    }
    with open(TRACE_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def traced(fn):
    """装饰器：自动计时 + 自动 trace。"""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = fn(*args, **kwargs)
        duration = (time.perf_counter() - start) * 1000
        trace_call(fn.__name__, args, kwargs, result, duration)
        return result

    return wrapper


def _safe(obj: Any) -> Any:
    """JSON 序列化兜底：把 ToolResult/异常/集合拍平成 dict/str。"""
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, (list, tuple)):
        return [_safe(o) for o in obj]
    if isinstance(obj, dict):
        return {k: _safe(v) for k, v in obj.items()}
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)


def _summarize(result: Any) -> str:
    if hasattr(result, "summary") and result.summary:
        return result.summary[:200]
    if isinstance(result, str):
        return result[:200]
    if hasattr(result, "to_dict"):
        d = result.to_dict()
        return f"success={d.get('success')} warnings={len(d.get('warnings', []))} errors={len(d.get('errors', []))}"
    return str(result)[:200]


def read_traces(limit: int = 50) -> list[dict]:
    if not os.path.exists(TRACE_LOG_PATH):
        return []
    with open(TRACE_LOG_PATH, encoding="utf-8") as f:
        lines = f.readlines()[-limit:]
    return [json.loads(line) for line in lines]


def summarize_traces() -> dict:
    """输出全局 trace 汇总：调用次数、平均耗时、成功率、按工具分组。"""
    records = read_traces(limit=10_000)
    by_tool: dict[str, dict] = {}
    for r in records:
        t = r["tool"]
        slot = by_tool.setdefault(t, {"calls": 0, "ok": 0, "fail": 0, "total_ms": 0.0})
        slot["calls"] += 1
        slot["total_ms"] += r["duration_ms"]
        if r["success"]:
            slot["ok"] += 1
        else:
            slot["fail"] += 1
    for t, slot in by_tool.items():
        slot["avg_ms"] = round(slot["total_ms"] / slot["calls"], 2)
        slot["total_ms"] = round(slot["total_ms"], 2)
        slot["success_rate"] = round(slot["ok"] / slot["calls"] * 100, 1)
    return {"total": len(records), "by_tool": by_tool}
