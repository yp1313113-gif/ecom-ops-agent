"""库存 / 订单 / 规则 的数据访问层（SQLite）。

设计动机（面试口径）：
    超卖检测的本质是「多平台数据一致性」问题 —— 数据散在 4 个平台，
    各自只知道自己那一份，谁都不知道全局还剩多少。
    所以在写检测逻辑之前，必须先有一个「全局可对账的数据视图」。

    本项目之前的数据是硬编码常量（_MOCK_EXPENSES 那类），
    工具调用完只在内存里返回一句字符串 —— 重启即丢、跨 Agent 读不到。
    这一层把业务数据落库，让「填进去的东西别人能读到」成立。

表设计：
    platform_inventory  各平台展示库存快照（定时拉取）
    orders              订单（含「已付款未发货」—— 超卖检测的关键输入）
    warehouse_stock     仓库实际库存（真值来源）
    water_level_rules   平台库存水位规则（闭环沉淀的资产）

    前 3 张是「过程数据」，最后 1 张是「资产」—— 它会随使用不断增值。
"""
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timedelta
from typing import Any

import config

# Windows 控制台默认 GBK，打印 emoji / 中文会 UnicodeEncodeError。
# 统一改成 UTF-8，避免脚本在 cmd / PowerShell 里直接崩。
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

DB_PATH = os.path.join(config.DATA_DIR, "ops.db")

# 订单状态中「占用库存」的那些 —— 已付款但还没发货，货还在仓库但已被预定
STOCK_OCCUPYING_STATUSES = ("paid", "shipped")


# ============ 连接与建表 ============

