"""数据清洗工具：把脏乱的销售/订单 Excel/CSV 自动规整。

对应实习工作：用 Python 重写手工 Excel 处理，日均节省约 2 小时。
mock 模式下读取 data/sales_raw.csv 并输出 data/sales_clean.csv。

[升级] 现在返回结构化 ToolResult, 同时保留中文 summary 便于向用户展示。
"""
import os
import re
import pandas as pd

from config import DATA_DIR
from tools.validators import ToolResult, validate_tool, file_exists


def _normalize_amount(val) -> float:
    """把 '¥1,234.5' / '1234.5元' / '  1234 ' 等统一成 float。"""
    if val is None:
        return 0.0
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "null", ""):
        return 0.0
    s = re.sub(r"[¥￥元,\s]", "", s)
    s = s.replace("（", "(").replace("）", ")")
    # 只保留数字、小数点、负号
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else 0.0


@validate_tool(
    schema={"output_path": file_exists},
    required_data_keys=("raw_rows", "clean_rows", "output_path"),
)
def clean_sales_data(input_path: str | None = None, output_path: str | None = None) -> ToolResult:
    """清洗销售数据：去重、补空、标准化金额与日期，输出清洗后文件。"""
    in_path = input_path or os.path.join(DATA_DIR, "sales_raw.csv")
    out_path = output_path or os.path.join(DATA_DIR, "sales_clean.csv")

    if not os.path.exists(in_path):
        return ToolResult(
            success=False,
            errors=[f"找不到原始数据文件：{in_path}"],
            summary=f"❌ 找不到原始数据文件：{in_path}",
        )

    df = pd.read_csv(in_path)
    raw_rows = len(df)

    # 1) 列名去空格、统一小写
    df.columns = [str(c).strip().lower() for c in df.columns]

    # 2) 文本字段去首尾空格
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].astype(str).str.strip()

    # 3) 金额字段标准化（兼容 ¥ / 元 / 千分位）
    for col in ("amount", "price", "total"):
        if col in df.columns:
            df[col] = df[col].map(_normalize_amount)

    # 4) 数量缺失补 0
    if "qty" in df.columns:
        df["qty"] = pd.to_numeric(df["qty"], errors="coerce").fillna(0).astype(int)

    # 5) 日期标准化为 YYYY-MM-DD
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce", format="mixed").dt.strftime("%Y-%m-%d")

    # 6) 去重（完全相同行）
    df = df.drop_duplicates()
    clean_rows = len(df)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df.to_csv(out_path, index=False, encoding="utf-8-sig")

    summary = (
        f"✅ 数据清洗完成\n"
        f"  · 原始行数：{raw_rows}\n"
        f"  · 清洗后行数：{clean_rows}（去重 {raw_rows - clean_rows} 行）\n"
        f"  · 输出文件：{out_path}"
    )
    return ToolResult(
        success=True,
        data={"raw_rows": raw_rows, "clean_rows": clean_rows, "deduped": raw_rows - clean_rows, "output_path": out_path},
        summary=summary,
    )
