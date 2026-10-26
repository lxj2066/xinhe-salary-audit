#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""薪核 · OCR 适配层（v1.0.0）

- 引擎：ppocr-lite（可选，缺失时降级为手动录入）
- 缓存：按文件 sha256 缓存，重复上传不重新识别
- 解析：把 OCR 文本映射到薪酬字段，低置信度如实标注
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "xinhe-salary-audit" / "ocr"
AMOUNT_RE = re.compile(r"[-+]?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|[-+]?\d+(?:\.\d{1,2})?")
MONTH_RE = re.compile(r"(20\d{2})\s*[-年/.]\s*(\d{1,2})")

FIELD_HINTS = {
    "gross_income": ["应发", "工资总额", "收入", "税前"],
    "net_pay": ["实发", "到手", "入账", "代发", "税后"],
    "si_personal": ["社保", "养老", "医疗", "失业"],
    "hf_personal": ["公积金"],
    "tax_paid": ["个税", "税额", "已缴", "应纳税额"],
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def available():
    try:
        import ppocr_lite  # noqa: F401
        return True, "ppocr-lite"
    except Exception as e:
        return False, f"未安装 ppocr-lite（{type(e).__name__}）。安装：pip install ppocr-lite"


def _engine():
    from ppocr_lite import PPOCRLite
    return PPOCRLite()


def extract(path, use_cache=True):
    path = Path(path)
    key = sha256(path)
    cache_file = CACHE_DIR / f"{key}.json"
    if use_cache and cache_file.exists():
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        data["cached"] = True
        return data

    ok, reason = available()
    if not ok:
        return {"available": False, "reason": reason, "items": [], "hash": key}

    try:
        engine = _engine()
        items = []
        for r in engine.run(str(path)):
            box = getattr(r, "box", None)
            items.append({
                "text": getattr(r, "text", ""),
                "score": round(float(getattr(r, "score", 0.0)), 3),
                "box": [int(v) for v in box.reshape(-1)[:4]] if box is not None else None,
            })
        data = {"available": True, "engine": "ppocr-lite", "items": items, "hash": key, "cached": False}
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data
    except Exception as e:
        return {"available": False, "reason": f"识别失败：{e}", "items": [], "hash": key}


def _amount(line):
    vals = AMOUNT_RE.findall(line.replace(" ", ""))
    if not vals:
        return None
    try:
        return float(vals[-1].replace(",", ""))
    except ValueError:
        return None


def parse_fields(ocr):
    """从 OCR 行里提取月份与薪酬字段。只认有明确标签的行，不做猜测。"""
    if not ocr.get("available"):
        return {"ok": False, "reason": ocr.get("reason"), "month": None, "fields": {}}
    items = ocr.get("items", [])
    lines = [it["text"] for it in items if it.get("text")]
    full = "\n".join(lines)

    month = None
    m = MONTH_RE.search(full)
    if m:
        month = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"

    fields, conf = {}, {}
    for fname, hints in FIELD_HINTS.items():
        best = None
        for it in items:
            text = it.get("text", "")
            if not any(h in text for h in hints):
                continue
            val = _amount(text)
            if val is None:
                continue
            score = float(it.get("score") or 0)
            if best is None or score > best[1]:
                best = (val, score, text)
        if best:
            fields[fname] = best[0]
            conf[fname] = round(min(best[1], 0.95), 3)

    return {
        "ok": bool(month and fields),
        "month": month,
        "fields": fields,
        "confidence": conf,
        "lines": lines,
        "reason": None if month else "未识别到月份",
    }


def doctor():
    ok, reason = available()
    return {
        "ppocr_lite": ok,
        "engine": reason,
        "install": "pip install ppocr-lite" if not ok else None,
        "cache_dir": str(CACHE_DIR),
        "cache_files": len(list(CACHE_DIR.glob("*.json"))) if CACHE_DIR.exists() else 0,
    }


if __name__ == "__main__":
    import sys
    print(json.dumps(doctor(), ensure_ascii=False, indent=2))
    if len(sys.argv) > 1:
        ocr = extract(sys.argv[1])
        print(json.dumps(parse_fields(ocr), ensure_ascii=False, indent=2))
