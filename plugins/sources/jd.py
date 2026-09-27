# plugins/sources/jd.py
"""京东 数据源插件。"""
from plugins.sources.local import LocalInventorySource


class JdSource(LocalInventorySource):
    name = "jd"
    label = "京东"
    description = "京东自营/POP，展示库存来自京麦后台同步"
    default_water_level = 0.2
    demo_stock = 20
    demo_order = 9


PLUGIN = JdSource
