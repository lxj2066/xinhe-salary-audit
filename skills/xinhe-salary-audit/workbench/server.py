#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""薪核 · 本地工作台（v1.0.0）

零依赖 HTTP 服务（Python 标准库），只监听 127.0.0.1。
- 四个上传栏：个税 / 银行流水 / 社保 / 公积金
- 上传即做图片风险筛查 + OCR（有则用，无则待手动录入）
- 按文件哈希缓存：没变的资料不会重跑
- 审核表可改，改完只重算受影响月份
- 报告带版本号，不覆盖历史

启动：
  python workbench/server.py
然后打开 http://127.0.0.1:8765
"""
from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import crosscheck
import normalize
import ocr
import forgery
import report as report_mod

CASES = Path(__file__).parent / "cases"
WEB = Path(__file__).parent
LOCK = threading.Lock()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def case_dir(case_id):
    safe = "".join(c for c in case_id if c.isalnum() or c in "-_")
    if not safe:
        raise ValueError("非法 case_id")
    p = CASES / safe
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_json(path, default=None):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8-sig"))
    return default if default is not None else {}


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


SLOT_FIELDS = {
    "tax": ["gross_income", "tax_paid"],
    "bank": ["net_pay"],
    "si": ["si_personal"],
    "hf": ["hf_personal"],
    "other": ["gross_income", "net_pay", "si_personal", "hf_personal", "tax_paid"],
}


def api_case(body):
    cid = body.get("case_id") or f"case_{datetime.now():%Y%m%d_%H%M%S}"
    d = case_dir(cid)
    case = {
        "case_id": cid,
        "person": body.get("person") or {},
        "window": body.get("window") or {},
        "assumptions": body.get("assumptions") or {
            "monthly_salary_caliber": "gross_fixed",
            "si_personal_rate": 0.105,
            "hf_rate_candidates": [0.05, 0.07, 0.12],
            "rounding_tolerance": 1.0,
        },
        "identity_sources": [],
    }
    write_json(d / "case.json", case)
    if not (d / "state.json").exists():
        write_json(d / "state.json", {"state": "COLLECTING", "version": 0, "changelog": []})
    return {"ok": True, "case_id": cid, "case": case}


def api_upload(body):
    cid = body.get("case_id")
    slot = body.get("slot") or "other"
    filename = Path(body.get("filename") or "upload").name
    data = base64.b64decode(body.get("data_b64") or "")
    d = case_dir(cid)
    up_dir = d / "uploads" / slot
    up_dir.mkdir(parents=True, exist_ok=True)

    h = hashlib.sha256(data).hexdigest()
    uploads = read_json(d / "uploads.json", {})
    if h in uploads:
        return {"ok": True, "cached": True, "upload": uploads[h]}

    path = up_dir / f"{h[:10]}_{filename}"
    path.write_bytes(data)

    result = {"hash": h, "filename": filename, "slot": slot,
              "path": str(path), "uploaded_at": now()}

    if path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
        result["forgery"] = forgery.analyze(path)
        ocr_data = ocr.extract(path)
        parsed = ocr.parse_fields(ocr_data)
        result["ocr"] = {"available": ocr_data.get("available", False),
                        "reason": ocr_data.get("reason"),
                        "items": ocr_data.get("items", []),
                        "cached": ocr_data.get("cached", False)}
        result["parsed"] = parsed
        result["ocr_status"] = "ok" if parsed.get("ok") else ("manual" if ocr_data.get("available") else "manual")
    else:
        result["forgery"] = {"risk": "unknown", "signals": [], "caveats": ["非图片文件，未做像素级筛查"]}
        result["ocr"] = {"available": False, "reason": "非图片"}
        result["parsed"] = {"ok": False, "month": None, "fields": {}}
        result["ocr_status"] = "manual"

    uploads[h] = result
    write_json(d / "uploads.json", uploads)
    return {"ok": True, "cached": False, "upload": result}


def api_manual(body):
    cid = body.get("case_id")
    d = case_dir(cid)
    overrides = read_json(d / "overrides.json", {})
    month = body.get("month")
    field = body.get("field")
    if not month or field not in normalize.FIELD_DEFS:
        return {"ok": False, "error": "month/field 非法"}
    value = body.get("value")
    overrides.setdefault(month, {})[field] = value
    write_json(d / "overrides.json", overrides)
    return {"ok": True, "overrides": overrides}


def build_case(d):
    case = read_json(d / "case.json")
    uploads = read_json(d / "uploads.json", {})
    overrides = read_json(d / "overrides.json", {})
    months = {}

    for up in uploads.values():
        parsed = up.get("parsed") or {}
        month = parsed.get("month")
        if not month:
            continue
        allowed = SLOT_FIELDS.get(up.get("slot"), SLOT_FIELDS["other"])
        rec = months.setdefault(month, {"month": month, "sources": {}})
        for f, v in (parsed.get("fields") or {}).items():
            if f not in allowed:
                continue
            rec[f] = v
            rec["sources"][f] = {
                "type": "ocr",
                "file": up.get("filename"),
                "confidence": (parsed.get("confidence") or {}).get(f, 0.75),
            }

    for month, fields in overrides.items():
        rec = months.setdefault(month, {"month": month, "sources": {}})
        for f, v in fields.items():
            rec[f] = v
            rec["sources"][f] = {"type": "manual", "confidence": 0.9}

    case["months"] = sorted(months.values(), key=lambda x: x["month"])
    return case


def api_analyze(body):
    cid = body.get("case_id")
    force = bool(body.get("force"))
    d = case_dir(cid)
    case = build_case(d)
    if not case.get("months"):
        return {"ok": False, "error": "还没有可用的月份数据：请上传能识别月份的截图，或手动录入。"}

    uploads = read_json(d / "uploads.json", {})
    high = [u for u in uploads.values() if (u.get("forgery") or {}).get("risk") == "high"]
    if high and not force:
        return {"ok": False, "blocked": True,
                "error": f"有 {len(high)} 张图片被标为高风险，请先确认来源，或选择“仍然继续”。",
                "images": [{"filename": u["filename"], "signals": (u.get("forgery") or {}).get("signals", [])} for u in high]}

    norm = normalize.normalize(case)
    findings = crosscheck.run(norm)
    write_json(d / "normalized.json", norm)
    write_json(d / "findings.json", findings)
    state = read_json(d / "state.json", {"state": "COLLECTING", "version": 0, "changelog": []})
    state["state"] = "REVIEW"
    write_json(d / "state.json", state)
    return {"ok": True, "findings": findings}


def api_report(body):
    cid = body.get("case_id")
    d = case_dir(cid)
    findings = read_json(d / "findings.json", None)
    if not findings:
        return {"ok": False, "error": "请先核验再生成报告"}
    case = read_json(d / "case.json")
    uploads = read_json(d / "uploads.json", {})
    images = sorted(uploads.values(), key=lambda x: x.get("uploaded_at", ""))
    state = read_json(d / "state.json", {"state": "REVIEW", "version": 0, "changelog": []})
    state["version"] = int(state.get("version", 0)) + 1
    note = body.get("note") or f"第 {state['version']} 版：{len(images)} 份材料，{findings['aggregate']['anchor_months']} 个月份"
    state.setdefault("changelog", []).insert(0, {"version": state["version"], "time": now(), "note": note})

    out = d / "reports" / f"report_v{state['version']}.html"
    report_mod.render(case, findings, images, state["version"], state["changelog"], out)
    state["state"] = "DONE"
    write_json(d / "state.json", state)
    return {"ok": True, "version": state["version"], "url": f"/reports/{cid}/report_v{state['version']}.html"}


def api_import(body):
    """从结构化 JSON 导入案件（给没有 OCR 或已有表格的用户用）。"""
    cid = body.get("case_id") or f"case_{datetime.now():%Y%m%d_%H%M%S}"
    d = case_dir(cid)
    data = body.get("case") or {}
    case = {
        "case_id": cid,
        "person": data.get("person") or {},
        "window": data.get("window") or {},
        "assumptions": data.get("assumptions") or {
            "monthly_salary_caliber": "gross_fixed",
            "si_personal_rate": 0.105,
            "hf_rate_candidates": [0.05, 0.07, 0.12],
            "rounding_tolerance": 1.0,
        },
        "identity_sources": data.get("identity_sources") or [],
    }
    write_json(d / "case.json", case)
    overrides = {}
    for m in data.get("months", []):
        month = m.get("month")
        if not month:
            continue
        for f in normalize.FIELD_DEFS:
            if m.get(f) is not None:
                overrides.setdefault(month, {})[f] = m[f]
    write_json(d / "overrides.json", overrides)
    if not (d / "state.json").exists():
        write_json(d / "state.json", {"state": "COLLECTING", "version": 0, "changelog": []})
    return {"ok": True, "case_id": cid, "months": len(overrides)}


def api_state(case_id):
    d = case_dir(case_id)
    state = read_json(d / "state.json", {"state": "COLLECTING", "version": 0, "changelog": []})
    uploads = read_json(d / "uploads.json", {})
    findings = read_json(d / "findings.json", None)
    reports = sorted([p.name for p in (d / "reports").glob("report_v*.html")]) if (d / "reports").exists() else []
    return {
        "ok": True,
        "case_id": case_id,
        "state": state,
        "uploads": list(uploads.values()),
        "findings": findings,
        "reports": reports,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        n = int(self.headers.get("Content-Length", 0))
        if not n:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            return self._send(200, (WEB / "index.html").read_text(encoding="utf-8"), "text/html; charset=utf-8")
        if u.path == "/api/state":
            q = parse_qs(u.query)
            return self._send(200, api_state(q.get("case_id", [""])[0]))
        if u.path.startswith("/reports/"):
            rel = u.path[len("/reports/"):]
            parts = [p for p in rel.split("/") if p]
            if len(parts) != 2:
                return self._send(403, {"ok": False, "error": "forbidden"})
            target = (CASES / parts[0] / "reports" / parts[1]).resolve()
            if CASES.resolve() not in target.parents or not target.exists():
                return self._send(404, {"ok": False, "error": "not found"})
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            return self._send(200, target.read_bytes(), ctype)
        return self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        routes = {
            "/api/case": api_case,
            "/api/import": api_import,
            "/api/upload": api_upload,
            "/api/manual": api_manual,
            "/api/analyze": api_analyze,
            "/api/report": api_report,
        }
        fn = routes.get(urlparse(self.path).path)
        if not fn:
            return self._send(404, {"ok": False, "error": "not found"})
        try:
            body = self._read_json()
            with LOCK:
                result = fn(body)
            return self._send(200, result)
        except Exception as e:
            return self._send(500, {"ok": False, "error": str(e)})


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"薪核工作台: http://127.0.0.1:{port}")
    print(f"OCR: {'可用' if ocr.available()[0] else ocr.available()[1]}")
    server.serve_forever()


if __name__ == "__main__":
    main()
