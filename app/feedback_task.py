#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
定时任务「星级群每日追踪汇总」· 卡片 2 / 3 / 22:00 未反馈统计
================================================================
本任务与「星级群每日追踪汇总」是【同一个定时任务】，一次运行连发 5 张卡片：

  第 1 张卡片：星级群每日追踪汇总（4 要点纵向）              -> star_daily_task.py
  第 2 张卡片：两图并排（保持）+ 单栏「今日待反馈明细」        -> 本文件
  第 3 张卡片：今日待办 / 每日反馈统计 / 待整改 + 重交键       -> 本文件
  第 4 张卡片：已反馈 > 12 家时「待整改」分离（重交键跟随）   -> 本文件
  第 5 张卡片：22:00 两段式「今日未反馈统计」+ 反馈提交键     -> 本文件

【第 2 张卡片】两图保持并排，下方单栏「今日待反馈明细」：
  · 每个店长 @ 一次，逐渠道列「渠道名称 中评 x 条 / 差评 x 条」，多渠道换行缩进对齐
  · 门店反馈后该店长的 @ 记录自动取消（明细动态收缩、原地刷新）
  · 渠道明细已剔除含「智慧」的渠道（平台自动产生、无需门店反馈）
  · 不含「每日反馈统计」与「待整改」——这两块统一在第 3 张卡片

【第 3 张卡片 · 每日反馈统计】只统计【已反馈】门店，不显示「已反馈✅」：
  · 每家门店一块：
      【门店名称：xxx店】
      回复率截图 ✅/❌，中评 ✅/❌（依卡 2 明细判断今日有无中评；无中评 → — 无需）
      差评：删除 x 条，申诉 x 条，无法处理 x 条
  · 差评按店长填写的「差评反馈」文本关键字归类：
      删除 / 已删除 / 撤销… → 删除；已审批 / 申诉中 / 申诉掉 / 申诉… → 申诉；
      无 / 没有 / 为空 → 不统计（今日有差评却填「无」判 ❌ 未反馈差评）；其他 → 无法处理
  · 全部 26 家（不含寮步城市店）都要反馈「回复率截图」；任一 ❌ @店长补交，补交立即重算改判
  · 【未反馈口径 2026-11-08】"未反馈" = 未上传回复率截图；店长一提交截图即视为已反馈、
    自动移出"未反馈"名单（自动改判）；已提交但不达 100% 归「待整改」@店长整改，
    不在"未反馈"名单重复 @。以下所有"回复率未反馈"均按此口径（rate_files==0）。
  · 23:59 补漏审核：无视阈值全部重新审核一遍（当天一次）

【22:00 未反馈统计】两段式、按店长归并、只 @ 店长不列门店：
  ① 中差评未反馈名单：括号写明中评 / 差评 / 回复率里具体哪几项没反馈（含回复率）
  ② 回复率截图未反馈名单：只 @ 店长；① 已统计过回复率的店长不再二次列出

【回复率截图 · 自学习判定（OCR）】只判定「今日」回复率有无达成 100%
  · 两种合规版式：
      A 横幅页：右上角「今日」两个 100%（左侧可能写「7日未获权益 / 已获银牌 / 已获金牌」）
      B 消息权益页：中下「权益指标」，「今日」两个 100% + 「过去 7 天平均回复率 xxx%」
  · 「过去 7 天平均回复率 / 7 日权益」的数字不参与判定、不拉低结论（96% / 94% 忽略）；
    今日真未达标（如 90% / 80%）仍拒绝。
  · 每次审核对同一张截图做 2~3 轮多方式识别（正向灰度 → 正向二值稀疏 → 旋转90°），
    任一命中「今日两个 100%」即通过，救回旋转 90° 翻拍 / 模糊的合规截图。
  · 判定结果按 file_token 缓存并带规则版本 OCR_VER / 版式 pattern / 审核轮次，
    重交新图自动重新识别；规则升级时旧版「不合格」结论自动重判，不误杀合规图。

【第 3 张卡片 · 22:00】「今日未反馈统计」两段式（按店长归并）
    ① 中差评未反馈名单：直接 @ 店长，统计他今天有无中差评、哪个没反馈就写哪个
       （中评 / 差评 / 回复率 三项里没反馈的项），三项全部没反馈写「均未反馈」；
       同一店长只 @ 一次，回复率也一并统计进来。
    ② 回复率截图未反馈名单：只 @ 店长、不加标注；① 里已统计过回复率的店长不再二次列出。
    数据仍来自 judge() 实时判定，补交后下一拍自动收缩 / 自动改判。

第 2 张卡片两个按键【上下两行】摆放，不挤同一行，每个按键上方有文字说明，手机端能看清按键文字。
每秒读取多维表格，卡片用 im.messages.patch 原地刷新（不重发）。

凭证沿用 star_daily_task 的 .env（tenant_access_token），不依赖 lark-cli，发布后可直接跑。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import random
import threading
import time
import urllib.request
import urllib.error
from collections import OrderedDict
from datetime import datetime

import star_daily_task as S

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(BASE, "config")
DATA_DIR = S.DATA_DIR

CFG = json.load(open(os.path.join(CONFIG_DIR, "feedback_config.json"), encoding="utf-8"))
BT = CFG["bitable"]
BOARD = CFG["board"]
LIVE = CFG["live"]
TRIAL = CFG["trial"]
SCHED = CFG["schedule"]

# 【2026-11-09 用户要求】@ 逐条刷新波：期间禁止 poll_once 重建卡片，
# 否则「删掉某一条 @ 生效」的中间态会被 10 秒轮询立刻覆盖回去。
_AT_WAVE = {"active": False, "wave": ""}


def at_wave_begin(wave=""):
    _AT_WAVE["active"] = True
    _AT_WAVE["wave"] = wave


def at_wave_end():
    _AT_WAVE["active"] = False


def _at_wave_active():
    return bool(_AT_WAVE["active"])

OPENID2STORE = json.load(open(os.path.join(CONFIG_DIR, "openid_to_store.json"), encoding="utf-8"))
MANAGER = json.load(open(os.path.join(CONFIG_DIR, "manager_openids.json"), encoding="utf-8"))
STORE_MAP = json.load(open(os.path.join(CONFIG_DIR, "store_mapping.json"), encoding="utf-8"))

# 【2026-11-09 用户要求】寮步城市店（东莞寮步城市学院店）整体不参与统计：
# 中差评未反馈、回复率未反馈、已反馈统计、汇总卡、网页数据一律不计入。
# 用关键字匹配，兼容全名 / 短名 / 看板简称（「东莞寮步城市学院店」「寮步城市店」）。
IGNORE_SHOP_KEYWORD = "寮步城市"


def is_ignored_shop(name):
    return IGNORE_SHOP_KEYWORD in str(name or "")


ALL_SHOPS = [m["门店名称"] for m in STORE_MAP
             if not is_ignored_shop(m["门店名称"])]             # 参与统计的门店（已剔除寮步城市店）
_STATIC_DETAIL = json.load(open(os.path.join(CONFIG_DIR, "midbad_shops.json"), encoding="utf-8"))
DETAIL_FALLBACK = _STATIC_DETAIL.get("shop_review_stat", {})    # 离线兜底快照（2026-11-05）

STATE_FILE = os.path.join(DATA_DIR, "feedback_state.json")
DETAIL_CACHE_FILE = os.path.join(DATA_DIR, "midbad_today.json")

# 今日群内卡片 message_id（仅当天有效）。
# 设计：第 1 张（星级汇总）为一次性发送，从第 2 张起由轮询 PATCH 原地更新（不重发）；
# 绝不调用发送接口发新卡片消息。统计 / 改判 / 审核（含 23:59 补漏全审）/ @店长照常运行。
# 原「锁定集合」已移除：用户要求『不要发新卡片、其余流程恢复正常运行』→ 第 2 张卡随反馈实时刷新。
CARD_VER = "v14-2026-11-09"   # 卡片结构版本：改版后首次轮询会原地刷新一次
# 新链路（① 分析 / ② 两图并排+单栏待反馈明细+16:00回复率未反馈 / ③ 待办统计整改 /
# ④ 待整改分离 / 最后一张为 23:00 汇总卡）生效日期。
# 【2026-11-09】原 22:00 的「未反馈统计」独立卡已删除，不再发送任何卡片⑤。
# 早于该日期的卡片仍按老链路跑完当天，不会被中途改版。
NEW_FLOW_FROM = "2026-11-08"
# 卡片 3「已反馈门店数」超过该阈值后，把「待整改」从卡片 3 分离成独立卡片 ④。
RECTIFY_SPLIT_THRESHOLD = 12
LOCKED_TODAY_CARD_IDS = {
    "om_x100b61d8ec1964acc08c2cebfbbfe13",  # 群内第1张：一次性发送，轮询不触碰
    "om_x100b61d8242b44a4df07927228b83a5",  # 同日另一批次群卡 id（保险）
    "om_x100b61d825da88a4c3cd61da67477e5",  # 同日另一批次群卡 id（保险）
}

# 「智慧门店」等渠道的中评 / 差评由平台自动产生，不需要门店回复 / 反馈：
# 识别「今日有无中差评」时直接剔除，既不 @ 对应店长，也不统计它有无反馈。
SMART_CHANNEL_KEYWORD = "智慧"


def _is_smart_channel(ch):
    """渠道名含「智慧」即视为无需门店回复的智慧门店渠道（覆盖命名变体）。"""
    return SMART_CHANNEL_KEYWORD in str(ch or "")


def _normalize_detail(stat):
    """统一清洗中差评明细：剔除智慧门店渠道的评价。

    实时看板已在 fetch_midbad_detail() 里逐条过滤（过滤后的「渠道」列表也只保留
    非智慧渠道），这里兼容旧缓存 / 静态兜底快照：某门店渠道全部为智慧类 →
    今日无中差评需要反馈，整店剔除，不 @、不统计。
    同时保留「渠道明细」（各渠道中评 / 差评条数），供卡片 2 的「今日待反馈明细」逐渠道展示。
    """
    out = OrderedDict()
    for name, v in (stat or {}).items():
        if is_ignored_shop(name):
            continue                      # 寮步城市店：整体不统计
        v = dict(v)
        chs = [c for c in (v.get("渠道") or []) if not _is_smart_channel(c)]
        cs = v.get("渠道明细") or {}
        if cs:
            cs = OrderedDict((c, d) for c, d in cs.items() if not _is_smart_channel(c))
            v["渠道明细"] = cs
        # 兼容旧缓存 / 静态兜底（无「评价明细」字段 → 空列表，卡片自动降级为不显示原文）
        rv = [d for d in (v.get("评价明细") or [])
              if not _is_smart_channel(d.get("渠道"))]
        v["评价明细"] = rv
        v["渠道"] = chs
        if chs and all(_is_smart_channel(c) for c in chs):
            continue
        if cs and not any(int(d.get("中评", 0)) or int(d.get("差评", 0))
                          for d in cs.values()):
            continue
        out[name] = v
    return out


def fetch_midbad_detail():
    """
    【先读取中差评明细】每天从看板 grade-data-dg.js 读取莫恩健所辖门店的评价明细，
    按「数据日期 == 看板日期（闸门已确认等于昨天）」过滤当天记录，
    按 g（中评 / 差评）分组统计每家门店「今天是否有中评、是否有差评」。
    ★ 渠道名称含「智慧」的中评 / 差评（智慧门店渠道）不需要门店回复反馈，
      识别时直接剔除：既不 @ 对应店长，也不统计它有无反馈。
    返回 (date, {门店短名: {"差评": n, "中评": m, "渠道": [...]}})，失败返回 (None, None)。
    """
    try:
        txt = S.http_text(S.DATA_JS)
        i = txt.find("{")
        raw, _ = json.JSONDecoder().raw_decode(txt[i:])
        sc = raw["scopes"]["dongguan"]
        date = sc["meta"]["date"]
        stat = OrderedDict()
        for sh in sc["shops"]:
            if sh.get("owner") != S.OWNER:
                continue
            rvs = [r for r in sh.get("reviews", [])
                   if r.get("date") == date and not r.get("deleted", "")]
            # 智慧门店渠道的中评 / 差评由平台自动产生，无需门店回复 / 反馈 → 整条剔除
            rvs = [r for r in rvs if not _is_smart_channel(r.get("ch"))]
            bad = sum(1 for r in rvs if r.get("g") == "差评")
            mid = sum(1 for r in rvs if r.get("g") == "中评")
            if bad or mid:
                # 逐渠道统计中评 / 差评条数，供卡片 2「今日待反馈明细」按渠道分行展示
                ch_stat = OrderedDict()
                for r in rvs:
                    c = r.get("ch", "") or "其他渠道"
                    d = ch_stat.setdefault(c, {"中评": 0, "差评": 0})
                    if r.get("g") == "中评":
                        d["中评"] += 1
                    elif r.get("g") == "差评":
                        d["差评"] += 1
                # 【2026-11-08】保留今日中差评【评价原文】，供 20:00 私聊提醒卡「复制粘贴」展示
                # 差评在前、中评在后；智慧门店渠道已在上面整条剔除，不会进入评价明细
                rtext = [r for r in rvs if r.get("g") in ("中评", "差评")]
                rtext.sort(key=lambda r: (0 if r.get("g") == "差评" else 1,
                                         r.get("time", "")))
                stat[sh["name"]] = {
                    "差评": bad, "中评": mid,
                    "渠道": sorted({r.get("ch", "") for r in rvs if r.get("ch")}),
                    "渠道明细": ch_stat,
                    "评价明细": [{
                        "渠道": (r.get("ch") or "").strip() or "其他渠道",
                        "评级": r.get("g", ""),
                        "内容": (r.get("txt") or "").strip(),
                        "分类": (r.get("cat") or "").strip(),
                        "时间": (r.get("time") or "").strip(),
                    } for r in rtext],
                }
        return date, stat
    except Exception:
        return None, None


