"""偏好记忆层：跨会话记住用户 / 租户级的设置与习惯。

[为什么需要这一层]
    ecom-ops-agent 原本是"无状态"的 —— 每次对话都从零开始。
    用户说「以后安全库存统一按 10 算」，下次它还是用 5，得再说一遍。

[三层记忆的分工]（写进 README 的设计口径）
    ① 会话记忆  —— 对话上下文，随会话结束失效            （agent 层，thread_id）
    ② 偏好记忆  —— 用户 / 租户级设置，跨会话长期有效       ← 本模块
    ③ 业务记忆  —— 实体级规则，跟着 SKU 走                （store.water_level_rules）

[两个关键设计取舍]
    · scope 作用域：global / platform:taobao / sku:A001
      为什么需要？「安全库存默认 10」和「A001 在淘宝的水位」不是一个粒度，
      混在一张无作用域的表里，早晚会互相覆盖。

    · source 来源：user_confirmed / inferred
      为什么需要？用户明确说的可以直接当默认值用；
      系统自己推断的**不能** —— 否则一次误判会被永久固化成"事实"。
      这就是「记忆污染」的入口，所以在读取侧就要把闸门设好（recall 默认只认 user_confirmed）。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from typing import Any

import store

# 允许被记住的 key 白名单 —— 防止 Agent 往记忆里塞任意字段（记忆污染的第一道闸）
ALLOWED_KEYS = {
    "default_safety_stock",   # 安全库存默认值
    "alert_channel",          # 告警推送通道
    "active_platforms",       # 在售平台
    "default_rules_enabled",  # 是否默认套用规则库
}

SOURCE_USER = "user_confirmed"
SOURCE_INFERRED = "inferred"


def init_db() -> None:
    store.init_db()
    conn = store.get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS preferences (
            scope      TEXT NOT NULL,
            key        TEXT NOT NULL,
            value      TEXT NOT NULL,
            source     TEXT NOT NULL DEFAULT 'user_confirmed',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (scope, key)
        );
        """
    )
    conn.commit()
    conn.close()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def remember(scope: str, key: str, value: Any, source: str = SOURCE_USER) -> None:
    """写入一条记忆。

    Args:
        scope: global / platform:xxx / sku:xxx
        key: 必须是 ALLOWED_KEYS 之一（白名单，防任意字段入库）
        value: 字符串、数字、列表都可以（内部统一 JSON 序列化，读出来还是原类型）
        source: user_confirmed（用户明确说的）/ inferred（系统推断的）
    """
    if key not in ALLOWED_KEYS:
        raise KeyError(f"不允许记住的配置项：{key}，可选 {sorted(ALLOWED_KEYS)}")
    if source not in (SOURCE_USER, SOURCE_INFERRED):
        raise ValueError(f"未知来源：{source}")

    init_db()
    conn = store.get_db()
    conn.execute(
        """INSERT INTO preferences (scope, key, value, source, updated_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT (scope, key) DO UPDATE SET value = excluded.value,
                                                  source = excluded.source,
                                                  updated_at = excluded.updated_at""",
        (scope, key, json.dumps(value, ensure_ascii=False), source, _now()),
    )
    conn.commit()
    conn.close()


def recall(scope: str, key: str, default: Any = None,
           allow_inferred: bool = False) -> Any:
    """读取一条记忆。

    ★ 默认只认 user_confirmed —— 系统推断出来的值不作为默认值使用，
      避免一次误判被固化成"事实"。
    """
    init_db()
    conn = store.get_db()
    row = conn.execute(
        "SELECT value, source FROM preferences WHERE scope = ? AND key = ?", (scope, key)
    ).fetchone()
    conn.close()
    if not row:
        return default
    if row["source"] == SOURCE_INFERRED and not allow_inferred:
        return default
    try:
        return json.loads(row["value"])
    except Exception:
        return row["value"]


def resolve(key: str, default: Any = None, extra_scopes: tuple[str, ...] = ()) -> Any:
    """按「精确作用域 → global → 默认值」的顺序取配置。

    例如查安全库存：
        resolve("default_safety_stock", 5, extra_scopes=("sku:A001",))
        → 先看 sku:A001 有没有单独设置，再看 global，最后用 5
    """
    for s in extra_scopes:
        v = recall(s, key, None)
        if v is not None:
            return v
    v = recall("global", key, None)
    return default if v is None else v


