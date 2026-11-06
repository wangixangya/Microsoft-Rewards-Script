#!/usr/bin/env python3
"""解析 microsoft-rewards 日志，产出按天/按账号/按任务项的收益统计。

数据来源：
  1) logs-7d.txt    旧的 cron 容器归档日志（docker logs 导出）
  2) runlog.jsonl   面板收集器从控制 API /logs 落盘的 raw 行（一次运行一份）
权威口径：每个账号的 ACCOUNT-END pointsGained；
分项来自各任务日志，按 (日期,账号,offerId) 去重取最大值，避免重跑重复计数。
"""
import json
import os
import re
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
ARCHIVE = os.path.join(BASE, "logs-7d.txt")
RUNLOG = os.path.join(BASE, "runlog.jsonl")
OUT = os.path.join(BASE, "history.json")
_WRITE_LOCK = threading.Lock()

LINE_RE = re.compile(
    r"^\[(\d{1,2})/(\d{1,2})/(\d{4}),\s+(\d{1,2}):(\d{2}):(\d{2})\s*(AM|PM)\]\s*"
    r"\[([^\]]+)\]\s*\[(\w+)\]\s*(?:(\w+)\s*)?\[([^\]]+)\]\s*(.*)$"
)

CATS = [
    ("dailySet", "每日任务集"),
    ("promotions", "活动/促销"),
    ("checkin", "每日签到"),
    ("read", "阅读赚积分"),
    ("searchDesktop", "桌面搜索"),
    ("searchMobile", "移动搜索"),
    ("punchcard", "任务卡"),
    ("bonus", "奖励领取"),
    ("other", "其他"),
]
LABEL = dict(CATS)
TZ = timezone(timedelta(hours=8))


def new_acct():
    return {"total": 0, "balance": None, "lastRunAt": None, "email": None,
            "offers": defaultdict(int), "read": 0, "search": defaultdict(int),
            "checkin": 0, "punch": 0, "bonus": 0}


def parse_lines(lines):
    days = defaultdict(lambda: defaultdict(new_acct))
    read_seen = set()
    for line in lines:
        m = LINE_RE.match(line.strip())
        if not m:
            continue
        mo, da, yr, hh, mi, ss, ap, user, level, platform, title, msg = m.groups()
        if user in ("MAIN", "API"):
            continue
        hh = int(hh) % 12 + (12 if ap == "PM" else 0)
        date = f"{int(yr):04d}-{int(mo):02d}-{int(da):02d}"
        rec = days[date][user]

        if title == "ACCOUNT-END":
            mp = re.search(r"pointsGained=(-?\d+)", msg)
            mb = re.search(r"currentBalance=(\d+)", msg)
            if mp:
                rec["total"] += int(mp.group(1))
            if mb:
                rec["balance"] = int(mb.group(1))
            if "Completed account:" in msg:
                rec["email"] = msg.split("Completed account:")[-1].split("|")[0].strip()
            rec["lastRunAt"] = f"{date}T{hh:02d}:{mi}:{ss}"
            continue

        mp = re.search(r"pointsGained=(-?\d+)", msg)
        if not mp:
            continue
        n = int(mp.group(1))
        if n <= 0:
            continue

        if title == "URL-REWARD":
            mid = re.search(r"offerId=([^\s|]+)", msg)
            oid = mid.group(1) if mid else f"{title}-{mo}{da}-{mi}{ss}-{n}"
            cat = "dailySet" if "DailySet" in oid else "promotions"
            key = (cat, oid)
            rec["offers"][key] = max(rec["offers"].get(key, 0), n)
        elif title == "DAILY-CHECK-IN":
            rec["offers"][("checkin", f"{date}-{platform}")] = max(
                rec["offers"].get(("checkin", f"{date}-{platform}"), 0), n)
        elif title == "READ-TO-EARN":
            if msg.startswith("Completed Read to Earn"):
                k = (date, user)
                if k not in read_seen:
                    read_seen.add(k)
                    rec["read"] = max(rec["read"], n)
        elif title == "SEARCH-BING":
            if "Completed Bing searches" in msg:
                continue
            pk = "searchDesktop" if platform == "DESKTOP" else "searchMobile"
            rec["search"][pk] += n
        elif title == "PUNCHCARD":
            rec["punch"] = max(rec["punch"], n)
        elif title.startswith("CLAIM-BONUS"):
            rec["bonus"] = max(rec["bonus"], n)
    return days


def acct_tasks(rec):
    tasks = defaultdict(int)
    for (cat, _oid), v in rec["offers"].items():
        tasks[cat] += v
    for k, v in rec["search"].items():
        tasks[k] += v
    if rec["read"]:
        tasks["read"] += rec["read"]
    if rec["punch"]:
        tasks["punchcard"] += rec["punch"]
    if rec["bonus"]:
        tasks["bonus"] += rec["bonus"]
    total = rec["total"] or sum(tasks.values())
    s = sum(tasks.values())
    # 分项超过权威总额时按比例压缩，保证总数一致
    if total and s > total:
        ratio = total / s
        tasks = defaultdict(int, {k: int(round(v * ratio)) for k, v in tasks.items()})
        s = sum(tasks.values())
    if total and total > s:
        tasks["other"] += total - s
    return total, {k: int(v) for k, v in tasks.items() if v}


def collect_lines():
    lines = []
    for path in (ARCHIVE,):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines.extend(f.readlines())
    if os.path.exists(RUNLOG):
        with open(RUNLOG, "r", encoding="utf-8", errors="replace") as f:
            for ln in f:
                try:
                    obj = json.loads(ln)
                    if obj.get("raw"):
                        lines.append(str(obj["raw"]) + "\n")
                except Exception:
                    continue
    return lines


def build(days=14):
    raw = parse_lines(collect_lines())
    today = datetime.now(TZ).date()
    out_days = []
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        rec = raw.get(d, {})
        accounts, tasks_total, total = {}, defaultdict(int), 0
        for acct, r in rec.items():
            t, tasks = acct_tasks(r)
            accounts[acct] = {"email": r.get("email") or acct, "total": t,
                              "balance": r.get("balance"), "tasks": tasks,
                              "lastRunAt": r.get("lastRunAt")}
            total += t
            for k, v in tasks.items():
                tasks_total[k] += v
        out_days.append({"date": d, "total": total, "accounts": accounts,
                         "tasks": {k: int(v) for k, v in tasks_total.items()}})
    return {
        "generatedAt": int(time.time()),
        "days": out_days,
        "categories": [{"key": k, "label": LABEL[k]} for k, _ in CATS],
        "accounts": sorted({a for dd in out_days for a in dd["accounts"]}),
    }


def refresh(days=14):
    data = build(days)
    # 并发安全：collector / HTTP 请求 / 推送线程都会调用 refresh，
    # 共用同一个 .tmp 会互相覆盖写出半截 JSON。加锁 + 每进程唯一临时文件。
    with _WRITE_LOCK:
        tmp = f"{OUT}.tmp.{os.getpid()}.{threading.get_ident()}"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, OUT)
    return data


if __name__ == "__main__":
    data = refresh(14)
    for d in data["days"][-8:]:
        print(d["date"], d["total"],
              {a: v["total"] for a, v in d["accounts"].items()},
              {k: v for k, v in d["tasks"].items() if v})
