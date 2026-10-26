# 同类项目与改进点（benchmarks）

调研时间：2026-10-26。结论：**没有现成项目同时做到「OCR + 薪酬核验 + 跨文档勾稽」**，
现有项目各占一段，薪核补的是中间的“勾稽层”。

## 1. 现有项目

| 项目 | 做什么 | 缺什么 |
|---|---|---|
| [Mermiges/financial-ocr](https://github.com/Mermiges/financial-ocr) | 用视觉模型/OCR 抽工资单、税表，输出 JSON | 仍处脚手架阶段；不做出入勾稽 |
| [morettimarco/MCP-Buste-Paga](https://glama.ai/mcp/servers/morettimarco/MCP-Buste-Paga) | 意大利工资单 PDF → SQLite，SHA-256 去重，历史查询 | 只做单文档抽取；无跨来源核验 |
| [vineus/payslip-overview](https://www.npmjs.com/package/@vineus/payslip-overview) | 法国工资单仪表盘，本地运行 | 文本抽取为主；无银行/社保对照 |
| [ashiqspace/MCP-server-DocumentAnalysis](https://github.com/ashiqspace/MCP-server-DocumentAnalysis) | 文档真实性检查 + 工资单分析 | 依赖在线大模型；无确定性勾稽 |
| [chenqg618/compliance-skills](https://github.com/chenqg618/compliance-skills) | 150+ 离线确定性核对工具（含 payroll） | 只核对表格内部一致性；不处理凭证 |
| [PaddleOCR PP-StructureV3](https://paddlepaddle.github.io/PaddleX/3.0-rc1/en/pipeline_usage/tutorials/ocr_pipelines/PP-StructureV3.html) | 版面/表格识别，保留单元格坐标 | 是能力，不是产品流程 |

## 2. 薪核补的四个空档

### 效率

- **SHA-256 内容缓存**：同一张图只 OCR 一次、只验图一次。
- **依赖图增量重算**：改一个字段只重算该月与汇总，不重跑全量。
- **报告版本化**：`report_vN.html`，旧版本保留，可对比。

### 智能

- **字段级置信度传播**：OCR 分数、来源类型、是否反推，一路带到报告。
- **多假设求解**：公积金比例多解时列候选，不硬选。
- **异常模式库**：13 薪、调基、补缴、报销、退税、绩效另发，每条都有诊断码与建议。
- **身份一致性阻塞**：姓名冲突直接停，不继续算。

### 架构

- **确定性内核**：`crosscheck.py` 纯函数，无网络、无 LLM；报告只渲染。
- **来源溯源**：每个数字带 `source / file / confidence / inferred`。
- **状态机**：COLLECTING → CONFIRMING → PROCESSING → REVIEW → REPORTING，状态落在 `state.json`。
- **可复算**：同输入同输出；测试覆盖关键分支。

### 互动

- **审核闸门**：先出可改表格，用户确认后才出报告。
- **本地工作台**：四个上传栏、风险徽标、可编辑表格、报告版本列表；零第三方依赖。
- **降级不阻塞**：没装 OCR 也能用，手动录入即可。

## 3. 还能继续做的（路线图）

| 方向 | 做法 |
|---|---|
| 表格 PDF | 接 PP-StructureV3，保留行列与单元格置信度 |
| 银行流水解析 | 按银行模板做列映射，支持多行合并 |
| 个税累计预扣 | 用官方税率表做区间复现（仍不给出“应缴”结论） |
| 多候选人批量 | 案件队列 + 汇总看板 |
| 报告导出 | PDF / Excel 导出 |
| 校准 | 记录人工修正，统计 OCR 字段错误率 |

## 4. 明确不做

- 不做“一键判定造假”。
- 不代发工资、不代报税。
- 不接在线 OCR 默认上传薪资原件（隐私）。
- 不给法律意见。
