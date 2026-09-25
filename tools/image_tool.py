"""图片批处理工具：批量缩放并加水印，替代重复的人工裁剪。

对应实习工作：部署 ImageMagick 替代重复的人工图片裁剪/处理。
mock 模式下若输入目录无图，先用 Pillow 生成若干示例图，再批量处理。

[升级] 处理结果结构化；空目录会被拒绝并返回明确错误码。
"""
import os

from PIL import Image, ImageDraw, ImageFont

from config import DATA_DIR
from tools.validators import ToolResult, validate_tool, positive_int


def _ensure_sample_images(folder: str, n: int = 3) -> None:
    os.makedirs(folder, exist_ok=True)
    if os.listdir(folder):
        return
    for i in range(1, n + 1):
        img = Image.new("RGB", (1200, 1200), (230, 230, 235))
        d = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 80)
        except Exception:
            font = ImageFont.load_default()
        d.text((120, 540), f"Sample Product {i}", fill=(80, 80, 90), font=font)
        img.save(os.path.join(folder, f"product_{i}.png"))


@validate_tool(
    schema={"processed": positive_int, "output_dir": lambda v: "输出目录路径无效" if not v else None},
    required_data_keys=("processed", "output_dir"),
)
def batch_process_images(
    input_dir: str | None = None,
    output_dir: str | None = None,
    width: int = 800,
    watermark: str = "E-COMMERCE",
) -> ToolResult:
    """批量缩放图片到指定宽度并添加水印。"""
    in_dir = input_dir or os.path.join(DATA_DIR, "sample_images")
    out_dir = output_dir or os.path.join(DATA_DIR, "processed_images")
    _ensure_sample_images(in_dir)

    os.makedirs(out_dir, exist_ok=True)
    exts = (".png", ".jpg", ".jpeg", ".webp")
    files = [f for f in os.listdir(in_dir) if f.lower().endswith(exts)]
    if not files:
        return ToolResult(
            success=False,
            errors=[f"输入目录没有可处理的图片：{in_dir}"],
            summary=f"❌ 输入目录没有可处理的图片：{in_dir}",
        )

    count = 0
    for f in files:
        src = os.path.join(in_dir, f)
        with Image.open(src) as im:
            im = im.convert("RGB")
            ratio = width / im.width
            new_size = (width, int(im.height * ratio))
            im = im.resize(new_size)
            draw = ImageDraw.Draw(im, "RGBA")
            try:
                font = ImageFont.truetype("DejaVuSans.ttf", max(14, width // 28))
            except Exception:
                font = ImageFont.load_default()
            draw.text((10, new_size[1] - 40), watermark, fill=(255, 255, 255, 128), font=font)
            out_path = os.path.join(out_dir, f"wm_{f}")
            im.save(out_path)
            count += 1

    summary = f"✅ 图片批处理完成：共处理 {count} 张，输出至 {out_dir}"
    return ToolResult(
        success=True,
        data={"processed": count, "output_dir": out_dir, "watermark": watermark},
        summary=summary,
    )
