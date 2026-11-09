#!/usr/bin/env bash
# 看门狗：每 30 秒探活，失败则重启 app.py（不休眠环境也能自愈）
set -u
cd "$(dirname "$0")"
PORT="${PORT:-3000}"
while true; do
  if ! curl -sf -m 5 "http://127.0.0.1:$PORT/api/heartbeat" >/dev/null 2>&1; then
    echo "$(date '+%F %T') 探活失败，重启 app.py" >> watchdog.log
    pkill -f "python3 app.py" 2>/dev/null || true
    sleep 2
    PORT="$PORT" FB_MODE="${FB_MODE:-trial}" setsid nohup python3 app.py >> deploy.log 2>&1 < /dev/null &
  fi
  sleep 30
done
