"""电商运营自动化 Agent · Streamlit 交互演示界面。

设计要点（对应简历里的「工程化 + 可演示」）：
  - 零凭证即可运行（mock 模式）：未配置 DeepSeek Key 时，6 个工具用内置示例数据跑通。
  - 每个工具都经由 agent_core.run_tool() 中间件执行，自动获得
    重试 + 熔断 + JSONL trace 三件套，界面实时展示结构化 ToolResult。
  - 右下「全链路 Trace」面板读取 logs/trace.jsonl，可观测每次调用的
    ts / duration / success，呼应「问题排查不再靠 print」。

运行：
    pip install -r requirements.txt
    streamlit run app.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

from agent_core import run_tool, breaker_status
from tools import (
    clean_sales_data,
    sync_orders,
    monitor_platforms,
    generate_daily_report,
    batch_process_images,
    backup_data,
)
from tools.oversell_tool import oversell_scan_demo
from tools.trace import read_traces, summarize_traces

st.set_page_config(page_title="电商运营自动化 Agent", page_icon="🛒", layout="wide")

# ============ 工具注册表 ============
TOOLS = [
    ("🧹 数据清洗", clean_sales_data, "把脏 CSV 清洗为规整表格：去重 + 标准化金额/日期"),
    ("🔗 订单同步校验", sync_orders, "SKU↔ERP 对照校验，缺失率超 20% 阈值显式报错"),
    ("📡 多平台监控告警", monitor_platforms, "库存/异常扫描，结果经企微推送（mock）"),
    ("📊 生成运营日报", generate_daily_report, "取数 → Excel 报表 → 企微推送（mock）"),
    ("🖼️ 图片批处理", batch_process_images, "批量缩略 + 水印，输出 processed_images/"),
    ("💾 数据备份", backup_data, "本地副本（网盘异地可选）"),
    ("🛡️ 超卖风险巡检", oversell_scan_demo,
     "各平台展示库存 vs 可用库存（仓库−在途占用−安全库存），输出缺口与水位建议"),
]

if "results" not in st.session_state:
    st.session_state["results"] = []


def run_one(label: str, fn) -> None:
    """通过 run_tool 中间件执行工具，并把结果存入 session_state。"""
    with st.spinner(f"执行 {label} …"):
        t0 = time.perf_counter()
        res = run_tool(fn)
        elapsed = (time.perf_counter() - t0) * 1000
    st.session_state["results"].insert(
        0,
        {
            "label": label,
            "res": res,
            "elapsed_ms": round(elapsed, 2),
            "ts": time.strftime("%H:%M:%S"),
        },
    )


# ============ 顶部 ============
st.title("🛒 电商运营自动化 Agent（ecom-ops-agent）")
st.caption("单 Agent + 6 业务工具 · 自然语言可调度 · 本演示为零凭证 mock 模式，直接点击运行")

# 熔断状态徽章
bs = breaker_status()
status_text = "🟢 正常" if not bs["is_open"] else "🔴 熔断中"
st.sidebar.markdown(f"**熔断器状态**：{status_text}")
st.sidebar.markdown(f"- 失败计数：`{bs['fail_count']}`")
st.sidebar.markdown("---")
st.sidebar.markdown("**工具调用链路**")
st.sidebar.markdown("```\n用户输入 → Agent 路由\n   ↓\nrun_tool() 中间件\n (重试 + 熔断 + trace)\n   ↓\n6 个业务工具\n   ↓\nToolResult(success,\n  data, warnings,\n  errors)\n```")

# ============ 工具按钮 ============
st.markdown("### ① 单工具运行")
cols = st.columns(3)
for i, (label, fn, desc) in enumerate(TOOLS):
    with cols[i % 3]:
        st.markdown(f"**{label}**\n\n_{desc}_")
        if st.button(label, key=f"btn_{i}", use_container_width=True):
            run_one(label, fn)
            st.rerun()

st.markdown("### ② 一键跑通全流程")
if st.button("▶ 运行全部 6 个工具", use_container_width=True, type="primary"):
    for label, fn, _ in TOOLS:
        run_one(label, fn)
    st.rerun()

# ============ 结果展示 ============
st.markdown("### ③ 运行结果（结构化 ToolResult）")
if not st.session_state["results"]:
    st.info("点击上方按钮运行工具，结果会显示在这里。")
else:
    for item in st.session_state["results"]:
        res = item["res"]
        ok = res.success
        head = f"{'✅' if ok else '❌'} {item['label']} · {item['ts']} · 耗时 {item['elapsed_ms']} ms"
        with st.expander(head, expanded=True):
            st.markdown("**摘要**")
            st.code(res.summary or ("OK" if ok else "FAILED"), language="text")
            if res.data:
                st.markdown("**结构化 data**")
                st.json(res.data)
            if res.warnings:
                st.warning("⚠️ 告警：\n" + "\n".join(f"- {w}" for w in res.warnings))
            if res.errors:
                st.error("❌ 错误：\n" + "\n".join(f"- {e}" for e in res.errors))

# ============ 全链路 Trace ============
st.markdown("### ④ 全链路 Trace（logs/trace.jsonl）")
summary = summarize_traces()
if summary["total"] == 0:
    st.info("暂无 trace 记录，运行工具后会自动写入 logs/trace.jsonl。")
else:
    st.markdown(f"累计调用 **{summary['total']}** 次")
    for tool, slot in summary["by_tool"].items():
        st.markdown(
            f"- `{tool}`：{slot['calls']} 次 · 成功率 {slot['success_rate']}% · 平均 {slot['avg_ms']} ms"
        )
    with st.expander("查看最近 10 条原始 trace"):
        for r in read_traces(limit=10):
            st.markdown(
                f"`{r['ts']:.3f}` **{r['tool']}** "
                f"{'✅' if r['success'] else '❌'} {r['duration_ms']} ms — {r['result_summary']}"
            )

st.markdown("---")
st.caption("配置 DeepSeek Key（cp .env.example .env）后，可在 run.py 中用自然语言调度上述工具。")
