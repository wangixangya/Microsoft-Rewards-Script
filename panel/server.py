#!/usr/bin/env python3
"""Microsoft Rewards 控制面板 —— 静态 UI + API 反向代理 + 计划任务
只用标准库，无第三方依赖。监听 0.0.0.0:5310。
"""
import base64
import datetime
import hashlib
import hmac
import json
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote, quote

BASE = os.path.dirname(os.path.abspath(__file__))
CONF = os.path.join(BASE, "panel.conf")
SCHED = os.path.join(BASE, "schedule.json")
STATE = os.path.join(BASE, "state.json")
PORT = int(os.environ.get("PANEL_PORT", "5310"))


def run_history_today():
    """从 v5 的 config/run-history.json 汇总「当天」每账号：余额、当日得分、状态、最后运行时间。
    容器重建、API 日志缓冲被冲掉时，这份文件依然是权威数据。"""
    path = "/root/microsoft-rewards-script/config/run-history.json"
    out = {}
    try:
        runs = json.load(open(path, encoding="utf-8"))
    except Exception:
        return out
    if isinstance(runs, dict):
        runs = runs.get("runs") or []
    today = time.strftime("%Y-%m-%d")
    for r in runs:
        ts = str(r.get("endedAt") or r.get("startedAt") or "")
        try:
            dt = datetime.datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
        except Exception:
            continue
        if dt.astimezone().strftime("%Y-%m-%d") != today:
            continue
        for acc in (r.get("run") or {}).get("accounts") or []:
            email = str(acc.get("email") or "").strip()
            if "@" not in email:
                continue
            k = email.split("@")[0]
            it = out.setdefault(k, {"initial": None, "balance": None, "status": "", "lastRunAt": ""})
            init, final = acc.get("initialPoints"), acc.get("finalPoints")
            if isinstance(init, int) and (it["initial"] is None or ts < it.get("firstTs", "9")):
                it["initial"] = init
                it["firstTs"] = ts
            if isinstance(final, int) and ts >= it.get("lastTs", ""):
                it["balance"] = final
                it["lastTs"] = ts
                it["status"] = str(acc.get("status") or "")
                it["lastRunAt"] = ts
    for it in out.values():
        if it["initial"] is not None and it["balance"] is not None:
            it["today"] = max(0, it["balance"] - it["initial"])
    return out


def sh(cmd, timeout=60):
    """跑一条只读 shell 命令，返回 (rc, stdout+stderr)。"""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return 1, str(e)


UPDATE_LOG = "/tmp/ms-update.log"
UPDATE_STATE = os.path.join(BASE, "update.json")
BASE_IMAGE = "ghcr.io/thenetsky/microsoft-rewards-script:5"
DERIVED_IMAGE = "ms-rewards:v5-cn"


def _img_digest(ref):
    rc, out = sh(f"docker image inspect -f '{{{{index .RepoDigests 0}}}}' {ref} 2>/dev/null", timeout=20)
    out = out.strip()
    return out.split("@")[-1] if rc == 0 and out else ""


def _img_created(ref):
    rc, out = sh(f"docker image inspect -f '{{{{.Created}}}}' {ref} 2>/dev/null", timeout=20)
    return out.strip()[:19] if rc == 0 and out else ""


def _img_size(ref):
    rc, out = sh(f"docker image inspect -f '{{{{.Size}}}}' {ref} 2>/dev/null", timeout=20)
    try:
        return round(int(out.strip()) / 1024 / 1024)
    except Exception:
        return None


