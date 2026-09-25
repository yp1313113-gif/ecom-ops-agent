"""订单同步工具：校验 SKU↔ERP 编码对照，检测同步异常。

对应实习工作：建立平台 SKU 与 ERP 的动态对照表 + 校验流程，
把订单同步失败率降低 70%+。

[升级] 返回 ToolResult; 失败率超阈值（20%）只是业务告警，
     不是工具本身的失败 —— 让 Agent 决定下一步是补对照还是干预。
"""
import os
import pandas as pd

from config import DATA_DIR
from tools.validators import (
    ToolResult,
    validate_tool,
    positive_int,
)


FAIL_RATE_THRESHOLD = 20.0  # 失败率超过 20% 视为高风险，写入 errors（工具未达成业务目标）


@validate_tool(
    schema={"total": positive_int},
    required_data_keys=("total", "synced", "failed", "fail_rate", "missing_skus"),
)
def sync_orders(orders_path: str | None = None, mapping_path: str | None = None) -> ToolResult:
    """校验订单 SKU 是否都能映射到 ERP 编码，输出同步对账报告。"""
    ord_path = orders_path or os.path.join(DATA_DIR, "orders.csv")
    map_path = mapping_path or os.path.join(DATA_DIR, "sku_erp_mapping.csv")

    if not os.path.exists(ord_path):
        return ToolResult(
            success=False,
            errors=[f"找不到订单文件：{ord_path}"],
            summary=f"❌ 找不到订单文件：{ord_path}",
        )
    if not os.path.exists(map_path):
        return ToolResult(
            success=False,
            errors=[f"找不到 SKU-ERP 对照表：{map_path}"],
            summary=f"❌ 找不到 SKU-ERP 对照表：{map_path}",
        )

    orders = pd.read_csv(ord_path)
    mapping = pd.read_csv(map_path)
    mapping = mapping.rename(columns={c: c.strip().lower() for c in mapping.columns})
    sku_col = "sku" if "sku" in mapping.columns else mapping.columns[0]
    erp_col = "erp_code" if "erp_code" in mapping.columns else mapping.columns[1]
    valid_skus = set(mapping[sku_col].astype(str).str.strip())

    orders = orders.rename(columns={c: c.strip().lower() for c in orders.columns})
    o_sku_col = "sku" if "sku" in orders.columns else orders.columns[0]
    orders[o_sku_col] = orders[o_sku_col].astype(str).str.strip()

    total = len(orders)
    synced = orders[o_sku_col].isin(valid_skus).sum()
    failed = total - synced
    fail_rate = (failed / total * 100) if total else 0.0
    missing_skus = sorted(set(orders[o_sku_col]) - valid_skus)

    report_lines = [
        "✅ 订单同步校验完成",
        f"  · 订单总数：{total}",
        f"  · 成功映射（已同步）：{synced}",
        f"  · 同步失败（缺对照）：{failed}",
        f"  · 失败率：{fail_rate:.1f}%",
    ]
    warnings: list[str] = []
    errors: list[str] = []
    if missing_skus:
        report_lines.append("  · 缺失对照的 SKU：")
        for s in missing_skus[:20]:
            report_lines.append(f"      - {s}")
        if len(missing_skus) > 20:
            report_lines.append(f"      ... 共 {len(missing_skus)} 个")
        warnings.append(f"存在 {len(missing_skus)} 个未映射 SKU, 建议补全对照表")
    else:
        report_lines.append("  · 全部 SKU 均有 ERP 对照，同步健康 ✅")

    # 业务级硬阈值：失败率过高视为业务未达成
    success = fail_rate < FAIL_RATE_THRESHOLD
    if not success:
        errors.append(
            f"订单同步失败率 {fail_rate:.1f}% 超过阈值 {FAIL_RATE_THRESHOLD:.0f}%, "
            f"建议立即补全 SKU-ERP 对照表"
        )

    return ToolResult(
        success=success,
        data={
            "total": total,
            "synced": synced,
            "failed": failed,
            "fail_rate": fail_rate,
            "missing_skus": missing_skus,
        },
        warnings=warnings,
        errors=errors,
        summary="\n".join(report_lines),
    )
