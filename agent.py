"""Agent 调度层：把 6 个业务工具交给一个 ReAct Agent，自然语言即可调度。

技术栈与现有 multi-agent-system 一致（DeepSeek + LangChain），便于复用经验。
未配置 DEEPSEEK_API_KEY 时进入 mock 模式：工具用本地数据跑，无需任何凭证。
"""
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

from config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    TEMPERATURE,
)
from tools import (
    clean_sales_data,
    sync_orders,
    monitor_platforms,
    generate_daily_report,
    batch_process_images,
    backup_data,
    oversell_check,
    oversell_scan,
    remember_preference,
    recall_preference,
)

AGENT_TOOLS = [
    clean_sales_data,
    sync_orders,
    monitor_platforms,
    generate_daily_report,
    batch_process_images,
    backup_data,
    oversell_check,
    oversell_scan,
    remember_preference,
    recall_preference,
]

SYSTEM_PROMPT = """你是一个「电商运营自动化 Agent」，服务于中小型电商/贸易公司的运营与数据岗。
你的职责是把用户的自然语言指令，转化为对下方工具的有序调用，自动完成日常运营任务。

可用工具：
- clean_sales_data：清洗脏乱的销售/订单 Excel/CSV（去重、补空、标准化金额与日期）
- sync_orders：校验订单 SKU 与 ERP 编码的对照，输出同步对账报告
- monitor_platforms：检测各平台商品的库存告急与价格异常，并推送告警
- generate_daily_report：聚合销售数据生成 Excel 日报并推送企业微信
- batch_process_images：批量缩放图片并加水印
- backup_data：把数据目录做本地异地备份（可选上传网盘）
- oversell_check：检查某个 SKU 的多平台超卖风险（可用库存 vs 各平台展示库存）
- oversell_scan：全量巡检，列出所有存在超卖风险的 SKU 与总缺口
- remember_preference：记住一条长期设置（如「以后安全库存按 10 算」），跨会话生效
- recall_preference：读取已记住的设置

工作原则：
1. 一次只调用完成当前任务所需的工具；多步任务按顺序调用。
2. 调用工具前先确认输入参数合理；参数缺省时工具会用默认 mock 数据。
3. 工具返回中文摘要，你把关键信息整理成简洁、面向业务的结果回复用户。
4. 不要编造数据；若工具报错，如实告知并给出排查建议。
5. 涉及真实凭证（ERP/企微/网盘）的功能在未配置时会自动降级为本地演示，请向用户说明。
"""


def build_agent():
    """构造 ReAct Agent。"""
    llm = ChatOpenAI(
        model=DEEPSEEK_MODEL,
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
        temperature=TEMPERATURE,
    )
    return create_agent(model=llm, tools=AGENT_TOOLS, system_prompt=SYSTEM_PROMPT)


def chat(user_input: str, agent=None) -> str:
    """与 Agent 进行一次对话，返回最终回答文本。"""
    if agent is None:
        agent = build_agent()
    result = agent.invoke({"messages": [{"role": "user", "content": user_input}]})
    msgs = result.get("messages", [])
    last = msgs[-1] if msgs else None
    content = getattr(last, "content", "") if last is not None else ""
    return content if isinstance(content, str) else str(content)
