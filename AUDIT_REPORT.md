# 代码审计与运行验证报告

## 结论

本项目已完成三轮逐文件代码审计，并对后端 Python、SQLite 事务/迁移、提醒并发去重、Webhook 网络边界、FastAPI API、前端 HTML/JavaScript/CSS、Docker 配置与测试代码进行了实际运行验证。第三轮针对旧数据兼容、设置接口健壮性、Webhook 协议异常、后台线程生命周期和前端文案一致性做了补强。

## 第三轮新增修复

1. **旧库秒级时间导致“仅改标题就重置提醒状态”**：历史数据可能存成 `:45` 秒或 naive 时间，而新请求统一归一化为整分。原比较逻辑直接对比字符串，会把这些任务误判为“改期”，从而把已发送的 `start_notified` / `end_notified` / `last_daily_notified` 重置为未发送。现新增 `_normalize_stored_datetime`，先把库内值按当前规则归一化再比较，状态保持不变，同时把时间写回为归一化值。
2. **`POST /api/settings` 缺字段会静默清空 Webhook**：原 `SettingsUpdate` 各字段带默认值，客户端漏传 `webhook_url` 时会被解析为空字符串并覆盖数据库，导致提醒直接停发。现改为三个字段全部必填，缺省返回 422 且原配置不变。
3. **Webhook 协议层异常会让测试接口 500**：`http.client` 的 `IncompleteRead`、`BadStatusLine` 等 `HTTPException` 不属于 `OSError`/`URLError`，此前会穿透到 API。现在与网络错误统一捕获并记录为失败，测试接口返回明确的失败结果，worker 也不会因异常退出。
4. **后台 worker 在“上次 stop 超时”后无法正确重启**：若旧线程仍在收尾（stop_event 已置位但线程未退出），原来的 `start()` 会直接返回，导致提醒彻底停摆。现在 `start()` 会先等待旧线程收尾，仍存活则清除 stop 事件复用旧线程，已退出则创建新线程。
5. **内部变更入口缺少空白标题防御**：`_build_task_mutation` 直接接收内部 patch，此前空白标题可绕过 Pydantic 校验写入空标题。现补充 `title.strip()` 非空校验并统一复用裁剪后的标题。
6. **前端移动端列标签与表头不一致**：移动端 `data-label` 里“提醒频率/状态”等文案与表头不一致，现已对齐。

## 第二轮新增修复

1. **并发局部更新可能静默覆盖其他请求**：原 `PUT /api/tasks/{id}` 先读取记录，再进入另一个事务写回完整任务。两个并发局部更新可能都基于同一旧快照，后提交者会覆盖先提交者修改。现改为在同一个 `BEGIN IMMEDIATE` 事务中完成“读取当前记录 → 合并 patch → 时间标准化 → 判断提醒状态重置 → 更新任务 → 清理旧 claim”，避免 lost update。
2. **Webhook SSRF/任意 URL 请求风险**：原配置只要求 `http(s)`，测试接口可被用来向任意目标发 POST。现在默认仅允许 HTTPS，并仅放行飞书/Lark 官方域名 `open.feishu.cn`、`open.larksuite.com`；可通过 `TODO_ALLOWED_WEBHOOK_HOSTS` 显式增加兼容代理域名。官方域名还会校验机器人 Webhook 路径格式。
3. **HTTP 明文泄露 Webhook 凭据**：默认拒绝 HTTP Webhook。确需可信内网兼容时，可显式设置 `TODO_ALLOW_INSECURE_WEBHOOK_HTTP=1`，生产环境不建议开启。
4. **Webhook 重定向绕过目标限制**：Webhook 客户端改为禁止自动 HTTP 重定向，避免允许域名把请求重定向到其他目标。
5. **Webhook 响应无大小上限**：响应读取限制为 64 KiB，避免异常/恶意服务返回超大响应导致内存不必要增长；HTTP 错误响应同样限长读取。
6. **HTTP 200 被误判为成功**：过去非 JSON 200、代理登录页、缺少飞书业务状态码的 JSON 都可能被当作成功，导致提醒被永久标记已发送。现在只有明确 `code == 0` 或 `StatusCode == 0` 才完成提醒状态。
7. **未来数据库版本可能被旧程序误降级**：启动时读取 `PRAGMA user_version`；若数据库 schema 版本高于当前程序支持版本，将明确拒绝启动，而不是覆盖版本号继续运行。
8. **敏感设置可被缓存**：所有 `/api/` 响应增加 `Cache-Control: no-store`，并统一增加 `X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy: no-referrer`。
9. **Docker 默认暴露面过大**：Compose 与 README Docker 示例改为 `127.0.0.1:8000:8000`，默认只监听宿主机回环地址；需要局域网/公网访问时应显式配反向代理、TLS 与身份认证。

