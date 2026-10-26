#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""薪核 · HTML 报告渲染（v1.0.0）。数字全部来自 findings，不经过模型。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATE_DIR = Path(__file__).parent / "templates"


def render(case, findings, images=None, version=1, changelog=None, out_path=None):
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    tpl = env.get_template("report.html.j2")
    html = tpl.render(
        case=case,
        findings=findings,
        images=images or [],
        version=version,
        changelog=changelog or [],
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    if out_path:
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(html, encoding="utf-8")
    return html


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("findings")
    ap.add_argument("--images", default=None)
    ap.add_argument("--version", type=int, default=1)
    ap.add_argument("--changelog", default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    case = json.loads(Path(a.case).read_text(encoding="utf-8-sig"))
    findings = json.loads(Path(a.findings).read_text(encoding="utf-8-sig"))
    images = json.loads(Path(a.images).read_text(encoding="utf-8-sig")) if a.images else []
    changelog = json.loads(Path(a.changelog).read_text(encoding="utf-8-sig")) if a.changelog else []
    render(case, findings, images, a.version, changelog, a.out)
    print(a.out)


if __name__ == "__main__":
    main()
