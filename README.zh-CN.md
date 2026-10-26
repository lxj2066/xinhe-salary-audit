# 薪核（XinHe Salary Audit）

> 版本：1.0.0 ｜ 内嵌技能：`xinhe-salary-audit` v1.0.0

**凭证驱动的薪酬交叉核验：先验图，再取数，后勾稽。**

面向猎头、HR 和需要核验候选人薪资的团队。不是“上传即出结果”的黑箱，而是一条带审核闸门的流水线：

1. **验图**：元数据 / ELA / 金额区域一致性，三档风险
2. **取数**：OCR 或手动录入个税、银行、社保、公积金
3. **勾稽**：逐月核对「应发 − 实发 ≈ 社保 + 公积金 + 个税」
4. **审核**：先出可改的中间表，确认后才出报告
5. **报告**：HTML，带覆盖率、置信度、版本记录

## 中国市场特化

- **个税**：按年度综合所得税率表做量级粗估，只用于异常提示，不出“应缴税额”结论。
- **累计预扣**：月度个税波动是制度效应，不用“各月实发均值”反推月均应发。
- **年终奖**：3.6/14.4/30/42/66/96 万六个临界点扫描，距临界点 ≤2% 提示跳档；一年只允许一次单独计税；1 月发放按新年度归属。
- **社保上下限**：支持传入当年当地上下限；反推基数越界会标黄，并提示“高于上限时按上限缴纳”。
- **公积金 5%–12%**：比例由公司定且可年中调整；自动求解并检测变更点。
- **退休返聘**：不缴社保公积金，只核个税。
- **劳务报酬**：预扣逻辑不同，不参与工资勾稽。
- **专项附加扣除**：截图不可见，只作差额的第一解释项。
- **外籍人士**：不覆盖。

## 为什么不是“又一个工资单 OCR”

调研了 6 个同类项目，没有一个是「OCR + 薪酬核验 + 跨文档勾稽」三合一：

| 项目 | 做了什么 | 缺什么 |
|---|---|---|
| [financial-ocr](https://github.com/Mermiges/financial-ocr) | 工资单/税表抽取 | 脚手架阶段；无勾稽 |
| [MCP-Buste-Paga](https://glama.ai/mcp/servers/morettimarco/MCP-Buste-Paga) | 意大利工资单 → SQLite | 单文档；无跨来源 |
| [payslip-overview](https://www.npmjs.com/package/@vineus/payslip-overview) | 法国工资单仪表盘 | 无银行/社保对照 |
| [MCP-server-DocumentAnalysis](https://github.com/ashiqspace/MCP-server-DocumentAnalysis) | 文档真实性检查 | 依赖在线模型；无确定性核验 |
| [compliance-skills](https://github.com/chenqg618/compliance-skills) | 离线工资表核对 | 只查表内一致性 |
| [PP-StructureV3](https://paddlepaddle.github.io/PaddleX/3.0-rc1/en/pipeline_usage/tutorials/ocr_pipelines/PP-StructureV3.html) | 表格结构识别 | 是能力，不是流程 |

薪核补的是中间那层：**确定性勾稽 + 来源溯源 + 审核闸门**。

## 核心特性

- **确定性内核**：所有数字由 `crosscheck.py` 计算，不经过语言模型
- **先验图**：高风险图片默认阻塞
- **增量处理**：文件按 SHA-256 缓存，没变的不重跑 OCR
- **版本化报告**：`report_v1.html`、`report_v2.html`，旧版本保留
- **本地工作台**：四栏上传、风险徽标、可编辑表格；只监听 127.0.0.1
- **降级不阻塞**：没装 OCR 也能用

## 安装

```bash
git clone https://github.com/lxj2066/xinhe-salary-audit.git
cp -r xinhe-salary-audit/skills/xinhe-salary-audit ~/.claude/skills/
```

OCR 可选：`pip install ppocr-lite`。

## 使用

```bash
python workbench/server.py      # 打开 http://127.0.0.1:8765
python tests/selftest.py        # 19 项自检
```

## 边界

- 验图只写“疑似/需复核”，不写“造假”，不构成鉴定意见。
- 不做个税精确复现、代发工资、报税、法律意见。
- 缺字段写 null，不猜；姓名不一致直接阻塞。

## 许可

[PolyForm Noncommercial License 1.0.0](LICENSE)。商用需单独授权，见 [COMMERCIAL.md](COMMERCIAL.md)。

作者：李献杰 Lyon
