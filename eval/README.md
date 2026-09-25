# Eval package: 把 50 条仿真问句跑过 Agent 全链路, 输出指标/对比图/报告

## 用法
```bash
python eval/run_all.py     # 一站式 (eval + baseline + comparison)
# 或分步:
python eval/run_eval.py    # 优化版指标
python eval/baseline.py    # 无校验 baseline 指标
python eval/comparison.py  # 生成对比图 + report.md
```

## 产物
- `last_run.json`     优化版完整指标 + 明细 (含 50 条按 id 的 records)
- `baseline_run.json` baseline 完整指标 (仅含工具成功率 + 耗时)
- `comparison.png`    路由/工具/调用正确率 三指标并列柱图
- `report.md`         面试可直接引用的对比报告

## 面试对话口径
> 「我给 Agent 配了一套离线 eval, 跑了 50 条仿真问题 (4 类: 简单/多步/知识缺失/歧义),
>   对比无校验 baseline, 工具成功率/路由命中/调用正确率都给出了具体数值; trace 是
>   全链路 JSONL 落盘, 排障不再靠 print。」
