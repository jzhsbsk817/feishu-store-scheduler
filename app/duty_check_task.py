# -*- coding: utf-8 -*-
"""22:00 分群「6 点未反馈统计」卡（各发各的群、各 @ 各的店长）。

【模板来源】群内 11-06 23:30 由本机器人发出的「6 点未反馈统计」post 卡。
用户 2026-11-09 要求「今天 22 点，按照上一次的统计模板，各发各的群 @店长，
当天未发、近三天未发、近七天未发 top3」，并追加「当天未测油的也要统计」。
四段口径沿用旧卡：
  1 今日未反馈门店名单（当天未发）       —— 今天还没交「值班自查 6 点模板」的门店
  2 近 3 天持续不反馈名单（近三天未发） —— 近 3 天一次都没交的门店
  3 近 7 天 top3（近七天未发 top3）      —— 近 7 天反馈天数最少的 3 家（每天去重计 1 次，7 天全勤不计）
  4 今天未测油的门店（文本未含第 6 点炸油更换内容）—— 当天反馈里没有第 6 点填写值

【数据源】两个反馈群的消息（不是星级群）：
  T 门店反馈收集-莫恩健   oc_38e3b9960d0f4069c4a3130b6dff75d6   （17 家 T 门店）
  小加盟店长沟通群-莫恩健 oc_9847adb724bc8cf7da2b1ac4bfc2f6da   （9 家 M 门店）
T 门店只在 T 群计、M 门店只在 M 群计；各自只 @ 本群店长（open_id 已核对全部在群内）。

【口径】沿用 2026-11-08「值班自查 6 点模板 · 近 7 天反馈统计」：
一次完整模板提交按自然日去重计 1 次；拆条的 3./5./6. 点位补充、图片视频并入同一次；
门店靠「门店：xxx」/ post 标题 / 正文别名识别，不带店名的用该 sender 全周消息投票回填；
排除「门店收货标准」「水印相机自查」及统计卡/提醒消息；寮步城市学院店不纳入，共 26 家。
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feedback_task as F

BASE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(BASE, "config")

CHATS = {
    "T": "oc_38e3b9960d0f4069c4a3130b6dff75d6",
    "M": "oc_9847adb724bc8cf7da2b1ac4bfc2f6da",
}
GROUP_NAME = {
    "T": "T 门店反馈收集-莫恩健",
    "M": "小加盟店长沟通群-莫恩健",
}

MAP = json.load(open(os.path.join(CFG, "store_mapping.json"), encoding="utf-8"))
MGR = json.load(open(os.path.join(CFG, "manager_openids.json"), encoding="utf-8"))
OID2 = json.load(open(os.path.join(CFG, "openid_to_store.json"), encoding="utf-8"))

EXCLUDE = "城市学院"     # 寮步城市学院店不统计
SHOPS = [m for m in MAP if EXCLUDE not in m["门店名称"]]


def _short(s):
    return str(s or "").replace("东莞市", "").replace("东莞", "")


# 短名 -> 门店信息（含店长姓名、open_id、T/M）
STD = {}
for m in SHOPS:
    k = _short(m["门店名称"])
    mi = MGR.get(m["门店名称"], {})
    STD[k] = {"tm": m["加盟T/M"], "mgr": mi.get("店长") or m.get("店长") or "",
              "oid": mi.get("open_id", "")}
TM = {k: v["tm"] for k, v in STD.items()}

ALIAS = {
    "厚街珊美店": ["珊美"], "厚街万达店": ["万达"], "寮步富竹山店": ["富竹山"],
    "寮步牛杨店": ["牛杨"], "寮步铭尚发到家店": ["铭尚", "发到家"],
    "寮步良平路店": ["良平"], "寮步凫山店": ["凫山"], "厚街寮厦店": ["寮厦"],
    "沙田大道店": ["沙田大道"], "寮步红荔路店": ["红荔路"],
    "沙田丽海中路店": ["丽海中路"], "寮步镇西溪店": ["西溪"],
    "寮步下岭贝店": ["下岭贝"], "虎门新天地店": ["新天地"],
    "寮步万联百货店": ["万联"], "厚街汀山店": ["汀山"], "厚街新塘店": ["新塘"],
    "南栅文明路店": ["文明路", "南栅"], "虎门威远店": ["威远"],
    "厚街盛和广场店": ["盛和"], "虎门新沙埔店": ["新沙埔", "新沙浦"],
    "厚街大汇下汴店": ["大汇", "下汴"], "石碣嘉荣广场店": ["嘉荣", "石碣"],
    "万科珠江东岸店": ["珠江东岸", "万科"], "厚街福民路店": ["福民路"],
    "厚街中学店": ["厚街中学"],
}
ALIAS_LIST = sorted([(a, s) for s, als in ALIAS.items() for a in als],
                    key=lambda x: -len(x[0]))
NOISE = ("反馈次数", "未反馈统计", "未反馈门店", "不合格提醒", "请核实",
         "今日未做反馈", "请尽快", "统计窗口", "关注置顶", "This message was recalled")

# 第 6 点题目行本身含「超过3天」「更换直接写更换即可」，判定前必须剔除，
# 否则会把只抄了题目、没填内容的门店误判成已测油。
OIL_TOPIC = "炸油更换情况"


def oil_done(txt):
    """当天该门店文本里是否有第 6 点「炸油更换」的实际填写值。"""
    body = "\n".join(l for l in str(txt or "").split("\n") if OIL_TOPIC not in l)
    return bool(re.search(r"单缸|双缸|换油|比色|更换", body))


def norm(s):
    return re.sub(r"[\s店（）()、,，。.:：·\-—0-9]", "", str(s or ""))


def match_store(txt):
    tn = norm(txt)
    for a, std in ALIAS_LIST:
        if norm(a) and norm(a) in tn:
            return std
    return ""


def extract_text(it):
    mt, c = it.get("msg_type"), (it.get("body") or {}).get("content", "")
    if mt == "text":
        try:
            return json.loads(c).get("text", "")
        except Exception:
            return str(c)[:300]
    if mt == "post":
        try:
            o = json.loads(c)
        except Exception:
            return str(c)[:300]
        parts = [o.get("title", "") or ""]
        for row in (o.get("content") or []):
            for e in row:
                if e.get("tag") == "text":
                    parts.append(e.get("text", ""))
        return "\n".join(parts)
    return ""


def log(msg, sink=print):
    try:
        sink("[6点统计] " + str(msg))
    except Exception:
        pass


def fetch_chat(chat_id, t0, t1, sink=print):
    """分页拉取一个群 [t0, t1) 区间的全部消息（秒级时间戳）。"""
    tok = F.S.get_token()
    items, pt = [], ""
    for _ in range(40):
        u = ("/open-apis/im/v1/messages?container_id_type=chat&container_id=%s"
             "&sort_type=ByCreateTimeAsc&page_size=50&start_time=%d&end_time=%d"
             % (chat_id, t0, t1))
        if pt:
            u += "&page_token=" + pt
        j = F._api("GET", u, tok, timeout=30)
        if j.get("code") != 0:
            log("拉取群消息失败：%s" % j.get("msg"), sink)
            break
        d = j.get("data") or {}
        items += d.get("items", [])
        pt = d.get("page_token", "")
        if not d.get("has_more") or not pt:
            break
    return items


def compute(today=None, sink=print):
    """实时算四段名单。返回 date / seven / three / stat / lists。"""
    today = today or datetime.now()
    d0 = today.replace(hour=0, minute=0, second=0, microsecond=0)
    seven = [(d0 - timedelta(days=i)).strftime("%m-%d") for i in range(6, -1, -1)]  # 近7天含今天
    three = seven[-3:]                                                                # 近3天含今天
    day_str = d0.strftime("%Y-%m-%d")
    # 多拉 1 天用于 sender 归属投票
    t0 = int((d0 - timedelta(days=7)).timestamp())
    t1 = int((d0 + timedelta(days=1)).timestamp())

    MSGS = {g: fetch_chat(cid, t0, t1, sink=sink) for g, cid in CHATS.items()}
    log("拉取消息 T %d 条 / M %d 条（%s ~ %s）"
        % (len(MSGS["T"]), len(MSGS["M"]), seven[0], seven[-1]), sink)

    # 结构化
    ROWS = []
    for g in ("T", "M"):
        for it in MSGS[g]:
            ts = int(it.get("create_time") or 0) / 1000
            if not (t0 <= ts < t1):
                continue
            txt = extract_text(it)
            oid = (it.get("sender") or {}).get("id", "")
            dt = datetime.fromtimestamp(ts)
            store = ""
            for pat in (r"门店[:：]\s*([^\s，,。\n]+)", r"编号店名[:：]\s*([^\s，,。\n]+)",
                        r"店名[:：]\s*([^\s，,。\n]+)"):
                m = re.search(pat, txt)
                if m:
                    store = match_store(m.group(1))
                    if store:
                        break
            if not store and it.get("msg_type") == "post":
                try:
                    store = match_store(json.loads(it["body"]["content"]).get("title", ""))
                except Exception:
                    pass
            if not store:
                store = match_store(txt[:60])
            if not store and oid in OID2:
                store = _short(OID2[oid].get("门店名称"))
            ROWS.append({"grp": g, "oid": oid, "ts": ts, "dt": dt,
                         "day": dt.strftime("%m-%d"), "store_raw": store,
                         "noise": any(n in txt for n in NOISE), "txt": txt})
    ROWS.sort(key=lambda r: (r["grp"], r["ts"]))

    # sender 全周投票（含窗口外消息），只用于回填不带店名的模板帖
    votes = defaultdict(Counter)
    for g in ("T", "M"):
        for it in MSGS[g]:
            oid = (it.get("sender") or {}).get("id", "")
            t = extract_text(it)
            if not t or any(n in t for n in NOISE):
                continue
            s = match_store(t[:400])
            if s:
                votes[(g, oid)][s] += 1
    oid_store = {k: c.most_common(1)[0][0] for k, c in votes.items()}

    # 归属到门店（显式店名优先，其次 sender 投票），仅保留「门店属于本群」
    def owner_of(r):
        s = r["store_raw"] or oid_store.get((r["grp"], r["oid"]), "")
        return s if (s in TM and TM[s] == r["grp"]) else ""

    # 当天文本（用于第 6 点测油判定）：合并该门店当天所有非噪声消息
    text_by = defaultdict(list)
    for r in ROWS:
        s = owner_of(r)
        if s and not r["noise"]:
            text_by[(s, r["day"])].append(r["txt"])

    # 聚类：同 sender、相邻 ≤ 25 分钟
    GAP = 25 * 60
    batches = []
    for g in ("T", "M"):
        cur, last_oid, last_ts = [], None, 0
        for r in [x for x in ROWS if x["grp"] == g]:
            if cur and (r["oid"] != last_oid or r["ts"] - last_ts > GAP):
                batches.append(list(cur))
                cur = []
            cur.append(r)
            last_oid, last_ts = r["oid"], r["ts"]
        if cur:
            batches.append(cur)

    def batch_info(b):
        body = "\n".join(x["txt"] for x in b if not x["noise"])
        if not body.strip() or "收货标准" in body or "水印相机" in body:
            return None
        has_title = bool(re.search(r"值班自查\s*[56]\s*个点", body))
        has_pts = bool(re.search(r"(?:^|\n)\s*[1-6][\.、．]\s*(?:裸手|重度|非标|解冻|裹粉|录制)", body))
        if not (has_title or has_pts):
            return None
        cs = Counter(owner_of(x) for x in b if owner_of(x) and not x["noise"])
        store = cs.most_common(1)[0][0] if cs else ""
        return {"grp": b[0]["grp"], "day": b[0]["day"], "store": store}

    FB = [i for i in (batch_info(b) for b in batches) if i and i["store"]]
    log("有效反馈批次 %d" % len(FB), sink)

    by_store = defaultdict(set)
    for i in FB:
        by_store[i["store"]].add(i["day"])

    stat = {}
    for k, info in STD.items():
        ds = by_store.get(k, set()) & set(seven)
        oil = oil_done("\n".join(text_by.get((k, seven[-1]), [])))
        stat[k] = {"tm": info["tm"], "mgr": info["mgr"], "oid": info["oid"],
                   "days": sorted(ds), "n": len(ds), "oil": oil,
                   "marks": "".join("●" if d in ds else "○" for d in seven)}

    lists = {}
    for g in ("T", "M"):
        ks = [k for k, v in STD.items() if v["tm"] == g]
        today_un = [k for k in ks if seven[-1] not in stat[k]["days"]]
        three_un = [k for k in ks if not (set(stat[k]["days"]) & set(three))]
        rank = [k for k in ks if stat[k]["n"] < 7]           # 7 天全勤不计
        rank.sort(key=lambda k: (stat[k]["n"], ks.index(k)))
        oil_un = [k for k in ks if not stat[k]["oil"]]        # 当天未测油（含当天未发者）
        lists[g] = {"today": today_un, "three": three_un, "top3": rank[:3],
                    "oil": oil_un, "shops": len(ks),
                    "full": sum(1 for k in ks if stat[k]["n"] == 7)}
    return {"date": day_str, "seven": seven, "three": three, "stat": stat,
            "lists": lists, "n_msgs": {g: len(MSGS[g]) for g in ("T", "M")}}


def _at(info, use_at=True):
    """正式：真 @（<at id=open_id>）；预览/降级：@姓名 文本。"""
    name = info["mgr"] or "店长"
    if use_at and info["oid"]:
        return '<at id=%s></at>' % info["oid"]
    return "@" + name


def _md(t):
    return {"tag": "markdown", "content": t}


def build_card(grp, data, use_at=True, preview=False):
    """构建某群的「6 点未反馈统计」卡（沿用 11-06 旧卡四段文案）。"""
    st, L = data["stat"], data["lists"][grp]
    seven, three = data["seven"], data["three"]
    nm = GROUP_NAME[grp]

    head = ("**【6 点未反馈统计 · %s 22:00】**\n" % data["date"]
            + "群：%s ｜ 本群门店 %d 家 ｜ 统计窗口：今日 / 近3天 / 近7天"
            % (nm, L["shops"]))
    if preview:
        head += ("\n<font color='grey'>注：本卡为私聊预览，生成于 %s；此刻今日门店多尚未开始反馈，"
                 "第 1、4 段显示的是当前实时状态。22:00 正式发群时会重新拉取当天数据计算。</font>"
                 % datetime.now().strftime("%m-%d %H:%M"))

    sec1 = ["**1 今日未反馈门店名单（%d 家）**" % len(L["today"])]
    if L["today"]:
        sec1 += ["　%s %s" % (k, _at(st[k], use_at)) for k in L["today"]]
    else:
        sec1.append("　<font color='green'>今日全部已反馈 ✅</font>")

    sec2 = ["**2 近 3 天持续不反馈名单（%s～%s · %d 家）**"
            % (three[0], three[-1], len(L["three"]))]
    if L["three"]:
        sec2 += ["　%s %s" % (k, _at(st[k], use_at)) for k in L["three"]]
    else:
        sec2.append("　<font color='grey'>暂无</font>")

    sec3 = ["**3 近 7 天 top3 的门店（反馈最少 · 每天去重计 1 次，7 天全勤不计）**"]
    if L["top3"]:
        sec3 += ["　%s  %d/7 天  %s" % (k, st[k]["n"], _at(st[k], use_at))
                 for k in L["top3"]]
    else:
        sec3.append("　<font color='grey'>全部 7 天全勤，无 top3</font>")

    sec4 = ["**4 今天未测油的门店（%d 家 · 文本未含第 6 点炸油更换内容）**" % len(L["oil"])]
    if L["oil"]:
        sec4 += ["　%s %s" % (k, _at(st[k], use_at)) for k in L["oil"]]
    else:
        sec4.append("　<font color='green'>今日全部已测油 ✅</font>")

    tail = ("<font color='grey'>口径：一次完整「值班自查 6 点模板」提交按自然日去重计 1 次；"
            "门店只在自己应属的群计数（%s 群）；拆条补点/图片并入同一次；"
            "第 6 点以「单缸/双缸/换油/更换」等实际填写值为准，仅抄题目不算。"
            "当天未发者自然也未测油，会同时出现在 1、4 两段。"
            "数据窗口 %s ~ %s（近 7 个自然日含今日）；本群 %d 家中 7 天全勤 %d 家。</font>"
            % (grp, seven[0], seven[-1], L["shops"], L["full"]))
    stamp = ("<font color='grey'>%s 生成 · 22:00 自动发本群 · 数据来源：本群消息</font>"
             % datetime.now().strftime("%m-%d %H:%M"))

    tag = "预览 · 拟发 %s 群" % grp if preview else "分群统计"
    elements = [_md(head), {"tag": "hr"}, _md("\n".join(sec1)), {"tag": "hr"},
                _md("\n".join(sec2)), {"tag": "hr"}, _md("\n".join(sec3)),
                {"tag": "hr"}, _md("\n".join(sec4)), {"tag": "hr"}, _md(tail),
                {"tag": "markdown", "text_align": "center", "content": stamp}]
    return {
        "schema": "2.0",
        "config": {"update_multi": True, "width_mode": "default"},
        "header": {
            "title": {"tag": "plain_text", "content": "6 点未反馈统计"},
            "subtitle": {"tag": "plain_text",
                         "content": "%s · 22:00 · %s" % (data["date"], nm)},
            "template": "blue" if preview else "orange",
            "text_tag_list": [{"tag": "text_tag",
                               "text": {"tag": "plain_text", "content": tag},
                               "color": "blue" if preview else "orange"}]},
        "body": {"direction": "vertical", "padding": "12px 12px 14px 12px",
                 "vertical_spacing": "medium", "elements": elements},
    }


def _post_chat(card, chat_id, sink=print, fallback_card=None):
    """发到指定群；真 @ 在该群失效时，降级为文本 @ 版本重发一次。"""
    tok = F.S.get_token()
    def _send(c):
        body = {"receive_id": chat_id, "msg_type": "interactive",
                "content": json.dumps(c, ensure_ascii=False)}
        return F._api("POST", "/open-apis/im/v1/messages?receive_id_type=chat_id",
                      tok, body, timeout=30)
    j = _send(card)
    msg = str(j.get("msg", ""))
    if j.get("code") != 0 and ("invalid user resource" in msg.lower()
                               or "at/person" in msg or j.get("code") == 230001):
        log("真 @ 在该群失效，降级为文本 @ 重发", sink)
        j = _send(fallback_card or card)
    return j


def run_daily(sink=print):
    """正式：算 + 分群各发一张卡（真 @），由 app.py 22:00 调用。"""
    data = compute(sink=sink)
    out = {"ok": True, "date": data["date"], "groups": {}}
    for g, cid in CHATS.items():
        j = _post_chat(build_card(g, data, use_at=True, preview=False), cid, sink=sink,
                       fallback_card=build_card(g, data, use_at=False, preview=False))
        ok = j.get("code") == 0
        out["ok"] &= ok
        out["groups"][g] = {"code": j.get("code"), "msg": j.get("msg"),
                            "today": len(data["lists"][g]["today"]),
                            "three": len(data["lists"][g]["three"]),
                            "top3": len(data["lists"][g]["top3"]),
                            "oil": len(data["lists"][g]["oil"]),
                            "message_id": (j.get("data") or {}).get("message_id", "")}
        log("%s 群发送 %s：今日未发 %d / 近3天 %d / top3 %d / 未测油 %d"
            % (g, "✅" if ok else "❌ " + str(j.get("msg"))[:80],
               out["groups"][g]["today"], out["groups"][g]["three"],
               out["groups"][g]["top3"], out["groups"][g]["oil"]), sink)
    return out


def run_preview(sink=print):
    """预览：算 + 把两张「拟发各群」卡发到本人私聊（文本 @，不真 @、不写状态）。"""
    data = compute(sink=sink)
    out = {"ok": True, "date": data["date"], "groups": {}}
    for g in ("T", "M"):
        j = F.send_card(build_card(g, data, use_at=False, preview=True), "trial")
        ok = j.get("code") == 0
        out["ok"] &= ok
        out["groups"][g] = {"code": j.get("code"), "msg": j.get("msg"),
                            "today": len(data["lists"][g]["today"]),
                            "three": len(data["lists"][g]["three"]),
                            "top3": len(data["lists"][g]["top3"]),
                            "oil": len(data["lists"][g]["oil"])}
        log("预览卡 %s 群 %s" % (g, "✅" if ok else "❌ " + str(j.get("msg"))[:80]), sink)
    return out


def report_md(data):
    """生成可复核的 markdown 报告。"""
    st, seven = data["stat"], data["seven"]
    md = ["# 6 点未反馈统计 · %s 22:00（分群 @店长）" % data["date"], "",
          "**模板**：沿用群内 11-06「6 点未反馈统计」四段口径（含「当天未测油」）",
          "**口径**：一次完整「值班自查 6 点模板」提交按自然日去重计 1 次；门店只在自己应属的群计数；"
          "寮步城市学院店不纳入，共 26 家。", "",
          "**数据窗口**：%s ~ %s（近 7 个自然日，含今日）；●=当天有反馈 ○=无" % (seven[0], seven[-1]), ""]
    for g, name in (("T", GROUP_NAME["T"]), ("M", GROUP_NAME["M"])):
        L = data["lists"][g]
        md += ["## %s（%d 家）" % (name, L["shops"]), "",
               "### 1 今日未反馈门店名单（%d 家）" % len(L["today"]), ""]
        md += ["- %s %s" % (k, st[k]["mgr"]) for k in L["today"]] or ["- 无"]
        md += ["", "### 2 近 3 天持续不反馈名单（%d 家）" % len(L["three"]), ""]
        md += ["- %s %s" % (k, st[k]["mgr"]) for k in L["three"]] or ["- 暂无"]
        md += ["", "### 3 近 7 天 top3（反馈最少，7 天全勤不计）", "",
               "| 门店 | 店长 | 反馈天数 | 逐日 %s→%s |" % (seven[0], seven[-1]),
               "|---|---|---:|---|"]
        for k in L["top3"]:
            md.append("| %s | %s | %d/7 | %s |" % (k, st[k]["mgr"], st[k]["n"], st[k]["marks"]))
        md += ["", "### 4 今天未测油的门店（%d 家 · 文本未含第 6 点炸油更换内容）" % len(L["oil"]), ""]
        md += ["- %s %s" % (k, st[k]["mgr"]) for k in L["oil"]] or ["- 无"]
        md += ["", "**本群 7 天全勤 %d 家**" % L["full"], ""]
    md += ["---", "", "数据源：T 群 %d 条 / M 群 %d 条消息（实时拉取）"
           % (data["n_msgs"]["T"], data["n_msgs"]["M"]), ""]
    return "\n".join(md)


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "dry"
    if action == "dry":
        d = compute()
        print("\n日期 %s ｜ 近7天 %s ｜ 近3天 %s"
              % (d["date"], d["seven"], d["three"]))
        for g in ("T", "M"):
            L = d["lists"][g]
            print("\n== %s 群（%d 家）==" % (g, L["shops"]))
            print(" 1 今日未反馈(%d): %s" % (len(L["today"]), L["today"]))
            print(" 2 近3天持续不反馈(%d): %s" % (len(L["three"]), L["three"]))
            print(" 3 近7天top3: %s" % [(k, d["stat"][k]["n"]) for k in L["top3"]])
            print(" 4 今天未测油(%d): %s" % (len(L["oil"]), L["oil"]))
    elif action == "preview":
        print(run_preview())
    elif action == "push":
        print(run_daily())
    elif action == "report":
        d = compute()
        p = "/workspace/6点未反馈统计_%s_22时.md" % d["date"]
        open(p, "w", encoding="utf-8").write(report_md(d))
        print("报告已生成：", p)
    else:
        print("用法: duty_check_task.py [dry|preview|push|report]")
