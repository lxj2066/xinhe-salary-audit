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


# ---------------- 年度口径（累计预扣的近似上限） ----------------
ANNUAL_BRACKETS = [
    (36000, 0.03, 0),
    (144000, 0.10, 2520),
    (300000, 0.20, 16920),
    (420000, 0.25, 31920),
    (660000, 0.30, 52920),
    (960000, 0.35, 85920),
    (float("inf"), 0.45, 181920),
]


def estimate_annual(taxable):
    if taxable is None:
        return None
    taxable = max(0.0, float(taxable))
    for upper, rate, quick in ANNUAL_BRACKETS:
        if taxable <= upper:
            return {"taxable": round(taxable, 2), "rate": rate,
                    "tax": round(max(0.0, taxable * rate - quick), 2),
                    "band": f"{rate*100:.0f}%"}
    return None


# ---------------- 全年一次性奖金 ----------------
BONUS_THRESHOLDS = [36000, 144000, 300000, 420000, 660000, 960000]


def separate_bonus_tax(amount):
    """单独计税：奖金÷12 查月度税率表，再用全额乘税率减速算扣除。"""
    if amount is None or amount <= 0:
        return 0.0
    monthly = amount / 12.0
    for upper, rate, quick in BRACKETS:
        if monthly <= upper:
            return round(max(0.0, amount * rate - quick), 2)
    return 0.0


def bonus_scan(amount):
    """临界点扫描：距离最近跳档点 ≤2% 时提示。"""
    if amount is None or amount <= 0:
        return None
    nearest = min(BONUS_THRESHOLDS, key=lambda x: abs(x - amount))
    dist = abs(amount - nearest) / nearest
    tax_at = separate_bonus_tax(nearest)
    tax_over = separate_bonus_tax(nearest + 1)
    return {
        "amount": round(amount, 2),
        "nearest_threshold": nearest,
        "distance_pct": round(dist, 4),
        "near_threshold": dist <= 0.02,
        "tax_at_threshold": tax_at,
        "tax_one_more": tax_over,
        "jump": round(tax_over - tax_at, 2),
    }


def annual_check(gross_annual, si_annual, hf_annual, tax_annual, threshold=60000.0):
    """年度勾稽参考：只看量级，不做精确复现。"""
    if not gross_annual:
        return None
    taxable = max(0.0, gross_annual - threshold - (si_annual or 0) - (hf_annual or 0))
    est = estimate_annual(taxable)
    if not est or not tax_annual:
        return {"taxable": round(taxable, 2), "estimate": est, "reported": tax_annual}
    ratio = tax_annual / est["tax"] if est["tax"] else None
    return {
        "taxable": round(taxable, 2),
        "estimate": est,
        "reported": round(tax_annual, 2),
        "ratio": round(ratio, 3) if ratio else None,
        "outlier": bool(ratio and (ratio < 0.4 or ratio > 2.5)),
        "note": "年度粗估未计专项附加扣除与一次性奖金计税方式，仅用于量级核对",
    }
