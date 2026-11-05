#!/usr/bin/env python3
"""Microsoft Rewards 控制面板 —— 静态 UI + API 反向代理 + 计划任务
只用标准库，无第三方依赖。监听 0.0.0.0:5310。
"""
import base64
import hashlib
import hmac
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

BASE = os.path.dirname(os.path.abspath(__file__))
CONF = os.path.join(BASE, "panel.conf")
SCHED = os.path.join(BASE, "schedule.json")
STATE = os.path.join(BASE, "state.json")
PORT = int(os.environ.get("PANEL_PORT", "5310"))


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


CONF_D = load_kv(CONF)
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
    """极简 cron：支持 * 数字 列表 范围 /步长。"""
    parts = expr.split()
    if len(parts) != 5:
        return False
    values = [tm.tm_min, tm.tm_hour, tm.tm_mday, tm.tm_mon, (tm.tm_wday + 1) % 7]
    for part, (lo, hi), val in zip(parts, CRON_FIELDS, values):
        if part == "*":
            continue
        ok = False
        for token in part.split(","):
            step = 1
            if "/" in token:
                token, s = token.split("/", 1)
                step = int(s or 1)
            if token == "*":
                rng = range(lo, hi + 1)
            elif "-" in token:
                a, b = token.split("-", 1)
                rng = range(int(a), int(b) + 1)
            else:
                start = int(token)
                rng = range(start, hi + 1) if step > 1 else [start]
            if val in rng and (val - rng.start) % step == 0:
                ok = True
                break
        if not ok:
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


def scheduler_loop():
    last_fire = ""
    while True:
        try:
            cfg = load_json(SCHED, {"enabled": False, "cron": "0 7 * * *"})
            if cfg.get("enabled") and cfg.get("cron"):
                tm = time.localtime()
                stamp = time.strftime("%Y%m%d%H%M", tm)
                if cron_match(cfg["cron"], tm) and last_fire != stamp:
                    st, _ = api_call("GET", "/status", timeout=15)
                    running = False
                    if st == 200:
                        code, body = api_call("GET", "/status", timeout=15)
                        try:
                            running = json.loads(body).get("state") == "running"
                        except Exception:
                            running = False
                    if running:
                        log("[sched] 已在运行，跳过本次触发")
                    else:
                        api_call("POST", "/start", {}, timeout=30)
                        log("[sched] 触发运行", cfg["cron"])
                    last_fire = stamp
        except Exception as e:
            log("[sched] 异常", e)
        time.sleep(20)


# ---------- 日志采集 → 统计 ----------
RUNLOG = os.path.join(BASE, "runlog.jsonl")
_SEEN_PATH = os.path.join(BASE, "runlog.seen")


def _load_seen():
    try:
        with open(_SEEN_PATH, "r", encoding="utf-8") as f:
            return int(f.read().strip() or 0)
    except Exception:
        return 0


def _save_seen(v):
    try:
        with open(_SEEN_PATH, "w", encoding="utf-8") as f:
            f.write(str(v))
    except Exception:
        pass


def collector_loop():
    """把控制 API 的日志落盘（API 日志是内存态，容器重启就丢），并刷新统计。"""
    import stats as statsmod
    last_id = _load_seen()
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
                new_lines = []
                for e in entries:
                    if not isinstance(e, dict):
                        continue
                    eid = e.get("id") or 0
                    if eid <= last_id:
                        continue
                    raw = e.get("raw") or e.get("message")
                    if raw:
                        new_lines.append({"id": eid, "t": e.get("receivedAt") or e.get("ts"), "raw": raw})
                    if eid > last_id:
                        last_id = eid
                if new_lines:
                    with open(RUNLOG, "a", encoding="utf-8") as f:
                        for item in new_lines:
                            f.write(json.dumps(item, ensure_ascii=False) + "\n")
                    _save_seen(last_id)
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
                        notifymod.broadcast(t, f"退出码 {code_exit}\n{text}")
                        log("[notify] 已推送异常")
                elif ev.get("on_finish", True):
                    notifymod.broadcast(f"Rewards 运行完成 +{score} 分", text)
                    log("[notify] 已推送完成")
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
        path = os.path.join(BASE, rel.lstrip("/"))
        if not os.path.isfile(path):
            self.send_json(404, {"error": "not found"})
            return
        ext = os.path.splitext(path)[1].lower()
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
        n = int(self.headers.get("Content-Length") or 0)
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
            return self.send_json(200, {"accounts": env_accounts(), "state": run_state()})

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
            try:
                data = json.loads(body or b"{}")
            except Exception:
                data = {}
            if hmac.compare_digest(str(data.get("password", "")), PASSWORD):
                self.send_response(200)
                self.send_header("Set-Cookie", make_cookie())
                payload = b'{"ok":true}'
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            else:
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

        if p.startswith("/api/"):
            target = p[4:] + (("?" + u.query) if u.query else "")
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


def main():
    if not os.path.exists(SCHED):
        save_json(SCHED, {"enabled": True, "cron": "0 7 * * *"})
    threading.Thread(target=scheduler_loop, daemon=True).start()
    threading.Thread(target=collector_loop, daemon=True).start()
    threading.Thread(target=notify_loop, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    log(f"面板已启动 http://0.0.0.0:{PORT}  → {API_BASE}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
