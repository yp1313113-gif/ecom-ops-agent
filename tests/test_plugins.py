# tests/test_plugins.py
"""插件化的测试。

重点验证的是**隔离性与三态语义**，这是插件化真正的价值所在：

  1. 单个插件模块导入失败，不能影响其他插件被发现；
  2. 单个平台拉取失败，不能影响其他平台同步（故障隔离）；
  3. 「未上架」与「不可用」必须区分 —— 前者跳过，后者告警；
     **绝不能把「不可用」当成 0 写库**（那会污染按平台数均分的基数）；
  4. 健康检查必须真的检查（历史上它在类上调 `health()`，每个都报
     `missing 'self'`，看起来在检查其实什么都没查）。
"""
import os

import pytest

import plugins as P
from plugins.registry import PluginRegistry
from plugins.base import PlatformPlugin, StockSnapshot


# ---------- 注册表 ----------

def test_registry_register_and_get():
    reg = PluginRegistry()
    reg.register("demo", "a", object(), label="A")
    assert reg.get("demo", "a") is not None
    assert reg.names("demo") == ["a"]
    assert reg.get("demo", "nope") is None


def test_registry_duplicate_overwrites_without_crash():
    reg = PluginRegistry()
    reg.register("demo", "a", "first")
    reg.register("demo", "a", "second")     # 应告警但不崩
    assert reg.get("demo", "a") == "second"


def test_registry_enabled_filter():
    reg = PluginRegistry()
    reg.register("demo", "on", object(), enabled=True)
    reg.register("demo", "off", object(), enabled=False)
    assert reg.names("demo") == ["on"]
    assert reg.names("demo", only_enabled=False) == ["off", "on"]


