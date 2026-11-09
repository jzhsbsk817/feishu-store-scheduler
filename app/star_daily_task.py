#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
星级群每日追踪汇总 · 核心任务脚本
================================================
可独立单跑，也可被常驻服务 app.py 调用。

完整流程（定时任务 #01）：
  1. 读取看板数据日期（grade-data-dg.js 的 scopes.dongguan.meta.date）
  2. 【日期闸门】数据日期必须 == 昨天；不相等 -> 下面所有步骤都不执行
  3. 下载「顾客满意」明细图片（留档）
  4. 分析图片对应的 4 个要点（+ 3 个平台低分板块）
  5. 生成飞书卡片（正式运行：真实 @ 店长）
  6. 正式运行发到「星级店长群」；试运行只发莫恩健本人
  7. 结果回写网页数据文件，供页面展示

用法：
  python3 star_daily_task.py --mode live           # 正式运行（严格日期闸门）
  python3 star_daily_task.py --mode trial          # 试运行（严格日期闸门）
  python3 star_daily_task.py --mode trial --force  # 忽略闸门，强制跑一次（联调用）

调度（常驻服务 app.py 内）：每天 14:20 首次检查，之后每 15 分钟检查一次；
只有数据日期 == 昨天时才真正执行，且当天成功执行一次后不再重复。
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import urllib.request
import urllib.error
from zoneinfo import ZoneInfo

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(BASE, "config")
DATA_DIR = os.path.join(BASE, "data")
os.makedirs(DATA_DIR, exist_ok=True)

TZ = ZoneInfo("Asia/Shanghai")
BOARD = "https://dashboard-board.app.workbuddy.host"
DATA_JS = BOARD + "/pages/grade-data-dg.js"
OWNER = "莫恩健"
PLATFORMS = ["美团外卖", "淘宝闪购", "京东外卖", "美团团购", "大众点评", "抖音团购"]

LARK_BASE = "https://open.feishu.cn/open-apis"
STAR_GROUP_CHAT_ID = "oc_2e8e3a192f6868b9f7517c30c839dd1f"  # 东莞-（莫ej）星级店长群
TRIAL_USER_OPEN_ID = "ou_44abfb099033aa534dc051ca3e220481"   # 莫恩健本人
# 顾客满意明细截图（2026-11-06 下载），用于插入第 1 张卡片最下方
STAR_IMAGE_KEY = "img_v3_02177_4d41dc46-72e1-4d7a-ad3a-55791d25c4cg"
STAR_IMAGE_FILE = os.path.join(DATA_DIR, "star_image.json")


def star_image_key(date=None):
    """当天已上传的顾客满意明细图（image_key）；没有则回退历史固定图。"""
    try:
        with open(STAR_IMAGE_FILE, encoding="utf-8") as f:
            j = json.load(f)
        if (not date or j.get("date") == date) and j.get("image_key"):
            return j["image_key"]
    except Exception:
        pass
    return STAR_IMAGE_KEY


def upload_image(path):
    """上传图片到飞书，返回 image_key（image_type=message）。"""
    import mimetypes
    import uuid
    token = get_token()
    boundary = "----wbboundary" + uuid.uuid4().hex
    ctype = mimetypes.guess_type(path)[0] or "image/png"
    fn = os.path.basename(path)
    with open(path, "rb") as f:
        content = f.read()
    parts = []
    parts.append(("--%s\r\nContent-Disposition: form-data; name=\"image_type\"\r\n\r\nmessage\r\n" % boundary).encode())
    parts.append(("--%s\r\nContent-Disposition: form-data; name=\"image\"; filename=\"%s\"\r\n"
                  "Content-Type: %s\r\n\r\n" % (boundary, fn, ctype)).encode())
    parts.append(content)
    parts.append(("\r\n--%s--\r\n" % boundary).encode())
    data = b"".join(parts)
    req = urllib.request.Request(
        LARK_BASE + "/im/v1/images", data=data, method="POST",
        headers={"Content-Type": "multipart/form-data; boundary=" + boundary,
                 "Authorization": "Bearer " + token})
    j = json.loads(urllib.request.urlopen(req, timeout=60).read())
    if j.get("code") != 0:
        raise RuntimeError("上传图片失败：%s" % j.get("msg"))
    return (j.get("data") or {}).get("image_key", "")


