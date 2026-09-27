# plugins/sources/rest_api.py
"""真实平台 API 接入模板（默认 disabled）。

━━━ 这个文件的价值不是「能跑」，而是说明插件化怎么落到真实系统上 ━━━
三个要点，每个都是踩过的坑：

1. **失败必须返回 None，不能抛异常。**
   一个平台读不到，不应该让整次巡检失败 —— 这是插件化的核心价值（故障隔离）。
   异常是「事故」，None 是「已知的不可用」，调用方对两者的处理不同。

2. **超时必须显式设置。**
   requests 默认没有超时，一个卡住的接口会把整个同步任务拖死。

3. **未配置凭证时 enabled=False。**
   discovery 会跳过它，不参与巡检，也不会在 /plugins 里显示为可用。

配置方式：
    ERP_API_BASE=https://erp.example.com
    ERP_API_TOKEN=xxx
    ERP_API_PLATFORM_FIELD=platform     # 可选，默认 platform
"""
from __future__ import annotations

import os

from plugins.base import PlatformPlugin, StockSnapshot

try:
    import requests
except Exception:  # pragma: no cover
    requests = None


class ErpProxySource(PlatformPlugin):
    """通过企业 ERP 的只读接口拉取各平台展示库存。

    ERP 通常已经聚合了各平台的库存，所以现实里常见的是「一个 ERP 代理源」
    而不是「每个平台各接一个 API」——这也是插件化能容纳的第二种形态。
    """

    name = "erp_proxy"
    label = "ERP 代理源"
    version = "0.1.0"
    description = "通过企业 ERP 只读接口拉取展示库存（模板，需配置 ERP_API_BASE）"
    # 未配置就不启用 —— discovery 会跳过，不污染巡检结果
    enabled = bool(os.getenv("ERP_API_BASE"))
    default_water_level = 0.25

    TIMEOUT = 3.0            # ★ 必须显式设超时，否则卡住的接口会拖死同步任务

    def fetch_display_stock(self, sku: str) -> StockSnapshot:
        base = os.getenv("ERP_API_BASE", "").rstrip("/")
        token = os.getenv("ERP_API_TOKEN", "")
        if not base or requests is None:
            return StockSnapshot(self.name, sku, available=False, detail="未配置 ERP_API_BASE")
        try:
            resp = requests.get(
                base + "/api/inventory/display",
                params={"sku": sku},
                headers={"Authorization": "Bearer " + token} if token else {},
                timeout=self.TIMEOUT,
            )
            if resp.status_code != 200:
                return StockSnapshot(self.name, sku, available=False,
                                     detail="ERP 返回 " + str(resp.status_code))
            data = resp.json()
            qty = data.get("display_qty")
            if qty is None:
                return StockSnapshot(self.name, sku, qty=None, detail="ERP 无该 SKU 记录")
            return StockSnapshot(self.name, sku, qty=int(qty))
        except Exception as e:
            # 网络抖动 / 解析失败 → 标记为不可用（而不是抛异常中断整次同步）
            return StockSnapshot(self.name, sku, available=False,
                                 detail=type(e).__name__ + ": " + str(e))

    def health(self) -> bool:
        base = os.getenv("ERP_API_BASE", "")
        if not base or requests is None:
            return False
        try:
            resp = requests.get(f"{base.rstrip('/')}/healthz", timeout=self.TIMEOUT)
            return resp.status_code == 200
        except Exception:
            return False


# enabled=False 时 discovery 仍会注册，但默认查询（only_enabled=True）看不到它
PLUGIN = ErpProxySource
