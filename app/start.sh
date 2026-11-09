#!/usr/bin/env bash
# Render Background Worker 启动脚本
# Render 自行管理进程生命周期，本脚本只做两件事：
#   1) 从环境变量 APP_SECRETS（gzip+base64 的 tar 包）还原 config/ 与 .env（运行时，不入库）
#   2) 前台常驻启动 Flask 调度服务（exec 交给 Render 管理，崩溃自动重启）
set -e
cd "$(dirname "$0")"

python3 - <<'PY'
import os, io, base64, tarfile, gzip
raw = os.environ.get("APP_SECRETS", "")
if not raw:
    print("[start] APP_SECRETS 未设置，假定本地已存在 config/ 与 .env（开发模式）", flush=True)
else:
    try:
        blob = base64.b64decode(raw)
        with gzip.GzipFile(fileobj=io.BytesIO(blob)) as gz:
            tar_bytes = gz.read()
        with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as tf:
            tf.extractall(".")
        print("[start] ✅ 已从 APP_SECRETS 还原 config/ 与 .env", flush=True)
    except Exception as e:
        print("[start] ❌ APP_SECRETS 还原失败：%s" % e, flush=True)
        raise
if "FB_MODE" not in os.environ:
    os.environ["FB_MODE"] = "live"
PY

mkdir -p data
exec python3 app.py
