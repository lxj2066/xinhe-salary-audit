# XinHe Salary Audit

**Evidence-first salary cross-check: verify the images, extract the numbers, reconcile them month by month.**

Built for headhunters, HR and anyone who has to trust a candidate's salary claims. It is not a black box that turns uploads into a verdict — it is a pipeline with an explicit review gate:

1. **Screen** — manipulation risk on every image (metadata / ELA / amount-region consistency)
2. **Extract** — OCR or manual entry for tax, bank, social insurance and housing fund
3. **Reconcile** — month by month: `gross − net ≈ social insurance + housing fund + IIT`
4. **Review** — an editable intermediate table before any report is produced
5. **Report** — self-contained HTML with coverage, confidence and version history

## China-specific rules

- **IIT**: annual bracket magnitude check only; never produces a “tax due” figure.
- **Cumulative withholding**: month-to-month tax variation is expected; monthly averages are not used to infer salary.
- **Year-end bonus**: scans six threshold points (36k/144k/300k/420k/660k/960k), flags within ±2%; only one separate-tax bonus per year; a January payment belongs to the new tax year.
- **Social insurance / housing fund**: base floors and caps are caller-supplied; July adjustment is structural, not an anomaly.
- **Housing fund rate**: 5%–12%, company-specific, can change mid-year; change-point detection included.
- **Rehired retirees**: no social insurance/housing fund; IIT only.
- **Labor remuneration**: different withholding; excluded from salary reconciliation.
- **Special additional deductions**: used only to explain residuals, never as a calculation input.
- **Foreign nationals**: out of scope.

## Why not another payslip OCR

We reviewed six adjacent projects; none combines OCR, salary verification and cross-document reconciliation:

| Project | What it does | Missing |
|---|---|---|
| [financial-ocr](https://github.com/Mermiges/financial-ocr) | Payslip/tax form extraction | Scaffolded; no reconciliation |
| [MCP-Buste-Paga](https://glama.ai/mcp/servers/morettimarco/MCP-Buste-Paga) | Italian payslips → SQLite | Single document; no cross-source |
| [payslip-overview](https://www.npmjs.com/package/@vineus/payslip-overview) | French payslip dashboard | No bank/social-insurance cross-check |
| [MCP-server-DocumentAnalysis](https://github.com/ashiqspace/MCP-server-DocumentAnalysis) | Document authenticity check | Online model; no deterministic reconciliation |
| [compliance-skills](https://github.com/chenqg618/compliance-skills) | Offline payroll table checks | Table-internal only |
| [PP-StructureV3](https://paddlepaddle.github.io/PaddleX/3.0-rc1/en/pipeline_usage/tutorials/ocr_pipelines/PP-StructureV3.html) | Table structure extraction | A capability, not a workflow |

XinHe fills the middle layer: **deterministic reconciliation + provenance + review gate**.

## Core features

- **Deterministic core**: every number comes from `crosscheck.py`, never from the language model
- **Image screening first**: high-risk images block the run by default
- **Incremental**: files are cached by SHA-256; unchanged files are not re-OCR'd
- **Versioned reports**: `report_v1.html`, `report_v2.html`; old versions are kept
- **Local workbench**: four upload slots, risk badges, editable table; listens on 127.0.0.1 only
- **Graceful degradation**: works without OCR via manual entry

## Layout

```
xinhe-salary-audit/
├── SKILL.md
├── references/
│   ├── data-schema.md
│   ├── crosscheck-rules.md
│   ├── china-policy.md
│   ├── ocr-and-forgery.md
│   └── benchmarks.md
├── scripts/
│   ├── normalize.py
│   ├── crosscheck.py
│   ├── forgery.py
│   ├── ocr.py
│   ├── tax.py
│   ├── report.py
│   └── templates/report.html.j2
├── workbench/
│   ├── server.py
│   └── index.html
└── tests/
    ├── selftest.py
    └── fixtures/case_zhangsan.json
```

## Install

```bash
git clone https://github.com/lxj2066/xinhe-salary-audit.git
cp -r xinhe-salary-audit/skills/xinhe-salary-audit ~/.claude/skills/
```

Optional OCR:

```bash
pip install ppocr-lite
```

Without it, the workbench marks images as “manual entry required”.

## Usage

### Workbench (recommended)

```bash
python workbench/server.py
# open http://127.0.0.1:8765
```

### CLI

```bash
python scripts/normalize.py case.json --out normalized.json
python scripts/crosscheck.py normalized.json --out findings.json
python scripts/report.py case.json findings.json --out report.html
```

### Self-test

```bash
python tests/selftest.py
```

## Safety and limits

- Local-only by default; the workbench never binds to a public interface.
- Image screening says “suspicious / needs review”, never “forged”; it is not a forensic opinion.
- No exact IIT reproduction, no payroll execution, no tax filing, no legal advice.
- Missing values stay `null` with an `UNKNOWN` reason; they are never guessed.
- Name mismatches block the run.

## License

[PolyForm Noncommercial License 1.0.0](LICENSE). Commercial use requires a separate licence — see [COMMERCIAL.md](COMMERCIAL.md).

Author: 李献杰 Lyon
