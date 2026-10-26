---
name: xinhe-salary-audit
display_name: "薪核"
display_name_en: "XinHe Salary Cross-Check"
description: "凭证驱动的薪酬交叉核验：先查图片篡改风险，再抽取个税/银行/社保/公积金数据，逐月勾稽并标出偏差，含年终奖临界点与返聘口径，输出带覆盖率与置信度的 HTML 薪酬报告。触发：核薪资、验流水、工资对不上、薪酬报告。不触发：代发工资、报税申报、劳动仲裁取证。"
description_zh: "先验图、再取数、后勾稽：逐月核对个税/银行/社保/公积金，偏差分级，报告带版本与溯源。"
description_en: "Evidence-first salary cross-check: screens image manipulation risk, extracts tax/bank/social-insurance/housing-fund figures, reconciles them month by month, grades deviations, and produces a versioned HTML report with coverage and confidence."
version: 1.1.0
author: "李献杰 Lyon"
category: utility
allowed-tools: Read, Write, Bash, PowerShell
agent_created: true
tags: [salary, payroll, reconciliation, ocr, forensics, report]
---

# 薪核 · 凭证驱动的薪酬交叉核验

一句话：**先验图，再取数，后勾稽；每个数字都能追到来源。**

## 触发条件

**触发**：
- 候选人/员工提供的薪资需要核验
- 个税、银行流水、社保、公积金对不上
- 要出一份能经得起追问的薪酬报告
- 资料分批给，想增量更新

**不触发**：
- 代发工资、个税申报、社保代缴（这是执行，不是核验）
- 劳动仲裁取证、司法鉴定
- 只问某个薪酬概念（直接答）

## 前置检查

- [ ] 有明确的核验窗口（起止月份）
- [ ] 至少有 1 份能锚定月份的材料（个税或银行流水）
- [ ] Python 3.9+（工作台与计算器需要）
- [ ] 图片为本机可读文件；不是微信转发后的低清缩略图

缺月份锚点：停在收集阶段，先问用户补哪个月。

## 工作流（六步 + 状态机）

```
COLLECTING → CONFIRMING → PROCESSING → REVIEW → REPORTING
```

| 步 | 动作 | 工具 | 出口条件 |
|---|---|---|---|
| 1 | 建案件：人、城市、窗口 | `workbench/server.py` 或 `case.json` | 窗口已定 |
| 2 | **验图**：篡改风险筛查 | `scripts/forgery.py` | 无高风险，或用户书面确认继续 |
| 3 | 抽取：OCR / 手动 / 结构化导入 | `scripts/ocr.py`、`/api/import` | 每月至少有个税或银行 |
| 4 | 归一化 | `scripts/normalize.py` | 字段带来源与置信度 |
| 5 | 交叉核验 | `scripts/crosscheck.py` | 输出逐月状态与诊断 |
| 6 | 审核闸门 → 报告 | Markdown 表 → `scripts/report.py` | 用户确认后出版本化 HTML |

### 第 2 步的硬规则

图片风险分 `low / medium / high`：

- `high`：**默认阻塞**，除非用户明确说“我知道，继续”。
- `medium`：继续，但在报告“凭证完整性”里列出信号。
- `low`：正常通过。

风险筛查只给提示，**不构成鉴定意见**；详见 @references/ocr-and-forgery.md。

### 第 5 步的勾稽

逐月校验：

```
应发 − 实发 ≈ 社保个人 + 公积金个人 + 个税
社保个人 ÷ 个人比例 ≈ 社保基数
公积金个人 ÷ 比例档位 ≈ 公积金基数（多解取最可能）
```

分级：绿 ≤10%，黄 ≤20%，红 >20%；缺个税 → `partial`，不判红。

### 中国口径要点（硬规则）

| 主题 | 规则 |
|---|---|
| **累计预扣** | 月度个税波动是制度效应，不用“各月均值”反推；年度口径单独粗估 |
| **年终奖** | 6 个临界点（3.6/14.4/30/42/66/96 万），±2% 提示；一年只允许一次单独计税；1 月发放按新年度归属 |
| **社保基数** | 有上下限，7 月调基；`si_base_bounds` 由调用方传入，不写死 |
| **公积金** | 比例 5%–12% 由公司定，可年中变更；自动求解并检测变更点 |
| **退休返聘** | `employment_type=rehired_retiree`：不缴社保公积金，只核个税 |
| **劳务报酬** | `income_type=labor`：预扣逻辑不同，不参与工资勾稽，判 `partial` |
| **专项附加扣除** | 截图不可见，只作差额的第一解释项，不作计算项 |
| **外籍人士** | 本工具不覆盖 |

详细参数与来源见 @references/china-policy.md。

### 第 6 步的闸门

先出**可修改的 Markdown / 表格**，用户改完再出报告。
报告数字全部来自 `crosscheck.py`，不经过语言模型。

## 增量更新

- 每份材料按 **SHA-256** 缓存：没改的文件不重新 OCR、不重新验图。
- 只改某个月的字段时，只重算该月及其汇总（依赖图见 @references/crosscheck-rules.md）。
- 新资料进来 → 重新核验 → 报告版本 +1，旧版本保留。

## 输出契约

**聊天里只给**：结论一行、偏差月份与幅度、下一步。
**文件**：
- `findings.json`：逐月结果、覆盖率、置信度
- `report_vN.html`：自包含报告，含凭证完整性、三口径表、诊断、假设附录、版本记录

## 红线

- 不做个税精确复现，只做区间勾稽。
- `inferred=true` 的字段不得被后续反推当作独立来源。
- 口述数字必须标注“口述，置信度低”，不与截图混同。
- 姓名不一致 → 直接阻塞。
- 图片风险结论只写“疑似/需复核”，不写“造假”。
- 不代发工资、不代报税、不出具法律意见。

## 降级设计

| 情况 | 处置 |
|---|---|
| 没装 ppocr-lite | 上传不丢，标记“待手动录入”，工作台表格可填 |
| OCR 识别不出月份 | 让用户指定月份，或走结构化导入 |
| 图片高风险 | 阻塞，要求确认或换原图 |
| 缺个税 | 该月判 `partial`，标注差额含税 |
| 缺银行流水 | 该月不参与勾稽，覆盖率下降 |
| 多解公积金比例 | 报告里列候选，不强行选一个 |
| 用户只要结论 | 只给偏差表，不生成 HTML |
| 工作台端口被占 | `python workbench/server.py <端口>` |

## 资源索引

| 要做什么 | 看哪个文件 |
|---|---|
| 输入 JSON 字段与来源定义 | @references/data-schema.md |
| 勾稽公式、阈值、诊断码 | @references/crosscheck-rules.md |
| 中国个税/年终奖/社保公积金参数 | @references/china-policy.md |
| OCR 安装、缓存、验图信号与局限 | @references/ocr-and-forgery.md |
| 同类项目与改进点 | @references/benchmarks.md |
| 计算内核 | `scripts/crosscheck.py` |
| 本地工作台 | `workbench/server.py` |
| 自检 | `tests/selftest.py` |

## 退出自检

- [ ] 每张图都做了风险筛查，高风险已确认？
- [ ] 每个数字都有来源（ocr / manual / inferred）？
- [ ] 缺字段写的是“缺失”，不是 0？
- [ ] 偏差月份都有诊断与建议？
- [ ] 报告版本号递增、旧版本保留？
- [ ] 姓名一致性检查做了？