def forget(scope: str, key: str | None = None) -> int:
    """删除记忆。key 为空则清空该作用域下所有记忆。返回删除条数。"""
    init_db()
    conn = store.get_db()
    if key:
        cur = conn.execute("DELETE FROM preferences WHERE scope = ? AND key = ?", (scope, key))
    else:
        cur = conn.execute("DELETE FROM preferences WHERE scope = ?", (scope,))
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n


def list_preferences() -> list[dict[str, Any]]:
    init_db()
    conn = store.get_db()
    rows = conn.execute(
        "SELECT scope, key, value, source, updated_at FROM preferences ORDER BY scope, key"
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["value"] = json.loads(d["value"])
        except Exception:
            pass
        out.append(d)
    return out


# ============ 便捷读取（供业务工具直接用） ============

def default_safety_stock(sku: str | None = None) -> int:
    """安全库存默认值。

    作用域优先级：sku:<sku>  >  global  >  项目默认 5

    Args:
        sku: 传了就先看这个 SKU 有没有单独设置
    """
    scopes = (f"sku:{sku}",) if sku else ()
    v = resolve("default_safety_stock", 5, extra_scopes=scopes)
    try:
        return int(v)
    except Exception:
        return 5


def alert_channel() -> str | None:
    return recall("global", "alert_channel", None)


def active_platforms() -> list[str] | None:
    return recall("global", "active_platforms", None)


# ============ Agent 工具入口 ============

def _coerce(value: str):
    """LLM 传进来的都是字符串；能解析成 JSON 就还原成原始类型。"""
    try:
        return json.loads(value)
    except Exception:
        return value


def remember_preference(key: str, value: str, scope: str = "global") -> str:
    """记住一条长期有效的设置（跨会话生效），下次不用再交代。

    可用 key（白名单）：
      - default_safety_stock：安全库存默认值（整数）
      - alert_channel：告警推送通道（wecom / feishu / dingtalk）
      - active_platforms：在售平台列表，如 ["taobao","douyin"]
      - default_rules_enabled：是否默认套用水位规则库（true/false）

    Args:
        key: 设置名
        value: 设置值（字符串；列表请写成 JSON，如 ["taobao","douyin"]）
        scope: 作用域，默认 global；也可指定 platform:taobao 或 sku:A001
    """
    v = _coerce(value)
    remember(scope, key, v)
    return f"✅ 已记住：[{scope}] {key} = {v}（下次会自动生效）"


def recall_preference(key: str, scope: str = "global") -> str:
    """读取一条已记住的设置。

    Args:
        key: 设置名
        scope: 作用域，默认 global
    """
    v = recall(scope, key, None)
    if v is None:
        v = recall("global", key, None)
    if v is None:
        return f"（没有记住 [{scope}] {key}）"
    return f"[{scope}] {key} = {v}"


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print("=== 偏好记忆演示 ===")
    forget("global")
    print("1) 初始（未记住任何设置）")
    print("   default_safety_stock ->", default_safety_stock())

    print("\n2) 用户说：「以后安全库存统一按 10 算」")
    remember("global", "default_safety_stock", 10)
    print("   default_safety_stock ->", default_safety_stock())

    print("\n3) 用户说：「我们只做淘宝和抖音，告警推企业微信」")
    remember("global", "active_platforms", ["taobao", "douyin"])
    remember("global", "alert_channel", "wecom")
    print("   active_platforms ->", active_platforms())
    print("   alert_channel    ->", alert_channel())

    print("\n4) 系统想「推断」一个值（不该被当默认值用）")
    remember("global", "default_safety_stock", 99, source=SOURCE_INFERRED)
    print("   recall(默认, 只认 user_confirmed) ->", default_safety_stock())
    print("   recall(allow_inferred=True)       ->",
          recall("global", "default_safety_stock", allow_inferred=True))

    print("\n5) 作用域优先级：sku:A001 单独设置 20")
    remember("global", "default_safety_stock", 10)
    remember("sku:A001", "default_safety_stock", 20)
    print("   resolve(无额外作用域) ->", resolve("default_safety_stock", 5))
    print("   resolve(sku:A001)     ->", resolve("default_safety_stock", 5, ("sku:A001",)))

    print("\n6) 白名单拦截（防止记忆污染）")
    try:
        remember("global", "api_key", "xxx")
    except KeyError as e:
        print("   拦截成功：", e)

    print("\n当前记忆：")
    for p in list_preferences():
        print(f"   [{p['scope']}] {p['key']} = {p['value']}  ({p['source']})")
