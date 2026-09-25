"""超卖检测的仿真用例集（28 条）。

★★ 关键设计：每条用例都带 ground_truth（真值）★★
    真值在造用例时就写死 —— 这是"检出率"能成立的前提。
    没有真值，就是自己评自己，面试官一眼看穿。

判定口径（真值怎么来的）：
    可用 = 仓库 − 在途占用(paid + shipped) − 安全库存
    真值 risky = 各平台展示合计 > 可用

用例分组（每组专门暴露某一版实现的缺陷）：
    S 系列（安全）：任何版本都不该报「全局超卖」
        · 均匀分布            → 连均分水位也过得去
        · 单平台独占 + 规则    → ★ v1（均分）会误报
        · 退款 / 取消订单      → 不该占用库存
        · 同一订单重复推送     → 幂等性
        · 边界（展示 == 可用） → 持平视为安全
    R 系列（风险）：必须报出「全局超卖」
        · 在途占用型          → ★ v0（基线）会漏检
        · 展示即超型          → 一眼可见
        · 有规则但仍超        → 规则不是免死金牌
        · 边界（可用 + 1）    → 差一件也是超
"""
from __future__ import annotations


def _C(cid, desc, sku, warehouse, platforms, orders=None, rules=None,
       safety=5, risky=False, why=""):
    return {
        "id": cid, "desc": desc, "sku": sku,
        "warehouse": warehouse, "safety_stock": safety,
        "platforms": platforms, "orders": orders or [], "rules": rules or [],
        "ground_truth": {"risky": risky, "why": why},
    }


def _evens(n, per):
    """构造 {taobao:per, douyin:per, pdd:per, jd:per}。"""
    return dict(zip(["taobao", "douyin", "pdd", "jd"], [per] * n))


