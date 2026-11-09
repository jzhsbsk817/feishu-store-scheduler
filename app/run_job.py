#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一次性调度入口（供 GitHub Actions 调用）
=====================================
原 app.py 是「常驻服务 + 内部线程调度」。GitHub Actions 是临时运行器、任务结束即销毁，
无法常驻。本脚本把调度逻辑拆成「一次性任务」，由 Actions 的 cron 按时间分派调用：

    python3 run_job.py check     # 日期闸门 → 连发卡片 1/2/3（群消息识别去重，绝不重复发）
    python3 run_job.py refresh   # 卡片 2/3 的 @店长 逐条删除→等 5 秒→恢复（@ 循环刷新）
    python3 run_job.py duty      # 22:00 两个反馈群各发「6 点未反馈统计」卡（带跨运行去重标记）
    python3 run_job.py summary   # 23:00 汇总卡 @ 魏兆翔/魏兆翎/莫恩健（带跨运行去重标记）
    python3 run_job.py verify    # 自检：还原密钥 → 取飞书 token，确认链路通（不发任何卡片）
    python3 run_job.py dispatch  # 按当前时间自动分流（Actions 主入口）

所有含密钥的配置与 .env 通过环境变量 APP_SECRETS（gzip+base64 的 tar 包）在运行时还原，
绝不落库到公开仓库。duty/summary 的去重标记写回仓库 markers.json 实现跨运行持久化。
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
import tarfile
import time
import gzip

BASE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE)
CONFIG_DIR = os.path.join(BASE, "config")
DATA_DIR = os.path.join(BASE, "data")


def log(msg):
    print("[run_job %s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def decode_secrets():
    """从 APP_SECRETS 还原 config/ 与 .env（仅运行时存在，不入库）。"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    raw = os.environ.get("APP_SECRETS", "")
    if not raw:
        log("⚠ APP_SECRETS 未设置：仅当本地已存在 config/ 与 .env 时可用（开发模式）")
        return False
    try:
        blob = base64.b64decode(raw)
        with gzip.GzipFile(fileobj=io.BytesIO(blob)) as gz:
            tar_bytes = gz.read()
        with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as tf:
            tf.extractall(BASE)   # tar 内含 config/ 与 .env（相对路径）
        # 确保运行时模式
        if "FB_MODE" not in os.environ:
            os.environ["FB_MODE"] = "trial"
        log("✅ 已从 APP_SECRETS 还原 config/ 与 .env（FB_MODE=%s）" % os.environ.get("FB_MODE"))
        return True
    except Exception as e:
        log("❌ APP_SECRETS 还原失败：%s" % e)
        raise


# ---------------------------------------------------------------- 去重标记（持久化到仓库）
def _markers_path():
    return os.path.join(REPO_ROOT, "markers.json")


def load_markers():
    try:
        with open(_markers_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_markers(m):
    with open(_markers_path(), "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=1)


def push_markers():
    """把 markers.json 提交回仓库（duty/summary 跨运行去重用）。失败不致命。"""
    try:
        token = os.environ.get("GITHUB_TOKEN", "")
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        if not token or not repo:
            log("(markers) 无 GITHUB_TOKEN/REPOSITORY，跳过回写")
            return
        import subprocess
        subprocess.run(["git", "config", "user.email", "bot@github-actions.local"],
                       cwd=REPO_ROOT, check=False)
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"],
                       cwd=REPO_ROOT, check=False)
        subprocess.run(["git", "add", "markers.json"], cwd=REPO_ROOT, check=False)
        # 只在有改动时提交
        r = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=REPO_ROOT)
        if r.returncode == 0:
            return
        subprocess.run(["git", "commit", "-m", "chore: update duty/summary markers"],
                       cwd=REPO_ROOT, check=False)
        url = "https://x-access-token:%s@github.com/%s.git" % (token, repo)
        branch = os.environ.get("GITHUB_REF_NAME", "") or "main"
        subprocess.run(["git", "push", url, "HEAD:%s" % branch], cwd=REPO_ROOT, check=False)
        log("(markers) 已回写仓库")
    except Exception as e:
        log("(markers) 回写失败（非致命）：%s" % e)


# ---------------------------------------------------------------- 各任务
def do_check():
    import app as A
    A.check_and_run(reason="gha-check")


def do_refresh():
    import app as A
    import feedback_task as F
    import star_daily_task as T
    mode = os.environ.get("FB_MODE", "trial")
    wave = T.now().strftime("%Y-%m-%d %H:%M")
    F.at_wave_begin(wave)
    try:
        r2 = F.refresh_card2_at(mode=mode, sink=print, wave_key=wave)
        log("卡片2 @刷新：%s" % (r2.get("reason", "完成") if r2.get("skipped") else "完成"))
        r3 = F.refresh_card3_at(mode=mode, sink=print, wave_key=wave)
        log("卡片3 @刷新：%s" % (r3.get("reason", "完成") if r3.get("skipped") else "完成"))
    finally:
        F.at_wave_end()


def do_duty():
    import duty_check_task as D
    out = D.run_daily(sink=print)
    log("22:00 6点未反馈统计：%s" % out)
    m = load_markers()
    m["duty_date"] = time.strftime("%Y-%m-%d")
    save_markers(m)
    push_markers()


def do_summary():
    import feedback_task as F
    mode = os.environ.get("FB_MODE", "trial")
    r = F.send_summary_at_card(mode=mode, sink=print, force=False)
    log("23:00 汇总卡：%s" % r)
    m = load_markers()
    m["summary_date"] = time.strftime("%Y-%m-%d")
    save_markers(m)
    push_markers()


def do_verify():
    decode_secrets()
    import star_daily_task as T
    tok = T.get_token()
    log("✅ verify 通过：飞书 tenant_access_token 长度=%d" % len(tok or ""))
    return True


# ---------------------------------------------------------------- 自动分流
def do_dispatch():
    import star_daily_task as T
    n = T.now()
    hour, minute = n.hour, n.minute
    today = n.strftime("%Y-%m-%d")
    m = load_markers()
    duty_done = (m.get("duty_date") == today)
    sum_done = (m.get("summary_date") == today)

    if hour == 22 and not duty_done:
        log("分流 → duty（22:00 统计卡）")
        do_duty()
        return
    if hour == 23 and not sum_done:
        log("分流 → summary（23:00 汇总卡）")
        do_summary()
        return

    # 14–21 点：日期闸门检查 + 连发卡片；16–23:50：@逐条刷新
    if 14 <= hour <= 21:
        log("分流 → check（日期闸门 + 卡片 1/2/3）")
        do_check()
    if 16 <= hour <= 23 and minute <= 50:
        log("分流 → refresh（@ 循环刷新）")
        do_refresh()


def main():
    job = (sys.argv[1] if len(sys.argv) > 1 else "dispatch")
    decode_secrets()
    if job == "verify":
        return do_verify()
    if job == "check":
        return do_check()
    if job == "refresh":
        return do_refresh()
    if job == "duty":
        return do_duty()
    if job == "summary":
        return do_summary()
    if job == "dispatch":
        return do_dispatch()
    print("unknown job: %s" % job, flush=True)
    sys.exit(2)


if __name__ == "__main__":
    main()