# ---------------------------------------------------------------- 配置 / 凭证
def _load_env():
    """从同目录 .env 读取凭证（不写入资料库产物）。环境变量优先。"""
    p = os.path.join(BASE, ".env")
    if not os.path.exists(p):
        return
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_env()
APP_ID = os.environ.get("LARK_APP_ID", "")  # 真实值由运行时环境变量/Secrets 注入，勿在此硬编码
APP_SECRET = os.environ.get("LARK_APP_SECRET", "")
BOARD_USER = os.environ.get("BOARD_USER", "莫恩健")
BOARD_PASSWORD = os.environ.get("BOARD_PASSWORD", "1234")

with open(os.path.join(CONFIG, "store_mapping.json"), encoding="utf-8") as f:
    STORE_MAP = json.load(f)
with open(os.path.join(CONFIG, "manager_openids.json"), encoding="utf-8") as f:
    MANAGER_OPENIDS = json.load(f)


# ---------------------------------------------------------------- 基础工具
def now():
    return datetime.datetime.now(TZ)


def yesterday():
    return (now().date() - datetime.timedelta(days=1)).isoformat()


def http_text(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "StarDailyBot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def fetch_board():
    """一次请求同时拿到数据日期与全部门店明细（静态数据文件，无需浏览器）。"""
    txt = http_text(DATA_JS)
    i = txt.find("{")
    raw, _ = json.JSONDecoder().raw_decode(txt[i:])
    sc = raw["scopes"]["dongguan"]
    return sc["meta"]["date"], sc


def _norm(s):
    s = str(s).replace(" ", "").replace("\u3000", "")
    for p in ("东莞市", "东莞"):
        if s.startswith(p):
            s = s[len(p):]
            break
    return s.replace("镇", "")


def lookup(shop_name):
    """门店简称 -> 架构映射（T/M、店长、负责人、店长 open_id）。"""
    n = _norm(shop_name)
    candidates = STORE_MAP
    hit = None
    for m in candidates:
        if _norm(m["门店名称"]) == n:
            hit = m
            break
    if hit is None:
        for m in candidates:
            k = _norm(m["门店名称"])
            if k and (k in n or n in k):
                hit = m
                break
    if hit is None:
        return {"name": shop_name, "tm": "?", "manager": "?", "owner": "?", "open_id": ""}
    return {
        "name": shop_name,
        "tm": hit["加盟T/M"],
        "manager": hit["店长"],
        "owner": hit["负责人"],
        "open_id": MANAGER_OPENIDS.get(hit["门店名称"], {}).get("open_id", ""),
    }


# ---------------------------------------------------------------- 图片下载
def capture_image(date):
    """
    按学习流程：登录看板 -> 顾客满意页签 -> 下载图片（预览弹窗内点保存图片）。
    环境无浏览器时降级为表格区域截图；仍失败则返回 None（不影响主流程）。
    """
    path = os.path.join(DATA_DIR, "星级明细_%s.png" % date)
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                executable_path=os.environ.get("CHROMIUM_PATH", "/usr/bin/chromium"),
                headless=True, args=["--no-sandbox"],
            )
            ctx = browser.new_context(viewport={"width": 1400, "height": 900},
                                      device_scale_factor=2, accept_downloads=True)
            pg = ctx.new_page()
            pg.goto(BOARD + "/#grade", wait_until="domcontentloaded", timeout=45000)
            pg.wait_for_timeout(3500)
            if pg.locator('input[type="password"]').count():
                pg.locator('input[placeholder="用户名"]').fill(BOARD_USER)
                pg.locator('input[placeholder="密码"]').fill(BOARD_PASSWORD)
                pg.get_by_role("button", name="进入看板").click()
                pg.wait_for_timeout(3500)
            frames = [x for x in pg.frames if "grade.html" in x.url]
            if not frames:
                raise RuntimeError("grade.html 未加载")
            fr = frames[0]
            fr.locator('div.tab[data-tab="star"]').click()
            pg.wait_for_timeout(1800)
            fr.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            pg.wait_for_timeout(400)
            try:
                # 真实点击「下载图片」-> 预览弹窗内「保存图片」
                fr.locator("button.dlbtn[data-dlshop]").click()
                fr.locator("#dlModalSave").wait_for(state="attached", timeout=60000)
                with pg.expect_download(timeout=60000) as di:
                    fr.locator("#dlModalSave").click()
                di.value.save_as(path)
            except Exception:
                # 降级：直接截图表格区域（浏览器渲染，中文正常）
                fr.locator("table").last.screenshot(path=path)
            browser.close()
        return path if os.path.exists(path) else None
    except Exception:
        return None