## 第一轮已完成修复（保留）

1. 旧 SQLite 数据库缺新增列时，初始化顺序导致启动失败：已改为先补列再建依赖索引。
2. 任务改期与后台 worker 认领存在竞态：任务时间更新与旧 claim 清理改为同一事务。
3. 每日提醒旧日程快照可能在任务改期后继续完成：每日 claim key 绑定当前计划快照。
4. 截止分钟内轮询可能漏掉每日提醒：按分钟精度保留截止分钟有效性。
5. SQLite 动态更新字段增加白名单，避免内部调用拼接非预期列名。
6. settings 单例记录被误删时可自动恢复。
7. 同步 SQLite API handler 使用 FastAPI 同步路由线程池语义，避免阻塞 async 事件循环。
8. Webhook 错误日志不再输出完整 URL 凭据。
9. 提醒 claim 增加 owner token，降低过期 claim 被旧 worker 错删/错完成风险。

## 回归测试

当前自动化测试总数：**45 项**，全部通过。新增覆盖包括：

- 并发局部任务修改不丢更新；
- 未来 schema version 拒绝误降级；
- API 敏感响应 no-store 与浏览器安全头；
- HTTP、未批准域名、非法 Webhook 拒绝；
- 显式允许自建 HTTPS 兼容域名；
- Webhook 超大响应拒绝；
- 非 JSON 200 不再误判成功；
- 缺少业务状态码的 JSON 不再误判成功；
- 旧库秒级/naive 时间仅改标题不重置提醒状态（第三轮）；
- `POST /api/settings` 缺少 webhook_url 返回 422 且不清空原值（第三轮）；
- 内部变更入口拒绝空白标题（第三轮）；
- worker 在中断的 stop 后恢复/重建（第三轮）；
- Webhook 协议异常（`IncompleteRead`）按失败处理（第三轮）；
- 原有 CRUD、全天时间、通知状态重置、旧数据库迁移、claim 并发、日提醒边界、worker 生命周期等测试继续通过。

## 交付边界

- 项目仍是个人/内网型应用，**没有内置用户登录系统**。默认本机监听/本机 Docker 端口绑定可以降低误暴露风险；若主动对外提供服务，必须在前置代理处增加身份认证、TLS 和访问控制。
- Webhook 在 SQLite 中仍以明文保存，这是单机工具的当前设计。应保护数据库文件和宿主机权限，不要把数据库提交到代码仓库。
- HTTP 请求与数据库提交之间无法实现真正的跨系统“恰好一次”原子事务：如果飞书已收到消息、但进程在 SQLite 写入“已完成”前崩溃，claim 过期后仍可能重试并产生一次重复消息。这属于无幂等键外部 Webhook 的固有限制；当前 claim token/TTL 已尽量缩小重复窗口。
- 当前执行环境无法联网重新下载依赖或在线跑 CVE 数据库，因此没有把“依赖漏洞数据库扫描”冒充为已完成。代码自身的依赖声明、导入、测试和实际启动会在最终验证中检查。

## 最终实际运行验证

第三轮交付前完整验证结果：

- `python -m unittest discover -s tests -v`：**45/45 通过**。
- `python -m compileall -q app tests`：通过。
- `node --check static/app.js`、`node --check static/tasks.js`：通过。
- HTML 重复 ID、`getElementById` 引用、`label for`、`aria-describedby` 检查：通过。
- 并发压力验证：6 写线程 + 4 读线程 + 4 claim 线程并行操作同一库 0 异常；4 个独立进程同时认领同一提醒，恰好 1 个成功。
- 真实 Uvicorn 进程冒烟：`/`、`/tasks`、静态资源、`GET /api/tasks`、`GET /api/settings` 全部 200；响应包含 `Cache-Control: no-store`、`X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy: no-referrer`。
- 真实 HTTP CRUD：创建、局部更新、非法时间窗 400、缺字段 422、删除 204 均符合预期；旧库秒级数据仅改标题后 `start_notified/end_notified/last_daily_notified` 保持已发送。
- 提醒端到端验证（本地 mock 飞书服务）：开始、截止、每日三类提醒均只发送一次；失败后 claim 释放且可重试成功；业务错误码不置完成；Webhook 为空不发送；未进入提前提醒窗口不发送。
- 浏览器验证：首屏加载、新建、编辑、删除、时间线排序、设置保存并刷新持久化均正常，无控制台错误。
- 后台 reminder worker 在服务启动时正常启动，在服务关闭时正常退出。
