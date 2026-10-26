#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""薪核 · 数据归一化（v1.0.0）

把用户给的结构化输入（或 OCR 提取结果）归一成统一 schema：
- 字段可以是纯数字，也可以是 {value, source, confidence}
- 缺失月份补齐为占位记录
- 每条字段保留来源与置信度，供后续溯源
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

FIELD_DEFS = {
    "gross_income": {"label": "个税申报收入", "caliber": "gross", "required": True},
    "net_pay":      {"label": "银行实发",     "caliber": "net",   "required": True},
    "si_personal":  {"label": "社保个人扣款", "caliber": "deduction", "required": False},
    "hf_personal":  {"label": "公积金个人缴存", "caliber": "deduction", "required": False},
    "tax_paid":     {"label": "个税实缴",     "caliber": "tax",   "required": False},
    "bonus":        {"label": "全年一次性奖金", "caliber": "bonus", "required": False},
    "si_base":      {"label": "社保基数",     "caliber": "base",  "required": False},
    "hf_base":      {"label": "公积金基数",   "caliber": "base",  "required": False},
}

SOURCE_CONF = {"ocr": 0.85, "pdf_table": 0.92, "oral": 0.55, "inferred": 0.4, "manual": 0.9}


def _num(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _field(raw, source_meta):
    """把纯数字或对象统一成 {value, source, confidence, raw_ref, inferred}。"""
    if raw is None:
        return None
    if isinstance(raw, dict):
        value = _num(raw.get("value"))
        src = raw.get("source") or (source_meta or {}).get("type") or "manual"
        conf = raw.get("confidence", SOURCE_CONF.get(src, 0.6))
        return {
            "value": value,
            "source": src,
            "confidence": round(float(conf), 3),
            "raw_ref": raw.get("raw_ref") or (source_meta or {}).get("file"),
            "inferred": bool(raw.get("inferred", src == "inferred")),
        }
    value = _num(raw)
    if value is None:
        return None
    src = (source_meta or {}).get("type") or "manual"
    conf = (source_meta or {}).get("confidence", SOURCE_CONF.get(src, 0.6))
    return {
        "value": value,
        "source": src,
        "confidence": round(float(conf), 3),
        "raw_ref": (source_meta or {}).get("file"),
        "inferred": src == "inferred",
    }


def month_range(start: str, end: str):
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def normalize(case: dict) -> dict:
    window = case.get("window") or {}
    start = window.get("start")
    end = window.get("end")
    if not start or not end:
        raise ValueError("window.start / window.end 必填（YYYY-MM）")

    months_in = {m.get("month"): m for m in case.get("months", []) if m.get("month")}
    months = []
    for key in month_range(start, end):
        src = months_in.get(key, {})
        sources = src.get("sources") or {}
        fields = {}
        for fname in FIELD_DEFS:
            fields[fname] = _field(src.get(fname), sources.get(fname))
        months.append({
            "month": key,
            "employment_type": src.get("employment_type") or "standard",
            "income_type": src.get("income_type") or "salary",
            "fields": fields,
        })

    return {
        "schema_version": "1.0",
        "case_id": case.get("case_id") or f"case_{date.today().isoformat()}",
        "person": case.get("person") or {},
        "window": {"start": start, "end": end, "months": len(months)},
        "assumptions": {
            "monthly_salary_caliber": case.get("assumptions", {}).get("monthly_salary_caliber", "gross_fixed"),
            "si_personal_rate": case.get("assumptions", {}).get("si_personal_rate", 0.105),
            "hf_rate_candidates": case.get("assumptions", {}).get("hf_rate_candidates", [round(x / 100, 2) for x in range(5, 13)]),
            "si_base_bounds": case.get("assumptions", {}).get("si_base_bounds"),
            "hf_base_bounds": case.get("assumptions", {}).get("hf_base_bounds"),
            "rounding_tolerance": case.get("assumptions", {}).get("rounding_tolerance", 1.0),
        },
        "identity_sources": case.get("identity_sources", []),
        "months": months,
    }


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    data = normalize(load(a.input))
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
