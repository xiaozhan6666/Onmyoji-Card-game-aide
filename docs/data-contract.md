# 阶段 1 数据约定（v1.0）

全项目使用 UTF-8、snake_case JSON 字段；Python 包名 `bwp_collector`，Java 后续使用自身 camelCase 属性并在 JSON 边界映射。数据库方案仍为 MySQL 8.4 / InnoDB。

## 三种文件

1. 样本标注：`sample.yaml`，对应 `contracts/sample.schema.json`。人工指定图片、像素框、真实时间与上下文，可另外记录标准答案。
2. 本地观察：`session.json`，由 prepare 生成，保存原图引用、哈希及稳定 capture_id。重跑识别生成独立 report，不修改原观察。
3. 上传候选：`upload_candidate.json`，对应 `contracts/batch.schema.json`。现在可作为第 3 阶段上传接口的 multipart JSON manifest；Python 离线工具仍只落盘，自动上传队列将在后续阶段实现。

## 上传候选

根字段为 `schema_version`、`scope_key`、`records`、`images`。每条 record 包含：

| 字段 | JSON 类型 | 约束 |
| --- | --- | --- |
| capture_id | string | UUID，采集端生成 UUIDv7，一次观察重试沿用 |
| shikigami_id | string | 1–4294967295 的规范十进制字符串 |
| season_key | string | 明确赛季标识，不用“当前赛季”，长度 1–64 |
| player_id | string | 保留前导零和大小写，不用昵称代替，长度 1–64 |
| grade | integer | 5、6、7、8、9=名士、10=大名士 |
| bailian_points | string | 0–9223372036854775807 的规范十进制字符串 |
| cumulative_wins | string | 同上 |
| captured_at | string | UTC 毫秒，如 `2026-10-13T12:00:00.123Z` |
| image_keys | array[string] | 本批 images 的 key，不能由客户端指定服务器路径 |

JSON Schema 验证结构及格式，精确整数上限、字符串空白、图片关联、身份与时效由应用继续校验。Java 接收时必须重复校验，不能信任采集端已通过的结论。

`images` 每项包含 `key` 与原始文件 `sha256`。上传时文件表单项名称使用 key，并从 session 中定位原始文件。后端校验内容哈希，按内容生成原图路径和稳定清单引用，再生成数据库 `source_image_ref`，客户端不上传该字段。数据库自增 `id` 由服务端生成。

同一图片可能供多条观察引用；同一观察可以引用榜单图和资料图。所有图片 key 必须存在，未使用图片不放入候选。服务器去重按照设计文档的 capture_id 与观察唯一键规则处理。

## 本地验证与可信边界

- scope、赛季、式神和资料页行关联首期通过人工标注确认，不声称已实现自动页面判断。
- `fields` 中的裁剪框从原始分辨率取得，不自动缩放套用到另一分辨率。
- 若榜单截图缺玩家 ID/段位，必须补充可靠关联的资料图；字段缺失时保持 pending。
- 一个字段框仅接受一段 OCR 文本，多个检测框不会盲目拼接；需扩大/调整框或人工检查。
- numeric 字段可规范化全角数字和合法千分位；玩家 ID 不进行字符替换。
- 精度、时间和负数边界与桌面的 MySQL 设计一致。截图时间首次落盘即截断到毫秒，重跑保留。
- OCR 输出、置信度、模型及包版本、失败原因仅在本地 report 中，不增加数据库字段。
- synthetic 或 replay 数据始终不进入上传候选。PaddleOCR 对真实截图的 ready 仍只表示格式和当前质量检查通过，不保证识别值一定正确。

## 验收状态

2026-10-13 更新：已在 MuMu 1920×1080 的书翁榜完成前十名真实观察，包含玩家 ID、当前段位与实际截图时间。`scripts/upload-live-run.py` 将完整采集报告转换为 outbox，每条一个符合本协议的 manifest，附四张原图，通过本机 Java 接口上传。十条基线已入库，原编号重传全部为 duplicate。数据库字段及 JSON 协议未变；离线工具自身仍只落盘。详见 [第 5 阶段记录](stage-5-status.md)。以下保留早期阶段记录。

已建立版本化协议、标注格式与离线工具。真实截图、布局校准、人工标准答案和游戏实测准确率仍待补齐。现阶段不能声称前两个阶段已全部验收完成。

## 第 3 阶段接口实现补充

接口、状态与批量限制见 `backend/README.md`。每条观察独立事务；出现 503/断连时重传原 capture_id，已有记录返回 duplicate。scope_key 为 ASCII 字母、数字、下划线或短横线组成的固定机器标识；JSON Schema 之外的容量、精确范围和业务约束由服务端重复校验。图片 key 保留名称 manifest 不可使用。

真实四张截图的数字试测已完成，资料 ID/段位及实际采集时间仍待补齐。后端阶段已通过隔离测试数据验收，没有将真实缺失字段补造后入库。
