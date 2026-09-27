# plugins/registry.py
"""通用插件注册表：注册 / 自动发现 / 查询 / 健康检查。

━━━ 为什么要有「插件」这一层 ━━━
本项目的扩展点有三类，但原来只有一类（推送通道）做成了适配器，其余是硬编码：

    · **数据源**（平台）：原来 seed_demo / 监控里的平台名写死在代码和数据里，
      接一个新平台要改好几处；
    · **推送通道**（企微/飞书/钉钉）：已经是适配器，但只能内部用，外部看不到；
    · **模型厂商**：目前只有 DeepSeek。

所以这里做一个**通用的插件注册表**，让「扩展点」变成同一个概念：
一类扩展点 = 一个 category，一个实现 = 一个插件。

━━━ 与 multi-agent-system 技能库的关系 ━━━
那边是「SKILL.md 元数据 + handler + eval.json」的**声明式目录**，
这边是「一个扩展点一个模块 + PLUGIN 变量」的**注册表**。
同一个思路的两种落地：**加能力 = 加一个文件，主流程代码零改动。**

━━━ 为什么不是简单的 dict ━━━
因为除了「注册」，还需要：自动发现（扫描目录）、按 category 分组、
健康检查、以及对**单个插件失败**的隔离 —— 后者是插件化真正的价值所在。
"""
from __future__ import annotations

import importlib
import os
import pkgutil
import traceback
from dataclasses import asdict, dataclass, field
from typing import Any

from loguru import logger


@dataclass
class PluginInfo:
    """一个插件的元信息（可序列化，供接口 / 文档生成）。"""

    name: str
    category: str
    label: str = ""
    version: str = "1.0.0"
    description: str = ""
    module: str = ""
    enabled: bool = True
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class PluginRegistry:
    """按 category 管理插件实现。

    设计原则：
      · 注册是**幂等**的（同一 name+category 重复注册覆盖并告警）；
      · 查询永不抛异常（找不到返回 None），调用方用 `enabled` 判断可用性；
      · **单个插件出问题不影响其他插件** —— 每条记录都带自己的状态。
    """

    def __init__(self):
        self._plugins: dict[str, dict[str, Any]] = {}
        self._infos: dict[str, dict[str, PluginInfo]] = {}

    # ---------- 注册 ----------

    def register(self, category: str, name: str, obj: Any, *,
                 label: str = "", version: str = "1.0.0",
                 description: str = "", module: str = "",
                 enabled: bool = True, **extra) -> PluginInfo:
        cat = self._plugins.setdefault(category, {})
        infos = self._infos.setdefault(category, {})
        if name in cat:
            logger.warning(f"[plugins] {category}/{name} 重复注册，后者覆盖前者")
        cat[name] = obj
        info = PluginInfo(name=name, category=category, label=label or name,
                          version=version, description=description, module=module,
                          enabled=enabled, extra=extra)
        infos[name] = info
        return info

    # ---------- 查询 ----------

    def get(self, category: str, name: str) -> Any | None:
        return self._plugins.get(category, {}).get(name)

    def info(self, category: str, name: str) -> PluginInfo | None:
        return self._infos.get(category, {}).get(name)

    def all(self, category: str, only_enabled: bool = True) -> list[tuple[PluginInfo, Any]]:
        infos = self._infos.get(category, {})
        out = []
        for name in sorted(infos):
            info = infos[name]
            if only_enabled and not info.enabled:
                continue
            out.append((info, self._plugins[category][name]))
        return out

    def names(self, category: str, only_enabled: bool = True) -> list[str]:
        return [i.name for i, _ in self.all(category, only_enabled)]

    def categories(self) -> list[str]:
        return sorted(self._infos)

    # ---------- 自动发现 ----------

    def discover(self, package_name: str, category: str,
                 attr: str = "PLUGIN", enabled_attr: str = "enabled") -> int:
        """扫描包目录，导入每个模块，把其中的 `PLUGIN` 注册到 category。

        容错原则：**单个插件模块导入失败只跳过它并告警，绝不让整个服务起不来。**
        （与技能库同一个道理：插头坏了不该烧主板。）

        约定：
          · 模块里定义 `PLUGIN = <类>`；
          · 类的 name / label / version / description / enabled 作为元信息；
          · 文件名以下划线开头或叫 `_*` 的模块跳过（基类/工具模块）。
        """
        try:
            pkg = importlib.import_module(package_name)
        except Exception as e:
            logger.warning(f"[plugins] 无法导入包 {package_name}: {e}")
            return 0

        count = 0
        for mod in pkgutil.iter_modules(pkg.__path__):
            if mod.name.startswith("_"):
                continue
            full = f"{package_name}.{mod.name}"
            try:
                m = importlib.import_module(full)
            except Exception as e:
                logger.warning(f"[plugins] 跳过 {full}（导入失败）: {e}")
                continue
            cls = getattr(m, attr, None)
            if cls is None:
                logger.debug(f"[plugins] {full} 没有 {attr}，跳过")
                continue
            name = getattr(cls, "name", None) or mod.name
            self.register(
                category, name, cls,
                label=getattr(cls, "label", "") or name,
                version=getattr(cls, "version", "1.0.0"),
                description=getattr(cls, "description", ""),
                module=full,
                enabled=bool(getattr(cls, enabled_attr, True)),
                default_water_level=getattr(cls, "default_water_level", None),
            )
            count += 1

        logger.info(f"[plugins] {category} 已发现 {count} 个插件: {self.names(category)}")
        return count

    # ---------- 观测 ----------

    def describe(self) -> dict:
        return {
            cat: [i.to_dict() for i in self._infos[cat].values()]
            for cat in self.categories()
        }

    def health(self) -> list[dict]:
        """对每个插件跑一次健康检查。

        **两个都必须是「隔离」的**：
          · 单个插件探活抛异常 → 只标记它不健康，不影响其他插件；
          · 插件注册的是**类**（平台/通道都是类）→ 先实例化再探活。
            早期实现在类上直接调 `health()`，结果每个平台都报
            `missing 1 required positional argument: 'self'` —— 一个「看起来
            在检查健康」的实现，其实什么都没检查。
        """
        out = []
        for cat in self.categories():
            for info, obj in self.all(cat, only_enabled=False):
                ok, detail = True, ""
                try:
                    target = obj() if isinstance(obj, type) else obj
                    fn = getattr(target, "health", None)
                    if callable(fn):
                        ok = bool(fn())
                except Exception as e:
                    ok, detail = False, type(e).__name__ + ": " + str(e)
                out.append({"category": cat, "name": info.name, "label": info.label,
                            "enabled": info.enabled, "healthy": ok, "detail": detail})
        return out

    def reset(self) -> None:
        """清空注册表（测试用）。"""
        self._plugins.clear()
        self._infos.clear()
