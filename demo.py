"""本地演示：不依赖任何 API 凭证, 直接调用 6 个工具跑通完整运营流程。

[升级] 通过 run_tool() 走「重试 + 校验 + trace」三件套, 末尾汇总熔断器 + trace 状态。

运行：python demo.py
"""
from agent_core import run_tool, breaker_status
from tools.trace import summarize_traces
from tools import (
    clean_sales_data,
    sync_orders,
    monitor_platforms,
    generate_daily_report,
    batch_process_images,
    backup_data,
)
from tools.oversell_tool import oversell_scan_demo


def _sep(title: str) -> None:
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def _print(result) -> None:
    print(result.to_text())
    if result.warnings:
        print(f"   ↑ 告警已记录于 ToolResult.warnings ({len(result.warnings)} 条)")


def main() -> None:
    print("🚀 电商运营自动化 Agent · 本地演示（mock 模式 + 重试/校验/trace）\n")

    _sep("1) 数据清洗")
    _print(run_tool(clean_sales_data))

    _sep("2) 订单同步校验")
    _print(run_tool(sync_orders))

    _sep("3) 多平台监控告警")
    _print(run_tool(monitor_platforms))

    _sep("4) 生成运营日报")
    _print(run_tool(generate_daily_report))

    _sep("5) 图片批处理")
    _print(run_tool(batch_process_images))

    _sep("6) 数据备份")
    _print(run_tool(backup_data))

    _sep("7) 多平台超卖风险巡检")
    _print(run_tool(oversell_scan_demo))

    _sep("📊 运维观察")
    print(f"· 熔断器状态：{breaker_status()}")
    summary = summarize_traces()
    print(f"· Trace 总调用：{summary['total']} 次")
    for tool, m in summary["by_tool"].items():
        print(f"   - {tool}: {m['calls']} 次, 成功率 {m['success_rate']}%, 平均 {m['avg_ms']}ms")

    print("\n✅ 演示结束。配置 DeepSeek Key 后这些工具将由 Agent 用自然语言调度。")


if __name__ == "__main__":
    main()
