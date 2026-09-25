"""推送通道 · 适配器模式（企业微信 / 飞书 / 钉钉）。

[为什么用适配器]
    三个平台的 webhook 只有两处不同：
        ① URL            （各自域名 + token）
        ② payload 字段名  （msgtype+text.content / msg_type+content.text / msgtype+text.content）
    而发送流程完全一样：POST → 校验状态码 → 异常兜底 → 本地日志留痕。

    如果每接一个平台就把发送逻辑复制一遍，就是典型的重复代码；
    以后再加一个通道（比如"飞书告警群"）还得改三处。
    适配器把「平台差异」收拢到子类的 build_url / build_payload，
    发送流程只在基类写一次。

[降级策略]（与项目整体一致：外部依赖缺失时不崩）
    未配置任何 webhook → 只写本地日志，功能不中断；
    某一个平台推送失败 → 记录错误，不影响其他平台。
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

import config
from tools.validators import ToolResult

LOG_PATH = os.path.join(config.DATA_DIR, "alerts.log")


class Notifier:
    """推送通道基类。子类只需给出 URL 和 payload 形状。"""

    channel = "base"

    def __init__(self, webhook: str = ""):
        self.webhook = webhook or ""

    # ---- 两个「平台差异」的钩子 ----
    def build_url(self) -> str:
        return self.webhook

    def build_payload(self, text: str) -> dict[str, Any]:
        raise NotImplementedError

    # ---- 发送流程：所有平台共用 ----
    def send(self, text: str) -> ToolResult:
        if not self.webhook:
            return ToolResult(success=False, errors=[f"[{self.channel}] webhook 未配置"], summary="")
        if requests is None:
            return ToolResult(success=False, errors=["未安装 requests，无法推送"], summary="")
        try:
            resp = requests.post(self.build_url(), json=self.build_payload(text), timeout=5)
            ok = 200 <= resp.status_code < 300
            return ToolResult(
                success=ok,
                data={"channel": self.channel, "status_code": resp.status_code},
                errors=[] if ok else [f"[{self.channel}] 推送返回 {resp.status_code}"],
                summary=f"已推送告警到[{self.channel}]" if ok else f"[{self.channel}] 推送失败",
            )
        except Exception as e:
            return ToolResult(success=False, errors=[f"[{self.channel}] 推送异常：{e}"], summary="")


class WeComNotifier(Notifier):
    """企业微信机器人。"""
    channel = "wecom"

    def build_payload(self, text: str) -> dict[str, Any]:
        return {"msgtype": "text", "text": {"content": text}}


class FeishuNotifier(Notifier):
    """飞书自定义机器人。"""
    channel = "feishu"

    def build_payload(self, text: str) -> dict[str, Any]:
        return {"msg_type": "text", "content": {"text": text}}


class DingTalkNotifier(Notifier):
    """钉钉自定义机器人。"""
    channel = "dingtalk"

    def build_payload(self, text: str) -> dict[str, Any]:
        return {"msgtype": "text", "text": {"content": text}}


# channel → (config 属性名, 适配器类)
_REGISTRY: dict[str, tuple[str, type[Notifier]]] = {
    "wecom": ("WECHAT_WEBHOOK", WeComNotifier),
    "feishu": ("FEISHU_WEBHOOK", FeishuNotifier),
    "dingtalk": ("DINGTALK_WEBHOOK", DingTalkNotifier),
}


def get_notifier(channel: str) -> Notifier:
    """按名字取适配器；未知通道抛 ValueError（早点炸比静默失败好）。"""
    if channel not in _REGISTRY:
        raise ValueError(f"未知推送通道：{channel}，可选 {list(_REGISTRY)}")
    attr, cls = _REGISTRY[channel]
    return cls(getattr(config, attr, ""))


def configured_channels() -> list[str]:
    return [c for c, (attr, _) in _REGISTRY.items() if getattr(config, attr, "")]


def _log_local(text: str) -> None:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {text}\n---\n")


def notify(text: str, channel: str | None = None) -> ToolResult:
    """统一推送入口。

    Args:
        text: 要推送的文本
        channel: 指定通道（wecom/feishu/dingtalk）；不传则用第一个已配置的通道

    未配置任何通道时降级为本地日志，并如实告知调用方（不假装成功）。
    """
    channels = [channel] if channel else configured_channels()
    if not channels:
        _log_local(text)
        return ToolResult(
            success=False,
            data={"channel": "local_log", "log_path": LOG_PATH},
            warnings=[f"未配置任何推送通道，已降级写入本地日志：{LOG_PATH}"],
            summary="（未配置推送通道，告警仅写入本地日志）",
        )

    results = [get_notifier(c).send(text) for c in channels]
    ok = [r for r in results if r.success]
    failed = [r for r in results if not r.success]
    if not ok:
        _log_local(text)
        return ToolResult(
            success=False,
            data={"attempted": channels},
            errors=[e for r in failed for e in r.errors],
            warnings=["所有通道推送失败，已降级写入本地日志"],
            summary="（推送失败，告警仅写入本地日志）",
        )
    return ToolResult(
        success=True,
        data={"pushed": [r.data["channel"] for r in ok], "failed": [r.data.get("channel") for r in failed]},
        errors=[e for r in failed for e in r.errors],
        summary="已推送告警到 " + "、".join(r.data["channel"] for r in ok),
    )


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print("已配置通道：", configured_channels() or "（无，将降级为本地日志）")
    for c in _REGISTRY:
        n = get_notifier(c)
        print(f"  {c:9} URL 前缀 {n.build_url()[:38] or '（空）'}｜payload 键 {sorted(n.build_payload('x').keys())}")
    print("\n试推一条：", notify("【测试】超卖巡检发现 2 个 SKU 存在风险").summary)
