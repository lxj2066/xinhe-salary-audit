#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""薪核 · 中国个税粗估（v1.0.0）

用途：**只做勾稽参考与异常提示**，不出具“应缴税额”结论。
方法：按月换算的综合所得税率表做粗略估算，忽略累计预扣、专项附加扣除、
年终奖单独计税等差异，因此结果是一个宽区间，不是精确值。
"""
from __future__ import annotations

# 月度换算税率表：(上限, 税率, 速算扣除数)
BRACKETS = [
    (3000, 0.03, 0),
    (12000, 0.10, 210),
    (25000, 0.20, 1410),
    (35000, 0.25, 2660),
    (55000, 0.30, 4410),
    (80000, 0.35, 7160),
    (float("inf"), 0.45, 15160),
]


def estimate(gross, si=0, hf=0, threshold=5000.0):
    if gross is None:
        return None
    taxable = max(0.0, float(gross) - float(threshold) - float(si or 0) - float(hf or 0))
    for upper, rate, quick in BRACKETS:
        if taxable <= upper:
            tax = max(0.0, taxable * rate - quick)
            return {
                "taxable": round(taxable, 2),
                "rate": rate,
                "quick_deduction": quick,
                "tax": round(tax, 2),
                "band": f"{rate*100:.0f}%",
                "note": "粗略估算，未计累计预扣与专项附加扣除",
            }
    return None


def interval(est, low=0.5, high=1.6):
    """给一个宽区间，用于判断“上报个税是否离谱”。"""
    if not est:
        return None
    return {"low": round(est["tax"] * low, 2), "high": round(est["tax"] * high, 2)}
