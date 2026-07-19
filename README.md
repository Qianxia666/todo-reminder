# 飞书任务提醒工具

该项目提供一个基于 Python + FastAPI 的任务提醒网页，帮助你维护多个任务的开始时间、截止时间与每日提醒，并通过飞书机器人推送通知。

## 功能概览
- 任务信息：支持标题、备注、开始时间、可选截止时间。
- 时间模式：开始和截止时间都支持“精确到分钟”或“全天任务”。
- 提醒策略：支持开始提醒、截止前若干分钟提醒、每日固定时间提醒。
- 飞书通知：配置机器人 Webhook 后自动发送纯文本消息。
- 前端页面：支持任务新增、编辑、删除与提醒配置。

## 快速开始
1. 创建虚拟环境并安装依赖：
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. 启动服务：
   ```bash
   python -m uvicorn app.main:app --reload
   ```
3. 浏览器访问 `http://127.0.0.1:8000`。

> 建议始终使用 `python -m uvicorn`（或虚拟环境中的解释器）启动，这样能确保运行时依赖与当前 Python 环境一致。

## 运行测试
安装包含测试工具的开发依赖后，运行完整回归测试：
```bash
pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python -m compileall -q app tests
```

## 飞书机器人配置
1. 在飞书群聊或单聊中创建自定义机器人，获取 Webhook 地址。
2. 在页面“提醒设置”中填入 Webhook 并保存。
3. 按需设置“截止前提醒分钟数”和“每日提醒时间”。

## 数据存储
- 默认数据库为 SQLite，文件位于 `app/data/reminder.db`。
- 服务启动时会自动建表，并初始化后台提醒线程。
- SQLite 已启用 `WAL` 和 `busy_timeout`，以降低 API 请求与后台提醒并发写入时的锁冲突概率。

## 并发与提醒行为
- 提醒发送前会先写入数据库认领记录，避免多线程、多进程或重复启动 worker 时重复推送同一提醒。
- 任务时间或每日提醒配置发生变化后，会自动重置对应提醒状态，避免旧状态阻塞新提醒。
- 每日提醒只会在同一天成功发送一次；如果发送失败，会自动释放认领并在后续轮询中重试。

## 可选环境变量
- `TODO_DB_PATH`：自定义 SQLite 文件路径。
- `TODO_SQLITE_TIMEOUT_SECONDS`：SQLite 连接超时时间，默认 `30`。
- `TODO_SQLITE_BUSY_TIMEOUT_MS`：SQLite 忙等待时间，默认 `30000`。
- `TODO_WEBHOOK_TIMEOUT_SECONDS`：飞书 Webhook 请求超时，默认 `5`。
- `TODO_NOTIFICATION_CLAIM_TTL_SECONDS`：提醒认领有效期，默认 `90`，且不会短于 Webhook 超时加 5 秒。

## 目录结构
```text
app/
  main.py          # FastAPI 入口与 API 定义
  database.py      # SQLite 访问与提醒认领逻辑
  models.py        # Pydantic 数据模型与校验
  reminder.py      # 后台提醒线程与飞书推送
  timezone.py      # 北京时间工具
static/
  index.html       # 主页面
  tasks.html       # 时间线页面
  app.js           # 主页面逻辑
  tasks.js         # 时间线页面逻辑
  styles.css       # 样式
tests/             # API、数据库与提醒服务回归测试
```

## 时区说明
- 后端存储与提醒计算统一转换为北京时间（`Asia/Shanghai`）。
- 前端展示与表单输入也按北京时间渲染，保证多客户端访问时的一致性。

## Docker 部署
1. 构建镜像：
   ```bash
   docker build -t todo-reminder .
   ```
2. 运行容器并挂载持久化数据卷：
   ```bash
   docker run -d --name todo-reminder -p 8000:8000 -v todo_data:/app/app/data todo-reminder
   ```
   该命令会把 SQLite 数据目录挂载到 Docker 卷 `todo_data`，容器重建后任务数据仍会保留。
3. 访问 `http://localhost:8000`。

## 常见问题
- **没有提醒？** 请确认 Webhook 地址正确，且部署环境可以访问飞书。
- **Webhook 返回 200 但没有真正发送？** 新版本会额外检查飞书返回体中的业务状态码，并在日志中输出失败原因。
- **时间显示不一致？** 请确保客户端理解当前系统统一使用北京时间。
