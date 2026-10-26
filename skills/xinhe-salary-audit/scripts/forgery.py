#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""薪核 · 图片篡改风险筛查（v1.0.0）

定位：**风险提示，不是司法鉴定。** 输出 low / medium / high 与证据，
供人工复核，绝不据此直接判定“造假”。

三类信号：
1. 元数据：编辑软件签名、EXIF 时间与文件时间冲突、相机信息缺失
2. ELA（Error Level Analysis）：重压缩误差在局部异常集中
3. 文字区域一致性：金额行的颜色/边缘锐度与其它文本行显著不同
"""
from __future__ import annotations

import base64
import io
import re
from pathlib import Path

EDIT_SOFTWARE = re.compile(
    r"photoshop|lightroom|snapseed|meitu|美图|picsart|gimp|pixelmator|affinity|canva|fotor|paint\.net|krita",
    re.I,
)
AMOUNT_RE = re.compile(r"(?<![\d.])(?:\d{1,3}(?:,\d{3})+|\d+\.\d{2})(?![\d.])")


def _exif_report(im, path):
    signals, info = [], {}
    try:
        exif = im.getexif()
    except Exception:
        exif = {}
    tags = {0x0131: "Software", 0x010F: "Make", 0x0110: "Model",
            0x0132: "DateTime", 0x9003: "DateTimeOriginal"}
    for tag, name in tags.items():
        try:
            v = exif.get(tag)
        except Exception:
            v = None
        if v:
            info[name] = str(v)
    sw = info.get("Software")
    if sw and EDIT_SOFTWARE.search(sw):
        signals.append({"code": "editing_software", "weight": 3,
                        "detail": f"EXIF 记录了编辑软件：{sw}"})
    if not info.get("Make") and not info.get("Model"):
        signals.append({"code": "no_camera_info", "weight": 1,
                        "detail": "没有相机厂商/型号信息（截图常见，单凭此条不足以判定）"})
    mtime = path.stat().st_mtime
    for key in ("DateTime", "DateTimeOriginal"):
        raw = info.get(key)
        if not raw:
            continue
        m = re.match(r"(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2}):(\d{2})", raw)
        if m:
            import datetime as dt
            try:
                t = dt.datetime(*map(int, m.groups())).timestamp()
                if abs(t - mtime) > 86400 * 2:
                    signals.append({"code": "exif_time_mismatch", "weight": 1,
                                    "detail": f"EXIF {key}={raw} 与文件时间相差超过 2 天"})
            except ValueError:
                pass
    return info, signals


def _ela(im, quality=90, grid=8):
    """返回 ELA 统计与热区。PNG 截图的 ELA 意义弱于 JPEG，需在结论里说明。"""
    try:
        import numpy as np
        from PIL import Image, ImageChops
    except Exception as e:
        return {"available": False, "reason": f"缺少 numpy/Pillow: {e}"}
    rgb = im.convert("RGB")
    # 控制分析尺寸
    if max(rgb.size) > 1600:
        scale = 1600 / max(rgb.size)
        rgb = rgb.resize((int(rgb.width * scale), int(rgb.height * scale)))
    buf = io.BytesIO()
    rgb.save(buf, "JPEG", quality=quality)
    buf.seek(0)
    recompressed = Image.open(buf).convert("RGB")
    diff = ImageChops.difference(rgb, recompressed)
    arr = np.asarray(diff, dtype=np.float32).mean(axis=2)
    mean, p99, mx = float(arr.mean()), float(np.percentile(arr, 99)), float(arr.max())

    h, w = arr.shape
    cells = []
    for gy in range(grid):
        for gx in range(grid):
            y0, y1 = int(h * gy / grid), int(h * (gy + 1) / grid)
            x0, x1 = int(w * gx / grid), int(w * (gx + 1) / grid)
            block = arr[y0:y1, x0:x1]
            cells.append((float(block.mean()), gx, gy, x0, y0, x1, y1))
    vals = [c[0] for c in cells]
    mu = sum(vals) / len(vals)
    sd = (sum((v - mu) ** 2 for v in vals) / len(vals)) ** 0.5
    hot = [c for c in cells if c[0] > mu + 3 * sd and c[0] > 8]
    hot_regions = [{"x": c[3], "y": c[4], "w": c[5] - c[3], "h": c[6] - c[4],
                    "score": round(c[0], 1)} for c in sorted(hot, key=lambda x: -x[0])[:5]]

    # 热力图（缩小后 base64）
    heat = np.clip(arr / (mx or 1) * 255, 0, 255).astype("uint8")
    hm = Image.fromarray(heat, mode="L").resize((320, int(320 * h / w)))
    hb = io.BytesIO()
    hm.save(hb, "PNG")
    preview = "data:image/png;base64," + base64.b64encode(hb.getvalue()).decode()

    return {
        "available": True,
        "mean": round(mean, 2),
        "p99": round(p99, 2),
        "max": round(mx, 2),
        "hot_region_count": len(hot),
        "hot_ratio": round(len(hot) / len(cells), 3),
        "hot_regions": hot_regions,
        "preview": preview,
    }


def _region_consistency(im, ocr_items):
    """金额行与其它文本行的颜色/锐度对比。"""
    try:
        import numpy as np
        from PIL import ImageFilter
    except Exception:
        return {"available": False, "reason": "缺少 numpy/Pillow"}
    if not ocr_items:
        return {"available": False, "reason": "没有 OCR 文本框，无法做区域一致性检查"}

    def stats(box):
        x0, y0, x1, y1 = [int(v) for v in box]
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(im.width, x1), min(im.height, y1)
        if x1 - x0 < 4 or y1 - y0 < 4:
            return None
        crop = im.crop((x0, y0, x1, y1)).convert("RGB")
        a = np.asarray(crop, dtype=np.float32)
        gray = a.mean(axis=2)
        dark = a[gray < np.percentile(gray, 15)]
        light = a[gray > np.percentile(gray, 85)]
        edges = np.asarray(crop.convert("L").filter(ImageFilter.FIND_EDGES), dtype=np.float32)
        return {
            "text_rgb": dark.mean(axis=0) if len(dark) else np.array([0, 0, 0]),
            "bg_rgb": light.mean(axis=0) if len(light) else np.array([255, 255, 255]),
            "edge": float(edges.var()),
        }

    rows = []
    for item in ocr_items:
        s = stats(item.get("box") or [])
        if s:
            rows.append({"text": item.get("text", ""), **s,
                         "is_amount": bool(AMOUNT_RE.search(item.get("text", "")))})
    if len(rows) < 4:
        return {"available": False, "reason": "有效文本框太少"}

    amounts = [r for r in rows if r["is_amount"]]
    others = [r for r in rows if not r["is_amount"]]
    if not amounts or not others:
        return {"available": False, "reason": "金额行或对照行不足"}

    base_edge = float(np.median([r["edge"] for r in others]))
    base_color = np.median(np.stack([r["text_rgb"] for r in others]), axis=0)
    outliers = []
    for r in amounts:
        color_d = float(np.linalg.norm(r["text_rgb"] - base_color))
        ratio = r["edge"] / base_edge if base_edge else 0
        if color_d > 60 or ratio > 2.5 or ratio < 0.4:
            outliers.append({"text": r["text"], "color_distance": round(color_d, 1),
                             "edge_ratio": round(ratio, 2)})
    return {"available": True, "amount_lines": len(amounts), "outliers": outliers}


def analyze(path, ocr_items=None):
    path = Path(path)
    try:
        from PIL import Image
        im = Image.open(path)
        im.load()
    except Exception as e:
        return {"file": str(path), "available": False, "reason": f"无法打开图片: {e}"}

    info, signals = _exif_report(im, path)
    ela = _ela(im)
    region = _region_consistency(im, ocr_items)

    if ela.get("available"):
        if ela["max"] > 60 and ela["hot_ratio"] > 0.03:
            signals.append({"code": "ela_hotspots", "weight": 2,
                            "detail": f"ELA 热区 {ela['hot_region_count']} 个，最大误差 {ela['max']}"})
        elif ela["max"] > 40:
            signals.append({"code": "ela_elevated", "weight": 1,
                            "detail": f"ELA 误差偏高（max {ela['max']}），需结合原图判断"})

    if region.get("available") and len(region["outliers"]) >= 2:
        signals.append({"code": "amount_region_outlier", "weight": 2,
                        "detail": "有 " + str(len(region["outliers"])) + " 行金额的文字颜色/锐度与其它文本明显不同"})

    score = sum(s["weight"] for s in signals)
    groups = len({s["code"] for s in signals})
    if score >= 4 and groups >= 2:
        risk = "high"
    elif score >= 2:
        risk = "medium"
    else:
        risk = "low"

    caveats = [
        "ELA 对 PNG 截图和二次压缩图片的敏感度有限，不能作为造假证据。",
        "社交软件转发、截图工具、压缩都会改变像素统计。",
        "结论只用于提示人工复核；不构成鉴定意见。",
    ]
    if im.format == "PNG":
        caveats.append("该文件是 PNG 截图，元数据与 ELA 的参考价值低于原始 JPEG。")

    return {
        "file": str(path),
        "available": True,
        "format": im.format,
        "size": list(im.size),
        "exif": info,
        "risk": risk,
        "score": score,
        "signals": signals,
        "ela": {k: v for k, v in ela.items() if k != "preview"},
        "ela_preview": ela.get("preview") if ela.get("available") else None,
        "region": region,
        "caveats": caveats,
    }