def update_status():
    st = load_json(UPDATE_STATE, {})
    pid = st.get("pid")
    running = False
    if pid:
        try:
            os.kill(int(pid), 0)
            running = True
        except Exception:
            running = False
    tail = ""
    try:
        with open(UPDATE_LOG, "r", encoding="utf-8", errors="replace") as f:
            tail = "".join(f.readlines()[-40:])
    except Exception:
        pass
    if pid and not running and not st.get("finishedAt"):
        st["finishedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
        st["exitCode"] = 0 if "✅ 更新完成" in tail else 1
        try:
            save_json(UPDATE_STATE, st)
        except Exception:
            pass
    rc, ps = sh(f"docker ps --filter name=ms-rewards-api --format '{{{{.Status}}}}|{{{{.Image}}}}'", timeout=15)
    container = ps.strip() if rc == 0 else ""
    return {
        "running": running,
        "startedAt": st.get("startedAt", ""),
        "finishedAt": st.get("finishedAt", ""),
        "exitCode": st.get("exitCode"),
        "log": tail,
        "container": container,
        "derived": {"tag": DERIVED_IMAGE, "digest": _img_digest(DERIVED_IMAGE)[:19], "created": _img_created(DERIVED_IMAGE), "sizeMB": _img_size(DERIVED_IMAGE)},
        "base": {"tag": BASE_IMAGE, "digest": _img_digest(BASE_IMAGE)[:19]},
    }


def start_update():
    """后台执行 update-image.sh；返回 (ok, msg)"""
    st = load_json(UPDATE_STATE, {})
    pid = st.get("pid")
    if pid:
        try:
            os.kill(int(pid), 0)
            return False, "更新任务已在运行"
        except Exception:
            pass
    if run_state() == "running":
        return False, "正在跑积分任务，等它结束后再更新（避免打断运行）"
    try:
        os.chmod("/root/ms-panel/update-image.sh", 0o755)
    except Exception:
        pass
    with open(UPDATE_LOG, "w", encoding="utf-8") as f:
        f.write("")
    proc = subprocess.Popen(
        ["/bin/bash", "/root/ms-panel/update-image.sh"],
        stdout=open(UPDATE_LOG, "ab"), stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    save_json(UPDATE_STATE, {"pid": proc.pid, "startedAt": time.strftime("%Y-%m-%d %H:%M:%S"), "exitCode": None})
    return True, "已开始更新"


def self_update_status():
    st = load_json(os.path.join(BASE, "selfupdate.json"), {})
    pid = st.get("pid")
    running = False
    if pid:
        try:
            os.kill(int(pid), 0)
            running = True
        except Exception:
            running = False
    tail = ""
    try:
        with open("/tmp/ms-panel-selfupdate.log", "r", encoding="utf-8", errors="replace") as f:
            tail = "".join(f.readlines()[-30:])
    except Exception:
        pass
    return {"running": running, "startedAt": st.get("startedAt", ""), "log": tail}


def start_self_update():
    st = load_json(os.path.join(BASE, "selfupdate.json"), {})
    pid = st.get("pid")
    if pid:
        try:
            os.kill(int(pid), 0)
            return False, "面板更新已在运行"
        except Exception:
            pass
    os.chmod(os.path.join(BASE, "self-update.sh"), 0o755)
    open("/tmp/ms-panel-selfupdate.log", "w").close()
    proc = subprocess.Popen(["/bin/bash", os.path.join(BASE, "self-update.sh")],
                            stdout=open("/tmp/ms-panel-selfupdate.log", "ab"),
                            stderr=subprocess.STDOUT, start_new_session=True)
    save_json(os.path.join(BASE, "selfupdate.json"),
              {"pid": proc.pid, "startedAt": time.strftime("%Y-%m-%d %H:%M:%S")})
    return True, "已开始更新面板程序（约 10 秒，期间页面会短暂断开）"


def start_self_restart():
    subprocess.Popen(["/bin/bash", "-c", "sleep 1; systemctl restart ms-panel"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return True, "面板将在 1 秒后重启"


def load_kv(path):
    out = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


try:
    CONF_D = load_kv(CONF)
except Exception as e:
    raise SystemExit(f"读不到 {CONF}：{e}")
for _k in ("API_TOKEN", "PANEL_PASSWORD"):
    if not CONF_D.get(_k):
        raise SystemExit(f"panel.conf 缺少 {_k}，拒绝以空密钥启动")
API_BASE = CONF_D.get("API_BASE", "http://127.0.0.1:3010").rstrip("/")
API_TOKEN = CONF_D["API_TOKEN"]
PASSWORD = CONF_D["PANEL_PASSWORD"]
COOKIE_KEY = hmac.new(API_TOKEN.encode(), b"panel-cookie", hashlib.sha256).digest()
COOKIE_NAME = "msr_auth"
LOCK = threading.Lock()


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ---------- 计划任务 ----------
def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


CRON_FIELDS = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]


def cron_match(expr, tm):
    """极简 cron：支持 * 数字 列表 范围 /步长。
    非法表达式（*/0、a-b、越界）一律判不匹配，绝不抛异常——否则调度线程会一直进 except。"""
    parts = (expr or "").split()
    if len(parts) != 5:
        return False
    values = [tm.tm_min, tm.tm_hour, tm.tm_mday, tm.tm_mon, (tm.tm_wday + 1) % 7]
    try:
        for part, (lo, hi), val in zip(parts, CRON_FIELDS, values):
            if part == "*":
                continue
            ok = False
            for token in part.split(","):
                step = 1
                if "/" in token:
                    token, s = token.split("/", 1)
                    step = int(s)
                    if step < 1:
                        continue
                if token == "*":
                    start, end = lo, hi
                elif "-" in token:
                    a, b = token.split("-", 1)
                    start, end = int(a), int(b)
                else:
                    start = int(token)
                    end = hi if step > 1 else start
                if start < lo or end > hi or start > end:
                    continue
                if val in range(start, end + 1, step):
                    ok = True
                    break
            if not ok:
                return False
    except (ValueError, ZeroDivisionError, TypeError):
        return False
    return True


def api_call(method, path, body=None, timeout=60):
    url = API_BASE + path
    data = None
    headers = {"Authorization": "Bearer " + API_TOKEN}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 502, json.dumps({"error": str(e)}).encode()


def proxy_blocked(target):
    """面板不代理 /config（API_ALLOW_CONFIG_REVEAL=true 时能读出账号明文密码）。
    先做 URL 解码 + 路径规范化，避免 //config、/%63onfig、/x/../config 之类绕过。"""
    from urllib.parse import unquote
    p = (target or "").split("?", 1)[0]
    for _ in range(5):          # 迭代解码到不动点，挡 /%2563onfig 这类多重编码
        q = unquote(p)
        if q == p:
            break
        p = q
    p = "/" + "/".join(seg for seg in p.replace("\\", "/").split("/") if seg and seg != ".")
    parts = []
    for seg in p.split("/"):
        if seg == "..":
            if parts:
                parts.pop()
        elif seg:
            parts.append(seg)
    return bool(parts) and parts[0] == "config"


def update_state(patch):
    """state.json 的读改写必须原子，否则调度线程与 HTTP 线程会互相覆盖。"""
    with LOCK:
        st = load_json(STATE, {})
        st.update(patch)
        save_json(STATE, st)
        return st


def _recent_schedule_hit(expr, now_min=None, window_min=360):
    """返回「最近一次 cron 命中」距现在的分钟差；没有命中过返回 None。
    用于面板重启/宕机后的补跑判断，避免整天的任务直接丢失。"""
    now = time.localtime() if now_min is None else None
    base = time.mktime(now) if now is not None else None
    for back in range(0, window_min + 1):
        t = time.localtime(base - back * 60) if base is not None else time.localtime(time.time() - back * 60)
        if cron_match(expr, t):
            return back
    return None


def scheduler_loop():
    last_fire = load_json(STATE, {}).get("lastFire", "")
    while True:
        try:
            cfg = load_json(SCHED, {"enabled": False, "cron": "0 7 * * *"})
            cron = (cfg.get("cron") or "").strip()
            if cfg.get("enabled") and cron:
                tm = time.localtime()
                stamp = time.strftime("%Y%m%d%H%M", tm)
                fire = cron_match(cron, tm)
                reason = "定时命中"
                if not fire:
                    # 补跑：今天该跑的点已经过去了（面板重启/宕机导致错过），且最近 6 小时内命中过
                    st_json = load_json(STATE, {})
                    today = time.strftime("%Y-%m-%d", tm)
                    if st_json.get("lastFireDate") != today:
                        back = _recent_schedule_hit(cron)
                        if back is not None and back >= 1:
                            fire = True
                            reason = f"补跑（错过 {back} 分钟）"
                today_str = time.strftime("%Y-%m-%d", tm)
                if fire and last_fire != stamp:
                    st_prev = load_json(STATE, {})
                    # 失败退避：10 分钟内不重复尝试，避免 API 挂掉时每 20 秒洪泛
                    if reason.startswith("补跑") and time.time() - float(st_prev.get("lastAttemptAt") or 0) < 600:
                        last_fire = stamp
                        time.sleep(20)
                        continue
                    running = False
                    code, body = api_call("GET", "/status", timeout=15)
                    if code == 200:
                        try:
                            running = json.loads(body).get("state") == "running"
                        except Exception:
                            running = False
                    if running:
                        # 今天这个点已经“处理过了”，必须写盘，否则任务跑完后补跑逻辑会再触发一次
                        log("[sched] 已在运行，跳过本次触发")
                        update_state({"lastFire": stamp, "lastFireDate": today_str,
                                      "lastFireAt": int(time.time()), "lastResult": "already-running"})
                    else:
                        code, _ = api_call("POST", "/start", {}, timeout=30)
                        log(f"[sched] 触发运行（{reason}，cron={cron}，HTTP {code}）")
                        if code < 400:
                            update_state({"lastFire": stamp, "lastFireDate": today_str,
                                          "lastFireAt": int(time.time()), "lastResult": "started",
                                          "lastAttemptAt": int(time.time())})
                        else:
                            update_state({"lastAttemptAt": int(time.time()),
                                          "lastAttemptStamp": stamp,
                                          "lastResult": f"failed-{code}"})
                    last_fire = stamp
        except Exception as e:
            log("[sched] 异常", e)
        time.sleep(20)


# ---------- 日志采集 → 统计 ----------
RUNLOG = os.path.join(BASE, "runlog.jsonl")
_SEEN_PATH = os.path.join(BASE, "runlog.seen")


def _load_seen():
    """游标 = {"id": 最后采集的日志 id, "t": 最后采集条目的 receivedAt}。
    兼容旧的纯数字格式。"""
    try:
        with open(_SEEN_PATH, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        if not raw:
            return {"id": 0, "t": ""}
        if raw.startswith("{"):
            d = json.loads(raw)
            return {"id": int(d.get("id") or 0), "t": str(d.get("t") or "")}
        return {"id": int(raw), "t": ""}
    except Exception:
        return {"id": 0, "t": ""}


def _save_seen(v):
    """原子写游标：掉电/崩溃时不会留下半截文件（否则游标归零会重复落盘）。"""
    tmp = _SEEN_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(v))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, _SEEN_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass


def collector_loop():
    """把控制 API 的日志落盘（API 日志是内存态，容器重启就丢），并刷新统计。"""
    import stats as statsmod
    seen = _load_seen()
    last_id = seen["id"]
    last_t = seen["t"]
    last_refresh = 0
    while True:
        try:
            code, body = api_call("GET", "/logs?limit=1000", timeout=20)
            if code == 200:
                try:
                    data = json.loads(body)
                except Exception:
                    data = {}
                entries = data.get("logs") or []
                # 控制 API 重启后日志 id 从 1 重新计数，会用 last_id 永远过滤掉所有新日志。
                # 用 latestLogId < last_id 判定“日志流已重置”，把游标归零重新采集。
                try:
                    latest = int(data.get("latestLogId") or 0)
                except Exception:
                    latest = 0
                first_t = str((entries[0] or {}).get("receivedAt") or "") if entries else ""
                epoch_reset = bool((latest and latest < last_id) or
                                   (last_id and last_t and first_t and first_t > last_t))
                if epoch_reset:
                    # 控制 API 重启后日志 id 从 1 重新计数：游标归零，但保留 last_t
                    # 作为水位线，避免把整个缓冲区重新落盘导致统计重复计数。
                    log(f"[collector] 日志流重置（latest={latest} / 游标={last_id}），按时间水位线续采")
                    last_id = 0
                new_lines = []
                for e in entries:
                    if not isinstance(e, dict):
                        continue
                    eid = e.get("id") or 0
                    et = str(e.get("receivedAt") or e.get("ts") or "")
                    if eid <= last_id:
                        continue
                    if last_t and et:
                        # 只有新周期的第一轮才允许丢弃“同一时间戳”的条目（防重复落盘）；
                        # 平时必须用严格小于，否则同一秒内的第 2 条日志会被永久丢弃。
                        if et < last_t or (epoch_reset and et == last_t):
                            continue
                    raw = e.get("raw") or e.get("message")
                    if raw:
                        item = {"id": eid, "t": et, "raw": raw}
                        # v5 控制 API 给的是结构化日志：把归一等价字段一并落盘，
                        # stats.py 优先按结构化解析（raw 只作兜底）
                        if e.get("title"):
                            item.update({
                                "ti": str(e.get("title") or ""),
                                "msg": str(e.get("message") or ""),
                                "u": str(e.get("user") or ""),
                                "p": str(e.get("platform") or ""),
                                "lv": str(e.get("level") or ""),
                                "ts": str(e.get("ts") or ""),
                            })
                        new_lines.append(item)
                    if eid > last_id:
                        last_id = eid
                    if et > last_t:
                        last_t = et
                if new_lines:
                    with open(RUNLOG, "a", encoding="utf-8") as f:
                        for item in new_lines:
                            f.write(json.dumps(item, ensure_ascii=False) + "\n")
                if new_lines or last_id:
                    _save_seen({"id": last_id, "t": last_t})
            if time.time() - last_refresh > 120:
                statsmod.refresh(14)
                last_refresh = time.time()
        except Exception as e:
            log("[collector] 异常", e)
        time.sleep(30)



# ---------- 账号管理（env.list） ----------
ENVFILE = os.path.join(BASE, "env.list")
RECREATE = CONF_D.get("RECREATE_SCRIPT") or os.path.join(os.path.dirname(BASE), "recreate_ms.sh")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def env_lines():
    if not os.path.exists(ENVFILE):
        return []
    with open(ENVFILE, "r", encoding="utf-8") as f:
        return [ln.rstrip("\n") for ln in f]


def env_accounts():
    rows = {}
    for line in env_lines():
        m = re.match(r"^ACCOUNT_(\d+)_([A-Z0-9_]+)=(.*)$", line)
        if not m:
            continue
        idx, key, val = int(m.group(1)), m.group(2), m.group(3)
        rows.setdefault(idx, {})[key] = val
    out = []
    for idx in sorted(rows):
        d = rows[idx]
        if not d.get("EMAIL"):
            continue
        out.append({
            "index": idx,
            "email": d["EMAIL"],
            "geoLocale": d.get("GEO_LOCALE", ""),
            "hasPassword": bool(d.get("PASSWORD")),
            "hasTotp": bool(d.get("TOTP_SECRET")),
        })
    return out


def _backup_env():
    if os.path.exists(ENVFILE):
        bak = ENVFILE + ".bak." + time.strftime("%Y%m%d_%H%M%S")
        with open(ENVFILE, "rb") as src, open(bak, "wb") as dst:
            dst.write(src.read())


def _write_env(lines):
    tmp = ENVFILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip("\n") + "\n")
    os.replace(tmp, ENVFILE)


def add_account(payload):
    email = str(payload.get("email", "")).strip()
    password = str(payload.get("password", ""))
    geo = str(payload.get("geoLocale", "") or "cn").strip()
    totp = str(payload.get("totp", "")).strip()
    recovery = str(payload.get("recoveryEmail", "")).strip()
    if not EMAIL_RE.match(email):
        return {"error": "邮箱格式不对"}
    if not password:
        return {"error": "密码不能为空"}
    if any(a["email"].lower() == email.lower() for a in env_accounts()):
        return {"error": "该邮箱已在账号列表里"}
    idx = max([a["index"] for a in env_accounts()] or [0]) + 1
    lines = env_lines()
    while lines and lines[-1].strip() == "":
        lines.pop()
    lines += [
        f"ACCOUNT_{idx}_EMAIL={email}",
        f"ACCOUNT_{idx}_PASSWORD={password}",
        f"ACCOUNT_{idx}_GEO_LOCALE={geo}",
    ]
    if totp:
        lines.append(f"ACCOUNT_{idx}_TOTP_SECRET={totp}")
    if recovery:
        lines.append(f"ACCOUNT_{idx}_RECOVERY_EMAIL={recovery}")
    _backup_env()
    _write_env(lines)
    return {"ok": True, "index": idx, "email": email}


def remove_account(idx):
    accs = {a["index"]: a for a in env_accounts()}
    if idx not in accs:
        return {"error": f"没有序号 {idx} 的账号"}
    if len(accs) <= 1:
        return {"error": "至少保留一个账号"}
    keep = [ln for ln in env_lines() if not re.match(rf"^ACCOUNT_{idx}_", ln)]
    _backup_env()
    _write_env(keep)
    return {"ok": True, "removed": accs[idx]["email"]}


def run_rebuild(timeout=300):
    import subprocess
    try:
        p = subprocess.run(["bash", RECREATE], capture_output=True, text=True, timeout=timeout)
        return {"code": p.returncode,
                "out": (p.stdout or "").strip()[-1200:],
                "err": (p.stderr or "").strip()[-600:]}
    except subprocess.TimeoutExpired:
        return {"code": -1, "err": "重建超时"}
    except Exception as e:
        return {"code": -1, "err": str(e)}


def run_state():
    code, body = api_call("GET", "/status", timeout=10)
    if code != 200:
        return "unknown"
    try:
        return json.loads(body).get("state", "unknown")
    except Exception:
        return "unknown"


# ---------- 推送 ----------
def build_summary():
    """从统计里拼当天收益摘要，返回 (分数, 正文)。"""
    import stats as statsmod
    data = statsmod.refresh(2)
    today = data["days"][-1]
    yest = data["days"][-2]
    lines = [f"今日 {today['total']} 分（昨日 {yest['total']}）"]
    for acct, v in today["accounts"].items():
        bal = v.get("balance")
        lines.append(f"· {acct}: +{v['total']}" + (f"，余额 {bal}" if bal else ""))
    total_bal = sum((v.get("balance") or 0) for v in today["accounts"].values())
    if total_bal:
        lines.append(f"合计余额 {total_bal}")
    return today["total"], "\n".join(lines)


def notify_loop():
    """监听运行状态变化 → 推送；另管每日汇总。"""
    import notify as notifymod
    prev = None
    daily_sent = ""
    while True:
        try:
            cfg = notifymod.load()
            ev = cfg.get("events") or {}
            code, body = api_call("GET", "/status", timeout=10)
            st = json.loads(body) if code == 200 else {}
            state = st.get("state")
            if prev == "running" and state in ("idle", "failed", "error", "stopped"):
                last = st.get("lastExit") or {}
                code_exit = last.get("code")
                score, text = build_summary()
                if code_exit not in (0, None, 143):
                    if ev.get("on_error", True):
                        t = "Rewards 运行异常退出"
                        res = notifymod.broadcast(t, f"退出码 {code_exit}\n{text}")
                        log(f"[notify] 异常通知渠道 {len(res or [])} 个" if res else "[notify] 未配置渠道，异常未外发")
                elif ev.get("on_finish", True):
                    res = notifymod.broadcast(f"Rewards 运行完成 +{score} 分", text)
                    if res:
                        okn = sum(1 for r in res if r.get("ok"))
                        log(f"[notify] 完成通知已发送 {okn}/{len(res)} 个渠道")
                    else:
                        log("[notify] 未配置推送渠道，跳过完成通知（每日汇总仍由 hermes cron 发送）")
            if ev.get("daily_summary"):
                now = time.strftime("%H:%M")
                stamp = time.strftime("%Y%m%d") + now
                if now == (ev.get("daily_time") or "10:00") and daily_sent != stamp:
                    score, text = build_summary()
                    notifymod.broadcast(f"Rewards 每日汇总 {score} 分", text)
                    daily_sent = stamp
                    log("[notify] 已推送每日汇总")
            prev = state
        except Exception as e:
            log("[notify] 异常", e)
        time.sleep(15)


# ---------- HTTP ----------
def sign_cookie(ts):
    msg = str(ts).encode()
    return hmac.new(COOKIE_KEY, msg, hashlib.sha256).hexdigest()


def make_cookie():
    ts = int(time.time())
    return f"{COOKIE_NAME}={ts}.{sign_cookie(ts)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800"


def check_cookie(header):
    if not header:
        return False
    for part in header.split(";"):
        part = part.strip()
        if part.startswith(COOKIE_NAME + "="):
            raw = part.split("=", 1)[1]
            try:
                ts, sig = raw.split(".", 1)
                if int(ts) + 604800 < time.time():
                    return False
                return hmac.compare_digest(sig, sign_cookie(ts))
            except Exception:
                return False
    return False


# ---------- 登录限速（防局域网爆破） ----------
_LOGIN_FAILS = {}
_LOGIN_LOCK = threading.Lock()
LOGIN_MAX_FAIL = 5
LOGIN_LOCK_SEC = 300


def _login_state(ip):
    now = time.time()
    with _LOGIN_LOCK:
        n, until = _LOGIN_FAILS.get(ip, (0, 0))
        if until and now > until:
            _LOGIN_FAILS.pop(ip, None)
            return 0, 0
        return n, until


def _login_fail(ip):
    with _LOGIN_LOCK:
        now = time.time()
        if len(_LOGIN_FAILS) > 500:          # 扫描器伪造来源时防止内存无界增长
            for k in [k for k, (_n, u) in _LOGIN_FAILS.items() if not u or u < now][:400]:
                _LOGIN_FAILS.pop(k, None)
        n, until = _LOGIN_FAILS.get(ip, (0, 0))
        n += 1
        until = time.time() + LOGIN_LOCK_SEC if n >= LOGIN_MAX_FAIL else until
        _LOGIN_FAILS[ip] = (n, until)
        return n, until


def _login_ok(ip):
    with _LOGIN_LOCK:
        _LOGIN_FAILS.pop(ip, None)


MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 30          # 单连接读写超时，防 slowloris 占线程

    def log_message(self, fmt, *a):
        pass

    # --- helpers ---
    def send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, rel):
        root = os.path.realpath(BASE)
        path = os.path.realpath(os.path.join(root, rel.lstrip("/")))
        # 只允许两种目标：BASE/index.html 与 BASE/static/ 下的静态资源。
        # 仅做「在根目录内」判断不够——panel.conf / notify.json / runlog.seen 都在根目录里，
        # /static/../panel.conf 会直接读到密钥。
        static_dir = os.path.join(root, "static")
        allowed = path == os.path.join(root, "index.html") or path.startswith(static_dir + os.sep)
        ext = os.path.splitext(path)[1].lower()
        if not allowed or ext not in MIME or not os.path.isfile(path):
            self.send_json(404, {"error": "not found"})
            return
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def authed(self):
        return check_cookie(self.headers.get("Cookie"))

    def read_body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except Exception:
            n = 0
        if n > 1_048_576:          # 面板最大 1MB，别被超大 body 拖死线程
            return b""
        return self.rfile.read(n) if n else b""

    # --- routes ---
    def do_GET(self):
        u = urlparse(self.path)
        p = u.path

        if p in ("/", "/index.html"):
            return self.send_file("index.html")
        if p.startswith("/static/"):
            return self.send_file(p)

        if p == "/login":
            return self.send_file("index.html")

        if not self.authed():
            return self.send_json(401, {"error": "unauthorized"})

        if p == "/panel/update/status":
            return self.send_json(200, update_status())

        if p == "/panel/self-update/status":
            return self.send_json(200, self_update_status())

        if p == "/panel/schedule":
            return self.send_json(200, load_json(SCHED, {"enabled": False, "cron": "0 7 * * *"}))

        if p == "/panel/notify":
            import notify as notifymod
            safe = notifymod.load()
            # 不回传密码类字段的明文
            out = {"events": safe.get("events"), "channels": []}
            for ch in safe.get("channels", []):
                meta = notifymod.TYPES.get(ch.get("type"), {})
                secret_keys = {f[0] for f in meta.get("fields", []) if len(f) > 4 and f[4]}
                cfg = {}
                for k, v in (ch.get("config") or {}).items():
                    cfg[k] = ("******" if (k in secret_keys and v) else v)
                out["channels"].append({"id": ch.get("id"), "type": ch.get("type"),
                                        "name": ch.get("name"), "enabled": ch.get("enabled", True),
                                        "config": cfg})
            out["types"] = {k: {"label": v["label"], "hint": v["hint"], "fields": v["fields"]}
                            for k, v in notifymod.TYPES.items()}
            return self.send_json(200, out)

        if p == "/panel/accounts":
            # API 的账号运行状态是内存态，容器重建后就归零（累计积分/连续成功全变 0）。
            # 这里用面板自己落盘的统计补齐「累计余额 / 今日 / 近7日」，前端不再依赖内存态。
            accs = env_accounts()
            try:
                import stats as statsmod
                data = statsmod.build(7)
                days = data.get("days") or []
                today = days[-1].get("accounts", {}) if days else {}
                per = {}
                for d in days:
                    for name, v in (d.get("accounts") or {}).items():
                        k = str(name).split("@")[0]
                        e = per.setdefault(k, {"d7": 0, "balance": None})
                        e["d7"] += int(v.get("total") or 0)
                        if v.get("balance") is not None:
                            e["balance"] = v["balance"]
                today_norm = {str(k).split("@")[0]: v for k, v in (today or {}).items()}
                rh = run_history_today()
                for a in accs:
                    key = str(a.get("email") or "").split("@")[0]
                    info = per.get(key) or {}
                    a["balance"] = info.get("balance")
                    a["todayPoints"] = int((today_norm.get(key) or {}).get("total") or 0)
                    a["points7d"] = info.get("d7", 0)
                    # run-history.json 是权威汇总：容器重建/日志被冲后依然准确，优先覆盖
                    h = rh.get(key) or {}
                    if h.get("balance") is not None:
                        a["balance"] = h["balance"]
                    if h.get("today") is not None:
                        a["todayPoints"] = max(int(a.get("todayPoints") or 0), int(h["today"]))
                    if h.get("status"):
                        a["lastStatus"] = h["status"]
                    if h.get("lastRunAt"):
                        a["lastRunAt"] = h["lastRunAt"]
            except Exception as e:
                log("[panel] 账号统计补全失败", e)
            return self.send_json(200, {"accounts": accs, "state": run_state()})

        if p == "/panel/stats":
            import stats as statsmod
            data = statsmod.refresh(14)
            try:
                n = int((parse_qs(u.query).get("days") or ["7"])[0])
            except Exception:
                n = 7
            n = max(1, min(14, n))
            return self.send_json(200, {
                "generatedAt": data["generatedAt"],
                "days": data["days"][-n:],
                "categories": data["categories"],
                "accounts": data["accounts"],
            })

        if p.startswith("/api/"):
            target = p[4:] or "/"
            if proxy_blocked(target):
                return self.send_json(403, {"error": "面板不代理 /config（含账号密码）"})
            qs = ("?" + u.query) if u.query else ""
            code, body = api_call("GET", target + qs, timeout=30)
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        return self.send_json(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        p = u.path
        body = self.read_body()

        if p == "/login":
            ip = self.client_address[0]
            n, until = _login_state(ip)
            if until and time.time() < until:
                return self.send_json(429, {"ok": False, "error": f"尝试过多，请 {int((until - time.time()) / 60) + 1} 分钟后再试"})
            try:
                data = json.loads(body or b"{}")
            except Exception:
                data = {}
            if hmac.compare_digest(str(data.get("password", "")), PASSWORD):
                _login_ok(ip)
                self.send_response(200)
                self.send_header("Set-Cookie", make_cookie())
                payload = b'{"ok":true}'
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            else:
                fails, lock_until = _login_fail(ip)
                if lock_until and time.time() < lock_until:
                    log(f"[login] {ip} 连续失败 {fails} 次，锁定 {LOGIN_LOCK_SEC}s")
                time.sleep(0.6)
                self.send_json(401, {"ok": False, "error": "密码错误"})
            return

        if p == "/logout":
            self.send_response(200)
            self.send_header("Set-Cookie", f"{COOKIE_NAME}=; Path=/; Max-Age=0")
            payload = b'{"ok":true}'
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if not self.authed():
            return self.send_json(401, {"error": "unauthorized"})

        if p == "/panel/self-update":
            ok, msg = start_self_update()
            return self.send_json(200 if ok else 409, {"ok": ok, "message": msg})

        if p == "/panel/self-restart":
            ok, msg = start_self_restart()
            return self.send_json(200, {"ok": ok, "message": msg})

        if p == "/panel/update":
            ok, msg = start_update()
            return self.send_json(200 if ok else 409, {"ok": ok, "message": msg, "status": update_status()})

        if p == "/panel/update/check":
            # 只检查：拉一下官方镜像，比对 digest 是否比本地派生镜像新
            rc, out = sh(f"docker pull -q {BASE_IMAGE}", timeout=300)
            if rc != 0:
                return self.send_json(502, {"ok": False, "error": "拉取官方镜像失败（网络？）", "detail": out.strip()[-300:]})
            cur = _img_digest(DERIVED_IMAGE)
            new = _img_digest(BASE_IMAGE)
            base_created = _img_created(BASE_IMAGE)
            return self.send_json(200, {
                "ok": True,
                "baseDigest": new[:19], "derivedDigest": cur[:19],
                "baseCreated": base_created,
                "note": "派生镜像是本地重建的，digest 与官方不同，仅作参考；点「立即更新」会重新打补丁+瘦身并重建容器",
            })

        if p == "/panel/notify/test":
            import notify as notifymod
            try:
                payload = json.loads(body or b"{}")
            except Exception:
                return self.send_json(400, {"error": "bad json"})
            cid = payload.get("id")
            results = notifymod.broadcast("Rewards 测试消息", "这是一条来自控制台的测试推送。\n如果收到说明渠道配置可用。",
                                          only=[cid] if cid else None)
            if not results:
                return self.send_json(400, {"error": "没有启用的渠道"})
            return self.send_json(200, {"results": results})

        if p == "/panel/accounts":
            try:
                payload = json.loads(body or b"{}")
            except Exception:
                return self.send_json(400, {"error": "bad json"})
            if run_state() == "running":
                return self.send_json(409, {"error": "任务正在运行，先停止再加账号"})
            res = add_account(payload)
            if res.get("error"):
                return self.send_json(400, res)
            res["rebuild"] = run_rebuild()
            return self.send_json(200, res)

        if p.startswith("/api/"):
            target = p[4:] or "/"
            if proxy_blocked(target):
                return self.send_json(403, {"error": "面板不代理 /config（含账号密码）"})
            try:
                payload = json.loads(body) if body else {}
            except Exception:
                payload = {}
            code, resp = api_call("POST", target, payload, timeout=120)
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            return

        return self.send_json(404, {"error": "not found"})

    def do_PUT(self):
        self._write("PUT")

    def do_PATCH(self):
        self._write("PATCH")

    def do_DELETE(self):
        self._write("DELETE")

    def _write(self, method):
        u = urlparse(self.path)
        p = u.path
        body = self.read_body()

        if not self.authed():
            return self.send_json(401, {"error": "unauthorized"})

        if p == "/panel/schedule" and method == "PUT":
            try:
                data = json.loads(body or b"{}")
            except Exception:
                return self.send_json(400, {"error": "bad json"})
            cron = str(data.get("cron", "")).strip()
            if cron and len(cron.split()) != 5:
                return self.send_json(400, {"error": "cron 需要 5 段，例如 0 7 * * *"})
            save_json(SCHED, {"enabled": bool(data.get("enabled")), "cron": cron or "0 7 * * *"})
            return self.send_json(200, {"ok": True})

        if p == "/panel/notify" and method == "PUT":
            import notify as notifymod
            try:
                data = json.loads(body or b"{}")
            except Exception:
                return self.send_json(400, {"error": "bad json"})
            old = notifymod.load()
            old_by_id = {c.get("id"): c for c in old.get("channels", [])}
            channels = []
            for ch in (data.get("channels") or []):
                t = ch.get("type")
                if t not in notifymod.TYPES:
                    return self.send_json(400, {"error": f"未知渠道类型 {t}"})
                conf = ch.get("config") or {}
                # ****** 表示沿用旧值
                prev_conf = (old_by_id.get(ch.get("id")) or {}).get("config") or {}
                for k, v in list(conf.items()):
                    if v == "******":
                        conf[k] = prev_conf.get(k, "")
                for f in notifymod.TYPES[t]["fields"]:
                    if f[2] and not str(conf.get(f[0], "")).strip():
                        return self.send_json(400, {"error": f"{notifymod.TYPES[t]['label']} 缺少 {f[1]}"})
                channels.append({"id": ch.get("id") or str(int(time.time() * 1000)),
                                 "type": t, "name": ch.get("name") or notifymod.TYPES[t]["label"],
                                 "enabled": bool(ch.get("enabled", True)), "config": conf})
            notifymod.save({"events": data.get("events") or old.get("events"), "channels": channels})
            return self.send_json(200, {"ok": True, "count": len(channels)})

        if p == "/panel/accounts" and method == "DELETE":
            qs = parse_qs(u.query)
            try:
                idx = int((qs.get("index") or ["0"])[0])
            except Exception:
                return self.send_json(400, {"error": "index 参数错误"})
            if run_state() == "running":
                return self.send_json(409, {"error": "任务正在运行，先停止再删账号"})
            res = remove_account(idx)
            if res.get("error"):
                return self.send_json(400, res)
            res["rebuild"] = run_rebuild()
            return self.send_json(200, res)

        if method == "DELETE" and p.startswith("/api/sessions/"):
            # v5 的会话删除是「按账号整删」（桌面+移动一起），没有按平台的删除接口；
            # 前端仍可能带 ?platform=xxx，这里丢掉该参数并统一走整号删除。
            email = unquote(p[len("/api/sessions/"):]).strip()
            if not email:
                return self.send_json(400, {"error": "缺少邮箱"})
            code, resp = api_call("DELETE", "/sessions/" + quote(email, safe=""), None, timeout=30)
            try:
                data = json.loads(resp) if resp else {}
            except Exception:
                data = {"raw": resp.decode("utf-8", "replace") if isinstance(resp, bytes) else str(resp)}
            if code < 400 and isinstance(data, dict):
                data["note"] = "v5 按账号整删：该号的桌面与移动会话都已清除"
            out = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)
            return

        if p.startswith("/api/"):
            target = p[4:] + (("?" + u.query) if u.query else "")
            if proxy_blocked(target):
                return self.send_json(403, {"error": "面板不代理 /config（含账号密码）"})
            payload = None
            if body:
                try:
                    payload = json.loads(body)
                except Exception:
                    payload = {}
            code, resp = api_call(method, target, payload, timeout=120)
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            return

        return self.send_json(404, {"error": "not found"})


def _rotate_runlog(max_bytes=20 * 1024 * 1024, keep_lines=50000):
    """runlog.jsonl 无上限增长会拖慢统计解析，超阈值时只保留最近 keep_lines 行。"""
    try:
        if not os.path.exists(RUNLOG) or os.path.getsize(RUNLOG) < max_bytes:
            return
        with open(RUNLOG, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        with open(RUNLOG, "w", encoding="utf-8") as f:
            f.writelines(lines[-keep_lines:])
        log(f"[collector] runlog 已裁剪：{len(lines)} → {min(len(lines), keep_lines)} 行")
    except Exception as e:
        log("[collector] runlog 裁剪失败", e)


def main():
    _rotate_runlog()
    if not os.path.exists(SCHED):
        save_json(SCHED, {"enabled": True, "cron": "0 7 * * *"})
    threading.Thread(target=scheduler_loop, daemon=True).start()
    threading.Thread(target=collector_loop, daemon=True).start()
    threading.Thread(target=notify_loop, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    srv.daemon_threads = True
    srv.timeout = 30          # 慢连接（slowloris）超时断开
    log(f"面板已启动 http://0.0.0.0:{PORT}  → {API_BASE}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