def test_discovery_survives_broken_module(tmp_path, monkeypatch):
    """★ 一个插件模块导入就炸，不能连累其他插件被发现。"""
    pkg = tmp_path / "fakeplug"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "good.py").write_text(
        "class G:\n    name = 'good'\n    label = 'Good'\n    enabled = True\nPLUGIN = G\n",
        encoding="utf-8")
    (pkg / "bad.py").write_text("raise RuntimeError('导入就炸')\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))

    reg = PluginRegistry()
    n = reg.discover("fakeplug", "x")
    assert n == 1
    assert reg.names("x") == ["good"]


def test_discovery_skips_underscore_modules():
    reg = PluginRegistry()
    # 真实的 plugins.sources 里有 _local 之外的 local（无 PLUGIN），应被跳过
    reg.discover("plugins.sources", "platform")
    assert "local" not in reg.names("platform", only_enabled=False)
    assert "taobao" in reg.names("platform")


# ---------- 三态快照 ----------

def test_stock_snapshot_three_states():
    ok = StockSnapshot("taobao", "A001", qty=50)
    assert ok.available and ok.qty == 50

    not_listed = StockSnapshot("taobao", "A001", qty=None)
    assert not_listed.available and not_listed.qty is None      # 未上架

    down = StockSnapshot("taobao", "A001", available=False, detail="超时")
    assert not down.available                                    # 不可用


def test_local_source_not_found_is_not_listed(tmp_path, monkeypatch):
    """本地源查不到记录 → 未上架（available=True + qty=None），不是故障、也不是 0。"""
    import store
    store.init_db()
    store.reset()
    store.set_warehouse_stock("Z999", 10)

    cls = P.get_platform("taobao")
    snap = cls().fetch_display_stock("Z999")
    assert snap.available is True
    assert snap.qty is None         # ★ 不能是 0 —— 那会凭空造出一条展示记录


def test_local_source_found_returns_qty():
    import store
    store.init_db()
    store.reset()
    store.set_platform_inventory("taobao", "Z001", 42)
    snap = P.get_platform("taobao")().fetch_display_stock("Z001")
    assert snap.available and snap.qty == 42


# ---------- 健康检查 ----------

def test_health_instantiates_classes():
    """回归：health() 曾在**类**上调用，导致每个平台都报 missing 'self'。"""
    results = P.health()
    platforms = [r for r in results if r["category"] == "platform"]
    assert platforms
    for r in platforms:
        assert "missing" not in r["detail"], f"{r['name']} 健康检查没有实例化: {r['detail']}"


def test_health_isolates_failures(monkeypatch):
    """单个插件探活抛异常，不能影响其他插件的检查结果。"""
    from plugins.registry import PluginRegistry
    reg = PluginRegistry()

    class Boom:
        name = "boom"

        def health(self):
            raise RuntimeError("探活炸了")

    class Fine:
        name = "fine"

        def health(self):
            return True

    reg.register("x", "boom", Boom)
    reg.register("x", "fine", Fine)
    res = {r["name"]: r for r in reg.health()}
    assert res["fine"]["healthy"] is True
    assert res["boom"]["healthy"] is False
    assert "RuntimeError" in res["boom"]["detail"]


# ---------- 同步工具：故障隔离 ----------

@pytest.fixture()
def clean_db():
    import store
    store.init_db()
    store.reset()
    yield
    store.reset()


@pytest.fixture()
def restore_registry():
    """测试期间往全局注册表加插件后，用完恢复原状。"""
    before_p = dict(P.registry._plugins.get("platform", {}))
    before_i = dict(P.registry._infos.get("platform", {}))
    yield
    P.registry._plugins["platform"] = before_p
    P.registry._infos["platform"] = before_i


def test_sync_isolates_failing_platform(clean_db, restore_registry):
    """★ 核心不变量：一个平台挂了，其他平台照常同步。"""
    import store
    from tools.platform_sync_tool import sync_platform_stock

    store.set_warehouse_stock("B001", 100)
    store.set_platform_inventory("taobao", "B001", 30)
    store.set_platform_inventory("douyin", "B001", 20)

    class BoomSource(PlatformPlugin):
        name = "boom"
        label = "爆炸平台"

        def fetch_display_stock(self, sku):
            raise RuntimeError("接口挂了")

    P.registry.register("platform", "boom", BoomSource, label="爆炸平台")

    res = sync_platform_stock(sku="B001")
    assert res.success is True                      # 整体仍然成功
    assert res.data["synced"] == 2                  # 淘宝 + 抖音 都同步了
    assert "爆炸平台" in res.data["degraded_platforms"]
    assert res.data["per_platform"]["taobao"]["ok"] == 1
    assert res.data["per_platform"]["boom"]["fail"] == 1


def test_sync_unavailable_platform_does_not_write_zero(clean_db, restore_registry):
    """★ 不可用**不能**被写成 0 —— 那会凭空造出一条「展示库存 0」的记录，
    并改变「按平台数均分」的基数，污染超卖判定。"""
    import store
    from tools.platform_sync_tool import sync_platform_stock

    store.set_warehouse_stock("C001", 100)
    store.set_platform_inventory("taobao", "C001", 30)

    class DownSource(PlatformPlugin):
        name = "down"
        label = "不可用平台"

        def fetch_display_stock(self, sku):
            return StockSnapshot(self.name, sku, available=False, detail="网络超时")

    P.registry.register("platform", "down", DownSource, label="不可用平台")

    res = sync_platform_stock(sku="C001")
    rows = {r["platform"]: r["qty"] for r in store.list_platform_inventory("C001")}
    assert "down" not in rows, "不可用的平台被写进了库存表"
    assert res.data["per_platform"]["down"]["fail"] == 1


def test_sync_not_listed_is_skipped_not_failed(clean_db, restore_registry):
    """未上架（qty=None）既不算写入也不算失败 —— 报成失败会天天误告警。"""
    import store
    from tools.platform_sync_tool import sync_platform_stock

    store.set_warehouse_stock("D001", 100)
    store.set_platform_inventory("taobao", "D001", 30)

    res = sync_platform_stock(sku="D001")
    tmall = res.data["per_platform"]["tmall"]
    assert tmall["skipped"] == 1
    assert tmall["fail"] == 0
    assert "天猫" not in res.data["degraded_platforms"]


def test_sync_unknown_platform_returns_error(clean_db):
    from tools.platform_sync_tool import sync_platform_stock
    res = sync_platform_stock(sku="A001", platform="not_exist")
    assert res.success is False
    assert "not_exist" in res.summary


def test_sync_no_skus(clean_db):
    from tools.platform_sync_tool import sync_platform_stock
    res = sync_platform_stock()
    assert res.success is True
    assert res.data["synced"] == 0


# ---------- 能力自描述 ----------

def test_list_platform_plugins_describes_all():
    from tools.platform_sync_tool import list_platform_plugins
    res = list_platform_plugins()
    names = [p["name"] for p in res.data["plugins"]]
    for expected in ("taobao", "douyin", "pdd", "jd", "tmall"):
        assert expected in names
    # 未启用的也列出来（能力自描述要完整），但 enabled 字段区分
    assert "erp_proxy" in names
    erp = next(p for p in res.data["plugins"] if p["name"] == "erp_proxy")
    assert erp["enabled"] is False


def test_notifiers_are_reflected_into_registry():
    P.discover()
    names = P.registry.names("notifier", only_enabled=False)
    assert set(names) == {"wecom", "feishu", "dingtalk"}


# ---------- 演示计划来自插件表 ----------

def test_demo_plan_comes_from_plugins():
    import store
    plan = store._demo_plan()
    names = [p[0] for p in plan]
    assert "taobao" in names and "douyin" in names
    # 天猫 demo_stock=0 且 demo_order=0 → 不参与演示种子
    assert "tmall" not in names


def test_seed_demo_keeps_known_totals():
    """回归：种子数据的总量不能因为插件化而变。"""
    import store
    store.seed_demo(quiet=True)
    rows = {r["platform"]: r["qty"] for r in store.list_platform_inventory("A001")}
    assert sum(rows.values()) == 140
    assert store.get_warehouse_stock("A001") == 80
    assert store.in_transit_qty("A001") == 54
    assert "tmall" not in rows          # 天猫不播种，避免改变均分基数


def test_list_skus_unions_three_sources():
    import store
    store.seed_demo(quiet=True)
    store.set_warehouse_stock("ONLY_WH", 5)
    store.insert_order("ORD_ONLY", "taobao", "ONLY_ORDER", 1, "paid")
    skus = store.list_skus()
    assert "A001" in skus and "ONLY_WH" in skus and "ONLY_ORDER" in skus
    assert skus == sorted(skus)
