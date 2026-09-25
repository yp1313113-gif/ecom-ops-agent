"""Eval 入口：一行命令跑完整评估 (baseline + optimized + 对比图 + 报告)。

支持 flag:
    --apply-fixes    套用 OPTIMIZATION_LOG.md 中的 fix (v1.2), 跑一轮「修复后」
                     的 eval, 给出 baseline / v1 / v2_fixed 三方对比
    --restore        还原 demo 数据 (清掉 --apply-fixes 写入的对照行)
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "data"
MAPPING_PATH = DATA_DIR / "sku_erp_mapping.csv"
BAK_PATH = DATA_DIR / "sku_erp_mapping.csv.bak"


def _restore_data() -> None:
    """还原 --apply-fixes 写入的对照表 (mapping backup).
    
    注意: fixed_run.json 是 v2 的产物, 不在 restore 范围, 用户可以自行删除.
    """
    if BAK_PATH.exists():
        shutil.copy(BAK_PATH, MAPPING_PATH)
        BAK_PATH.unlink()
        print(f"↩️  还原对照表: {MAPPING_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply-fixes", action="store_true",
                        help="套用 OPTIMIZATION_LOG.md 的 fix, 跑 baseline/v1/v2_fixed 三方对比")
    parser.add_argument("--restore", action="store_true",
                        help="还原 demo 数据 + 删除 fixed_run 缓存")
    args = parser.parse_args()

    if args.restore:
        _restore_data()
        return

    print("▶ step 1/3: run_eval.py  (v1 · 含校验 + trace)")
    from eval import run_eval
    run_eval.main()

    print("\n▶ step 2/3: baseline.py  (v0 · 无校验无 trace)")
    from eval import baseline
    baseline.main()

    if args.apply_fixes:
        print("\n▶ step 2.5/3: 套用 OPTIMIZATION_LOG.md fix → 重跑 v1 链路")
        from eval import optimization_fixes
        fix_result = optimization_fixes.apply()
        print(f"   ✅ 补全 {len(fix_result['added'])} 条对照行: {fix_result['added']}")
        # 重跑 run_eval 写入 fixed_run.json
        from eval import run_eval as _run_eval
        # 临时把 last_run 改成 fixed_run
        from pathlib import Path as _P
        import json as _json
        cases = _run_eval.load_dataset()
        out = _run_eval.evaluate(cases)
        fixed_path = _P(__file__).resolve().parent / "fixed_run.json"
        with open(fixed_path, "w", encoding="utf-8") as f:
            _json.dump(out, f, ensure_ascii=False, indent=2, default=_run_eval._json_safe)
        m = out["metrics"]
        print(f"\n   📊 v2_fixed Metrics:")
        print(f"   · routing_accuracy : {m['routing_accuracy']}%")
        print(f"   · tool_success_rate: {m['tool_success_rate']}%")
        print(f"   · call_correctness : {m['call_correctness']}%")
        print(f"   · avg_latency_ms   : {m['avg_latency_ms']} ms")
        for c, s in m["by_category"].items():
            print(f"   · {c:18s}: count={s['count']}, routing_hit={s['routing_hit']}, tool_ok={s['tool_ok']}, call_correct={s['call_correct']}")
        print(f"\n   报告已写入: {fixed_path}")

    print("\n▶ step 3/3: comparison.py  (图 + 报告)")
    from eval import comparison
    comparison.main(apply_fixes=args.apply_fixes)


if __name__ == "__main__":
    main()
