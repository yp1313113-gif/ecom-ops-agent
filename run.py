"""CLI 入口：与电商运营自动化 Agent 交互。

运行：python run.py
命令：
  /demo   直接跑全部工具的本地演示（无需 API Key）
  /reset  重置对话
  q       退出
"""
import sys

from loguru import logger

from agent import build_agent, chat
from config import LOG_LEVEL, mock_mode

logger.remove()
logger.add(sys.stdout, format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> - <level>{message}</level>", level=LOG_LEVEL)


def main() -> None:
    print("\n🤖 电商运营自动化 Agent")
    if mock_mode():
        print("⚠️ 未检测到 DEEPSEEK_API_KEY，将以 mock 模式运行（工具用本地数据，无需凭证）。")
        print("   配置 .env 中的 DEEPSEEK_API_KEY 后即可由大模型智能调度。")
    else:
        print("✅ 已检测到 DEEPSEEK_API_KEY，大模型调度已启用。")
    print("输入 /demo 查看本地演示，输入 q 退出。\n")

    agent = None
    try:
        if not mock_mode():
            agent = build_agent()
    except Exception as e:
        logger.warning(f"Agent 初始化失败，降级为 mock 模式：{e}")

    while True:
        try:
            user_input = input("👤 你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 已退出")
            break
        if not user_input:
            continue
        if user_input.lower() == "q":
            break
        if user_input.lower() == "/demo":
            import demo
            demo.main()
            continue
        if user_input.lower() == "/reset":
            agent = build_agent() if (not mock_mode() and agent is not None) else agent
            print("🔄 对话已重置")
            continue
        if mock_mode():
            print("⚠️ 当前为 mock 模式，请用 /demo 查看工具演示，或在 .env 配置 DEEPSEEK_API_KEY 后重试。")
            continue
        try:
            answer = chat(user_input, agent)
            print(f"🤖 {answer}")
        except Exception as e:
            logger.error(f"调用失败：{e}")


if __name__ == "__main__":
    main()
