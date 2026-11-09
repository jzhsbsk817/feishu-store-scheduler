#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
定时任务调度台 · 常驻服务
================================
单端口 HTTP 服务：托管网页 + 内置定时调度 + 任务 API。

【一个定时任务，一次运行连发 5 张卡片】
  第 1 张卡片：星级群每日追踪汇总（4 要点纵向）              —— star_daily_task.py
  第 2 张卡片：两图并排（保持）+ 单栏「今日待反馈明细」        —— feedback_task.py
  第 3 张卡片：已反馈统计①（今日待办 + 前 10 家已反馈）        —— feedback_task.py
  第 4 张卡片：已反馈统计②（> 10 家时第 11 家起脱离，> 20 家再开③，一直分页） —— feedback_task.py
  最后一张：23:00「未反馈门店汇总」卡（@ 魏兆翔/魏兆翎/莫恩健，数字随提交自动更新到 23:59） —— feedback_task.py
  22:00 星级群不再发送任何卡片（原「未反馈统计」独立卡已删除）；但 22:00 另向「T 门店反馈收集群」与「小加盟店长沟通群」各发一张「6 点未反馈统计」卡（各 @ 各群店长，见 duty_check_task.py）；16:00–23:50 每 10 分钟把卡片 2、卡片 3 的 @店长 逐条删除→等 5 秒→恢复（群内 @ 循环刷新）
  卡片 2 从 16:00 起在最下方插入「未反馈统计（回复率截图未反馈）」@ 店长。

调度：每天 14:15 起每 15 分钟检查「看板数据日期是否 == 昨天」
      · 不相等 -> 下载 / 分析 / 卡片 / 推送等所有步骤都不执行
      · 相等且当天未成功 -> 先发第 1 张，紧跟发第 2、3 张；当天不再重复
      · 卡片发出后，每秒读取多维表格、原地刷新（不重发）

第 2 张卡片只含两张并排缩略图 + 单栏「今日待反馈明细」（按店长 @、逐渠道列中评/差评条数，门店反馈后自动取消 @ 记录）；
不含「已反馈统计」——统一放在第 3 张卡片（已反馈统计①）。
★ 智慧门店渠道（渠道名含「智慧」）的中评 / 差评由平台自动产生、无需门店回复反馈：
  识别「今日有无中差评」时直接剔除，不 @ 对应店长、也不统计它有无反馈
  （回复率截图仍按全部 26 家（不含寮步城市店）要求，不受影响）。
第 3 张卡片统计板块：只统计【已反馈】门店、不显示「已反馈✅」，每家门店一块 →
  【门店名称：】/ 回复率截图 ✅❌，中评 ✅❌（依卡 2 明细判断今日有无中评）/
  差评：删除 x 条，申诉 x 条，无法处理 x 条（按店长「差评反馈」文本关键字归类）；
  今日无中评/差评显示「— 无需」，有差评却填「无/没有」判 ❌ 未反馈差评。
已反馈门店数 > 10 家时，第 11 家起脱离到「已反馈统计②」；> 20 家再开「③」，一直分页。原「待整改」独立卡已取消：审核不过的问题直接在各门店块里 @店长。
  23:59 补漏审核：无视阈值全部重新审核一遍（当天一次）。
【星级群 22:00 群卡已删除；两个反馈群 22:00 另发「6 点未反馈统计」卡】16:00–23:50 每 10 分钟把卡片 2、卡片 3 的 @店长 删除 → 等 5 秒 → 重新填入，让群内 @ 每 10 分钟重新触发一次（仅原地 PATCH，绝不在群里发新消息）；已反馈门店从卡片 2 剔除、不再 @。
  卡片 2「回复率截图未反馈」、已反馈统计各页「审核不过」的 @ 同步参与该刷新；23:00 单独新发一张「未反馈门店汇总」@ 魏兆翔/魏兆翎/莫恩健（唯一走群发新消息之处），发出后每 10 秒原地刷新数字，23:59 定格。

回复率截图自学习判定（feedback_task.py）：只判定「今日」回复率有无达成 100%。
  版式 A 横幅页右上角「今日」两个 100%（左侧可能写 7日未获权益/已获银牌/已获金牌）；
  版式 B 消息权益页「权益指标」中下位置「今日」两个 100% + 「过去 7 天平均回复率 xxx%」。
  「过去 7 天 / 7 日」数字不参与判定（96%/94% 忽略）；今日真未达标（90%/80%）仍拒绝。
  每次审核 2~3 轮多方式 OCR（正向/二值/旋转90°），任一命中即通过，救回旋转翻拍的合规图。

