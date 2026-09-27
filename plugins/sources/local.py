# plugins/sources/local.py
"""本地库存数据源：展示库存来自本地 `platform_inventory` 表。

这是四个内置平台插件的共同基类。数据可以是 CSV 导入 / mock 种子 / 定时同步 ——
对插件接口来说都一样。

**为什么要有这一层基类**：让每个平台插件文件只剩「元信息」，
把「怎么读」这个实现细节收在一处。否则 5 个平台插件会有 5 份一模一样的代码，
那就不是插件化，只是把重复代码拆散了。
"""
from __future__ import annotations

from plugins.base import PlatformPlugin, StockSnapshot


class LocalInventorySource(PlatformPlugin):
    """从本地 platform_inventory 表读展示库存。"""

    # 演示种子数据（store.seed_demo 用）—— 加一个平台插件，演示数据里自动出现
    demo_stock: int = 20
    demo_order: int = 5

    def fetch_display_stock(self, sku: str) -> StockSnapshot:
        try:
            import store      # 延迟导入：避免 store 与 plugins 循环依赖
            rows = store.list_platform_inventory(sku)
        except Exception as e:
            # 读不到 → available=False，**不抛异常**
            return StockSnapshot(self.name, sku, available=False,
                                 detail="本地库存表不可读: " + type(e).__name__)

        for row in rows:
            if row["platform"] == self.name:
                return StockSnapshot(self.name, sku, qty=int(row["qty"]))
        # 该平台上没有这个 SKU 的记录 → 未上架（不是 0，也不是故障）
        return StockSnapshot(self.name, sku, qty=None,
                             detail="本地库存表中无该平台记录（未上架）")

    def health(self) -> bool:
        try:
            import store
            store.get_db().close()
            return True
        except Exception:
            return False
