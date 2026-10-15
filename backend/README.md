# Java 后端：MySQL 入库与样本统计

2026-10-13：已应用 Flyway V3，式神表新增 `sample_games BIGINT UNSIGNED` 存储生成列，自动等于 `sample_wins + sample_losses`。仍为两张业务表，分别 9 / 10 个字段；原始段位保留。口径与登场率后续设计见 [段位及场数设计](../docs/grade-focus-and-game-counts.md)。

已实现 Java 21、Spring Boot 4.0.8、MyBatis Starter 4.0.0、Flyway 和 MySQL 8.4.11。当前提供采集上传、计分规则、赛季折算、相邻区间推算和式神统计。配置与计算边界见 [第 4 阶段记录](../docs/stage-4-status.md)；管理页面尚未实现。

## 本机启动

在项目根目录的 PowerShell 中执行（脚本只使用项目专用实例）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-local-mysql.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/backend.ps1 test
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-backend.ps1
```

- MySQL：`127.0.0.1:33307`，开发库 `bwp_aide`，测试库 `bwp_stage3_test_local`。
- Java：`http://127.0.0.1:18080`，后台运行，Java 堆配置为 64–256 MiB。
- 凭据：项目 `data/backend-local/connection.json`，已被 `.gitignore` 排除。不要提交或公开这个文件。
- 日志：`data/backend-local/backend.log`、`backend-error.log`、`mysql.log`。
- Java/MySQL 工具链位于 `.cache/toolchains/`，没有替换本机原有 Java 8/MySQL 8.0；下载来源和 SHA-256 保存在该目录的 `downloads.json`。
- 修改后重新打包：`powershell -File scripts/backend.ps1 package`。正在运行的 JAR 不会自动更新，需停止后重启。
- 停止两个项目进程：`powershell -File scripts/stop-local-services.ps1`。它先核对 PID 与命令路径，不停止其他 Java/MySQL 服务，数据库文件保留。

这些辅助脚本用于本机开发，固定范围标识为 `local-development`，当前用途为用户确认的单服百炼榜、S56。该标识不代表另一个游戏区服；今后切换其他模式或范围时须用独立数据库或明确迁移。Flyway 将范围写入两张表的 COMMENT，启动时核对，避免修改配置后混入其他范围。

## 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 服务进程就绪信息 |
| GET | `/api/shikigami` | 式神目录；编号、计数和胜率使用字符串，零样本胜率为 null |
| GET | `/api/rankings` | 默认窗口的样本推算榜，附规则版本、状态和排除原因 |
| GET | `/api/shikigami/{id}/statistics` | 单式神统计，不存在返回 404 |
| POST | `/api/collector/batches` | Bearer 令牌认证的 multipart 上传 |

式神目录初始包含已提供截图中的璇、追月神、书翁，内部 ID 分别为 1、2、3。这些是本项目编号，不是游戏官方 ID。迁移不插入玩家战绩，也不提供未经计算的胜率。

上传表单包含一个 `manifest` 项（`application/json`），内容与根目录 `contracts/batch.schema.json` 对应；其余文件项名与 manifest 的 images.key 一致。详情见 `docs/data-contract.md`。服务端独立校验所有字段，不依赖采集器声称已通过校验。

接口限制：每批 1–100 条记录、1–8 张图片；每张最多 8 MiB、2000 万像素；请求最多 40 MiB；manifest 最多 256 KiB。只接收可解码的 PNG/JPEG。scope_key 使用 1–64 位 ASCII 字母、数字、下划线或短横线。图片 key 不得使用保留名称 `manifest`。

示例响应：

```json
{"schema_version":"1.0","results":[{"capture_id":"019a0000-0000-7000-8000-000000000001","status":"saved","id":"1","reason":null,"record_index":0}]}
```

| 状态 | 含义与采集端处理 |
| --- | --- |
| saved | 单条事务已提交，可以确认该条已保存 |
| duplicate | 与现存观察内容一致，返回现有 id 和 stored_capture_id，可以确认已保存 |
| invalid | 必填项、类型、范围、段位或关联不合法，留在待处理文件 |
| conflict | 采集编号/观察唯一键已存在，但数据或图片内容不同，不能覆盖，需人工核对 |

范围/协议错误、缺图或图片哈希错误返回 HTTP 400；认证失败返回 401；超过请求限制返回 413；基础设施错误返回 503。逐条业务校验结果包含在 HTTP 200 的 results 中，**不能只看 HTTP 200 就删除整批待上传文件**。

每条记录独立事务，已提交的记录不会因批次后续某条失败而撤销。若中途发生 503 或连接断开，客户端保留原 capture_id 重传整批；已经提交的记录返回 duplicate。并发去重由数据库两个唯一索引保证，不用 INSERT IGNORE 或覆盖写入。

图片按 SHA-256 保存，清单按内容集合生成稳定引用。客户端原文件名不参与服务器路径；换文件名/表单 key 后重传同一图片不会导致误冲突。图片先落盘再提交数据库，避免出现已保存快照却缺原图的情况。数据库失败可能留下未引用文件；本阶段保留它们，后续通过引用审计清理，不在失败时盲目删除可能被并发请求共用的文件。数据库、图片目录和规则配置需一起备份。

## 运行配置与测试

非本机辅助脚本部署时，通过环境变量设置：

```text
BWP_DB_URL=jdbc:mysql://HOST:PORT/DATABASE?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true
BWP_DB_USER=...
BWP_DB_PASSWORD=...
BWP_SCOPE_KEY=...
BWP_COLLECTOR_TOKEN=至少32字符的随机令牌
BWP_STORAGE_ROOT=原图保存目录
BWP_BIND_ADDRESS=127.0.0.1
BWP_PORT=8080
```

本机专用实例的连接关闭 TLS，仅监听回环地址；远程部署应配置数据库 TLS、站点 HTTPS 和独立权限。当前采集令牌不授予管理权限，其他接口默认拒绝访问。管理员登录尚未实现，不提供默认管理员账号。

标准 Java 21 + Maven 3.9 环境可执行 `mvn -B -ntp verify`；未提供外部测试库时，Testcontainers 启动 `mysql:8.4.11`（需 Docker）。本机 Docker 未运行，已使用原生 MySQL 8.4.11 的隔离测试库执行相同测试。外部测试库通过 `BWP_TEST_DB_URL/USER/PASSWORD` 提供，库名必须匹配 `bwp_stage3_test_*`，测试会清理该测试库中的快照；不要指向真实数据。

当前 39 项单元测试与 26 项真实 MySQL 集成测试全部通过，共 65 项。S56 观察配置与段位统计见 [S56 补充](../docs/s56-observation.md)。覆盖算法与折算边界、窗口和异常记录阻断、迁移字段数量、UTC 往返、UUID 二进制转换、前导零、严格数字类型、生成列精度、唯一键、图片校验、认证、文件竞争、并发重传和快照/统计共同回滚。已有四张游戏截图仍缺 ID/段位/实际时间，没有填假值上传。

## 技术依据

- [Spring Boot 系统要求](https://docs.spring.io/spring-boot/system-requirements.html)
- [MyBatis Starter 兼容矩阵](https://mybatis.org/spring-boot-starter/mybatis-spring-boot-autoconfigure/)
- [Flyway MySQL 模块](https://documentation.red-gate.com/flyway/reference/database-driver-reference/mysql)
