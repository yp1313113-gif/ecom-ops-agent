"""超卖风险检测工具。

[业务背景]
    一个 SKU 在多个平台同时销售时，各平台库存相互独立 ——
    谁都不知道「全局还剩多少可卖」。超卖由此产生。
    代价：平台赔付（订单额约 30%）+ 差评 + 店铺降权（最贵的是降权，掉流量）。

[核心公式]
    可用库存   = 仓库实际库存 − 在途订单占用 − 安全库存
    超卖风险量 = 各平台展示库存合计 − 可用库存

[为什么必须减「在途订单占用」—— 本工具存在的理由]
    已付款未发货的订单：货还在仓库（所以仓库库存还没减），
    但已经被卖掉了（所以不能再算作可售）。
    朴素实现两边都漏 → 「看着还有货，其实早就卖超」。
    这是绝大多数超卖事故的真实成因。

[三阶段演进 —— 与 eval/oversell_report.md 的对比口径一致]
    v0 naive : 只比「展示合计 vs 仓库库存」             → 漏检多（把在途占用整段漏掉）
    v1 avail : 用「可用库存」判断 + 各平台水位均分        → 检出率高，但均分导致误报
    v2 rules : 用规则库里的真实水位（人工确认后沉淀）      → 误报下降
"""
from __future__ import annotations

from typing import Any

from tools.validators import ToolResult
import memory
import store

# 安全库存：不参与售卖、留给退换货/破损的缓冲
DEFAULT_SAFETY_STOCK = 5

# 风险等级阈值（超卖风险量占可用库存的比例）
RED_RATIO = 0.30
YELLOW_RATIO = 0.05


def _available(sku: str, safety_stock: int) -> tuple[int, int, int, int]:
    """返回 (可用库存, 仓库库存, 在途占用, 安全库存)。"""
    wh = store.get_warehouse_stock(sku)
    if wh is None:
        wh = 0
    transit = store.in_transit_qty(sku)
    avail = wh - transit - safety_stock
    return avail, wh, transit, safety_stock


def _shown(sku: str) -> dict[str, int]:
    """各平台当前展示库存 {platform: qty}。"""
    return {r["platform"]: int(r["qty"]) for r in store.list_platform_inventory(sku)}


def _level(risk_qty: int, available: int) -> str:
    if risk_qty <= 0:
        return "green"
    base = available if available > 0 else 1
    ratio = risk_qty / base
    if ratio >= RED_RATIO:
        return "red"
    if ratio >= YELLOW_RATIO:
        return "yellow"
    return "green"


# ============ v0 · baseline（对照组，用于评测） ============

def check_oversell_naive(sku: str, safety_stock: int = 0) -> ToolResult:
    """v0 baseline：只比「各平台展示合计 vs 仓库库存」，完全忽略在途订单占用。

    这不是"错误实现"，而是一个**看起来很合理**的朴素实现 ——
    正是因为它合理，才会被广泛使用，也才会漏掉真正的超卖。
    """
    wh = store.get_warehouse_stock(sku) or 0
    avail = wh - safety_stock          # 只减安全库存；★ 不减在途占用 —— 这就是它的缺陷
    shown = _shown(sku)
    shown_total = sum(shown.values())
    risk_qty = shown_total - avail
    level = _level(risk_qty, avail)

    detail = [
        {"platform": p, "shown": q, "limit": None, "over": False}
        for p, q in sorted(shown.items())
    ]
    alerts = []
    if risk_qty > 0:
        alerts.append(
            f"各平台展示合计 {shown_total} 超过可售 {avail}"
            f"（仓库 {wh} − 安全库存 {safety_stock}），风险量 {risk_qty}"
        )

    return ToolResult(
        success=True,
        data={
            "sku": sku,
            "mode": "naive",
            "warehouse_qty": wh,
            "in_transit": None,          # ★ baseline 不算这一项
            "safety_stock": safety_stock,
            "available": avail,
            "shown_total": shown_total,
            "risk_qty": max(0, risk_qty),
            "risk_level": level,
            "alerts": alerts,
            "platform_detail": detail,
            "rules_hit": 0,
            "alerted": bool(risk_qty > 0),
        },
        warnings=alerts,
        summary=("⚠️ 检测到超卖风险：" if risk_qty > 0 else "✅ 未发现超卖风险：")
                + f"{sku} 展示合计 {shown_total} / 可售 {avail}（未计在途占用）",
    )


# ============ v1 / v2 · 正确实现 ============

