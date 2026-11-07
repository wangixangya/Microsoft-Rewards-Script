# Microsoft Rewards Script · v5 中文说明

> 本文件是 v5 分支的汉化文档，对应上游 `TheNetsky/Microsoft-Rewards-Script` 的 v5 版本。
> 上游 README 保持英文不动，方便跟随更新；中文内容与本地改造（镜像补丁、面板、单文件包）都写在这里。

---

## 1. 这一版和 v4 的区别

| 项目 | v4 | v5 |
|---|---|---|
| Node.js | ≥ 20 | **≥ 24**（低于 24 直接拒绝启动） |
| 浏览器 | playwright | **patchright**（反检测分支）+ fingerprint 注入 |
| 并发 | 单进程串行 | 原生 `clusters`（每个 cluster 一个浏览器） |
| 配置 | `config.json` 部分字段不同 | 新增 `clusters` / `accountDelay` / `taskDelay` / `searchSettings` / `experimental` |
| 运行记录 | 字符串 | `API_RUN_HISTORY` 是**整数**（天数） |
| 目录 | `dist/` | `dist/` 同构，但 `scripts/api/*` 扩充了控制接口 |

会话（cookies）默认在 `sessions/`，账号密码建议只走环境变量或 `config.json` 的 `accounts`。

---

## 2. 快速开始（Docker，推荐）

```bash
docker run -d --name ms-rewards \
  -e TZ=Asia/Shanghai \
  -e CONFIG_CLUSTERS=2 \
  -v "$PWD/config:/usr/src/microsoft-rewards-script/config" \
  -v "$PWD/sessions:/usr/src/microsoft-rewards-script/sessions" \
  ghcr.io/thenetsky/microsoft-rewards-script:5
```

带国内补丁的镜像（本项目产出，Bing 域名判定放宽到 `cn.bing.com`）：

```bash
ghcr.io/wangixangya/microsoft-rewards-script:5-cn
```

两个镜像的区别只有一处：源码里 `origin === URLs.bing.origin` 这类比较改成 `isBingHost(...)`，
让 `cn.bing.com` 也能通过校验，避免国内网络下搜索任务被判“不在 Bing 页面”。

---

## 3. 关键配置（`config/config.json`）

```jsonc
{
  "clusters": 2,              // 并发分片数，1~4，每片独占一个浏览器
  "headless": true,           // 无头模式；面板/青龙跑必须 true
  "accountDelay": { "min": 1, "max": 3 },   // 分片之间的随机间隔（分钟）
  "taskDelay":   { "min": 3, "max": 8 },    // 单任务之间的随机间隔（秒）
  "rewardsMode": "maximize",  // maximize=尽量多刷；points=只做基础分
  "workers": {
    "doDailySet": true,
    "doMorePromotions": true,
    "doPunchCard": true,
    "doDesktopSearch": true,
    "doMobileSearch": true,
    "doDailyCheckIn": true
  },
  "searchSettings": { "useGeoLocale": false, "scrollRandomResults": true },
  "globalTimeout": "30m",
  "debugLogs": false,
  "proxy": { "query": "", "httpsAgent": false }
}
```

- `clusters` 只是**分片并行**，不是“同一账号多开”；同一账号永远只会有一个浏览器。
- 内存经验值：空闲约 34 MiB，单账号跑起来峰值约 **1.19 GiB**；2 并发建议留 2 GB 以上。
- 账号密码写在 `accounts` 里即可；有 2FA 的用 `otpauth` 的 secret 或 `TOTP` 字段。

---

## 4. 面板（`panel/`，中文）

`panel/` 是本项目自带的中文控制台，直连 v5 的 `scripts/api` 后端，不修改上游代码：

```bash
cd panel && python3 server.py      # 默认 0.0.0.0:5310，密码见 panel.conf
```

功能：总览、账号与会话、运行日志、任务配置、奖励中心、设置（运行计划 / 推送渠道 / 代理管理 / 镜像与版本 / 发布中心）。
镜像与版本页可以直接「用远端 :5-cn 重建」，发布中心能看到仓库提交、远端镜像摘要、JS 单文件、通知目标。

---

## 5. 青龙单文件版（可选）

Release `ql-single-v5` 提供一个自解包单文件（约 31.7 MB，内嵌 glibc/musl 两种 `impit`）：

```bash
bash ms-rewards-single-v5.js          # 需要 Node ≥ 24；可用环境变量注入账号
```

> 注意：青龙容器通常是 Node 20 或 22，**必须先升到 24** 才能跑 v5 单文件，否则会在启动时报版本错误。

---

## 6. 更新与同步（本项目做法）

```
上游 v5 更新
   └─ 每天 05:00 自动 merge → 推送我的仓库 v5 分支
        ├─ GitHub Actions：Validate(v5) + 构建带补丁的 :5-cn 镜像
        ├─ 拉取/重建本地运行容器（ms-rewards-api）
        ├─ 重建单文件包并上传 Release（payload 变化时才发）
        └─ 摘要推送到 Telegram 通知群
```

上游更新不会覆盖本仓库的汉化文件：`panel/`、`README.zh-CN.md`、`.github/scripts/patch-bing-origin.js`、
`.github/workflows/cn-image.yml` 都是**新增文件**；合并时若上游恰好也新增同名文件，脚本会保留本仓库版本。

---

## 7. 常见问题

**Q：搜索结果全是 0 分？**
A：先确认用的是 `:5-cn` 镜像（或本地派生镜像），国内网络下未打补丁会被 Bing 域名校验拦掉；再看 `debugLogs`。

**Q：登录一直失败？**
A：v5 默认 patchright，容器里必须能起 Chromium；`headless:true` 时若报浏览器缺失，先执行 `npm run install:browser`。

**Q：会不会封号？**
A：脚本只是把日常任务自动化，`accountDelay` / `taskDelay` 随机化就是为了避免固定节奏；仍建议一个账号一台出口 IP，别多开。

**Q：面板和脚本同时跑会不会抢浏览器？**
A：不会。面板只在 API 容器里以“单次任务”形式调用 `rewards-center.js`，且运行中会拒绝重建镜像/同步这类操作。