def get_db() -> sqlite3.Connection:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS platform_inventory (
            platform    TEXT NOT NULL,
            sku         TEXT NOT NULL,
            qty         INTEGER NOT NULL,
            snapshot_at TEXT NOT NULL,
            PRIMARY KEY (platform, sku)
        );

        CREATE TABLE IF NOT EXISTS orders (
            order_id   TEXT PRIMARY KEY,
            platform   TEXT NOT NULL,
            sku        TEXT NOT NULL,
            qty        INTEGER NOT NULL,
            status     TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS warehouse_stock (
            sku        TEXT PRIMARY KEY,
            qty        INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS water_level_rules (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            sku        TEXT NOT NULL,
            platform   TEXT NOT NULL,
            max_ratio  REAL NOT NULL,
            rationale  TEXT DEFAULT '',
            hit_count  INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            UNIQUE (sku, platform)
        );

        CREATE INDEX IF NOT EXISTS idx_orders_sku  ON orders (sku, status);
        CREATE INDEX IF NOT EXISTS idx_rules_sku   ON water_level_rules (sku);
        """
    )
    conn.commit()
    conn.close()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ============ 平台库存 ============

def set_platform_inventory(platform: str, sku: str, qty: int, snapshot_at: str | None = None) -> None:
    conn = get_db()
    conn.execute(
        """INSERT INTO platform_inventory (platform, sku, qty, snapshot_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT (platform, sku) DO UPDATE SET qty = excluded.qty,
                                                     snapshot_at = excluded.snapshot_at""",
        (platform, sku, int(qty), snapshot_at or _now()),
    )
    conn.commit()
    conn.close()


def list_platform_inventory(sku: str | None = None) -> list[dict[str, Any]]:
    conn = get_db()
    if sku:
        rows = conn.execute(
            "SELECT * FROM platform_inventory WHERE sku = ? ORDER BY platform", (sku,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM platform_inventory ORDER BY sku, platform"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============ 订单 ============

def insert_order(order_id: str, platform: str, sku: str, qty: int,
                 status: str = "paid", created_at: str | None = None) -> None:
    conn = get_db()
    conn.execute(
        """INSERT INTO orders (order_id, platform, sku, qty, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT (order_id) DO UPDATE SET status = excluded.status""",
        (order_id, platform, sku, int(qty), status, created_at or _now()),
    )
    conn.commit()
    conn.close()


def list_orders(sku: str | None = None,
                statuses: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    conn = get_db()
    sql = "SELECT * FROM orders WHERE 1=1"
    params: list[Any] = []
    if sku:
        sql += " AND sku = ?"
        params.append(sku)
    if statuses:
        placeholders = ",".join("?" for _ in statuses)
        sql += f" AND status IN ({placeholders})"
        params.extend(statuses)
    rows = conn.execute(sql + " ORDER BY created_at", params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def in_transit_qty(sku: str) -> int:
    """在途占用 = 已付款/已发货但未完成的订单数量之和。

    ★ 这是超卖检测里最容易被漏掉的一项 —— 见 oversell_tool 的说明。
    """
    conn = get_db()
    placeholders = ",".join("?" for _ in STOCK_OCCUPYING_STATUSES)
    row = conn.execute(
        f"SELECT COALESCE(SUM(qty), 0) AS n FROM orders WHERE sku = ? AND status IN ({placeholders})",
        (sku, *STOCK_OCCUPYING_STATUSES),
    ).fetchone()
    conn.close()
    return int(row["n"]) if row else 0


# ============ 仓库库存 ============

def set_warehouse_stock(sku: str, qty: int) -> None:
    conn = get_db()
    conn.execute(
        """INSERT INTO warehouse_stock (sku, qty, updated_at) VALUES (?, ?, ?)
           ON CONFLICT (sku) DO UPDATE SET qty = excluded.qty,
                                           updated_at = excluded.updated_at""",
        (sku, int(qty), _now()),
    )
    conn.commit()
    conn.close()


def get_warehouse_stock(sku: str) -> int | None:
    conn = get_db()
    row = conn.execute("SELECT qty FROM warehouse_stock WHERE sku = ?", (sku,)).fetchone()
    conn.close()
    return int(row["qty"]) if row else None


# ============ 水位规则（闭环沉淀的资产） ============

def upsert_rule(sku: str, platform: str, max_ratio: float, rationale: str = "") -> int:
    conn = get_db()
    conn.execute(
        """INSERT INTO water_level_rules (sku, platform, max_ratio, rationale, created_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT (sku, platform) DO UPDATE SET max_ratio = excluded.max_ratio,
                                                     rationale = excluded.rationale""",
        (sku, platform, float(max_ratio), rationale, _now()),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM water_level_rules WHERE sku = ? AND platform = ?", (sku, platform)
    ).fetchone()
    conn.close()
    return int(row["id"]) if row else -1


def find_rules(sku: str) -> list[dict[str, Any]]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM water_level_rules WHERE sku = ? ORDER BY platform", (sku,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def touch_rule(rule_id: int) -> None:
    """规则被命中一次 —— hit_count 是「规则库在起作用」的证据。"""
    conn = get_db()
    conn.execute("UPDATE water_level_rules SET hit_count = hit_count + 1 WHERE id = ?", (rule_id,))
    conn.commit()
    conn.close()


def rule_stats() -> dict[str, Any]:
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) AS rules, COALESCE(SUM(hit_count), 0) AS hits FROM water_level_rules"
    ).fetchone()
    conn.close()
    return {"rules": int(row["rules"]), "hits": int(row["hits"])}


# ============ 演示数据与重置 ============

def reset() -> None:
    """清空业务数据（规则库也清）—— 评测脚本每轮开头调用。"""
    conn = get_db()
    for t in ("platform_inventory", "orders", "warehouse_stock", "water_level_rules"):
        conn.execute(f"DELETE FROM {t}")
    conn.commit()
    conn.close()


def reset_rules() -> None:
    """只清规则库 —— 用来跑「规则库从空到满」的闭环对比。"""
    conn = get_db()
    conn.execute("DELETE FROM water_level_rules")
    conn.commit()
    conn.close()


def seed_demo(quiet: bool = False) -> None:
    """造一份最小可演示数据：一个 SKU 在 4 个平台卖，但总量超了。

    Args:
        quiet: True 时不打印，供 demo / app 反复调用。
    """
    init_db()
    reset()

    sku = "A001"
    set_warehouse_stock(sku, 80)          # 仓库只有 80 件
    set_platform_inventory("taobao", sku, 50)
    set_platform_inventory("douyin", sku, 40)
    set_platform_inventory("pdd",    sku, 30)
    set_platform_inventory("jd",     sku, 20)
    # 4 个平台展示合计 140 件 > 仓库 80 件 —— 展示层面就已经超了

    base = datetime.now() - timedelta(hours=6)
    plan = [
        ("T001", "taobao", 12),
        ("D001", "douyin", 15),
        ("P001", "pdd",    18),
        ("J001", "jd",      9),
    ]
    for i, (oid, plat, qty) in enumerate(plan):
        insert_order(oid, plat, sku, qty, "paid",
                     (base + timedelta(minutes=10 * i)).strftime("%Y-%m-%d %H:%M:%S"))

    if not quiet:
        print(f"✅ 演示数据已写入 {DB_PATH}")
        print(f"   仓库库存 {get_warehouse_stock(sku)} / 在途占用 {in_transit_qty(sku)}")
        print(f"   平台展示合计 {sum(r['qty'] for r in list_platform_inventory(sku))}")


if __name__ == "__main__":
    seed_demo()
