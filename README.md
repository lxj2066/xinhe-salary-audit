# 薪核（XinHe Salary Audit）

**凭证驱动的薪酬交叉核验：先验图，再取数，后勾稽。**

薪核面向猎头、HR 和需要核验候选人薪资的团队。它不是“上传即出结果”的黑箱，而是一条有审核闸门的流水线：

1. **验图**：筛查图片篡改风险（元数据 / ELA / 金额区域一致性）
2. **取数**：OCR 或手动录入个税、银行、社保、公积金
3. **勾稽**：逐月核对「应发 − 实发 ≈ 社保 + 公积金 + 个税」
4. **审核**：先出可修改的中间表，确认后才出报告
5. **报告**：自包含 HTML，带覆盖率、置信度、版本记录

## 为什么不是“又一个工资单 OCR”

调研了 6 个同类项目，没有一个同时做到「OCR + 薪酬核验 + 跨文档勾稽」：

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
- **先验图**：高风险图片默认阻塞，确认后才继续
- **增量处理**：文件按 SHA-256 缓存，没变的不重跑 OCR
- **版本化报告**：`report_v1.html`、`report_v2.html`，旧版本保留
- **本地工作台**：四个上传栏、风险徽标、可编辑表格、报告版本列表；只监听 127.0.0.1
- **降级不阻塞**：没装 OCR 也能用，手动录入即可

## 目录

```
xinhe-salary-audit/
├── SKILL.md
├── references/
│   ├── data-schema.md
│   ├── crosscheck-rules.md
│   ├── ocr-and-forgery.md
│   └── benchmarks.md
├── scripts/
│   ├── normalize.py
│   ├── crosscheck.py
│   ├── forgery.py
│   ├── ocr.py
│   ├── report.py
│   └── templates/report.html.j2
├── workbench/
│   ├── server.py
│   └── index.html
└── tests/
    ├── selftest.py
    └── fixtures/case_zhangsan.json
```

## 安装

```bash
git clone https://github.com/lxj2066/xinhe-salary-audit.git
cp -r xinhe-salary-audit/skills/xinhe-salary-audit ~/.claude/skills/
```

OCR 可选：

```bash
pip install ppocr-lite
```

不装也能用：工作台会把图片标为“待手动录入”。

## 使用

### 工作台（推荐）

```bash
python workbench/server.py
# 打开 http://127.0.0.1:8765
```

### 命令行

```bash
python scripts/normalize.py case.json --out normalized.json
python scripts/crosscheck.py normalized.json --out findings.json
python scripts/report.py case.json findings.json --out report.html
```

### 自检

```bash
python tests/selftest.py
```

## 安全与边界

- 默认只读本地；工作台不对外网开放。
- 验图结论只写“疑似/需复核”，不写“造假”，不构成鉴定意见。
- 不做个税精确复现，不做代发工资、报税、法律意见。
- 缺字段写 `null` 并标 `UNKNOWN`，不猜。
- 姓名不一致直接阻塞。

## 许可

[PolyForm Noncommercial License 1.0.0](LICENSE)。商用需单独授权，见 [COMMERCIAL.md](COMMERCIAL.md)。

作者：李献杰 Lyon
