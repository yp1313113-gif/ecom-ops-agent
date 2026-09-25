"""ecom-ops-agent 配置。

所有外部凭证（DeepSeek / 企微机器人 / 百度网盘）都从环境变量读取，
未配置时自动降级为「mock 模式」——工具用本地 mock 数据跑，无需任何凭证即可演示。
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ---------- LLM（DeepSeek，兼容 OpenAI 协议） ----------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0"))

# ---------- 推送通道（日报/告警，全部可选） ----------
# 三条通道共用一个适配器（见 notifier.py），配置哪个就用哪个，可同时配。
# 全部未配置时降级为本地日志（data/alerts.log），功能不中断。
WECHAT_WEBHOOK = os.getenv("WECHAT_WEBHOOK", "")      # 企业微信机器人
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK", "")      # 飞书自定义机器人
DINGTALK_WEBHOOK = os.getenv("DINGTALK_WEBHOOK", "")  # 钉钉自定义机器人

# ---------- 百度网盘备份（可选） ----------
# 配置后 backup_data 会模拟上传；未配置时仅做本地异地副本。
BAIDU_NETDISK_ENABLED = os.getenv("BAIDU_NETDISK_ENABLED", "false").lower() == "true"

# ---------- 路径 ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


def mock_mode() -> bool:
    """是否处于 mock 模式（未配置 DeepSeek Key 时工具用本地数据运行）。"""
    return not bool(DEEPSEEK_API_KEY)
