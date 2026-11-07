#!/bin/bash
# ms-sync-publish.sh — 仓库同步后的「分发」阶段：更新 Web 面板 + 重建 JS 单文件版本
#  1) 面板：比对 /root/repos/ms-rewards/panel/* 与 /root/ms-panel/*，有差异就备份+替换+语法检查+重启服务
#  2) JS  ：build-single-v5.sh 重建 v5 单文件（payload 变了才动），变了就传到 GitHub Release ql-single-v5
# 用法: ms-sync-publish.sh [--panel-only|--js-only]
# 退出码 0=正常（无论有没有变化）；stdout 只在有变化时输出一行，方便 cron 静默
set -uo pipefail
LOG=/root/.hermes/logs/ms-sync-publish.log
REPO=/root/repos/ms-rewards
PANEL=/root/ms-panel
QL=$PANEL/ql
HASHFILE=$QL/.single-v5-hash
OUT=$QL/ms-rewards-single-v5.js
REPO_SLUG=wangixangya/Microsoft-Rewards-Script
REL_TAG=ql-single-v5
TS=$(date '+%Y-%m-%d %H:%M:%S')
say() { echo "[$TS] $*" >> "$LOG"; }
mkdir -p /root/.hermes/logs
unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY

MODE="${1:-all}"
MSGS=()

# ---------- 1. 面板 ----------
deploy_panel() {
  local changed=0
  for f in server.py stats.py notify.py index.html rewards-center.js; do
    [ -f "$REPO/panel/$f" ] || continue
    if ! cmp -s "$REPO/panel/$f" "$PANEL/$f"; then
      cp "$PANEL/$f" "$PANEL/$f.bak.$(date +%s)" 2>/dev/null
      cp "$REPO/panel/$f" "$PANEL/$f"
      say "面板文件更新: $f"
      changed=1
    fi
  done
  [ "$changed" = "1" ] || return 0

  if ! python3 -m py_compile "$PANEL/server.py" 2>>"$LOG"; then
    say "❌ server.py 语法错误，回滚"
    local b; b=$(ls -t "$PANEL"/server.py.bak.* 2>/dev/null | head -1)
    [ -n "$b" ] && cp "$b" "$PANEL/server.py"
    MSGS+=("⚠️ 面板更新失败（server.py 语法错误），已回滚")
    return 1
  fi
  if node --check "$PANEL/rewards-center.js" 2>>"$LOG"; then :; else
    say "❌ rewards-center.js 语法错误，回滚"
    local b; b=$(ls -t "$PANEL"/rewards-center.js.bak.* 2>/dev/null | head -1)
    [ -n "$b" ] && cp "$b" "$PANEL/rewards-center.js"
    MSGS+=("⚠️ 面板更新失败（rewards-center.js 语法错误），已回滚")
    return 1
  fi

  systemctl restart ms-panel >>"$LOG" 2>&1
  sleep 3
  local code; code=$(curl -s -o /dev/null -w '%{http_code}' -m 8 http://127.0.0.1:5310/login)
  say "面板已重启，/login = $code"
  if [ "$code" = "200" ]; then
    MSGS+=("面板已更新并重启（$code）")
  else
    MSGS+=("⚠️ 面板已更新但自检异常（/login=$code）")
  fi
}

# ---------- 2. JS 单文件 ----------
build_js() {
  local out hash
  out=$(bash "$QL/build-single-v5.sh" "$OUT" 2>>"$LOG" | tail -1)
  hash=$(echo "$out" | sed -n 's/.*hash=\([0-9a-f]*\).*/\1/p')
  [ -n "$hash" ] || { say "❌ 单文件构建失败"; MSGS+=("⚠️ JS 单文件构建失败，见 $LOG"); return 1; }
  local old=""; [ -f "$HASHFILE" ] && old=$(cat "$HASHFILE")
  local size; size=$(stat -c%s "$OUT")
  if [ "$hash" = "$old" ]; then
    say "JS 单文件无变化（$hash）"
    return 0
  fi
  say "JS 单文件更新: $hash（$(awk "BEGIN{printf \"%.1f\", $size/1048576}") MB）"

  local TOKEN; TOKEN=$(awk -F'oauth_token: ' '/oauth_token: /{print $2; exit}' ~/.config/gh/hosts.yml | tr -d ' \r')
  [ -n "$TOKEN" ] || { MSGS+=("⚠️ JS 已构建但无 GitHub token，未上传"); return 1; }
  export GH_TOKEN="$TOKEN"

  gh release view "$REL_TAG" --repo "$REPO_SLUG" >/dev/null 2>&1 || \
    gh release create "$REL_TAG" --repo "$REPO_SLUG" \
      --title "Microsoft Rewards v5 单文件版" \
      --notes "v5 自解包单文件（内嵌 dist + node_modules + 双 libc impit，使用系统 chromium）。由同步任务自动重建。" \
      >>"$LOG" 2>&1
  if gh release upload "$REL_TAG" "$OUT" --repo "$REPO_SLUG" --clobber >>"$LOG" 2>&1; then
    echo "$hash" > "$HASHFILE"
    say "已上传 Release $REL_TAG"
    MSGS+=("JS 单文件已更新并上传 Release $REL_TAG")
  else
    MSGS+=("⚠️ JS 已构建但上传 Release 失败")
    return 1
  fi
}

case "$MODE" in
  --panel-only) deploy_panel ;;
  --js-only)    build_js ;;
  *)            deploy_panel; build_js ;;
esac

say "=== 分发完成（$(printf '%s; ' "${MSGS[@]:-无变化}")）==="
[ ${#MSGS[@]} -gt 0 ] && printf '%s\n' "${MSGS[@]}"
exit 0