# ---------------------------------------------------------------- 4 要点分析
def analyze(sc, date):
    """分析顾客满意明细（与下载图片同源数据），严格复现图 3 的口径。"""
    prev = (datetime.date.fromisoformat(date) - datetime.timedelta(days=1)).isoformat()
    out = {
        "date": date, "prev": prev,
        "p1": [], "p2": {p: [] for p in PLATFORMS}, "p3": [], "p4": [], "low": {},
        "shop_count": 0,
    }
    for sh in sc["shops"]:
        if sh.get("owner") != OWNER:
            continue
        cur = sh["byDate"].get(date)
        if not cur:
            continue
        out["shop_count"] += 1        # 所辖门店总数（与看板 27 家一致）
        s_raw = cur.get("s")
        if not isinstance(s_raw, (int, float)):
            continue  # 当天无满意得分的门店不参与板块判定
        pre = sh["byDate"].get(prev) or {}
        info = lookup(sh["name"])
        s = round(float(s_raw), 2)
        uro_raw = cur.get("uro")
        uro = round(float(uro_raw), 2) if isinstance(uro_raw, (int, float)) else 0.0
        reply = (cur.get("b") or {}).get("replyRate")
        if not isinstance(reply, (int, float)):
            reply = None
        p = cur.get("p") or {}
        pp = (pre or {}).get("p") or {}

        # 一、满意得分 < 3
        if s < 3:
            out["p1"].append(dict(info, score=s))
        # 二、美团外卖 -> 抖音团购列，带 ⬇️（较前一日下降）即为下滑
        for plat in PLATFORMS:
            a, b = p.get(plat), pp.get(plat)
            if isinstance(a, (int, float)) and isinstance(b, (int, float)) and a < b:
                out["p2"][plat].append(dict(info, score=round(a, 2), frm=round(b, 2)))
        # 三、不满意发生 > 20
        if uro > 20:
            out["p3"].append(dict(info, value=uro))
        # 四、中差评回复率 < 100%
        if reply is not None and reply < 0.9999:
            out["p4"].append(dict(info, value=round(reply * 100, 2)))
        # 附：平台低分
        for label, plat, th in (("淘宝闪购<4.4", "淘宝闪购", 4.4),
                                ("美团外卖<4.7", "美团外卖", 4.7),
                                ("京东外卖<4.7", "京东外卖", 4.7)):
            v = p.get(plat)
            if isinstance(v, (int, float)) and v < th:
                out["low"].setdefault(label, []).append(dict(info, score=round(v, 2)))

    out["p1"].sort(key=lambda x: x["score"])
    out["p3"].sort(key=lambda x: -x["value"])
    return out


# ---------------------------------------------------------------- 卡片构造
def _prefix(info, use_at):
    if use_at and info.get("open_id"):
        return "<at id=%s></at> " % info["open_id"]
    return "@%s " % info["tm"]


