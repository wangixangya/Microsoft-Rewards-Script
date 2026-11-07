<div align="center">

# Microsoft&nbsp;Rewards · 中文增强版
### Microsoft Rewards Script · Chinese Enhanced Edition

**把每天的积分任务交给机器，把时间留给自己。**
*Let the machine handle the daily grind. Keep your time for yourself.*

[![版本](https://img.shields.io/badge/版本-2.4.1-000000?style=flat-square)](panel)
[![引擎](https://img.shields.io/badge/引擎-v5.0.0-000000?style=flat-square)](https://github.com/TheNetsky/Microsoft-Rewards-Script/tree/v4)
[![镜像](https://img.shields.io/badge/镜像-ms--rewards%3Av5--cn-000000?style=flat-square)](Dockerfile)
[![面板](https://img.shields.io/badge/面板-中文%20%2F%20English-000000?style=flat-square)](panel)
[![许可](https://img.shields.io/badge/许可-GPL--3.0-000000?style=flat-square)](LICENSE)

</div>

> **中文** — 本仓库是 [TheNetsky/Microsoft-Rewards-Script](https://github.com/TheNetsky/Microsoft-Rewards-Script) v5 的中文增强分支。引擎原封不动，我们只做三件上游没做的事：让它在国内网络下真正跑得通、给它一副好看好用的控制台、把它塞进一个更小的镜像里。
>
> **English** — A Chinese-enhanced branch of upstream v5. The engine is untouched; we only did the three things upstream doesn't: make it actually work behind a mainland-China network, give it a control panel you'd want to open, and fit it into a smaller image.

---

## 它解决什么 / What it solves

|  | 中文 | English |
|---|---|---|
| 🧭 **能跑通** | 国内 IP 访问 Bing 会被 302 跳转，上游写死的 `www.bing.com` 判断永远匹配不上，桌面搜索直接 45 秒超时放弃。本分支在 `dist` 层做了 host 判定补丁，**不碰 API 请求逻辑**，随上游更新可重新打补丁。 | Bing redirects CN traffic to `cn.bing.com`, which never matches upstream's hard-coded origin check — desktop search times out and gives up. This branch patches the host comparison only, leaving request logic untouched. |
| 🖥 **看得见** | 自带中文 Web 控制台：总览、账号会话、运行日志、任务开关、奖励中心、设置，手机浏览器就能管。 | A bilingual web console: dashboard, accounts & sessions, live logs, task switches, rewards center, settings — manageable from a phone. |
| 🪶 **更轻** | 只保留 headless 浏览器与运行期依赖，图片从 1.34 GB 压到 **763 MB**，空载内存 **34 MiB**，单账号运行峰值约 **825 MiB**（实测）。 | Only the headless browser and runtime deps survive. Image: 1.34 GB → **763 MB**. Idle memory **34 MiB**; one account peaks at **825 MiB** (measured). |

---

## 能力 / Capabilities

```
每日任务   Daily set · More promotions · Punch cards · Bonus points
搜索积分   Desktop & mobile search · Random scroll & click · Local queries
连胜守护   Streak protection · Daily check-in · Read to earn · Search perk
奖励中心   Points / streak / claimable snapshot · Auto claim · Cron
批量运行   Native clusters (1–4) · Per-account cron · Manual single run
网络出口    Long-lived SOCKS5 / HTTP proxy, bound per account
运维面板    Logs · Task switches · Image update · Panel self-update · Push channels
```

| 功能 | Feature |
|---|---|
| **并发执行** — v5 原生 `CONFIG_CLUSTERS`，1–4 个 worker 各带一个浏览器，账号真正并行，面板里手填数字即生效 | **Concurrency** — native `CONFIG_CLUSTERS`, 1–4 workers each with its own browser; set the number in the panel and it takes effect |
| **账号独立定时** — 每个账号一条 cron，互不干扰 | **Per-account schedules** — one cron per account, no interference |
| **代理绑定** — 长效 SOCKS5 / HTTP 按账号绑定，切换即重建容器 | **Proxy binding** — long-lived SOCKS5/HTTP per account, applied by container rebuild |
| **奖励中心** — 读积分、连胜、可领取额度，一键领取，可挂定时 | **Rewards center** — points, streak, claimable; one-click claim or scheduled |
| **任务开关** — 12 个 workers 开关 + 搜索行为 + 原始 JSON，改动自动备份 `config.json.bak` | **Task switches** — 12 worker toggles, search behaviour, raw JSON; auto-backup on save |
| **远程更新** — 面板里检查并重建镜像，面板自身也能在线更新自重启 | **Remote updates** — check & rebuild the image from the panel; the panel can update itself |

---

## 青龙 / QingLong（单文件）

`qinglong/ms-rewards.js` 是**一个文件**的青龙运行器：丢进 `scripts` 目录，定时任务填 `ms-rewards.js` 即可。

- **在线更新**：每次运行按 `MSR_CHECK_HOURS`（默认 12h）拉上游源码比对哈希，变了就自动重装依赖 + 重建，会话与配置保留
- **自动装浏览器**：优先用系统 chromium（Alpine 青龙自带 `/usr/bin/chromium`，省 ~270 MB）；没有才下载 patchright 版
- **账号走环境变量**：`ACCOUNT_1_EMAIL` / `ACCOUNT_1_PASSWORD` / `ACCOUNT_1_TOTP_SECRET`，密码不落盘
- **自检**：`MSR_SELFTEST=1 node ms-rewards.js` 只验证依赖 + 浏览器 + 访问必应，不跑任务

```bash
# 青龙脚本目录里
node ms-rewards.js                 # 正常跑
MSR_SELFTEST=1 node ms-rewards.js  # 环境自检
MSR_CLUSTERS=2 MSR_AUTO_UPDATE=0 node ms-rewards.js
```

| 变量 | 默认 | 说明 |
|---|---|---|
| `MSR_HOME` | `/ql/data/msr` | 工作区（源码 / 会话 / 配置 / 浏览器） |
| `MSR_AUTO_UPDATE` | `1` | 是否在线同步上游 |
| `MSR_CHECK_HOURS` | `12` | 检查间隔 |
| `MSR_CLUSTERS` | `1` | 并发账号数 1–4 |
| `MSR_CHROMIUM_PATH` | 自动 | 指定浏览器可执行文件 |

---

## 快速开始 / Quick start

```bash
# 1 · 准备账号（每行一个：邮箱;密码[;TOTP密钥]）
echo "you@example.com;your-password" > accounts.txt

# 2 · 起容器
docker run -d --name ms-rewards \
  -p 3010:3000 \
  --env-file <(sed 's/^/ACCOUNT_/;=' accounts.txt) \
  -v "$PWD/config:/usr/src/microsoft-rewards-script/config" \
  -v "$PWD/sessions:/usr/src/microsoft-rewards-script/sessions" \
  ms-rewards:v5-cn
```

```bash
# 3 · 带上控制台（可选，推荐）
bash panel/install.sh      # 默认 0.0.0.0:5310，密码见 panel/panel.conf
```

> 手动登录一次后，`sessions/` 里会存下 storage_state，之后每天自动续跑。
> *Log in once manually; `sessions/` keeps the storage state and every later run reuses it.*

---

## 控制台 / The console

```
总览          Dashboard       状态 · 今日积分 · 上次运行 · 一键运行
账号与会话     Accounts        cookie 数量与更新时间 · 添加/删除 · 单账号运行
运行日志       Logs            实时日志 · 关键字过滤
任务配置       Tasks           12 个任务开关 · 搜索行为 · 原始 config.json
奖励中心       Rewards         积分/连胜/可领取 · 一键领取 · 定时领取
设置           Settings        运行计划 · 并发数 · 推送渠道 · 代理管理 · 镜像与版本
```

设计取向：白底黑字、单一强调色、移动端优先——运维面板不需要花哨，需要一眼看清哪里坏了。
*Design: white on black, one accent, mobile-first. An ops panel should tell you at a glance what's broken — not decorate.*

---

## 工作原理 / How it works

```
           ┌──────────────────────────────┐
           │  ms-rewards:v5-cn  (镜像)      │
           │  upstream v5  + dist 补丁      │
           │  headless chromium  ·  node   │
           └──────────────┬───────────────┘
                          │ HTTP 3010
           ┌──────────────┴───────────────┐
           │  panel  (5310)  ·  Python     │
           │  读写 config.json / env.list   │
           │  调度 · 代理 · 奖励 · 自更新    │
           └──────────────────────────────┘
```

- 面板与引擎解耦：面板只通过 API 与 `config.json` 操作容器，容器重启不会丢配置。
- `CONFIG_CLUSTERS` 决定并发；每个 worker 独立浏览器、独立账号分片。
- 镜像构建链：`docker build`（补丁 + 删无用体积）→ `docker export | docker import` 拍扁单层 → 打 tag。删除只有在拍扁后才真正减小体积。

---

## 免责声明 / Disclaimer

本项目仅供个人学习与自动化实践。请遵守 [Microsoft 服务协议](https://www.microsoft.com/servicesagreement) 与 Rewards 使用准则，**不要**多账号刷分、不要用于商业用途。账号风险由使用者自负。

*For personal learning and automation practice only. Respect Microsoft's Terms of Service and the Rewards guidelines. No multi-account farming, no commercial use. You own the risk.*

---

<div align="center">

**上游 / Upstream →** [TheNetsky/Microsoft-Rewards-Script](https://github.com/TheNetsky/Microsoft-Rewards-Script) · GPL-3.0

*Made with patience, insomnia, and an N100.*

</div>

---

## 上游文档 / Upstream documentation

<details>
<summary><b>展开查看完整上游说明（English, 原文保留）/ Expand for the full upstream README</b></summary>

