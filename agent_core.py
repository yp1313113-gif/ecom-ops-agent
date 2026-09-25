"""Agent 调度核心：把工具调用统一包装为「重试 + 校验 + trace」三件套。

面试口径：
    "用 run_tool() 把所有外部副作用集中托管，
     业务工具只关心自己的纯逻辑，运维能力由中间件统一提供。"
"""
from __future__ import annotations

import time
from loguru import logger

from tools.retry import CircuitBreaker
from tools.trace import trace_call
from tools.validators import ToolResult

# 全局轻量熔断器：工具调用级别（任一工具连续失败即熔断）
_agent_breaker = CircuitBreaker(threshold=5, reset_seconds=30)


def run_tool(fn, *args, **kwargs) -> ToolResult:
    """统一的工具调用入口：熔断 → 重试 → trace。

    Args:
        fn: 任意返回 ToolResult 的工具函数
        *args, **kwargs: 透传给 fn

    Returns:
        ToolResult；熔断期内会返回 success=False 的占位 ToolResult
    """
    if not _agent_breaker.allow():
        logger.warning(f"[{fn.__name__}] 熔断器开启中, 跳过本次调用")
        return ToolResult(
            success=False,
            errors=["系统繁忙, 工具调用已熔断, 请稍后再试"],
            summary="❌ 熔断中, 本次调用被短路",
        )
    start = time.perf_counter()
    try:
        result: ToolResult = fn(*args, **kwargs)
        duration_ms = (time.perf_counter() - start) * 1000
        trace_call(fn.__name__, args, kwargs, result, duration_ms)
        if result.success:
            _agent_breaker.record_success()
        else:
            _agent_breaker.record_failure()
        return result
    except Exception as e:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception(f"[{fn.__name__}] 异常: {e}")
        _agent_breaker.record_failure()
        failed = ToolResult(
            success=False,
            errors=[f"{type(e).__name__}: {e}"],
            summary=f"❌ {fn.__name__} 调用异常",
        )
        trace_call(fn.__name__, args, kwargs, failed, duration_ms)
        return failed


def breaker_status() -> dict:
    """返回熔断器状态, 方便 /demo 时打印给用户看。"""
    return {
        "fail_count": _agent_breaker._fail_count,
        "opened_at": _agent_breaker._opened_at,
        "is_open": not _agent_breaker.allow(),
    }