def _score_line(x, use_at):
    # 【2026-11-08】@店长后不再跟「店名-店长名字」文本，只保留具体分数
    return "%s%.2f 分" % (_prefix(x, use_at), x["score"])


def _value_line(x, use_at, suffix=""):
    # 【2026-11-08】@店长后不再跟「店名-店长名字」文本，只保留数值
    return "%s%s%s" % (_prefix(x, use_at), x["value"], suffix)


def _block_md(title, lines):
    """一个要点的正文（标题 + 逐行明细），供并排列复用。"""
    return "**%s**\n%s" % (title, "\n".join(lines) or "无")


def _block(title, lines):
    """单个要点占满整行（旧版式，保留给需要全宽的场景）。"""
    return {
        "tag": "column_set", "flex_mode": "none", "background_style": "grey-50",
        "columns": [{"tag": "column", "width": "weighted", "weight": 1,
                     "padding": "8px 12px",
                     "elements": [{"tag": "markdown",
                                   "content": _block_md(title, lines)}]}],
    }


def _two_blocks(a, b):
    """两个要点并排（各占一半、顶部对齐、灰底），把原来两行压成一行。"""
    return {
        "tag": "column_set", "flex_mode": "none", "horizontal_spacing": "small",
        "background_style": "grey-50",
        "columns": [
            {"tag": "column", "width": "weighted", "weight": 1,
             "vertical_align": "top", "padding": "8px 12px",
             "elements": [{"tag": "markdown", "content": a}]},
            {"tag": "column", "width": "weighted", "weight": 1,
             "vertical_align": "top", "padding": "8px 12px",
             "elements": [{"tag": "markdown", "content": b}]},
        ],
    }


def build_card(res, mode, use_at=True):
    n1 = len(res["p1"])
    n2 = sum(len(v) for v in res["p2"].values())
    n3 = len(res["p3"])
    n4 = len(res["p4"])

    metrics = [
        ("## %d\n满意得分 &#60;3" % n1),
        ("## %d\n外部星级下滑" % n2),
        ("## %d\n不满意发生 &#62;20" % n3),
        ("## %d\n回复率 &#60;100%%" % n4),
    ]
    metric_set = {
        "tag": "column_set", "flex_mode": "none", "horizontal_spacing": "medium",
        "background_style": "blue-50",
        "columns": [{"tag": "column", "width": "weighted", "weight": 1, "padding": "8px",
                     "elements": [{"tag": "markdown", "content": m}]} for m in metrics],
    }

    p2_lines = []
    for plat in PLATFORMS:
        lst = res["p2"][plat]
        if not lst:
            continue
        p2_lines.append("**%s · %d 家下滑**" % (plat, len(lst)))
        p2_lines += [_score_line(x, use_at) for x in lst]

    # 四个要点取消并排：每个要点占满整行，纵向排列（不再 2×2 并排）
    elements = [metric_set,
                _block("一、满意得分 &#60;3 分门店（共 %d 家）" % n1,
                       [_score_line(x, use_at) for x in res["p1"]]),
                _block("二、外部星级板块 · 带 ⬇️ 即下滑（共 %d 家）" % n2, p2_lines),
                # 【2026-11-08】第三点只 @ 数值最大的 3 家（p3 已按 value 降序排好）
                _block("三、不满意发生 &#62;20 门店（共 %d 家 · 仅 @ 数值最大 3 家）" % n3,
                       [_value_line(x, use_at) for x in res["p3"][:3]]),
                _block("四、中差评回复率 &#60;100%% 门店（共 %d 家）" % n4,
                       [_value_line(x, use_at, "%") for x in res["p4"]])]

    low_lines = []
    for label in ("淘宝闪购<4.4", "美团外卖<4.7", "京东外卖<4.7"):
        lst = res["low"].get(label, [])
        low_lines.append("**%s（共 %d 家）**" % (label, len(lst)))
        low_lines += ["%s-%s %.2f" % (x["name"], x["manager"], x["score"]) for x in lst] or ["无"]
    elements.append({
        "tag": "collapsible_panel", "expanded": False,
        "header": {"title": {"tag": "plain_text", "content": "附：平台低分门店（3 个板块）"}},
        "elements": [{"tag": "markdown", "content": "\n".join(low_lines)}],
    })

    # 明细截图已挪到第 2 张卡片（与中差评明细并排），本卡只保留 4 小点文字分析
    tag = "正式运行 · 星级店长群" if mode == "live" else "试运行 · 仅发本人"

    return {
        "schema": "2.0",
        "config": {"update_multi": True, "width_mode": "default"},
        "header": {
            "title": {"tag": "plain_text", "content": "① 星级群每日追踪汇总"},
            "subtitle": {"tag": "plain_text",
                         "content": "数据日期 %s · %d 家门店 · 四要点纵向排列 · 星级板块直接 @店长并附具体分数"
                                    % (res["date"], res["shop_count"])},
            "template": "blue",
            "icon": {"tag": "standard_icon", "token": "wiki-bitable_colorful"},
            "text_tag_list": [{"tag": "text_tag",
                               "text": {"tag": "plain_text", "content": tag},
                               "color": "blue"}],
        },
        "body": {"direction": "vertical", "padding": "12px 12px 16px 12px",
                 "vertical_spacing": "medium", "elements": elements},
    }


