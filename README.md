# 百闻牌助手

**前端首版已可使用：** 本地访问 `http://127.0.0.1:5173/`，包含总览、式神图鉴、分段位详情和采集概览。运行方式见 [frontend/README.md](frontend/README.md)，交付与验证见 [前端阶段记录](docs/stage-6-frontend.md)。2026-10-13 已完成式神录名称顺序前 50 个式神各前五名的第二轮观察，本轮新增 250 条，网站累计 530 条观察、16 个式神有有效胜率样本；详见 [本轮刷新结果](docs/first50-refresh-20261013.md)。第一轮前两个式神原先保存的各十条继续保留，历史基线见 [首轮说明](docs/first50-capture.md)。

已实现第 1、2 阶段离线采集、第 3 阶段 Java/MySQL 入库，以及第 4 阶段计分、赛季折算和区间样本统计。运行方式见 [backend/README.md](backend/README.md)，统计配置、接口与边界见 [第 4 阶段记录](docs/stage-4-status.md)。已按用户确认的 S56 单服百炼榜启用观察推算，新增六个段位汇总，详见 [S56 补充](docs/s56-observation.md)。第 5 阶段已跑通 MuMu 书翁榜前十名滚动采集、头像资料识别与 Java/MySQL 上传，十条真实观察基线已保存，重传去重验证通过。首轮没有有效胜负区间，胜率保持为空。循环调度仍待实现；前端首版已完成，采集流程详见 [实机采集及上传说明](docs/stage-5-status.md)。

**已用用户提供的 4 张真实榜单截图完成数字识别试测：榜单 40/40 个字段、底部自身记录 8/8 个字段正确。** 其中一页有两个分辨率版本；本次图片同时用于裁剪校准，不代表独立验收准确率。详见 `data/screenshots-test/run-20261013-122442/测试结果.md`。玩家 ID、段位和采集时间仍待补齐，默认配置不生成上传候选。`data/demo-input` 中的图片仍为合成测试素材。

## 本机运行

项目已创建独立 `.venv`。在项目根目录打开 PowerShell：

```powershell
.\.venv\Scripts\python.exe -m bwp_collector --help
.\.venv\Scripts\python.exe -m pytest -q
```

换电脑安装时使用 Python 3.12，创建虚拟环境并安装已验证依赖：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
```

首次运行 PaddleOCR 会下载公开模型到项目 `.cache/paddlex`。推理在本地进行，截图不会上传给模型服务。可以在 `config/ocr.yaml` 中指定已下载模型目录；断网运行前要完成首次下载。PaddleOCR 适配器按[官方 3.x Python 接口](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html)实现。

## 第一步：准备一份真实标注

1. 将原始百炼榜截图保存在 `data/screenshots/`，保持游戏原分辨率，不经聊天软件压缩。
2. 保存实际截图时间、式神、区服/模式/榜单范围和赛季。不要用文件修改时间猜截图时间。
3. 如果榜单不显示玩家 ID 和段位，同时准备能可靠关联到该榜单行的资料页截图。昵称不能代替玩家 ID。
4. 复制 `examples/sample.template.yaml` 到 `data/my-sample.yaml`，填入图片路径（相对 YAML 文件）、原图尺寸和带时区的截图时间。
5. 生成坐标网格，按原图像素填写每一行的字段框 `[left, top, right, bottom]`。右、下边界不包含在裁剪中。

```powershell
.\.venv\Scripts\python.exe -m bwp_collector inspect data/screenshots/board.png --output data/board-grid.png
```

每个框只包含一个完整字段，不包含标签或上下行内容。`fields` 只记录位置；`expected` 保存人工逐字核对的标准答案，识别程序不会读取标准答案。`shikigami_id` 是我们自己的式神目录编号，不是 OCR 猜出来的编号。

`context_confirmed` 表示人工已核对式神、范围和赛季；每行 `identity_confirmed` 表示资料页与榜单行关联已确认。未知项保持空缺/false，不能为了生成候选而填假值。配置中的 `calibrated` 仅在真实截图校准后设为 true。

```powershell
.\.venv\Scripts\python.exe -m bwp_collector prepare data/my-sample.yaml --output data/observations/sample-001
.\.venv\Scripts\python.exe -m bwp_collector recognize data/observations/sample-001 --config config/ocr.yaml
```

`prepare` 保存原图、SHA-256 和 UUIDv7。之后重跑识别直接用同一个观察目录，不能重新 prepare 替换已生成的观察编号；已有目录会被拒绝覆盖。

每次 `recognize` 都创建独立的 `runs/<run_id>/`：

- `report.json`：每行解析值、置信度、原文、裁剪来源、模型名称及包版本、失败原因。
- `crops/`：原始裁剪和预处理后的图片。
- `*.regions.png`：标出字段区域的核对图。
- `upload_candidate.json`：仅在有合格的真实观察时生成。当前阶段只落盘，没有网络上传功能。

缺失字段、低置信度、多段文字、未知段位、重复玩家、过期资料页以及不确定关联都进入 `pending`。积分和胜场必须来自同一截图。数字不自动替换 O/0、I/1，不接受“1.8万”这类近似值。

## 第二步：测量识别效果

将实际运行输出的 `report.json` 路径代入：

```powershell
.\.venv\Scripts\python.exe -m bwp_collector evaluate data/observations/sample-001/runs/<run_id>/report.json --labels data/my-sample.yaml --output data/evaluation-001.json
```

评估分别统计玩家 ID、段位、百炼值、累计胜场的完全一致率，以及四字段全部正确的整行率。缺失识别结果计为错误；未标注字段不计分母。报告列出每一个错项，方便回查对应裁剪图。

目前置信度 0.95、资料页时间差 30 秒是试验参数，不是已经验证的游戏规则或验收标准。建议先用至少 30 张不同页、覆盖至少 200 行的真实截图建立标注集，再约定关键字段与整行准确率门槛；调参截图和验收截图分开。样本不足时只报告测量结果，不宣布阶段验收通过。

## 不需要游戏即可运行的演示

下面命令供新环境使用；本机已有 `data/demo-input` 和 `data/demo-session`，可以直接重跑 recognize。

```powershell
.\.venv\Scripts\python.exe scripts/make_demo.py
.\.venv\Scripts\python.exe -m bwp_collector prepare data/demo-input/sample.yaml --output data/demo-session
.\.venv\Scripts\python.exe -m bwp_collector recognize data/demo-session --engine replay --replay data/demo-input/replay.json
.\.venv\Scripts\python.exe -m bwp_collector recognize data/demo-session --engine paddle
```

`replay` 用固定 OCR 输出测试解析；`paddle` 真正运行模型。两种演示都标记为 synthetic，不生成上传候选，也不证明真实游戏识别准确率。

## 目录与协议

```text
collector/src/bwp_collector/  命令行、裁剪、OCR 适配、解析和本地结果
collector/tests/              边界和集成测试
config/                      OCR 参数及用户提供的计分规则
contracts/                   导出的 JSON Schema
examples/                    真实样本标注模板
docs/                        数据协议与阶段进度
scripts/                     合成测试图生成工具
data/                        本机原图和运行结果（不提交版本库）
.cache/                      OCR 模型（不提交版本库）
```

协议变更先修改 `collector/src/bwp_collector/contracts.py`，再执行 `python -m bwp_collector schemas --output contracts` 导出。后续 Java 服务按相同版本验收数据，详见 `docs/data-contract.md`。
