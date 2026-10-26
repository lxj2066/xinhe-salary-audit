# OCR 与验图（ocr-and-forgery）

## 1. OCR 引擎：ppocr-lite

- 安装：`pip install ppocr-lite`（CPU 版；约 100MB 依赖）
- 依赖：`numpy`、`Pillow`、`onnxruntime`，不拉 OpenCV
- 模型：首次运行自动下载 PP-OCRv5 mobile 到 `~/.cache/ppocr_lite/`，之后离线
- 用法：

```python
from ppocr_lite import PPOCRLite
engine = PPOCRLite()
for r in engine.run("screenshot.png"):
    print(r.score, r.text, r.box)
```

- 本技能的适配层：`scripts/ocr.py`
  - 按文件 SHA-256 缓存到 `~/.cache/xinhe-salary-audit/ocr/`
  - 未安装时返回 `available=false`，工作台标记“待手动录入”，**不阻塞主流程**

## 2. PDF 路由

| 类型 | 处理 |
|---|---|
| 有文本层 | `pypdf` 直接抽文本（快、准） |
| 扫描件 / 截图 | ppocr-lite |
| 表格密集（工资明细表） | 建议 PP-StructureV3，保留行列 |

PP-StructureV3 参考命令：

```bash
paddleocr api --model_type doc_parsing --model PP-StructureV3 --file_path payslip.pdf
```

输出含 `markdownText`、表格 HTML、`cell_bbox`、逐页置信度。
低置信度单元格（<0.8）必须人工复核，不要直接入账。

## 3. 字段映射

只认“标签 + 金额”同一行，例如：

- `应发工资 30,000.00` → `gross_income`
- `实发工资 20,750.00` → `net_pay`
- `社保个人 3,150.00` → `si_personal`
- `公积金个人 3,600.00` → `hf_personal`
- `税额 2,500.00` → `tax_paid`
- 月份：`2026-05` / `2026年5月` / `2026/5`

**没有标签的孤立数字不入账**，宁可让用户手填。

## 4. 验图（forgery.py）

三层信号：

| 层 | 看什么 | 权重 |
|---|---|---|
| 元数据 | EXIF 里的编辑软件（Photoshop/美图/Snapseed…）、EXIF 时间与文件时间冲突、相机信息缺失 | 3 / 1 / 1 |
| ELA | 重压缩误差的局部集中（hot region） | 2 |
| 区域一致性 | 金额行的文字颜色/边缘锐度与其它文本行显著不同 | 2 |

分级：

- `score ≥ 4` 且至少 2 类独立信号 → `high`
- `score ≥ 2` → `medium`
- 其余 → `low`

## 5. 验图的边界（必须写进结论）

- ELA 对 **PNG 截图**、二次压缩、社交软件转发的敏感度有限。
- 截图工具、压缩、缩放都会改变像素统计。
- 不能据此判定“造假”，只能提示“需人工复核”。
- 真正强的信号是**跨来源不一致**：个税、银行、社保、公积金互相矛盾，比像素更可靠。

## 6. 可选：AI 视觉复核

Agent 可以用视觉模型看原图，描述“数字区域是否有拼接痕迹、字体是否一致、背景是否有涂抹”。
输出必须标为“AI 观察，非鉴定”，并且不能单独作为拒绝依据。

## 7. 隐私

薪资材料含身份证号、银行卡号、住址。工作台只监听 `127.0.0.1`，默认不上传云端；
如使用在线视觉模型，先脱敏（遮住证件号、卡号）并取得用户同意。
