"""多平台监控工具：检测价格异常/库存告急，推送告警到企业微信。

对应实习工作：Python 定时任务 + 爬虫 + 企业微信告警的多平台监控看板。
mock 模式下读取 data/platforms.csv，检测异常并写入本地告警日志。

[升级] 返回 ToolResult; 告警条目作为结构化 alerts 字段暴露给 Agent 决策。
"""
import os
import requests

from config import DATA_DIR, WECHAT_WEBHOOK
from tools.validators import ToolResult, validate_tool, file_exists


@validate_tool(
    schema={"alert_count": lambda v: "告警数应为非负整数" if not isinstance(v, int) or v < 0 else None},
    required_data_keys=("alert_count", "alerts", "log_path"),
)
def monitor_platforms(
    data_path: str | None = None,
    stock_threshold: int = 10,
    price_change_pct: float = 15.0,
) -> ToolResult:
    """检测各平台商品的库存告急与价格异常，并推送告警。"""
    path = data_path or os.path.join(DATA_DIR, "platforms.csv")
    if not os.path.exists(path):
        return ToolResult(
            success=False,
            errors=[f"找不到平台数据文件：{path}"],
            summary=f"❌ 找不到平台数据文件：{path}",
        )

    import pandas as pd
    df = pd.read_csv(path)
    alerts: list[dict] = []
    alert_lines: list[str] = []
    for _, row in df.iterrows():
        platform = row.get("platform", "?")
        sku = row.get("sku", "?")
        stock = float(row.get("stock", 0) or 0)
        price = float(row.get("price", 0) or 0)
        base = float(row.get("base_price", price) or price)
        if stock < stock_threshold:
            msg = f"[{platform}] {sku} 库存告急：仅剩 {int(stock)} 件"
            alerts.append({"type": "stock_low", "platform": platform, "sku": sku, "stock": stock})
            alert_lines.append(msg)
        if base and abs(price - base) / base * 100 > price_change_pct:
            direction = "上涨" if price > base else "下降"
            pct = abs(price - base) / base * 100
            msg = f"[{platform}] {sku} 价格异常{direction}：{price}（基准 {base}，波动 {pct:.1f}%）"
            alerts.append({"type": "price_abnormal", "platform": platform, "sku": sku, "pct": pct})
            alert_lines.append(msg)

    log_path = os.path.join(DATA_DIR, "wechat_alerts.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    if not alerts:
        text = "✅ 监控完成：各平台价格与库存均正常，无异常。"
        _push_alert("电商监控：无异常", log_path)
        return ToolResult(
            success=True,
            data={"alert_count": 0, "alerts": [], "log_path": log_path},
            summary=text,
        )

    header = "⚠️ 电商运营监控告警：\n" + "\n".join(f"  · {a}" for a in alert_lines)
    _push_alert(header, log_path)
    summary = header + f"\n\n已推送告警（共 {len(alerts)} 条）"
    return ToolResult(
        success=True,
        data={"alert_count": len(alerts), "alerts": alerts, "log_path": log_path},
        warnings=[f"{len(alerts)} 条告警已推送" + ("（含库存）" if any(a["type"] == "stock_low" for a in alerts) else "")],
        summary=summary,
    )


def _push_alert(text: str, log_path: str) -> None:
    """推送告警：走统一适配器（企业微信/飞书/钉钉），未配置则降级写本地日志。"""
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(text + "\n---\n")
    try:
        from notifier import notify
        notify(text)
    except Exception:
        pass
