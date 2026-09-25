"""工具逻辑单元测试：覆盖六大工具的返回结构 + 校验逻辑。

运行：python -m pytest tests/test_tools.py -q
或：  python tests/test_tools.py

[升级] 同时验证 ToolResult 结构（不再仅看 summary 文本）：
    - success / data / warnings 三层都断言
    - 失败场景（输入不存在）也覆盖
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import (
    clean_sales_data,
    sync_orders,
    monitor_platforms,
    generate_daily_report,
    batch_process_images,
    backup_data,
)
from config import DATA_DIR, BACKUP_DIR


class TestTools(unittest.TestCase):
    def test_clean_sales_data(self):
        result = clean_sales_data()
        self.assertTrue(result.success)
        self.assertIn("数据清洗完成", result.to_text())
        self.assertGreater(result.data["raw_rows"], 0)
        self.assertGreaterEqual(result.data["raw_rows"], result.data["clean_rows"])
        self.assertTrue(os.path.exists(result.data["output_path"]))

    def test_sync_orders(self):
        """mock 数据里 8 单有 2 个缺对照 SKU, 失败率 25% 超阈值 -> 业务未达成."""
        result = sync_orders()
        self.assertIn("订单同步校验完成", result.to_text())
        self.assertIn("A008", result.data["missing_skus"])
        self.assertIn("A009", result.data["missing_skus"])
        self.assertGreater(len(result.warnings), 0, "应当有缺失 SKU 的 warning")
        self.assertGreater(len(result.errors), 0, "失败率超阈值应当升级为 errors")
        self.assertFalse(result.success, "失败率超阈值时 success 应当为 False")

    def test_sync_orders_healthy(self):
        """当所有 SKU 都能映射时, success=True 且无 errors."""
        # 用一个临时对照表覆盖全部订单 SKU
        import tempfile, csv, shutil
        from pathlib import Path
        tmp_map = Path(DATA_DIR) / "_all_skus.csv"
        try:
            with open(tmp_map, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["sku", "erp_code"])
                for sku in ["A001","A002","A003","A004","A005","A006","A008","A009"]:
                    w.writerow([sku, f"ERP-{sku}"])
            result = sync_orders(mapping_path=str(tmp_map))
            self.assertTrue(result.success)
            self.assertEqual(result.data["fail_rate"], 0.0)
            self.assertEqual(result.data["missing_skus"], [])
        finally:
            tmp_map.unlink(missing_ok=True)

    def test_monitor_platforms(self):
        result = monitor_platforms()
        self.assertTrue(result.success)
        self.assertIn("监控", result.to_text())
        # mock 数据：京东 A002 库存 8 < 10；抖音 A009 库存 0
        types = {a["type"] for a in result.data["alerts"]}
        self.assertIn("stock_low", types)
        self.assertGreater(result.data["alert_count"], 0)

    def test_generate_daily_report(self):
        result = generate_daily_report()
        self.assertTrue(result.success)
        self.assertIn("运营日报", result.to_text())
        self.assertTrue(result.data["output_path"].endswith(".xlsx"))
        # mock 数据中最新日期为 08-06, 只有 1 行 (A006 充电宝)
        self.assertEqual(result.data["order_count"], 1)
        self.assertGreater(result.data["total_sales"], 0)

    def test_batch_process_images(self):
        result = batch_process_images()
        self.assertTrue(result.success)
        self.assertIn("图片批处理完成", result.to_text())
        self.assertGreater(result.data["processed"], 0)
        self.assertTrue(os.path.isdir(result.data["output_dir"]))

    def test_backup_data(self):
        result = backup_data()
        self.assertTrue(result.success)
        self.assertIn("数据备份完成", result.to_text())
        self.assertTrue(os.path.isdir(result.data["target"]))
        self.assertGreater(result.data["size_bytes"], 0)

    # === 失败场景 ===
    def test_clean_sales_data_missing_file(self):
        result = clean_sales_data(input_path="data/__不存在__.csv")
        self.assertFalse(result.success)
        self.assertGreater(len(result.errors), 0)
        self.assertIn("找不到", result.to_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
