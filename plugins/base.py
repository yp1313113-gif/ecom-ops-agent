# plugins/base.py
"""扩展点接口定义。

三类扩展点的抽象：
  · `PlatformPlugin`  —— 数据源（平台）
  · `NotifierPlugin`  —— 推送通道（企微 / 飞书 / 钉钉）
  · `ModelPlugin`     —— 模型厂商

━━━ 为什么接口要定在「插件层」而不是「工具层」━━━
工具层关心的是「这次调用成功了吗」（ToolResult），
插件层关心的是「这个数据源/通道现在能不能用」。

两者是不同的问题。插件**不引入 tools 的依赖**，保持可独立测试、可独立加载 ——
否则 `tools/__init__.py` 会被插件反向依赖，形成循环导入。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class StockSnapshot:
    """一次平台库存拉取的结果 —— **三态，不是二态**。

    为什么不用 `int | None`：None 会把三种完全不同的业务情况混在一起，

        · 这个平台上**没上架**这个 SKU       → 不是问题，跳过就行
        · 这个平台**现在读不到**（网络/鉴权）→ 是问题，要隔离并告警
        · 读到了，值就是 0                   → 正常数据，可以落库

    混在一起会导致两种后果之一：把「读不到」当成 0 写进库（凭空造出一个
    「展示库存 0」，还会改变按平台数均分的基数），或者把「未上架」报成故障
    （天天误告警，最后没人看告警）。

    所以用显式两个字段表达：

        qty=None + available=True   → 未上架（跳过）
        available=False             → 不可用（隔离 + 告警）
        qty=N    + available=True   → 正常
    """

    platform: str
    sku: str
    qty: int | None = None
    available: bool = True
    detail: str = ""


class PlatformPlugin(ABC):
    """一个电商平台的数据源插件。

    约定：类属性声明元信息，模块末尾 `PLUGIN = XxxSource`。
    """

    name: str = ""                    # 唯一标识（taobao）
    label: str = ""                   # 展示名（淘宝）
    version: str = "1.0.0"
    description: str = ""
    enabled: bool = True
    # 未确认水位时的保守默认值（0~1）。注意：**不参与 v1 的均分逻辑** ——
    # v1 刻意保留「按平台数均分」这个朴素做法作为评测对照，见 docs/mechanisms/oversell.md。
    default_water_level: float = 0.25

    @abstractmethod
    def fetch_display_stock(self, sku: str) -> StockSnapshot:
        """拉取该平台上某 SKU 的展示库存，返回 **StockSnapshot（三态）**。

        实现约定：
          · 正常读到       → `StockSnapshot(qty=N)`
          · 该平台上没上架 → `StockSnapshot(qty=None, available=True)`
          · 网络/鉴权/超时 → `StockSnapshot(available=False, detail=...)`

        **不要抛异常**：不可用是一种正常的业务状态，不是程序错误。
        调用方（sync 工具）据此做隔离，而不是被异常打断。
        """

    def push_action(self, sku: str, qty: int, reason: str = "") -> dict:
        """把调整指令推回平台。

        默认实现只记录（mock 模式）。真实接入时覆写它。
        返回普通 dict 而不是 ToolResult —— 插件层不依赖工具层。
        """
        return {"ok": True, "platform": self.name, "sku": sku,
                "qty": qty, "reason": reason, "mock": True}

    def health(self) -> bool:
        """该数据源当前是否可用。默认认为可用；真实接入时覆写成探活。"""
        return True


class NotifierPlugin(ABC):
    """一个推送通道插件。"""

    name: str = ""
    label: str = ""
    version: str = "1.0.0"
    description: str = ""
    enabled: bool = True

    @abstractmethod
    def configured(self) -> bool:
        """是否已配置凭证。未配置的通道不参与广播。"""

    @abstractmethod
    def send(self, text: str) -> bool:
        """推送一条文本，返回是否成功。"""


class ModelPlugin(ABC):
    """一个模型厂商插件。"""

    name: str = ""
    label: str = ""
    version: str = "1.0.0"
    description: str = ""
    enabled: bool = True

    @abstractmethod
    def build(self, **kwargs):
        """构造 LangChain ChatModel。"""
