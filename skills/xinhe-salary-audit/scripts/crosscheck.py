#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""薪核 · 交叉核验内核（v1.0.0）

纯函数、无网络、无 LLM。所有数字来自这里，报告只负责渲染。
"""
from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

import tax as tax_mod

DEFAULT_THRESHOLDS = {"green": 0.10, "yellow": 0.20}
FIELD_ORDER = ["gross_income", "net_pay", "si_personal", "hf_personal", "tax_paid", "si_base", "hf_base"]


def _v(field):
    return None if not field else field.get("value")


def _c(field, default=0.0):
    return default if not field else float(field.get("confidence") or 0)


def _present(field):
    return field is not None and field.get("value") is not None


def _implied_base(amount, rate):
    if amount is None or not rate:
        return None
    return round(amount / rate, 2)


def _cv(values):
    vals = [v for v in values if v]
    if len(vals) < 2:
        return 0.0
    mean = statistics.fmean(vals)
    if mean == 0:
        return 0.0
    return statistics.pstdev(vals) / abs(mean)


def identity_check(case):
    sources = case.get("identity_sources") or []
    names = {str(s.get("name", "")).strip() for s in sources if s.get("name")}
    if len(names) > 1:
        return {
            "status": "conflict",
            "names": sorted(names),
            "detail": "不同来源的姓名不一致：" + "、".join(sorted(names)),
        }
    return {"status": "ok" if names else "unknown", "names": sorted(names)}


def analyze_month(rec, ctx):
    f = rec["fields"]
    emp = rec.get("employment_type") or "standard"
    income_type = rec.get("income_type") or "salary"
    gross, net = _v(f["gross_income"]), _v(f["net_pay"])
    si, hf, tax = _v(f["si_personal"]), _v(f["hf_personal"]), _v(f["tax_paid"])
    month = rec["month"]
    out = {
        "month": month,
        "employment_type": emp,
        "income_type": income_type,
        "gross": gross, "net": net, "si": si, "hf": hf, "tax": tax,
        "status": "insufficient",
        "deviation": None, "deviation_pct": None,
        "expected_deduction": None, "actual_deduction": None,
        "confidence": 0.0, "tags": [], "diagnostics": [],
    }
    if gross is None or net is None:
        out["diagnostics"].append({
            "code": "missing_anchor",
            "label": "缺少个税收入或银行实发",
            "detail": "没有这两项就无法做勾稽。",
            "action": "补个税截图或银行流水，或口述该月数字。",
        })
        return out

    if emp == "rehired_retiree":
        # 退休返聘通常不缴社保/公积金，只核对个税
        expected = tax if tax is not None else 0
        out["diagnostics"].append({
            "code": "rehired_retiree",
            "label": "退休返聘口径",
            "detail": "按仅扣个税处理，社保/公积金不计入应扣合计。",
            "action": "若实际仍在缴社保/公积金，请把 employment_type 改为 standard。",
        })
    else:
        expected = sum(x for x in (si, hf, tax) if x is not None)
    actual = gross - net
    residual = actual - expected
    base = expected if expected > 0 else max(abs(actual), 1.0)
    pct = abs(residual) / base
    has_tax = tax is not None

    out.update({
        "expected_deduction": round(expected, 2),
        "actual_deduction": round(actual, 2),
        "deviation": round(residual, 2),
        "deviation_pct": round(pct, 4),
    })

    present = [f[k] for k in ("gross_income", "net_pay", "si_personal", "hf_personal", "tax_paid") if _present(f[k])]
    conf = statistics.fmean([float(x["confidence"]) for x in present]) if present else 0.0
    if not has_tax:
        conf *= 0.9
    if any(x.get("inferred") for x in present):
        conf = min(conf, 0.5)
    out["confidence"] = round(conf, 3)

    # 偏差分级
    if abs(residual) <= ctx["tolerance"]:
        grade = "green"
    elif pct <= ctx["green"]:
        grade = "green"
    elif pct <= ctx["yellow"]:
        grade = "yellow"
    else:
        grade = "red"

    # 13薪 / 一次性奖金：收入显著高于常态，先在报告里标出来，不直接判红
    if ctx["median_gross"] and gross > ctx["median_gross"] * 1.25:
        out["tags"].append("gross_jump")
        out["diagnostics"].append({
            "code": "one_off_bonus",
            "label": "本月收入显著高于常态",
            "detail": f"{gross:.0f} vs 常态中位数 {ctx['median_gross']:.0f}",
            "action": "确认是否包含年终奖/一次性奖金；若是，扣减项应同月匹配。",
        })
        if grade == "red":
            grade = "yellow"

    if not has_tax:
        out["tags"].append("tax_missing")
        out["diagnostics"].append({
            "code": "tax_missing",
            "label": "未提供个税",
            "detail": "差额里包含个税，无法精确判级，暂按部分核验处理。",
            "action": "补个税截图可把该月升级为完整核验。",
        })
        if pct > ctx["yellow"]:
            out["tags"].append("large_residual")
            out["diagnostics"].append({
                "code": "large_residual_unexplained",
                "label": "差额明显超过已知扣款",
                "detail": f"即使按未知个税处理，仍有约 {residual:.0f} 元无法解释。",
                "action": "优先补个税截图；若仍对不上，检查是否有其他扣款或录入错误。",
            })

    # 解释性诊断
    if residual > ctx["tolerance"] and has_tax:
        out["diagnostics"].append({
            "code": "deduction_shortfall",
            "label": "应发与实发的差额大于已知扣款",
            "detail": f"多扣了约 {residual:.0f} 元",
            "action": "优先用专项附加扣除（子女教育、房贷/租金、赡养老人、个人养老金等）解释——截图通常看不到；其次查补充公积金、企业年金、借款、个税补缴。",
        })
    elif residual < -ctx["tolerance"]:
        out["diagnostics"].append({
            "code": "net_extra",
            "label": "实发高于应发差额",
            "detail": f"少了约 {abs(residual):.0f} 元的扣款",
            "action": "检查报销、补贴、绩效另发、税后退款。",
        })

    # 社保基数反推
    if si is not None and ctx["si_rate"]:
        implied = _implied_base(si, ctx["si_rate"])
        out["si_base_implied"] = implied
        if ctx["si_base_median"] and implied:
            shift = abs(implied - ctx["si_base_median"]) / ctx["si_base_median"]
            if shift > 0.15:
                out["tags"].append("si_base_shift")
                out["diagnostics"].append({
                    "code": "si_base_shift",
                    "label": "社保基数疑似变化",
                    "detail": f"本月反推基数 {implied:.0f}，与常态 {ctx['si_base_median']:.0f} 相差 {shift*100:.0f}%",
                    "action": ("1 月/7 月是常见调基月，属结构性变化；确认当年当地上下限即可。"
                               if month[5:] in ("01", "07") else "确认是否调基（常见于 1 月/7 月）或存在补缴。"),
                })
                if grade == "green":
                    grade = "yellow"
        bounds = ctx.get("si_bounds")
        if bounds and implied and not (float(bounds[0]) <= implied <= float(bounds[1])):
            out["tags"].append("si_base_out_of_bounds")
            out["diagnostics"].append({
                "code": "si_base_out_of_bounds",
                "label": "社保基数超出当年上下限",
                "detail": f"反推基数 {implied:.0f}，设定区间 {bounds[0]}–{bounds[1]}",
                "action": "确认当年当地上下限；若工资高于上限，应按上限缴纳，超额部分不进入社保基数。",
            })
            if grade == "green":
                grade = "yellow"

    # 公积金比例多解
    if hf is not None and ctx["hf_rates"]:
        cands = [{"rate": r, "base": _implied_base(hf, r)} for r in ctx["hf_rates"]]
        out["hf_candidates"] = cands

    if any(_present(f[k]) and float(f[k]["confidence"]) < 0.7 for k in FIELD_ORDER):
        out["tags"].append("low_confidence")
        out["diagnostics"].append({
            "code": "extraction_risk",
            "label": "存在低置信度字段",
            "detail": "OCR 或口述字段置信度低于 0.7。",
            "action": "人工核对原始截图，或在中间表直接改正。",
        })

    # 个税粗估：只做异常提示，不参与判级
    est = tax_mod.estimate(gross, si, hf)
    if est:
        out["tax_estimate"] = dict(est, interval=tax_mod.interval(est))
        if tax is not None and est["tax"] > 0:
            lo, hi = est["tax"] * 0.5, est["tax"] * 1.6
            if tax < lo or tax > hi:
                out["tags"].append("tax_outlier")
                out["diagnostics"].append({
                    "code": "tax_outlier",
                    "label": "个税与收入粗估差距较大",
                    "detail": f"上报 {tax:.0f}，粗估区间 {lo:.0f}–{hi:.0f}（{est['band']} 档）",
                    "action": "累计预扣、年终奖单独计税、专项附加扣除都会造成偏差；核对个税截图即可，本条不改判级。",
                })
        elif tax is None:
            out["diagnostics"].append({
                "code": "tax_estimated",
                "label": "个税缺失，给出粗略区间",
                "detail": f"按 {est['band']} 档粗估约 {est['tax']:.0f} 元（区间 {est['tax']*0.5:.0f}–{est['tax']*1.6:.0f}）",
                "action": "该区间只用于理解差额，不作为判级依据；补个税截图可精确核验。",
            })

    # 全年一次性奖金：临界点扫描与跨年归属
    bonus = _v(f.get("bonus"))
    explicit = bonus is not None
    if bonus is None and ctx["median_gross"] and gross > ctx["median_gross"] * 1.25:
        bonus = gross - ctx["median_gross"]
    if bonus and bonus > 0:
        scan = tax_mod.bonus_scan(bonus)
        out["bonus"] = dict(scan, explicit=explicit)
        if scan["near_threshold"]:
            out["tags"].append("bonus_threshold")
            out["diagnostics"].append({
                "code": "bonus_threshold",
                "label": "年终奖位于税率跳档临界点",
                "detail": (f"奖金 {bonus:.0f} 距 {scan['nearest_threshold']} 仅 {scan['distance_pct']*100:.1f}%；"
                           f"多发 1 元税额约增加 {scan['jump']:.0f} 元"),
                "action": "确认是否为薪酬结构设计，或存在拆分/递延发放；这是解释项，不是造假结论。",
            })
        if month[5:] == "01" and ctx.get("calendar_year"):
            out["tags"].append("cross_year_bonus")
            out["diagnostics"].append({
                "code": "cross_year_bonus",
                "label": "奖金可能跨年归属",
                "detail": "1 月发放的奖金通常计入发放年度，不属于上一个纳税年度。",
                "action": "报告已区分“个税年度口径”与“现金流入口径”，请确认归属年度。",
            })

    if income_type == "labor":
        out["status"] = "partial"
        out["tags"].append("labor_income")
        out["diagnostics"].append({
            "code": "labor_income",
            "label": "劳务报酬月份",
            "detail": "劳务报酬按 20%–40% 预扣，逻辑与工资薪金不同。",
            "action": "该月不参与工资勾稽；如需核验，请单独提供劳务报酬发票或结算单。",
        })
    elif emp == "rehired_retiree" and tax is None:
        out["status"] = "partial"
    else:
        out["status"] = "partial" if not has_tax else grade
    return out


def run(case, thresholds=None):
    th = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        th.update(thresholds)
    assumptions = case.get("assumptions") or {}
    si_rate = float(assumptions.get("si_personal_rate") or 0.105)
    hf_rates = assumptions.get("hf_rate_candidates") or [0.05, 0.07, 0.12]
    tolerance = float(assumptions.get("rounding_tolerance") or 1.0)

    months = case["months"]
    grosses = [m["fields"]["gross_income"]["value"] for m in months if _present(m["fields"]["gross_income"])]
    median_gross = statistics.median(grosses) if grosses else None
    si_bases = []
    for m in months:
        si = _v(m["fields"]["si_personal"])
        if si is not None and si_rate:
            si_bases.append(_implied_base(si, si_rate))
    ctx = {
        "green": th["green"], "yellow": th["yellow"], "tolerance": tolerance,
        "si_rate": si_rate, "hf_rates": hf_rates,
        "si_bounds": assumptions.get("si_base_bounds"),
        "hf_bounds": assumptions.get("hf_base_bounds"),
        "calendar_year": str(case.get("window", {}).get("start", ""))[:4] == str(case.get("window", {}).get("end", ""))[:4],
        "median_gross": median_gross,
        "si_base_median": statistics.median(si_bases) if si_bases else None,
    }

    identity = identity_check(case)
    rows = [analyze_month(m, ctx) for m in months]

    # 公积金比例：跨月一致性 + 与社保基数/收入中位数的接近程度，双重打分
    # 同时尝试检测“年中调整比例”（5%–12% 可由公司调整）
    hf_rate = None
    hf_cv = None
    hf_segments = None
    ref_base = ctx["si_base_median"] or median_gross

    def fit_hf(pairs):
        best = None
        for r in hf_rates:
            bases = [hf / r for _, hf in pairs if hf]
            if len(bases) < 2:
                continue
            cv = _cv(bases)
            base_med = statistics.median(bases)
            distance = abs(base_med - ref_base) / ref_base if ref_base else 0
            score = cv + 0.5 * distance
            if best is None or score < best[0]:
                best = (score, r, cv, base_med)
        return best

    pairs = [(m["month"], _v(m["fields"]["hf_personal"])) for m in months if _v(m["fields"]["hf_personal"]) is not None]
    global_fit = fit_hf(pairs)
    if global_fit:
        _, hf_rate, hf_cv, _ = global_fit
        # 变更点检测：分段后 CV 显著更低，才认为是调比例
        best_split = None
        for i in range(3, len(pairs) - 2):
            left, right = pairs[:i], pairs[i:]
            lf, rf = fit_hf(left), fit_hf(right)
            if not lf or not rf:
                continue
            score = (len(left) * lf[2] + len(right) * rf[2]) / len(pairs)
            if best_split is None or score < best_split[0]:
                best_split = (score, i, lf, rf)
        if best_split and hf_cv > 0 and best_split[0] < hf_cv * 0.5:
            _, i, lf, rf = best_split
            hf_segments = [
                {"start": pairs[0][0], "end": pairs[i - 1][0], "rate": lf[1], "cv": round(lf[2], 4)},
                {"start": pairs[i][0], "end": pairs[-1][0], "rate": rf[1], "cv": round(rf[2], 4)},
            ]
            hf_rate = None
        elif hf_cv > 0.15:
            hf_rate = None

    hf_bounds_note = None
    if ctx.get("hf_bounds") and pairs:
        rate_for_bounds = hf_segments[0]["rate"] if hf_segments else hf_rate
        if rate_for_bounds:
            bases = [hf / rate_for_bounds for _, hf in pairs if hf]
            lo, hi = float(ctx["hf_bounds"][0]), float(ctx["hf_bounds"][1])
            if any(not (lo <= b <= hi) for b in bases):
                hf_bounds_note = f"公积金基数超出设定区间 {lo:.0f}–{hi:.0f}"

    def total(key):
        return round(sum(r[key] for r in rows if r.get(key) is not None), 2)

    # 年度口径个税粗估（只做量级核对）
    gross_sum = sum(g for g in grosses if g)
    si_sum = sum(_v(m["fields"]["si_personal"]) or 0 for m in months)
    hf_sum = sum(_v(m["fields"]["hf_personal"]) or 0 for m in months)
    tax_sum = sum(_v(m["fields"]["tax_paid"]) or 0 for m in months)
    tax_check = tax_mod.annual_check(gross_sum, si_sum, hf_sum, tax_sum)

    # 一年只能有一次单独计税的年终奖
    bonus_months = [r["month"] for r in rows if r.get("bonus")]
    if len(bonus_months) > 1:
        first = next(r for r in rows if r["month"] == bonus_months[0])
        first["diagnostics"].append({
            "code": "multiple_bonus",
            "label": "同一年出现多笔疑似年终奖",
            "detail": "年内单独计税只允许一次，其余应并入综合所得。",
            "action": "确认各笔奖金的归属年度与计税方式，不要自动都按单独计税处理。",
        })
        first["tags"].append("multiple_bonus")

    counts = {s: 0 for s in ("green", "yellow", "red", "partial", "insufficient")}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    full_months = sum(1 for m in months if all(_present(m["fields"][k]) for k in ("gross_income", "net_pay", "si_personal", "hf_personal", "tax_paid")))
    anchor_months = sum(1 for r in rows if r["status"] != "insufficient")
    coverage = round(anchor_months / len(months), 4) if months else 0
    full_coverage = round(full_months / len(months), 4) if months else 0
    conf = statistics.fmean([r["confidence"] for r in rows if r["status"] != "insufficient"]) if anchor_months else 0
    conf = round(conf * coverage, 3)

    conclusion = {
        "usable": [r["month"] for r in rows if r["status"] == "green"],
        "needs_review": [r["month"] for r in rows if r["status"] in ("yellow", "partial")],
        "unusable": [r["month"] for r in rows if r["status"] in ("red", "insufficient")],
    }

    return {
        "tool": "xinhe-salary-audit",
        "version": "1.0.0",
        "case_id": case.get("case_id"),
        "person": case.get("person", {}),
        "window": case.get("window"),
        "identity": identity,
        "thresholds": th,
        "rates": {"si_personal": si_rate, "hf_selected": hf_rate, "hf_cv": round(hf_cv, 4) if hf_cv is not None else None,
                  "hf_segments": hf_segments, "hf_bounds_note": hf_bounds_note},
        "months": rows,
        "aggregate": {
            "months": len(months),
            "anchor_months": anchor_months,
            "full_months": full_months,
            "coverage": coverage,
            "full_coverage": full_coverage,
            "confidence": conf,
            "annual_gross": total("gross"),
            "annual_net": total("net"),
            "annual_deduction": total("actual_deduction"),
            "avg_monthly_gross": round(total("gross") / anchor_months, 2) if anchor_months else None,
            "counts": counts,
        },
        "conclusion": conclusion,
        "tax_check": tax_check,
        "bonus_months": bonus_months,
        "blocking": identity["status"] == "conflict",
    }


def affected_months(case, month, field):
    """修改某字段后，需要重算哪些月份。"""
    if field in ("si_personal_rate", "hf_rate_candidates", "monthly_salary_caliber"):
        return [m["month"] for m in case["months"]]
    return [month]


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    case = json.loads(Path(a.input).read_text(encoding="utf-8-sig"))
    result = run(case)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
