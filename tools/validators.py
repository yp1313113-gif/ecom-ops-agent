"""工具统一返回结构与校验层。

目标（面试口径）：
    "把工具调用从'返回字符串'升级为'返回结构化结果 + 可观测校验'，
     让 Agent 能基于 ToolResult 决定下一步（兜底 / 重试 / 拒答）。"

设计动机（来自真实项目复盘）：
    - 之前所有工具都返回 long string，遇到部分失败只能整段失败
    - 没有任何 schema 检查，运行时才发现字段缺失
    - 阈值告警（库存告急、失败率过高）混在文本里，解析困难
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Callable


@dataclass
class ToolResult:
    """工具统一返回结构。任何工具都应通过它向上层返回结果。

    字段约定：
        success: 主流程是否完成（True=成功，False=失败）
        data: 结构化业务数据（可被 Agent 直接消费或序列化）
        warnings: 非致命异常（部分 SKU 缺失、价格轻微异常等）
        errors: 致命错误（文件丢失、权限拒绝等）
        summary: 人类可读的总结（保留原有的中文 str 风格）
    """

    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    summary: str = ""

    def to_text(self) -> str:
        """向前兼容旧的 str 返回风格。"""
        parts = [self.summary] if self.summary else []
        if self.warnings:
            parts.append("⚠️ 告警：\n" + "\n".join(f"  · {w}" for w in self.warnings))
        if self.errors:
            parts.append("❌ 错误：\n" + "\n".join(f"  · {e}" for e in self.errors))
        return "\n".join(parts) if parts else ("✅ OK" if self.success else "❌ FAILED")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ============ 校验装饰器 ============
def validate_tool(schema: dict[str, Callable[[Any], str | None]] | None = None,
                  required_data_keys: tuple[str, ...] = ()):
    """工具校验装饰器：在工具运行成功后做字段存在性 + 阈值校验。

    Args:
        schema: {字段名 -> 校验函数(值) -> Optional[错误信息]}
        required_data_keys: 必现的 data 字段，缺失则记入 errors
    """
    def decorator(fn):
        def wrapper(*args, **kwargs):
            result: ToolResult = fn(*args, **kwargs)
            # 结构校验
            for key in required_data_keys:
                if key not in result.data:
                    result.errors.append(f"缺少必现字段：data.{key}")
                    result.success = False
            # 字段级 schema 校验
            if schema:
                for k, validator in schema.items():
                    if k in result.data:
                        err = validator(result.data[k])
                        if err:
                            result.errors.append(err)
                            result.success = False
            return result
        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper
    return decorator


# ============ 复用校验函数 ============
def non_empty_str(value: Any) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return "字符串字段为空"
    return None


def positive_int(value: Any) -> str | None:
    if not isinstance(value, (int, float)) or value < 0:
        return "数值字段应为非负数"
    return None


def fail_rate_threshold(max_pct: float):
    def _check(value):
        if not isinstance(value, (int, float)):
            return "失败率字段应为数值"
        if value > max_pct:
            return f"失败率 {value:.1f}% 超过阈值 {max_pct:.1f}%"
        return None
    return _check


def file_exists(path: str) -> str | None:
    """校验文件是否真实存在（防止工具谎报成功）。"""
    import os
    if not path or not os.path.exists(path):
        return f"声称的输出文件不存在：{path}"
    return None


def dir_exists(path: str) -> str | None:
    import os
    if not path or not os.path.isdir(path):
        return f"声称的输出目录不存在：{path}"
    return None
