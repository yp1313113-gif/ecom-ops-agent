# 插件化：一个扩展点一个模块

把「扩展点」变成同一个概念：**一类扩展点 = 一个 category，一个实现 = 一个模块。**
主流程代码零改动就能加平台。

> 实现：`plugins/`（`registry.py` / `base.py` / `sources/`）｜观测：`list_platform_plugins()`

---

## 为什么要做

这个项目原来只有一类扩展点做成了适配器（推送通道），其余是硬编码：

| 扩展点 | 原来 | 现在 |
|---|---|---|
| **平台数据源** | 平台名写死在 `store.seed_demo` 里，加平台要改代码 | `plugins/sources/*.py`，**加平台 = 加一个文件** |
| 推送通道 | 已经是适配器（`notifier.py`） | 反射注册进同一个注册表（**不为统一而重写**） |
| 模型厂商 | 只有 DeepSeek | 反射注册（同上） |

━━━ 关键：插件化的价值不在「少写几行」━━━

而在**故障隔离**。多平台运营最怕的场景是：

    淘宝的接口抖了一下  →  整个巡检任务失败  →  看板全空  →  没人知道到底有没有超卖

有了插件层之后，每个平台独立拉取、独立记录成败：

    淘宝接口挂了  →  抖音 / 拼多多 / 京东照常同步，
                     报告里写「淘宝：数据不可用」，
                     而不是整条链路一起挂。

---

## 目录结构

~~~text
plugins/
├── __init__.py        对外门面：discover / platforms / describe / health
├── registry.py        通用注册表：注册 · 自动发现 · 查询 · 健康检查
├── base.py            扩展点接口：PlatformPlugin / NotifierPlugin / ModelPlugin
└── sources/           平台数据源插件（自动发现）
    ├── local.py       LocalInventorySource —— 四个内置平台的共同基类
    ├── taobao.py      仅声明元信息（name / label / 水位 / 演示种子）
    ├── douyin.py
    ├── pdd.py
    ├── jd.py
    ├── tmall.py       演示「加一个平台 = 加一个文件」
    └── rest_api.py    真实 API 接入模板（默认 disabled）
~~~

**为什么要有 `local.py` 这一层基类**：让每个平台插件文件只剩「元信息」。
否则 5 个平台插件会有 5 份一模一样的读库代码 —— 那不是插件化，只是把重复代码拆散了。

---

## 加一个平台要做什么

就在 `plugins/sources/` 下加一个文件：

~~~python
# plugins/sources/taobao.py
from plugins.sources.local import LocalInventorySource

class TaobaoSource(LocalInventorySource):
    name = "taobao"
    label = "淘宝"
    description = "淘宝/天猫店铺，展示库存来自卖家后台同步"
    default_water_level = 0.30
    demo_stock = 50      # 演示种子数据
    demo_order = 12

PLUGIN = TaobaoSource
~~~

然后自动发生这些事：

~~~mermaid
flowchart LR
    F["新增 plugins/sources/xxx.py"] --> D["registry.discover()<br/>扫描目录 + 读 PLUGIN"]
    D --> L["list_platform_plugins()<br/>能力自描述里出现"]
    D --> S["sync_platform_stock()<br/>同步时自动纳入"]
    D --> SD["store.seed_demo()<br/>演示数据自动多一个平台"]
    D --> H["health()<br/>健康检查自动覆盖"]
~~~

**主流程代码一行不改。**

---

## 三态语义：StockSnapshot

这是整个插件接口里最需要说清楚的一点 —— **不能用 `int | None` 糊过去**：

| 业务情况 | 表达 | 调用方该怎么处理 |
|---|---|---|
| 正常读到 | `StockSnapshot(qty=N)` | 落库 |
| 这个平台**没上架**这个 SKU | `StockSnapshot(qty=None, available=True)` | **跳过**（不是故障） |
| 这个平台**读不到**（网络/鉴权/超时） | `StockSnapshot(available=False)` | **隔离 + 告警** |

━━━ 混在一起会怎样 ━━━

用 `None` 一锅端的话，必然滑向两种错误之一：

**① 把「读不到」当成 0 写进库。**
这会凭空造出一条「展示库存 0」的记录。更隐蔽的后果是：
v1 的均分水位是 `1 / len(platforms)` —— 多一行假的 0，
**均分的分母就变了**，超卖判定跟着错。这类 bug 不会报错，只会让结果悄悄偏掉。

**② 把「未上架」报成故障。**
结果是天天误告警，最后没人看告警 —— 这比不告警更糟。

所以插件接口明确约定：**不要抛异常**，不可用是一种正常的业务状态。

---

## 通用注册表

