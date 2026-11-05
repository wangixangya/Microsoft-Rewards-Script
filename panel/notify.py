#!/usr/bin/env python3
"""推送渠道 —— 只用标准库，支持 Telegram / 企业微信 / 钉钉 / Bark / Server酱 / PushPlus / Gotify / ntfy / SMTP / 通用 Webhook。

配置存同目录 notify.json：
{
  "events": {"on_finish": true, "on_error": true, "daily_summary": false, "daily_time": "10:00"},
  "channels": [
    {"id": "tg1", "type": "telegram", "name": "我的 TG", "enabled": true,
     "config": {"bot_token": "...", "chat_id": "..."}}
  ]
}
"""
import json
import os
import smtplib
import ssl
import time
import urllib.parse
import urllib.request
from email.mime.text import MIMEText
from email.header import Header

BASE = os.path.dirname(os.path.abspath(__file__))
CONF_PATH = os.path.join(BASE, "notify.json")

# 每种渠道的元数据 + 字段定义（key, 标签, 是否必填, 默认值, 是否密码）
TYPES = {
    "telegram": {
        "label": "Telegram",
        "hint": "找 @BotFather 建 bot 拿 token，chat_id 可用 @userinfobot 查",
        "fields": [
            ("bot_token", "Bot Token", True, "", True),
            ("chat_id", "Chat ID", True, "", False),
            ("api_base", "API 地址", False, "https://api.telegram.org", False),
        ],
    },
    "wecom": {
        "label": "企业微信群机器人",
        "hint": "群设置 → 群机器人 → 添加，复制 Webhook 地址",
        "fields": [("url", "Webhook 地址", True, "", True)],
    },
    "dingtalk": {
        "label": "钉钉群机器人",
        "hint": "群设置 → 智能群助手 → 自定义机器人，复制 Webhook",
        "fields": [
            ("url", "Webhook 地址", True, "", True),
            ("secret", "加签密钥（可选）", False, "", True),
        ],
    },
    "bark": {
        "label": "Bark（iOS）",
        "hint": "App 首页给出的完整地址里的 key，官方服务器可留空",
        "fields": [
            ("key", "Device Key", True, "", True),
            ("server", "服务器", False, "https://api.day.app", False),
            ("group", "分组（可选）", False, "Rewards", False),
        ],
    },
    "serverchan": {
        "label": "Server酱",
        "hint": "sct.ftqq.com 微信扫码登录后拿 SendKey",
        "fields": [("sendkey", "SendKey", True, "", True)],
    },
    "pushplus": {
        "label": "PushPlus（微信）",
        "hint": "pushplus.plus 微信登录后复制 token",
        "fields": [("token", "Token", True, "", True)],
    },
    "gotify": {
        "label": "Gotify（自建）",
        "hint": "Gotify 服务地址 + 应用 token",
        "fields": [
            ("url", "服务地址", True, "http://127.0.0.1:8080", False),
            ("token", "App Token", True, "", True),
            ("priority", "优先级", False, "5", False),
        ],
    },
    "ntfy": {
        "label": "ntfy",
        "hint": "手机装 ntfy 订阅同名 topic；自建就把服务器地址改掉",
        "fields": [
            ("topic", "Topic", True, "", False),
            ("server", "服务器", False, "https://ntfy.sh", False),
            ("token", "访问令牌（可选）", False, "", True),
        ],
    },
    "smtp": {
        "label": "邮件 SMTP",
        "hint": "QQ 邮箱用 smtp.qq.com:465 + 授权码（不是登录密码）",
        "fields": [
            ("host", "SMTP 服务器", True, "", False),
            ("port", "端口", True, "465", False),
            ("user", "账号", True, "", False),
            ("password", "口令/授权码", True, "", True),
            ("to", "收件人（逗号分隔）", True, "", False),
            ("ssl", "SSL", False, "true", False),
        ],
    },
    "webhook": {
        "label": "通用 Webhook",
        "hint": "POST JSON：{title, text, ts}，可接自建服务或中转",
        "fields": [
            ("url", "地址", True, "", True),
            ("header", "额外请求头（可选，Key: Value）", False, "", True),
        ],
    },
}

DEFAULT = {"events": {"on_finish": True, "on_error": True, "daily_summary": False, "daily_time": "10:00"},
           "channels": []}


def load():
    try:
        with open(CONF_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("events", dict(DEFAULT["events"]))
        data.setdefault("channels", [])
        return data
    except Exception:
        return json.loads(json.dumps(DEFAULT))


def save(data):
    tmp = CONF_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONF_PATH)
    try:
        os.chmod(CONF_PATH, 0o600)
    except Exception:
        pass


def _req(url, data=None, headers=None, method=None, timeout=15):
    h = {"User-Agent": "ms-rewards-panel/1.0"}
    if headers:
        h.update(headers)
    body = None
    if data is not None:
        if isinstance(data, (dict, list)):
            body = json.dumps(data, ensure_ascii=False).encode()
            h.setdefault("Content-Type", "application/json")
        elif isinstance(data, str):
            body = data.encode()
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return True, f"{r.status} {r.read()[:300].decode('utf-8', 'ignore')}"
    except Exception as e:
        return False, str(e)[:300]


