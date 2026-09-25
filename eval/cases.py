"""测试问句集：覆盖四类典型用户诉求。

口径说明：
    - simple_qa        : 单步、单工具即可完成的常规问题（占比 ~40%）
    - multi_turn       : 需要连续多步的复合指令（占比 ~16%）
    - missing_knowledge: 用户问业务范围外的问题, 期望路由失败 / 工具兜底（~20%）
    - ambiguous        : 意图不明, 期望 Agent 给出兜底提示而非幻觉（~24%）

每条用例字段：
    id                : 用例 id（1-50）
    category          : 上述四类之一
    question          : 用户问句（中文）
    expected_tool     : 期望路由到的工具名; null 表示不应命中任何工具
    expect_success    : 期望本次问句最终成功
"""
CASES = [
    # ================ simple_qa (1-20) ================
    {"id": 1,  "category": "simple_qa", "question": "帮我清洗一下今天的销售数据", "expected_tool": "clean_sales_data", "expect_success": True},
    {"id": 2,  "category": "simple_qa", "question": "去重并整理销售表", "expected_tool": "clean_sales_data", "expect_success": True},
    {"id": 3,  "category": "simple_qa", "question": "看看订单同步对账", "expected_tool": "sync_orders", "expect_success": True},
    {"id": 4,  "category": "simple_qa", "question": "ERP 对照表里缺哪些 SKU", "expected_tool": "sync_orders", "expect_success": True},
    {"id": 5,  "category": "simple_qa", "question": "监控一下各平台库存", "expected_tool": "monitor_platforms", "expect_success": True},
    {"id": 6,  "category": "simple_qa", "question": "今天有没有价格异常", "expected_tool": "monitor_platforms", "expect_success": True},
    {"id": 7,  "category": "simple_qa", "question": "把告警推到企微", "expected_tool": "monitor_platforms", "expect_success": True},
    {"id": 8,  "category": "simple_qa", "question": "生成今天的运营日报", "expected_tool": "generate_daily_report", "expect_success": True},
    {"id": 9,  "category": "simple_qa", "question": "给我汇总一下今日营业额", "expected_tool": "generate_daily_report", "expect_success": True},
    {"id": 10, "category": "simple_qa", "question": "日报里想看 Top 商品", "expected_tool": "generate_daily_report", "expect_success": True},
    {"id": 11, "category": "simple_qa", "question": "帮我批处理一下商品图", "expected_tool": "batch_process_images", "expect_success": True},
    {"id": 12, "category": "simple_qa", "question": "所有商品图加水印", "expected_tool": "batch_process_images", "expect_success": True},
    {"id": 13, "category": "simple_qa", "question": "给图片缩放并打标", "expected_tool": "batch_process_images", "expect_success": True},
    {"id": 14, "category": "simple_qa", "question": "做一次数据备份", "expected_tool": "backup_data", "expect_success": True},
    {"id": 15, "category": "simple_qa", "question": "把数据异地容灾", "expected_tool": "backup_data", "expect_success": True},
    {"id": 16, "category": "simple_qa", "question": "上传到网盘一份", "expected_tool": "backup_data", "expect_success": True},
    {"id": 17, "category": "simple_qa", "question": "整理销售 csv", "expected_tool": "clean_sales_data", "expect_success": True},
    {"id": 18, "category": "simple_qa", "question": "订单对账报告发我", "expected_tool": "sync_orders", "expect_success": True},
    {"id": 19, "category": "simple_qa", "question": "库存告急提示一下", "expected_tool": "monitor_platforms", "expect_success": True},
    {"id": 20, "category": "simple_qa", "question": "今天日报推企微", "expected_tool": "generate_daily_report", "expect_success": True},

    # ================ multi_turn (21-28) ================
    {"id": 21, "category": "multi_turn", "question": "先清洗数据再做订单对账", "expected_tool": "clean_sales_data", "expect_success": True},
    {"id": 22, "category": "multi_turn", "question": "监控加备份一气呵成", "expected_tool": "monitor_platforms", "expect_success": True},
    {"id": 23, "category": "multi_turn", "question": "清洗→监控→日报全跑一遍", "expected_tool": "clean_sales_data", "expect_success": True},
    {"id": 24, "category": "multi_turn", "question": "先查订单同步失败率, 再决定备份", "expected_tool": "sync_orders", "expect_success": True},
    {"id": 25, "category": "multi_turn", "question": "清洗一下,然后对账,然后监控", "expected_tool": "clean_sales_data", "expect_success": True},
    {"id": 26, "category": "multi_turn", "question": "日报发完后做一次备份", "expected_tool": "generate_daily_report", "expect_success": True},
    {"id": 27, "category": "multi_turn", "question": "图片批处理后再备份", "expected_tool": "batch_process_images", "expect_success": True},
    {"id": 28, "category": "multi_turn", "question": "先监控库存告急, 之后把数据备份一下", "expected_tool": "monitor_platforms", "expect_success": True},

    # ================ missing_knowledge (29-38) ================
    {"id": 29, "category": "missing_knowledge", "question": "上个月的客户投诉率是多少", "expected_tool": None, "expect_success": False},
    {"id": 30, "category": "missing_knowledge", "question": "我们的仓储 SKU 总数", "expected_tool": None, "expect_success": False},
    {"id": 31, "category": "missing_knowledge", "question": "退货流程怎么走", "expected_tool": None, "expect_success": False},
    {"id": 32, "category": "missing_knowledge", "question": "供应商账期是几天", "expected_tool": None, "expect_success": False},
    {"id": 33, "category": "missing_knowledge", "question": "广告投放 ROI 趋势", "expected_tool": None, "expect_success": False},
    {"id": 34, "category": "missing_knowledge", "question": "用户画像分析", "expected_tool": None, "expect_success": False},
    {"id": 35, "category": "missing_knowledge", "question": "员工考勤记录", "expected_tool": None, "expect_success": False},
    {"id": 36, "category": "missing_knowledge", "question": "财务报表本周汇总", "expected_tool": None, "expect_success": False},
    {"id": 37, "category": "missing_knowledge", "question": "物流时效分布", "expected_tool": None, "expect_success": False},
    {"id": 38, "category": "missing_knowledge", "question": "客服转化率", "expected_tool": None, "expect_success": False},

    # ================ ambiguous (39-50) ================
    {"id": 39, "category": "ambiguous", "question": "搞一下", "expected_tool": None, "expect_success": False},
    {"id": 40, "category": "ambiguous", "question": "看看情况", "expected_tool": None, "expect_success": False},
    {"id": 41, "category": "ambiguous", "question": "怎么办", "expected_tool": None, "expect_success": False},
    {"id": 42, "category": "ambiguous", "question": "现在的状态", "expected_tool": None, "expect_success": False},
    {"id": 43, "category": "ambiguous", "question": "帮我弄一下那个", "expected_tool": None, "expect_success": False},
    {"id": 44, "category": "ambiguous", "question": "出问题了", "expected_tool": None, "expect_success": False},
    {"id": 45, "category": "ambiguous", "question": "今天的进度", "expected_tool": None, "expect_success": False},
    {"id": 46, "category": "ambiguous", "question": "最新情况呢", "expected_tool": None, "expect_success": False},
    {"id": 47, "category": "ambiguous", "question": "咋整", "expected_tool": None, "expect_success": False},
    {"id": 48, "category": "ambiguous", "question": "该不该担心", "expected_tool": None, "expect_success": False},
    {"id": 49, "category": "ambiguous", "question": "随便", "expected_tool": None, "expect_success": False},
    {"id": 50, "category": "ambiguous", "question": "随便搞搞", "expected_tool": None, "expect_success": False},
]