~~~python
registry.register(category, name, obj, label=..., enabled=...)
registry.get(category, name)
registry.names(category, only_enabled=True)
registry.discover(package_name, category, attr="PLUGIN")
registry.health()
~~~

### 容错：插头坏了不该烧主板

`discover()` 逐模块导入，**单个模块导入失败只跳过它并告警**：

~~~python
try:
    m = importlib.import_module(full)
except Exception as e:
    logger.warning(f"[plugins] 跳过 {full}（导入失败）: {e}")
    continue
~~~

有回归测试锁住这条：造一个「一导入就 raise」的模块，验证其他插件仍被发现。

### 健康检查的两个坑

`health()` 会把每个插件的 `health()` 跑一遍，**单个失败不影响其他**。
这里踩过一个坑，值得单独说：

~~~python
# 早期实现：直接在**类**上调用
fn = getattr(obj, "health", None)
ok = bool(fn())
~~~

平台插件注册的是**类**，所以每个都报
`TypeError: ... health() missing 1 required positional argument: 'self'`。

—— 一个「看起来在检查健康」的实现，其实每个插件都被判成不健康。
**这种 bug 的特点是不会崩，只是结论全错。** 现在先实例化再探活，并有回归测试。

---

## 与 multi-agent-system 技能库的对照

两个项目用了**同一个思路的两种落地**，这个对照在面试时很好用：

| | multi-agent-system `skills/` | ecom-ops-agent `plugins/` |
|---|---|---|
| 形态 | 声明式目录（`SKILL.md` front matter） | 注册表（模块级 `PLUGIN` 变量） |
| 元信息 | YAML front matter | 类属性 |
| 装配 | 按 `worker` 字段装给指定 Agent | 按 `category` 分组，调用方按需取 |
| 共同点 | **加能力 = 加一个文件，主流程零改动**；单包损坏不影响启动 | 同左 |

---

## 为什么推送通道只做「反射注册」

`notifier.py` 已经是成熟的适配器模式，工作正常。
**为了「统一」而重写一遍能跑的代码，收益是零、风险是正的。**

所以 `plugins/__init__.py` 里只是把它读出来注册进同一个表：

~~~python
def _reflect_notifiers():
    import notifier
    for channel, (attr, cls) in notifier._REGISTRY.items():
        registry.register("notifier", channel, cls,
                          enabled=bool(getattr(config, attr, "")), ...)
~~~

这样 `/plugins` 能看到**全部**扩展点，但不需要为了统一而制造一次回归风险。

> 判断标准：**这个扩展点是不是已经足够好？**
> 是 → 反射暴露即可；否 → 才值得重写成插件。

---

## 对外工具

| 工具 | 作用 |
|---|---|
| `sync_platform_stock(sku, platform)` | 遍历平台插件拉取展示库存并落库；单平台失败被隔离 |
| `list_platform_plugins()` | 能力自描述：当前支持哪些平台、是否启用、默认水位 |

`sync_platform_stock` 的输出区分三态：

~~~text
🔄 平台库存同步完成：4 条写入（1 个 SKU × 5 个平台）
  ✅ 淘宝（taobao）：写入 1 / 跳过 0 / 失败 0
  ✅ 天猫（tmall）：写入 0 / 跳过 1 / 失败 0
~~~

---

## 测试

`tests/test_plugins.py`，20 项：

| 不变量 | 测试 |
|---|---|
| 单模块导入失败不连累其他插件 | `test_discovery_survives_broken_module` |
| **单平台失败不连累其他平台同步** | `test_sync_isolates_failing_platform` |
| **不可用不能被写成 0** | `test_sync_unavailable_platform_does_not_write_zero` |
| 未上架算跳过、不算失败 | `test_sync_not_listed_is_skipped_not_failed` |
| 健康检查真的在检查（会实例化） | `test_health_instantiates_classes` |
| 单插件探活异常不影响其他 | `test_health_isolates_failures` |
| 种子数据总量没被插件化改掉 | `test_seed_demo_keeps_known_totals` |
| 演示计划来自插件表 | `test_demo_plan_comes_from_plugins` |

---

## 已知不足

| 不足 | 改进方向 |
|---|---|
| 插件按目录自动发现，没有版本兼容校验 | 加 `requires` 声明与启动时校验 |
| 无插件配置界面 | Streamlit 侧栏展示 `describe()` + 启停开关 |
| 平台级水位默认值（`default_water_level`）还没参与判定 | 可以作为 v3：规则库为空时用平台声明值替代均分 |
| 没有真正的 API 插件在跑 | `rest_api.py` 是模板，接真实 ERP 后可验证端到端 |
