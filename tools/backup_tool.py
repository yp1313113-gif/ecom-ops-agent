"""数据备份工具：本地异地副本 + 可选百度网盘上传。

对应实习工作：本地 + 百度网盘异地备份，曾成功恢复故障数据。

[升级] 返回 ToolResult; 同时校验备份目录真实存在, 避免假成功。
"""
import os
import shutil
from datetime import datetime

from config import DATA_DIR, BACKUP_DIR, BAIDU_NETDISK_ENABLED
from tools.validators import ToolResult, validate_tool, dir_exists


@validate_tool(
    schema={"target": dir_exists, "size_bytes": lambda v: None},
    required_data_keys=("target", "size_bytes", "created_at"),
)
def backup_data(source_dir: str | None = None) -> ToolResult:
    """备份数据目录到带时间戳的备份目录。"""
    src = source_dir or DATA_DIR
    if not os.path.isdir(src):
        return ToolResult(
            success=False,
            errors=[f"待备份目录不存在：{src}"],
            summary=f"❌ 待备份目录不存在：{src}",
        )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dst = os.path.join(BACKUP_DIR, f"backup_{stamp}")
    os.makedirs(BACKUP_DIR, exist_ok=True)

    # 防止同一毫秒重复备份 (eval 等场景)
    if os.path.exists(dst):
        i = 1
        while os.path.exists(f"{dst}_{i}"):
            i += 1
        dst = f"{dst}_{i}"
    shutil.copytree(src, dst)

    # 计算备份大小
    total_bytes = 0
    for root, _, files in os.walk(dst):
        for f in files:
            try:
                total_bytes += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass

    lines = [f"✅ 数据备份完成", f"  · 源：{src}", f"  · 目标：{dst}"]
    if BAIDU_NETDISK_ENABLED:
        lines.append("  · 已模拟上传至百度网盘（异地容灾）✅")
    else:
        lines.append("  · 仅本地副本（未启用网盘，配置 BAIDU_NETDISK_ENABLED=true 可启用）")
    summary = "\n".join(lines)
    warnings: list[str] = []
    if total_bytes == 0:
        warnings.append("备份目录为空，请确认源数据是否齐全")

    return ToolResult(
        success=True,
        data={
            "target": dst,
            "size_bytes": total_bytes,
            "created_at": stamp,
            "netdisk_enabled": BAIDU_NETDISK_ENABLED,
        },
        warnings=warnings,
        summary=summary,
    )
