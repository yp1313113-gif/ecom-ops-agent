# plugins/sources/taobao.py
"""淘宝 数据源插件。"""
from plugins.sources.local import LocalInventorySource


class TaobaoSource(LocalInventorySource):
    name = "taobao"
    label = "淘宝"
    description = "淘宝/天猫店铺，展示库存来自卖家后台同步"
    default_water_level = 0.3
    demo_stock = 50
    demo_order = 12


PLUGIN = TaobaoSource
