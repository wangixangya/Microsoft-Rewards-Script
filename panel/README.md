# Rewards Web 控制台

给 [Microsoft-Rewards-Script](https://github.com/wangixangya/Microsoft-Rewards-Script) 配的 Web 面板。
脚本本身只有控制 API（`scripts/api/server.js`，日志里写 `headless - no UI`），这里补上前端 + 反向代理 + 调度 + 统计 + 推送。

纯 Python 标准库 + 原生 JS，无构建、无第三方依赖。

## 功能

| 页面 | 内容 |
|---|---|
| 总览 | 今日收益、区间合计、累计余额、运行状态；收益趋势折线（7/14 天）、收益构成分项、账号对比、最近运行；按账号切换整页数据 |
| 账号与会话 | 账号余额/连续成功/上次运行；Cookie 会话增删；**Web 里直接添加/删除账号**（写 env.list 后自动重建容器） |
| 运行日志 | 实时拉取控制 API 日志，按级别着色，自动滚动 |
| 任务配置 | 任务开关、搜索设置、整份 config.json 编辑（保存自动备份） |
| 运行计划 | 面板侧 cron 调度（不依赖容器内 cron），可启停、改表达式、立刻试跑 |
| 推送渠道 | Telegram / 企业微信 / 钉钉 / Bark / Server酱 / PushPlus / Gotify / ntfy / SMTP / 通用 Webhook，运行结束、失败、每日汇总三类事件 |

## 部署

```bash
# 1. 目录
mkdir -p /root/ms-panel && cd /root/ms-panel
# 把本目录的 *.py index.html 拷进来，recreate_ms.sh 放到 /root/

# 2. 配置
cp panel.conf.example panel.conf && chmod 600 panel.conf
# 填 API_TOKEN（容器启动时注入的同一个值）、PANEL_PASSWORD
cp env.example env.list && chmod 600 env.list   # 账号密码

# 3. 起 API 模式容器（不要和旧 cron 容器同时跑）
bash /root/recreate_ms.sh wangixangya/microsoft-rewards-script:v4.3.3

# 4. 起面板
cp systemd/ms-panel.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now ms-panel
```

访问 `http://<NAS-IP>:5310`，密码是 `panel.conf` 里的 `PANEL_PASSWORD`。

## 设计要点

- **token 不下发浏览器**：登录后发 `HMAC(API_TOKEN, ts)` 签名 cookie，前端只访问面板自己的 `/api/*`，由 `server.py` 注入 `Authorization`。
- **调度在面板侧**：容器跑 `API_MODE=true` + `CRON_SCHEDULE=` 时不会自己跑任务；面板的调度线程匹配 cron 后 `POST /start`，这样日志/进度才在 API 的视野里。
- **统计靠日志**：`stats.py` 解析容器日志归档 `logs-7d.txt` 和面板采集的 `runlog.jsonl`，按 (日期, 账号, offerId) 去重取最大值，产出 `history.json`；容器重启丢的是 API 内存态，历史不丢。
- **账号只能靠环境变量**：脚本从 `ACCOUNT_N_EMAIL` 读账号，所以增删账号 = 改 `env.list` + 重建容器；面板在任务运行中会拒绝这种操作（409）。

## 接口一览

```
GET    /panel/stats?days=N      收益统计
GET    /panel/accounts          账号（读 env.list）
POST   /panel/accounts          添加账号 {email,password,geoLocale,totp?}
DELETE /panel/accounts?index=N  删除账号
GET    /panel/schedule          调度配置
PUT    /panel/schedule          保存调度
GET    /panel/notify            推送配置（密钥字段脱敏返回）
PUT    /panel/notify            保存推送配置
POST   /panel/notify/test       发送测试 {id?}
*      /api/*                  反向代理到 127.0.0.1:3010（自动注入 Bearer）
```

## 注意

- `microsoft-rewards-script`（旧 cron 容器）和 `ms-rewards-api` 共用 config/sessions 卷，**不能同时运行**，否则同账号双跑抢积分、易触发风控。
- `panel.conf`、`env.list`、`notify.json` 含凭据，已在 `.gitignore` 里，别提交。
- 推送里的密钥保存后回显为 `******`，保存时原样回传即表示“沿用旧值”。

## v2.6.0 新增

- 总览：系统状态卡（CPU / 内存 / 磁盘 / 温度 / 容器 / 运行时长）
- 运行日志：运行历史表（开始、耗时、退出码、得分）+ 自动刷新开关
- 设置 → 备份与恢复：配置打包成 zip、列表下载、一键回滚（回滚前自动留档）
- 设置 → 发布中心：可一键重建 JS 单文件、直达 GitHub Release
- 账号页：每行「密码/2FA」按钮，可直接改 env.list 并重建容器
- 推送：Telegram 渠道支持代理（自动读 `TELEGRAM_PROXY`），解决直连超时
