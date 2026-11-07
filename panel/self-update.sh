#!/bin/bash
# 面板自更新：从 GitHub 仓库 v4 分支的 panel/ 拉取最新面板代码，备份 → 语法检查 → 替换 → 重启
# 用法: bash /root/ms-panel/self-update.sh
# 日志: /tmp/ms-panel-selfupdate.log
set -uo pipefail
LOG=/tmp/ms-panel-selfupdate.log
DEST=/root/ms-panel
REPO=wangixangya/Microsoft-Rewards-Script
REF=v4
FILES="server.py index.html update-image.sh stats.py notify.py"
ts() { date '+%H:%M:%S'; }
say() { echo "[$(ts)] $*" >> "$LOG"; }

: > "$LOG"
say "=== 面板自更新开始（$REPO@$REF）==="

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/new"

say "[1/4] 拉取远端 panel/ 文件…"
# 面板由 systemd 启动，环境里带 https_proxy（指向常失效的 mihomo）且可能没有 HOME，
# gh 会因此认不到凭据。这里显式取 token、清代理、固定 HOME。
export HOME=/root
GH_TOKEN=$(awk '/oauth_token:/{print $2; exit}' /root/.config/gh/hosts.yml 2>/dev/null)
if [ -z "$GH_TOKEN" ]; then say "❌ 取不到 GitHub token（/root/.config/gh/hosts.yml），已中止"; exit 2; fi
export GH_TOKEN
gnoh() { env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY "$@"; }

for f in $FILES; do
  if ! gnoh gh api "repos/$REPO/contents/panel/$f?ref=$REF" --jq '.content' 2>>"$LOG" | base64 -d > "$TMP/new/$f" 2>>"$LOG"; then
    say "❌ 拉取 $f 失败，已中止（面板未改动）"; exit 2
  fi
  if [ ! -s "$TMP/new/$f" ]; then
    say "❌ $f 内容为空，已中止（面板未改动）"; exit 2
  fi
done
say "      远端文件就绪：$(ls -1 "$TMP/new" | tr '\n' ' ')"

say "[2/4] 语法检查…"
if ! python3 -m py_compile "$TMP/new/server.py" "$TMP/new/stats.py" "$TMP/new/notify.py" 2>>"$LOG"; then
  say "❌ 新代码语法错误，已中止（面板未改动）"; exit 3
fi
if ! grep -q "镜像更新\|sec-update" "$TMP/new/index.html"; then
  say "⚠️ 新 index.html 看起来不完整，已中止（面板未改动）"; exit 3
fi
say "      语法 OK"

say "[3/4] 备份并替换…"
BAK="$DEST/backup-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BAK"
cp -a "$DEST"/server.py "$DEST"/index.html "$DEST"/update-image.sh "$DEST"/stats.py "$DEST"/notify.py "$BAK"/ 2>/dev/null
for f in $FILES; do
  install -m 644 "$TMP/new/$f" "$DEST/$f"
done
chmod +x "$DEST/update-image.sh" 2>/dev/null
say "      已备份到 $BAK"

say "[4/4] 重启面板…"
if systemctl restart ms-panel; then
  sleep 2
  if systemctl is-active --quiet ms-panel; then
    say "✅ 面板自更新完成，服务运行中"
  else
    say "⚠️ 面板重启后未变为 active，回滚中…"
    cp -a "$BAK"/* "$DEST"/ && systemctl restart ms-panel
    say "↩️ 已回滚到更新前版本"
    exit 5
  fi
else
  say "❌ 重启失败，回滚中…"
  cp -a "$BAK"/* "$DEST"/ && systemctl restart ms-panel
  say "↩️ 已回滚"
  exit 5
fi
