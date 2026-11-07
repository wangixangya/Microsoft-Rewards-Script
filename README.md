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

`panel/ql/ms-rewards.js` 是**一个文件**的青龙运行器：丢进 `scripts` 目录，定时任务填 `ms-rewards.js` 即可。

- **运行器自更新**：每次检查时从本仓库 `panel/ql/ms-rewards.js` 取最新版，变了自动替换（旧版存 `.bak`，下次运行生效）
- **上游同步**：按 `MSR_CHECK_HOURS`（默认 12h）拉上游源码比对哈希，变了自动重装依赖 + 重建，会话与配置保留
- **不下载浏览器**：优先用系统 chromium（Alpine 青龙自带 `/usr/bin/chromium`，省 ~270 MB）；没有才下 patchright 版
- **账号走环境变量**：`ACCOUNT_1_EMAIL` / `ACCOUNT_1_PASSWORD` / `ACCOUNT_1_TOTP_SECRET`，密码不落盘
- **自检**：`MSR_SELFTEST=1 node ms-rewards.js` 只验证依赖 + 浏览器 + 访问必应，不跑任务

### 拉取到青龙面板（三种方式）

**① 面板上传（最省事）** — 左下「脚本管理」→ 新建文件夹 `msr` → 上传 `ms-rewards.js` → 保存。

**② 面板里一条命令拉（推荐，可重复执行自动覆盖）**

「定时任务」→ 新建任务 → 命令里先执行一次：

```bash
mkdir -p /ql/data/scripts && cd /ql/data/scripts && \
curl -sL https://codeload.github.com/wangixangya/Microsoft-Rewards-Script/tar.gz/refs/heads/v4 -o /tmp/msr.tgz && \
rm -rf /tmp/msrpull && mkdir -p /tmp/msrpull && tar -xzf /tmp/msr.tgz -C /tmp/msrpull && \
cp /tmp/msrpull/Microsoft-Rewards-Script-*/panel/ql/ms-rewards.js ./ms-rewards.js && \
rm -rf /tmp/msr.tgz /tmp/msrpull && ls -lh ./ms-rewards.js
```

（青龙是 Alpine，`tar` 是 busybox 版，不支持 `--wildcards`，所以先整包解开再 `cp`。）

拉完之后，运行器自己会每 12h 回本仓库取新版，不需要再手动拉。

**③ 订阅管理（ql repo）** — 仅当你想整仓拉取时用：

```bash
ql repo https://github.com/wangixangya/Microsoft-Rewards-Script.git "panel/ql" "" "" "v4"
```

> 注意：`ql repo` 走 `github.com`，国内常被墙；不通就用方式 ②，走 `codeload.github.com`。

### 定时任务怎么填

| 项 | 值 |
|---|---|
| 名称 | 微软 Rewards |
| 命令 | `task msr/ms-rewards.js`（放 `msr` 文件夹时）或 `node /ql/data/scripts/ms-rewards.js` |
| 定时规则 | `0 7 * * *`（每天 7 点；青龙用 6 段式就填 `0 0 7 * * *`） |
| 环境变量 | `ACCOUNT_1_EMAIL`、`ACCOUNT_1_PASSWORD`，多账号依次 `ACCOUNT_2_*` |

```bash
# 手动跑 / 自检
node /ql/data/scripts/ms-rewards.js
MSR_SELFTEST=1 node /ql/data/scripts/ms-rewards.js
MSR_CLUSTERS=2 node /ql/data/scripts/ms-rewards.js
```

| 变量 | 默认 | 说明 |
|---|---|---|
| `MSR_HOME` | `/ql/data/msr` | 工作区（源码 / 会话 / 配置 / 浏览器） |
| `MSR_AUTO_UPDATE` | `1` | 是否在线同步上游 |
| `MSR_SELF_UPDATE` | `1` | 是否在线更新运行器本身 |
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

