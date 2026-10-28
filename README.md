# 飞书任务提醒

> 一个装在自己电脑上的任务提醒小工具：把要做的事记下来，到时间自动发飞书消息提醒你。

不用注册账号，不用买服务器，任务数据保存在本机。页面简单，适合个人使用，也适合小团队放在内网共用。

如果你没有部署过网页项目，建议直接从 [方式一：本机运行](#方式一本机运行) 开始，按顺序复制命令即可。

## 目录

- [这个工具能做什么](#这个工具能做什么)
- [部署前准备](#部署前准备)
- [方式一：本机运行](#方式一本机运行)
- [方式二：Docker 部署](#方式二docker-部署)
- [方式三：局域网访问](#方式三局域网访问)
- [部署完成检查清单](#部署完成检查清单)
- [日常使用](#日常使用)
- [提醒规则](#提醒规则)
- [配置说明](#配置说明)
- [数据备份与升级](#数据备份与升级)
- [常见问题](#常见问题)
- [项目结构](#项目结构)
- [运行测试](#运行测试)
- [API 速览](#api-速览)
- [安全建议](#安全建议)

## 这个工具能做什么

| 能力 | 说明 |
| --- | --- |
| 任务管理 | 新建、编辑、删除任务；支持标题、备注、开始时间与可选截止时间 |
| 时间模式 | 开始/截止时间均可选择「具体时间」或「全天」 |
| 三类提醒 | 开始提醒、截止前 N 分钟提醒、每日固定时间提醒 |
| 飞书推送 | 配置机器人 Webhook 后自动发送纯文本消息，支持一键测试连通性 |
| 双视图 | 「任务管理」工作台与「时间线」总览页面 |
| 本地存储 | SQLite 自动建表、自动兼容旧版数据库，无需手工迁移 |
| 时区一致 | 后端存储、提醒计算与前端展示统一使用北京时间 |

页面入口：

| 页面 | 地址 | 用途 |
| --- | --- | --- |
| 任务管理 | `http://127.0.0.1:8000/` | 新建任务、编辑任务、配置提醒 |
| 时间线 | `http://127.0.0.1:8000/tasks` | 按开始时间查看全部任务 |
| API 文档 | `http://127.0.0.1:8000/docs` | 查看接口说明，可选 |

## 部署前准备

开始之前，请确认：

- 有一台可以正常上网的电脑，Windows、macOS 或 Linux 都可以。
- 有权限在这台电脑上安装软件（Python 或 Docker）。
- 如果需要飞书提醒，准备一个飞书群，并且你有添加群机器人的权限。
- 知道怎么打开终端（命令行）。不会也没关系，下面会一步一步说明。

不需要准备：公网 IP、域名、云服务器。

> **重要提醒**：提醒是由运行在这台电脑上的程序发出的。电脑关机、休眠或程序退出后，提醒会暂停。如果希望长期稳定运行，建议使用一台常开的小主机，或者部署到云服务器。

## 方式一：本机运行

适合第一次接触这个项目、想先在自己电脑上试用的用户。Windows、macOS、Linux 都可以，按步骤操作即可。

### 第 1 步：安装 Python

项目需要 **Python 3.11 或 3.12**。推荐这两个版本，因为项目依赖和 Docker 镜像都以 3.11 为基准；过新的 Python 版本可能暂时没有可用的依赖包。

**Windows**

1. 打开 <https://www.python.org/downloads/>。
2. 下载 Python 3.12 的 Windows 安装包。
3. 运行安装包，安装时务必勾选 **Add python.exe to PATH**，然后点击 Install Now。
4. 安装完成后打开 PowerShell，输入：

   ```powershell
   python --version
   ```

   看到类似 `Python 3.12.x` 就说明安装成功。
5. 如果提示找不到 `python`，尝试：

   ```powershell
   py --version
   ```

**macOS**

1. 打开 <https://www.python.org/downloads/> 下载 macOS 安装包并安装。
2. 或者使用 Homebrew 安装：

   ```bash
   brew install python@3.12
   ```

3. 打开「终端」，输入：

   ```bash
   python3 --version
   ```

**Linux（以 Ubuntu / Debian 为例）**

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
python3 --version
```

> Windows 通常使用 `python` 或 `py` 命令；macOS / Linux 通常使用 `python3`。下面命令按 Windows 编写，macOS / Linux 用户把 `python` 换成 `python3` 即可。

### 第 2 步：下载项目

**情况 A：电脑上已经安装了 Git**

打开终端，执行：

```bash
git clone https://github.com/Qianxia666/todo-reminder.git
cd todo-reminder
```

**情况 B：没有安装 Git**

1. 打开项目页面 <https://github.com/Qianxia666/todo-reminder>。
2. 点击绿色的 **Code** 按钮，选择 **Download ZIP**。
3. 解压下载的压缩包。
4. 打开终端并进入解压后的项目文件夹。

不会进入文件夹时，可以这样做：

- **Windows**：打开项目文件夹，在空白处按住 `Shift` 再点右键，选择「在此处打开 PowerShell 窗口」；Windows 11 可直接选择「在终端中打开」。
- **macOS**：打开「终端」，输入 `cd `（注意 `cd` 后面有一个空格），把项目文件夹拖进终端窗口，再按回车。
- **Linux**：在文件管理器中右键项目文件夹，选择「在终端中打开」。

进入文件夹后，确认位置是否正确：

```bash
dir     # Windows
ls      # macOS / Linux
```

应该能看到 `README.md`、`app`、`static`、`requirements.txt` 等内容。

### 第 3 步：创建并激活虚拟环境

虚拟环境相当于给这个项目单独准备一个 Python 工具箱，不会影响电脑里其他 Python 程序。

**Windows PowerShell**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

如果 `python` 命令不可用，把第一行换成：

```powershell
py -3 -m venv .venv
```

激活成功后，命令行最前面会出现 `(.venv)`。

如果 PowerShell 提示「无法加载文件，因为在此系统上禁止运行脚本」，先执行：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

然后再次执行 `.venv\Scripts\Activate.ps1`。

**Windows CMD（命令提示符）**

```bat
python -m venv .venv
.venv\Scripts\activate.bat
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

激活成功后，命令行最前面会出现 `(.venv)`。

> Linux 如果提示缺少 venv，请先安装：`sudo apt install python3-venv`。
>
> 以后每次重新打开终端，都要先进入项目文件夹并重新激活虚拟环境。

### 第 4 步：安装依赖

确认命令行前面有 `(.venv)`，然后执行：

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

安装成功的标志是最后出现 `Successfully installed ...`。

如果下载速度很慢或超时，可以换用国内镜像源：

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 第 5 步：启动服务

在项目文件夹中执行：

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

启动成功后，终端会显示类似内容：

```text
INFO: Started server process [...]
INFO: Application startup complete.
INFO: Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

看到最后一行就说明服务已经启动。

- **不要关闭这个终端窗口**，关闭窗口等于停止服务。
- 需要停止服务时，在终端里按 `Ctrl + C`。
- 不要同时启动两个相同的服务，否则会遇到端口占用问题。

### 第 6 步：打开网页并使用

打开浏览器，访问：

```text
http://127.0.0.1:8000
```

应该能看到「任务与提醒」页面。第一次使用时：

1. 在「新建任务」中填写任务标题，例如「准备周会资料」。
2. 选择开始时间，可以选「具体时间」或「全天」。
3. 如果需要截止提醒，再填写截止时间。
4. 需要每天提醒时，打开「每日提醒」开关。
5. 点击「保存任务」。
6. 刷新页面，任务仍然存在，说明数据保存成功。

### 第 7 步：配置飞书机器人

如果只需要本地任务管理，可以跳过这一步；需要飞书推送时再配置。

1. 在飞书群聊中打开「群设置」→「群机器人」→「添加机器人」→「自定义机器人」。
2. 按提示创建机器人，复制生成的 Webhook 地址，形如：

   ```text
   https://open.feishu.cn/open-apis/bot/v2/hook/...
   ```

3. 回到任务提醒页面，在右侧「提醒设置」中粘贴 Webhook。
4. 设置「提前提醒」分钟数（默认 30 分钟）和「每日时间」（默认 09:00）。
5. 点击「保存设置」，再点击「测试推送」。
6. 飞书群里收到测试消息，说明配置成功。

注意事项：

- Webhook 留空会暂停所有飞书推送，适合先体验任务管理功能。
- Webhook 属于敏感凭据，不要发到公开群、截图或代码仓库里。
- 默认只允许飞书 / Lark 官方 HTTPS 域名，自建代理需要通过环境变量额外配置。

### 第 8 步：让服务保持运行

提醒功能依赖后台程序持续运行：

- **最简单的方式**：保持终端窗口打开，并关闭电脑自动休眠。
- 关闭浏览器页面没有关系，只要终端里的服务还在运行，提醒就会继续。
- 电脑关机、休眠或终端被关闭后，提醒会暂停；重新启动服务后，未发送的提醒可能会补发。

**macOS / Linux 后台运行（可选）**

```bash
nohup python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > reminder.log 2>&1 &
```

停止后台服务：

```bash
pkill -f "uvicorn app.main:app"
```

**Windows**

可以把终端窗口最小化。若希望开机自动运行、长期常驻，建议改用下面的 Docker 方式，或使用系统自带的任务计划程序。

## 方式二：Docker 部署

适合已经安装 Docker，或者希望服务在后台常驻的用户。Docker 会把运行环境打包好，避免本地 Python 版本和依赖问题。

### 第 1 步：安装 Docker

**Windows / macOS**

1. 打开 <https://www.docker.com/products/docker-desktop/>，下载并安装 Docker Desktop。
2. Windows 安装过程中如果提示启用 WSL2，按提示完成。
3. 安装完成后启动 Docker Desktop，等待界面显示 Docker 正在运行。
4. 打开终端，确认命令可用：

   ```bash
   docker --version
   docker compose version
   ```

**Linux**

安装 Docker Engine 和 Compose 插件，可参考官方文档：<https://docs.docker.com/engine/install/>。

安装后同样执行上面的两条命令确认版本。

> 如果提示 `docker: command not found`，通常是 Docker 没有安装成功，或者 Docker Desktop 还没有启动。

### 第 2 步：启动服务

进入项目文件夹，执行：

```bash
docker compose up -d --build
```

这条命令会完成三件事：

1. 根据 `Dockerfile` 构建镜像。
2. 创建并启动名为 `todo-reminder` 的容器。
3. 把容器内的数据目录挂载到 Docker 卷 `todo_data`，重建容器不会丢失任务。

第一次执行需要下载基础镜像和安装依赖，请耐心等待。

查看运行状态：

```bash
docker compose ps
```

看到容器状态为 `running`，并且端口显示 `127.0.0.1:8000->8000/tcp`，说明启动成功。

查看日志：

```bash
docker compose logs -f app
```

看到 `Uvicorn running on http://0.0.0.0:8000` 即可。按 `Ctrl + C` 退出日志查看，不会停止容器。

### 第 3 步：打开网页

浏览器访问：

```text
http://127.0.0.1:8000
```

后续使用步骤与方式一相同：新建任务、配置 Webhook、测试推送。

### 常用 Docker 命令

| 目的 | 命令 |
| --- | --- |
| 查看容器状态 | `docker compose ps` |
| 查看实时日志 | `docker compose logs -f app` |
| 停止服务（保留数据） | `docker compose stop` |
| 再次启动 | `docker compose start` |
| 重启服务 | `docker compose restart` |
| 停止并删除容器（保留数据卷） | `docker compose down` |
| 更新代码后重新构建 | `git pull` 后执行 `docker compose up -d --build` |
| 删除容器和数据卷（会丢失任务数据） | `docker compose down -v` |

> `docker compose down` 只会删除容器，任务数据仍在 `todo_data` 卷里；`docker compose down -v` 会连数据一起删除，请谨慎使用。

### 不用 Compose 的启动方式（可选）

如果只想使用 `docker` 命令：

```bash
docker build -t todo-reminder .
docker run -d --name todo-reminder \
  -p 127.0.0.1:8000:8000 \
  -v todo_data:/app/app/data \
  todo-reminder
```

查看日志：

```bash
docker logs -f todo-reminder
```

停止并删除容器：

```bash
docker stop todo-reminder
docker rm todo-reminder
```

## 方式三：局域网访问

默认情况下，服务只允许本机访问（`127.0.0.1`），这样最安全。如果希望手机或同一 Wi-Fi 下的其他电脑也能访问，可以按下面的方法调整。

### 本机运行时

启动命令把 `--host 127.0.0.1` 改成 `--host 0.0.0.0`：

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Docker 运行时

编辑 `docker-compose.yml`，把端口映射：

```yaml
ports:
  - "127.0.0.1:8000:8000"
```

改成：

```yaml
ports:
  - "8000:8000"
```

然后重新启动：

```bash
docker compose up -d
```

### 查找电脑的局域网 IP

- **Windows**：执行 `ipconfig`，找到「IPv4 地址」，通常是 `192.168.x.x`。
- **macOS**：执行 `ipconfig getifaddr en0`；如果为空，把 `en0` 换成 `en1`。
- **Linux**：执行 `hostname -I`。

然后在同一局域网的设备上访问：

```text
http://电脑的局域网IP:8000
```

例如：

```text
http://192.168.1.10:8000
```

### 局域网访问不了怎么办

1. 确认两台设备连接的是同一个 Wi-Fi / 局域网。
2. 确认启动命令使用了 `--host 0.0.0.0`，或 Docker 端口映射没有绑定 `127.0.0.1`。
3. 检查电脑防火墙是否允许 8000 端口：
   - Windows 首次启动时如果弹出防火墙提示，选择允许「专用网络」。
   - macOS 在「系统设置 → 网络 → 防火墙」中允许 Python 接收连接。
   - Linux 如果启用了 ufw，可执行 `sudo ufw allow 8000/tcp`。
4. 确认访问的 IP 和端口正确，不要使用 `127.0.0.1` 或 `localhost` 访问另一台设备。

> **安全提醒**：本项目没有内置登录功能。只建议在可信的家庭或公司内网开启局域网访问，不要直接把 8000 端口暴露到公网。

## 部署完成检查清单

部署完成后，建议逐项确认：

- [ ] 浏览器能打开 `http://127.0.0.1:8000`。
- [ ] 能新建任务，刷新页面后任务仍然存在。
- [ ] 已配置飞书 Webhook，并点击「测试推送」成功收到消息。
- [ ] 关掉浏览器再打开，任务仍然存在。
- [ ] 停止并重新启动服务后，任务仍然存在。
- [ ] 知道如何停止服务（`Ctrl + C` 或 `docker compose stop`）。
- [ ] 知道电脑关机或休眠期间不会发送提醒。

全部确认后，就可以正常使用了。

## 日常使用

| 操作 | 位置 | 说明 |
| --- | --- | --- |
| 新建任务 | 首页「新建任务」 | 填写标题和开始时间，按需添加截止时间 |
| 编辑任务 | 任务列表的操作按钮 | 修改时间会重置对应提醒状态 |
| 删除任务 | 任务列表的操作按钮 | 删除后不可恢复 |
| 查看时间线 | 顶部「时间线」 | 按开始时间从早到晚排列 |
| 配置提醒 | 首页右侧「提醒设置」 | Webhook、提前分钟数、每日时间 |
| 测试推送 | 「提醒设置」中的「测试推送」 | 立即发送一条测试消息 |

提醒发送状态会显示在任务列表中；页面顶部还会显示通知是否已配置。

## 提醒规则

| 提醒类型 | 触发时机 | 触发次数 |
| --- | --- | --- |
| 开始提醒 | 到达任务开始时间之后 | 每个任务 1 次 |
| 截止提醒 | 截止时间前 N 分钟（默认 30 分钟） | 每个任务 1 次 |
| 每日提醒 | 任务有效期内，每天到达设定时间之后 | 每天 1 次 |

几个细节：

- 所有时间均按北京时间（`Asia/Shanghai`）计算和展示。
- 时间精度为分钟；例如截止时间为 17:00，后台在 17:00:30 检查仍会正常提醒。
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
| `TODO_ALLOWED_WEBHOOK_HOSTS` | 额外允许的 HTTPS Webhook 域名，逗号分隔 | 空 |
| `TODO_ALLOW_INSECURE_WEBHOOK_HTTP` | 设为 `1`/`true` 允许 HTTP Webhook，仅限可信网络 | 关闭 |

**Windows PowerShell 临时设置示例**

```powershell
$env:TODO_DB_PATH = "D:\todo-data\reminder.db"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**macOS / Linux 临时设置示例**

```bash
TODO_DB_PATH=/path/to/reminder.db python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Docker 设置示例**

编辑 `docker-compose.yml` 的 `environment` 部分，例如：

```yaml
environment:
  - TZ=Asia/Shanghai
  - TODO_WEBHOOK_TIMEOUT_SECONDS=10
```

修改后执行 `docker compose up -d` 生效。

### Webhook 安全限制

- 默认只接受 HTTPS 地址。
- 默认只允许 `open.feishu.cn` 与 `open.larksuite.com` 域名。
- 飞书 / Lark 官方域名必须使用 `/open-apis/bot/v2/hook/...` 路径。
- 使用自建兼容代理时，需要通过 `TODO_ALLOWED_WEBHOOK_HOSTS` 显式加入域名。
- 不建议开启 `TODO_ALLOW_INSECURE_WEBHOOK_HTTP`，除非网络环境完全可信。

## 数据备份与升级

### 数据保存在哪里

- 本机运行：`app/data/reminder.db`，同目录下可能还有 `reminder.db-wal`、`reminder.db-shm`。
- Docker 运行：命名卷 `todo_data`，挂载到容器内 `/app/app/data`。

### 本机备份与恢复

1. 在运行服务的终端按 `Ctrl + C` 停止服务。
2. 复制整个 `app/data` 文件夹到安全位置。
3. 需要恢复时，停止服务，把备份的 `app/data` 文件夹复制回项目目录。
4. 重新启动服务。

> 建议在停止服务后备份，避免复制到正在写入的数据库文件。

### Docker 备份与恢复

备份：

```bash
docker compose stop
docker cp todo-reminder:/app/app/data ./todo-data-backup
docker compose start
```

恢复：

```bash
docker compose stop
docker cp ./todo-data-backup/. todo-reminder:/app/app/data
docker compose start
```

> 如果执行过 `docker compose down` 删除了容器，先执行 `docker compose up -d` 重新创建容器，再进行恢复。

### 升级到新版本

**本机运行**

```bash
# 先停止服务：Ctrl + C
git pull
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Docker 运行**

```bash
git pull
docker compose up -d --build
```

数据库会在启动时自动补齐新增的列和索引，不需要手工迁移。建议升级前先备份数据；如果数据库版本比程序新，启动时会报错，此时需要升级程序而不是修改数据库。

## 常见问题

**提示「python 不是内部或外部命令」怎么办？**

说明 Python 没有加入系统 PATH。重新运行 Python 安装包，选择 Modify，勾选 **Add python.exe to PATH**；或者尝试使用 `py` 命令。也可以重新安装 Python。

**PowerShell 提示禁止运行脚本怎么办？**

执行：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

然后重新激活虚拟环境。只对当前用户生效，不会影响其他账户。

**pip 安装依赖很慢或失败怎么办？**

先确认网络可以访问 PyPI。国内网络可以使用镜像：

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

如果公司网络需要代理，请先配置 `HTTP_PROXY` / `HTTPS_PROXY` 环境变量。

**启动时提示端口被占用怎么办？**

说明 8000 端口已经被其他程序使用。换一个端口即可：

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

然后访问 `http://127.0.0.1:8001`。Docker 用户同理，修改 `docker-compose.yml` 中的端口映射。

**浏览器打不开页面怎么办？**

1. 确认终端里的服务仍在运行，没有报错退出。
2. 确认地址是 `http://127.0.0.1:8000`，不是 `https`。
3. 如果修改过端口，使用新端口访问。
4. 查看终端日志中的错误信息，常见原因是依赖没有安装完整。

**关闭终端后为什么没有提醒了？**

提醒服务运行在终端里，关闭终端就会停止服务。请保持终端窗口打开，或使用 Docker / 后台运行方式。电脑休眠或关机期间也不会发送提醒。

**没有收到飞书提醒怎么办？**

1. 在「提醒设置」中点击「测试推送」，确认能否收到测试消息。
2. 检查 Webhook 地址是否完整、是否被清空。
3. 确认电脑可以访问飞书（公司网络或代理可能拦截）。
4. 查看终端日志中的 `Failed to send` 或 `business failure` 信息。
5. 确认任务时间已经到了，并且后台仍在运行。

**Webhook 返回 200，但飞书群里没有消息？**

程序会进一步检查飞书返回体中的业务状态码。返回 200 只代表 HTTP 请求成功，不一定代表消息发送成功；具体失败原因会写入终端日志。

**局域网访问不了怎么办？**

检查启动命令是否使用 `--host 0.0.0.0`、Docker 端口映射是否绑定 `127.0.0.1`、电脑防火墙是否放行 8000 端口，以及设备是否在同一局域网。详见[方式三：局域网访问](#方式三局域网访问)。

**Docker 命令找不到，或者容器启动后立刻退出怎么办？**

先确认 Docker Desktop 已经启动，并且 `docker --version` 有输出。容器启动失败时查看日志：

```bash
docker compose logs app
```

常见原因是 8000 端口被占用，修改端口映射后重新执行 `docker compose up -d`。

**数据会丢吗？**

任务保存在本机 SQLite 文件或 Docker 卷中，正常关闭和重启不会丢失。删除项目文件夹、执行 `docker compose down -v`、或手动删除数据库文件会丢失数据，建议定期备份。

**时间显示不一致怎么办？**

后端、前端与提醒计算统一使用北京时间，请以此为准；服务器或电脑本身的时区设置不会影响任务时间。

## 项目结构

```text
app/
  main.py             # FastAPI 入口、路由与中间件
  database.py         # SQLite 访问、建表迁移与提醒认领
  models.py           # Pydantic 数据模型与校验
  reminder.py         # 后台提醒线程与飞书推送
  webhook_security.py # Webhook URL 安全策略
  timezone.py         # 北京时间工具
  data/               # SQLite 数据目录（运行时生成）
static/
  index.html          # 任务管理页面
  tasks.html          # 时间线页面
  app.js              # 任务管理页面逻辑
  tasks.js            # 时间线页面逻辑
  styles.css          # 页面样式
tests/                # API、数据库与提醒服务回归测试
```

## 运行测试

如果你修改了代码，可以运行回归测试：

```bash
pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python -m compileall -q app tests
```

测试覆盖任务 API 增删改查与部分更新、数据库提醒认领与迁移、提醒时间边界、Webhook 安全策略等。

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

- 项目默认没有内置登录鉴权，适合个人或内网使用；默认只监听本机 `127.0.0.1`。
- 若要在局域网共享，请只在可信网络中使用；若要暴露到公网，必须放在带身份认证、TLS 和访问控制的反向代理之后。
- 飞书 Webhook 属于敏感凭据，请避免写入代码仓库、日志或公开截图。
- API 响应已设置 `Cache-Control: no-store`，减少浏览器或代理缓存敏感设置的风险。
- 页面响应附带 `X-Content-Type-Options`、`X-Frame-Options`、`Referrer-Policy` 等安全头。

## 技术栈

Python 3.11 · FastAPI · Pydantic · SQLite · 原生 HTML / CSS / JavaScript · Docker
