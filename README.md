# 飞书任务提醒

> 用一个轻量网页管理任务时间线，在任务开始、临近截止和每天固定时间，自动把提醒推送到飞书。

这是一个面向个人的任务提醒工具：后端使用 Python + FastAPI + SQLite，前端是原生 HTML/CSS/JavaScript。不需要注册账号，配置一个飞书机器人 Webhook 就能开始使用，适合个人或小团队内网部署。

## 目录

- [功能特点](#功能特点)
- [快速开始](#快速开始)
- [三步开始使用](#三步开始使用)
- [提醒规则](#提醒规则)
- [配置说明](#配置说明)
- [Docker 部署](#docker-部署)
- [数据与可靠性](#数据与可靠性)
- [运行测试](#运行测试)
- [项目结构](#项目结构)
- [API 速览](#api-速览)
- [安全建议](#安全建议)
- [常见问题](#常见问题)

## 功能特点

| 能力 | 说明 |
| --- | --- |
| 任务管理 | 新建、编辑、删除任务；支持标题、备注、开始时间与可选截止时间 |
| 时间模式 | 开始/截止时间均可选择「具体时间」或「全天」 |
| 三类提醒 | 开始提醒、截止前 N 分钟提醒、每日固定时间提醒 |
| 飞书推送 | 配置机器人 Webhook 后自动发送纯文本消息，支持一键测试连通性 |
| 双视图 | 「任务管理」工作台与「时间线」总览页面（`/tasks`） |
| 本地存储 | SQLite 自动建表、自动兼容旧版数据库，无需手工迁移 |
| 时区一致 | 后端存储、提醒计算与前端展示统一使用北京时间 |

## 快速开始

### 环境要求

- Python 3.11 或更高版本（Docker 镜像基于 3.11）
- 可选：Docker / Docker Compose
- 可选：飞书群自定义机器人 Webhook（仅在需要推送时配置）

### 本地运行

```bash
git clone https://github.com/Qianxia666/todo-reminder.git
cd todo-reminder

python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

启动后访问：

- 任务管理：<http://127.0.0.1:8000>
- 任务时间线：<http://127.0.0.1:8000/tasks>
- API 文档：<http://127.0.0.1:8000/docs>

> 建议始终使用 `python -m uvicorn` 启动，确保运行时依赖来自当前虚拟环境。

### Docker 运行

```bash
docker build -t todo-reminder .
docker run -d --name todo-reminder \
  -p 127.0.0.1:8000:8000 \
  -v todo_data:/app/app/data \
  todo-reminder
```

或者直接使用 Compose：

```bash
docker compose up -d --build
```

SQLite 数据保存在 Docker 卷 `todo_data` 中，容器重建后任务不会丢失。默认只绑定本机回环地址 `127.0.0.1`，避免无鉴权接口暴露到局域网或公网。

## 三步开始使用

1. **新建任务**：打开首页，填写任务标题与开始时间，按需补充备注、截止时间和每日提醒。
2. **配置飞书**：在「提醒设置」中填入机器人 Webhook，设置提前提醒分钟数与每日提醒时间，点击「测试推送」确认连通。
3. **等待提醒**：后台每 30 秒检查一次任务，满足条件时自动推送；页面顶部会展示通知配置状态。

### 获取飞书 Webhook

1. 在飞书群聊中打开「群设置」→「群机器人」→「添加机器人」→「自定义机器人」。
2. 复制生成的 Webhook 地址，形如 `https://open.feishu.cn/open-apis/bot/v2/hook/...`。
3. 粘贴到页面「提醒设置」并保存即可。

> Webhook 留空会暂停所有飞书推送，适合先本地体验任务管理功能。

## 提醒规则

| 提醒类型 | 触发时机 | 触发次数 |
| --- | --- | --- |
| 开始提醒 | 到达任务开始时间之后 | 每个任务 1 次 |
| 截止提醒 | 截止时间前 N 分钟（默认 30 分钟） | 每个任务 1 次 |
| 每日提醒 | 任务有效期内，每天到达设定时间之后 | 每天 1 次 |

几个细节：

- 所有时间均按北京时间（`Asia/Shanghai`）计算和展示。
- 时间精度为分钟；例如截止时间为 17:00，worker 在 17:00:30 轮询仍会正常提醒。
- 每日提醒从任务开始后生效，超过截止时间后不再发送。
- 修改开始或截止时间会重置对应的已发送状态，让新的时间点可以再次提醒；任一时间变化也会重置每日提醒。
- 推送失败会自动释放本次认领，并在后续轮询中重试。
- 每日提醒每成功发送一次当天不再重复；改期后旧日程不会产生重复推送。

## 配置说明

### 页面内设置

| 配置项 | 说明 | 默认值 |
| --- | --- | --- |
| 飞书 Webhook | 飞书自定义机器人地址；留空则暂停推送 | 空 |
| 提前提醒 | 截止前多少分钟发送提醒，范围 1–10080 | `30` |
| 每日时间 | 每日提醒的发送时间，24 小时制 `HH:MM` | `09:00` |

### 环境变量

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `TODO_DB_PATH` | 自定义 SQLite 文件路径（相对路径按项目根目录解析） | `app/data/reminder.db` |
| `TODO_SQLITE_TIMEOUT_SECONDS` | SQLite 连接超时（秒） | `30` |
| `TODO_SQLITE_BUSY_TIMEOUT_MS` | SQLite 忙等待时间（毫秒） | `30000` |
| `TODO_WEBHOOK_TIMEOUT_SECONDS` | 飞书 Webhook 请求超时（秒） | `5` |
| `TODO_NOTIFICATION_CLAIM_TTL_SECONDS` | 提醒认领有效期（秒），不会短于 Webhook 超时 + 5 秒 | `90` |
| `TODO_ALLOWED_WEBHOOK_HOSTS` | 额外允许的 HTTPS Webhook 域名，逗号分隔；默认已允许 `open.feishu.cn` 与 `open.larksuite.com` | 空 |
| `TODO_ALLOW_INSECURE_WEBHOOK_HTTP` | 设为 `1`/`true` 允许 HTTP Webhook，仅限可信网络 | 关闭 |

Webhook 默认只接受 HTTPS 且域名必须在允许列表内，飞书/Lark 官方域名还要求路径为 `/open-apis/bot/v2/hook/...`。如果使用自建兼容代理，请通过 `TODO_ALLOWED_WEBHOOK_HOSTS` 显式加入域名。

## Docker 部署

仓库自带 `Dockerfile` 与 `docker-compose.yml`：

- 容器内时区固定为 `Asia/Shanghai`。
- 数据目录 `/app/app/data` 挂载到命名卷 `todo_data`。
- 端口映射为 `127.0.0.1:8000`，如需局域网访问可自行调整，但请先阅读[安全建议](#安全建议)。
- 容器重启策略为 `unless-stopped`。

## 数据与可靠性

- 默认数据库为 `app/data/reminder.db`，服务启动时自动建表并初始化后台提醒线程。
- SQLite 启用 `WAL` 与 `busy_timeout`，降低 API 请求与后台提醒并发写入时的锁冲突。
- 启动时自动兼容旧版数据库：先补齐新增列，再创建依赖这些列的索引，无需手工迁移。
- 提醒发送前会先写入数据库认领记录，多线程、多进程或重复启动 worker 时不会重复推送同一条提醒。
- 任务时间变化时，会在同一个 SQLite 事务中更新任务并清理旧认领，减少改期与后台 worker 并发造成的重复推送。
- 每日提醒认领绑定当前任务时间快照，改期后旧日程产生的 worker 不会继续完成新的每日提醒。

## 运行测试

安装开发依赖后运行完整回归测试：

```bash
pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python -m compileall -q app tests
```

测试覆盖任务 API 增删改查与部分更新、数据库提醒认领与迁移、提醒时间边界、Webhook 安全策略等。

## 项目结构

```text
app/
  main.py             # FastAPI 入口、路由与中间件
  database.py         # SQLite 访问、建表迁移与提醒认领
  models.py           # Pydantic 数据模型与校验
  reminder.py         # 后台提醒线程与飞书推送
  webhook_security.py # Webhook URL 安全策略
  timezone.py         # 北京时间工具
static/
  index.html          # 任务管理页面
  tasks.html          # 时间线页面
  app.js              # 任务管理页面逻辑
  tasks.js            # 时间线页面逻辑
  styles.css          # 页面样式
tests/                # API、数据库与提醒服务回归测试
```

## API 速览

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/tasks` | 获取全部任务 |
| `POST` | `/api/tasks` | 新建任务 |
| `PUT` | `/api/tasks/{id}` | 更新任务（支持部分字段） |
| `DELETE` | `/api/tasks/{id}` | 删除任务 |
| `GET` | `/api/settings` | 读取提醒设置 |
| `POST` | `/api/settings` | 保存提醒设置 |
| `POST` | `/api/settings/test` | 发送 Webhook 测试消息 |

完整的请求/响应结构可在 `/docs` 中查看。

## 安全建议

- 项目默认没有内置登录鉴权，适合个人或内网使用；快速启动与 Compose 默认只监听本机。
- 若要暴露到局域网或公网，请放在带身份认证、TLS 和访问控制的反向代理之后。
- 飞书 Webhook 属于敏感凭据，请避免写入代码仓库、日志或公开截图。
- API 响应已设置 `Cache-Control: no-store`，减少浏览器或代理缓存敏感设置的风险。
- 页面响应附带 `X-Content-Type-Options`、`X-Frame-Options`、`Referrer-Policy` 等安全头。

## 常见问题

**没有收到提醒？**
确认 Webhook 地址正确、已点击「测试推送」并成功，且部署环境可以访问飞书。任务时间到了之后仍需等待下一轮轮询（约 30 秒）。

**Webhook 返回 200 但飞书里没有消息？**
工具会检查飞书返回体中的业务状态码，失败原因会写入服务日志。请查看日志中的 `business failure` 或 `Failed to send` 记录。

**时间显示不一致？**
后端、前端与提醒计算统一使用北京时间，请以此为准；服务器本身时区不会影响任务时间。

**端口被占用？**
换一个端口启动，例如 `python -m uvicorn app.main:app --port 8001`。

**旧数据需要迁移吗？**
不需要。服务启动时会自动补齐缺失的列和索引，并在数据库版本过新时给出明确错误。

## 技术栈

Python 3.11 · FastAPI · Pydantic · SQLite · 原生 HTML / CSS / JavaScript · Docker
