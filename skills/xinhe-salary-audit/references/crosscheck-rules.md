# 勾稽规则与阈值（crosscheck-rules）

## 1. 逐月勾稽

```
expected = si_personal + hf_personal + tax_paid
actual   = gross_income − net_pay
residual = actual − expected
pct      = |residual| / max(expected, 1)
```

| 情况 | 处理 |
|---|---|
| `gross` 或 `net` 缺失 | `insufficient`，不计算 |
| `tax` 缺失 | `partial`，差额含税，不判红 |
| `|residual| ≤ tolerance` | `green` |
| `pct ≤ 10%` | `green` |
| `10% < pct ≤ 20%` | `yellow` |
| `pct > 20%` | `red` |

阈值可在 `assumptions` 或调用参数中覆盖。

## 2. 基数反推

```
si_base ≈ si_personal / si_personal_rate
hf_base ≈ hf_personal / hf_rate
```

- 社保基数跨月偏离中位数 > 15% → `si_base_shift`（黄）
- 公积金比例多解：按“跨月稳定性 + 与社保基数/收入中位数接近程度”打分；仍不唯一 → 报告列候选，不硬选

## 3. 状态

| 状态 | 含义 |
|---|---|
| `green` | 通过 |
| `yellow` | 需确认（偏差或结构异常） |
| `red` | 异常（>20% 或关键不一致） |
| `partial` | 部分核验（缺个税等） |
| `insufficient` | 资料不足（缺锚点） |

## 4. 诊断码

| 码 | 触发 | 建议 |
|---|---|---|
| `missing_anchor` | 缺应发或实发 | 补个税/银行 |
| `tax_missing` | 缺个税 | 补个税截图 |
| `large_residual_unexplained` | 缺个税且差额仍大 | 查其他扣款/录入 |
| `deduction_shortfall` | 多扣 | 查补充公积金、年金、借款、补税 |
| `net_extra` | 少扣 | 查报销、补贴、绩效另发、退税 |
| `one_off_bonus` | 收入 > 中位数 ×1.25 | 确认年终奖/一次性奖金 |
| `si_base_shift` | 反推基数偏离 >15% | 查调基/补缴 |
| `extraction_risk` | 字段置信度 <0.7 | 人工核对原图 |
| `identity_conflict` | 姓名不一致 | 阻塞 |

## 5. 覆盖率与置信度

```
coverage      = 有应发+实发的月份数 / 窗口月份数
full_coverage = 五项齐全的月份数 / 窗口月份数
confidence    = 各月字段置信度均值 × coverage
```

报告里每个指标都要带这三个值。

## 6. 依赖图（增量重算）

| 改动 | 需要重算 |
|---|---|
| 某月某字段 | 仅该月 + 年度汇总 |
| `si_personal_rate` | 全部月份 |
| `hf_rate_candidates` | 全部月份 |
| `monthly_salary_caliber` | 全部月份（口径说明） |

工作台按此规则重算，不重跑 OCR。

## 7. 边界

- 不做个税精确复现；个税只用于勾稽。
- 反推值不得再作为独立证据参与第二轮反推。
- 年度汇总只汇总有值月份，并同时给出覆盖率，避免“用缺失值凑总数”。
