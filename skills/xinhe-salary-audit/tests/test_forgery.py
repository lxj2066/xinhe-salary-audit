#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""篡改筛查自检：合成干净图与改图，验证风险分级与信号。"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from PIL import Image, ImageDraw, ImageFont
import forgery

FONT = "C:/Windows/Fonts/arial.ttf"


def make_base(path):
    im = Image.new("RGB", (900, 600), "white")
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(FONT, 26)
    lines = [
        ("2026-05 工资明细", 40, 40),
        ("应发工资 30,000.00", 60, 140),
        ("社保个人 3,150.00", 60, 210),
        ("公积金个人 3,600.00", 60, 280),
        ("实发工资 20,750.00", 60, 350),
        ("税额 2,500.00", 60, 420),
    ]
    boxes = []
    for text, x, y in lines:
        d.text((x, y), text, fill=(20, 20, 20), font=f)
        boxes.append([x - 4, y - 4, x + 420, y + 38])
    im.save(path, "JPEG", quality=95)
    return boxes


def make_tampered(src, dst, boxes):
    im = Image.open(src).convert("RGB")
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(FONT, 30)
    # 抹掉两行金额，换成浅灰底 + 蓝色字体（模拟粘贴）
    for idx, new_text in ((1, "应发工资 38,000.00"), (4, "实发工资 28,750.00")):
        x0, y0, x1, y1 = boxes[idx]
        d.rectangle([x0, y0, x1, y1], fill=(236, 236, 236))
        d.text((x0 + 4, y0 + 2), new_text, fill=(20, 40, 160), font=f)
    exif = Image.Exif()
    exif[0x0131] = "Adobe Photoshop 25.0"
    im.save(dst, "JPEG", quality=92, exif=exif)


def main():
    with tempfile.TemporaryDirectory() as td:
        clean = Path(td) / "clean.jpg"
        tampered = Path(td) / "tampered.jpg"
        boxes = make_base(str(clean))
        make_tampered(str(clean), str(tampered), boxes)
        ocr_items = [
            {"text": "2026-05 工资明细", "box": boxes[0]},
            {"text": "应发工资 38,000.00", "box": boxes[1]},
            {"text": "社保个人 3,150.00", "box": boxes[2]},
            {"text": "公积金个人 3,600.00", "box": boxes[3]},
            {"text": "实发工资 28,750.00", "box": boxes[4]},
            {"text": "税额 2,500.00", "box": boxes[5]},
        ]
        a = forgery.analyze(str(clean), ocr_items)
        b = forgery.analyze(str(tampered), ocr_items)
        print("clean   :", a["risk"], a["score"], [s["code"] for s in a["signals"]])
        print("tampered:", b["risk"], b["score"], [s["code"] for s in b["signals"]])
        ok = a["risk"] == "low" and b["risk"] in ("medium", "high") and any(
            s["code"] == "editing_software" for s in b["signals"])
        print("PASS" if ok else "FAIL")
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