# ---------------------------------------------------------------- 飞书发送
def _strip_at(obj):
    if isinstance(obj, dict):
        return {k: (re.sub(r"<at id=[^>]*></at>", "@", v)
                    if k == "content" and isinstance(v, str) else _strip_at(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [_strip_at(x) for x in obj]
    return obj


def get_token():
    if not APP_SECRET:
        raise RuntimeError("缺少 LARK_APP_SECRET（请在 .env 或环境变量中配置）")
    body = json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET}).encode()
    req = urllib.request.Request(
        LARK_BASE + "/auth/v3/tenant_access_token/internal", data=body,
        headers={"Content-Type": "application/json"})
    j = json.loads(urllib.request.urlopen(req, timeout=20).read())
    if j.get("code") != 0:
        raise RuntimeError("获取 tenant_access_token 失败：%s" % j.get("msg"))
    return j["tenant_access_token"]


def _post_message(card, mode, token):
    if mode == "live":
        rid, rtype = STAR_GROUP_CHAT_ID, "chat_id"
    else:
        rid, rtype = TRIAL_USER_OPEN_ID, "open_id"
    url = LARK_BASE + "/im/v1/messages?receive_id_type=" + rtype
    payload = {"receive_id": rid, "msg_type": "interactive",
               "content": json.dumps(card, ensure_ascii=False)}
    req = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8",
                 "Authorization": "Bearer " + token})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def patch_card(message_id, card):
    """原地编辑已有卡片（不新发消息）。"""
    token = get_token()
    req = urllib.request.Request(
        LARK_BASE + "/im/v1/messages/" + message_id, method="PATCH",
        data=json.dumps({"content": json.dumps(card, ensure_ascii=False)},
                        ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8",
                 "Authorization": "Bearer " + token})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=30).read())
    except urllib.error.HTTPError as e:
        return {"code": -1, "msg": "HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:300])}


def send_card(card, mode):
    token = get_token()
    j = _post_message(card, mode, token)
    if j.get("code") == 0:
        return j
    msg = str(j.get("msg", ""))
    if "invalid user resource" in msg.lower() or "at/person" in msg or j.get("code") == 230001:
        # @ 的 open_id 在目标会话里无效时，降级为纯文本 @ 重发一次
        j2 = _post_message(_strip_at(card), mode, token)
        if j2.get("code") == 0:
            return j2
        j = j2
    raise RuntimeError("飞书发送失败：%s" % msg)


# ---------------------------------------------------------------- 主流程
def persist_result(record):
    with open(os.path.join(DATA_DIR, "last_result.json"), "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=1)


def run_once(mode="live", force=False, log=print, reuse_message_id=None, reuse_mode=None):
    """
    返回 dict。严格闸门：data_date != 昨天 时，下载/分析/发送等所有步骤都不执行。
    已有当天同一模式的卡片（reuse_message_id）时，只做 PATCH 原地编辑，绝不新发消息。
    """
    date, sc = fetch_board()
    target = yesterday()
    log("看板数据日期 = %s ｜ 目标（昨天）= %s" % (date, target))

    if not force and date != target:
        log("⛔ 日期闸门未通过 → 图片下载、4 要点分析、卡片推送等所有后续步骤均不执行")
        rec = {"ok": False, "gate": "blocked", "date": date, "target": target,
               "mode": mode, "ts": now().strftime("%Y-%m-%d %H:%M:%S")}
        # 闸门未通过不覆盖上一次成功结果，只记录本次检查
        with open(os.path.join(DATA_DIR, "last_check.json"), "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=1)
        return rec

    log("✅ 日期闸门通过，开始执行完整流程")
    img = capture_image(date)
    log("图片：%s" % (img or "下载跳过（环境无浏览器），分析基于同源结构化数据"))
    # 当天图片上传一次，卡片用当天 image_key（避免群里长期显示旧图）
    if img:
        try:
            if star_image_key(date) == STAR_IMAGE_KEY:
                key = upload_image(img)
                with open(STAR_IMAGE_FILE, "w", encoding="utf-8") as f:
                    json.dump({"date": date, "image_key": key,
                               "ts": now().strftime("%Y-%m-%d %H:%M:%S")},
                              f, ensure_ascii=False, indent=1)
                log("顾客满意明细图已上传：image_key=%s" % key)
        except Exception as e:
            log("顾客满意明细图上传失败（沿用历史图）：%s" % e)

    res = analyze(sc, date)
    log("分析完成：满意<3 %d 家｜星级下滑 %d 家｜不满意>20 %d 家｜回复率<100%% %d 家"
        % (len(res["p1"]), sum(len(v) for v in res["p2"].values()),
           len(res["p3"]), len(res["p4"])))

    use_at = (mode == "live")
    card = build_card(res, mode, use_at=use_at)

    reused = bool(reuse_message_id) and (reuse_mode in (None, mode))
    if reused:
        j = patch_card(reuse_message_id, card)
        if j.get("code") != 0:
            log("⚠️ 第 1 张卡片原地编辑失败（不新发）：%s" % j.get("msg"))
            mid = reuse_message_id
        else:
            mid = reuse_message_id
            log("第 1 张卡片已原地编辑：message_id=%s（未新发消息）" % mid)
    else:
        sent = send_card(card, mode)
        mid = (sent.get("data") or {}).get("message_id", "")
        log("第 1 张卡片已发出：mode=%s message_id=%s" % (mode, mid))

    rec = {
        "ok": True, "gate": "passed", "mode": mode, "date": date, "target": target,
        "ts": now().strftime("%Y-%m-%d %H:%M:%S"), "edited": reused,
        "image": img, "analysis": res, "message_id": mid,
        "target_name": "东莞-（莫ej）星级店长群" if mode == "live" else "莫恩健（本人私聊）",
    }
    persist_result(rec)
    with open(os.path.join(DATA_DIR, "card_%s.json" % date), "w", encoding="utf-8") as f:
        json.dump(card, f, ensure_ascii=False, indent=1)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["live", "trial"], default="live")
    ap.add_argument("--force", action="store_true", help="忽略日期闸门（仅联调使用）")
    a = ap.parse_args()
    rec = run_once(mode=a.mode, force=a.force)
    print(json.dumps({k: v for k, v in rec.items() if k != "analysis"},
                     ensure_ascii=False, indent=2))
    return 0 if rec.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
