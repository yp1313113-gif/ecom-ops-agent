"""电商运营自动化 Agent 的工具集。

每个工具都是独立可测的纯函数，对应一项真实业务：
  - clean_sales_data      数据清洗（替代手工 Excel）
  - sync_orders           订单同步校验（SKU↔ERP 对照）
  - monitor_platforms     多平台监控告警（爬虫 + 推送）
  - generate_daily_report 日报自动化（取数 → Excel → 推送）
  - batch_process_images  图片批处理（缩略 + 水印）
  - backup_data           数据备份（本地 + 网盘异地）
  - oversell_check        ★ 单 SKU 超卖风险检测（可用库存 − 在途占用）
  - oversell_scan         ★ 全量超卖巡检
"""
from tools.sales_data_tool import clean_sales_data
from tools.order_sync_tool import sync_orders
from tools.monitor_tool import monitor_platforms
from tools.report_tool import generate_daily_report
from tools.image_tool import batch_process_images
from tools.backup_tool import backup_data
from tools.oversell_tool import oversell_check, oversell_scan
from tools.platform_sync_tool import sync_platform_stock, list_platform_plugins
from memory import remember_preference, recall_preference

__all__ = [
    "clean_sales_data",
    "sync_orders",
    "monitor_platforms",
    "generate_daily_report",
    "batch_process_images",
    "backup_data",
    "oversell_check",
    "oversell_scan",
    "sync_platform_stock",
    "list_platform_plugins",
    "remember_preference",
    "recall_preference",
]