CASES = [
    # ================= S 系列 · 安全 =================
    _C("S01", "均匀分布·无规则", "A001", 100, _evens(4, 23),
       risky=False, why="可用 95（100−0−5），展示 92；均分水位 23 也过得去"),

    _C("S02", "淘宝独占·已确认 85%", "A002", 100,
       {"taobao": 80, "douyin": 5, "pdd": 5, "jd": 5},
       rules=[{"platform": "taobao", "max_ratio": 0.85, "rationale": "该 SKU 主战场在淘宝，人工确认水位 85%"}],
       risky=False, why="可用 95，展示 95 持平；淘宝占比高是业务事实 → v1 均分必误报"),

    _C("S03", "有在途·四平台已确认水位", "A003", 200,
       {"taobao": 40, "douyin": 30, "pdd": 20, "jd": 10},
       orders=[{"platform": "taobao", "qty": 30, "status": "paid"},
               {"platform": "douyin", "qty": 20, "status": "shipped"}],
       rules=[{"platform": "taobao", "max_ratio": 0.30, "rationale": "人工确认 30%"},
              {"platform": "douyin", "max_ratio": 0.25, "rationale": "人工确认 25%"},
              {"platform": "pdd",    "max_ratio": 0.20, "rationale": "人工确认 20%"},
              {"platform": "jd",     "max_ratio": 0.15, "rationale": "人工确认 15%"}],
       risky=False, why="可用 145（200−50−5），展示 100，充足"),

    _C("S04", "退款订单不占库存", "A004", 100, _evens(4, 23),
       orders=[{"platform": "taobao", "qty": 50, "status": "refunded"}],
       risky=False, why="退款订单不计入在途 → 可用仍为 95，展示 92"),

    _C("S05", "取消订单不占库存", "A005", 100, _evens(4, 23),
       orders=[{"platform": "taobao", "qty": 80, "status": "cancelled"}],
       risky=False, why="取消订单不计入在途 → 可用仍为 95，展示 92"),

    _C("S06", "同一订单重复推送·幂等", "A006", 100, _evens(4, 20),
       orders=[{"order_id": "DUP-1", "platform": "taobao", "qty": 10, "status": "paid"},
               {"order_id": "DUP-1", "platform": "taobao", "qty": 10, "status": "paid"}],
       risky=False, why="两条重复推送只算一次 → 在途 10，可用 85，展示 80"),

    _C("S07", "全部已发货·仓库充足", "A007", 300, _evens(4, 40),
       orders=[{"platform": "taobao", "qty": 100, "status": "shipped"}],
       risky=False, why="已发货仍占用 → 可用 195，展示 160，充足"),

    _C("S08", "边界·展示刚好等于可用", "A008", 100,
       {"taobao": 25, "douyin": 25, "pdd": 24, "jd": 21},
       rules=[{"platform": "taobao", "max_ratio": 0.30, "rationale": "均衡水位"},
              {"platform": "douyin", "max_ratio": 0.30, "rationale": "均衡水位"},
              {"platform": "pdd",    "max_ratio": 0.30, "rationale": "均衡水位"},
              {"platform": "jd",     "max_ratio": 0.30, "rationale": "均衡水位"}],
       risky=False, why="可用 95，展示 95 持平（≤ 视为安全）→ v1 均分 23 会误报"),

    _C("S09", "超宽松水位", "A009", 500, _evens(4, 100),
       safety=10, risky=False, why="可用 490，展示 400，余量巨大"),

    _C("S10", "有在途·均匀调整后安全", "A010", 150, _evens(4, 28),
       orders=[{"platform": "taobao", "qty": 30, "status": "paid"}],
       risky=False, why="可用 115（150−30−5），展示 112，刚好在均分水位 28 内"),

    _C("S11", "天猫独占·已确认 40%", "A011", 250,
       {"taobao": 95, "douyin": 50, "pdd": 50, "jd": 50},
       rules=[{"platform": "taobao", "max_ratio": 0.40, "rationale": "人工确认 40%"},
              {"platform": "douyin", "max_ratio": 0.21, "rationale": "人工确认 21%"},
              {"platform": "pdd",    "max_ratio": 0.21, "rationale": "人工确认 21%"},
              {"platform": "jd",     "max_ratio": 0.21, "rationale": "人工确认 21%"}],
       risky=False, why="可用 245，展示 245 持平；各平台均在已确认水位内 → v1 均分 61 会误报"),

    # ================= R 系列 · 风险 =================
    _C("R01", "在途占大头（v0 漏检）", "A101", 100,
       {"taobao": 30, "douyin": 10, "pdd": 5, "jd": 5},
       orders=[{"platform": "taobao", "qty": 60, "status": "paid"}],
       risky=True, why="可用 35（100−60−5），展示 50 → 超 15；但展示 50 ≤ 仓库 100，v0 会漏"),

    _C("R02", "小幅超（v0 漏检）", "A102", 100,
       {"taobao": 20, "douyin": 20, "pdd": 20, "jd": 10},
       orders=[{"platform": "taobao", "qty": 30, "status": "paid"}],
       risky=True, why="可用 65（100−30−5），展示 70 → 超 5"),

    _C("R03", "在途刚好顶破（v0 漏检）", "A103", 120,
       {"taobao": 40, "douyin": 30, "pdd": 20, "jd": 10},
       orders=[{"platform": "pdd", "qty": 30, "status": "paid"}],
       risky=True, why="可用 85（120−30−5），展示 100 → 超 15"),

    _C("R04", "展示即超仓库", "A104", 80,
       {"taobao": 50, "douyin": 40, "pdd": 30, "jd": 20},
       risky=True, why="展示 140 > 仓库 80，一眼可见"),

    _C("R05", "有规则但仍超", "A105", 100,
       {"taobao": 90, "douyin": 20, "pdd": 10, "jd": 5},
       rules=[{"platform": "taobao", "max_ratio": 0.85, "rationale": "历史水位"}],
       risky=True, why="可用 95，展示 125；且淘宝 90 > 80.75 的已确认水位"),

    _C("R06", "边界·展示比可用多 1", "A106", 100,
       {"taobao": 30, "douyin": 25, "pdd": 20, "jd": 21},
       risky=True, why="可用 95，展示 96 → 差一件也是超"),

    _C("R07", "大额在途", "A107", 200, _evens(4, 20),
       orders=[{"platform": "taobao", "qty": 150, "status": "paid"}],
       risky=True, why="可用 45（200−150−5），展示 80 → 超 35"),

    _C("R08", "已发货占用", "A108", 100, _evens(4, 15),
       orders=[{"platform": "taobao", "qty": 60, "status": "shipped"}],
       risky=True, why="已发货仍占用 → 可用 35，展示 60 → 超 25"),

    _C("R09", "混合状态订单", "A109", 120, _evens(4, 20),
       orders=[{"platform": "taobao", "qty": 40, "status": "paid"},
               {"platform": "douyin", "qty": 20, "status": "shipped"},
               {"platform": "pdd", "qty": 100, "status": "cancelled"}],
       risky=True, why="取消的不算 → 可用 55（120−60−5），展示 80 → 超 25"),

    _C("R10", "安全库存为 0 仍超", "A110", 100, _evens(4, 30),
       safety=0, risky=True, why="可用 100，展示 120 → 超 20"),

    _C("R11", "多平台极端不均", "A111", 200,
       {"taobao": 150, "douyin": 20, "pdd": 20, "jd": 20},
       risky=True, why="可用 195，展示 210 → 超 15"),

    _C("R12", "退款后又被买走", "A112", 100, _evens(4, 10),
       orders=[{"platform": "taobao", "qty": 50, "status": "refunded"},
               {"platform": "douyin", "qty": 70, "status": "paid"}],
       risky=True, why="退款不占、新单占用 → 可用 25（100−70−5），展示 40 → 超 15"),

    _C("R13", "小幅超·安全库存 10", "A113", 100, _evens(4, 17),
       safety=10, orders=[{"platform": "taobao", "qty": 25, "status": "paid"}],
       risky=True, why="可用 65（100−25−10），展示 68 → 超 3"),

    _C("R14", "展示远超", "A114", 50, _evens(4, 30),
       risky=True, why="可用 45，展示 120 → 超 75"),

    _C("R15", "仓库为零", "A115", 0, _evens(4, 5),
       safety=0, risky=True, why="可用 0，展示 20 → 全超"),

    _C("R16", "在途占一半", "A116", 100, _evens(4, 15),
       safety=0, orders=[{"platform": "taobao", "qty": 50, "status": "paid"}],
       risky=True, why="可用 50，展示 60 → 超 10"),

    _C("R17", "在途 + 展示双重超标", "A117", 150,
       {"taobao": 40, "douyin": 30, "pdd": 30, "jd": 30},
       orders=[{"platform": "pdd", "qty": 40, "status": "paid"}],
       risky=True, why="可用 105（150−40−5），展示 130 → 超 25"),
]


def stats() -> dict:
    risky = sum(1 for c in CASES if c["ground_truth"]["risky"])
    return {"total": len(CASES), "risky": risky, "safe": len(CASES) - risky}


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    s = stats()
    print(f"用例总数 {s['total']}｜有风险 {s['risky']}｜无风险 {s['safe']}")
    for c in CASES:
        tag = "风险" if c["ground_truth"]["risky"] else "安全"
        print(f"  {c['id']} [{tag}] {c['desc']}")
        print(f"       {c['ground_truth']['why']}")