def load_today_detail(refresh=False):
    """取当日中差评明细：优先实时看板；失败按日期回退缓存，再回退静态快照。
    所有来源统一经 _normalize_detail() 剔除智慧门店渠道的中评 / 差评。
    """
    global DETAIL_SHOPS, BOARD_DATE, DETAIL_SOURCE
    if refresh:
        date, stat = fetch_midbad_detail()
        if stat is not None:
            DETAIL_SHOPS = _normalize_detail(stat)
            BOARD_DATE = date
            DETAIL_SOURCE = "看板实时数据 grade-data-dg.js · %s" % date
            try:
                os.makedirs(DATA_DIR, exist_ok=True)
                with open(DETAIL_CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump({"data_date": date, "shop_review_stat": DETAIL_SHOPS,
                               "source": DETAIL_SOURCE}, f, ensure_ascii=False, indent=1)
            except Exception:
                pass
            return DETAIL_SHOPS
    # 缓存（按日期）
    try:
        c = json.load(open(DETAIL_CACHE_FILE, encoding="utf-8"))
        if c.get("data_date") == S.yesterday() or c.get("data_date") == BOARD_DATE:
            DETAIL_SHOPS = _normalize_detail(c["shop_review_stat"])
            BOARD_DATE = c["data_date"]
            DETAIL_SOURCE = c.get("source", "本地当日缓存")
            return DETAIL_SHOPS
    except Exception:
        pass
    return DETAIL_SHOPS


# ---------------------------------------------------------------- 历史明细（按评价日期回溯）
DETAIL_HIST_FILE = os.path.join(DATA_DIR, "midbad_hist.json")
_BOARD_RAW = {"ts": 0.0, "raw": None}


def _board_raw(max_age=300):
    """拉一次看板原始 JSON（里面含最近 30 天评价），进程内缓存 5 分钟。

    汇总卡每 10 秒原地刷新，不能每次打网络；历史日期一天只用一次，缓存足够。
    """
    t = time.time()
    if _BOARD_RAW["raw"] is not None and t - _BOARD_RAW["ts"] < max_age:
        return _BOARD_RAW["raw"]
    txt = S.http_text(S.DATA_JS)
    i = txt.find("{")
    raw, _ = json.JSONDecoder().raw_decode(txt[i:])
    _BOARD_RAW["ts"] = t
    _BOARD_RAW["raw"] = raw
    return raw


def fetch_detail_by_date(target_date):
    """按【评价日期】取门店中差评统计（看板含最近 30 天评价，可回溯昨天）。

    口径与 fetch_midbad_detail() 完全一致：只算莫恩健所辖门店、剔除智慧门店渠道、
    剔除寮步城市店。汇总卡用它判断「昨天」的中差评任务。
    """
    try:
        sc = _board_raw()["scopes"]["dongguan"]
    except Exception:
        return {}
    stat = OrderedDict()
    for sh in sc.get("shops", []):
        if sh.get("owner") != S.OWNER:
            continue
        if is_ignored_shop(sh.get("name")):
            continue
        rvs = [r for r in sh.get("reviews", [])
               if r.get("date") == target_date and not r.get("deleted", "")]
        rvs = [r for r in rvs if not _is_smart_channel(r.get("ch"))]
        bad = sum(1 for r in rvs if r.get("g") == "差评")
        mid = sum(1 for r in rvs if r.get("g") == "中评")
        if not (bad or mid):
            continue
        ch_stat = OrderedDict()
        for r in rvs:
            c = r.get("ch", "") or "其他渠道"
            d = ch_stat.setdefault(c, {"中评": 0, "差评": 0})
            d["中评" if r.get("g") == "中评" else "差评"] += 1
        stat[sh["name"]] = {"差评": bad, "中评": mid,
                            "渠道": sorted({r.get("ch", "") for r in rvs if r.get("ch")}),
                            "渠道明细": ch_stat}
    return _normalize_detail(stat)


def detail_for_date(target_date, refresh=False):
    """指定评价日期的中差评统计：先读本地历史缓存，没有再回看板拉一次并落盘。"""
    if not target_date:
        return {}
    try:
        hist = json.load(open(DETAIL_HIST_FILE, encoding="utf-8"))
    except Exception:
        hist = {}
    if (not refresh) and target_date in hist:
        return OrderedDict(hist[target_date])
    d = fetch_detail_by_date(target_date)
    if d:
        hist[target_date] = d
        for k in sorted(hist)[:-10]:       # 只留最近 10 天
            hist.pop(k, None)
        try:
            with open(DETAIL_HIST_FILE, "w", encoding="utf-8") as f:
                json.dump(hist, f, ensure_ascii=False, indent=1)
        except Exception:
            pass
    return d



DETAIL_SHOPS = {}          # 当日有中评/差评的门店（动态）
BOARD_DATE = BOARD.get("data_date", S.yesterday())
DETAIL_SOURCE = "静态快照（离线兜底）"
load_today_detail(refresh=True)
if not DETAIL_SHOPS:
    DETAIL_SHOPS = _normalize_detail(DETAIL_FALLBACK)
    DETAIL_SOURCE = "静态快照（看板读取失败，离线兜底）"
OK = "✅"
NO = "❌"
NA = "<font color='grey'>— 无需</font>"
NA_TXT = "— 无需"

BOARD_IMAGE_FILE = os.path.join(DATA_DIR, "midbad_image.json")


def board_image_key(date=None):
    """当天已上传的中差评明细图 image_key；没有则回退历史固定图。"""
    try:
        j = json.load(open(BOARD_IMAGE_FILE, encoding="utf-8"))
        if (not date or j.get("date") == date) and j.get("image_key"):
            return j["image_key"]
    except Exception:
        pass
    return BOARD.get("image_key", "")


def capture_midbad_image(date):
    """下载当天的【中差评明细】图片（评价看板 · 下载图片 → 预览弹窗保存）。"""
    path = os.path.join(DATA_DIR, "中差评明细_%s.png" % date)
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(
                executable_path=os.environ.get("CHROMIUM_PATH", "/usr/bin/chromium"),
                headless=True, args=["--no-sandbox"])
            ctx = b.new_context(viewport={"width": 1500, "height": 1000},
                                device_scale_factor=2, accept_downloads=True)
            pg = ctx.new_page()
            pg.goto(S.BOARD + "/#grade", wait_until="domcontentloaded", timeout=45000)
            pg.wait_for_timeout(3000)
            if pg.locator('input[type="password"]').count():
                pg.locator('input[placeholder="用户名"]').fill(S.BOARD_USER)
                pg.locator('input[placeholder="密码"]').fill(S.BOARD_PASSWORD)
                pg.get_by_role("button", name="进入看板").click()
                pg.wait_for_timeout(4500)
            frames = [x for x in pg.frames if "grade.html" in x.url]
            if not frames:
                raise RuntimeError("grade.html 未加载")
            fr = frames[0]
            fr.locator('div.tab[data-tab="reviews"]').click()
            pg.wait_for_timeout(4000)
            fr.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            pg.wait_for_timeout(500)
            try:
                fr.locator('button.dlbtn[data-dlrevlist]').first.click()
                fr.locator("#dlModalSave").first.wait_for(state="attached", timeout=60000)
                pg.wait_for_timeout(800)
                with pg.expect_download(timeout=60000) as di:
                    fr.locator("#dlModalSave").first.click()
                di.value.save_as(path)
            except Exception:
                # 降级：整页截图（至少日期是当天）
                pg.screenshot(path=path, full_page=False)
            b.close()
        return path if os.path.exists(path) else None
    except Exception:
        return None


def refresh_board_image(date):
    """抓当天中差评明细图 → 上传飞书 → 记录 image_key（供第 2 张卡使用）。"""
    if board_image_key(date) != BOARD.get("image_key", ""):
        return board_image_key(date)          # 当天已上传过
    img = capture_midbad_image(date)
    if not img:
        return board_image_key(date)
    key = S.upload_image(img)
    with open(BOARD_IMAGE_FILE, "w", encoding="utf-8") as f:
        json.dump({"date": date, "image_key": key, "file": img,
                   "ts": now().strftime("%Y-%m-%d %H:%M:%S")}, f, ensure_ascii=False, indent=1)
    return key



# ---------------------------------------------------------------- 基础工具
def now():
    return S.now()


def _sec_since(ts):
    """距 ts(YYYY-MM-DD HH:MM:SS) 的秒数；空值或解析失败 → 视为早已到期（返回极大值）。"""
    if not ts:
        return 10 ** 9
    try:
        t = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        # now() 是带时区的 aware datetime，这里统一转 naive 再相减
        return (now().replace(tzinfo=None) - t).total_seconds()
    except Exception:
        return 10 ** 9


def log(msg, sink=print):
    line = "[%s] %s" % (now().strftime("%H:%M:%S"), msg)
    sink(line)
    return line


def _norm(name):
    """门店名归一：去行政前缀 / 空格 / 括号备注，用于短名、全名、简称互配。"""
    if not name:
        return ""
    s = str(name).strip().replace(" ", "").replace("\u3000", "")
    s = s.replace("（", "(").replace("）", ")")
    s = re.sub(r"\([^)]*\)", "", s)
    for p in ("广东省", "东莞市", "东莞"):
        if s.startswith(p):
            s = s[len(p):]
            break
    s = s.replace("分店", "店").replace("门店", "店")
    return s


def _lev(a, b):
    """编辑距离：用于识别门店名错别字。"""
    if a == b:
        return 0
    if not a or not b:
        return max(len(a), len(b))
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def match_store(name):
    """把任意写法的门店名（全称 / 简称 / 短称 / 错别字 / 带备注）匹配到 26 家标准门店。"""
    if not name:
        return None
    raw = str(name).strip()
    if raw in ALL_SHOPS:
        return raw
    n = _norm(raw)
    if not n:
        return None
    # ① 归一化精确
    for full in ALL_SHOPS:
        if _norm(full) == n:
            return full
    # ② 包含关系（简称、短称、带前后缀）
    for full in ALL_SHOPS:
        fn = _norm(full)
        if n in fn or fn in n:
            return full
    # ③ 去掉「店」后的核心字
    k = n[:-1] if n.endswith("店") else n
    if len(k) >= 2:
        for full in ALL_SHOPS:
            fk = _norm(full)
            fk = fk[:-1] if fk.endswith("店") else fk
            if k in fk or fk in k:
                return full
    # ④ 错别字：与「任意等长片段」比编辑距离（容忍少写/多写行政区前缀）
    best, bd = None, 99
    for full in ALL_SHOPS:
        fk = _norm(full)
        fk = fk[:-1] if fk.endswith("店") else fk
        d = _min_sub_dist(k, fk)
        if d < bd:
            best, bd = full, d
    if best and bd <= min(2, max(1, len(k) // 2)):
        return best
    return None


_DEPT_CODE_RE = re.compile(r"^[A-Za-z]{1,3}\d{2,4}")


def dept_to_store(v):
    """「创建人.部门」字段 → 门店。值形如 ['TW0308东莞市虎门威远店']：
    剥掉开头的门店编号（TW0308 / MW0600 等），再用 match_store 归一化匹配到 26 家标准门店。"""
    if isinstance(v, list):
        v = v[0] if v else ""
    if not isinstance(v, str):
        return None
    raw = v.strip()
    if not raw:
        return None
    stripped = _DEPT_CODE_RE.sub("", raw)
    return match_store(stripped) or match_store(raw)


def _min_sub_dist(k, fk):
    """k 与 fk 任意等长片段的最小编辑距离（应对「富朱山」vs「寮步富竹山」）。"""
    if not k or not fk:
        return 99
    best = _lev(k, fk)
    L = len(k)
    for size in range(max(2, L - 1), L + 3):
        for i in range(0, max(1, len(fk) - size + 1)):
            d = _lev(k, fk[i:i + size])
            if d < best:
                best = d
    return best


def store_by_person(person):
    """创建人姓名 → 门店：先按店长姓名精确匹配，再用姓名里的门店关键字匹配。"""
    if not person:
        return None
    p = str(person).strip()
    for full, v in MANAGER.items():
        if v.get("店长") and v["店长"] == p:
            return full
    return match_store(p)


def _short(name):
    """展示用短名：去掉「东莞市」前缀，保留「xx店」。"""
    s = str(name or "").strip()
    for p in ("东莞市", "东莞"):
        if s.startswith(p):
            return s[len(p):]
    return s


def detail_of(shop_full):
    """查今日中差评明细里该门店的差评/中评条数。返回 (差评, 中评, 匹配到的短名)。"""
    n = _norm(shop_full)
    for k, v in DETAIL_SHOPS.items():
        if _norm(k) == n or _norm(k) in n or n in _norm(k):
            return int(v.get("差评", 0)), int(v.get("中评", 0)), k
    return 0, 0, _short(shop_full)


def creator_info(open_id):
    """创建人 open_id → {门店名称, 店长, 店长open_id, 加盟T/M, 姓名}。"""
    return OPENID2STORE.get(open_id)


def _manager_match(shop):
    """门店（全名/短名）→ MANAGER 记录 {店长, open_id}，做归一化匹配。"""
    v = MANAGER.get(shop)
    if v:
        return v
    n = _norm(shop)
    for k, val in MANAGER.items():
        if _norm(k) == n:
            return val
    return {}


def manager_open_id(shop_full):
    """门店 → 店长 open_id（真实 @ 用）。"""
    return _manager_match(shop_full).get("open_id", "")


def manager_name(shop_full):
    return _manager_match(shop_full).get("店长", "")


def manager_tm(shop_full):
    """门店 → 加盟T/M 前缀（@T / @M）。"""
    n = _norm(shop_full)
    for oid, v in OPENID2STORE.items():
        if _norm(v["门店名称"]) == n:
            return v.get("加盟T/M", "")
    for m in STORE_MAP:
        if _norm(m["门店名称"]) == n:
            return m.get("加盟T/M", "")
    return ""


_TM_CACHE = {}          # 归一化门店名 → 'T' / 'M' / ''（避免反复遍历门店表）


def tm_of(shop_full):
    """门店 → 加盟类型 'T' / 'M'（取不到返回空串）。带缓存。"""
    key = _norm(shop_full)
    if key in _TM_CACHE:
        return _TM_CACHE[key]
    v = (manager_tm(shop_full) or "").strip().upper()
    _TM_CACHE[key] = v
    return v


def tm_rank(shop_full):
    """加盟类型排序键：T 加盟 → 0（排前面），M 加盟 → 1（排后面），未知 → 2。

    【2026-11-09 用户要求】「回复率截图未反馈」和「已反馈统计」两个名单里，
    T 加盟门店排在上、M 加盟门店排在下；**只排序，不做 T/M 分类分组**，
    也不加任何分组标题，组内维持原有先后顺序（稳定排序）。
    """
    return {"T": 0, "M": 1}.get(tm_of(shop_full), 2)


def sort_by_tm(items, key=None):
    """按加盟类型稳定排序（T 在前、M 在后）；组内顺序不变，不产生分组。"""
    kf = key or (lambda x: x)
    return sorted(items, key=lambda x: tm_rank(kf(x)))


# ---------------------------------------------------------------- 门店负责人（汇总卡分组）
# 【2026-11-09 用户要求】汇总卡按【门店负责人】分两段：
#   · T 加盟（负责人魏兆翔 / 魏兆翎）→ @魏兆翔 @魏兆翎
#   · M 加盟（其余加盟商，大狮兄莫恩健）→ @莫恩健（用户本人）
OWNER_WSX = "魏兆翔"
OWNER_WSL = "魏兆翎"
OWNER_MEJ = "莫恩健"


def owner_of(shop_full):
    """门店负责人（加盟商老板）：读 store_mapping.json 的「负责人」字段。"""
    n = _norm(shop_full)
    for m in STORE_MAP:
        if _norm(m["门店名称"]) == n:
            return (m.get("负责人") or "").strip()
    return ""


def owner_group(shop_full):
    """门店归属哪一段：负责人魏兆翔 / 魏兆翎各自单独一段，其余（M 加盟）→ 'M'。"""
    o = owner_of(shop_full)
    if o in (OWNER_WSX, OWNER_WSL):
        return o
    return "M"


def at_tag(open_id, fallback_name=""):
    if open_id:
        return '<at id=%s></at>' % open_id
    return _plain_name(fallback_name)


def _plain_name(name):
    """【2026-11-09 用户要求】封板后 @店长 降级为纯文本：只写名字。

    · 不生成 `<at id=…>`，封板后不再触发 @ 提醒；
    · 只写「张三」，不附带任何门店名，避免一长串「张三（东莞市XX店）」。
    """
    return "<font color='grey'>%s</font>" % (str(name or "").strip() or "店长")


def _plain_store(name):
    """【2026-11-09 用户要求】封板后「未反馈」区块：人名文本改为【店名】文本。

    只写门店名（灰色），不写店长姓名、不真 @、也不带 @ 符号。
    """
    nm = _short(name).strip()
    return "<font color='grey'>%s</font>" % (nm or "门店")


def _name_of(info):
    """取店长姓名（用于纯文本降级）：先看 manager，再用 open_id 反查，绝不回退成门店名。"""
    info = info or {}
    nm = str(info.get("manager") or "").strip()
    if nm:
        return nm
    oid = str(info.get("manager_open_id") or info.get("open_id") or "").strip()
    if oid:
        v = OPENID2STORE.get(oid) or {}
        nm = str(v.get("店长") or v.get("manager") or "").strip()
    return nm or "店长"

# ---------------------------------------------------------------- 飞书 API（原生 HTTP，自包含）
def _api(method, path, token, body=None, timeout=30):
    # LARK_BASE 已含 /open-apis，这里统一去掉重复前缀
    if path.startswith("/open-apis"):
        path = path[len("/open-apis"):]
    url = S.LARK_BASE + path
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json; charset=utf-8",
                 "Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        return {"code": -1, "msg": "HTTP %s: %s" % (e.code, detail[:400])}


def fetch_records():
    """读取多维表格全部记录。字段：创建人 / 提交时间 / 差评反馈 / 中评回复申诉反馈 / 回复率截图。"""
    token = S.get_token()
    app, tbl = BT["app_token"], BT["table_id"]
    j = _api("GET", "/open-apis/bitable/v1/apps/%s/tables/%s/records?page_size=200" % (app, tbl), token)
    if j.get("code") != 0:
        raise RuntimeError("读取多维表格失败：%s" % j.get("msg"))
    return j.get("data", {}).get("items", [])


def patch_card(message_id, card):
    """原地刷新同一张卡片（不重发）。"""
    token = S.get_token()
    body = {"content": json.dumps(card, ensure_ascii=False)}
    return _api("PATCH", "/open-apis/im/v1/messages/%s" % message_id, token, body)


def send_card(card, mode="trial"):
    return S.send_card(card, mode)


def send_text(text, mode="trial"):
    """发一条带 @ 的文本（markdown）消息，用于审核告警。"""
    token = S.get_token()
    if mode == "live":
        rid, rtype = LIVE["chat_id"], "chat_id"
    else:
        rid, rtype = TRIAL["open_id"], "open_id"
    card = {"schema": "2.0", "config": {"update_multi": True},
            "header": {"title": {"tag": "plain_text", "content": "反馈审核提醒"},
                       "template": "orange",
                       "text_tag_list": [{"tag": "text_tag",
                                          "text": {"tag": "plain_text", "content": "有 ❌ 需整改"},
                                          "color": "orange"}]},
            "body": {"direction": "vertical", "padding": "12px 12px 12px 12px",
                     "elements": [{"tag": "markdown", "content": text}]}}
    payload = {"receive_id": rid, "msg_type": "interactive",
               "content": json.dumps(card, ensure_ascii=False)}
    j = _api("POST", "/open-apis/im/v1/messages?receive_id_type=" + rtype, token, payload)
    if j.get("code") != 0:
        plain = _strip_at_text(text)
        payload["content"] = json.dumps(
            {**card, "body": {"direction": "vertical", "padding": "12px",
                              "elements": [{"tag": "markdown", "content": plain}]}},
            ensure_ascii=False)
        j = _api("POST", "/open-apis/im/v1/messages?receive_id_type=" + rtype, token, payload)
    return j


def _strip_at_text(t):
    import re
    return re.sub(r'<at id=[^>]+></at>', lambda m: "@店长", t)


# ---------------------------------------------------------------- 状态存取
def load_state():
    try:
        return json.load(open(STATE_FILE, encoding="utf-8"))
    except Exception:
        return {}


def save_state(st):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def _sig(records):
    """记录签名：任何新增/修改都会变，用于每秒轮询去重。"""
    return json.dumps(
        [(r.get("record_id"), list((r.get("fields") or {}).keys()),
          str((r.get("fields") or {}).get("差评反馈（当天）")
              or (r.get("fields") or {}).get("差评反馈") or "")[:60],
          len((r.get("fields") or {}).get("中评回复申诉反馈") or []),
          len((r.get("fields") or {}).get("回复率截图") or []))
         for r in records], ensure_ascii=False)


# ---------------------------------------------------------------- 聚合 / 审核
# 业务时段：08:00 - 23:59 正常记录；00:00 - 07:59 的提交作废（不记录、不改判）
BIZ_DAY_START_HOUR = SCHED.get("biz_day_start_hour", 8)


def _biz_ok(ts_ms, biz_date=None):
    """提交时间是否落在有效业务时段。
       · 当天 00:00-07:59 的提交 → 不记录（第二天 8 点前的反馈作废）
       · 指定 biz_date 时只认这一天的提交（跨天记录不串到今天的卡）
       · 提交时间缺失 / 无法解析 → 放行，避免丢数据
    """
    try:
        if not ts_ms:
            return True
        dt = datetime.fromtimestamp(float(ts_ms) / 1000)
    except Exception:
        return True
    if biz_date and dt.strftime("%Y-%m-%d") != biz_date:
        return False
    if dt.hour < BIZ_DAY_START_HOUR:
        return False
    return True


def aggregate(records, biz_date=None):
    """
    按门店聚合所有提交（含补交）。补交 = 同一门店再来一条记录，
    只要任一记录补齐了某项，就视为该项已提供 → 对应 ❌ 自动改 ✅。
    返回 OrderedDict[门店全名] = dict。
    """
    shops = OrderedDict()
    for r in records:
        f = r.get("fields") or {}
        if not _biz_ok(f.get("提交时间"), biz_date):
            continue          # 00:00-07:59 的提交 / 非当天提交：不计入
        cb = f.get("创建人")
        oid = ""
        if isinstance(cb, dict):
            oid = cb.get("id", "")
        elif isinstance(cb, list) and cb and isinstance(cb[0], dict):
            oid = cb[0].get("id", "")
        # 先解析三项内容；三项全空的记录（误点提交）不算已反馈
        # 表格实际字段名是「差评反馈（当天）」，兼容旧名「差评反馈」
        txt = f.get("差评反馈（当天）")
        if txt is None:
            txt = f.get("差评反馈")
        if isinstance(txt, list):
            txt = "".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in txt)
        txt = txt.strip() if isinstance(txt, str) else ""
        midd = [x for x in (f.get("中评回复申诉反馈") or []) if isinstance(x, dict)]
        rated = [x for x in (f.get("回复率截图") or []) if isinstance(x, dict)]
        if not txt and not midd and not rated:
            continue
        info = creator_info(oid)
        # 门店识别优先级：①「创建人.部门」字段（组织架构，最准）② open_id 静态映射 ③ 姓名模糊
        shop = dept_to_store(f.get("创建人.部门"))
        if not shop and info:
            shop = info["门店名称"]
        if not shop:
            # 静态映射里也没有这个创建人（新人 / 换了账号）→ 用姓名 + 部门名做模糊识别
            pname = ""
            if isinstance(cb, dict):
                pname = cb.get("name") or cb.get("en_name") or ""
            depts = []
            if isinstance(cb, dict):
                for k in ("departments", "department_ids"):
                    v = cb.get(k)
                    if isinstance(v, list):
                        depts += [str(x.get("name") if isinstance(x, dict) else x) for x in v]
            shop = (store_by_person(pname)
                    or next((m for m in (match_store(d) for d in depts if d) if m), None))
            if not shop:
                shop = "（未识别提交人）" + ((pname or oid[-6:]) if (pname or oid) else "")
        if is_ignored_shop(shop):
            continue                      # 寮步城市店：提交也不计入任何统计
        d = shops.setdefault(shop, {
            "store": shop,
            "creator_open_id": oid,
            "manager": (info["店长"] if info else "") or manager_name(shop),
            "tm": (info["加盟T/M"] if info else "") or manager_tm(shop),
            "manager_open_id": (info["店长open_id"] if info else "") or manager_open_id(shop),
            "bad_text": "",          # 差评反馈文本
            "mid_files": 0,          # 中评回复申诉反馈 附件数
            "rate_files": 0,         # 回复率截图 附件数
            "mid_tokens": [],        # 中评附件 file_token
            "rate_tokens": [],       # 回复率截图 file_token
            "records": 0,
            "last_ts": 0,
        })
        d["records"] += 1
        if txt:
            d["bad_text"] = txt
        d["mid_files"] += len(midd)
        d["rate_files"] += len(rated)
        d["mid_tokens"] += [x.get("file_token") for x in midd if x.get("file_token")]
        d["rate_tokens"] += [x.get("file_token") for x in rated if x.get("file_token")]
        ts = f.get("提交时间") or 0
        if isinstance(ts, (int, float)) and ts > d["last_ts"]:
            d["last_ts"] = ts
    return shops


def _empty_agg(name):
    info = _manager_match(name)
    return {
        "store": name, "creator_open_id": "",
        "manager": info.get("店长", manager_name(name)),
        "tm": manager_tm(name),
        "manager_open_id": info.get("open_id", manager_open_id(name)),
        "bad_text": "", "mid_files": 0, "rate_files": 0, "records": 0, "last_ts": 0,
        "mid_tokens": [], "rate_tokens": [],
    }


def agg_for(shops, name):
    """按归一化门店名取该门店的聚合记录；没有提交过返回空聚合。"""
    n = _norm(name)
    for k, v in shops.items():
        if _norm(k) == n:
            return v
    return _empty_agg(name)


# ---------------------------------------------------------------- 回复率截图识别（OCR）
OCR_CACHE_FILE = os.path.join(DATA_DIR, "ocr_rate_cache.json")
# 判定规则版本：升级后旧缓存自动重判（尤其旧版把「旋转翻拍的合规截图」误判为不合格的），
# 旧版判 ok 的结果直接沿用、不重复下载。每次识别结果带 ver/pattern/round，沉淀为自学习样本。
OCR_VER = 2
_OCR_MEM = {}
_OCR_LOCK = threading.Lock()


def _ocr_mem():
    if not _OCR_MEM:
        try:
            _OCR_MEM.update(json.load(open(OCR_CACHE_FILE, encoding="utf-8")))
        except Exception:
            pass
    return _OCR_MEM


def _ocr_save():
    try:
        with open(OCR_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_OCR_MEM, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def download_media(token):
    """下载多维表格附件（file_token → bytes）。"""
    url = "https://open.feishu.cn/open-apis/drive/v1/medias/%s/download" % token
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + S.get_token()})
    return urllib.request.urlopen(req, timeout=60).read()


def _ocr_tokens(up, psm=6):
    """OCR 词框（坐标基于传入图）。"""
    import pytesseract
    d = pytesseract.image_to_data(up, lang="chi_sim+eng", config="--psm %d" % psm,
                                  output_type=pytesseract.Output.DICT)
    toks = []
    for i in range(len(d["text"])):
        s = str(d["text"][i] or "").replace(" ", "")
        if not s:
            continue
        x, y, w, h = d["left"][i], d["top"][i], d["width"][i], d["height"][i]
        toks.append({"s": s, "x": x, "y": y, "w": w, "h": h,
                     "cx": x + w / 2.0, "cy": y + h / 2.0})
    return toks


def _pct_list(toks):
    """抽取所有百分比数值（带坐标），支持「100%100%」粘成一个词。"""
    out = []
    for t in toks:
        s = t["s"].replace("％", "%")
        ms = list(re.finditer(r"(\d{1,3})%", s))
        if not ms:
            continue
        for k, m in enumerate(ms):
            v = int(m.group(1))
            if not (0 <= v <= 100):
                continue
            cx = t["cx"] if len(ms) == 1 else t["x"] + t["w"] * (k + 0.5) / len(ms)
            out.append({"v": v, "cx": cx, "cy": t["cy"]})
    return out


def _pick_pair(pcts, anchor=None):
    """选出（5分钟, 1分钟）两个数值：优先「今日」同一水平带的两个，按 x 左→右。"""
    cand = list(pcts)
    if anchor is not None:
        near = [p for p in cand if abs(p["cy"] - anchor["cy"]) <= 200]
        if len(near) >= 2:
            cand = near
    if len(cand) < 2:
        return None
    cand.sort(key=lambda p: p["cx"])
    uniq = []
    for p in cand:
        if uniq and abs(p["cx"] - uniq[-1]["cx"]) < 20:
            continue
        uniq.append(p)
    if len(uniq) < 2:
        return None
    return uniq[0], uniq[1]


def _rate_pair(toks, pcts):
    """
    取（5分钟, 1分钟）两个回复率数值，三级定位：
      ① 标签与数值在同一个词里（消息权益页）："5分钟回复率98%"
      ② 标签与数值分开（消息页顶部横幅）：按「5分钟」「1分钟」标签坐标就近取上方数值
      ③ 兜底：以「今日」为锚点、或全量按 x 左→右配对
    """
    five = one = None
    for t in toks:
        s = t["s"].replace("％", "%")
        for m in re.finditer(r"([51])分钟[^0-9]{0,8}(\d{1,3})%", s):
            k, v = m.group(1), int(m.group(2))
            if v > 100:
                continue
            if k == "5":
                five = v
            else:
                one = v
    if five is not None and one is not None:
        return five, one, "label"

    def near(lbl):
        c = [p for p in pcts if abs(p["cx"] - lbl["cx"]) <= 320
             and -450 <= (p["cy"] - lbl["cy"]) <= 140]
        if not c:
            return None
        c.sort(key=lambda p: (abs(p["cy"] - lbl["cy"]), abs(p["cx"] - lbl["cx"])))
        return c[0]["v"]

    for t in toks:
        s = t["s"]
        if five is None and "5分钟" in s:
            five = near(t)
        if one is None and "1分钟" in s:
            one = near(t)
    if five is not None and one is not None:
        return five, one, "coord"

    anchor = None
    for t in toks:
        if "今日" in t["s"]:
            anchor = t
            break
    pair = _pick_pair(pcts, anchor) or _pick_pair(pcts, None)
    if pair:
        return pair[0]["v"], pair[1]["v"], "fallback"
    return five, one, "partial"


# 「过去 7 天平均回复率 / 7 日权益」列标题特征：这些数字不参与「今日」判定
_RATE_PAST_LABELS = ("过去7", "过去 7", "过去七", "7天", "7 天", "7日", "7 日",
                     "七天", "七日", "平均回复", "平均", "复购", "近7", "近 7")


def _rate_today_verdict(toks):
    """从【一次 OCR 结果】判定「今日回复率是否 100%」。

    返回 (ok, five, one, src, reason, info)，info 记录版式/列分组，沉淀为自学习样本。

    规则（用户 2026-11-08 定义）：
      · 只判定「今日」有无达成 100%；「过去 7 天平均回复率」「7 日已获银牌/金牌/
        7 日未获权益」的数字与文字都不参与判定、不拉低结论（96% / 94% 之类忽略）。
      · 两种版式都覆盖：
        A 横幅页：右上角「今日」两个 100%（左侧可能写「7日未获权益 / 已获银牌 / 已获金牌」）；
        B 消息权益页：中下「权益指标」，「今日」两个 100% + 「过去 7 天平均回复率 xxx%」。
      · 真未达标（今日 90% / 80%，全画面没有任何 100%）仍要拒绝。
    """
    pcts = _pct_list(toks)
    n100 = sum(1 for p in pcts if p["v"] == 100)
    today_lbl = [t for t in toks if "今日" in t["s"]]
    past_lbl = [t for t in toks
                if any(k in t["s"] for k in _RATE_PAST_LABELS)]
    info = {"n_pct": len(pcts), "n100": n100}

    # ① 精确列切分：版式 B「消息权益页」——「今日」与「过去7天平均」两个列标题
    #    处在同一水平行、且画面识别出 ≥3 个百分比（今日 2 个 + 过去7天 1~2 个）。
    #    以两标题 x 的中线为界，只取「今日」侧数值判定，彻底排除 7 天数字：
    #      · 今日 100/100、7 天 96/94 → 通过（7 天数字不拉低结论）
    #      · 今日 90/80、7 天 100/100 → 拒绝（只认今日，7 天达标不算数）
    #    横幅页只有右上角 2 个 100%，不满足「≥3 个百分比」，不会误进列切分。
    same_row = bool(today_lbl and past_lbl and
                    any(abs(a["cy"] - b["cy"]) <= 120
                        for a in today_lbl for b in past_lbl))
    if same_row and len(pcts) >= 3:
        boundary = (min(t["cx"] for t in today_lbl) +
                    max(t["cx"] for t in past_lbl)) / 2.0
        ordered = sorted(pcts, key=lambda p: p["cx"])
        tvals = [p["v"] for p in ordered if p["cx"] < boundary]
        pvals = [p["v"] for p in ordered if p["cx"] >= boundary]
        info.update({"pattern": "消息权益页", "today_col": tvals, "past_col": pvals})
        if len(tvals) >= 2:
            five, one = tvals[0], tvals[1]
            ok = (five == 100 and one == 100)
            return (ok, five, one, "today_col",
                    "" if ok else "今日回复率未达 100%%（%s%% / %s%%）" % (five, one),
                    info)

    # ② 通用强信号：出现两个及以上 100% → 今日达成
    #    （横幅页 / 旋转翻拍 / 标签没识别到时，画面里就只有右上角那两个 100%）
    if n100 >= 2:
        info.setdefault("pattern", "横幅页（右上角两个100%）")
        return True, 100, 100, "two_100", "", info
    # ③ 只识别到一个 100% 且没有任何低于 100 的数值 → 视为达成
    #    （「7 日已获银牌/金牌」简版横幅可能只显示一个 100%，或 OCR 拆坏了另一个）
    if n100 == 1 and not any(p["v"] < 100 for p in pcts):
        info.setdefault("pattern", "横幅页（单个100%）")
        return True, 100, 100, "one_100", "", info
    # ④ 没有任何 100%：有数值→真未达标；无数值→无法识别（交给下一轮审核）
    if pcts:
        vals = [p["v"] for p in sorted(pcts, key=lambda p: p["cx"])]
        five = vals[0]
        one = vals[1] if len(vals) > 1 else vals[0]
        info.setdefault("pattern", "未达标")
        return (False, five, one, "numeric",
                "今日回复率未达 100%%（%s%% / %s%%）" % (five, one), info)
    info.setdefault("pattern", "无法识别")
    return (False, None, None, "empty",
            "截图中未识别到回复率数值（空白照 / 无关照片 / 角度问题）", info)


def _ocr_rate_image(data):
    """识别【回复率截图】：判定「今日」回复率是否达成 100%。

    按用户要求「每次审核需要审核 2 到 3 次」——同一张截图用多轮
    （方向 × 预处理 × psm）重复 OCR 识别，任一命中「今日 100%」即通过，
    避免因旋转 90° 翻拍、模糊、二值化差异导致把合规截图误判为不合格。
    正常清晰截图第 1 轮即短路；只有识别不出的疑难图才会追加到 2~3 轮。

    返回 {"ok", "five", "one", "blur", "src", "reason", "ver", "pattern",
          "round", "mode", "today_col", "past_col", "attempts"}
    """
    try:
        from PIL import Image
        import numpy as np
        import cv2
        import pytesseract
    except Exception as e:
        return {"ok": False, "reason": "OCR 组件不可用：%s" % e, "ver": OCR_VER,
                "pattern": "无法识别", "attempts": []}
    try:
        im = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        return {"ok": False, "reason": "图片无法打开（非图片 / 已损坏）",
                "ver": OCR_VER, "pattern": "无法识别", "attempts": []}
    if im.width < 300 or im.height < 300:
        return {"ok": False, "reason": "图片尺寸过小，非有效截图",
                "ver": OCR_VER, "pattern": "无法识别", "attempts": []}
    base = np.array(im)
    g0 = cv2.cvtColor(base, cv2.COLOR_RGB2GRAY)
    blur = float(cv2.Laplacian(g0, cv2.CV_64F).var())

    # 审核轮次：正向 → 正向二值稀疏文本 → 旋转90°灰度 → 旋转90°二值。
    # 前两轮覆盖合规横幅/权益页/真未达标；后两轮专救旋转翻拍的金牌横幅。
    rounds = [
        ("正向·灰度", None, "gray", 6),
        ("正向·二值稀疏", None, "binar", 11),
        ("旋转90°·灰度", cv2.ROTATE_90_CLOCKWISE, "gray", 6),
        ("旋转90°·二值", cv2.ROTATE_90_CLOCKWISE, "binar", 6),
    ]

    def _prep(gray, how):
        if how == "binar":
            gray = cv2.threshold(gray, 0, 255,
                                 cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        return cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

    attempts = []
    best_fail = None       # 保留「信息最全」的非通过结论（有今日数值 > 有数值 > 空）
    for i, (mode, rot, how, psm) in enumerate(rounds):
        arr = base if rot is None else cv2.rotate(np.ascontiguousarray(base), rot)
        gray = cv2.cvtColor(np.ascontiguousarray(arr), cv2.COLOR_RGB2GRAY)
        toks = _ocr_tokens(_prep(gray, how), psm)
        ok, five, one, src, reason, info = _rate_today_verdict(toks)
        attempts.append({"round": i + 1, "mode": mode, "psm": psm,
                         "ok": ok, "five": five, "one": one, "src": src,
                         "n_pct": info.get("n_pct"), "n100": info.get("n100"),
                         "pattern": info.get("pattern")})
        result = {
            "ok": ok, "five": five, "one": one, "blur": round(blur, 1),
            "src": src, "reason": reason, "ver": OCR_VER,
            "pattern": info.get("pattern", ""), "round": i + 1, "mode": mode,
            "today_col": info.get("today_col"), "past_col": info.get("past_col"),
        }
        if ok:
            result["attempts"] = attempts
            return result
        score = (1 if five is not None else 0, info.get("n_pct") or 0)
        if best_fail is None or score > best_fail[0]:
            best_fail = (score, result)
    out = best_fail[1] if best_fail else {"ok": False, "reason": "无法识别",
                                          "ver": OCR_VER, "pattern": "无法识别"}
    out["attempts"] = attempts
    return out


# 申诉状态关键词：必须有明确状态；只有「申诉」按钮 / 申诉入口不算
APPEAL_RE = re.compile(r"已申诉|申诉(?!心)(已)?(中|成功|失败|通过|驳回|处理中|已完成|已提交)")


def _ocr_mid_image(data):
    """
    识别【中评回复申诉反馈截图】：必须能看到申诉状态（申诉中 / 申诉成功 / 申诉失败 等）。
    只显示「申诉」按钮、或只是评价列表页 → 不通过。
    """
    try:
        from PIL import Image
        import numpy as np
        import cv2
        import pytesseract
    except Exception as e:
        return {"ok": False, "reason": "OCR 组件不可用：%s" % e}
    try:
        im = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        return {"ok": False, "reason": "图片无法打开（非图片 / 已损坏）"}
    if im.width < 300 or im.height < 300:
        return {"ok": False, "reason": "图片尺寸过小，非有效截图"}
    base = np.array(im)
    # 方向自适应：手机竖屏截图常被存成横向，逐方向 OCR 取中文字符最多者
    best = None
    for rot in (None, cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE, cv2.ROTATE_180):
        a = np.rot90(base) if rot is None else cv2.rotate(base, rot)
        gg = cv2.cvtColor(np.ascontiguousarray(a), cv2.COLOR_RGB2GRAY)
        uu = cv2.resize(gg, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        tt = pytesseract.image_to_string(uu, lang="chi_sim+eng", config="--psm 6")
        cjk = len(re.findall(r"[\u4e00-\u9fff]", tt or ""))
        if best is None or cjk > best[0]:
            best = (cjk, tt or "", gg)
    _cjk, txt, g = best
    blur = float(cv2.Laplacian(g, cv2.CV_64F).var())
    compact = re.sub(r"\s+", "", txt or "")
    # 「暂无评价」＝ 评价列表为空 → 该门店今日无中差评
    empty = bool(re.search(r"暂[^0-9]{0,4}(?:无[^0-9]{0,4}评价|评价[^0-9]{0,4}无)|暂无评价", compact))
    m = APPEAL_RE.search(compact)
    if m:
        return {"ok": True, "empty": empty,
                "hit": compact[max(0, m.start() - 4):m.end() + 4],
                "blur": round(blur, 1), "reason": ""}
    if empty:
        return {"ok": False, "empty": True, "blur": round(blur, 1),
                "reason": "中差评截图为「暂无评价」，该店今日无中差评"}
    if "申诉" in compact or "评价" in compact:
        return {"ok": False, "empty": False, "blur": round(blur, 1),
                "reason": "中评截图未显示「申诉中 / 申诉成功 / 申诉失败」等申诉状态"}
    return {"ok": False, "empty": False, "blur": round(blur, 1),
            "reason": "中评截图无法识别（空白照 / 无关照片）"}


def _ocr_cached(token, kind):
    """按 token + 类型缓存识别结果；重交新图（新 token）会重新识别。

    规则版本升级（OCR_VER）时的自愈：
      · 旧版判 ok=True 的结果 → 直接沿用（本来就是合规的，省一次下载）；
      · 旧版判 ok=False 的 rate 结果 → 用新规则重判一次，救回被旧版
        「单次 dir=0 识别」误判不合格的旋转翻拍 / 消息权益页合规截图；
      · mid（中评截图）不涉及本次改动，沿用旧结论。
    """
    key = "%s:%s" % (kind, token)
    with _OCR_LOCK:
        cache = _ocr_mem()
        old = cache.get(key)
    if old is not None:
        stale = old.get("ver") != OCR_VER
        # 仅「旧版本的 rate 不合格」才重判；其余一律沿用（并补写版本号，避免反复检查）
        need_recheck = (stale and kind == "rate" and not old.get("ok"))
        if not need_recheck:
            if stale:
                old = dict(old)
                old["ver"] = OCR_VER
                with _OCR_LOCK:
                    _OCR_MEM[key] = old
                    _ocr_save()
            return old
    try:
        data = download_media(token)
        r = _ocr_rate_image(data) if kind == "rate" else _ocr_mid_image(data)
    except Exception as e:
        r = {"ok": False, "reason": "截图下载失败：%s" % str(e)[:60],
             "ver": OCR_VER, "pattern": "无法识别", "attempts": []}
    r["ts"] = now().strftime("%Y-%m-%d %H:%M:%S")
    r.setdefault("ver", OCR_VER)
    with _OCR_LOCK:
        _OCR_MEM[key] = r
        _ocr_save()
    return r


def mid_verdict(agg):
    """中评：只看是否上传了「中评回复申诉反馈」，图片内容不再审核，默认合格。
    未上传 → 不通过。返回 (ok, 原因)。"""
    toks = agg.get("mid_tokens") or []
    if not toks:
        return False, "中评回复申诉反馈未填写"
    return True, ""


def rate_check(token):
    """单个回复率截图的判定结果（token 级缓存，重交新图会重新识别）。"""
    return _ocr_cached(token, "rate")


def rate_verdict(agg):
    """按门店全部回复率截图判定：任一附件两个 100% 即通过。返回 (ok, 原因)。"""
    toks = agg.get("rate_tokens") or []
    if not toks:
        return False, "回复率截图未上传"
    reason = ""
    for t in toks:
        r = rate_check(t)
        if r.get("ok"):
            return True, ""
        reason = r.get("reason", "")
    return False, "回复率截图不合规：%s" % (reason or "无法识别")


def _reviews_empty(agg):
    """中差评截图明确显示「暂无评价」→ 该店今日无中差评（覆盖可能滞后/串店的看板）。
    没有截图或无法判断 → 返回 False，不改动看板结论。"""
    for t in (agg.get("mid_tokens") or []):
        r = _ocr_cached(t, "mid")
        if r.get("empty"):
            return True
    return False


# ---------------------------------------------------------------- 差评反馈文本 · 关键字归类
# 店长在「差评反馈（当天）」里填的是自由文本，按条目切分后按关键字归类到
# 「删除 / 申诉 / 无法处理」三类，供第 3 张卡片的【门店名称】统计块显示条数。
BAD_DELETE_KEYS = ("已删除", "删除", "撤销", "已撤销", "下架", "拦截", "已拦截", "免责")
BAD_APPEAL_KEYS = ("已审批", "申诉中", "申诉掉", "申诉成功", "申诉失败", "已申诉",
                   "申诉", "审批", "复审")
BAD_NONE_WORDS = ("无差评", "无中差评", "无评价", "没有差评", "为空", "暂无", "未填", "没有")
# 纯否定条目（允许日期 / 数字 / 标点噪声）：不做统计
_BAD_NONE_PURE = re.compile(
    r"^[\s\d\W_]*(?:无|没有|为空|暂无|未填|无差评|无中差评|无评价|没有差评|—|-|/)*[\s\d\W_]*$")
_BAD_SPLIT = re.compile(r"[\r\n；;，,、。]+|\s{2,}")
_BAD_SEQ = re.compile(r"^\s*(?:\d+\s*[、.．)）:：]|[①-⑩])\s*")
_BAD_DATE = re.compile(r"^\s*\d{1,2}[.．/]\d{1,2}\s*号?\s*")
_BAD_QTY = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
            "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def bad_text_is_none(txt):
    """「无 / 没有 / 为空」类否定反馈 → True（不做统计，且有差评时判 ❌ 未反馈差评）。"""
    s = str(txt or "").strip()
    if not s:
        return True
    # 一旦出现删除 / 申诉类关键字，说明有实质处理描述，不是否定反馈
    if any(k in s for k in BAD_DELETE_KEYS) or any(k in s for k in BAD_APPEAL_KEYS):
        return False
    if _BAD_NONE_PURE.match(s):
        return True
    return any(k in s for k in BAD_NONE_WORDS)


def _bad_qty(seg):
    """条目里的「两条 / 2条 / 一条」数量词 → 该类别计入的条数（默认 1）。"""
    m = re.search(r"([一二两三四五六七八九十\d]+)\s*条", seg)
    if not m:
        return 1
    t = m.group(1)
    if t.isdigit():
        return max(1, min(int(t), 20))
    return _BAD_QTY.get(t, 1)


def bad_feedback_breakdown(txt):
    """把店长填写的差评反馈文本归类为 (删除条数, 申诉条数, 无法处理条数, 是否否定反馈)。

    · 关键字「已删除 / 删除」等  → 删除 x 条
    · 关键字「已审批 / 申诉中 / 申诉掉 / 申诉…」等 → 申诉 x 条
    · 整段是「无 / 没有 / 为空」→ 不做统计，返回否定标记（有差评的门店判 ❌ 未反馈差评）
    · 其他内容一律 → 无法处理 x 条
    """
    s = str(txt or "").strip()
    if not s or bad_text_is_none(s):
        return 0, 0, 0, True
    d = a = u = 0
    for raw in _BAD_SPLIT.split(s):
        seg = _BAD_SEQ.sub("", raw)
        seg = _BAD_DATE.sub("", seg).strip()
        if not seg:
            continue
        if _BAD_NONE_PURE.match(seg):
            continue                       # 纯「无 / 没有」条目不做统计
        q = _bad_qty(seg)
        if any(k in seg for k in BAD_DELETE_KEYS):
            d += q
        elif any(k in seg for k in BAD_APPEAL_KEYS):
            a += q
        else:
            u += q
    if d == a == u == 0:
        return 0, 0, 0, True
    return d, a, u, False


def judge(name, shops):
    """
    【新判定】按「今天是否有中评 / 是否有差评」+ 多维表格填写情况：

      · 差评：今日有差评 → 表格「差评反馈」填了=ok / 没填=fail；今日无差评 → na（— 无需）
      · 中评：今日有中评 → 表格「中评回复申诉反馈」上传=ok / 没上传=fail；今日无中评 → na
      · 回复率：全部 26 家（不含寮步城市店）门店都要 → 表格「回复率截图」已上传=ok / 未上传=fail
      · 中评 / 差评分开判定，各自对应表格独立字段，不合并成「中差评」一项

    参数 shops = aggregate() 的结果（全表聚合），name = 门店全名或短名。
    """
    agg = agg_for(shops, name)
    bad_n, mid_n, short = detail_of(name)
    has_bad, has_mid = bad_n > 0, mid_n > 0

    # ★ 以门店上传的「中差评截图」为准：截图显示「暂无评价」→ 今日无中差评，
    #    覆盖看板（看板可能滞后一天 / 串店），此时中评、差评均为「— 无需」。
    if (has_bad or has_mid) and _reviews_empty(agg):
        has_bad, has_mid = False, False

    # 今日无差评 → 差评「— 无需」（不打 ✅）；有差评 → 填了实质内容✅、
    # 空或「无 / 没有 / 为空」类否定反馈 → ❌（未反馈差评）
    bad = "na" if not has_bad else (
        "ok" if (agg["bad_text"] and not bad_text_is_none(agg["bad_text"])) else "fail")
    # 中评：今日无中评 → 「— 无需」；有中评 → 截图里必须看得到申诉状态
    mid_ok, mid_why = (mid_verdict(agg) if has_mid else (True, ""))
    mid = "na" if not has_mid else ("ok" if mid_ok else "fail")
    # 回复率：全部 26 家（不含寮步城市店）门店都必须，下载截图 OCR —— 5 分钟 100% + 1 分钟 100%
    rate_ok, rate_why = rate_verdict(agg)
    rate = "ok" if rate_ok else "fail"

    reasons = []
    if bad == "fail":
        reasons.append("差评反馈未填写")
    if mid == "fail":
        reasons.append(mid_why if has_mid else "中评回复申诉反馈未填写")
    if rate == "fail":
        reasons.append(rate_why)

    return {
        "has_bad": has_bad, "has_mid": has_mid,
        "bad": bad, "mid": mid, "rate": rate,
        "reasons": reasons, "detail": (bad_n, mid_n, short),
        "manager": agg.get("manager", ""),
        "manager_open_id": agg.get("manager_open_id", ""),
        "store": name,          # 封板后未反馈区块按门店名展示（不显示人名）
        "tm": agg.get("tm", ""),
        # 兼容旧键（api / 前端旧版）
        "回复率": rate == "ok", "差评": bad != "fail", "中评": mid != "fail",
    }


def collect_failures(shops):
    """
    【审核】只针对「已反馈」的门店判定 ❌（未反馈门店不统计进来，留给 22:00 第 3 张卡片）。
    审核在满 5 家反馈后、或 23:59 补漏审核时执行。
    返回 [(展示短名, judge, reasons)]，同一门店合并去重。
    """
    merged = OrderedDict()
    # 【排序 2026-11-09 用户要求】待整改名单（卡片④ / 卡片③内联）同样按加盟类型排：
    # T 加盟在前、M 加盟在后；只排序，不做 T/M 分类分组。
    for store in sort_by_tm(list(shops)):     # shops = aggregate()：只有已提交过记录的门店
        j = judge(store, shops)
        rs = list(j["reasons"])               # 中评 / 差评 / 回复率 三维度里的 ❌ 原因
        if not rs:
            continue
        n = _norm(store)
        if n not in merged:
            merged[n] = [_short(store), j, rs]
        else:
            for r in rs:
                if r not in merged[n][2]:
                    merged[n][2].append(r)
    return [tuple(v) for v in merged.values()]


def unfed_entries(shops):
    """【旧三段式】22:00 未反馈名单：中评 / 差评 / 回复率三组。
    保留兼容；新两段式模板改用 unfed_grouped()，本函数不再参与线上卡片。
    """
    g1, g2, g3 = [], [], []
    for short in DETAIL_SHOPS:              # 中评 / 差评：只在今日有中差评的门店里找
        j = judge(short, shops)
        if j["mid"] == "fail":
            g1.append(j)
        if j["bad"] == "fail":
            g2.append(j)
    for full in ALL_SHOPS:                  # 回复率：全部门店都必须
        j = judge(full, shops)
        if j["rate"] == "fail":
            g3.append(j)
    return g1, g2, g3


def _mgr_key(j):
    """店长归并键：优先 open_id，其次店长姓名，最后回退空串。"""
    return j.get("manager_open_id") or j.get("manager") or ""


def unfed_grouped(shops):
    """22:00 未反馈统计【按店长归并】，判定仍全部走 judge()（改判 / 自动收缩不变）。

    ① 中差评未反馈名单：今日「有中评 / 有差评」的门店所属店长，把
       「中评 / 差评 / 回复率」三项里没反馈的项写在 @店长 后面的括号里；
       哪个没反馈就写哪个、三项全部没反馈就写「均未反馈」，同一店长只 @ 一次。
       其中「回复率」也一并统计（有无差评 + 回复率都算进来）。
    ② 回复率截图未反馈名单：全部 26 家（不含寮步城市店）里回复率仍未反馈的店长，只 @ 店长、不加标注；
       已在①里统计过回复率的店长不再二次列出（避免同一店长被 @ 两次）。

    返回 (g1_rows, g2_js)：
      g1_rows = [(judge, 标注文本), ...]   标注文本如「（差评未反馈）」
      g2_js   = [judge, ...]              ② 待 @ 的店长
    """
    bucket = OrderedDict()
    # 一次遍历即可覆盖中差评与回复率：judge(全名) 内部会归一匹配当日中差评明细
    for full in ALL_SHOPS:
        j = judge(full, shops)
        agg = agg_for(shops, full)
        k = _mgr_key(j) or full
        b = bucket.get(k)
        if b is None:
            b = {"j": j, "mid": False, "bad": False, "rate": False, "has_review": False}
            bucket[k] = b
        elif j.get("manager_open_id") and not b["j"].get("manager_open_id"):
            b["j"] = j                      # 尽量用带 open_id 的记录来 @
        if j.get("has_bad") or j.get("has_mid"):
            b["has_review"] = True
        b["mid"] = b["mid"] or j["mid"] == "fail"
        b["bad"] = b["bad"] or j["bad"] == "fail"
        # 【回复率未反馈口径 2026-11-08】= 未上传回复率截图（rate_files==0）；
        # 已提交但不达标归「待整改」，不算未反馈（提交即改判移出）。
        b["rate"] = b["rate"] or (agg.get("rate_files", 0) == 0)

    g1_rows, g1_keys = [], set()
    for k, b in bucket.items():
        if not b["has_review"]:             # ① 只针对今日有中差评的门店所属店长
            continue
        miss = [x for x, flag in (("中评", b["mid"]), ("差评", b["bad"]),
                                  ("回复率", b["rate"])) if flag]
        if not miss:
            continue
        if len(miss) == 3:
            label = "（中评、差评和回复率均未反馈）"
        elif len(miss) == 2:
            label = "（%s和%s未反馈）" % (miss[0], miss[1])
        else:
            label = "（%s未反馈）" % miss[0]
        g1_rows.append((b["j"], label))
        g1_keys.add(k)

    # ② 回复率未反馈：去掉①里已出现的店长（其回复率已被①统计，不二次写）
    g2_js = [b["j"] for k, b in bucket.items() if b["rate"] and k not in g1_keys]
    return g1_rows, g2_js


def at_people(js, use_at=True, plain_store=False, mute_key=""):
    """正常态：不列门店名、不做对齐换行，直接真 @ 店长。

    【2026-11-09 用户要求】封板后（use_at=False + plain_store=True）不再显示人名，
    改为显示【门店名】文本 —— 只用于「未反馈」区块；已反馈统计里的审核不过名单仍用人名。
    """
    if not js:
        return "<font color='grey'>无</font>"
    out = []
    for j in js:
        if mute_key and _mgr_key(j) == str(mute_key):
            out.append(_plain_name(_name_of(j)))   # 本条 @ 降级为文本（其余仍真 @）
        elif use_at and j.get("manager_open_id"):
            out.append(at_tag(j["manager_open_id"], j["manager"]))
        elif plain_store:
            nm = j.get("store") or (j.get("detail") or ("", "", ""))[2]
            out.append(_plain_store(nm))
        else:
            out.append(_plain_name(_name_of(j)))
    return " ".join(out)


def unfed_elements(shops, use_at=True, title="今日未反馈统计", compact=False,
                   with_rate=True, plain_store=False):
    """22:00 未反馈统计【按店长归并】（只 @ 店长，不列门店名）。

    ① 中差评未反馈名单：每个店长 @ 一次，括号里写明他具体哪几项没反馈
       （中评 / 差评 / 回复率）；三项全没反馈写「均未反馈」。
    ② 回复率截图未反馈名单：只 @ 店长、不加标注；①里已统计过回复率的店长不再二次列出。

    【2026-11-09 用户要求】回复率截图未反馈只在卡片 2（16:00 起）出现，
    卡片⑤ 不再重复列 —— 传 with_rate=False 即只输出 ① 段，避免同一店长一晚被 @ 两次。

    数据仍来自 judge() 实时判定 → 补交后下一拍自动收缩 / 自动改判，逻辑不变。
    compact 参数保留兼容旧调用，两段式下两处版面一致。
    """
    g1_rows, g2_js = unfed_grouped(shops)
    head = [
        {"tag": "hr"},
        _md("**%s**  <font color='grey'>（不列门店，直接 @ 店长；补交后自动消失）</font>" % title),
    ]
    if g1_rows:
        g1 = "\n".join("%s%s" % (at_people([j], use_at, plain_store), label)
                       for j, label in g1_rows)
    else:
        g1 = "<font color='grey'>无</font>"
    out = head + [_md("**① 中差评未反馈名单 · %d 人**\n%s" % (len(g1_rows), g1))]
    if with_rate:
        out += [
            {"tag": "hr"},
            _md("**② 回复率截图未反馈名单 · %d 人**\n%s"
                % (len(g2_js), at_people(g2_js, use_at, plain_store))),
        ]
    return out


def rate_unfed_managers(shops):
    """【未反馈 = 未上传回复率截图】返回仍未上传回复率截图的店长列表（按店长去重）。

    口径（2026-11-08 用户要求「提交即自动改判」）：
      · 店长只要提交了回复率截图，就视为【已反馈】→ 立刻从"未反馈"名单移出（自动改判）；
      · 截图是否达到 100% 由「待整改 / 审核」判定，并在待整改区块单独 @ 店长整改，
        不再在"未反馈"名单里重复 @（避免"提交了还当未反馈"）。

    判定用 judge() 的 manager / manager_open_id 供 @，用 agg 的 rate_files 判定是否已上传。

    【排序 2026-11-09】T 加盟门店排在前、M 加盟门店排在后（只排序，不做 T/M 分类分组）；
    组内保持 ALL_SHOPS 原有先后顺序。
    """
    out, seen = [], set()
    for full in ALL_SHOPS:
        agg = agg_for(shops, full)
        if agg.get("rate_files", 0) > 0:
            continue                      # 已上传回复率截图 → 已反馈，自动移出未反馈名单
        j = judge(full, shops)
        k = _mgr_key(j)
        if k and k not in seen:
            seen.add(k)
            out.append((full, j))
    out.sort(key=lambda p: tm_rank(p[0]))
    for full, j in out:
        j["store"] = full          # 封板后「回复率未反馈」要按门店名展示
    return [j for _, j in out]


def _rate_block_on():
    """「回复率截图未反馈」区块是否显示（每天 16:00 起，插在卡片 2 最下方）。

    【2026-11-09 用户要求】从 22:00/卡片3 改为 16:00/卡片2。
    判定不能只看 hour：跨天后（0-8 点冻结、8:00-14:15 仍挂着昨天的卡）区块要保留，
    因此用「main_date 是否还是旧日期」兜底 —— 只要还没发当天新卡，就视为仍处于该卡的
    16:00 之后阶段；14:15 发新卡后 main_date=today，16:00 前自然不显示。
    """
    t = now()
    if t.hour >= 16:
        return True
    try:
        st = load_state()
    except Exception:
        return False
    md = st.get("main_date") or ""
    return bool(md) and md != t.strftime("%Y-%m-%d")


def _late_night():
    """是否已进入「当天夜间阶段」（22:00 起：未反馈名单 该显示了）。

    不能只用 now().hour >= 22：到 00:00 跨天后 hour 变 0，会让区块突然消失、
    封板兜底刷新把卡片刷成「没有未反馈统计」的残缺版。
    因此额外用状态记忆：当天一旦封板（day_closed == main_date）或已改名
    （card2_renamed_date == main_date），就视为仍处于该卡的夜间阶段，
    直到次日 14:15 发新卡（main_date 变了）才复位。
    """
    if now().hour >= 22:
        return True
    try:
        st = load_state()
    except Exception:
        return False
    md = st.get("main_date") or ""
    if not md:
        return False
    return st.get("day_closed") == md or st.get("card2_renamed_date") == md


def reply_rate_unfed_block(shops, use_at=True, plain_store=False, mute_key=""):
    """卡片 2 最下方的「未反馈统计（回复率截图未反馈）」区块（每天 16:00 起显示）。

    【2026-11-09 用户要求】原先在卡片 3（22:00 起），现改为插在【卡片 2 最下方】、16:00 起显示；
    该区块下方只保留一个「反馈」按键（卡片 2 本来就只有一个反馈键，不会新增第二个）。
    紧贴未反馈名单（中差评）之后、反馈按键之前，直接 @ 出【回复率截图仍未反馈】的店长。
    仅 16:00 之后显示（用户口径：16 点起把回复率截图未反馈的门店 @ 出来）。
    该区块参与「卡片 2 @刷新」：use_at=False 时只留灰色 @文本、use_at=True 时重新 @。
    格式：@店长（只 @ 店长，不附带任何文本），所有店长一排连排。
    全部门店都要反馈回复率截图；已反馈门店不出现；补交后下一拍自动收缩、@ 自动取消。

    【未反馈口径 2026-11-08】= 未上传回复率截图；店长一提交即自动移出（自动改判），
    已提交但不达标归「待整改」处理，不在本名单重复 @。
    """
    if not _rate_block_on():
        return []
    js = rate_unfed_managers(shops)
    if not js:
        return [_md("**未反馈统计（回复率截图未反馈）**  "
                    "<font color='grey'>（全部门店已提交回复率截图 ✅）</font>")]
    # 【2026-11-08 用户要求】@店长不换行：所有未反馈店长一排连排在同一行（空格分隔）。
    lines = at_people(js, use_at, plain_store, mute_key)
    return [
        _md("**未反馈统计（回复率截图未反馈）**  "
            "<font color='grey'>（提交即自动消失）</font>"),
        _md(lines),
    ]


def _count_card3_at(shops):
    """统计卡片 3 本轮 @ 的店长处数（待整改），仅用于日志。

    「回复率截图未反馈」已移至卡片 2（16:00 起），不再计入卡片 3。
    """
    return len(collect_failures(shops))


# ---------------------------------------------------------------- 卡片渲染
def _md(content):
    return {"tag": "markdown", "content": content}


def _mark(v):
    """把 ok/fail/na 渲染成 ✅ / ❌ / — 无需。"""
    return {"ok": OK, "fail": NO, "na": NA}[v]


def _cnt_brief(mid_n, bad_n):
    """「中评 x 条 / 差评 y 条」文案。

    【2026-11-09 用户要求】0 条的项**不显示、不统计**：
    只有中评就只写「中评 x 条」，只有差评就只写「差评 y 条」，都为 0 返回空串。
    """
    parts = []
    if int(mid_n or 0):
        parts.append("中评 %d 条" % int(mid_n))
    if int(bad_n or 0):
        parts.append("差评 %d 条" % int(bad_n))
    return " / ".join(parts)


# ---------------------------------------------------------------- 已反馈统计分页
STATS_PAGE_SIZE = 10          # 每张「已反馈统计」卡最多放 10 家，超出自动分到下一张卡
_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def cn_index(i):
    """0 → ①、1 → ② …；超过 20 用 (21) 表示。"""
    if 0 <= int(i) < len(_CIRCLED):
        return _CIRCLED[int(i)]
    return "(%d)" % (int(i) + 1)


def stats_pages(shops, size=None):
    """已反馈门店按 T→M 排序后，每 size 家分一页（= 一张卡）。

    【2026-11-09 用户要求】已反馈 > 10 家就把第 11 家起脱离到下一张卡，
    > 20 家再分第三张，一直分下去（不做 T/M 分类，只在页内保持 T 在前 M 在后）。
    返回 [[store, ...], ...]；无门店时返回 [[]]，仍保留第一张卡。
    """
    size = int(size or STATS_PAGE_SIZE)
    ordered = sort_by_tm(list(shops))
    if not ordered:
        return [[]]
    return [ordered[i:i + size] for i in range(0, len(ordered), size)]


def stats_elements(shops, audited=False, use_at=True, mode="trial", compact=False,
                   with_rectify=True, page_stores=None, page_idx=0, total=None,
                   mute_key=""):
    """
    【统计板块 · 只统计已反馈门店】新版模板（用户口径）：
      · 不显示「已反馈✅」字样；未反馈门店不列进来
      · 每家门店一个块：
          【门店名称：xxx店】
          回复率截图 ✅/❌，中评 ✅/❌（今日有无中评 → 依据卡 2 同一份中差评明细）
          差评：删除 x 条，申诉 x 条，无法处理 x 条
      · 差评条数来自店长填写的「差评反馈」文本，按关键字自动归类：
          已删除 / 删除… → 删除；已审批 / 申诉中 / 申诉掉… → 申诉；
          无 / 没有 / 为空 → 不做统计；其他 → 无法处理
      · 有差评的门店反馈「无 / 没有 / 为空」或未填 → 判 ❌ 未反馈差评（自动进待整改）
      · 审核后有 ❌ → 「待整改 · 已 @店长」区块（只列已反馈门店里的 ❌）
    """
    els = []
    n_total = len(shops) if total is None else int(total)
    page_stores = sort_by_tm(list(shops)) if page_stores is None else list(page_stores)
    if not n_total:
        els.append(_md("<font color='grey'>暂无门店提交反馈，等待店长填写…</font>"))
        return els
    if not page_stores:
        els.append(_md("<font color='grey'>本卡暂无门店。</font>"))
        return els

    blocks = []
    for store in page_stores:
        short = _short(store)
        j = judge(store, shops)
        agg = agg_for(shops, store)
        # 昨日中评 / 差评条数（来源同卡片 2 的中差评明细；judge.detail = (差评, 中评, 短名)）
        d_bad, d_mid = int(j["detail"][0]), int(j["detail"][1])
        # 【2026-11-09 用户要求】昨日无中差评的也要写出来；0 条的项本身不统计条数
        _cnt = _cnt_brief(d_mid, d_bad)
        cnt_txt = ("昨日" + _cnt) if _cnt else "昨日无中评差评"
        # 首行：门店 + 昨日条数 + 回复率截图（+ 中评状态，0 条不写）
        # 【2026-11-09 用户要求】不对的问题直接在已反馈里 @店长，不再单列「待整改」区块
        line = "**【%s】** %s · 回复率截图 %s" % (short, cnt_txt, _mark(j["rate"]))
        if d_mid:
            line += " · 中评 %s" % _mark(j["mid"])
        rs = list(j.get("reasons") or [])
        if rs:
            tag = (at_tag(j["manager_open_id"], j["manager"]) if use_at
                   else _plain_name(_name_of(j)))
            if mute_key and _mgr_key(j) == str(mute_key):
                tag = _plain_name(_name_of(j))     # 本条 @ 降级为文本
            line += " %s <font color='red'>%s</font>" % (tag, "；".join(rs))
        # 第二行：只有「差评反馈」换行；删除/申诉/无法处理 里 0 的项不显示不统计
        bad_line = ""
        if j["has_bad"]:
            bad_txt = agg.get("bad_text", "") or ""
            d, a, u, none = bad_feedback_breakdown(bad_txt)
            if none:
                bad_line = ("差评：%s <font color='red'>未反馈差评</font>"
                            "（店长填「无 / 没有 / 为空」或未填）" % NO)
            else:
                _p = []
                if d:
                    _p.append("删除 %d 条" % d)
                if a:
                    _p.append("申诉 %d 条" % a)
                if u:
                    _p.append("无法处理 %d 条" % u)
                if _p:
                    bad_line = "差评：" + "，".join(_p)
        blocks.append(line + (("\n" + bad_line) if bad_line else ""))
    for b in blocks:
        els.append(_md(b))
    return els


def rectify_elements(shops, use_at=True):
    """待整改 · 已 @店长 区块（仅列出审核未通过的已反馈门店）。供卡片 3 / 卡片 4 复用。"""
    fails = collect_failures(shops)
    if not fails:
        return [{"tag": "markdown",
                 "content": "**%s 已反馈门店全部审核通过，无 ❌ 项**" % OK}]
    wl = []
    for name, j, rs in fails:
        tag = (at_tag(j["manager_open_id"], j["manager"]) if use_at
               else _plain_name(_name_of(j)))
        wl.append("%s **%s** 今日反馈有误：%s" % (tag, name, " / ".join(rs)))
    return [{"tag": "markdown",
             "content": "**待整改 · 已 @店长**（%d 家）\n" % len(fails) + "\n".join(wl)}]


def _form_btn(text, typ):
    """表单入口按键（统一跳转反馈表单）。"""
    return {"tag": "button", "text": {"tag": "plain_text", "content": text},
            "type": typ, "width": "fill",
            "behaviors": [{"type": "open_url", "default_url": BT["form_share_url"]}]}


def _todo_markdown(use_at=True):
    # @逐条刷新波期间不用真 @所有人（否则每一条 PATCH 都会重复提醒全体成员）
    if _at_wave_active():
        use_at = False
    _atall = "<at id=all></at>" if use_at else "@所有人"
    return {"tag": "markdown", "content":
            "**今日待办：** " + _atall + "\n"
            "1 差评处理（今日有差评的门店 → 填「差评反馈」）\n"
            "2 中评回复 + 申诉完成（今日有中评的门店 → 传「中评回复申诉反馈」）\n"
            "3 全部门店都要反馈「回复率截图」（今日 5 分钟、1 分钟回复率均需 100%）"}


def feedback_block(shops, audited=False, use_at=True, mode="trial", with_todo=True,
                   can_submit=True, closed=False, submit_on_card3=False, with_rectify=True,
                   page_idx=0, page_stores=None, total=None, sync_ts="",
                   mute_key=""):
    """「已反馈统计①/②…」卡正文（每 10 家一张卡，超出自动分页）。

      · 第 ① 张（page_idx=0）：今日待办 + 本页已反馈统计 + 「反馈提交 / 重交」按键；
      · 第 ② 张起：只放本页门店的统计内容，无待办、无按键；
      · 审核不过的门店直接在该行 @ 店长并标红原因（不再有「待整改」独立区块）；
      · closed=True（23:59 封板）：内容全部保留，只把按键换成封板说明。
    """
    page_stores = list(page_stores if page_stores is not None else shops)
    els = []
    if with_todo and page_idx == 0:
        els += [_todo_markdown(use_at=use_at), {"tag": "hr"}]
    els += stats_elements(shops, audited=audited, use_at=use_at, mode=mode, compact=False,
                          with_rectify=with_rectify, page_stores=page_stores,
                          page_idx=page_idx, total=total, mute_key=mute_key)
    els += [{"tag": "hr"}]
    if page_idx == 0:
        if closed:
            els += [{"tag": "markdown", "content":
                     "<font color='grey'>今日 23:59 已封板 · 本卡内容全部保留，"
                     "「提交」「重交」按键已关闭；明日 14:15 发新卡。</font>"}]
        elif can_submit:
            els += [_form_btn("重交", "default"), {"tag": "hr"}]
            if submit_on_card3:
                els += [_form_btn("中差评处理 / 回复率100%反馈", "primary_filled")]
        else:
            els += [{"tag": "markdown", "content":
                     "<font color='grey'>今日 23:59 已封板 · 提交与重交按键已关闭。</font>"}]
    if closed:
        _bottom = "**今日已封板 · 结果不再改变**"
    elif page_idx == 0:
        _bottom = "**提交后自动统计 / 改判**"
    else:
        _bottom = "**接上页 · 每 10 家一张卡**"
    els += [
        {"tag": "markdown", "text_align": "center", "content": _bottom},
        {"tag": "markdown", "text_align": "center", "content":
            "<font color='grey'>最近同步 %s</font>"
            % (sync_ts or now().strftime("%m-%d %H:%M:%S"))},
    ]
    return els


def build_handoff_card(shops, audited=False, use_at=True, mode="trial", legacy=False,
                       can_submit=True, closed=False, submit_on_card3=False,
                       with_rectify=True, page_idx=0, page_stores=None, total=None,
                       sync_ts="", mute_key=""):
    """「已反馈统计①/②/③…」卡：每 10 家已反馈门店一张，超出自动分页。

    【2026-11-09 用户要求】
      · 卡片③ 改名「已反馈统计①」、卡片④ 改名「已反馈统计②」，依次 ⑤ ⑥ …；
      · 已反馈 > 10 家 → 第 11 家起脱离到下一张卡；> 20 家再分第三张，一直分下去；
      · 取消「待整改」独立卡：审核不过的问题直接在各门店块里 @ 店长并标红原因；
      · 第 ① 张保留「今日待办 + 反馈提交 / 重交按键」，第 ② 张起只有统计内容、无按键。
    """
    page_stores = list(page_stores if page_stores is not None else shops)
    n_total = len(shops) if total is None else int(total)
    # 【2026-11-09 用户要求】封板卡不再真 @：@店长 一律降级为灰色姓名文本（不带店名）
    if closed:
        use_at = False
    tag = "试运行 · 仅发本人" if mode == "trial" else "正式运行 · 星级店长群"
    _no = cn_index(page_idx)
    _from = page_idx * STATS_PAGE_SIZE + 1
    _to = _from + len(page_stores) - 1
    _range = ("本卡 %d-%d 家" % (_from, _to)) if page_stores else "本卡暂无门店"
    if closed:
        title = "已反馈统计%s（已封板）" % _no
        subtitle = ("23:59 已封板 · 内容全部保留、仅关闭按键 · 共 %d 家 · %s"
                    % (n_total, _range))
        template = "grey"
    else:
        title = "已反馈统计%s" % _no
        subtitle = ("共 %d 家 · %s · 每 10 秒自动统计 · 审核不过直接 @店长"
                    % (n_total, _range))
        template = "turquoise"
    icon, tag_color = "chat-history_colorful", "blue"
    elements = feedback_block(shops, audited=audited, use_at=use_at, mode=mode,
                              can_submit=can_submit, closed=closed,
                              submit_on_card3=submit_on_card3, with_rectify=with_rectify,
                              page_idx=page_idx, page_stores=page_stores, total=n_total,
                              sync_ts=sync_ts, mute_key=mute_key)
    return {
        "schema": "2.0",
        "config": {"update_multi": True, "width_mode": "default"},
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "subtitle": {"tag": "plain_text", "content": subtitle},
            "template": template,
            "icon": {"tag": "standard_icon", "token": icon},
            "text_tag_list": [{"tag": "text_tag",
                               "text": {"tag": "plain_text", "content": tag},
                               "color": tag_color}]},
        "body": {"direction": "vertical", "padding": "12px 12px 14px 12px",
                 "vertical_spacing": "medium", "elements": elements},
    }


def stats_card(shops, page_idx=0, pages=None, **kw):
    """按分页构建第 page_idx 张「已反馈统计」卡（不传 pages 则按 10 家自动分页）。"""
    pages = pages if pages is not None else stats_pages(shops)
    page_stores = pages[page_idx] if 0 <= page_idx < len(pages) else []
    return build_handoff_card(shops, page_idx=page_idx, page_stores=page_stores,
                              total=len(shops), **kw)


def _stats_card_ids(st):
    """已反馈统计卡的 message_id 列表（[0]=①、[1]=②…）。

    兼容两个旧字段：handoff_message_id（第①张）与 rectify_card_id
    （旧的「待整改分离卡」——已取消，其消息位置直接复用为第②页）。
    """
    ids = [x for x in (st.get("stats_card_ids") or []) if x]
    hid = st.get("handoff_message_id") or ""
    if hid and hid not in ids:
        ids.insert(0, hid)
    rid = st.get("rectify_card_id") or ""
    if rid and rid not in ids:
        ids.append(rid)
    return ids


def _set_stats_card_ids(st, ids):
    """写回分页卡 id 列表，并同步 handoff_message_id（= 第①张，兼容旧代码）。"""
    ids = [x for x in ids if x]
    st["stats_card_ids"] = ids
    if ids:
        st["handoff_message_id"] = ids[0]


def _img_col(img_key, title, alt):
    """并排图的一列：左右各留 26px 空白，让两张图在半宽里再缩一圈。"""
    return {"tag": "column", "width": "weighted", "weight": 1, "vertical_align": "top",
            "padding": "0px 26px",
            "elements": [{"tag": "img", "img_key": img_key,
                          "alt": {"tag": "plain_text", "content": alt},
                          "title": {"tag": "plain_text", "content": title},
                          "scale_type": "fit_horizontal", "corner_radius": "4px"}]}


def pending_review_entries(shops):
    """今日「待反馈中评 / 差评处理」门店 → 按店长归并（只 @ 店长、不列门店名）。

    数据来自当天中差评明细看板（DETAIL_SHOPS：今日各门店中评 / 差评条数，
    已剔除智慧门店渠道 —— 那些中评 / 差评不需要门店回复，故不 @ 也不统计），
    与门店是否已提交反馈无关 —— 这是早上的「今天要处理哪些店」待办清单，
    区别于 22:00 的「中评 / 差评未反馈」统计。同一店长管多家店只 @ 一次。
    """
    g_mid, g_bad = [], []
    n_mid_shops, n_bad_shops = 0, 0
    seen_mid, seen_bad = set(), set()
    for short in DETAIL_SHOPS:
        bad_n, mid_n, matched = detail_of(short)
        info = _empty_agg(matched or short)
        j = {"manager": info.get("manager", ""),
             "manager_open_id": info.get("manager_open_id", "")}
        key = j["manager_open_id"] or j["manager"] or short
        if mid_n > 0:
            n_mid_shops += 1
            if key not in seen_mid:
                seen_mid.add(key)
                g_mid.append(j)
        if bad_n > 0:
            n_bad_shops += 1
            if key not in seen_bad:
                seen_bad.add(key)
                g_bad.append(j)
    # 标题用真实门店数；@ 名单按店长去重，避免同一店长管多店被重复 @
    return g_mid, g_bad, (n_mid_shops, n_bad_shops)


def pending_review_columns(shops, use_at=True):
    """【已废弃·保留兼容】旧版两栏并排；卡片 2 现改用单栏 pending_review_detail()。"""
    g_mid, g_bad, (n_mid, n_bad) = pending_review_entries(shops)

    def col(title, js, n):
        return {"tag": "column", "width": "weighted", "weight": 1,
                "vertical_align": "top", "padding": "8px 10px",
                "elements": [
                    _md("**%s**（%d 家）" % (title, n)),
                    _md(at_people(js, use_at)),
                ]}

    return {"tag": "column_set", "flex_mode": "none",
            "horizontal_spacing": "small", "background_style": "grey-50",
            "columns": [col("今天待反馈中评处理的门店", g_mid, n_mid),
                        col("今天待反馈差评处理的门店", g_bad, n_bad)]}


def store_feedback_done(name, shops):
    """门店的【中差评维度】是否已反馈 —— 决定卡片 2「未反馈名单（中差评）」是否移除它。

    【必须按维度判定，不能只看「shops 里有这条门店」】
    表单一次提交可能只填了「回复率截图」，此时 aggregate 里已有该门店，
    若按旧逻辑直接判「已反馈」，会把中差评还没处理的门店从名单里错误删掉
    （2026-11-09 自查发现的「过早改判」：厚街万达店 / 厚街汀山店只交了回复率）。

    正确口径：
      · 差评反馈文本非空，或 中评回复申诉反馈附件数 > 0 → 中差评维度已反馈 → 移出名单；
      · 只交了回复率截图（bad_text 空、mid_files=0）→ 中差评仍未反馈 → 继续留在名单里被 @。
    内容写得是否合规由「待整改」审核，不在此处否决（与用户 2026-11-08 口径一致）。
    """
    agg = agg_for(shops or {}, name)
    if (agg.get("bad_text") or "").strip():
        return True
    if int(agg.get("mid_files") or 0) > 0:
        return True
    return False


def pending_review_detail_rows(shops):
    """「今日待反馈明细」数据：按店长归并，逐渠道列出中评 / 差评条数。

    只保留今日有中差评、且门店尚未完成中差评反馈的记录：
    门店一反馈，该店长的 @ 记录即从本卡自动取消（动态收缩）。
    渠道条数来自当天中差评明细看板的「渠道明细」（已剔除智慧门店渠道）。
    返回 [(店长key, [(渠道名, 中评数, 差评数), ...], info), ...]
    """
    out = []
    for short, v in DETAIL_SHOPS.items():
        bad_n, mid_n = int(v.get("差评", 0)), int(v.get("中评", 0))
        if not (bad_n or mid_n):
            continue
        # 【2026-11-08 用户口径】只要该门店已在卡片 3「已反馈统计」里出现，
        # 卡片 2 的「今日待反馈明细」就必须删除它（不再用 judge 的 ❌ 判定，
        # 避免已反馈门店仍被 @）。签名随之变化 → 卡片 2 原地刷新（不发新消息）。
        if store_feedback_done(short, shops):
            continue
        info = _empty_agg(short)
        key = info.get("manager_open_id") or info.get("manager") or short
        ch = v.get("渠道明细") or {}
        chans = []
        for cname, d in ch.items():
            m, b = int(d.get("中评", 0)), int(d.get("差评", 0))
            if m or b:
                chans.append((cname, m, b))
        if not chans:                        # 旧缓存 / 静态兜底无渠道明细时的降级
            chans = [(" / ".join(v.get("渠道") or []) or short, mid_n, bad_n)]
        out.append((key, chans, info))
    return out


def pending_detail_sig(shops):
    """卡片 2 内容签名：任一名单发生变化，都要触发卡片 2 原地刷新（否则不改判）。

    【2026-11-09 自查修复】旧签名只含「未反馈名单（中差评）」。
    16:00 起卡片 2 底部还有「未反馈统计（回复率截图未反馈）」@ 区块，
    店长补交回复率截图后该名单会收缩，但中差评行没变 → 签名不变 →
    poll_once 提前 return → 卡片 2 不重建 → 已反馈门店仍挂在"未反馈"里不改判。
    因此把回复率未反馈名单的店长 key 也纳入签名。
    """
    rows = pending_review_detail_rows(shops)
    sig1 = "|".join("%s:%s" % (k, ",".join("%s/%d/%d" % r for r in rs))
                    for k, rs, _ in rows)
    sig2 = ",".join(sorted((_mgr_key(j) or j.get("store") or "")
                           for j in rate_unfed_managers(shops)))
    return "%s##RATE##%s" % (sig1, sig2)


def _card2_late():
    """是否已进入「未反馈名单（中差评）」阶段。

    23:00 起为 True；并用 card2_renamed_date 记忆当天已改名，
    避免 00:00 跨天后标题退回「今日待反馈明细」（封板兜底刷新会重建卡片 2）。
    """
    if now().hour >= 23:
        return True
    try:
        st = load_state()
    except Exception:
        return False
    md = st.get("main_date") or ""
    return bool(md) and st.get("card2_renamed_date") == md


def pending_review_detail(shops, use_at=True, plain_store=False, mute_key=""):
    """单栏「今日待反馈明细」：取消原来的两栏并排。

    每个店长 @ 一次，后面逐渠道列出「渠道名称 中评 x 条 / 差评 x 条」，
    多个渠道换行缩进对齐；门店反馈后该 @ 记录自动取消。
    """
    rows = pending_review_detail_rows(shops)
    # 【2026-11-08 用户要求】23:00 起随未反馈汇总卡，把本栏标题改为「未反馈名单」
    # （该栏本就只含有中差评、且尚未反馈的门店；改名后与 23:00 汇总口径一致）。
    _late = _card2_late()
    # 【2026-11-08 用户要求】23:00 起的标题再补一个括号「（中差评）」，
    # 与卡片 3 的「未反馈统计（回复率截图未反馈）」区分：本栏是中差评维度。
    _head = "未反馈名单（中差评）" if _late else "今日待反馈明细"
    _hint = ("（截至 23:00 仍未反馈的中差评门店；按渠道列出）" if _late
             else "（按渠道列出；门店反馈后自动取消 @ 记录）")
    els = [_md("**%s**  <font color='grey'>%s</font>" % (_head, _hint))]
    if not rows:
        els.append(_md("<font color='grey'>今日有中差评的门店均已反馈，暂无待反馈明细。</font>"))
        return els
    lines = []
    for key, chans, info in rows:
        if mute_key and str(key) == str(mute_key):
            tag = _plain_name(_name_of({"manager": info.get("manager"),
                                        "manager_open_id": key}))
        elif use_at and str(key).startswith("ou_"):
            tag = at_tag(key, info.get("manager", ""))
        elif plain_store:
            tag = _plain_store(info.get("store") or key)
        else:
            tag = _plain_name(_name_of({"manager": info.get("manager"),
                                        "manager_open_id": key}))
        c0, m0, b0 = chans[0]
        # 【2026-11-09 用户要求】0 条的项不显示不统计（如「中评 0 条」不再出现）
        lines.append("%s：%s %s" % (tag, c0, _cnt_brief(m0, b0)))
        for cname, m, b in chans[1:]:
            lines.append("　　%s %s" % (cname, _cnt_brief(m, b)))
    els.append(_md("\n".join(lines)))
    return els


def build_gallery_card(mode="trial", shops=None, use_at=True, can_submit=True,
                       closed=False, mute_key=""):
    """第 2 张卡片：两张并排缩略图（保持并行）+ 单栏「今日待反馈明细」。

    两图各占一半宽度、再各留 26px 空白缩一圈；点单张可看原图。
    下方【取消并行】改为单栏明细：按店长 @ + 逐渠道中评/差评条数，
    门店反馈后自动取消对应 @ 记录。
    本卡不放「每日反馈统计」、也不放「待整改」——统一归卡片 ③。

    【2026-11-08 用户要求】待反馈明细（含 23:00 后改名的「未反馈名单」）下方
    常驻一个「反馈」按键，方便店长就地提交；该键只在 23:59 封板（can_submit=False）
    时随其它按键一起消失。
    """
    # 【2026-11-09 用户要求】封板（can_submit=False）后不再真 @：改成灰色姓名文本
    if not can_submit:
        use_at = False
    star_key = S.star_image_key()          # 当日已上传的顾客满意明细图
    board_key = board_image_key(BOARD_DATE)  # 当日中差评明细图
    tag = "试运行 · 仅发本人" if mode == "trial" else "正式运行 · 星级店长群"

    _detail = pending_review_detail(shops or {}, use_at=use_at, plain_store=closed,
                                    mute_key=mute_key)
    # 【2026-11-09 用户要求】「回复率截图未反馈」16:00 起插在本卡【最下方】——
    # 位置：未反馈名单（中差评）之后、反馈按键之前；全卡仍只有这一个反馈按键。
    _rate = reply_rate_unfed_block(shops or {}, use_at=use_at, plain_store=closed,
                                   mute_key=mute_key)
    if _rate:
        _detail += [{"tag": "hr"}] + _rate
    if can_submit:
        _detail += [{"tag": "hr"},
                    _form_btn("反馈（中评 / 差评 / 回复率）", "primary_filled")]
    elements = [
        {"tag": "column_set", "flex_mode": "none", "horizontal_spacing": "medium",
         "columns": [_img_col(star_key, "① 顾客满意明细", "顾客满意明细截图"),
                     _img_col(board_key, "② 中差评明细", "中差评明细截图")]},
        {"tag": "hr"},
    ] + _detail
    return {
        "schema": "2.0",
        "config": {"update_multi": True, "width_mode": "default"},
        "header": {
            "title": {"tag": "plain_text", "content": "② 顾客满意 + 中差评明细（并排）"},
            "subtitle": {"tag": "plain_text", "content":
                         "数据日期 %s · 两图并排缩略 + 今日待反馈明细（单栏，按渠道列条数）"
                         % BOARD_DATE},
            "template": "orange",
            "icon": {"tag": "standard_icon", "token": "image_colorful"},
            "text_tag_list": [{"tag": "text_tag",
                               "text": {"tag": "plain_text", "content": tag},
                               "color": "blue"}]},
        "body": {"direction": "vertical", "padding": "12px 12px 14px 12px",
                 "vertical_spacing": "medium", "elements": elements},
    }


def build_merged_card(mode="trial", legacy=False):
    """第 3 张卡被第 4 张接管后的占位卡：正文全部删除，只留一句提示。

    B 分支（22:00 补发第 4 张完整卡）专用：第 3 张卡上的今日待办、每日反馈统计、
    待整改、未反馈、两个按键全部移除，只保留「统计结果已合并下方卡片。」，
    避免同一份统计在群里出现两遍、也避免旧卡上的按键继续被点。
    """
    title = ("今日反馈统计与待整改 · 中差评和回复率反馈" if legacy
             else "③ 今日待办 / 每日反馈统计 / 待整改")
    tag = "试运行 · 仅发本人" if mode == "trial" else "正式运行 · 星级店长群"
    return {
        "schema": "2.0",
        "config": {"update_multi": True, "width_mode": "default"},
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "subtitle": {"tag": "plain_text", "content": "内容已合并到下方第 4 张卡"},
            "template": "grey",
            "icon": {"tag": "standard_icon", "token": "chat-history_colorful"},
            "text_tag_list": [{"tag": "text_tag",
                               "text": {"tag": "plain_text", "content": tag},
                               "color": "blue"}]},
        "body": {"direction": "vertical", "padding": "16px 12px 20px 12px",
                 "vertical_spacing": "medium",
                 "elements": [
                     {"tag": "markdown", "text_align": "center",
                      "content": "<font color='grey'>统计结果已合并下方卡片。</font>"},
                 ]},
    }


def _clean_review_text(t):
    """评价原文清洗：保留内容本身，只做卡片 markdown 安全处理。

    · 去掉零宽字符 / 折叠内部换行（避免撑破排版）
    · 空占位（"-" / "此用户未填写评价内容" / 空白）→ 明确写「未填写评价内容」
    · 转义 < > &，避免评价里的符号被当成卡片标签解析
    · 极端超长（>400 字）才截断，正常情况下 135 字以内的原文完整复制粘贴
    """
    t = (t or "").replace("\u200b", "").strip()
    t = re.sub(r"\s+", " ", t)
    if not t or t in ("-", "—", "–", "此用户未填写评价内容", "无", "null", "None"):
        return "（该条未填写评价内容）"
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if len(t) > 400:
        t = t[:400] + "…（原文过长，已截取前 400 字）"
    return t


def build_rectify_card(shops, use_at=True, mode="trial", closed=False):
    if closed:
        use_at = False
    """卡片 ④（待整改分离卡）：列「待整改 · 已 @店长」名单 + 重交按键（锁定待整改下方）。

    当卡片 ③ 的已反馈门店数超过 RECTIFY_SPLIT_THRESHOLD 时，由 poll_once 自动把
    「待整改」连同其下方的「重交」按键一起从卡片 ③ 分离出来、独立发成此卡（卡片 ④）。
    【2026-11-09】原 22:00「未反馈统计」卡（曾编号⑤）已删除，本卡即最后一张内容卡，
    之后只接 23:00 汇总卡。本卡每 10 秒原地刷新；23:59 封板时名单保留、重交键关闭。
    """
    tag = "试运行 · 仅发本人" if mode == "trial" else "正式运行 · 星级店长群"
    els = rectify_elements(shops, use_at=use_at)
    if closed:
        els += [
            {"tag": "hr"},
            _md("<font color='grey'>今日 23:59 已封板 · 本卡保留完整待整改名单"
                "（已反馈统计见卡片③）；重交按键已关闭，本卡不再更新。</font>"),
        ]
    else:
        els += [
            {"tag": "hr"},
            _form_btn("重交", "default"),
            {"tag": "hr"},
            _md("<font color='grey'>本卡片由卡片③「每日反馈统计」中分离而出"
                "（已反馈门店数 &gt; %d 家时自动生成）；重交按键锁定在待整改下方 · 每 10 秒自动刷新。</font>"
                % RECTIFY_SPLIT_THRESHOLD),
        ]
    return {
        "schema": "2.0",
        "config": {"update_multi": True, "width_mode": "default"},
        "header": {
            "title": {"tag": "plain_text", "content": "④ 待整改 · 已 @店长"},
            "subtitle": {"tag": "plain_text",
                         "content": ("23:59 已封板 · 重交键已关闭 · 已反馈统计见卡片③"
                                     if closed else
                                     "已反馈门店数 > %d 家时从卡片③分离 · 每 10 秒自动刷新"
                                     % RECTIFY_SPLIT_THRESHOLD)},
            "template": "orange",
            "icon": {"tag": "standard_icon", "token": "remind_colorful"},
            "text_tag_list": [{"tag": "text_tag",
                               "text": {"tag": "plain_text", "content": tag},
                               "color": "blue"}]},
        "body": {"direction": "vertical", "padding": "12px 12px 14px 12px",
                 "vertical_spacing": "medium", "elements": els},
    }


def build_unfed_only_card(shops, use_at=True, mode="trial", can_submit=True,
                          closed=False, audited=True, renumbered=False):
    if closed:
        use_at = False
    """【已停用 · 2026-11-09】第 4 张卡（22:00 独立卡）：只保留「今日未反馈统计」+ 反馈提交按键。

    用户已删除这张卡：22:00 不再新发任何消息，群里最后一张业务卡是 ④ 待整改，
    最后一条消息是 23:00「未反馈门店汇总」。本函数仅保留给历史数据 / 老链路兜底，
    线上调度不再调用（summary_message_id 恒为空）。

    按用户要求：本卡不复制、不合并第 3 张卡内容，只列「① 中差评未反馈名单」
    （按店长归并、括号写明具体哪几项没反馈，含差评 + 回复率）。
    【2026-11-09 用户要求】原「② 回复率截图未反馈名单」已删除 —— 该名单只在卡片 2
    （16:00 起）出现，本卡不再重复 @，避免同一店长一晚被 @ 两次。
    + 反馈提交按键（反馈按键已从第 3 张卡下移至此）。重交按键跟随待整改，本卡不放。
    · closed=True（23:59 封板版）：把第 3 张卡删掉的「待整改」合并到本卡，
      并删除反馈提交按键（当日不再改判）。
    · renumbered=True：待整改已分离成独立卡片 ④ 时，本卡顺延编号为 ⑤。
    """
    tag = "试运行 · 仅发本人" if mode == "trial" else "正式运行 · 星级店长群"
    # 【2026-11-09 用户要求】本卡只保留 ① 中差评未反馈；回复率截图未反馈只在卡片 2（16:00 起）
    els = unfed_elements(shops, use_at=use_at, compact=True, with_rate=False,
                         plain_store=closed)
    if els and els[0].get("tag") == "hr":
        els = els[1:]                     # 卡片顶部不需要额外分割线
    els += [{"tag": "hr"}]
    if closed:
        # 23:59：待整改从卡片 3 合并到此处
        els += [{"tag": "hr"}]
        els += rectify_elements(shops, use_at=use_at)  # 已反馈审核名单：仍只写人名
        els += [
            {"tag": "hr"},
            {"tag": "markdown", "content":
                "<font color='grey'>今日 23:59 已封板 · 未反馈统计与待整改已合并至此卡片，"
                "反馈提交按键已关闭；明日 14:15 发新卡。</font>"},
            {"tag": "hr"},
            {"tag": "markdown", "text_align": "center",
             "content": "**今日已封板 · 结果不再改变**"},
        ]
    else:
        els += [
            _form_btn("中差评处理 / 回复率100%反馈", "primary_filled"),
            {"tag": "hr"},
            {"tag": "markdown", "text_align": "center", "content": "**提交后自动统计 / 改判**"},
        ]
    els += [{"tag": "markdown", "text_align": "center",
             "content": "<font color='grey'>最近同步 %s</font>"
                        % now().strftime("%m-%d %H:%M:%S")}]
    tail = ("每 %d 秒自动统计 · 补交后名单自动收缩"
            % SCHED.get("stats_interval_seconds", 10))
    no = "⑤" if renumbered else "④"
    return {
        "schema": "2.0",
        "config": {"update_multi": True, "width_mode": "default"},
        "header": {
            "title": {"tag": "plain_text", "content": "%s 今日未反馈统计" % no},
            "subtitle": {"tag": "plain_text",
                         "content": ("23:59 已封板 · 待整改已合并至此 · 反馈按键已关闭"
                                     if closed else
                                     "%s 22:00 · 只 @ 店长不列门店 · %s · 反馈提交按键在本卡下方"
                                     % (no, tail))},
            "template": "red",
            "icon": {"tag": "standard_icon", "token": "remind_colorful"},
            "text_tag_list": [{"tag": "text_tag",
                               "text": {"tag": "plain_text", "content": tag},
                               "color": "red" if mode == "live" else "blue"}]},
        "body": {"direction": "vertical", "padding": "12px 12px 14px 12px",
                 "vertical_spacing": "medium", "elements": els},
    }


def build_summary_card(shops, audited=True, use_at=True, mode="trial", with_stats_block=False):
    """【老链路遗留】「今日未反馈统计」独立卡片（2026-11-09 起线上不再发送）。

    当前链路：22:00 不发卡；回复率未反馈只在卡片 2（16:00 起），
    中差评未反馈只在卡片 2 的「未反馈名单（中差评）」，
    23:00 最后发一张「未反馈门店汇总」。本函数仅为历史兼容保留。
    """
    tag_txt = "试运行 · 仅发本人" if mode == "trial" else "正式运行 · 星级店长群"
    elements = unfed_elements(shops, use_at=use_at)[1:]   # 卡片顶部不需要 hr
    elements += [
        {"tag": "hr"},
        {"tag": "markdown", "content":
            "<font color='grey'>请以上门店于 24:00 前补交；23:59 将全部重新审核一遍（补漏审核），"
            "补交后名单自动消失。</font>"},
    ]
    if with_stats_block:
        elements += [{"tag": "hr"}]
        elements += stats_elements(shops, audited=audited, use_at=use_at, mode=mode)
        elements += [
            {"tag": "hr"},
            _form_btn("中差评处理 / 回复率100%反馈", "primary_filled"),
            {"tag": "hr"},
            _form_btn("重交", "default"),
        ]
    return {
        "schema": "2.0",
        "config": {"update_multi": True, "width_mode": "default"},
        "header": {
            "title": {"tag": "plain_text", "content": "今日未反馈统计"},
            "subtitle": {"tag": "plain_text",
                         "content": "数据日期 %s · 只 @ 店长不列门店 · 每 %d 秒自动统计 / 每 %d 秒自动审核"
                                    % (BOARD_DATE, SCHED.get("stats_interval_seconds", 10),
                                       SCHED["audit_interval_seconds"])},
            "template": "red",
            "icon": {"tag": "standard_icon", "token": "remind_colorful"},
            "text_tag_list": [{"tag": "text_tag",
                               "text": {"tag": "plain_text", "content": tag_txt}, "color": "red"}]},
        "body": {"direction": "vertical", "padding": "12px 12px 14px 12px",
                 "vertical_spacing": "medium",
                 "elements": elements},
    }


def build_trial_summary_card(n=None, use_at=False):
    """
    试运行专用：随机 5~10 家样例，完整预览第 3 张卡片
    （每日反馈统计 + 待整改 @店长 + 提交/重交按键 + 旧三段式未反馈统计样例）。
    历史样例卡，未被调用；线上 22:00 卡片模板已改为两段式（unfed_elements）。
    不读真实多维表格。
    """
    if n is None:
        n = random.randint(5, 10)
    pool = list(ALL_SHOPS)
    random.shuffle(pool)
    picks = pool[:min(n, len(pool))]

    STATE_POOL = [
        ("fail", "fail", "fail"),
        ("ok", "fail", "fail"),
        ("fail", "ok", "fail"),
        ("fail", "fail", "ok"),
        ("ok", "ok", "ok"),
        ("ok", "ok", "fail"),
    ]

    rows = []
    for full in picks:
        mid, bad, rate = random.choice(STATE_POOL)
        info = _manager_match(full)
        rows.append((full, mid, bad, rate,
                     info.get("店长", manager_name(full)),
                     info.get("open_id", manager_open_id(full))))

    def mk(v):
        return OK if v == "ok" else NO

    def at_of(mgr, moid):
        return at_tag(moid, mgr) if use_at else _plain_name(mgr)

    stat_lines = ["**%s**，已反馈%s · 中评 %s · 差评 %s · 回复率 %s"
                  % (_short(r[0]), OK, mk(r[1]), mk(r[2]), mk(r[3])) for r in rows]

    fails, wl = [], []
    for full, mid, bad, rate, mgr, moid in rows:
        rs = []
        if mid == "fail":
            rs.append("中评回复申诉反馈未填写")
        if bad == "fail":
            rs.append("差评反馈未填写")
        if rate == "fail":
            rs.append("回复率未达 100%（5分钟 / 1分钟需同时 100%）")
        if rs:
            fails.append(full)
            wl.append("%s **%s** 今日反馈有误：%s"
                      % (at_of(mgr, moid), _short(full), " / ".join(rs)))

    def block(items):
        return "\n".join(items) if items else "<font color='grey'>无</font>"

    g1 = ["**%s**，中评未反馈　%s" % (_short(r[0]), at_of(r[4], r[5])) for r in rows if r[1] == "fail"]
    g2 = ["**%s**，差评未反馈　%s" % (_short(r[0]), at_of(r[4], r[5])) for r in rows if r[2] == "fail"]
    g3 = ["**%s**，回复率截图未反馈　%s" % (_short(r[0]), at_of(r[4], r[5])) for r in rows if r[3] == "fail"]

    form_url = BT["form_share_url"]

    def btn(text, typ):
        return {"tag": "button", "text": {"tag": "plain_text", "content": text},
                "type": typ, "width": "fill",
                "behaviors": [{"type": "open_url", "default_url": form_url}]}

    # 历史样例版面：先未反馈三段，再接过卡片 2 的统计 / 整改 / 按键
    elements = [
        _md("**中评未反馈**（今日有中评未传申诉凭证）\n" + block(g1)),
        {"tag": "hr"},
        _md("**差评未反馈**（今日有差评未填差评反馈）\n" + block(g2)),
        {"tag": "hr"},
        _md("**回复率截图未反馈 / 未达标**（全部 %d 家）\n" % len(ALL_SHOPS) + block(g3)),
        {"tag": "hr"},
        {"tag": "markdown", "content":
            "<font color='grey'>（以上为试运行随机样例，非真实门店反馈情况）</font>"},
        {"tag": "hr"},
        {"tag": "div", "text_size": "large",
         "text": {"tag": "lark_md",
                  "content": "**每日反馈统计**  <font color='grey'>（每10秒自动完成统计）</font>"}},
        _md("\n".join(stat_lines)),
        {"tag": "hr"},
        _md(("**待整改 · 已 @店长**（%d 家）\n" % len(fails) + "\n".join(wl)) if wl
            else "**%s 已反馈门店全部审核通过，无 ❌ 项**" % OK),
        {"tag": "hr"},
        btn("中差评处理 / 回复率100%反馈", "primary_filled"),
        {"tag": "hr"},
        btn("重交", "default"),
        {"tag": "hr"},
        {"tag": "markdown", "content":
            "<font color='grey'>重交自动改判 · 每 10 秒重新统计并审核 · 最近同步 %s · 试运行随机样例</font>"
            % now().strftime("%m-%d %H:%M:%S")},
    ]
    return {
        "schema": "2.0",
        "config": {"update_multi": True, "width_mode": "default"},
        "header": {
            "title": {"tag": "plain_text",
                      "content": "今日中差评和审核统计未反馈统计（试运行 · 随机样例）"},
            "subtitle": {"tag": "plain_text",
                         "content": "试运行样例 · 随机生成 %d 条（非真实统计）" % len(picks)},
            "template": "red",
            "icon": {"tag": "standard_icon", "token": "remind_colorful"},
            "text_tag_list": [{"tag": "text_tag",
                               "text": {"tag": "plain_text", "content": "试运行 · 仅发本人"}, "color": "red"}]},
        "body": {"direction": "vertical", "padding": "12px 12px 14px 12px",
                 "vertical_spacing": "medium", "elements": elements},
    }


# ---------------------------------------------------------------- 演示数据（样式预览用，不写库）
def demo_shops():
    """两区块统计的 5 家门店演示态（含 ✅ / ❌ / — 无需 三种状态），仅用于把效果发给本人确认。"""
    picks = OrderedDict([
        ("厚街万达店", dict(bad="已逐条联系顾客并补救", mid=0, rate=1)),     # 有差评无中评：差评✅ 中评—
        ("虎门新沙埔店", dict(bad="已致歉并补偿", mid=1, rate=1)),          # 有差评有中评：全✅
        ("寮步牛杨店", dict(bad="", mid=1, rate=0)),                        # 无差评有中评：中评✅ 回复率❌
        ("寮步万联百货店", dict(bad="已处理差评", mid=0, rate=1)),          # 有差评有中评：中评❌
        ("厚街大汇下汴店", dict(bad="", mid=0, rate=0)),                    # 有差评有中评：全❌
    ])
    out = OrderedDict()
    for short, v in picks.items():
        full = short
        for k in MANAGER:
            if _norm(k) == _norm(short):
                full = k
                break
        info = _manager_match(full)
        out[full] = {
            "store": full, "creator_open_id": "",
            "manager": info.get("店长", manager_name(full)),
            "tm": manager_tm(full),
            "manager_open_id": info.get("open_id", manager_open_id(full)),
            "bad_text": v["bad"], "mid_files": v["mid"], "rate_files": v["rate"],
            "records": 1, "last_ts": 0,
        }
    return out


# ---------------------------------------------------------------- 主流程
def send_main(mode="trial", demo=True, audited=None, sink=print, reuse_message_id=None):
    """第 2 张卡片：当天已有卡片时只做原地编辑（PATCH），绝不新发消息。"""
    st = load_state()
    today = now().strftime("%Y-%m-%d")
    load_today_detail(refresh=True)      # 先读取中差评明细（当天实时）
    log("已读取中差评明细：数据日期 %s · 今日有中评/差评门店 %d 家 · 来源 %s"
        % (BOARD_DATE, len(DETAIL_SHOPS), DETAIL_SOURCE), sink)
    # 当天中差评明细截图：抓取 + 上传，卡片引用当天 image_key（避免群里一直显示旧图）
    if mode == "live" and not demo:
        try:
            old = board_image_key(BOARD_DATE)
            new = refresh_board_image(BOARD_DATE)
            if new and new != old:
                log("中差评明细图已更新为 %s 当日图片（image_key=%s）" % (BOARD_DATE, new), sink)
        except Exception as e:
            log("中差评明细图更新失败（沿用上一张）：%s" % str(e)[:120], sink)
    shops = aggregate(fetch_records(), biz_date=now().strftime("%Y-%m-%d"))
    use_at = (mode == "live")
    if audited is None:
        audited = bool(demo)          # 演示态直接展示完整审核效果
    # 卡 2：两张并排缩略图（保持并行）+ 单栏「今日待反馈明细」（按渠道列条数、反馈后取消 @）
    card = build_gallery_card(mode=mode, shops=shops, use_at=use_at)

    reuse = reuse_message_id or st.get("main_message_id")
    reused = bool(reuse) and st.get("main_mode") == mode and st.get("main_date") == today
    if reused:
        j = patch_card(reuse, card)
        if j.get("code") != 0:
            raise RuntimeError("第 2 张卡片原地编辑失败（未新发）：%s" % j.get("msg"))
        mid = reuse
        log("第 2 张卡片已原地编辑：message_id=%s（未新发消息）" % mid, sink)
    else:
        j = send_card(card, mode)
        if j.get("code") != 0:
            raise RuntimeError("第 2 张卡片发送失败：%s" % j.get("msg"))
        mid = (j.get("data") or {}).get("message_id", "")
        log("第 2 张卡片已发出：mode=%s message_id=%s" % (mode, mid), sink)

    st = load_state()
    if mode != "live":
        # 试运行只发本人预览：绝不覆盖正式群的卡片跟踪状态
        # （否则一次试运行就会把 main_message_id / 第 3 张卡状态改成私聊的卡，
        #   导致群里第 2、3 张卡停止刷新、22:00 也补不到群卡上）
        st["trial_message_id"] = mid
        st["trial_ts"] = now().strftime("%Y-%m-%d %H:%M:%S")
        save_state(st)
        return {"ok": True, "message_id": mid, "mode": mode, "demo": bool(demo),
                "edited": reused, "audited": bool(audited), "shops": len(shops),
                "detail_shops": len(DETAIL_SHOPS), "all_shops": len(ALL_SHOPS),
                "trial_preview": True}
    st["main_message_id"] = mid
    st["main_mode"] = mode
    st["main_date"] = today
    st["day_closed"] = None            # 新一天的卡 → 解除封板
    st["demo"] = bool(demo)
    st["main_sent_ts"] = now().strftime("%Y-%m-%d %H:%M:%S")
    st["main_card_ver"] = CARD_VER
    st["main_layout"] = "gallery2"
    st["main_img_key"] = board_image_key(BOARD_DATE)
    st["last_sig"] = _sig(fetch_records())       # 演示态也记录真实签名，避免立刻被空数据刷新
    st["audited"] = bool(audited)
    st["detail_date"] = S.yesterday()            # 今天已读取过明细，避免轮询重复刷新
    st["final_date"] = today
    st["final_done"] = False                     # 新一天 → 23:59 补漏审核重新生效
    st["warned_sig"] = ""
    st["last_audit_run"] = ""
    st["last_stats_ts"] = ""
    if not reused:
        # 新的一天 / 换了模式 → 清空当日第 3 张卡与 22:00 补统计状态，避免沿用昨天的旧卡
        for k in ("handoff_message_id", "handoff_date", "handoff_mode",
                  "handoff_ts", "slot3_kind",
                  "evening_date", "evening_mode", "evening_ts",
                  "slot4_message_id", "slot4_date", "slot4_mode", "slot4_ts",
                  "summary_message_id", "summary_date", "summary_mode",
                  "summary_ts", "fb_summary_key",
                  "rectify_split", "rectify_card_id", "rectify_ts"):
            st[k] = ""
        st["handoff_shops"] = 0
    save_state(st)
    return {"ok": True, "message_id": mid, "mode": mode, "demo": bool(demo),
            "edited": reused, "audited": bool(audited), "shops": len(shops),
            "detail_shops": len(DETAIL_SHOPS), "all_shops": len(ALL_SHOPS)}


def send_handoff_card(mode="live", sink=print, force=False):
    """第 3 张卡「今日待办 / 每日反馈统计 / 待整改 + 两个按键」。

    触发：紧跟第 2 张卡发出（run_combined 连发链路），不再等「已反馈满 10 家」。
    当天同模式已有卡 3 → 只 PATCH 原地刷新，不新发消息；
    trial：只发本人私聊预览，绝不写正式群的卡片跟踪状态。
    """
    st = load_state()
    today = now().strftime("%Y-%m-%d")
    shops = aggregate(fetch_records(), biz_date=st.get("main_date") or today)
    if mode == "trial" and not shops:
        shops = demo_shops()
    use_at = (mode == "live")
    legacy = (st.get("main_date") or "") < NEW_FLOW_FROM
    # 卡片 4（22:00 独立卡）是否已发出：没发则反馈提交键留在卡片 3，发出后移到卡片 5
    evening_done = (st.get("evening_date") == today and st.get("evening_mode") == mode)
    # 【2026-11-09 分页】第①张「已反馈统计①」= 前 10 家；> 10 家的页由 poll_once 追加
    pages = stats_pages(shops)
    card = stats_card(shops, page_idx=0, pages=pages, audited=True, use_at=use_at,
                      mode=mode, legacy=legacy, submit_on_card3=not evening_done)
    hid = st.get("handoff_message_id") or ""
    reuse = (bool(hid) and st.get("handoff_date") == today
             and st.get("handoff_mode") == mode and not force)
    if reuse:
        j = patch_card(hid, card)
        if j.get("code") != 0:
            raise RuntimeError("第 3 张卡原地编辑失败（未新发）：%s" % j.get("msg"))
        mid, edited = hid, True
        log("第 3 张卡已原地编辑（未新发）：%s" % mid, sink)
    else:
        j = send_card(card, mode)
        if j.get("code") != 0:
            raise RuntimeError("第 3 张卡发送失败：%s" % j.get("msg"))
        mid, edited = (j.get("data") or {}).get("message_id", ""), False
        log("第 3 张卡紧跟第 2 张发出：mode=%s message_id=%s · 已反馈 %d 家"
            % (mode, mid, len(shops)), sink)
    if mode == "live":
        st = load_state()
        st["handoff_message_id"] = mid
        st["handoff_date"] = today
        st["handoff_mode"] = mode
        st["handoff_ts"] = now().strftime("%Y-%m-%d %H:%M:%S")
        st["handoff_shops"] = len(shops)
        # 分页卡列表：① 就是这张；②③… 由 poll_once 按 10 家一页自动追加
        _old = [x for x in (st.get("stats_card_ids") or []) if x and x != mid]
        st["stats_card_ids"] = [mid] + _old
        if not reuse:
            st["slot3_kind"] = "stats"
        save_state(st)
    return {"ok": True, "message_id": mid, "edited": edited,
            "shops": len(shops), "mode": mode}


def _refresh_closed_card(st, sink=print):
    """23:59 封板后：把带按键的卡片刷成「无提交按键」版（每天只做一次）。

    正常在 23:59 那一拍就完成；若服务错过 / 重启，下一次轮询会补做，保证封板后
    第 3 张卡（以及 22:00 补发的那张完整卡）上不再有「中差评处理 / 回复率100%反馈」
    和「重交」两个按键。
    """
    day = st.get("day_closed") or ""
    if not day or st.get("closed_card_ts") == day:
        return False
    hid = st.get("handoff_message_id") or ""
    if st.get("slot3_kind") in ("merged", "revoked"):
        hid = ""          # 第 3 张卡已被撤回/清空，无需再刷
    mid2 = st.get("main_message_id") or ""     # 第 2 张卡（常驻「反馈」键，封板要删）
    sid = st.get("summary_message_id") or ""
    # 独立「未反馈统计」卡（今晚旧值 full / 新逻辑 unfed 都覆盖）封板时删两个按键
    full_sid = sid if (sid and st.get("summary_kind") in ("full", "unfed")
                       and sid != hid) else ""
    # 待整改分离卡（卡片 ④）：封板时本卡内容合并进「未反馈统计」卡（卡片 ⑤），自身留一句说明
    rid = st.get("rectify_card_id") or ""
    # 23:00「未反馈门店汇总」卡：只有属于本业务日的那条才刷（避免去改昨天的卡）
    said = st.get("summary_at_message_id") or ""
    if said and st.get("summary_at_date") != day:
        said = ""
    if said in (hid, sid):
        said = ""
    if not hid and not full_sid and not rid and not mid2 and not said:
        st["closed_card_ts"] = day
        save_state(st)
        return False
    try:
        _recs = fetch_records()
        shops = aggregate(_recs, biz_date=st.get("main_date"))
        mmode = st.get("main_mode", "trial")
        legacy = (st.get("main_date") or "") < NEW_FLOW_FROM
        # 【2026-11-09 用户要求】封板刷新的卡片一律不真 @：@店长 → 灰色姓名文本（不带店名）
        use_at = False
        done = True
        # 【2026-11-09 分页】把每一张「已反馈统计①/②…」都刷成封板版（关闭所有按键）
        _pages = stats_pages(shops)
        for _i, _mid in enumerate(_stats_card_ids(st)):
            if not _mid:
                continue
            j = patch_card(_mid, stats_card(shops, page_idx=_i, pages=_pages, audited=True,
                                            use_at=use_at, mode=mmode, legacy=legacy,
                                            closed=True, can_submit=False))
            if j.get("code") != 0:
                log("封板「已反馈统计%s」刷新失败（下个节拍重试）：%s"
                    % (cn_index(_i), j.get("msg")), sink)
                done = False
        if full_sid:
            card2 = build_unfed_only_card(shops, use_at=use_at, mode=mmode,
                                          can_submit=False, closed=True, audited=True,
                                          renumbered=bool(st.get("rectify_split")))
            j2 = patch_card(full_sid, card2)
            if j2.get("code") != 0:
                log("封板补发卡刷新失败（下个节拍重试）：%s" % j2.get("msg"), sink)
                done = False
        if mid2 and mid2 not in (_stats_card_ids(st) + [full_sid]):
            j4 = patch_card(mid2, build_gallery_card(mode=mmode, shops=shops,
                                                     use_at=use_at, can_submit=False,
                                                     closed=True))
            if j4.get("code") != 0:
                log("封板卡片 2 刷新失败（下个节拍重试）：%s" % j4.get("msg"), sink)
                done = False
        # 23:00 汇总卡：封板最后一刷，把数字定格并标注「已封板」（之后不再更新）
        if said:
            j5 = patch_card(said, build_summary_at_card(shops, closed=True, date_str=day,
                                                       records=_recs))
            if j5.get("code") != 0:
                log("封板汇总卡刷新失败（下个节拍重试）：%s" % j5.get("msg"), sink)
                done = False
        if not done:
            return False
        st["closed_card_ts"] = day
        save_state(st)
        log("23:59 封板：卡片已删除「提交」「重交」「反馈」按键（%s%s%s%s%s）"
            % (hid or "-", "、" + full_sid if full_sid else "",
               "、" + rid if rid else "", "、" + mid2 if mid2 else "",
               "、汇总卡已定格" if said else ""), sink)
        return True
    except Exception as e:
        log("封板卡片刷新异常（下个节拍重试）：%s" % e, sink)
        return False


def poll_once(sink=print, force=False):
    """
    每秒调用：读取多维表格 → 有变更就重算「只统计已反馈门店」的统计板块 → 原地刷新卡片（不重发）。
    审核触发：每 15 秒（audit_interval_seconds）周期性审核，或 23:59 补漏审核（无视阈值全部重审一遍）。
    补交：任何新记录到达即重算，❌ 自动改 ✅。
    """
    st = load_state()
    # 快照：末尾只写「本拍改动过的键」，避免用旧快照整体覆盖掉
    # 20:00 / 22:00 调度线程刚写入的 evening_* / summary_* / dm_* 字段
    st0 = json.loads(json.dumps(st))
    if not st.get("main_message_id"):
        return {"ok": False, "reason": "尚未发送第 2 张卡片"}

    # 封板：23:59 之后结果不再改变
    #  · 00:00-07:59 → 新一天 8 点前的反馈不记录、不改判
    #  · 已封板且还在同一张卡上 → 一律不动，等次日 14:15 新卡
    _t0 = now()
    if st.get("day_closed"):
        _refresh_closed_card(st, sink)     # 兜底：错过 23:59 那一拍也保证按键被删掉
    if _t0.hour < BIZ_DAY_START_HOUR:
        return {"ok": True, "changed": False, "frozen": True,
                "shops": st.get("last_shops", 0),
                "reason": "封板时段 00:00-%02d:00：提交不记录、不改判" % BIZ_DAY_START_HOUR}
    if st.get("day_closed") and st.get("day_closed") == st.get("main_date"):
        return {"ok": True, "changed": False, "frozen": True, "closed": True,
                "shops": st.get("last_shops", 0),
                "reason": "%s 的反馈已封板（23:59 截止），结果不再改变" % st.get("day_closed")}

    records = fetch_records()
    sig = _sig(records)
    shops = aggregate(records, biz_date=st.get("main_date"))
    n_shops = len(shops)

    t = now()
    today = t.strftime("%Y-%m-%d")
    dirty = False
    if st.get("detail_date") != S.yesterday():
        # 仅在日期真正变化时刷新一次中差评明细，并把标记落盘（避免每秒重复请求看板）
        load_today_detail(refresh=True)
        log("日期变化，重新读取中差评明细：%s · %d 家有中评/差评"
            % (BOARD_DATE, len(DETAIL_SHOPS)), sink)
        st["detail_date"] = S.yesterday()
        dirty = True
    if st.get("final_date") != today:
        # 每日重置补漏/告警标记
        st["final_done"] = False
        st["warned_sig"] = ""
        st["final_date"] = today
        dirty = True
    # 23:59 补漏审核：无视阈值全部重新审核一遍（当天一次）
    final = (t.hour == SCHED.get("audit_final_hour", 23)
             and t.minute == SCHED.get("audit_final_minute", 59))
    closing = final and not st.get("final_done")   # 本次轮询即 23:59 封板那一拍
    # 审核改为「每 15 秒执行一次」，不再以「满 5 家反馈」为阈值
    audit_interval = SCHED.get("audit_interval_seconds", 15)
    periodic_due = _sec_since(st.get("last_audit_run", "")) >= audit_interval
    sig_changed_now = sig != st.get("last_sig")
    if n_shops >= 1 and (periodic_due or sig_changed_now):
        audited = True
        st["last_audit_run"] = now().strftime("%Y-%m-%d %H:%M:%S")
        dirty = True
    elif n_shops >= 1:
        audited = bool(st.get("audited", False))   # 保持上一次审核态，避免栏目闪烁
    else:
        audited = False
    audited = audited or final
    # 【2026-11-09 用户要求】23:59 封板那一拍起不再真 @：@店长 降级为纯文本姓名
    use_at = (st.get("main_mode") == "live") and not closing

    # 统计每 10 秒刷新一次卡片（即使数据没变，也让「最近同步」时间走起来）
    stats_interval = SCHED.get("stats_interval_seconds", 10)
    stats_due = force or _sec_since(st.get("last_stats_ts", "")) >= stats_interval

    # 审核有 ❌ → @店长说明原因：只写进【同一张卡片】的整改区块，绝不新发消息
    fails = collect_failures(shops) if audited else []
    fail_sig = "|".join("%s:%s" % (name, "/".join(rs)) for name, j, rs in fails)
    fail_changed = bool(fails) and st.get("warned_sig") != fail_sig
    if audited and final and not st.get("final_done"):
        st["warned_sig"] = ""          # 23:59 补漏审核：全部重审，强制刷新一次整改区块
        fail_changed = True

    mmode = st.get("main_mode", "trial")
    today = now().strftime("%Y-%m-%d")
    # 22:00 单独发出的「今日未反馈统计」卡（与第 3 张卡是两条独立消息）
    sid = st.get("summary_message_id")
    sid_live = (bool(sid) and st.get("summary_date") == today
                and st.get("summary_mode") == mmode
                and st.get("evening_date") == today
                and sid != (st.get("handoff_message_id") or ""))

    # 第 3 张卡：满阈值时发出的「今日待办 / 每日反馈统计 / 待整改」；
    # 22:00 不新发第 4 张，直接在这张卡里补出「今日未反馈统计」（message_id 与位置不变）
    hid = st.get("handoff_message_id")
    hid_live = bool(hid) and st.get("handoff_date") == today and st.get("handoff_mode") == mmode
    kind3 = ((st.get("slot3_kind") or ("stats" if hid_live else "")) if hid_live else "")
    # 22:00 是否已单独发出「今日未反馈统计」卡（当天 + 同模式）
    evening_done = (st.get("evening_date") == today and st.get("evening_mode") == mmode)
    # 【2026-11-09 分页改造】「待整改」独立卡已取消（审核不过的问题直接在各门店块里 @店长）。
    # 已反馈统计改为每 10 家一张卡：①=handoff，> 10 家时自动新发 ②③…
    rectify_split = False
    split_just_done = False
    pages = stats_pages(shops)
    _ids = _stats_card_ids(st)

    # 兜底：卡 2 已发但卡 3 没发（连发时失败）→ 下一拍自动补发，
    # 不再要求「已反馈满 10 家」；正常情况第 3 张卡由 run_combined 紧跟卡 2 发出。
    if (not hid_live) and (st.get("main_date") or "") >= NEW_FLOW_FROM:
        try:
            _pg = stats_pages(shops)
            _j = send_card(stats_card(shops, page_idx=0, pages=_pg, audited=audited,
                                      use_at=use_at, mode=mmode, legacy=False,
                                      can_submit=not closing, closed=closing,
                                      submit_on_card3=not evening_done), mmode)
            _hid = (_j.get("data") or {}).get("message_id") or ""
            if _hid:
                hid, hid_live, kind3 = _hid, True, "stats"
                st["handoff_message_id"] = _hid
                st["handoff_date"] = today
                st["handoff_mode"] = mmode
                st["handoff_ts"] = now().strftime("%Y-%m-%d %H:%M:%S")
                st["handoff_shops"] = n_shops
                st["slot3_kind"] = "stats"
                st["stats_card_ids"] = [_hid] + [x for x in _ids if x and x != _hid]
                dirty = True
                log("卡 2 已发、卡 3 未发 → 兜底补发「已反馈统计①」卡片：%s" % _hid, sink)
        except Exception as e:
            log("第 3 张卡片发送失败（下个节拍自动重试）：%s" % e, sink)

    # layout：卡 2 恒为两图并排，只在第 3 张卡出现 / 版式变化时触发一次刷新
    layout = "handoff3" if hid_live else "gallery2"
    if (st.get("main_date") or "") < NEW_FLOW_FROM:
        layout = st.get("main_layout") or "handoff"   # 老链路不改版，避免每拍都判定为布局变化
    layout_changed = st.get("main_layout") != layout
    # 「今日待反馈明细」内容签名：门店反馈后明细收缩（取消 @ 记录）→ 触发卡片 2 原地刷新
    detail_sig_now = pending_detail_sig(shops)
    detail_changed = detail_sig_now != st.get("main_detail_sig")

    # 到点强制重建卡片 2（必须在提前返回之前算，否则内容没变就永远不触发）：
    #   16:00 把「回复率截图未反馈」插入卡片 2 最下方
    #   23:00 把标题「今日待反馈明细」改成「未反馈名单（中差评）」
    rename_due = (t.hour >= 23 and st.get("card2_renamed_date") != today)
    rate16_due = (t.hour >= 16 and st.get("rate16_date") != today)

    if (not stats_due and sig == st.get("last_sig")
            and not fail_changed and not layout_changed and not detail_changed
            and not rename_due and not rate16_due
            and not (final and not st.get("final_done")) and not split_just_done):
        if dirty:
            save_state(st)          # 关键：提前返回前也要落盘，否则标记永远写不进去
        return {"ok": True, "changed": False, "shops": n_shops, "audited": audited}

    sig_changed = sig != st.get("last_sig")
    ts_mark = now().strftime("%Y-%m-%d %H:%M:%S")   # 以「开始刷新」计时，节奏更接近整 10 秒
    refreshed = False
    closed_card_done = False      # 封板那一拍是否已把按键删干净（没删成 → 下拍补）

    # 第 2 张卡片（两张并排图 + 单栏今日待反馈明细）→
    # 图换了 / 版本变了 / 布局变了 / 明细变了（门店反馈后取消 @ 记录）时原地刷新
    img_now = board_image_key(BOARD_DATE)
    # 老链路（NEW_FLOW_FROM 之前的卡）保持原样，不因为改版去改它
    close2_due = closing   # 23:59 封板那拍：重建卡片2，把常驻的「反馈」键删掉
    need2 = (st.get("main_card_ver") != CARD_VER or layout_changed
             or st.get("main_img_key") != img_now or detail_changed
             or rename_due or rate16_due or close2_due)
    if (st.get("main_date") or "") < NEW_FLOW_FROM:
        need2 = False
    # @逐条刷新波期间不重建卡片，避免「删掉某一条 @」的中间态被 10 秒轮询覆盖
    if need2 and not _at_wave_active():
        try:
            if st["main_message_id"] not in LOCKED_TODAY_CARD_IDS:
                patch_card(st["main_message_id"],
                           build_gallery_card(mode=mmode, shops=shops, use_at=use_at,
                                              can_submit=not closing, closed=closing))
                refreshed = True
                st["main_card_ver"] = CARD_VER
                st["main_layout"] = layout
                st["main_img_key"] = img_now
                st["main_detail_sig"] = detail_sig_now
                if rename_due:
                    st["card2_renamed_date"] = today
                if rate16_due:
                    st["rate16_date"] = today
        except Exception as e:
            log("第 2 张卡片刷新失败：%s" % e, sink)

    # 【2026-11-09 分页】「已反馈统计①/②/③…」：每 10 家一张卡，逐页原地刷新；
    # 页数不够（已反馈 > 10 家）时自动新发下一张，第①张保留待办与按键，其余只放统计。
    if (hid_live and stats_due and kind3 not in ("summary", "merged", "revoked")
            and not _at_wave_active()):
        _legacy3 = (st.get("main_date") or "") < NEW_FLOW_FROM
        _pages = stats_pages(shops)
        _ids = _stats_card_ids(st)
        # ① 页数不足 → 新发（封板当天不再新增卡）
        while (len(_ids) < len(_pages)) and not st.get("day_closed"):
            _idx = len(_ids)
            try:
                _c = stats_card(shops, page_idx=_idx, pages=_pages, audited=audited,
                                use_at=use_at, mode=mmode, legacy=_legacy3,
                                can_submit=not closing, closed=closing,
                                submit_on_card3=not evening_done)
                _j = send_card(_c, mmode)
                _mid = (_j.get("data") or {}).get("message_id") or ""
                if not _mid:
                    log("新发「已反馈统计%s」失败：%s" % (cn_index(_idx), _j.get("msg")), sink)
                    break
                _ids.append(_mid)
                _set_stats_card_ids(st, _ids)
                dirty = True
                log("已反馈 %d 家 → 第 %d-%d 家脱离成「已反馈统计%s」新卡：%s"
                    % (n_shops, _idx * STATS_PAGE_SIZE + 1,
                       _idx * STATS_PAGE_SIZE + len(_pages[_idx]), cn_index(_idx), _mid), sink)
            except Exception as e:
                log("新发「已反馈统计%s」失败（下个节拍重试）：%s" % (cn_index(_idx), e), sink)
                break
        # ② 逐页刷新
        for _i, _mid in enumerate(_ids):
            _pg = _pages[_i] if _i < len(_pages) else []
            try:
                patch_card(_mid, stats_card(shops, page_idx=_i, pages=_pages,
                                            audited=audited, use_at=use_at, mode=mmode,
                                            legacy=_legacy3, can_submit=not closing,
                                            closed=closing,
                                            submit_on_card3=not evening_done))
                refreshed = True
                if closing:
                    closed_card_done = True
            except Exception as e:
                log("「已反馈统计%s」刷新失败：%s" % (cn_index(_i), e), sink)
        st["last_stats_ts"] = ts_mark

    # 22:00 发出的那张【独立】「今日未反馈统计」卡：每拍原地刷新（只保留未反馈统计
    # 板块），店长补交后名单自动收缩；封板那一拍再刷一次，把两个按键删掉。
    # 待整改分离后本卡顺延编号为 ⑤（renumbered=True）。
    # 无论是新逻辑的 summary_kind=unfed，还是今晚旧逻辑留下的 full，统一刷成新卡面。
    if (sid_live and stats_due and (not st.get("day_closed") or closing)
            and not _at_wave_active()):
        try:
            card_s = build_unfed_only_card(shops, use_at=use_at, mode=mmode,
                                           can_submit=not closing, closed=closing, audited=audited,
                                           renumbered=rectify_split)
            patch_card(sid, card_s)
            refreshed = True
            st["summary_ts"] = now().strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            log("22:00 未反馈统计卡刷新失败：%s" % e, sink)

    # 23:00「未反馈门店汇总」卡（新发的那条）：发出后由本循环接管，每拍原地刷新，
    # 店长补交 / 审核改判 → 三项家数立刻跟着变；23:59 封板那一拍再刷一次并标注「已封板」。
    # 【2026-11-09 用户要求】不再是一次性快照。
    said = st.get("summary_at_message_id") or ""
    if said and said in (sid, hid):        # 与卡片⑤/③ 同一条消息时不重复 patch
        said = ""
    if (said and stats_due
            and st.get("summary_at_date") == (st.get("main_date") or today)
            and (not st.get("day_closed") or closing)
            and not _at_wave_active()):
        try:
            patch_card(said, build_summary_at_card(
                shops, closed=closing, date_str=st.get("main_date") or today,
                records=records))
            refreshed = True
        except Exception as e:
            log("23:00 汇总卡刷新失败：%s" % e, sink)

    if audited and fails and fail_changed:
        brief = "；".join("%s：%s" % (name, "/".join(rs)) for name, j, rs in fails)
        log("审核有误 %d 家（原因已写入卡片整改区块并 @店长，未新发消息）：%s"
            % (len(fails), brief), sink)
        st["warned_sig"] = fail_sig
    elif audited and not fails:
        st["warned_sig"] = ""

    st["last_sig"] = sig
    st["last_poll_ts"] = now().strftime("%Y-%m-%d %H:%M:%S")
    st["last_shops"] = n_shops
    st["audited"] = bool(audited)
    if final:
        st["final_done"] = True
        st["final_audit_ts"] = now().strftime("%Y-%m-%d %H:%M:%S")
        st["day_closed"] = st.get("main_date") or today
        st["day_closed_ts"] = now().strftime("%Y-%m-%d %H:%M:%S")
        if closed_card_done:
            st["closed_card_ts"] = st["day_closed"]      # 按键已删除，兜底不再重复刷
        log("23:59 补漏审核完成：全部 %d 家已反馈门店重新审核一遍 → 今日结果封板，"
            "此后不再记录、不再改判%s"
            % (n_shops, "，第 3 张卡的提交 / 重交按键已删除" if closed_card_done else ""), sink)
    # 合并写：重新读磁盘最新状态，只覆盖本拍实际改动的键；
    # 调度线程并发写入的字段一律保留（否则 22:00 补发卡片会失去轮询接管）。
    latest = load_state()
    for k, v in st.items():
        if k not in st0 or st0.get(k) != v:
            latest[k] = v
    for k in list(st0):
        if k not in st and k in latest and latest.get(k) == st0.get(k):
            latest.pop(k, None)
    save_state(latest)
    return {"ok": True, "changed": True, "refreshed": refreshed,
            "sig_changed": sig_changed,
            "shops": n_shops, "audited": audited, "final_audit": bool(final)}


# ---------------------------------------------------------------- 群消息识别（补发前的权威判重）
# 本任务卡片标题指纹：群里今天出现过任意一张，就说明「今天的任务已经执行过」。
# 补发前必须读一次群消息做识别，绝不只依赖本地状态文件，防止「已经发了又补发一次」。
TASK_CARD_MARKERS = (
    "① 星级群每日追踪汇总",
    "② 顾客满意 + 中差评明细",
    "③ 今日待办",
    "④ 待整改",
    "未反馈门店汇总",
)


def group_task_cards_sent_today(max_pages=6, page_size=50):
    """识别星级店长群里【今天】是否已有本任务发出的卡片。

    返回 (state, detail)：
      · True  → 今天群里已有任务卡片，调用方必须放弃补发
      · False → 今天群里没有任务卡片，允许补发
      · None  → 群消息读取失败 / 超时（结果未知），调用方必须保守跳过补发

    识别依据：只看今天的 interactive 卡片消息，卡片正文含本任务标题指纹。
    既用 start_time/end_time 限定，又按 create_time 再过滤一次，双保险排除历史消息。
    """
    import urllib.parse
    try:
        tok = S.get_token()
        n = S.now()
        day0 = n.replace(hour=0, minute=0, second=0, microsecond=0)
        t0 = int(day0.timestamp())
        t1 = int(n.timestamp()) + 60
        page_token = ""
        hits, scanned = [], 0
        for _ in range(max_pages):
            path = ("/open-apis/im/v1/messages?container_id_type=chat&container_id=%s"
                    "&sort_type=ByCreateTimeDesc&page_size=%d&start_time=%d&end_time=%d"
                    % (LIVE["chat_id"], page_size, t0, t1))
            if page_token:
                path += "&page_token=" + urllib.parse.quote(page_token)
            j = _api("GET", path, tok, timeout=15)
            if j.get("code") != 0:
                return None, "读取群消息失败：%s" % j.get("msg", "")
            data = j.get("data") or {}
            for it in (data.get("items") or []):
                scanned += 1
                if it.get("deleted") or it.get("msg_type") != "interactive":
                    continue
                ct = int(it.get("create_time") or 0) // 1000
                if ct < t0 or ct > t1:          # 只认今天创建的消息
                    continue
                content = (it.get("body") or {}).get("content") or ""
                if any(m in content for m in TASK_CARD_MARKERS):
                    hits.append((it.get("message_id") or "", ct))
            if not data.get("has_more") or not data.get("page_token"):
                break
            page_token = data["page_token"]
        if hits:
            return True, ("群里今日已有 %d 张任务卡片（扫描 %d 条消息）：%s"
                          % (len(hits), scanned,
                             " / ".join(mid[:14] for mid, _ in hits[:5])))
        return False, "群里今日无任务卡片（扫描 %d 条消息）" % scanned
    except Exception as e:
        return None, "读取群消息异常：%s" % e


def _group_tail_message_id():
    """读取星级店长群最后一条消息的 message_id（跳过已撤回 / 系统消息）。读不到返回 ""。"""
    try:
        tok = S.get_token()
        j = _api("GET",
                 "/open-apis/im/v1/messages?container_id_type=chat&container_id=%s"
                 "&sort_type=ByCreateTimeDesc&page_size=10" % LIVE["chat_id"], tok)
        if j.get("code") != 0:
            log("读取群消息失败：%s" % j.get("msg"))
            return ""
        for it in (j.get("data") or {}).get("items") or []:
            if it.get("deleted"):
                continue
            return it.get("message_id") or ""
    except Exception as e:
        log("读取群消息异常：%s" % e)
    return ""


def run_evening_swap(mode="trial", sink=print, persist=None, force_new=None):
    """【已停用 · 2026-11-09】22:00 独立「今日未反馈统计」卡（曾编号 ⑤）—— 用户已删除，不再发送。

    线上调度只剩：14:15 发 ①②③、已反馈 > 10 家时分页 ④、16:00–23:50 每 10 分钟 @逐条刷新、
    23:00 新发「未反馈门店汇总」。本函数仅保留兼容旧入口（调度台按钮），调用不会新发卡片。
    """
    if persist is None:
        persist = (mode == "live")
    st = load_state()
    today = now().strftime("%Y-%m-%d")
    load_today_detail(refresh=True)
    shops = aggregate(fetch_records(), biz_date=st.get("main_date") or today)
    if mode == "trial" and not shops:
        shops = demo_shops()
    use_at = (mode == "live")
    # 待整改已分离成独立卡片 ④ 时，本卡顺延编号为 ⑤
    card = build_unfed_only_card(shops, use_at=use_at, mode=mode,
                                renumbered=bool(st.get("rectify_split")))

    # 当天同模式已发过独立卡 → 原地刷新，绝不新发；否则发一张新的独立卡
    sid = (st.get("summary_message_id") or "") if persist else ""
    sid_today = (persist and bool(sid) and st.get("summary_date") == today
                 and st.get("summary_mode") == mode)
    if sid_today:
        j = patch_card(sid, card)
        if j.get("code") != 0:
            raise RuntimeError("22:00 未反馈统计卡原地刷新失败：%s" % j.get("msg"))
        mid = sid
        log("22:00：当天独立卡已存在 → 原地刷新为「只保留未反馈统计」（不新发）：%s" % mid, sink)
    else:
        j = send_card(card, mode)
        if j.get("code") != 0:
            raise RuntimeError("22:00 未反馈统计卡发送失败：%s" % j.get("msg"))
        mid = (j.get("data") or {}).get("message_id", "")
        log("22:00：发一张独立的「今日未反馈统计」卡（只保留未反馈统计板块，"
            "卡片 3 保留待办 / 统计 / 整改、不合并）：%s" % mid, sink)

    if persist:
        st = load_state()
        st["evening_date"] = today
        st["evening_mode"] = mode
        st["evening_ts"] = now().strftime("%Y-%m-%d %H:%M:%S")
        st["fb_summary_key"] = today
        st["summary_kind"] = "unfed"       # 独立「未反馈统计」卡
        st["summary_message_id"] = mid
        st["summary_date"] = today
        st["summary_mode"] = mode
        st["summary_ts"] = st["evening_ts"]
        # 卡片 3 一律保持正常主卡：绝不写 merged / stats_evening，避免被清空或塞进未反馈
        if st.get("slot3_kind") in ("merged", "stats_evening"):
            st["slot3_kind"] = "stats"
        for k in ("slot4_message_id", "slot4_date", "slot4_mode", "slot4_ts"):
            st.pop(k, None)
        # 22:00 卡片 4 已发出 → 卡片 3 移除反馈提交键（只保留重交，锁定在待整改下方）
        hid = st.get("handoff_message_id") or ""
        if hid and hid != mid and st.get("slot3_kind") not in ("merged", "revoked"):
            try:
                _pg = stats_pages(shops)
                patch_card(hid, stats_card(shops, page_idx=0, pages=_pg, audited=True,
                                           use_at=use_at, mode=mode, legacy=False,
                                           submit_on_card3=False))
                log("22:00：卡片 4 已发出 → 卡片 3 反馈提交键已移除（重交仍锁定在待整改下）", sink)
            except Exception as e:
                log("22:00：卡片 3 移除反馈提交键失败（下个节拍轮询会接管）：%s" % e, sink)
        save_state(st)
    return {"ok": True, "mode": mode, "persist": persist,
            "inserted": False, "tail": "",
            "message_id": mid, "slot3": mid, "slot3_kind": "stats",
            "summary_kind": "unfed", "slot4": ""}


# ---------------------------------------------------------------- 20:00 / 22:00 私发「反馈不合格」卡片
def _today_ms(hour, minute=0):
    """当天指定时刻的毫秒时间戳（Asia/Shanghai，和飞书提交时间同一基准）。"""
    t = now().replace(hour=hour, minute=minute, second=0, microsecond=0)
    return int(t.timestamp() * 1000)


def refresh_card2_at(mode="live", sink=print, force=False, wave_key=None):
    """【2026-11-09 逐条版】卡片 2 的 @ 逐家刷新（16:00 起每 10 分钟一轮）。

    对每一个待 @ 的店长（按 T 加盟在前、M 加盟在后）：
      ① 只把「这一家」的 @ 降级为文本并原地 PATCH → 卡片即时生效；
      ② 等 5 秒；
      ③ 恢复全部真 @ 并原地 PATCH → 即时生效；
    然后才轮到第 2 家：删 @ 生效 → 恢复 @ 生效 → 第 3 家……一直逐条走完。
    与旧版「一次性全删 → 5 秒 → 全恢复」不同，现在是【逐一删除、逐一恢复】。
    全程仅原地 PATCH，绝不新发群消息；23:59 封板后不再执行。
    """
    st = load_state()
    mid = st.get("main_message_id") or ""
    today = now().strftime("%Y-%m-%d")
    if wave_key is None:
        wave_key = "%s manual" % today
    if (not force) and st.get("at_refresh_last_wave") == wave_key:
        return {"ok": True, "skipped": True, "reason": "本波次已刷新过", "wave": wave_key,
                "at_count": 0, "steps": 0}
    if not mid:
        log("卡片 2 @逐条刷新跳过：main_message_id 为空", sink)
        return {"ok": False, "skipped": True, "reason": "第 2 张卡尚未发出",
                "at_count": 0, "steps": 0}
    if st.get("day_closed") == today:
        log("卡片 2 @逐条刷新跳过：今日已封板", sink)
        return {"ok": True, "skipped": True, "reason": "今日已封板",
                "at_count": 0, "steps": 0}
    if mode != "trial":       # 提前落盘，防止逐条耗时期间被同一波次重复触发
        _s = load_state()
        _s["at_refresh_last_wave"] = wave_key
        save_state(_s)

    load_today_detail(refresh=True)
    shops = aggregate(fetch_records(), biz_date=st.get("main_date") or today)
    use_at = (mode == "live")
    _can = True               # 未封板 → 保留反馈按键
    step = int(SCHED.get("at_step_seconds", 5) or 5)

    # 待 @ 名单：中差评未反馈 + 16:00 起回复率未反馈（按 T→M，去重）
    keys = []
    for key, _chans, _info in pending_review_detail_rows(shops):
        if key and key not in keys:
            keys.append(key)
    for j in rate_unfed_managers(shops):
        k = _mgr_key(j)
        if k and k not in keys:
            keys.append(k)

    ok_all, off_all, on_all, done = True, True, True, 0
    for idx, k in enumerate(keys, 1):
        try:
            j_off = patch_card(mid, build_gallery_card(
                mode=mode, shops=shops, use_at=use_at, can_submit=_can,
                closed=False, mute_key=k))
            off_ok = j_off.get("code") == 0
            log("卡片 2 @逐条[%d/%d] 删除该店 @（%s）生效：%s"
                % (idx, len(keys), k, "✅" if off_ok else
                   "❌ " + str(j_off.get("msg"))[:100]), sink)
            time.sleep(step)
            j_on = patch_card(mid, build_gallery_card(
                mode=mode, shops=shops, use_at=use_at, can_submit=_can,
                closed=False))
            on_ok = j_on.get("code") == 0
            log("卡片 2 @逐条[%d/%d] 恢复 @ 生效：%s"
                % (idx, len(keys), "✅" if on_ok else
                   "❌ " + str(j_on.get("msg"))[:100]), sink)
            off_all &= off_ok
            on_all &= on_ok
            ok_all &= off_ok and on_ok
            done += 1
        except Exception as e:
            ok_all = False
            log("卡片 2 @逐条[%d/%d] 异常：%s" % (idx, len(keys), e), sink)

    if mode != "trial":
        st = load_state()
        st["at_refresh_last_wave"] = wave_key
        st["at_refresh_ts"] = now().strftime("%Y-%m-%d %H:%M:%S")
        st["at_refresh_count"] = len(keys)
        save_state(st)
    log("卡片 2 @逐条刷新完成：%d 家，逐条删除/恢复 %d 轮（删除@%s / 恢复@%s）"
        % (len(keys), done, "✅" if off_all else "❌", "✅" if on_all else "❌"), sink)
    return {"ok": ok_all, "wave": wave_key, "skipped": False,
            "at_count": len(keys), "steps": done, "off_ok": off_all, "on_ok": on_all}


def refresh_card3_at(mode="live", sink=print, wave_key=None, force=False):
    """【2026-11-09 逐条版】卡片 3（已反馈统计①/②…）审核不过的 @ 逐家刷新。

    与卡片 2 同一节奏：第 1 家删 @ 生效 → 恢复 @ 生效 → 第 2 家删 @ 生效 → 恢复 …
    只 PATCH 该门店所在的那一页卡，其余页不动；全程不发新消息。
    """
    st = load_state()
    ids = [x for x in _stats_card_ids(st) if x]
    today = now().strftime("%Y-%m-%d")
    if wave_key is None:
        wave_key = "%s manual" % today
    if (not force) and st.get("card3_at_last_wave") == wave_key:
        return {"ok": True, "skipped": True, "reason": "本波次已刷新过", "wave": wave_key,
                "at_count": 0, "steps": 0}
    if not ids:
        log("卡片 3 @逐条刷新跳过：统计卡尚未发出", sink)
        return {"ok": False, "skipped": True, "reason": "第 3 张卡尚未发出",
                "at_count": 0, "steps": 0}
    if st.get("day_closed") == today:
        log("卡片 3 @逐条刷新跳过：今日已封板", sink)
        return {"ok": True, "skipped": True, "reason": "今日已封板",
                "at_count": 0, "steps": 0}
    if mode != "trial":
        _s = load_state()
        _s["card3_at_last_wave"] = wave_key
        save_state(_s)

    load_today_detail(refresh=True)
    shops = aggregate(fetch_records(), biz_date=st.get("main_date") or today)
    use_at = (mode == "live")
    legacy = (st.get("main_date") or "") < NEW_FLOW_FROM
    evening_done = (st.get("evening_date") == today and st.get("evening_mode") == mode)
    pages = stats_pages(shops)
    step = int(SCHED.get("at_step_seconds", 5) or 5)

    # 每个审核不过的门店 → (静音键, 所在页)；同一店长只做一轮
    tasks, seen = [], set()
    for short, j, _rs in collect_failures(shops):
        k = _mgr_key(j)
        if not k or k in seen:
            continue
        seen.add(k)
        pi = 0
        for i, pg in enumerate(pages):
            if any(_norm(_short(x)) == _norm(short) for x in pg):
                pi = i
                break
        if pi < len(ids):
            tasks.append((k, pi))

    def _card(pi, mute):
        return stats_card(shops, page_idx=pi, pages=pages, audited=True,
                          use_at=use_at, mode=mode, legacy=legacy,
                          can_submit=True, closed=False,
                          submit_on_card3=not evening_done,
                          mute_key=mute)

    ok_all, off_all, on_all, done = True, True, True, 0
    for idx, (k, pi) in enumerate(tasks, 1):
        mid = ids[pi]
        try:
            j_off = patch_card(mid, _card(pi, k))
            off_ok = j_off.get("code") == 0
            log("卡片 3 @逐条[%d/%d] 删除该店 @（%s·%s）生效：%s"
                % (idx, len(tasks), cn_index(pi), k, "✅" if off_ok else
                   "❌ " + str(j_off.get("msg"))[:100]), sink)
            time.sleep(step)
            j_on = patch_card(mid, _card(pi, ""))
            on_ok = j_on.get("code") == 0
            log("卡片 3 @逐条[%d/%d] 恢复 @ 生效：%s"
                % (idx, len(tasks), "✅" if on_ok else
                   "❌ " + str(j_on.get("msg"))[:100]), sink)
            off_all &= off_ok
            on_all &= on_ok
            ok_all &= off_ok and on_ok
            done += 1
        except Exception as e:
            ok_all = False
            log("卡片 3 @逐条[%d/%d] 异常：%s" % (idx, len(tasks), e), sink)

    if mode != "trial":
        st = load_state()
        st["card3_at_last_wave"] = wave_key
        st["card3_at_ts"] = now().strftime("%Y-%m-%d %H:%M:%S")
        save_state(st)
    log("卡片 3 @逐条刷新完成：%d 处，逐条删除/恢复 %d 轮（删除@%s / 恢复@%s）"
        % (len(tasks), done, "✅" if off_all else "❌", "✅" if on_all else "❌"), sink)
    return {"ok": ok_all, "wave": wave_key, "skipped": False,
            "at_count": len(tasks), "steps": done, "off_ok": off_all, "on_ok": on_all}


# ---------------------------------------------------------------- 23:00 汇总卡（新发一条 @ 相关同事）
# 注：与此前「绝不在群里发新消息」的硬约束不同，23:00 这一张汇总卡是用户明确要求「新发一条卡片」。
#
# 【2026-11-09 用户模板】按【门店负责人】分三段，每段四行：
#   @负责人，中差评未反馈回复（x 家），
#   回复率未反馈（x 家）
#   昨天今天中差评都未反馈是：@店长 @店长
#   昨天今天回复率都未反馈的是：@店长 @店长
# M 加盟（其余加盟商，大狮兄莫恩健）→ @莫恩健（用户本人）；
# T 加盟的两位负责人【分开汇总】：魏兆翔一段、魏兆翎一段，各自 @ 本人。
SUMMARY_GROUPS = (
    {"key": "M", "name": "M 加盟（大狮兄 莫恩健）",
     "at": (("莫恩健", "ou_44abfb099033aa534dc051ca3e220481"),)},
    {"key": OWNER_WSX, "name": "T 加盟（魏兆翔）",
     "at": (("魏兆翔", "ou_e92b25b7a317f3ae1e5ffca8eb17128a"),)},   # 用户口述「魏照祥」（音近字）
    {"key": OWNER_WSL, "name": "T 加盟（魏兆翎）",
     "at": (("魏兆翎", "ou_f4b6dd04711b0665afbb1f750264da22"),)},  # 用户口述「魏照岭」（音近字）
)
SUMMARY_AT_OPEN_IDS = {nm: oid for _g in SUMMARY_GROUPS for nm, oid in _g["at"]}


def _date_shift(date_str, days):
    """'2026-11-08' + (-1) → '2026-11-07'；解析失败按今天算。"""
    from datetime import datetime as _dt, timedelta as _td
    try:
        d = _dt.strptime(str(date_str), "%Y-%m-%d")
    except Exception:
        d = now()
    return (d + _td(days=days)).strftime("%Y-%m-%d")


SUMMARY_WINDOW_START = "2026-11-09"     # 从这天起「昨天今天」改为「近 3 天」，此前仍是近 2 天
SUMMARY_WINDOW_MIN, SUMMARY_WINDOW_MAX = 2, 7


def summary_window_days(date_str):
    """汇总卡回溯窗口 N（近 N 天）。

    · 2026-11-08 及以前：近 2 天（= 原来的「昨天今天」，只对比上一张卡和本卡）；
    · 2026-11-09 起：近 3 天，之后每天 +1，到 7 天封顶。
    用户 2026-11-09 口径：今天 14:15 起这一轮跑到晚上汇总才是近 3 天；
    群里 11-08 那张卡仍按近 2 天。
    """
    from datetime import datetime as _dt
    try:
        d = _dt.strptime(str(date_str), "%Y-%m-%d").date()
        s = _dt.strptime(SUMMARY_WINDOW_START, "%Y-%m-%d").date()
    except Exception:
        return SUMMARY_WINDOW_MIN
    if d < s:
        return SUMMARY_WINDOW_MIN                # 11-08 及以前：近 2 天
    n = SUMMARY_WINDOW_MIN + 1 + (d - s).days    # 11-09 起：近 3 天，逐日 +1
    return max(SUMMARY_WINDOW_MIN, min(SUMMARY_WINDOW_MAX, n))


def summary_group_stats(shops, records, date_str):
    """汇总卡数据：按门店负责人分段，每段四项。

    ① 中差评未反馈回复（x 家）—— 本卡业务日仍没交中差评反馈的门店；
    ② 回复率未反馈（x 家）—— 本卡业务日仍没上传回复率截图的店；
    ③ 近 N 天中差评都未反馈是：—— 窗口内每一天都欠中差评反馈的店长（按店长去重）；
    ④ 近 N 天回复率都未反馈的是：—— 窗口内每一天都没交回复率截图的店长。

    窗口 N 由 summary_window_days() 给出（今天 3 天，逐日 +1，7 天封顶）。
    每天：业务日 d 处理评价日 d-1；「欠」= 当天有中差评任务却没交反馈 / 没交回复率截图。
    某天提交记录整体为空（表格没数据）时跳过该天，避免把「数据缺失」误判成全员欠账。
    """
    date_str = date_str or now().strftime("%Y-%m-%d")
    n_days = summary_window_days(date_str)
    day_ctx = []
    for i in range(n_days):
        biz = _date_shift(date_str, -i)
        rev = _date_shift(biz, -1)
        det = detail_for_date(rev) or {}
        try:
            sh = aggregate(records or [], biz_date=biz)
        except Exception:
            sh = OrderedDict()
        day_ctx.append((biz, det, sh))

    def _mgr(name):
        info = _empty_agg(name)
        k = info.get("manager_open_id") or info.get("manager") or name
        return k, info

    out = OrderedDict()
    for g in SUMMARY_GROUPS:
        key = g["key"]
        # 今天（窗口第一天）的家数
        _biz0, det0, shops0 = day_ctx[0]
        cur_mid = [s for s in det0
                   if owner_group(match_store(s) or s) == key
                   and not store_feedback_done(s, shops0)]
        cur_rate = [f for f in ALL_SHOPS
                    if owner_group(f) == key
                    and agg_for(shops0, f).get("rate_files", 0) == 0]
        # 窗口内「每一天都欠」→ 逐天求集合、再取交集
        mid_sets, rate_sets, info_map = [], [], {}
        for _biz, det, sh in day_ctx:
            if not sh:
                continue                      # 该天无任何提交记录（数据缺失）→ 不参与判断
            ms = set()
            for s in det:
                full = match_store(s) or s
                if owner_group(full) != key or store_feedback_done(s, sh):
                    continue
                k, info = _mgr(s)
                info_map[k] = info
                ms.add(k)
            rs = set()
            for f in ALL_SHOPS:
                if owner_group(f) != key:
                    continue
                if agg_for(sh, f).get("rate_files", 0) == 0:
                    k, info = _mgr(f)
                    info_map[k] = info
                    rs.add(k)
            mid_sets.append(ms)
            rate_sets.append(rs)
        both_mid = set.intersection(*mid_sets) if mid_sets else set()
        both_rate = set.intersection(*rate_sets) if rate_sets else set()
        out[key] = {
            "mid_unfed": len(cur_mid),
            "rate_unfed": len(cur_rate),
            "mid_both": [info_map[k] for k in info_map if k in both_mid],
            "rate_both": [info_map[k] for k in info_map if k in both_rate],
            "days": n_days,
            "prev_known": any(bool(x[2]) for x in day_ctx),
        }
    return out


def _at_line(infos, use_at=True):
    """一行 @：@张三 @李四；空则灰色「无」。

    use_at=False（23:59 封板后）→ 只留灰色姓名文本，不再真 @、也不带门店名。
    """
    if not infos:
        return "<font color='grey'>无</font>"
    if not use_at:
        return " ".join(_plain_name(_name_of(i)) for i in infos)
    return " ".join(at_tag(i.get("manager_open_id"), i.get("manager")) for i in infos)


def build_summary_at_card(shops, closed=False, date_str="", records=None):
    """23:00「未反馈门店汇总」卡（新发一条群消息，按门店负责人分段 @）。

    【2026-11-09 用户要求】这张卡不是发完就定格的快照：
    发出后由 poll_once 每拍（10 秒）原地刷新，店长一补交，家数和 @ 名单立刻跟着变；
    23:59 封板后传 closed=True 再刷一次，标注「已封板 · 数字不再变化」，之后不再更新。

    records 可由调用方传入（poll_once 已拉过），避免每个节拍重复读多维表格。
    """
    date_str = date_str or now().strftime("%Y-%m-%d")
    if records is None:
        try:
            records = fetch_records()
        except Exception:
            records = []
    stats = summary_group_stats(shops, records, date_str)
    tail = ("<font color='grey'>23:59 已封板 · 以上数字不再变化</font>" if closed
            else "<font color='grey'>提交后本卡数字自动更新 · 23:59 封板 · "
                 "最近同步 %s</font>" % now().strftime("%m-%d %H:%M:%S"))
    body = []
    nd_all = summary_window_days(date_str)
    for i, g in enumerate(SUMMARY_GROUPS):
        s = stats.get(g["key"]) or {}
        nd = s.get("days") or nd_all
        if i:
            body.append({"tag": "hr"})
        # 【2026-11-09 用户要求】汇总卡的 @ 例外：封板后也保持【真 @】（不降级为文本），
        # 只有卡片 2 / 已反馈统计卡里的 @店长 才在封板后变纯文本。
        ats = " ".join(at_tag(oid, nm) for nm, oid in g["at"])
        body.append(_md("%s，中差评未反馈回复（%d 家），\n回复率未反馈（%d 家）"
                        % (ats, s.get("mid_unfed", 0), s.get("rate_unfed", 0))))
        body.append(_md("近 %d 天中差评都未反馈是：%s"
                        % (nd, _at_line(s.get("mid_both") or [], use_at=True))))
        body.append(_md("近 %d 天回复率都未反馈的是：%s"
                        % (nd, _at_line(s.get("rate_both") or [], use_at=True))))
    body.append({"tag": "hr"})
    body.append(_md(tail))
    return {
        "schema": "2.0", "config": {"update_multi": True, "width_mode": "default"},
        "header": {
            "title": {"tag": "plain_text", "content":
                      "未反馈门店汇总 · 23:00" + ("（已封板）" if closed else "")},
            "subtitle": {"tag": "plain_text", "content":
                         "%s · 按门店负责人统计 · 近 %d 天%s"
                         % (date_str, nd_all, " · 已封板" if closed else "")},
            "template": "grey" if closed else "red",
            "text_tag_list": [{"tag": "text_tag", "text": {"tag": "plain_text",
                                                           "content": "汇总"},
                              "color": "blue" if closed else "red"}]},
        "body": {"direction": "vertical", "padding": "12px 12px 14px 12px",
                 "vertical_spacing": "medium", "elements": body},
    }


def send_summary_at_card(mode="live", sink=print, force=False, mark_date=None):
    """23:00：在群里【新发】一张汇总卡，@ 魏兆翔、魏兆翎、莫恩健，写明「以上未反馈门店请查收」。

    仅此一张卡例外地走「群发新消息」（用户明确要求）。其余时段仍严守「只原地编辑、不新发」。
    发出后由 poll_once 接管，每 10 秒原地刷新数字，直到 23:59 封板（不再是一次性快照）。
    当天只发一次（按日期去重）。

    mark_date：写进 summary_at_date 的去重日期，默认今天。
      补发前一天的卡时传 main_date，否则会占用次日名额、导致次日 23:00 不再发。
    """
    st = load_state()
    today = now().strftime("%Y-%m-%d")
    _mark = mark_date or today
    if (not force) and st.get("summary_at_date") == _mark:
        return {"ok": True, "skipped": True, "reason": "今天已发过 23:00 汇总卡", "sent": False}
    _recs = fetch_records()
    shops = aggregate(_recs, biz_date=st.get("main_date") or today)
    stats = summary_group_stats(shops, _recs, st.get("main_date") or today)
    card = build_summary_at_card(shops, closed=False,
                                 date_str=st.get("main_date") or today,
                                 records=_recs)
    try:
        j = send_card(card, mode)
        ok = j.get("code") == 0
    except Exception as e:
        ok, j = False, {"msg": str(e)}
    if ok:
        mid = (j.get("data") or {}).get("message_id", "")
        if mode != "trial":
            st = load_state()
            st["summary_at_date"] = _mark
            st["summary_at_ts"] = now().strftime("%Y-%m-%d %H:%M:%S")
            st["summary_at_message_id"] = mid
            save_state(st)
        _brief = "；".join("%s 中差评未反馈 %d 家 / 回复率未反馈 %d 家"
                           % (g["name"], (stats.get(g["key"]) or {}).get("mid_unfed", 0),
                              (stats.get(g["key"]) or {}).get("rate_unfed", 0))
                           for g in SUMMARY_GROUPS)
        log("23:00 汇总卡已新发：%s（message_id=%s）" % (_brief, mid), sink)
        return {"ok": True, "sent": True, "message_id": mid,
                "groups": {k: {kk: vv for kk, vv in v.items() if kk != "mid_both"
                               and kk != "rate_both"} for k, v in stats.items()}}
    log("23:00 汇总卡发送失败：%s" % str(j.get("msg"))[:160], sink)
    return {"ok": False, "sent": False, "reason": str(j.get("msg"))[:160]}


def preview_summary_at_card(mode="trial"):
    """把 23:00 汇总卡按当前业务日数据渲染并发到本人私聊预览（默认 trial）。

    只发不看状态：不写 summary_at_date / summary_at_message_id，
    不影响 23:00 正式发送、次日去重和后续原地刷新。
    """
    st = load_state()
    day = st.get("main_date") or now().strftime("%Y-%m-%d")
    recs = fetch_records()
    shops = aggregate(recs, biz_date=day)
    card = build_summary_at_card(shops, closed=False, date_str=day, records=recs)
    j = send_card(card, mode)
    ok = j.get("code") == 0
    return {"ok": ok, "sent": ok, "date": day,
            "message_id": (j.get("data") or {}).get("message_id", ""),
            "code": j.get("code"), "msg": j.get("msg"),
            "stats": {k: {"mid_unfed": v["mid_unfed"], "rate_unfed": v["rate_unfed"],
                          "mid_both": [x.get("manager") for x in v["mid_both"]],
                          "rate_both": [x.get("manager") for x in v["rate_both"]]}
                      for k, v in summary_group_stats(shops, recs, day).items()}}


def push_summary_to_group(date_str=None, closed=None, sink=print):
    """把汇总结果【原地更新】到群里那张汇总卡（不新发消息）。

    2026-11-09 用户要求：「把汇总结果修改到群里的汇总卡」。
    date_str 默认取当前 main_date（正在生效的业务日）；closed 默认沿用当天封板状态，
    已封板就保持灰色定格样式，只更新数字和名单。
    """
    st = load_state()
    day = date_str or st.get("main_date") or now().strftime("%Y-%m-%d")
    said = st.get("summary_at_message_id") or ""
    if not said:
        return {"ok": False, "reason": "群里还没有汇总卡（summary_at_message_id 为空）"}
    if closed is None:
        closed = (st.get("day_closed") == day)
    recs = fetch_records()
    shops = aggregate(recs, biz_date=day)
    card = build_summary_at_card(shops, closed=closed, date_str=day, records=recs)
    j = patch_card(said, card)
    ok = j.get("code") == 0
    log("汇总卡已原地更新到群里（%s · 近 %d 天 · %s）：%s"
        % (day, summary_window_days(day), "已封板" if closed else "进行中",
           "成功" if ok else "失败：" + str(j.get("msg"))), sink)
    return {"ok": ok, "message_id": said, "date": day,
            "days": summary_window_days(day), "closed": closed,
            "code": j.get("code"), "msg": j.get("msg")}


def run_summary(mode="trial", sink=print):
    """兼容旧入口（调度台按钮 / 22:00 定时都走这里）→ 现在等价于 22:00 对调。"""
    return run_evening_swap(mode=mode, sink=sink)


def status():
    """给网页 /api/status 用的完整状态（两区块数据）。"""
    st = load_state()
    try:
        records = fetch_records()
        shops = aggregate(records, biz_date=st.get("main_date"))
        midbad_rows, rate_rows, rows = [], [], []
        for short in DETAIL_SHOPS:
            j = judge(short, shops)
            midbad_rows.append({
                "门店": short, "店长": j["manager"],
                "有差评": j["has_bad"], "有中评": j["has_mid"],
                "差评": j["bad"], "中评": j["mid"],
                "缺失": [x for x in j["reasons"] if x != "回复率截图未上传"],
            })
        # 回复率名单同样按加盟类型排（T 在前、M 在后）
        for full in sort_by_tm(ALL_SHOPS):
            j = judge(full, shops)
            _agg = agg_for(shops, full)
            if j["rate"] == "ok":
                _miss = []
            elif _agg.get("rate_files", 0) == 0:
                _miss = ["回复率截图未上传"]          # 未反馈（没交截图）
            else:
                _miss = ["回复率未达 100%"]            # 已反馈但不达标（待整改）
            rate_rows.append({"门店": _short(full), "店长": j["manager"],
                              "回复率": j["rate"] == "ok", "缺失": _miss})
        submitted_rows = []
        # 与群卡一致：已反馈门店按加盟类型排（T 在前、M 在后），只排序不分组
        for store in sort_by_tm(list(shops)):
            agg = shops[store]
            j = judge(store, shops)
            rows.append({"门店": _short(store), "店长": agg["manager"],
                         "回复率": j["回复率"], "差评": j["差评"], "中评": j["中评"],
                         "缺失": j["reasons"]})
            submitted_rows.append({
                "门店": _short(store), "店长": agg["manager"],
                "中评": j["mid"], "差评": j["bad"], "回复率": j["rate"],
                "缺失": j["reasons"],
            })
        st_err = ""
    except Exception as e:
        midbad_rows, rate_rows, rows, submitted_rows = [], [], [], []
        st_err = str(e)

    # 状态接口保留的三段明细（中评 / 差评 / 回复率截图），供历史消费者兼容；
    # 群里 22:00 卡片模板已改用 unfed_elements() 的两段式（按店长归并）。
    sm_mid = [{"门店": r["门店"], "店长": r["店长"]}
              for r in midbad_rows if r["有中评"] and r["中评"] == "fail"]
    sm_bad = [{"门店": r["门店"], "店长": r["店长"]}
              for r in midbad_rows if r["有差评"] and r["差评"] == "fail"]
    sm_rate = [{"门店": r["门店"], "店长": r["店长"]}
               for r in rate_rows if not r["回复率"]]
    _sd, _smode = st.get("summary_date", ""), st.get("summary_mode", "")
    _w2 = st.get("at_refresh_last_wave", "")
    _w3 = st.get("card3_at_last_wave", "")
    return {
        "task": CFG["task_name"],
        "form_url": BT["form_share_url"],
        "bitable_url": BT["url"],
        "main_message_id": st.get("main_message_id", ""),
        "main_mode": st.get("main_mode", ""),
        "demo": st.get("demo", False),
        "audited": st.get("audited", False),
        "audit_min_records": SCHED["audit_min_records"],
        "final_audit_ts": st.get("final_audit_ts", ""),
        "main_date": st.get("main_date", ""),
        "day_closed": st.get("day_closed"),
        "closed": bool(st.get("day_closed")) and st.get("day_closed") == st.get("main_date"),
        "closed_ts": st.get("day_closed_ts", ""),
        "closed_card_done": bool(st.get("closed_card_ts"))
                            and st.get("closed_card_ts") == st.get("day_closed"),
        "last_poll_ts": st.get("last_poll_ts", ""),
        "handoff_message_id": st.get("handoff_message_id", ""),
        "stats_card_ids": st.get("stats_card_ids", []),
        "stats_pages": len(st.get("stats_card_ids") or []),
        "slot3_kind": st.get("slot3_kind", ""),
        "evening_ts": st.get("evening_ts", ""),
        "evening_done": bool(st.get("evening_date"))
                        and st.get("evening_date") == st.get("main_date"),
        # 22:00 的实际做法：insert=插进第 3 张卡 / new=补发一张完整卡
        "evening_kind": ("insert" if st.get("slot3_kind") == "stats_evening"
                         else ("new" if st.get("summary_kind") == "full" else "")),
        "summary_kind": st.get("summary_kind", ""),
        "slot4_message_id": st.get("slot4_message_id", ""),
        "slot4_ts": st.get("slot4_ts", ""),
        "swap_done": False,          # 旧版「第 4 张卡」已取消，保留键位兼容前端
        "handoff_date": st.get("handoff_date", ""),
        "handoff_ts": st.get("handoff_ts", ""),
        "handoff_shops": st.get("handoff_shops", 0),
        "handoff_threshold": SCHED.get("handoff_threshold_shops", 10),
        "summary_message_id": st.get("summary_message_id", ""),
        "summary_ts": st.get("summary_ts", ""),
        # 23:00「未反馈门店汇总」卡（最后一张，发出后每拍自动刷新到 23:59）
        "summary_at_message_id": st.get("summary_at_message_id", ""),
        "summary_at_date": st.get("summary_at_date", ""),
        "summary_at_ts": st.get("summary_at_ts", ""),
        "summary_date": _sd,
        "summary_mode": _smode,
        # 第 3 张卡片是否已在「当天 + 同模式」下发过（决定卡 2 统计是否移交）
        "summary_sent": bool(st.get("summary_message_id")) and _sd == st.get("main_date")
                        and _smode == st.get("main_mode"),
        "summary": {
            "time": "%02d:%02d" % (SCHED["summary_hour"], SCHED["summary_minute"]),
            "message_id": st.get("summary_message_id", ""),
            "ts": st.get("summary_ts", ""),
            "date": _sd,
            "mode": _smode,
            "sent": bool(st.get("summary_message_id")) and _sd == st.get("main_date")
                    and _smode == st.get("main_mode"),
            "mid": sm_mid, "bad": sm_bad, "rate": sm_rate,
            "counts": {"mid": len(sm_mid), "bad": len(sm_bad), "rate": len(sm_rate),
                       "all": len(ALL_SHOPS)},
        },
        # 16:00–23:50 每 10 分钟「卡片 2/3 @店长 逐条删除@→等 5 秒→恢复@」循环刷新执行状态
        # （仅记录波次时间，不暴露店长身份；私聊提醒卡已移除）
        "dm_2000": {"date": _w2.split(" ")[0] if _w2 else "", "ts": _w2, "wave": _w2,
                    "sent": bool(_w2) and _w2.split(" ")[0] == now().strftime("%Y-%m-%d")},
        "dm_2200": {"date": _w3.split(" ")[0] if _w3 else "", "ts": _w3, "wave": _w3,
                    "sent": bool(_w3) and _w3.split(" ")[0] == now().strftime("%Y-%m-%d")},
        "submitted_shops": len(rows),
        "detail_shops": len(DETAIL_SHOPS),
        "all_shops": len(ALL_SHOPS),
        "submitted_rows": submitted_rows,  # 只统计已反馈门店（卡片 / 网页主视图）
        "midbad_rows": midbad_rows,        # 兼容旧版：今日中差评明细（含未反馈）
        "rate_rows": rate_rows,            # 兼容旧版：全部 26 家（不含寮步城市店）回复率（含未反馈）
        "rows": rows,                     # 兼容旧版：已提交门店三维度布尔
        "error": st_err,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["send-main", "poll", "summary", "status", "records",
                                       "summary-preview", "summary-push"])
    ap.add_argument("--mode", choices=["live", "trial"], default="trial")
    ap.add_argument("--live-data", action="store_true", help="send-main 用真实表格数据而非演示")
    ap.add_argument("--audited", action="store_true", help="send-main 直接展示审核态")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.action == "send-main":
        out = send_main(mode=a.mode, demo=not a.live_data, audited=True if a.audited else None)
    elif a.action == "poll":
        out = poll_once(force=a.force)
    elif a.action == "summary":
        out = run_summary(mode=a.mode)
    elif a.action == "status":
        out = status()
    elif a.action == "summary-preview":
        out = preview_summary_at_card(mode=a.mode)
    elif a.action == "summary-push":
        out = push_summary_to_group()
    else:
        out = aggregate(fetch_records(), biz_date=now().strftime("%Y-%m-%d"))
        out = {k: {kk: vv for kk, vv in v.items()} for k, v in out.items()}
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