启动：python3 app.py  （监听 $PORT，绑定 0.0.0.0）
"""
from __future__ import annotations

import fcntl
import json
import os
import sys
import threading
import time
import traceback

from flask import Flask, jsonify, request, send_from_directory

import star_daily_task as T
import feedback_task as F
import duty_check_task as D

BASE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(BASE, "static")
DATA_DIR = T.DATA_DIR

START_MIN = 14 * 60 + 15      # 14:15
INTERVAL_MIN = 15             # 每 15 分钟
END_MIN = 23 * 60 + 59

app = Flask(__name__, static_folder=None)
run_lock = threading.Lock()
state_lock = threading.Lock()
LOGS = []          # 第 1 张卡片 / 调度日志
FB_LOGS = []       # 第 2 张卡片 / 反馈轮询日志
MAX_LOGS = 300


# ---------------------------------------------------------------- 日志 / 状态
def log(msg):
    line = "[%s] %s" % (T.now().strftime("%H:%M:%S"), msg)
    LOGS.append(line)
    del LOGS[:-MAX_LOGS]
    print(line, flush=True)
    try:
        with open(os.path.join(DATA_DIR, "logs.json"), "w", encoding="utf-8") as f:
            json.dump(LOGS, f, ensure_ascii=False, indent=1)
    except Exception:
        pass
    return line


def fb_log(msg):
    import re
    # feedback_task 传来的行已带时间戳，避免重复添加
    line = msg if re.match(r"^\[\d{2}:\d{2}:\d{2}\]", str(msg)) else \
        "[%s] %s" % (T.now().strftime("%H:%M:%S"), msg)
    FB_LOGS.append(line)
    del FB_LOGS[:-MAX_LOGS]
    print("[T02] " + line, flush=True)
    try:
        with open(os.path.join(DATA_DIR, "feedback_logs.json"), "w", encoding="utf-8") as f:
            json.dump(FB_LOGS, f, ensure_ascii=False, indent=1)
    except Exception:
        pass
    return line


def combined_logs():
    """单任务单日志框：把两张卡片的日志按时间合并。"""
    pairs = [(l, l[1:9]) for l in LOGS]
    pairs += [("[T02] " + l, l[1:9]) for l in FB_LOGS]
    pairs.sort(key=lambda p: p[1])
    return [p[0] for p in pairs][-120:]


STATE_FILE = os.path.join(DATA_DIR, "state.json")


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(s):
    with state_lock:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=1)


def read_json(name):
    try:
        with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def write_json(name, obj):
    with open(os.path.join(DATA_DIR, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- 组合运行（同一个任务）
def run_combined(mode="live", force=False, logfn=log):
    """
    同一个定时任务的一次运行：
      日期闸门 -> 第 1 张卡片（星级汇总）-> 紧跟第 2 张卡片（中差评回馈）
    闸门不通过则下面所有步骤都不执行。
    """
    date, _ = T.fetch_board()
    target = T.yesterday()
    logfn("数据日期 = %s ｜ 目标（昨天）= %s" % (date, target))

    if not force and date != target:
        logfn("⛔ 日期闸门未通过 → 图片下载、4 要点分析、两张卡片推送等所有后续步骤均不执行")
        rec = {"ok": False, "gate": "blocked", "date": date, "target": target,
               "mode": mode, "ts": T.now().strftime("%Y-%m-%d %H:%M:%S")}
        write_json("last_check.json", rec)
        return rec

    logfn("✅ 日期闸门通过 → 编辑第 1 张卡片：星级群每日追踪汇总（已有当天卡片就原地编辑）")
    st0 = load_state()
    today = T.now().strftime("%Y-%m-%d")
    reuse1 = st0.get("card1_message_id") if st0.get("card1_date") == today else None
    r1 = T.run_once(mode=mode, force=force, log=logfn,
                    reuse_message_id=reuse1, reuse_mode=st0.get("card1_mode"))
    if not r1.get("ok"):
        rec = {"ok": False, "gate": "passed", "failed_at": "card1",
               "error": "第 1 张卡片发送失败", "date": date, "target": target,
               "mode": mode, "ts": T.now().strftime("%Y-%m-%d %H:%M:%S")}
        write_json("last_combined.json", rec)
        return rec
    card1_mid = r1.get("message_id", "")
    logfn("第 1 张卡片%s：message_id=%s"
          % ("已原地编辑" if r1.get("edited") else "已发出", card1_mid))

    logfn("→ 紧跟处理第 2 张卡片：先读取中差评明细，判断今天是否有中评 / 是否有差评")
    try:
        F.load_today_detail(refresh=True)
        logfn("中差评明细读取完成：数据日期 %s · 今日需反馈中差评 %d 家 · 全部 %d 家需回复率截图"
              % (F.BOARD_DATE, len(F.DETAIL_SHOPS), len(F.ALL_SHOPS)))
        r2 = F.send_main(mode=mode, demo=False, audited=False, sink=fb_log)
    except Exception as e:
        logfn("第 2 张卡片发送失败：%s" % e)
        rec = {"ok": False, "gate": "passed", "failed_at": "card2",
               "error": str(e), "date": date, "target": target,
               "mode": mode, "card1_message_id": card1_mid,
               "ts": T.now().strftime("%Y-%m-%d %H:%M:%S")}
        write_json("last_combined.json", rec)
        return rec
    card2_mid = r2.get("message_id", "")
    logfn("第 2 张卡片%s：message_id=%s ｜ 今日有中差评 %d 家 / 全部门店 %d 家需回复率截图"
          % ("已原地编辑" if r2.get("edited") else "已发出",
             card2_mid, r2.get("detail_shops", 0), r2.get("all_shops", 0)))
    fb_log("第 2 张卡片：两图并排（保持）+ 单栏今日待反馈明细（按渠道列条数，反馈后取消 @ 记录）")

    logfn("→ 紧跟第 2 张卡片发出「已反馈统计①」（今日待办 + 前 10 家已反馈，>10 家自动开②）")
    try:
        r3 = F.send_handoff_card(mode=mode, sink=fb_log)
    except Exception as e:
        logfn("第 3 张卡片发送失败：%s" % e)
        rec = {"ok": False, "gate": "passed", "failed_at": "card3",
               "error": str(e), "date": date, "target": target, "mode": mode,
               "card1_message_id": card1_mid, "card2_message_id": card2_mid,
               "ts": T.now().strftime("%Y-%m-%d %H:%M:%S")}
        write_json("last_combined.json", rec)
        return rec
    card3_mid = r3.get("message_id", "")
    logfn("第 3 张卡片%s：message_id=%s ｜ 已反馈 %d 家"
          % ("已原地编辑" if r3.get("edited") else "已发出",
             card3_mid, r3.get("shops", 0)))
    fb_log("第 3 张卡片紧跟第 2 张发出（不再等满 10 家）：每 10 秒原地刷新，23:59 封板删两个按键")

    rec = {
        "ok": True, "gate": "passed", "mode": mode, "date": date, "target": target,
        "ts": T.now().strftime("%Y-%m-%d %H:%M:%S"),
        "card1": {"name": "星级群每日追踪汇总", "message_id": card1_mid,
                  "target": "东莞-（莫ej）星级店长群" if mode == "live" else "莫恩健（本人私聊）"},
        "card2": {"name": "中差评和回复率回馈", "message_id": card2_mid,
                  "target": "东莞-（莫ej）星级店长群" if mode == "live" else "莫恩健（本人私聊）",
                  "detail_shops": r2.get("detail_shops", 0), "all_shops": r2.get("all_shops", 0)},
        "card3": {"name": "已反馈统计①（今日待办 + 前 10 家已反馈；问题是就地 @店长）",
                  "message_id": card3_mid,
                  "target": "东莞-（莫ej）星级店长群" if mode == "live" else "莫恩健（本人私聊）",
                  "note": "紧跟第 2 张卡发出；每 10 秒原地刷新；已反馈 > 10 家时第 11 家起自动开「已反馈统计②」，逐页刷新；23:59 封板删按键",
                  "edited": bool(r3.get("edited"))},
    }
    write_json("last_combined.json", rec)
    return rec


def _mark_done_from_group(st, target, detail):
    """群消息识别到「今天已发过」→ 回写本地判重，避免后续反复读群、更避免重复发。"""
    st["last_live_date"] = target
    st["last_success_date"] = target
    st["last_success_mode"] = "live"
    st["last_success_ts"] = T.now().strftime("%Y-%m-%d %H:%M:%S")
    st["group_check_note"] = detail
    save_state(st)


def _with_cross_process_lock(fn):
    """跨进程互斥：沙箱恢复时可能有多个 app.py 同时被拉起，只能有一个去发卡。

    拿不到锁直接返回 None（调用方跳过本次），绝不与另一个进程并发发卡。
    """
    fp = open(os.path.join(DATA_DIR, "run.lock"), "a+")
    try:
        fcntl.flock(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except Exception:
        fp.close()
        return None
    try:
        return fn()
    finally:
        try:
            fcntl.flock(fp, fcntl.LOCK_UN)
        finally:
            fp.close()


def check_and_run(reason="定时检查"):
    """一次定时 / 补跑检查。

    防重复发的四道关（按用户要求，群消息识别是硬性一步）：
      ① 每次检查都真实读一次群消息，识别今天群里有没有本任务的卡片；
      ② 本地判重（last_live_date）与群识别结果取「或」，任一命中都不发；
      ③ 群消息读取失败（结果未知）→ 保守跳过，下一拍重试，绝不盲目补发；
      ④ 真正发卡前：跨进程文件锁 + 二次群识别 + 二次本地判重。
    只有群里今天确实没有卡片、且本地也判定未执行、且在 14:15–23:59 窗口内，才补发。
    """
    st = load_state()
    target = T.yesterday()
    n = T.now()
    mins = n.hour * 60 + n.minute
    local_done = bool(
        st.get("last_live_date") == target or (
            st.get("last_success_date") == target and st.get("last_success_mode") == "live"))

    # ① 群消息识别（每次检查都读一次，权威依据）
    sent, detail = F.group_task_cards_sent_today()
    log("%s：群消息识别 → %s" % (reason, detail))

    # ② 任一判重命中 → 绝不补发
    if sent is True or local_done:
        why = "群里今日已有任务卡片" if sent is True else "本地判重已命中"
        if sent is True and not local_done:
            _mark_done_from_group(st, target, detail)
            log("%s：本地判重缺失，已按群消息回写判重" % reason)
        log("%s：%s → 不补发（绝不重复发卡）" % (reason, why))
        return {"skipped": "already_sent"}

    # ③ 群消息读取失败 → 结果未知，保守跳过
    if sent is None:
        log("%s：群消息结果未知 → 保守跳过，下一拍（15 分钟后）重试" % reason)
        return {"skipped": "group_unknown"}

    # ④ 发卡时间窗口（凌晨/上午恢复不误发）
    if not (START_MIN <= mins <= END_MIN):
        log("%s：当前 %s 不在 14:15–23:59 发卡窗口 → 跳过" % (reason, n.strftime("%H:%M")))
        return {"skipped": "outside_window"}

    def _do_send():
        with run_lock:
            # 二次群识别：防止刚有另一个进程/手动操作发完卡
            sent2, detail2 = F.group_task_cards_sent_today()
            if sent2 is not False:
                log("%s：二次群识别=%s → 放弃发卡（保守）" % (reason, detail2))
                return {"skipped": "second_group_check"}
            # 二次本地判重
            st2 = load_state()
            if st2.get("last_live_date") == target:
                log("%s：二次本地判重已命中 → 放弃发卡" % reason)
                return {"skipped": "second_local_dedup"}

            log("%s：群消息确认今天未执行任务 → 触发【同一个任务】正式运行" % reason)
            rec = run_combined("live", force=False, logfn=log)
            if not rec.get("ok"):
                log("%s：本次运行未成功（gate=%s failed_at=%s），不写判重，下一拍重试"
                    % (reason, rec.get("gate"), rec.get("failed_at", "")))
                return {"ok": False, "rec": rec}
            st3 = load_state()
            st3["last_success_date"] = rec["date"]
            st3["last_success_mode"] = "live"
            st3["last_live_date"] = rec["date"]
            st3["last_success_ts"] = rec["ts"]
            st3["last_message_id"] = rec["card1"]["message_id"]
            st3["last_card2_message_id"] = rec["card2"]["message_id"]
            st3["card1_message_id"] = rec["card1"]["message_id"]
            st3["card1_date"] = T.now().strftime("%Y-%m-%d")
            st3["card1_mode"] = "live"
            save_state(st3)
            log("✅ 补发完成（群里此前无今日卡片），今日不再重复")
            return {"ok": True, "rec": rec}

    out = _with_cross_process_lock(_do_send)
    if out is None:
        log("%s：另一个进程正在发卡（拿不到跨进程锁）→ 跳过，避免重复发" % reason)
        return {"skipped": "locked"}
    return out


def light_gate_check():
    """启动时只读取日期，不下载图片、不分析、不发任何消息。"""
    try:
        date, _ = T.fetch_board()
        target = T.yesterday()
        rec = {"ok": False, "gate": "passed" if date == target else "blocked",
               "date": date, "target": target, "mode": "check",
               "ts": T.now().strftime("%Y-%m-%d %H:%M:%S")}
        write_json("last_check.json", rec)
    except Exception:
        pass


def internal_keepalive_loop():
    """进程内自保活：每 30 秒产生一次真实活动，降低沙箱因长时间空闲被回收的概率。

    只写心跳文件 + 打一次本地 /api/heartbeat，不发任何群消息、不改业务状态。
    与外部的 keepalive.sh / ensure_service.sh 是互相独立的多道保活措施。
    """
    import urllib.request
    while True:
        try:
            with open(os.path.join(DATA_DIR, "heartbeat.json"), "w", encoding="utf-8") as f:
                json.dump({"ts": T.now().strftime("%Y-%m-%d %H:%M:%S"),
                           "pid": os.getpid()}, f, ensure_ascii=False)
            try:
                urllib.request.urlopen(
                    "http://127.0.0.1:%d/api/heartbeat"
                    % int(os.environ.get("PORT", "3000")), timeout=5).read()
            except Exception:
                pass
        except Exception:
            pass
        time.sleep(30)


def scheduler_loop():
    light_gate_check()
    # 启动即补跑：沙箱休眠打断后服务重新拉起，不必等下一个 15 分钟整点。
    # check_and_run 会先真实读一次群消息识别，群里今天已发过就绝不补发。
    try:
        time.sleep(3)
        check_and_run(reason="启动补跑检查")
    except Exception:
        log("启动补跑检查异常：" + traceback.format_exc(limit=2).replace("\n", " | "))
    while True:
        try:
            n = T.now()
            mins = n.hour * 60 + n.minute
            key = n.strftime("%Y-%m-%d %H:%M")
            # 14:15 起每 15 分钟检查日期闸门，通过后连发两张卡片
            if START_MIN <= mins <= END_MIN and (mins - START_MIN) % INTERVAL_MIN == 0 and n.second < 25:
                st = load_state()
                if st.get("last_check_key") != key:
                    st["last_check_key"] = key
                    st["last_check_ts"] = n.strftime("%Y-%m-%d %H:%M:%S")
                    save_state(st)
                    check_and_run(reason="定时检查")
            # 22:00：分群「6 点未反馈统计」卡（沿用群内 11-06 模板）。
            # 各发各的群：T 门店发到「T 门店反馈收集群」、M 门店发到「小加盟店长沟通群」，
            # 各自只 @ 本群店长。四段：今日未发 / 近3天持续未发 / 近7天 top3 / 当天未测油。
            # 按业务日期去重，每天只发一次；发送失败时同一分钟内继续重试。
            if n.hour == 22 and n.minute == 0 and n.second < 50:
                stx = load_state()
                dstr = n.strftime("%Y-%m-%d")
                if stx.get("duty_stat_date") != dstr:
                    try:
                        r6 = D.run_daily(sink=fb_log)
                        fb_log("22:00 6点未反馈统计：%s" % r6)
                        if r6.get("ok"):
                            stx["duty_stat_date"] = dstr
                            stx["duty_stat_ts"] = n.strftime("%Y-%m-%d %H:%M:%S")
                            save_state(stx)
                    except Exception as e:
                        fb_log("22:00 6点未反馈统计失败（下拍重试）：%s" % e)
            # 16:00–23:50：每 10 分钟把卡片 2、卡片 3 的 @店长【逐条】刷新。
            # 每一家：删掉这一家 @ 生效 → 等 5 秒 → 恢复 @ 生效 → 再轮到下一家，
            # 逐条走完全部待 @ 门店；仅原地 PATCH，绝不新发消息；23:59 封板后自动停止。
            # 【2026-11-09 用户要求】由原「一次性全删→5秒→全恢复」改为逐条，起点由 20:00 改为 16:00。
            if 16 <= n.hour <= 23 and n.minute % 10 == 0 and n.second < 25:
                wave = n.strftime("%Y-%m-%d %H:%M")
                st2 = load_state()
                mode0 = st2.get("main_mode") or os.environ.get("FB_MODE", "trial")
                if (st2.get("at_refresh_last_wave") != wave
                        or st2.get("card3_at_last_wave") != wave):
                    F.at_wave_begin(wave)     # 期间暂停 poll_once 重建，保住逐条中间态
                    try:
                        try:
                            r = F.refresh_card2_at(mode=mode0, sink=fb_log, wave_key=wave)
                            fb_log("波次 %s：卡片 2 @逐条刷新 %s（%d 家 / %d 轮，删除@%s / 恢复@%s）"
                                   % (wave,
                                      "跳过：" + str(r.get("reason", "")) if r.get("skipped") else "完成",
                                      r.get("at_count", 0), r.get("steps", 0),
                                      "✅" if r.get("off_ok") else "❌",
                                      "✅" if r.get("on_ok") else "❌"))
                        except Exception as e:
                            fb_log("波次 %s 卡片 2 @逐条刷新失败：%s" % (wave, e))
                        try:
                            r3 = F.refresh_card3_at(mode=mode0, sink=fb_log, wave_key=wave)
                            fb_log("波次 %s：卡片 3 @逐条刷新 %s（%d 处 / %d 轮，删除@%s / 恢复@%s）"
                                   % (wave,
                                      "跳过：" + str(r3.get("reason", "")) if r3.get("skipped") else "完成",
                                      r3.get("at_count", 0), r3.get("steps", 0),
                                      "✅" if r3.get("off_ok") else "❌",
                                      "✅" if r3.get("on_ok") else "❌"))
                        except Exception as e:
                            fb_log("波次 %s 卡片 3 @逐条刷新失败：%s" % (wave, e))
                    finally:
                        F.at_wave_end()
                # 23:00：新发一张汇总卡 @ 魏兆翔/魏兆翎/莫恩健，写明「以上未反馈门店请查收」
                # （唯一例外走群发新消息；当天按日期去重，只发一次）
                if n.hour == 23 and n.minute == 0 and st2.get("summary_at_date") != now().strftime("%Y-%m-%d"):
                    try:
                        r5 = F.send_summary_at_card(mode=mode0, sink=fb_log)
                        fb_log("23:00 汇总卡：%s" % r5)
                    except Exception as e:
                        fb_log("23:00 汇总卡发送失败（下个节拍重试）：%s" % e)
        except Exception:
            log("调度异常：" + traceback.format_exc(limit=2).replace("\n", " | "))
        time.sleep(15)


def feedback_poll_loop():
    """固定节拍轮询：统计每 10 秒原地刷新一次卡片，审核每 15 秒执行一次（均不重发）。"""
    last_err = 0
    tick = F.SCHED.get("poll_tick_seconds", 2)
    while True:
        t0 = time.time()
        try:
            st = F.load_state()
            # 演示态卡片不被真实空数据覆盖；正式运行（demo=False）才轮询
            if st.get("main_message_id") and not st.get("demo"):
                out = F.poll_once(sink=fb_log)
                if out.get("sig_changed") and out.get("refreshed"):
                    fb_log("检测到新提交 → 卡片已原地刷新：%d 家已反馈%s"
                           % (out.get("shops", 0), "（已重新审核）" if out.get("audited") else ""))
        except Exception as e:
            ts = time.time()
            if ts - last_err > 60:
                fb_log("轮询异常：" + str(e)[:120])
                last_err = ts
        # 按固定节拍休眠（把本次执行耗时算进去），避免周期被网络耗时拖长
        time.sleep(max(0.5, tick - (time.time() - t0)))


# ---------------------------------------------------------------- 路由
@app.after_request
def cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return resp


@app.route("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.route("/static/<path:p>")
def assets(p):
    return send_from_directory(STATIC, p)


@app.route("/midbad.png")
def midbad_png():
    """网页端预览：中差评明细截图（自动取最新日期文件）。"""
    import glob
    cand = sorted(glob.glob(os.path.join(DATA_DIR, "中差评明细_*.png")))
    if cand:
        return send_from_directory(DATA_DIR, os.path.basename(cand[-1]))
    return "", 404


@app.route("/star.png")
def star_png():
    """网页端预览：顾客满意明细截图（自动取最新日期文件）。"""
    import glob
    cand = sorted(glob.glob(os.path.join(DATA_DIR, "星级明细_*.png")))
    if cand:
        return send_from_directory(DATA_DIR, os.path.basename(cand[-1]))
    return "", 404


@app.route("/health")
def health():
    return jsonify({"ok": True, "service": "star-daily-scheduler", "time": T.now().isoformat()})


@app.route("/api/catchup", methods=["GET", "POST"])
def api_catchup():
    """外部 / 手动触发一次补发检查：先真实读群消息识别，群里今天已发过绝不补发。

    供云端定时器、保活守护或人工核验调用；返回值里 result.skipped 说明为何没发。
    """
    try:
        out = check_and_run(reason="外部补发检查")
        return jsonify({"ok": True, "result": out,
                        "now": T.now().strftime("%Y-%m-%d %H:%M:%S")})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/heartbeat")
def api_heartbeat():
    """保活探活端点：只返回时间与 pid，不触发任何业务动作。"""
    return jsonify({"ok": True, "pid": os.getpid(),
                    "now": T.now().strftime("%Y-%m-%d %H:%M:%S")})


@app.route("/api/status")
def api_status():
    st = load_state()
    chk = read_json("last_check.json") or {}
    result = read_json("last_result.json")
    combined = read_json("last_combined.json")
    return jsonify({
        "service": "online",
        "now": T.now().strftime("%Y-%m-%d %H:%M:%S"),
        "task": {
            "id": "01",
            "name": "星级群每日追踪汇总",
            "card2_name": "中差评和回复率回馈",
            "note": "同一个定时任务 · 群卡（卡1 四要点纵向、卡2 两图并排+单栏待反馈明细、卡3 已反馈统计①、卡4 已反馈统计②（>10 家脱离）、最后一张 23:00 汇总卡；星级群 22:00 未反馈卡已停用；另 22:00 向两个反馈群各发「6 点未反馈统计」）+ 16:00–23:50 每 10 分钟把卡片 2、卡片 3 的 @店长 删除→等 5 秒→重新填入（群内 @ 循环刷新，仅原地 PATCH 绝不在群里发新消息；卡片 3 已反馈门店从卡片 2 剔除不再 @）；23:00 另新发一张汇总卡 @ 魏兆翔/魏兆翎/莫恩健",
            "live_target": "东莞-（莫ej）星级店长群",
            "trial_target": "莫恩健（本人私聊）",
            "cards": [
                {"no": 1, "name": "星级汇总 4 要点（纵向排列，不含图）", "time": "14:15 起每 15 分钟（闸门通过后）"},
                {"no": 2, "name": "顾客满意 + 中差评明细（并排两图保持）+ 单栏今日待反馈明细（@店长：渠道名称 中评 x 条 / 差评 x 条，反馈后取消 @ 记录）；不含已反馈统计", "time": "紧跟第 1 张卡片发出"},
                {"no": 3, "name": "已反馈统计①：今日待办 + 前 10 家已反馈（每店一行「昨日中评/差评 x 条 · 回复率截图 · 中评」；差评反馈单独一行，0 条项不显示；审核不过当场 @店长 标红原因）", "time": "紧跟第 2 张卡片发出"},
                {"no": 4, "name": "已反馈统计②：已反馈 > 10 家时第 11-20 家脱离到本卡；> 20 家再开③，一直分页", "time": "已反馈门店数 > 10 家自动触发"},
                {"no": 5, "name": "【已停用·星级群】22:00 未反馈统计群卡（改由 16:00 起卡片 2 @逐条刷新承担）", "time": "不再发送"},
                {"no": 6, "name": "卡片 2 @店长 逐条循环刷新（逐一：删 @ 生效 → 等 5 秒 → 恢复 @ 生效（逐家循环），仅原地 PATCH、不进群、不新发消息）", "time": "16:00–23:50 每 10 分钟一波"},
                {"no": 7, "name": "已反馈统计①/②… 的 @店长 逐条循环刷新（审核不过的 @ 逐条删除→等 5 秒→恢复，覆盖所有分页卡）", "time": "16:00–23:50 每 10 分钟一波"},
                {"no": 8, "name": "23:00 汇总卡（新发一条群消息，@ 魏兆翔/魏兆翎/莫恩健，列明「回复率截图未反馈 X 家 / 待整改 X 家 / 中差评未反馈 X 家」，详情看上方 2、3 卡片）", "time": "23:00 一次"},
                {"no": 9, "name": "22:00「6 点未反馈统计」分群卡：T 门店反馈收集群 / 小加盟店长沟通群各一张，各 @ 本群店长；四段＝今日未发 / 近3天持续未发 / 近7天 top3 / 当天未测油", "time": "22:00 一次"},
            ],
        },
        "schedule": {
            "start": "14:15",
            "interval_min": INTERVAL_MIN,
            "timezone": "Asia/Shanghai",
            "rule": "数据日期必须等于昨天，否则下面所有步骤都不执行",
            "next_check_note": "14:15 起每 15 分钟检查一次",
            "last_check_ts": st.get("last_check_ts", ""),
            "last_success_date": st.get("last_success_date", ""),
            "last_success_ts": st.get("last_success_ts", ""),
        },
        "gate": {
            "data_date": chk.get("date", ""),
            "target_date": chk.get("target", T.yesterday()),
            "passed": bool(chk.get("date") == T.yesterday()),
            "checked_at": chk.get("ts", ""),
        },
        "last_result": result,          # 第 1 张卡片 4 要点
        "last_combined": combined,      # 两张卡片连发记录
        "logs": LOGS[-60:],
        "feedback_logs": FB_LOGS[-60:],
        "combined_logs": combined_logs(),
        "feedback": _feedback_status(),  # 第 2 张卡片两区块统计
    })


def _feedback_status():
    """第 2 张卡片状态：两区块统计（容错：服务未就绪时也返回结构）。"""
    try:
        base = F.status()
        base.update({
            "poll_seconds": F.SCHED.get("poll_seconds", 1),
            "audit_min_records": F.SCHED.get("audit_min_records", 5),
            "summary_time": "%02d:%02d" % (F.SCHED["summary_hour"], F.SCHED["summary_minute"]),
            "live_target": F.LIVE["name"],
            "trial_target": F.TRIAL["name"],
        })
        return base
    except Exception as e:
        return {"error": str(e)[:120], "rows": [], "midbad_rows": [], "rate_rows": [],
                "detail_shops": len(F.DETAIL_SHOPS), "all_shops": len(F.ALL_SHOPS)}


@app.route("/api/check", methods=["GET", "POST"])
def api_check():
    """只做日期闸门检查，不执行下载/分析/发送。"""
    try:
        date, _ = T.fetch_board()
        target = T.yesterday()
        passed = date == target
        log("手动检查闸门：数据日期 %s ｜ 目标 %s ｜ %s"
            % (date, target, "通过" if passed else "未通过，所有后续步骤不执行"))
        return jsonify({"ok": True, "date": date, "target": target, "passed": passed})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def _do_run(mode, force):
    """统一运行入口：同一个任务处理两张卡片（当天已有卡片 → 只原地编辑）。"""
    if not run_lock.acquire(blocking=False):
        return jsonify({"ok": False, "error": "已有任务正在运行，请稍候"}), 409
    try:
        log("手动触发【同一个任务】：mode=%s force=%s（已有当天卡片则只编辑，不发新消息）" % (mode, force))
        rec = run_combined(mode=mode, force=force, logfn=log)
        if rec.get("ok"):
            st = load_state()
            if mode == "live":
                # 只有正式运行才写 live 闸门状态，试运行不再影响定时任务判断
                st["last_success_date"] = rec["date"]
                st["last_success_mode"] = "live"
                st["last_live_date"] = rec["date"]
                st["last_success_ts"] = rec["ts"]
                st["last_message_id"] = rec["card1"]["message_id"]
                st["last_card2_message_id"] = rec["card2"]["message_id"]
                st["card1_message_id"] = rec["card1"]["message_id"]
                st["card1_date"] = T.now().strftime("%Y-%m-%d")
                st["card1_mode"] = "live"
            else:
                st["last_trial_ts"] = rec["ts"]
            save_state(st)
            # 试运行：卡 1 / 卡 2 / 卡 3 已由 run_combined 连发；
            # 额外预览 23:00 汇总卡（仅本人私聊，不 @ 真实店长、不写状态）。
            # 【2026-11-08】私聊提醒卡已彻底移除，不再预览私聊模板。
            if mode == "trial":
                try:
                    r5 = F.send_summary_at_card(mode="trial", sink=fb_log, force=True)
                    rec["card5"] = {
                        "name": "23:00 汇总卡（@ 魏兆翔/魏兆翎/莫恩健，列明回复率截图未反馈 / 待整改 / 中差评未反馈三项目家数）",
                        "message_id": r5.get("message_id", ""),
                        "target": "莫恩健（本人私聊预览）",
                        "template_preview": True,
                        "note": "仅模板预览；正式运行时 23:00 自动发到群并 @ 三人",
                    }
                    fb_log("试运行：23:00 汇总卡模板已发到本人私聊")
                except Exception as e:
                    rec["card5_error"] = str(e)
                    fb_log("试运行 汇总卡预览失败：" + str(e))
        return jsonify(rec)
    except Exception as e:
        log("运行失败：" + str(e))
        return jsonify({"ok": False, "error": str(e),
                        "trace": traceback.format_exc(limit=3)}), 500
    finally:
        run_lock.release()


@app.route("/api/run/<mode>", methods=["POST"])
def api_run(mode):
    """兼容旧入口：同样走「连发两张卡片」。"""
    if mode not in ("live", "trial"):
        return jsonify({"ok": False, "error": "mode 只能是 live 或 trial"}), 400
    body = request.get_json(silent=True) or {}
    force = request.args.get("force") == "1" or body.get("force") is True
    return _do_run(mode, force)


@app.route("/api/run-task/<mode>", methods=["POST"])
def api_run_task(mode):
    """网页主按钮：同一个定时任务，连发两张卡片。"""
    if mode not in ("live", "trial"):
        return jsonify({"ok": False, "error": "mode 只能是 live 或 trial"}), 400
    body = request.get_json(silent=True) or {}
    force = request.args.get("force") == "1" or body.get("force") is True
    return _do_run(mode, force)


# ---------------------------------------------------------------- 第 2 张卡片 API（调试/手动）
@app.route("/api/feedback/status")
def api_fb_status():
    return jsonify({"ok": True, "feedback": _feedback_status(), "logs": FB_LOGS[-60:]})


@app.route("/api/feedback/send-main", methods=["POST"])
def api_fb_send_main():
    """单独发/重发第 2 张卡片（调试用）。"""
    if not run_lock.acquire(blocking=False):
        return jsonify({"ok": False, "error": "已有任务正在运行"}), 409
    try:
        body = request.get_json(silent=True) or {}
        mode = body.get("mode", "trial")
        demo = body.get("demo", True)
        rec = F.send_main(mode=mode, demo=demo, sink=fb_log)
        fb_log("第 2 张卡片已发送：mode=%s demo=%s" % (mode, demo))
        return jsonify(rec)
    except Exception as e:
        fb_log("发送失败：" + str(e))
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        run_lock.release()


@app.route("/api/feedback/poll", methods=["POST"])
def api_fb_poll():
    """手动触发一次：读记录 → 重算两区块 → 原地刷新卡片。"""
    try:
        rec = F.poll_once(sink=fb_log, force=True)
        fb_log("手动轮询：%d 家已反馈，审核=%s" % (rec.get("shops", 0), rec.get("audited")))
        return jsonify(rec)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/feedback/summary", methods=["POST"])
def api_fb_summary():
    """【已停用】22:00「今日未反馈统计」群卡（2026-11-08 起不再发送）。

    提醒改由 16:00–23:50 每 10 分钟把卡片 2/3 的 @店长 逐条删除→等 5 秒→恢复（@ 循环刷新）；
    23:00 另新发一条汇总卡 @ 魏兆翔/魏兆翎/莫恩健（见 send_summary_at_card）。
    """
    return jsonify({"ok": False, "skipped": True,
                    "reason": "【星级群】22:00 未反馈群卡已停用（两个反馈群 22:00 另发 6 点未反馈统计卡）：改为 16:00–23:50 每 10 分钟把卡片 2/3 的 @店长 逐条删除→等 5 秒→恢复（@ 循环刷新）；23:00 另新发汇总卡 @ 魏兆翔/魏兆翎/莫恩健"}), 200


@app.route("/api/feedback/summary-preview", methods=["POST"])
def api_fb_summary_preview():
    """预览 23:00 汇总卡（trial 模式只发本人私聊，不写状态、不 @ 真实店长）。

    body: {mode: "live"|"trial", force: true|false}
    """
    if not run_lock.acquire(blocking=False):
        return jsonify({"ok": False, "error": "已有任务正在运行"}), 409
    try:
        body = request.get_json(silent=True) or {}
        mode = body.get("mode", "trial")
        force = body.get("force") is True
        rec = F.send_summary_at_card(mode=mode, sink=fb_log, force=force)
        return jsonify(rec)
    except Exception as e:
        fb_log("汇总卡预览失败：" + str(e))
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        run_lock.release()


@app.route("/api/logs/clear", methods=["POST"])
def api_logs_clear():
    LOGS[:] = []
    FB_LOGS[:] = []
    write_json("logs.json", [])
    write_json("feedback_logs.json", [])
    return jsonify({"ok": True})


@app.route("/api/feedback/logs/clear", methods=["POST"])
def api_fb_logs_clear():
    FB_LOGS[:] = []
    return jsonify({"ok": True})


_INSTANCE_LOCK_FP = None


def acquire_instance_lock():
    """进程级单实例锁：沙箱恢复时可能被多道保活同时拉起，只留一个调度进程。

    拿不到锁的进程直接退出（不占端口、不跑调度、不发卡），避免两个进程并发补发。
    """
    global _INSTANCE_LOCK_FP
    fp = open(os.path.join(DATA_DIR, "app.lock"), "a+")
    try:
        fcntl.flock(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except Exception:
        fp.close()
        return False
    _INSTANCE_LOCK_FP = fp        # 持有到进程结束，锁随进程释放
    return True


if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    if not acquire_instance_lock():
        print("[启动] 已有 app.py 实例持有 app.lock，本进程退出（防止双进程重复发卡）")
        sys.exit(0)
    threading.Thread(target=scheduler_loop, daemon=True).start()
    threading.Thread(target=feedback_poll_loop, daemon=True).start()
    threading.Thread(target=internal_keepalive_loop, daemon=True).start()
    log("服务启动：【同一个定时任务】已装载；启动即做群消息识别式补跑，14:15 起每 15 分钟检查日期闸门")
    fb_log("服务启动：卡 2 两图并排 + 单栏待反馈明细；星级群 22:00 群卡已停用（两个反馈群 22:00 各发 6 点未反馈统计卡）；16:00–23:50 每 10 分钟把卡片 2/3 的 @店长 逐条删除→等 5 秒→恢复@（@ 循环刷新）；私聊提醒卡已彻底移除")
    port = int(os.environ.get("PORT", "3000"))
    app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=False)
