#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""薪核自检：内核、勾稽、报告、验图、OCR 解析。"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import normalize
import crosscheck
import report as report_mod
import forgery
import ocr
import test_forgery as tf

fails = []


def check(name, cond, detail=""):
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


case_raw = json.loads((ROOT / "tests" / "fixtures" / "case_zhangsan.json").read_text(encoding="utf-8"))
norm = normalize.normalize(case_raw)
check("normalize.months", len(norm["months"]) == 12, len(norm["months"]))

res = crosscheck.run(norm)
c = res["aggregate"]["counts"]
check("crosscheck.counts", c == {"green": 9, "yellow": 1, "red": 1, "partial": 1, "insufficient": 0}, c)
check("crosscheck.red_month", next(m["month"] for m in res["months"] if m["status"] == "red") == "2026-02")
check("crosscheck.partial_month", next(m["month"] for m in res["months"] if m["status"] == "partial") == "2025-09")
check("crosscheck.si_shift", any("si_base_shift" in m["tags"] for m in res["months"]))
check("crosscheck.hf_rate", res["rates"]["hf_selected"] == 0.12, res["rates"])
check("crosscheck.coverage", abs(res["aggregate"]["coverage"] - 1.0) < 1e-6)
check("crosscheck.full_coverage", abs(res["aggregate"]["full_coverage"] - round(11 / 12, 4)) < 1e-9, res["aggregate"]["full_coverage"])

# 身份冲突阻塞
bad = json.loads(json.dumps(case_raw))
bad["identity_sources"] = [{"source": "tax", "name": "张三"}, {"source": "bank", "name": "张山"}]
r2 = crosscheck.run(normalize.normalize(bad))
check("identity.blocking", r2["blocking"] is True and r2["identity"]["status"] == "conflict")

# 报告渲染
with tempfile.TemporaryDirectory() as td:
    out = Path(td) / "r.html"
    report_mod.render(normalize.normalize(case_raw), res, [], 1, [], out)
    html = out.read_text(encoding="utf-8")
    check("report.name", "张三" in html)
    check("report.diagnostic", "社保基数" in html)
    check("report.table", "<table>" in html)

# 验图
with tempfile.TemporaryDirectory() as td:
    clean = Path(td) / "c.jpg"
    tam = Path(td) / "t.jpg"
    boxes = tf.make_base(str(clean))
    tf.make_tampered(str(clean), str(tam), boxes)
    items = [
        {"text": "2026-05 工资明细", "box": boxes[0]},
        {"text": "应发工资 38,000.00", "box": boxes[1]},
        {"text": "社保个人 3,150.00", "box": boxes[2]},
        {"text": "公积金个人 3,600.00", "box": boxes[3]},
        {"text": "实发工资 28,750.00", "box": boxes[4]},
        {"text": "税额 2,500.00", "box": boxes[5]},
    ]
    a = forgery.analyze(str(clean), items)
    b = forgery.analyze(str(tam), items)
    check("forgery.clean_low", a["risk"] == "low", a["risk"])
    check("forgery.tampered", b["risk"] in ("medium", "high") and any(s["code"] == "editing_software" for s in b["signals"]), b["signals"])

# OCR 字段解析（不依赖引擎）
parsed = ocr.parse_fields({
    "available": True,
    "items": [
        {"text": "2026年5月 工资明细", "score": 0.95, "box": None},
        {"text": "应发工资 30,000.00", "score": 0.93, "box": None},
        {"text": "实发工资 20,750.00", "score": 0.94, "box": None},
        {"text": "社保个人 3,150.00", "score": 0.9, "box": None},
        {"text": "公积金个人 3,600.00", "score": 0.9, "box": None},
        {"text": "税额 2,500.00", "score": 0.9, "box": None},
    ],
})
check("ocr.month", parsed["month"] == "2026-05", parsed)
check("ocr.fields", parsed["fields"].get("gross_income") == 30000 and parsed["fields"].get("net_pay") == 20750, parsed["fields"])

# 个税粗估：高薪进入高税率档
import tax as tax_mod
est = tax_mod.estimate(100000, 10500, 12000)
check("tax.high_salary", est and est["band"] == "35%" and abs(est["tax"] - 18215) < 1, est)

# 社保基数超出上下限
bounded = json.loads(json.dumps(case_raw))
bounded["assumptions"]["si_base_bounds"] = [10000, 40000]
bounded["months"][0]["si_personal"] = 6000
rb = crosscheck.run(normalize.normalize(bounded))
check("bounds.si_out", any("si_base_out_of_bounds" in m["tags"] for m in rb["months"]), [m["tags"] for m in rb["months"]][:2])

# 公积金比例年中调整（5%–12% 可调）
changed = json.loads(json.dumps(case_raw))
for m in changed["months"][:6]:
    m["hf_personal"] = 1800
    m["net_pay"] = 22550
rc = crosscheck.run(normalize.normalize(changed))
check("hf.change_point", bool(rc["rates"]["hf_segments"]), rc["rates"])

# 退休返聘：不缴社保公积金，只核对个税
ret = json.loads(json.dumps(case_raw))
ret["months"] = [{
    "month": "2026-01", "gross_income": 20000, "net_pay": 17000, "tax_paid": 3000,
    "employment_type": "rehired_retiree"
}]
rr = crosscheck.run(normalize.normalize(ret))
ret_month = next(m for m in rr["months"] if m["month"] == "2026-01")
check("retiree.green", ret_month["status"] == "green", ret_month)
check("retiree.note", any(d["code"] == "rehired_retiree" for d in ret_month["diagnostics"]))

# 年终奖临界点
bon = json.loads(json.dumps(case_raw))
bon["months"][0]["bonus"] = 36000
rb2 = crosscheck.run(normalize.normalize(bon))
check("bonus.threshold", rb2["months"][0].get("bonus", {}).get("near_threshold") is True, rb2["months"][0].get("bonus"))

# 劳务报酬月份判 partial
lab = json.loads(json.dumps(case_raw))
lab["months"][0]["income_type"] = "labor"
rl = crosscheck.run(normalize.normalize(lab))
check("labor.partial", rl["months"][0]["status"] == "partial", rl["months"][0]["status"])

# 年度个税粗估存在
check("tax.annual_check", rc.get("tax_check") is not None, rc.get("tax_check"))

print()
if fails:
    print("FAILED:", fails)
    sys.exit(1)
print("ALL PASS")
