# 定时任务调度台 · Northflank Sandbox 部署说明

把「星级群每日追踪 + 反馈 @店长 + 22:00 分群 6 点未反馈统计」这套常驻定时任务部署到
Northflank Sandbox（免费档 0.5 vCPU / 1GB，不休眠）。

## 一、包内文件

```
northflank/
├── DEPLOY.md                本文件
└── app/
    ├── app.py               常驻服务：HTTP + 内置调度（14:15发卡 / 16:00–23:50 @刷新 / 22:00 分群统计 / 23:00 汇总 / 23:59 封板）
    ├── feedback_task.py     中差评明细 / 回复率 / 已反馈统计 / @店长 / 汇总卡
    ├── star_daily_task.py   星级群第1张汇总卡 + 看板数据拉取
    ├── duty_check_task.py   22:00 分群「6 点未反馈统计」（各发各群、各 @ 各店长）
    ├── requirements.txt     flask / requests
    ├── start.sh             启动(app + 看门狗)，不依赖固定 Python 路径
    ├── watchdog.sh          每 30s 探活，崩溃自愈
    ├── Dockerfile           容器部署备选
    ├── .env.example         凭证模板（复制为 .env 后填值）
    ├── config/              门店映射、店长 open_id、群 chat_id、表单/多维表格 token（业务配置，无真实飞书 secret）
    └── static/index.html    调度台网页
```

## 二、把代码放到 Sandbox

任选一种：

- **A. 直接上传**：从本环境下载 `northflank.tar.gz`，在 Northflank Sandbox 的终端/上传功能传上去，解压。
- **B. Git**：本包可 `git init` 后提交，推到你的仓库，Sandbox 拉取（注意 `.env` 不要提交，见第五节）。
- **C. 容器**：用 `Dockerfile` 构建镜像部署（推荐生产，隔离更干净）。

## 三、在 Sandbox 终端执行

```bash
# 1) 解压（若用上传方式）
tar xzf northflank.tar.gz && cd northflank/app

# 2) 配置凭证（从原 .env 把 5 个值抄过来；CHROMIUM_PATH 留空即可，OCR 缺失自动跳过）
cp .env.example .env
vi .env          # 填 LARK_APP_ID / LARK_APP_SECRET / BOARD_USER / BOARD_PASSWORD

# 3) 启动（首次用 trial 试运行，确认无误再切 live）
PORT=3000 FB_MODE=trial bash start.sh

# 4) 验证
curl -s localhost:3000/api/heartbeat        # 返回 ok 即服务起
curl -s localhost:3000/api/status            # 返回卡片清单

# 5) 正式运行（发群 + 真 @ 店长）
pkill -f "python3 app.py"; pkill -f "bash watchdog.sh"
PORT=3000 FB_MODE=live bash start.sh
```

> 网页也可手动操作：`http://<Sandbox公网IP>:3000/` 点「正式运行」按钮（会把模式写入本地状态）。
> 但用 `FB_MODE=live` 启动更稳，所有定时任务都按 live 走。

## 四、定时任务时间表（内置，无需额外 cron）

| 时间 | 动作 |
|---|---|
| 14:15 起每 15 分钟 | 检查看板日期==昨天 → 发星级群第1/2/3张卡（当天只发一次） |
| 16:00–23:50 每 10 分钟 | 卡片2/3 @店长 逐条删除→等5秒→恢复（仅 PATCH，不新发） |
| 22:00 | 向「T门店反馈收集群」「小加盟店长沟通群」各发一张「6 点未反馈统计」卡（各 @ 本群店长：今日未发 / 近3天持续未发 / 近7天 top3 / 当天未测油） |
| 23:00 | 星级群发「未反馈门店汇总」卡（@ 魏兆翔/魏兆翎/莫恩健，数字每10秒自动更新） |
| 23:59 | 封板：卡片关按键、@变文本/店名、汇总卡定格 |

## 五、注意事项

1. **凭证安全**：`.env` 含飞书 `app_secret`，**绝对不要**提交到 git 或公开仓库；用容器时通过 Secret 注入。
2. **看板网络**：卡片1/数据来自 `dashboard-board.app.workbuddy.host`，需 Sandbox 能访问公网；若拉取失败，相关卡片会跳过但有 try/except 兜底，不至于整进程崩。
3. **OCR**：回复率截图判定用到 tesseract，Sandbox 若无则自动跳过（不影响中差评/已反馈统计与 @）。
4. **时区**：调度按 Sandbox 系统本地时间（UTC+8 业务时间）。确认 Sandbox 时区设置正确（`date` 应显示北京时间），否则发卡时刻会偏移。
5. **端口**：默认 3000，`PORT` 可改；外部访问需在 Northflank 配端口转发/域名。
6. **单实例**：调度线程内含单实例锁；同一包不要重复启动多份。

## 六、日志与排错

- 启动日志：`deploy.log`；看门狗：`watchdog.log`；网页内也有实时日志框。
- 进程：`cat app.pid`；重启：`bash start.sh`（会先杀旧进程）。
- 状态文件：`app/data/feedback_state.json`（首次运行自动建，含发卡 message_id、封板标记等）。
