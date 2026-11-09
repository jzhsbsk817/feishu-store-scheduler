# 飞书门店调度（GitHub Actions 版）

原项目是一个「常驻 Flask 服务 + 内部线程调度」的定时任务系统，向飞书群推送：星级群每日追踪汇总、中差评/回复率回馈卡片、已反馈统计、22:00「6 点未反馈统计」分群卡、23:00 汇总卡，并在 16:00–23:50 每 10 分钟把卡片里的 @ 店长逐条刷新。

GitHub Actions 运行器是临时的（任务结束即销毁，无法常驻），因此本仓库把调度逻辑拆成**一次性任务**（`app/run_job.py`），由 Actions 的 `schedule` cron 按北京时间触发：

| 任务 | 触发（北京时间） | 说明 |
|---|---|---|
| `check` | 14:00–21:59 每 10 分钟 | 日期闸门 → 连发卡片 1/2/3（群消息识别去重，绝不重复发） |
| `refresh` | 16:00–23:50 每 10 分钟 | 卡片 2/3 的 @ 店长逐条删除→等 5 秒→恢复（@ 循环刷新） |
| `duty` | 22:00（当天首次） | 两反馈群各发「6 点未反馈统计」卡 |
| `summary` | 23:00（当天首次） | 汇总卡 @ 魏兆翔/魏兆翎/莫恩健 |

cron 在 UTC 配置：`*/10 6-15 * * *` ≈ 北京时间 14:00–23:59。

## 密钥与配置（不入库）

所有含密钥的文件（`app/config/`、`app/.env`）通过 **GitHub Secret `APP_SECRETS`** 在运行时还原：

```
APP_SECRETS = base64( gzip( tar(app/config/* , app/.env) ) )
```

仓库公开，但密钥/业务数据只在运行时存在，不落库。

## 需要的 Secrets / Variables

- `APP_SECRETS`：上述打包后的字符串（在仓库 Settings → Secrets 中设置）。
- `FB_MODE`（Variables，可选，默认 `live`）：`live`=发群并真 @；`trial`=仅本人私聊。

## 手动触发

在 Actions 页面 `Run workflow` 并填写 `job`：`dispatch | check | refresh | duty | summary | verify`。
`verify` 只取飞书 token 验证链路，不发任何卡片。

## 本地开发

```bash
cd app
cp .env.example .env   # 填入真实凭证
python run_job.py verify
python run_job.py dispatch
```
