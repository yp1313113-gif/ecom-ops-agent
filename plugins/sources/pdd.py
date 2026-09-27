# plugins/sources/pdd.py
"""拼多多 数据源插件。"""
from plugins.sources.local import LocalInventorySource


class PddSource(LocalInventorySource):
    name = "pdd"
    label = "拼多多"
    description = "拼多多店铺，展示库存来自商家后台同步"
    default_water_level = 0.2
    demo_stock = 30
    demo_order = 18


PLUGIN = PddSource
