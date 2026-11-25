# 微软 / Bing 域名强制直连说明

> 本页是本机运维说明（中文）。适用：mihomo 作为代理网关、Microsoft Rewards 自动化容器在本机运行的场景。

## 为什么要直连

Microsoft Rewards 脚本要访问 `cn.bing.com` / `rewards.bing.com` 做搜索、去 `rewards.bing.com/earn` 拿任务面板、并维持 `login.live.com` 的登录会话。这些域名一旦走代理节点，会出现一连串故障：

- 桌面搜索阶段 `page.waitForURL: Timeout`、搜索 0 条、积分掉分；
- bootstrap 阶段 `page.goto` 30s 超时、双账号 0 分；
- `reqwest::Error ... PROTOCOL_ERROR` / 504，任务被记 `partial`。

根因：代理节点的 TLS 指纹与中间件会破坏微软 React flight chunk 的解析，且国内 IP 访问 `www.bing.com` 会被 302 到 `cn.bing.com`，origin 比对失败。**这些域名必须直连，不走任何代理节点。**

实测对比：bing.com 直连约 0.18s，走代理约 1.09s（差 6 倍）；走代理时搜索解析直接失败。

## 规则清单（必须 DIRECT）

以下域名全部在 mihomo `rules:` 段**最前面**配 `DOMAIN-SUFFIX,<域>,DIRECT`（首次匹配生效，放最前才不会被后面的代理规则抢走）：

| 类别        | 域名                                                                                                                                                                      |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 搜索 / 积分 | `bing.com` `bing.net` `msn.com` `msn.net` `msn.cn`                                                                                                                        |
| 账号 / 登录 | `live.com` `live.cn` `live.net` `outlook.com` `hotmail.com` `microsoftonline.com`                                                                                         |
| 服务 / 域   | `microsoft.com` `microsoft.net` `office.com` `office365.com` `sharepoint.com` `onedrive.com` `skype.com` `windows.com` `windows.net` `xbox.com` `microsofttranslator.com` |
| CDN / 其他  | `azureedge.net` `azurewebsites.net` `livefilestore.com` `clarity.ms` `grammarly.com`                                                                                      |

共 24 个域名。任何一条落成代理，都可能导致登录态失效或搜索掉分。

## 配置示例

`/etc/mihomo/config.yaml` 的 `rules:` 段开头：

```yaml
rules:
    # === 微软/bing 全系直连（走代理会破坏 rewards 登录态/触发风控，必须 DIRECT）===
    - DOMAIN-SUFFIX,bing.com,DIRECT
    - DOMAIN-SUFFIX,bing.net,DIRECT
    - DOMAIN-SUFFIX,msn.com,DIRECT
    - DOMAIN-SUFFIX,msn.net,DIRECT
    - DOMAIN-SUFFIX,msn.cn,DIRECT
    - DOMAIN-SUFFIX,microsoft.com,DIRECT
    - DOMAIN-SUFFIX,microsoftonline.com,DIRECT
    - DOMAIN-SUFFIX,live.com,DIRECT
    - DOMAIN-SUFFIX,live.cn,DIRECT
    - DOMAIN-SUFFIX,live.net,DIRECT
    - DOMAIN-SUFFIX,outlook.com,DIRECT
    - DOMAIN-SUFFIX,hotmail.com,DIRECT
    - DOMAIN-SUFFIX,office.com,DIRECT
    - DOMAIN-SUFFIX,office365.com,DIRECT
    - DOMAIN-SUFFIX,sharepoint.com,DIRECT
    - DOMAIN-SUFFIX,onedrive.com,DIRECT
    - DOMAIN-SUFFIX,skype.com,DIRECT
    - DOMAIN-SUFFIX,microsoft.net,DIRECT
    - DOMAIN-SUFFIX,windows.com,DIRECT
    - DOMAIN-SUFFIX,windows.net,DIRECT
    - DOMAIN-SUFFIX,xbox.com,DIRECT
    - DOMAIN-SUFFIX,azureedge.net,DIRECT
    - DOMAIN-SUFFIX,azurewebsites.net,DIRECT
    - DOMAIN-SUFFIX,livefilestore.com,DIRECT
    - DOMAIN-SUFFIX,microsofttranslator.com,DIRECT
    - DOMAIN-SUFFIX,clarity.ms,DIRECT
    - DOMAIN-SUFFIX,grammarly.com,DIRECT
# ... 其余规则照旧
```

注意把原配置里 `live.com / outlook.com / skype.com / azureedge.net / onedrive.com / windows.net` 等指向代理节点（如 `Crush Cloud`）的行**注释掉**，避免误读。即使不注释，前面的 DIRECT 规则也会优先生效。

改前先备份：`cp /etc/mihomo/config.yaml /etc/mihomo/config.yaml.bak-msdirect-$(date +%s)`，改完 `systemctl restart mihomo`。

## 验证

1. 看 mihomo 实际加载的规则（确认全部 `DIRECT`）：

    ```bash
    curl -s http://127.0.0.1:9090/rules | python3 -c "
    import sys,json
    d=json.load(sys.stdin)
    seen={}
    for x in d['rules']:
        for k in ['bing.com','live.com','outlook.com','microsoft.com','msn.com']:
            if k not in seen and x.get('payload')==k: seen[k]=x['proxy']
    for k,v in seen.items(): print(k,'->',v)"
    ```

    期望每行都是 `-> DIRECT`。

2. 直连连通性：

    ```bash
    curl -s -o /dev/null -w '%{http_code}\n' --max-time 12 https://cn.bing.com
    ```

    期望 `200`。

3. 真跑一轮 rewards，日志里 `SEARCH-BING] Searching | search=1..N` 正常推进、无 `waitForURL ... Timeout`，即确认直连生效。

## 注意

- 重启 mihomo 会短暂断代理，正在走代理的其它任务（如京东 relayPool）可能受影响，尽量避开任务时段，或事后检查。
- 上游代理节点失效时，`curl -x http://127.0.0.1:7890 https://cn.bing.com` 可能返回 000——这是节点问题，**不影响 bing/msn 的 DIRECT 规则**（DIRECT 本就绕开节点）。别把这个 000 误判成规则配错。
