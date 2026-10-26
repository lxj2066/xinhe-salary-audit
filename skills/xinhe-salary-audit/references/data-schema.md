# 输入数据结构（data-schema）

## 1. 案件顶层

```json
{
  "case_id": "case_zhangsan_2025_07_2026_06",
  "person": { "name": "张三", "city": "杭州", "id_last4": "1234" },
  "window": { "start": "2025-07", "end": "2026-06" },
  "assumptions": {
    "monthly_salary_caliber": "gross_fixed",
    "si_personal_rate": 0.105,
    "hf_rate_candidates": [0.05, 0.07, 0.12],
    "rounding_tolerance": 1.0
  },
  "identity_sources": [
    { "source": "tax", "name": "张三" },
    { "source": "bank", "name": "张三" }
  ],
  "months": []
}
```

| 字段 | 说明 |
|---|---|
| `window` | 核验窗口，缺月份会补占位记录 |
| `monthly_salary_caliber` | `gross_fixed` / `net` / `total_package_div_12` |
| `si_personal_rate` | 社保个人合计比例；杭州常用 10.5% |
| `hf_rate_candidates` | 公积金比例候选；不一致时会标记多解 |
| `rounding_tolerance` | 允许的四舍五入误差（元） |
| `identity_sources` | 各来源姓名；不一致直接阻塞 |

## 2. 月份记录

值可以是数字，也可以是对象：

```json
{
  "month": "2025-07",
  "gross_income": 30000,
  "net_pay": 20750,
  "si_personal": 3150,
  "hf_personal": 3600,
  "tax_paid": 2500,
  "sources": {
    "gross_income": { "type": "ocr", "file": "tax_07.png", "confidence": 0.93 },
    "net_pay": { "type": "pdf_table", "file": "bank_07.pdf", "confidence": 0.95 }
  }
}
```

对象形式：

```json
{ "value": 30000, "source": "oral", "confidence": 0.55, "inferred": false }
```

## 3. 字段定义

| 字段 | 中文 | 口径 | 必填 |
|---|---|---|---|
| `gross_income` | 个税申报收入 | gross | 是（锚点） |
| `net_pay` | 银行实发 | net | 是（锚点） |
| `si_personal` | 社保个人扣款 | deduction | 否 |
| `hf_personal` | 公积金个人缴存 | deduction | 否 |
| `tax_paid` | 个税实缴 | tax | 否 |
| `si_base` | 社保基数 | base | 否 |
| `hf_base` | 公积金基数 | base | 否 |

## 4. 来源类型与默认置信度

| 类型 | 默认置信度 | 说明 |
|---|---|---|
| `pdf_table` | 0.92 | 原生 PDF 表格解析 |
| `manual` | 0.90 | 用户在工作台手填 |
| `ocr` | 0.85 | ppocr-lite 识别 |
| `oral` | 0.55 | 口述 |
| `inferred` | 0.40 | 反推；不得再作为独立来源 |

## 5. 校验规则

- `window.start` / `end` 必须为 `YYYY-MM`
- 月份必须落在窗口内
- 同一字段多个来源时，按“置信度高者优先”，并在 `sources` 保留冲突记录
- 缺字段写 `null`，不写 0
- 姓名出现多个 → `identity.conflict`，核验阻塞
