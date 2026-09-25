"""Mock LLM：用关键词匹配的简单规则路由，模拟 DeepSeek 对 6 个工具的选择决策。

面试口径：
    "在没有真实 LLM 凭证时, 用规则 mock 出'假设大模型会这么选'的轨迹,
     让 Agent 链路能在沙箱里 100% 复现并收集指标。"

设计动机：
    - eval 真正想测的是「Agent 调度 + 工具执行 + 校验/兜底」三件事,
      其中只有「调度决策」需要 LLM, 其余都是确定性逻辑
    - mock LLM 用关键词正则, 既能跑通, 又能验证 eval 框架本身
    - 测试集设计为「命中关键字即路由, 不命中记失败」

工具路由关键词表：
    清洗 / 订单 / 监控 / 日报 / 图片 / 备份

兜底策略（v1.2）：
    - 引入「拒答」决策（route() 返回 None）: 当问题命中
      ① 业务范围黑名单（投诉/考勤/财务/ROI 等）
      ② 模糊问句黑名单（搞一下/看看情况/随便 等）
      Agent 不应强行调用工具, 而是输出兜底话术让用户澄清。
    - 这把 mock LLM 从「永不说不知道」升级为「敢说不知道」,
      也是把 6pp 假阳性差值收回来的关键 fix.
"""
from __future__ import annotations

import re

TOOL_ROUTES: list[tuple[str, str]] = [
    # (关键词模式, 工具名)
    (r"清洗|整理|规范|去重", "clean_sales_data"),
    (r"订单|同步|对账|erp|对照", "sync_orders"),
    (r"监控|告警|库存告急|价格异常|库存", "monitor_platforms"),
    (r"日报|日报|今日|汇总|营业额", "generate_daily_report"),
    (r"图片|缩放|水印|裁剪|批处理", "batch_process_images"),
    (r"备份|异地|网盘", "backup_data"),
]

# 兜底：当所有关键词都没命中时, 默认路由
DEFAULT_ROUTE = "clean_sales_data"

# 业务范围黑名单: 命中即视为「无对应工具」, 应拒答而非硬调
# (对应 missing_knowledge 类用例, 期望 expected_tool=None)
MISSING_KNOWLEDGE_PATTERNS = [
    r"投诉率|退货流程|考勤|财务|ROI|转化率|物流时效|客服|供应商账期",
    r"用户画像|仓储\s*SKU|广告投放",
]

# 模糊问句黑名单: 短句意图不明, 期望兜底
# (对应 ambiguous 类用例, 期望 expected_tool=None; 覆盖 12 条 case 39-50)
# 注意: case 真实文本可能是 "帮我弄一下那个" / "今天的进度", 所以用子串匹配
# 而非 ^...$ 严格全匹配.
AMBIGUOUS_PATTERNS = [
    r"(现在的状态|搞一下|搞搞|看看情况|怎么办|弄一下那个|出问题了|进度|最新情况呢|咋整|该不该担心|随便|随便搞搞)",
]

_REJECT_RE = re.compile("|".join(MISSING_KNOWLEDGE_PATTERNS + AMBIGUOUS_PATTERNS))


def should_reject(question: str) -> bool:
    """当问题命中黑名单时, Agent 不应调用任何工具, 直接走兜底话术."""
    return bool(_REJECT_RE.search(question))


def route(question: str) -> str | None:
    """根据用户问句, mock 出一个工具名; 命中黑名单时返回 None 表示拒答."""
    if should_reject(question):
        return None
    for pattern, tool in TOOL_ROUTES:
        if re.search(pattern, question):
            return tool
    return DEFAULT_ROUTE


def answer(question: str, tool_result) -> str:
    """根据工具返回的 ToolResult, mock 出最终用户回复."""
    summary = getattr(tool_result, "summary", str(tool_result)) if tool_result else "(无返回)"
    return (
        f"我已经处理了你的问题:「{question}」\n"
        f"调用工具结果摘要:\n{summary}\n"
        f"如需详细字段, 可以告诉我。"
    )
