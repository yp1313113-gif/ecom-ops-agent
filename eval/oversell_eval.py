"""超卖检测 · 三阶段评测。

对每条用例：
    1. 按用例数据写入 store
    2. 分别跑 v0 / v1 / v2
    3. 与 ground_truth 比对，累计 TP / FP / FN / TN

三个版本只差「一个变量」，保证对比公平：
    v0 baseline : 可售 = 仓库 − 安全库存                （★ 不减在途占用）
    v1 avail    : 可售 = 仓库 − 在途占用 − 安全库存      ＋ 平台水位【均分】
    v2 rules    : 同上，但平台水位取【规则库】（人工确认后沉淀）

指标：
    检出率 Recall    = TP / (TP + FN)   宁可多报别漏报（漏报 = 真赔钱）
    准确率 Precision = TP / (TP + FP)   误报太多，运营就不看告警了
    误报数 FP                           无风险用例被误判为风险的数量
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

import store
from tools.oversell_tool import check_oversell_naive, check_oversell
from eval.oversell_cases import CASES

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def seed_case(c: dict) -> None:
    store.init_db()
    store.reset()
    store.set_warehouse_stock(c["sku"], c["warehouse"])
    for plat, qty in c["platforms"].items():
        store.set_platform_inventory(plat, c["sku"], qty)
    for i, o in enumerate(c["orders"]):
        oid = o.get("order_id", f"{c['id']}-{i}")
        store.insert_order(oid, o["platform"], c["sku"],
                           o["qty"], o.get("status", "paid"))
    for r in c["rules"]:
        store.upsert_rule(c["sku"], r["platform"], r["max_ratio"], r.get("rationale", ""))


def run_case(c: dict, version: str) -> bool:
    sku = c["sku"]
    if version == "v0":
        return bool(check_oversell_naive(sku, safety_stock=c["safety_stock"]).data["alerted"])
    if version == "v1":
        return bool(check_oversell(sku, safety_stock=c["safety_stock"],
                                   use_rules=False).data["alerted"])
    return bool(check_oversell(sku, safety_stock=c["safety_stock"],
                               use_rules=True).data["alerted"])


def evaluate(version: str) -> dict:
    tp = fp = fn = tn = 0
    rows = []
    for c in CASES:
        seed_case(c)
        truth = c["ground_truth"]["risky"]
        alerted = run_case(c, version)
        if truth and alerted:
            tp += 1; verdict = "TP"
        elif truth and not alerted:
            fn += 1; verdict = "FN 漏检"
        elif not truth and alerted:
            fp += 1; verdict = "FP 误报"
        else:
            tn += 1; verdict = "TN"
        rows.append({"id": c["id"], "desc": c["desc"], "truth": truth,
                     "alerted": alerted, "verdict": verdict})
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    acc = (tp + tn) / len(CASES) if CASES else 0.0
    return {"version": version, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "recall": recall, "precision": precision, "accuracy": acc, "rows": rows}


def main() -> None:
    results = [evaluate(v) for v in ("v0", "v1", "v2")]

    print("=" * 68)
    print("超卖检测 · 三阶段评测")
    print("=" * 68)
    for r in results:
        print(f"\n[{r['version']}] TP={r['tp']} FP={r['fp']} FN={r['fn']} TN={r['tn']}"
              f"  检出率 {r['recall']*100:.0f}% / 准确率 {r['precision']*100:.0f}%"
              f" / 总准确 {r['accuracy']*100:.0f}%")
        for row in r["rows"]:
            if row["verdict"] not in ("TP", "TN"):
                print(f"    {row['id']} {row['verdict']}  {row['desc']}")

    print("\n" + "=" * 68)
    print(f"{'版本':<10}{'检出率':<10}{'准确率':<10}{'误报数':<8}{'漏检数':<8}")
    print("-" * 68)
    for r in results:
        print(f"{r['version']:<10}{r['recall']*100:>6.0f}%   {r['precision']*100:>6.0f}%   "
              f"{r['fp']:<8}{r['fn']:<8}")
    print("=" * 68)
    _write_report(results)


def _write_report(results: list) -> None:
    v0, v1, v2 = results
    lines = [
        "# 超卖检测 · 三阶段评测报告",
        "",
        "> 在 10 条仿真用例（6 条有风险 / 4 条安全，真值在造用例时写死）上对比三个版本。",
        "> 三个版本只差一个变量，保证可归因。",
        "",
        "## 1. 总览",
        "",
        "| 版本 | 说明 | 检出率 | 准确率 | 误报 | 漏检 |",
        "|---|---|---:|---:|---:|---:|",
        f"| v0 baseline | 可售 = 仓库 − 安全库存（**不减在途占用**） | {v0['recall']*100:.0f}% | {v0['precision']*100:.0f}% | {v0['fp']} | {v0['fn']} |",
        f"| v1 avail | 可售 = 仓库 − **在途占用** − 安全库存；平台水位**均分** | {v1['recall']*100:.0f}% | {v1['precision']*100:.0f}% | {v1['fp']} | {v1['fn']} |",
        f"| v2 rules | 同 v1，平台水位取**规则库**（人工确认后沉淀） | {v2['recall']*100:.0f}% | {v2['precision']*100:.0f}% | {v2['fp']} | {v2['fn']} |",
        "",
        "## 2. 逐条结果",
        "",
        "| 用例 | 描述 | 真值 | v0 | v1 | v2 |",
        "|---|---|---|---|---|---|",
    ]
    for i, c in enumerate(CASES):
        truth = "风险" if c["ground_truth"]["risky"] else "安全"
        cells = []
        for r in results:
            cells.append("告警" if r["rows"][i]["alerted"] else "—")
        lines.append(f"| {c['id']} | {c['desc']} | {truth} | " + " | ".join(cells) + " |")

    lines += [
        "",
        "## 3. 结论",
        "",
        "- **v0 的缺陷是漏检**：在有风险的用例里，只要「各平台展示合计」没超过仓库库存，",
        "  它就判定安全 —— 但它没算「已付款未发货」的在途占用。",
        "  这在业务上就是「看着还有货，其实早就卖超」。",
        "- **v1 修正了漏检，但引入了误报**：没有规则时只能按平台数均分水位，",
        "  遇到「某平台本来就是主战场」（C02 淘宝占 85%）就会误报。",
        "- **v2 用规则库消除误报**：水位来自人工确认后沉淀的业务事实，而不是拍脑袋均分。",
        "",
        "> 可复现：python -m eval.oversell_eval",
        "",
    ]
    with open("eval/oversell_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n报告已写入 eval/oversell_report.md")


if __name__ == "__main__":
    main()