[![Discord](https://img.shields.io/badge/Join%20Our%20Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/8BxYbV4pkj)
[![Latest Build](https://img.shields.io/github/actions/workflow/status/TheNetsky/Microsoft-Rewards-Script/auto-release.yml?branch=v4&style=for-the-badge&label=Latest%20Build)](https://github.com/TheNetsky/Microsoft-Rewards-Script/actions/workflows/auto-release.yml)
[![Docker](https://img.shields.io/badge/Docker-GHCR-blue?style=for-the-badge&logo=docker)](https://github.com/TheNetsky/Microsoft-Rewards-Script/pkgs/container/microsoft-rewards-script)

> [!NOTE]
> **语言 / Language:** English (current) | [简体中文](README.zh-CN.md)

> [!TIP]
> This version supports the **new, modern Bing Rewards dashboard only** - it does **not** support the legacy dashboard.
> If your account still uses the old dashboard, use the [v3 branch](https://github.com/TheNetsky/Microsoft-Rewards-Script/tree/v3) and v3.x releases instead!
>
> Use at your own risk - some features may not work as expected.

---

## Table of Contents

- [Table of Contents](#table-of-contents)
- [Quick Setup](#quick-setup)
    - [Bare metal](#bare-metal)
        - [Get the script](#get-the-script)
- [Account Setup](#account-setup)
- [Config Setup](#config-setup)
    - [Build and run the script (bare metal version)](#build-and-run-the-script-bare-metal-version)
- [Docker](#docker)
- [Control API and Dashboard](#control-api-and-dashboard)
- [Nix Setup](#nix-setup)
- [Configuration Options](#configuration-options)
    - [Core](#core)
    - [Workers](#workers)
    - [Activities](#activities)
    - [Search Settings](#search-settings)
        - [Query sources](#query-sources)
    - [Experimental](#experimental)
        - [Activity source layout](#activity-source-layout)
    - [Logging](#logging)
    - [Proxy](#proxy)
    - [Webhooks](#webhooks)
- [Troubleshooting](#troubleshooting)
    - [Manual login](#manual-login)
    - [Session management](#session-management)
- [Disclaimer](#disclaimer)

---

## Quick Setup

### Bare metal

**Requirements:** Node.js >= 24 and Git  
Works on Windows, Linux, macOS, and WSL.

#### Get the script

```bash
git clone https://github.com/TheNetsky/Microsoft-Rewards-Script.git
cd Microsoft-Rewards-Script
```

Or, download the latest release ZIP and extract it.

## Account Setup

- Copy and rename [`env.example`](env.example) to `.env` and add your account credentials:

```env
ACCOUNT_1_EMAIL=email@example.com
# ACCOUNT_1_PASSWORD=your_password
```

> [!NOTE]
> `ACCOUNT_N_PASSWORD` is optional. Set it when password sign-in should be available; leave it unset for passwordless/Authenticator-only accounts.
>
> Add one `ACCOUNT_N_*` block per account. Account slots do not need to be contiguous: `ACCOUNT_2` or `ACCOUNT_4` can be configured even when earlier slots are missing. Accounts run in ascending slot order. Optional per-account fields cover recovery email, locale, language, proxy, and fingerprint persistence - see [`env.example`](env.example) for all of them.

`ACCOUNT_N_LANG_CODE` accepts a BCP 47 language tag such as `nl`, `it`, or `pt-BR`. `ACCOUNT_N_GEO_LOCALE` accepts a two-letter country code or defaults to `auto`. The selected language and country are applied consistently to browser fingerprints, `Accept-Language`, Microsoft Rewards app headers, and market-specific requests. In `auto` mode, the country reported by the Microsoft profile is cached after the first successful dashboard request; changing either locale setting automatically replaces an incompatible saved fingerprint.

> [!TIP]
> For 2FA accounts, set `ACCOUNT_N_TOTP_SECRET` and the script will generate and enter the 6-digit code automatically. To get the secret: in your Microsoft Security settings open 'Manage how you sign in', add an Authenticator app, and when the QR code appears choose 'enter code manually' - use that code as the value in your `.env`.

> [!WARNING]
> You must rebuild your script after making any changes to the `.env`.

## Config Setup

> [!WARNING]
> Do **not** skip this step if you are running the script bare metal.

- **Bare metal:** Copy or rename `config.example.json` to `config.json` (in the project root) and customize your preferences.
- **Docker:** A valid `config.json` is automatically created on first run and saved locally to `./config/`. You can optionally manually create a `config.json` (e.g., if you need to specify regex values) using the provided `config.example.json`

> [!CAUTION]
> Prior versions of accounts.json and config.json are not compatible with current release.

### Build and run the script (bare metal version)

```bash
npm run pre-build
npm run build
npm run start
```

## Docker

- Copy the sample [`compose.yaml`](compose.yaml)
- Copy and rename [`env.example`](env.example) to `.env` and add your account credentials:

```env
ACCOUNT_1_EMAIL=email@example.com
# ACCOUNT_1_PASSWORD=your_password
```

`ACCOUNT_N_PASSWORD` is optional; omit it for passwordless/Authenticator-only accounts.

- Review `compose.yaml` to adjust scheduling, timezone, and config options.

> [!NOTE]
> A valid `config.json` is auto-generated on first run using default values, and saved locally to `./config/`.
> Optionally, use `CONFIG_*` variables in the `environment:` section of the `compose.yaml` to customise your options (e.g., clusters, webhook, etc.).
> A full list of available options are in the [table below](#configuration-options).
> `CONFIG_*` variables are applied on every startup and always take precedence over `./config/config.json`.

> [!TIP]
> If a new image adds config options you're missing, a warning will appear in the container logs.
> To update, delete `./config/config.json` and restart - a fresh one will be generated from the latest example, with your `compose.yaml` overrides re-applied.

- Start the container: `docker compose up -d`

> [!TIP]
> Monitor logs with `docker logs microsoft-rewards-script`, useful for viewing passwordless login codes or diagnosing issues.
> You can also enable a webhook in `compose.yaml` for notifications.

---

## Control API and Dashboard

The optional Control API lets a local dashboard or another trusted tool monitor
and control the script over HTTP. See the [complete Control API
documentation](scripts/api/README.md) for setup, authentication, every endpoint,
request fields, response examples, and security guidance.

Common uses include:

- checking API health and the current run state with `GET /health` and
  `GET /status`;
- reading live points, logs, errors, account summaries, run history, and error
  diagnostics;
- listing safe stored-session metadata and deleting the mobile/desktop sessions
  for one account;
- starting all accounts with `POST /start` and an empty JSON body;
- running only one account with `POST /start` and `{"accountIndex":2}`;
- running all accounts except selected slots with `POST /start` and
  `{"excludedAccountIndexes":[2,4]}`;
- stopping or restarting a run with `POST /stop` or `POST /restart`;
- streaming live logs and status updates from `GET /events` using
  Server-Sent Events (SSE);
- reading the active configuration and schedule, with config and schedule
  changes available only when their explicit `API_ALLOW_*` options are enabled.

For example, start only `ACCOUNT_2` with cURL:

```bash
curl --request POST \
  --url http://127.0.0.1:3010/start \
  --header 'Authorization: Bearer YOUR_API_TOKEN' \
  --header 'Content-Type: application/json' \
  --data '{"accountIndex":2}'
```

For a ready-made web interface, use the supported and endorsed
[Rewards Dashboard](https://github.com/mgrimace/rewards-dashboard). It connects
to this Control API to manage runs, accounts, schedules, logs, points, and
related script settings.

---

## Nix Setup

If using Nix: `bash scripts/nix/run.sh`

---

## Configuration Options

Edit `config.json` to customize behavior, or set `CONFIG_*` environment variables in `compose.yaml` (Docker). Below are all currently available options.

> [!WARNING]
> Rebuild the script (bare metal), or recreate the container (Docker) after all config changes.

### Core

| Setting                     | Type    | Default      | Description                                                        | Docker environment variable           |
| --------------------------- | ------- | ------------ | ------------------------------------------------------------------ | ------------------------------------- |
| `sessionPath`               | string  | `"sessions"` | Directory to store browser sessions                                |                                       |
| `headless`                  | boolean | `false`      | Run browser invisibly                                              | Always `true` in Docker               |
| `clusters`                  | number  | `1`          | Number of concurrent account clusters                              | `CONFIG_CLUSTERS`                     |
| `errorDiagnostics`          | boolean | `false`      | Save error and unknown-login page diagnostics under `diagnostics/` | `CONFIG_ERROR_DIAGNOSTICS`            |
| `ensureStreakProtection`    | boolean | `true`       | Ensure streak protection is enabled                                | `CONFIG_ENSURE_STREAK_PROTECTION`     |
| `autoClaimPunchcardRewards` | boolean | `false`      | Auto-claim completed punchcard rewards                             | `CONFIG_AUTO_CLAIM_PUNCHCARD_REWARDS` |
| `contintueOnBotWarning`     | boolean | `false`      | Continue despite the Microsoft bot-score warning (not recommended) | `CONFIG_CONTINTUE_ON_BOT_WARNING`     |
| `skipNonPointTasks`         | boolean | `true`       | Skip tasks that award no points                                    | `CONFIG_SKIP_NON_POINT_TASKS`         |
| `accountDelay.min`          | string  | `"1min"`     | Minimum delay before starting the next configured account          | `CONFIG_ACCOUNT_DELAY_MIN`            |
| `accountDelay.max`          | string  | `"3min"`     | Maximum delay before starting the next configured account          | `CONFIG_ACCOUNT_DELAY_MAX`            |
| `searchOnBingLocalQueries`  | boolean | `false`      | Use the local query list for ExploreOnBing                         | `CONFIG_SEARCH_ON_BING_LOCAL`         |
| `globalTimeout`             | string  | `"30sec"`    | Timeout for all actions                                            | `CONFIG_GLOBAL_TIMEOUT`               |

### Workers

| Setting                        | Type    | Default | Description                                                                | Docker environment variable          |
| ------------------------------ | ------- | ------- | -------------------------------------------------------------------------- | ------------------------------------ |
| `workers.doDailySet`           | boolean | `true`  | Complete daily set                                                         | `CONFIG_WORKER_DAILY_SET`            |
| `workers.doClaimBonusPoints`   | boolean | `true`  | Claim bonus points                                                         | `CONFIG_WORKER_CLAIM_BONUS_POINTS`   |
| `workers.doMorePromotions`     | boolean | `true`  | Complete "more activities"                                                 | `CONFIG_WORKER_MORE_PROMOTIONS`      |
| `workers.doPunchCards`         | boolean | `true`  | Complete punchcards                                                        | `CONFIG_WORKER_PUNCH_CARDS`          |
| `workers.doAppPromotions`      | boolean | `true`  | Complete app promotions                                                    | `CONFIG_WORKER_APP_PROMOTIONS`       |
| `workers.doDesktopSearch`      | boolean | `true`  | Perform desktop searches                                                   | `CONFIG_WORKER_DESKTOP_SEARCH`       |
| `workers.doMobileSearch`       | boolean | `true`  | Perform mobile searches                                                    | `CONFIG_WORKER_MOBILE_SEARCH`        |
| `workers.doBonusSearches`      | boolean | `false` | Farm bonus searches beyond the cap                                         | `CONFIG_WORKER_BONUS_SEARCHES`       |
| `workers.doDailyCheckIn`       | boolean | `true`  | Complete daily check-in                                                    | `CONFIG_WORKER_DAILY_CHECKIN`        |
| `workers.doReadToEarn`         | boolean | `true`  | Complete Read-to-Earn                                                      | `CONFIG_WORKER_READ_TO_EARN`         |
| `workers.doActivateSearchPerk` | boolean | `true`  | Activate the "search Nx more" perk when present (runs after the daily set) | `CONFIG_WORKER_ACTIVATE_SEARCH_PERK` |
| `workers.doVisualSearch`       | boolean | `false` | Activate the visual-search streak and perform visual searches              | `CONFIG_WORKER_VISUAL_SEARCH`        |

### Activities

| Setting                   | Type    | Default | Description                    | Docker environment variable      |
| ------------------------- | ------- | ------- | ------------------------------ | -------------------------------- |
| `activities.urlReward`    | boolean | `true`  | Complete URL reward activities | `CONFIG_ACTIVITY_URL_REWARD`     |
| `activities.searchOnBing` | boolean | `true`  | Complete ExploreOnBing offers  | `CONFIG_ACTIVITY_SEARCH_ON_BING` |

### Search Settings

| Setting                                | Type     | Default                             | Description                                               | Docker environment variable        |
| -------------------------------------- | -------- | ----------------------------------- | --------------------------------------------------------- | ---------------------------------- |
| `searchSettings.scrollRandomResults`   | boolean  | `false`                             | Scroll randomly on results                                | `CONFIG_SEARCH_SCROLL_RANDOM`      |
| `searchSettings.clickRandomResults`    | boolean  | `false`                             | Click random links                                        | `CONFIG_SEARCH_CLICK_RANDOM`       |
| `searchSettings.runOnZeroPoints`       | boolean  | `false`                             | Run searches even when no search points remain            | `CONFIG_SEARCH_RUN_ON_ZERO_POINTS` |
| `searchSettings.maxBonusSearches`      | number   | `110`                               | Max bonus searches per run (when `doBonusSearches` is on) | `CONFIG_SEARCH_MAX_BONUS_SEARCHES` |
| `searchSettings.parallelSearching`     | boolean  | `true`                              | Run searches in parallel                                  | `CONFIG_SEARCH_PARALLEL`           |
| `searchSettings.clusterSearch`         | boolean  | `true`                              | Cluster each main topic with Bing suggestions             | `CONFIG_SEARCH_CLUSTER`            |
| `searchSettings.queryEngines`          | string[] | see [Query sources](#query-sources) | Sources used to build the search query pool               | `CONFIG_SEARCH_QUERY_ENGINES` \*   |
| `searchSettings.searchResultVisitTime` | string   | `"10sec"`                           | Time to spend on each search result                       | `CONFIG_SEARCH_VISIT_TIME`         |
| `searchSettings.searchDelay.min`       | string   | `"30sec"`                           | Minimum delay between searches                            | `CONFIG_SEARCH_DELAY_MIN`          |
| `searchSettings.searchDelay.max`       | string   | `"1min"`                            | Maximum delay between searches                            | `CONFIG_SEARCH_DELAY_MAX`          |
| `searchSettings.readDelay.min`         | string   | `"30sec"`                           | Minimum delay for reading                                 | `CONFIG_SEARCH_READ_DELAY_MIN`     |
| `searchSettings.readDelay.max`         | string   | `"1min"`                            | Maximum delay for reading                                 | `CONFIG_SEARCH_READ_DELAY_MAX`     |

Desktop and mobile search quotas are tracked independently from the dashboard counters. All `mobileSearch` entries are combined for the mobile quota, while all `pcSearch` entries are combined for desktop execution; a counter explicitly identified as Edge is also shown separately for diagnostics. The script skips only the completed platform, so a completed `60/60` mobile quota does not prevent an incomplete desktop quota from running. With `parallelSearching` enabled, both incomplete quotas can run concurrently in their own browser contexts.

> [!NOTE]
> \* Docker `CONFIG_*` array values are comma-separated strings e.g. `"error,warn"`. Regex patterns must be set directly in `config.json`.

#### Query sources

`searchSettings.queryEngines` controls where the main search topics come from. Pick any combination; topics from all selected sources are pooled and de-duplicated. When `searchSettings.clusterSearch` is enabled, each main topic is expanded on demand with Bing suggestions, that topic cluster is shuffled and completed, and only then does searching move to the next main topic.

Core sources:

| Selector     | Source                                           |
| ------------ | ------------------------------------------------ |
| `google`     | Google Trends (trending searches)                |
| `wikipedia`  | Wikipedia most-read articles (previous day)      |
| `wikirandom` | Random Wikipedia articles                        |
| `hackernews` | Hacker News front-page stories                   |
| `reddit`     | Reddit r/popular post titles                     |
| `local`      | Bundled `src/functions/search-queries.json` list |

RSS feeds use a dotted path - `rss` for every feed, `rss.<site>` for a whole site, or `rss.<site>.<endpoint>` for a single feed:

| Selector           | Feeds                                                          |
| ------------------ | -------------------------------------------------------------- |
| `rss.googleTrends` | Google Trends RSS (`gb`, `us`)                                 |
| `rss.googleNews`   | Google News (`gb`, `us`, `world`, `technology`, `business`)    |
| `rss.bbc`          | BBC News (`top`, `world`, `technology`, `business`, `science`) |
| `rss.guardian`     | The Guardian (`international`, `world`, `technology`)          |
| `rss.theVerge`     | The Verge (`all`)                                              |
| `rss.arsTechnica`  | Ars Technica (`all`)                                           |
| `rss.reddit`       | Reddit listing feeds (`popular`, `worldnews`, `technology`)    |

Add your own feeds in `src/constants/rssFeeds.ts`.

Default:

```json
[
    "google",
    "wikipedia",
    "wikirandom",
    "hackernews",
    "reddit",
    "local",
    "rss.googleTrends",
    "rss.googleNews",
    "rss.bbc",
    "rss.guardian.world",
    "rss.theVerge.all"
]
```

### Experimental

Opt-in features that may change. Disabled by default.

| Setting                        | Type    | Default | Description                                                             | Docker environment variable              |
| ------------------------------ | ------- | ------- | ----------------------------------------------------------------------- | ---------------------------------------- |
| `experimental.apiSearch`       | boolean | `false` | Perform Bing searches over HTTP instead of driving a browser page       | `CONFIG_EXPERIMENTAL_API_SEARCH`         |
| `experimental.apiSearchOnBing` | boolean | `false` | Complete ExploreOnBing offers over HTTP instead of the browser          | `CONFIG_EXPERIMENTAL_API_SEARCH_ON_BING` |
| `experimental.blockMedia`      | boolean | `false` | Block post-login browser `image` and `media` requests to reduce traffic | `CONFIG_EXPERIMENTAL_BLOCK_MEDIA`        |
| `experimental.edgeBrowsing`    | boolean | `false` | Report the 30-minute Edge browsing activity as a background HTTP task   | `CONFIG_EXPERIMENTAL_EDGE_BROWSING`      |

When `experimental.blockMedia` is enabled, the automated flow activates it only after authentication has been
verified and the session has been saved. The manual-login flow keeps media enabled throughout; `npm run open-session` still
applies the configured blocker immediately because it opens an already-saved session.

When `experimental.edgeBrowsing` is enabled, the task starts before the normal activity sequence and runs as a separate Promise alongside Daily Set, promotions, app activities, and searches. If foreground work finishes first, the account remains open until this Promise settles. Accounts without the promotion, an access token, or remaining Edge work are skipped immediately.

#### Activity source layout

Standard activities live under `src/functions/activities`, grouped by responsibility:

- `rewards`: Daily Set, More Promotions, Punch Cards, and shared promotion dispatch
- `api`: individual Rewards API actions
- `app`: individual mobile-app activities and App Promotions orchestration
- `search`: browser search flows, search tracking, and shared SearchOnBing behavior
- `visualSearch`: the visual-search activity and its browser transport
- `experimental`: API Search, API SearchOnBing, Edge Browsing, and their supporting transports

Experimental activities live with the other activities under `src/functions/activities/experimental`. The browser-only media blocker lives at `src/browser/MediaBlocker.ts`. `BrowserFunc` contains shared Rewards/browser/session transport only, rather than individual search or visual-search implementations.

> [!NOTE]
> [Playwright documents](https://playwright.dev/docs/api/class-browsercontext#browser-context-route) that request routing disables the browser HTTP cache while routing is active. Image-heavy pages will usually transfer substantially less data with media blocking enabled, but cache-heavy sites are not guaranteed to use less total bandwidth or load faster. Keep this option disabled if a site depends on image/media load events.

> [!NOTE]
> The API paths are faster but depend on the modern dashboard's endpoints. If an ExploreOnBing offer ever fails to be credited, turn `apiSearchOnBing` off to fall back to the browser path.

Regardless of the experimental search settings, normal Rewards actions use the cookies and action data captured during bootstrap without refreshing the visible page. The browser remains idle until a browser-backed search starts. A failed or unacknowledged URL-reward request triggers one context refresh and one retry; successful requests use the balance returned by the server action.

### Logging

| Setting                          | Type     | Default                | Description                       | Docker environment variable     |
| -------------------------------- | -------- | ---------------------- | --------------------------------- | ------------------------------- |
| `debugLogs`                      | boolean  | `false`                | Enable debug logging              | `CONFIG_DEBUG_LOGS`             |
| `consoleLogFilter.enabled`       | boolean  | `false`                | Enable console log filtering      | `CONFIG_LOG_FILTER_ENABLED`     |
| `consoleLogFilter.mode`          | string   | `"whitelist"`          | Filter mode (whitelist/blacklist) | `CONFIG_LOG_FILTER_MODE`        |
| `consoleLogFilter.levels`        | string[] | `["error", "warn"]`    | Log levels to filter              | `CONFIG_LOG_FILTER_LEVELS` \*   |
| `consoleLogFilter.keywords`      | string[] | `["starting account"]` | Keywords to filter                | `CONFIG_LOG_FILTER_KEYWORDS` \* |
| `consoleLogFilter.regexPatterns` | string[] | `[]`                   | Regex patterns for filtering      |                                 |

> [!NOTE]
> \* Docker `CONFIG_*` array values are comma-separated strings e.g. `"error,warn"`. Regex patterns must be set directly in `config.json`.

### Proxy

| Setting                         | Type    | Default | Description                                                        | Docker environment variable              |
| ------------------------------- | ------- | ------- | ------------------------------------------------------------------ | ---------------------------------------- |
| `proxy.queryEngine`             | boolean | `true`  | Proxy query engine requests                                        | `CONFIG_PROXY_QUERY_ENGINE`              |
| `proxy.ignoreCertificateErrors` | boolean | `false` | Disable browser TLS certificate verification for intercept proxies | `CONFIG_PROXY_IGNORE_CERTIFICATE_ERRORS` |

Leave `proxy.ignoreCertificateErrors` disabled for normal HTTP(S)/SOCKS proxies. Enabling it weakens TLS protection for the entire browser context and should only be used when a trusted intercepting proxy cannot otherwise present a valid certificate.

`proxy.queryEngine` controls whether query-source HTTP requests use the account HTTP proxy. Set the corresponding `ACCOUNT_N_PROXY_HTTP=true` (and configure `ACCOUNT_N_PROXY_*`) for those HTTP requests to have a proxy available; browser traffic uses `ACCOUNT_N_PROXY_URL` independently.

Account browser proxies support `http://`, `https://`, `socks4://`, and `socks5://` (a bare hostname is treated as HTTP). HTTP(S) proxies may use `ACCOUNT_N_PROXY_USERNAME` and `ACCOUNT_N_PROXY_PASSWORD`; Patchright does not support browser authentication for SOCKS4/SOCKS5 proxies. Invalid protocols, ports, partial credentials, and authenticated SOCKS proxy configurations are rejected during account validation before the browser starts.

### Webhooks

| Setting                                  | Type     | Default                                              | Description                       | Docker environment variable             |
| ---------------------------------------- | -------- | ---------------------------------------------------- | --------------------------------- | --------------------------------------- |
| `webhook.discord.enabled`                | boolean  | `false`                                              | Enable Discord webhook            | `CONFIG_DISCORD_ENABLED`                |
| `webhook.discord.url`                    | string   | `""`                                                 | Discord webhook URL               | `CONFIG_DISCORD_URL`                    |
| `webhook.telegram.enabled`               | boolean  | `false`                                              | Enable Telegram webhook           | `CONFIG_TELEGRAM_ENABLED`               |
| `webhook.telegram.botToken`              | string   | `""`                                                 | Telegram bot token                | `CONFIG_TELEGRAM_BOTTOKEN`              |
| `webhook.telegram.chatId`                | string   | `""`                                                 | Telegram chat id                  | `CONFIG_TELEGRAM_CHATID`                |
| `webhook.ntfy.enabled`                   | boolean  | `false`                                              | Enable ntfy notifications         | `CONFIG_NTFY_ENABLED`                   |
| `webhook.ntfy.url`                       | string   | `""`                                                 | ntfy server URL                   | `CONFIG_NTFY_URL`                       |
| `webhook.ntfy.topic`                     | string   | `""`                                                 | ntfy topic                        | `CONFIG_NTFY_TOPIC`                     |
| `webhook.ntfy.token`                     | string   | `""`                                                 | ntfy authentication token         | `CONFIG_NTFY_TOKEN`                     |
| `webhook.ntfy.title`                     | string   | `"Microsoft-Rewards-Script"`                         | Notification title                | `CONFIG_NTFY_TITLE`                     |
| `webhook.ntfy.tags`                      | string[] | `["bot", "notify"]`                                  | Notification tags                 | `CONFIG_NTFY_TAGS` \*                   |
| `webhook.ntfy.priority`                  | number   | `3`                                                  | Notification priority (1-5)       | `CONFIG_NTFY_PRIORITY`                  |
| `webhook.webhookLogFilter.enabled`       | boolean  | `false`                                              | Enable webhook log filtering      | `CONFIG_WEBHOOK_LOG_FILTER_ENABLED`     |
| `webhook.webhookLogFilter.mode`          | string   | `"whitelist"`                                        | Filter mode (whitelist/blacklist) | `CONFIG_WEBHOOK_LOG_FILTER_MODE`        |
| `webhook.webhookLogFilter.levels`        | string[] | `["error"]`                                          | Log levels to send                | `CONFIG_WEBHOOK_LOG_FILTER_LEVELS` \*   |
| `webhook.webhookLogFilter.keywords`      | string[] | `["starting account", "select number", "collected"]` | Keywords to filter                | `CONFIG_WEBHOOK_LOG_FILTER_KEYWORDS` \* |
| `webhook.webhookLogFilter.regexPatterns` | string[] | `[]`                                                 | Regex patterns for filtering      |                                         |

> [!NOTE]
> \* Docker `CONFIG_*` array values are comma-separated strings e.g. `"error,warn"`. Regex patterns must be set directly in `config.json`.

> [!WARNING]
> **NTFY** users set the `webhookLogFilter` to `enabled`, or you will receive push notifications for _all_ logs.
> When enabled, only account start, 2FA codes, and account completion summaries are delivered as push notifications.
> Customize which notifications you receive with the `keywords` options.

---

## Troubleshooting

> [!TIP]
> Most login issues can be fixed by deleting your /sessions folder, and redeploying the script

### Manual login

Use the manual-login command when an account needs an interactive Microsoft sign-in. It opens the same bundled
patched Chromium browser in headful mode and does not invoke the automated login handler. After you finish signing
in, the command waits until the browser remains on `rewards.bing.com` for five continuous seconds, saves the session,
and closes the browser automatically.

```bash
# Create or refresh the mobile session used at the start of automated runs
npm run manual-login -- --email user@example.com

# Create or refresh only the desktop session
npm run manual-login -- --email user@example.com --platform desktop

# Create mobile and desktop sessions sequentially
npm run manual-login -- --email user@example.com --platform both

# Ignore existing cookies and perform a clean sign-in
npm run manual-login -- --email user@example.com --fresh
```

The email must match an `ACCOUNT_N_EMAIL` entry in `.env`. Existing cookies are restored by default, while `--fresh`
starts without them but retains a compatible saved fingerprint when fingerprint persistence is enabled. The command
uses the selected account's language, region, proxy, proxy credentials, and fingerprint settings from `.env`. For
consistent device identity between the manual and automated browser, enable `ACCOUNT_N_SAVE_FINGERPRINT_MOBILE=true`
and/or
`ACCOUNT_N_SAVE_FINGERPRINT_DESKTOP=true` for the platforms you use.

The session path, global timeout, media-blocking option, and proxy TLS option come from `config.json`. The corresponding
`CONFIG_GLOBAL_TIMEOUT`, `CONFIG_EXPERIMENTAL_BLOCK_MEDIA`, and
`CONFIG_PROXY_IGNORE_CERTIFICATE_ERRORS` environment overrides are also applied after `.env` is loaded. Manual login
forces a visible browser and defers media blocking for the entire interactive authentication flow, even when
`experimental.blockMedia` is enabled. Automated runs resume the configured blocker only after login verification and
session saving, so authentication SVGs, QR codes, and videos cannot be blocked by this option.

Run this command directly on a computer with a graphical desktop and a full Patchright Chromium installation. The
default Docker image contains only the headless browser shell and cannot display this interactive window.

### Session management

The session utility requires an explicit command, so running it without an
argument only displays help and never deletes anything.

```bash
# List stored mobile and desktop sessions
npm run clear-sessions -- list

# Delete the sessions belonging to one account
npm run clear-sessions -- email user@example.com

# Delete every stored session
npm run clear-sessions -- all
```

```bash
# List safe session metadata
curl --request GET \
  --url http://127.0.0.1:3010/sessions \
  --header 'Authorization: Bearer YOUR_API_TOKEN'

# Delete only user@example.com's mobile and desktop sessions
curl --request DELETE \
  --url http://127.0.0.1:3010/sessions/user%40example.com \
  --header 'Authorization: Bearer YOUR_API_TOKEN'
```

See the [Control API session documentation](scripts/api/README.md#session-management)
for response data, Axios examples, and error behavior.

---

## Disclaimer

Use at your own risk.  
Automation of Microsoft Rewards may lead to account suspension or bans.  
This software is provided for educational purposes only.  
The authors are not responsible for any actions taken by Microsoft.


</details>
