# plugins/__init__.py
"""插件化扩展点。

━━━ 一句话 ━━━
**一类扩展点 = 一个 category，一个实现 = 一个模块。**

    平台数据源   plugins/sources/*.py     加平台 = 加一个文件
    推送通道     notifier.py（反射注册）   已有适配器，只暴露给统一观测
    模型厂商     config（反射注册）        目前只有 DeepSeek

━━━ 用法 ━━━
    import plugins
    plugins.discover()
    for info, cls in plugins.platforms():        # 已启用的平台插件
        qty = cls().fetch_display_stock("A001")
    plugins.describe()                            # 给接口/文档生成用
    plugins.health()                              # 逐插件探活（失败相互隔离）
"""
from __future__ import annotations

from loguru import logger

from plugins.base import ModelPlugin, NotifierPlugin, PlatformPlugin
from plugins.registry import PluginInfo, PluginRegistry

registry = PluginRegistry()

_discovered = False


def discover(force: bool = False) -> PluginRegistry:
    """发现并注册所有插件（幂等；force=True 时重新扫描）。"""
    global _discovered
    if _discovered and not force:
        return registry
    if force:
        registry.reset()

    # ① 平台数据源：真正的自动发现（扫描目录 + PLUGIN 约定）
    registry.discover("plugins.sources", "platform")

    # ② 推送通道：反射注册既有适配器
    #    为什么不做成自动发现：notifier.py 已经是成熟的适配器模式，工作正常。
    #    为了「统一」而重写一遍能跑的代码，收益是零、风险是正的。
    #    这里只把它暴露给同一个注册表，让 /plugins 能看到全部扩展点。
    _reflect_notifiers()

    # ③ 模型厂商：同上，目前只有一个
    _reflect_models()

    _discovered = True
    logger.info(f"[plugins] 扩展点: {registry.describe() and {c: registry.names(c) for c in registry.categories()}}")
    return registry


def _reflect_notifiers() -> None:
    try:
        import config
        import notifier
        for channel, (attr, cls) in notifier._REGISTRY.items():
            registry.register(
                "notifier", channel, cls,
                label=getattr(cls, "label", None) or channel,
                description=(cls.__doc__ or "").strip().splitlines()[0] if cls.__doc__ else "",
                module="notifier",
                enabled=bool(getattr(config, attr, "")),
            )
    except Exception as e:
        logger.warning(f"[plugins] 推送通道反射注册失败（不影响主流程）: {e}")


def _reflect_models() -> None:
    try:
        import config
        registry.register(
            "model", "deepseek", None,
            label="DeepSeek", description="OpenAI 兼容接口（默认底座）",
            module="config", enabled=bool(config.DEEPSEEK_API_KEY),
            base_url=config.DEEPSEEK_BASE_URL, model=config.DEEPSEEK_MODEL,
        )
    except Exception as e:
        logger.warning(f"[plugins] 模型插件反射注册失败（不影响主流程）: {e}")


# ---------- 便捷入口 ----------

def platforms(only_enabled: bool = True) -> list[tuple[PluginInfo, type]]:
    """已注册的平台插件（默认只返回启用的）。"""
    discover()
    return registry.all("platform", only_enabled=only_enabled)


def platform_names(only_enabled: bool = True) -> list[str]:
    discover()
    return registry.names("platform", only_enabled=only_enabled)


def get_platform(name: str):
    discover()
    return registry.get("platform", name)


def platform_labels() -> dict[str, str]:
    discover()
    return {i.name: i.label for i, _ in registry.all("platform", only_enabled=True)}


def describe() -> dict:
    discover()
    return registry.describe()


def health() -> list[dict]:
    discover()
    return registry.health()


__all__ = [
    "registry", "discover", "platforms", "platform_names", "get_platform",
    "platform_labels", "describe", "health",
    "PluginRegistry", "PluginInfo", "PlatformPlugin", "NotifierPlugin", "ModelPlugin",
]
