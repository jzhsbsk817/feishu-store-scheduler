#!/usr/bin/env bash
# 启动脚本（不依赖 pyenv / 固定路径，适配任意干净的 Ubuntu/Debian 环境）
# 用法：
#   PORT=3000 FB_MODE=trial bash start.sh        # 试运行（卡片只发本人）
#   PORT=3000 FB_MODE=live  bash start.sh        # 正式运行（发群 + 真 @ 店长）
set -u
cd "$(dirname "$0")"

PORT="${PORT:-3000}"
FB_MODE="${FB_MODE:-trial}"

echo "[start] 安装依赖..."
python3 -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
python3 -m pip install --quiet -r requirements.txt 2>&1 | tail -5 || true

mkdir -p data
if [ ! -f .env ]; then
  echo "[start] ⚠ 未找到 .env，请先： cp .env.example .env  并填入飞书凭证，然后重新启动"
fi

# 单实例：终止已有 app.py / watchdog
pkill -f "python3 app.py" 2>/dev/null && sleep 2 || true
pkill -f "bash watchdog.sh" 2>/dev/null || true

echo "[start] 启动 app.py  (PORT=$PORT, FB_MODE=$FB_MODE)"
PORT="$PORT" FB_MODE="$FB_MODE" setsid nohup python3 app.py >> deploy.log 2>&1 < /dev/null &
echo $! > app.pid

# 启动看门狗（崩溃/探活失败自动重启；Northflank 不休眠，无需 cron）
PORT="$PORT" FB_MODE="$FB_MODE" setsid nohup bash watchdog.sh >> watchdog.log 2>&1 < /dev/null &

sleep 7
if curl -sf -m 5 "http://127.0.0.1:$PORT/api/heartbeat" >/dev/null 2>&1; then
  echo "[start] ✅ 心跳正常，服务已启动（PID $(cat app.pid)）"
  echo "[start] 网页： http://<本机IP>:$PORT/    健康检查： curl localhost:$PORT/api/heartbeat"
else
  echo "[start] ❌ 心跳失败，最近日志："; tail -25 deploy.log
fi
