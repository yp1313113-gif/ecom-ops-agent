# 演进记录（OPTIMIZATION_LOG）

> 一份给面试官看的"我们遇到了什么问题 → 怎么改的 → 改完变怎样"清单.
> 项目从 v0 demo 走向 v1 可观测性的全部决策, 都集中在这里.

## v1.1 · 2026-08 · 可观测性 + 校验改造

### 改进 #1: 工具返回字符串 → ToolResult 结构化
- **改前问题**: 6 个工具全部 `return str`, 调用方只能 `print(out)`, 无法判断工具内部是部分成功还是整体失败. sync_orders 即便有 25% SKU 缺失, 仍然返回 happy string.
- **改动**: 引入 `tools/validators.py` 的 `ToolResult` dataclass (success / data / warnings / errors / summary), 6 个工具全部改为返回结构化对象; 旧的 `str` 输出通过 `to_text()` 兼容.
- **改进效果**: 业务失败 (sync_orders 失败率超 20%) 现在会显式出现在 `ToolResult.errors`, Agent 可据此选择报警 / 兜底 / 重试, 不再 silent failure.

### 改进 #2: 加 schema + 阈值校验层
- **改前问题**: 工具只校验"数据能不能读到", 不校验"输出符合预期". 比如 backup 声称目标路径, 但如果磁盘满了照样会假成功.
- **改动**: `validate_tool` 装饰器 + `file_exists` / `dir_exists` / `fail_rate_threshold` / `positive_int` / `non_empty_str` 一组可复用校验器, 按工具分别配置.
- **改进效果**: 单元测试新增了"输入不存在文件 → success=False 且 errors 非空"场景, 由校验层强制覆盖.

### 改进 #3: 加指数退避 + 熔断器
- **改前问题**: 工具调用链对外部依赖 (企微 webhook / 网盘 API) 完全裸调用, 不稳时直接把异常抛回 Agent.
- **改动**: `tools/retry.py` 提供 `retry_with_backoff` 装饰器和 `CircuitBreaker` 类; `agent_core.run_tool()` 在调用前查熔断器, 失败时 `record_failure`. 阈值 5 次失败 / 30s 恢复.
- **改进效果**: 在 demo 中可观察到熔断器状态 (`breaker_status()`), 排查"为什么这个工具最近老是失败"不再靠猜.

### 改进 #4: 加轻量 JSONL trace
- **改前问题**: 排查 Agent 行为靠 loguru print, 没有统一的工具级 trace.
- **改动**: `tools/trace.py` 提供 `trace_call()` 显式记录 + `@traced` 装饰器 + `summarize_traces()` 汇总; `run_tool()` 自动写入 `logs/trace.jsonl`.
- **改进效果**: 包含 `ts / tool / args / kwargs / duration_ms / success / result_summary` 7 个字段, 单文件即可做时间序列分析.

### 改进 #5: 加离线 eval + baseline 对比
- **改前问题**: 没有任何指标说明"项目改造有没有效果", 简历上无法写出量化提升.
- **改动**: 50 条仿真问句 (4 类: simple_qa / multi_turn / missing_knowledge / ambiguous), mock LLM 用关键词路由走通全链路; `eval/last_run.json` vs `eval/baseline_run.json` 给出对比.
- **改进效果**: 报告见 `eval/report.md`. 关键洞察是 **工具成功率数值上 baseline 反而更高**, 因为 baseline 不过校验 → 当 sync_orders 25% 失败率时也判 success=True. 这个数值差恰好证明了"校验能让隐性失败浮出水面"这个论点.

### 改进 #6: 完整单元测试 + 失败场景覆盖
- **改前问题**: 6 个工具只有 happy-path 测试.
- **改动**: `tests/test_tools.py` 新增 `test_clean_sales_data_missing_file`、`test_sync_orders_healthy` 等场景, 总数 8 个, 包含业务硬阈值 + 软警告两层断言.
- **改进效果**: 跑 `python tests/test_tools.py` 即可一键验证 → 当前 8/8 通过.

## v1.0 · 初始 demo
- 单 ReAct Agent + 6 个工具 + mock 模式 / 真实模式双轨; LangChain + DeepSeek 配置层;
  README + 工程降级 + 完整文档.

---

## 后续可能演进 (未做)
- 接 OpenTelemetry / Jaeger 替代轻量 trace, 横向对比多个 Agent 实例
- eval 升级为 LLM-as-judge, 引入"答案质量"主观指标
- 把 multi_turn 真正跑通 (目前 mock LLM 只取第一条)
- 接真实 ERP/平台 API, 把 mock 数据替换为真实流
