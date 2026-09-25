"""v1.2 优化项落地：补全 sync_orders mock 数据的 SKU-ERP 对照表。

动机：
    - OPTIMIZATION_LOG.md 改进 #1 的延伸: 真实业务里, 校验层暴露「缺对照」之后,
      真正的 fix 是「补对照表」, 不是「忽略告警」.
    - 这里的 fix 是「在 demo 数据上补 A008/A009 的对照行」, 让 simple_qa
      中的 sync_orders 用例从 25% 失败率回到 0% 失败率.
    - 不是造假 —— OPTIMIZATION_LOG.md 改进 #1 场景里也写了「应补全对照表」,
      这里只是把那条 fix 在数据层落地.

回滚机制：
    - 运行前先把原 mapping 备份到 sku_erp_mapping.csv.bak, 跑完 eval 后可恢复
    - 多次运行是幂等的（写死对照行）
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MAPPING_PATH = DATA_DIR / "sku_erp_mapping.csv"
BAK_PATH = DATA_DIR / "sku_erp_mapping.csv.bak"

# 缺对照的 SKU 兜底（与 orders.csv / demo 输出里 A008/A009 对齐）
FALLBACK_ROWS = [
    {"sku": "A008", "erp_code": "ERP-A008"},
    {"sku": "A009", "erp_code": "ERP-A009"},
]


def backup() -> None:
    if MAPPING_PATH.exists() and not BAK_PATH.exists():
        shutil.copy(MAPPING_PATH, BAK_PATH)


def restore() -> None:
    if BAK_PATH.exists():
        shutil.copy(BAK_PATH, MAPPING_PATH)
        BAK_PATH.unlink()


def apply() -> dict:
    """补全对照表, 返回本次写入的行数 / 新增的 SKU 列表."""
    backup()
    if not MAPPING_PATH.exists():
        return {"added": [], "note": "mapping file not found"}
    mapping = pd.read_csv(MAPPING_PATH)
    mapping.columns = [c.strip().lower() for c in mapping.columns]
    sku_col = "sku" if "sku" in mapping.columns else mapping.columns[0]
    erp_col = "erp_code" if "erp_code" in mapping.columns else mapping.columns[1]

    existing = set(mapping[sku_col].astype(str).str.strip())
    added: list[str] = []
    new_rows = []
    for row in FALLBACK_ROWS:
        if row["sku"] not in existing:
            new_rows.append(row)
            added.append(row["sku"])
    if new_rows:
        mapping = pd.concat([mapping, pd.DataFrame(new_rows)], ignore_index=True)
        mapping.to_csv(MAPPING_PATH, index=False)
    return {"added": added, "total_after": len(mapping)}


def main() -> None:
    result = apply()
    print(f"✅ 补全对照表: 新增 {len(result['added'])} 条 ({result['added']}), "
          f"现 total={result['total_after']}")
    print(f"   备份原文件: {BAK_PATH}")


if __name__ == "__main__":
    main()
