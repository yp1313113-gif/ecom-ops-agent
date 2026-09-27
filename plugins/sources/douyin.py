# plugins/sources/douyin.py
"""抖音 数据源插件。"""
from plugins.sources.local import LocalInventorySource


class DouyinSource(LocalInventorySource):
    name = "douyin"
    label = "抖音"
    description = "抖音小店，展示库存来自抖店后台同步"
    default_water_level = 0.25
    demo_stock = 40
    demo_order = 15


PLUGIN = DouyinSource
