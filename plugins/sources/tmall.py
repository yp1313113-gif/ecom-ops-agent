# plugins/sources/tmall.py
"""天猫 数据源插件。"""
from plugins.sources.local import LocalInventorySource


class TmallSource(LocalInventorySource):
    name = "tmall"
    label = "天猫"
    description = "天猫旗舰店；演示「加一个平台 = 加一个文件」（默认库存 0）"
    default_water_level = 0.35
    demo_stock = 0
    demo_order = 0


PLUGIN = TmallSource