def send(channel, title, text, timeout=15):
    """发送一条消息。返回 (ok, detail)。"""
    t = channel.get("type")
    c = channel.get("config") or {}
    try:
        if t == "telegram":
            base = (c.get("api_base") or "https://api.telegram.org").rstrip("/")
            ok, d = _req(f"{base}/bot{c['bot_token']}/sendMessage",
                         {"chat_id": c["chat_id"], "text": f"<b>{title}</b>\n\n{text}",
                          "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=timeout)
            return ok, d
        if t == "wecom":
            return _req(c["url"], {"msgtype": "markdown",
                                   "markdown": {"content": f"**{title}**\n\n{text}"}}, timeout=timeout)
        if t == "dingtalk":
            url = c["url"]
            if c.get("secret"):
                import base64
                import hashlib
                import hmac
                ts = str(round(time.time() * 1000))
                sign = urllib.parse.quote_plus(base64.b64encode(hmac.new(
                    c["secret"].encode(), f"{ts}\n{c['secret']}".encode(), hashlib.sha256).digest()))
                url += f"&timestamp={ts}&sign={sign}"
            return _req(url, {"msgtype": "markdown", "markdown": {"title": title, "text": f"### {title}\n\n{text}"}},
                        timeout=timeout)
        if t == "bark":
            server = (c.get("server") or "https://api.day.app").rstrip("/")
            q = urllib.parse.urlencode({"group": c.get("group") or "Rewards", "isArchive": 1})
            return _req(f"{server}/{c['key']}/{urllib.parse.quote(title)}/{urllib.parse.quote(text)}?{q}",
                        timeout=timeout)
        if t == "serverchan":
            return _req(f"https://sctapi.ftqq.com/{c['sendkey']}.send",
                        {"title": title, "desp": text.replace("\n", "\n\n")}, timeout=timeout)
        if t == "pushplus":
            return _req("https://www.pushplus.plus/send",
                        {"token": c["token"], "title": title, "content": text.replace("\n", "<br>"),
                         "template": "html"}, timeout=timeout)
        if t == "gotify":
            url = (c.get("url") or "").rstrip("/")
            return _req(f"{url}/message?token={urllib.parse.quote(c['token'])}",
                        {"title": title, "message": text, "priority": int(c.get("priority") or 5)},
                        timeout=timeout)
        if t == "ntfy":
            server = (c.get("server") or "https://ntfy.sh").rstrip("/")
            h = {"Title": title.encode("utf-8").decode("latin-1", "ignore") or "Rewards", "Tags": "chart_with_upwards_trend"}
            if c.get("token"):
                h["Authorization"] = f"Bearer {c['token']}"
            return _req(f"{server}/{urllib.parse.quote(c['topic'])}", text, headers=h, timeout=timeout)
        if t == "smtp":
            port = int(c.get("port") or 465)
            msg = MIMEText(text, "plain", "utf-8")
            msg["Subject"] = Header(title, "utf-8")
            msg["From"] = c["user"]
            msg["To"] = c["to"]
            if str(c.get("ssl", "true")).lower() in ("1", "true", "yes", "on"):
                ctx = ssl.create_default_context()
                srv = smtplib.SMTP_SSL(c["host"], port, timeout=timeout, context=ctx)
            else:
                srv = smtplib.SMTP(c["host"], port, timeout=timeout)
                srv.starttls(context=ssl.create_default_context())
            try:
                srv.login(c["user"], c["password"])
                srv.sendmail(c["user"], [x.strip() for x in str(c["to"]).split(",") if x.strip()], msg.as_string())
                return True, "smtp ok"
            finally:
                try:
                    srv.quit()
                except Exception:
                    pass
        if t == "webhook":
            headers = {}
            raw = c.get("header") or ""
            if raw and ":" in raw:
                k, v = raw.split(":", 1)
                headers[k.strip()] = v.strip()
            return _req(c["url"], {"title": title, "text": text, "ts": int(time.time())},
                        headers=headers, timeout=timeout)
        return False, f"未知渠道类型: {t}"
    except KeyError as e:
        return False, f"缺少字段: {e}"
    except Exception as e:
        return False, str(e)[:300]


def broadcast(title, text, only=None):
    """发给所有启用的渠道，返回 [{name,type,ok,detail}]"""
    cfg = load()
    out = []
    for ch in cfg.get("channels", []):
        if not ch.get("enabled", True):
            continue
        if only and ch.get("id") not in only:
            continue
        ok, detail = send(ch, title, text)
        out.append({"id": ch.get("id"), "name": ch.get("name") or ch.get("type"),
                    "type": ch.get("type"), "ok": ok, "detail": detail})
    return out
