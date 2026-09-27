"""平台库存同步：遍历所有已注册的平台插件，拉取展示库存并落库。

━━━ 插件化的真实价值在这里，不在「少写几行」━━━
是**故障隔离**：

    淘宝接口挂了  →  抖音 / 拼多多 / 京东照常同步，
                     报告里写「淘宝：数据不可用」，
                     而不是整个任务失败、看板全空。

这正是多平台运营最怕的场景 —— 一个平台的接口抖动把整条链路拖垮。

━━━ 三态，不是二态 ━━━
每次拉取的结果分三种，**不能混为一谈**：

    · 正常写入   qty 有值          → 落库
    · 未上架     qty=None          → 跳过（不是故障，报它等于天天误告警）
    · 不可用     available=False   → 隔离 + 告警（不是 0！写 0 会凭空
                                     造出一个「展示库存 0」，还会改变
                                     按平台数均分的基数，污染超卖判定）

这个区分见 plugins/base.py 的 StockSnapshot。
"""
from __future__ import annotations

from tools.validators import ToolResult


def sync_platform_stock(sku: str | None = None,
                        platform: str | None = None) -> ToolResult:
    """从各平台插件拉取展示库存并写入本地 `platform_inventory`。

    每个平台独立拉取、独立记录成败：**一个平台不可用不影响其他平台。**

    Args:
        sku: 只同步某个 SKU；不传则同步全部已知 SKU
        platform: 只同步某个平台（如 taobao）；不传则同步全部已启用平台
    """
    import plugins
    import store

    plugins.discover()
    entries = plugins.platforms()
    if platform:
        entries = [(i, c) for i, c in entries if i.name == platform]
        if not entries:
            available = [i.name for i, _ in plugins.platforms(only_enabled=False)]
            return ToolResult(
                success=False,
                data={"available": available},
                errors=["未注册的平台：" + platform],
                summary="❌ 未注册的平台：" + platform + "（可用：" + str(available) + "）",
            )
    if not entries:
        return ToolResult(success=False, errors=["没有任何已启用的平台插件"],
                          summary="❌ 没有任何已启用的平台插件")

    skus = [sku] if sku else store.list_skus()
    if not skus:
        return ToolResult(success=True, data={"synced": 0, "skus": [], "failures": []},
                          summary="✅ 没有需要同步的 SKU（仓库/平台库存/订单都是空的）")

    synced = 0
    failures: list[dict] = []
    per_platform: dict[str, dict] = {}

    for s in skus:
        for info, cls in entries:
            slot = per_platform.setdefault(
                info.name, {"label": info.label, "ok": 0, "skipped": 0, "fail": 0})
            try:
                snap = cls().fetch_display_stock(s)
            except Exception as e:
                # ★ 插件抛异常也要被隔离 —— 一个平台不能拖垮整次同步
                failures.append({"platform": info.name, "label": info.label, "sku": s,
                                 "error": type(e).__name__ + ": " + str(e)})
                slot["fail"] += 1
                continue

            if not getattr(snap, "available", True):
                failures.append({"platform": info.name, "label": info.label, "sku": s,
                                 "error": getattr(snap, "detail", "不可用")})
                slot["fail"] += 1
                continue
            if snap.qty is None:
                # 未上架：既不是成功写入，也不是故障
                slot["skipped"] += 1
                continue

            store.set_platform_inventory(info.name, s, int(snap.qty))
            slot["ok"] += 1
            synced += 1

    ok_platforms = [v["label"] for v in per_platform.values() if v["fail"] == 0]
    bad_platforms = [v["label"] for v in per_platform.values() if v["fail"] > 0]

    lines = ["🔄 平台库存同步完成：" + str(synced) + " 条写入"
             "（" + str(len(skus)) + " 个 SKU × " + str(len(entries)) + " 个平台）"]
    for name, v in per_platform.items():
        flag = "✅" if v["fail"] == 0 else "⚠️"
        lines.append("  " + flag + " " + v["label"] + "（" + name + "）："
                     "写入 " + str(v["ok"]) + " / 跳过 " + str(v["skipped"])
                     + " / 失败 " + str(v["fail"]))
    if bad_platforms:
        lines.append("⚠️ 数据不完整的平台：" + "、".join(bad_platforms)
                     + "（**不影响其他平台**；超卖检测会把这些平台的缺口标记为"
                       "「数据不可用」，而不是当成 0）")

    return ToolResult(
        success=len(ok_platforms) > 0,
        data={"synced": synced, "skus": skus, "per_platform": per_platform,
              "failures": failures, "ok_platforms": ok_platforms,
              "degraded_platforms": bad_platforms},
        warnings=[str(len(failures)) + " 条拉取失败（已隔离，未影响其他平台）"] if failures else [],
        errors=[] if ok_platforms else ["所有平台都拉取失败"],
        summary="\n".join(lines),
    )


def list_platform_plugins() -> ToolResult:
    """列出当前注册了哪些平台插件（能力自描述，供 Agent 回答「你支持哪些平台」）。"""
    import plugins

    plugins.discover()
    rows = []
    for info, cls in plugins.platforms(only_enabled=False):
        rows.append({
            "name": info.name, "label": info.label, "enabled": info.enabled,
            "version": info.version, "description": info.description,
            "default_water_level": getattr(cls, "default_water_level", None),
            "module": info.module,
        })
    lines = ["当前注册 " + str(len(rows)) + " 个平台插件："]
    for r in rows:
        flag = "✅" if r["enabled"] else "⏸"
        lines.append("  " + flag + " " + r["label"] + "（" + r["name"] + "）v" + str(r["version"])
                     + "　默认水位 " + str(r["default_water_level"]) + "　" + r["description"])
    lines.append("\n（加一个平台 = 在 plugins/sources/ 加一个文件，主流程代码零改动）")
    enabled = [r["name"] for r in rows if r["enabled"]]
    return ToolResult(success=True, data={"plugins": rows, "enabled": enabled},
                      summary="\n".join(lines))


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print(list_platform_plugins().summary)
    print()
    import store
    store.seed_demo(quiet=True)
    print(sync_platform_stock().summary)
    print()
    health = __import__("plugins").health()
    print("插件健康检查：")
    for h in health:
        print("  " + ("✅" if h["healthy"] else "❌") + " [" + h["category"] + "] "
              + h["label"] + ("　" + h["detail"] if h["detail"] else ""))
