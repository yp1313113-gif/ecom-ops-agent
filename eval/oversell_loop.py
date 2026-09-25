"""超卖防护 · 闭环指标评测（人工介入率曲线）。

核心命题（也是简历上"闭环"两个字的证据）：
    系统不是"第一次就准"，而是"越用越不需要人"。

模型（贴近真实运营节奏）：
    · 电商每天都有新 SKU 上架 —— 每轮引入 new_per_round 个新 SKU
    · 每轮巡检「已确认过的历史 SKU + 新 SKU」（新老交错，避免某一轮全是安全品）
    · 巡检中报出风险的 SKU：
        - 已有水位规则（人工确认过） → 系统自动给出建议 → 【自动】
        - 没有规则                    → 必须人工确认水位     → 【人工介入】
    · 人工确认后，水位规则沉淀入库 —— 下一轮它就自动了

指标：
    人工介入率 = 本轮需人工确认数 / 本轮告警数

预期曲线：单调下降，趋近于「新 SKU 占比」
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, ".")

import store
from tools.oversell_tool import check_oversell
from eval.oversell_cases import CASES

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

NEW_PER_ROUND = 2
ROUNDS = 12


def _interleaved_pool() -> list[dict]:
    """风险用例与安全用例交错 —— 保证每一轮都有量可看，不出现"整轮零告警"。"""
    risky = [c for c in CASES if c["ground_truth"]["risky"]]
    safe = [c for c in CASES if not c["ground_truth"]["risky"]]
    pool: list[dict] = []
    for i in range(max(len(risky), len(safe))):
        if i < len(risky):
            pool.append(risky[i])
        if i < len(safe):
            pool.append(safe[i])
    return pool


def _seed(case: dict) -> None:
    store.set_warehouse_stock(case["sku"], case["warehouse"])
    for plat, qty in case["platforms"].items():
        store.set_platform_inventory(plat, case["sku"], qty)
    for i, o in enumerate(case["orders"]):
        oid = o.get("order_id", f"{case['id']}-{i}")
        store.insert_order(oid, o["platform"], case["sku"], o["qty"], o.get("status", "paid"))


def _human_confirm(case: dict, available: int) -> None:
    """模拟人工确认：按当前各平台实际占比 + 5% 余量拍板一个水位。

    真实场景里这一步是运营/主管看着数据做决定；
    这里用「实际占比 + 余量」代替，因为人工的结论就是"按现状留一点缓冲"。
    """
    avail = available if available > 0 else 1
    for plat, shown in case["platforms"].items():
        ratio = min(0.95, round(shown / avail + 0.05, 3))
        store.upsert_rule(case["sku"], plat, ratio, "人工确认水位")


def simulate(rounds: int = ROUNDS, new_per_round: int = NEW_PER_ROUND) -> list[dict]:
    store.init_db()
    store.reset()

    pool = _interleaved_pool()
    confirmed: list[dict] = []
    confirmed_skus: set[str] = set()
    rows: list[dict] = []

    for r in range(1, rounds + 1):
        start = (r - 1) * new_per_round
        fresh = pool[start:start + new_per_round]
        if not fresh and not confirmed:
            break

        scanned = len(confirmed) + len(fresh)
        alerts = auto = manual = 0

        for case in list(confirmed) + fresh:
            _seed(case)
            res = check_oversell(case["sku"], safety_stock=case["safety_stock"], use_rules=True)
            if not res.data["alerted"]:
                continue
            alerts += 1
            if case["sku"] in confirmed_skus:          # ★ 快照集合，避免本轮新增被误判为自动
                auto += 1
            else:
                manual += 1
                _human_confirm(case, int(res.data["available"]))
                confirmed.append(case)
                confirmed_skus.add(case["sku"])

        rate = (manual / alerts) if alerts else 0.0
        rows.append({"round": r, "scanned": scanned, "alerts": alerts,
                     "auto": auto, "manual": manual, "rate": rate})
        print(f"第 {r} 轮｜巡检 {scanned:>2} 个 SKU｜告警 {alerts:>2}"
              f"｜自动 {auto:>2}｜人工 {manual:>2}｜人工介入率 {rate*100:>5.0f}%")
    return rows


def plot(rows: list[dict]) -> str | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
        matplotlib.rcParams["axes.unicode_minus"] = False
    except Exception as e:
        print(f"（未安装 matplotlib，跳过绘图：{e}）")
        return None

    xs = [r["round"] for r in rows]
    ys = [r["rate"] * 100 for r in rows]
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=140)
    ax.plot(xs, ys, marker="o", color="#b45309", linewidth=2)
    for x, y in zip(xs, ys):
        ax.annotate(f"{y:.0f}%", (x, y), textcoords="offset points",
                    xytext=(0, 8), ha="center", fontsize=9)
    ax.set_xlabel(f"巡检轮次（每轮新增 {NEW_PER_ROUND} 个 SKU）")
    ax.set_ylabel("人工介入率 (%)")
    ax.set_title("超卖防护 · 人工介入率随规则库积累而下降")
    ax.set_ylim(-8, 115)
    ax.grid(alpha=0.3)
    out = os.path.join("docs", "assets", "oversell_loop.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fig.tight_layout()
    fig.savefig(out)
    print(f"\n图已保存：{out}")
    return out


def main() -> None:
    print("=" * 66)
    print("超卖防护 · 闭环指标（人工介入率）")
    print("=" * 66)
    rows = simulate()
    print("\n" + "=" * 66)
    plot(rows)
    print("\n" + "=" * 66)
    print(f"{'轮次':<8}{'巡检':<8}{'告警':<8}{'自动':<8}{'人工':<8}{'介入率':<8}")
    print("-" * 66)
    for r in rows:
        print(f"{r['round']:<8}{r['scanned']:<8}{r['alerts']:<8}{r['auto']:<8}"
              f"{r['manual']:<8}{r['rate']*100:>5.0f}%")
    print("=" * 66)

    lines = [
        "# 超卖防护 · 闭环指标（人工介入率）",
        "",
        f"> 模型：每轮新增 {NEW_PER_ROUND} 个 SKU 上架，巡检「已确认历史 SKU + 新 SKU」（风险/安全用例交错）。",
        "> 告警中已有水位规则的自动处理，没有的必须人工确认；确认后规则沉淀，下轮转自动。",
        "",
        "| 轮次 | 巡检 SKU | 告警 | 自动 | 人工 | 人工介入率 |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(f"| {r['round']} | {r['scanned']} | {r['alerts']} | {r['auto']} | "
                     f"{r['manual']} | {r['rate']*100:.0f}% |")
    lines += [
        "",
        "> 可复现：python -m eval.oversell_loop",
        "",
        "![人工介入率曲线](../docs/assets/oversell_loop.png)",
        "",
    ]
    with open("eval/oversell_loop_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("报告已写入 eval/oversell_loop_report.md")


if __name__ == "__main__":
    main()
