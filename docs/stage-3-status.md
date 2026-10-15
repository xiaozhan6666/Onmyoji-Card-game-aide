# 第 3 阶段交付记录

日期：2026-10-13。

## 已完成

- Java 21 + Spring Boot 4.0.8 + MyBatis 4.0.0 工程，打包为可执行 JAR。
- MySQL 8.4.11 + InnoDB；Flyway 创建式神表 8 字段、采集快照表 10 字段及约束。Flyway 另有自身历史表。
- 初始目录为璇、追月神、书翁，项目 ID 分别为 1、2、3，不插入玩家战绩。
- multipart 上传接口 `/api/collector/batches`：令牌认证、JSON 校验、图片格式/尺寸/哈希校验、文件保存与逐条事务。
- 同 capture_id 重传、不同 capture_id 命中同一观察、并发请求均通过数据库唯一约束去重。业务字段或图片内容不一致返回 conflict，不覆盖已有观察。
- 图片与清单按内容哈希保存，客户端文件名不决定服务器路径。数据库提交失败时不会返回 saved。
- UTC 毫秒时间、16 字节 UUID、保留玩家 ID 前导零、Java Long 边界、六位精度生成列和零样本 null。
- 公开健康接口、式神目录查询；其他未实现接口默认拒绝访问。
- 本机 Java/MySQL 使用项目独立工具链和独立端口，不改动原有系统安装。

## 验证证据

运行 `scripts/backend.ps1 test`：3 项单元测试 + 19 项真实 MySQL 集成测试，共 22 项通过、0 失败、0 跳过。

测试包括：正常保存、UUID/UTC 往返、前导零、缺少字段、非法段位、错误数字类型、溢出、缺图、图片损坏或哈希不符、范围不符、认证、逐条混合结果、两种唯一键交叉冲突、同 ID 和不同 ID 并发去重、外键保护、CHECK、胜率生成列精度、故意数据库错误后的事务回滚及重试。

Maven 报告：

- `backend/target/surefire-reports/cn.baiwen.aide.ingestion.PayloadValidatorTest.txt`
- `backend/target/failsafe-reports/cn.baiwen.aide.BackendIT.txt`

本机 Docker 引擎未启动，集成测试已使用隔离的原生 MySQL 8.4.11，未使用 H2 代替。Testcontainers 启动路径已配置，当前机器没有执行该容器路径。

打包后服务启动检查：`GET /api/health` 返回 ok；`GET /api/shikigami` 返回 3 个目录项，样本胜负均为 0、胜率为 null。

## 本地运行

Java 服务：`http://127.0.0.1:18080`；MySQL：`127.0.0.1:33307`。

启动、停止、凭据位置、HTTP 协议和限制见 `backend/README.md`。当前进程是本次手动启动，尚未设置开机自启。

## 下一阶段

第 4 阶段实现计分配置、赛季折算、相邻区间推算及式神汇总。当前数据库生成列只是根据已经写入的汇总胜负场生成比例，不代表已经完成区间胜率算法。

点击头像读取 ID/段位、自动翻页和循环采集仍属于第 5、6 阶段；现有 Python 工具仍以离线落盘为主，没有自动上传队列。四张真实截图没有被填入虚构身份或时间后上传。