def check_oversell(sku: str, safety_stock: int | None = None,
                   use_rules: bool = True) -> ToolResult:
    """检测某 SKU 的超卖风险。

    Args:
        sku: 商品编码
        safety_stock: 安全库存缓冲；不传则读「偏好记忆」里的默认值（再退回项目默认 5）
        use_rules: True=v2（按规则库的真实水位判定）；False=v1（各平台按均分水位判定）
    """
    safety_stock = memory.default_safety_stock(sku) if safety_stock is None else int(safety_stock)
    available, wh, transit, safety = _available(sku, safety_stock)
    shown = _shown(sku)
    shown_total = sum(shown.values())
    risk_qty = shown_total - available
    level = _level(risk_qty, available)

    # ---- 平台级水位 ----
    rules = store.find_rules(sku) if use_rules else []
    rule_map = {r["platform"]: r for r in rules}
    platforms = sorted(shown.keys())
    # 没有规则时按平台数均分（这就是 v1 误报的来源）
    even_ratio = (1.0 / len(platforms)) if platforms else 0.0

    detail: list[dict[str, Any]] = []
    alerts: list[str] = []
    rules_hit = 0

    for p in platforms:
        shown_q = shown[p]
        rule = rule_map.get(p)
        if rule:
            ratio = float(rule["max_ratio"])
            source = "rule"
            store.touch_rule(int(rule["id"]))
            rules_hit += 1
        else:
            ratio = even_ratio
            source = "even_split"

        limit = max(0, int(available * ratio))
        over = shown_q > limit
        detail.append({
            "platform": p, "shown": shown_q, "limit": limit,
            "ratio": round(ratio, 4), "source": source, "over": over,
        })
        if over:
            alerts.append(f"[{p}] 展示 {shown_q} 超过水位上限 {limit}（{source}）")

    if risk_qty > 0:
        alerts.insert(0, f"全局超卖风险：展示合计 {shown_total} 超过可用库存 {available}，缺口 {risk_qty}")

    summary_lines = [
        ("⚠️ 检测到超卖风险" if level != "green" else "✅ 未发现超卖风险") + f"：{sku}",
        f"  · 仓库库存：{wh}",
        f"  · 在途占用：{transit}（已付款未发货 —— baseline 会漏掉这一项）",
        f"  · 安全库存：{safety}",
        f"  · 可用库存：{available}",
        f"  · 平台展示合计：{shown_total}",
        f"  · 风险等级：{level}（规则命中 {rules_hit} 条）",
    ]
    for a in alerts:
        summary_lines.append(f"  - {a}")

    return ToolResult(
        success=True,
        data={
            "sku": sku,
            "mode": "rules" if use_rules else "avail",
            "warehouse_qty": wh,
            "in_transit": transit,
            "safety_stock": safety,
            "available": available,
            "shown_total": shown_total,
            "risk_qty": max(0, risk_qty),
            "risk_level": level,
            "alerts": alerts,
            "platform_detail": detail,
            "rules_hit": rules_hit,
            "alerted": bool(risk_qty > 0 or any(d["over"] for d in detail)),
        },
        warnings=alerts,
        summary="\n".join(summary_lines),
    )


def scan_all_oversell(safety_stock: int | None = None,
                      use_rules: bool = True) -> ToolResult:
    """扫描所有有库存记录的 SKU，汇总超卖风险（供 Agent 一键巡检）。

    safety_stock 不传时读偏好记忆里的默认值。
    """
    # 不在这里统一解析 —— 交给 check_oversell 按 SKU 逐条解析，
    # 这样 sku:xxx 级别的偏好才能各自生效。
    conn_skus = {r["sku"] for r in store.list_platform_inventory()}
    results = [check_oversell(s, safety_stock, use_rules) for s in sorted(conn_skus)]
    risky = [r for r in results if r.data["risk_level"] != "green"]
    total_gap = sum(r.data["risk_qty"] for r in results)

    lines = [f"📊 超卖巡检完成：{len(results)} 个 SKU，{len(risky)} 个有风险，总缺口 {total_gap} 件"]
    for r in risky:
        d = r.data
        lines.append(f"  · {d['sku']}｜可用 {d['available']} / 展示 {d['shown_total']}"
                     f"｜缺口 {d['risk_qty']}｜{d['risk_level']}")

    return ToolResult(
        success=True,
        data={"scanned": len(results), "risky": len(risky), "total_gap": total_gap},
        warnings=[f"{len(risky)} 个 SKU 存在超卖风险"] if risky else [],
        summary="\n".join(lines),
    )


# ============ Agent 工具入口 ============
# 上面两个函数返回 ToolResult（给评测脚本用）；
# 下面两个是交给 LLM Agent 调用的入口 —— 转成人类可读文本，便于模型理解与复述。

def oversell_check(sku: str, safety_stock: int | None = None) -> str:
    """检查某个 SKU 的多平台超卖风险。

    计算可用库存（仓库 − 在途占用 − 安全库存），与各平台展示库存比对，
    返回缺口数量、风险等级与建议水位。

    Args:
        sku: 商品编码，例如 A001
        safety_stock: 安全库存缓冲，默认 5
    """
    return check_oversell(sku, safety_stock=safety_stock, use_rules=True).to_text()


def oversell_scan_demo() -> ToolResult:
    """演示入口：先写入演示数据，再全量巡检（供 demo.py / app.py 零参数调用）。"""
    store.seed_demo(quiet=True)
    return scan_all_oversell()


def oversell_scan(safety_stock: int | None = None) -> str:
    """扫描全部 SKU 的多平台超卖风险，返回有风险的 SKU 清单与总缺口件数。

    Args:
        safety_stock: 安全库存缓冲，默认 5
    """
    return scan_all_oversell(safety_stock=safety_stock, use_rules=True).to_text()


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    store.seed_demo()
    print("\n--- v0 baseline（忽略在途占用）---")
    print(check_oversell_naive("A001").summary)
    print("\n--- v1 可用库存 + 均分水位 ---")
    print(check_oversell("A001", use_rules=False).summary)
    print("\n--- v2 可用库存 + 规则水位（规则库为空）---")
    print(check_oversell("A001", use_rules=True).summary)
