#!/bin/bash
# 面板「远程更新」执行器：重建派生镜像 → 重建容器
# 用法: bash /root/ms-panel/update-image.sh
# 日志: /tmp/ms-update.log（面板从该文件读进度）
set -uo pipefail
LOG=/tmp/ms-update.log
IMG=ms-rewards:v5-cn
ts() { date '+%H:%M:%S'; }
# 注意：整个脚本 stdout 已被面板重定向到 $LOG，这里只写文件，避免 tee 造成重复行
say() { echo "[$(ts)] $*" >> "$LOG"; }

: > "$LOG"
say "=== 开始更新（镜像 $IMG）==="

say "[1/3] 拉取官方基础镜像…"
if docker pull -q ghcr.io/thenetsky/microsoft-rewards-script:5 >>"$LOG" 2>&1; then
  say "      基础镜像就绪"
else
  say "❌ 基础镜像拉取失败（网络？），已中止，容器未动"
  exit 2
fi

say "[2/3] 重建派生镜像（cn.bing.com 补丁 + 瘦身 + 拍扁）…"
if bash /root/ms-v5-cn/build.sh >>"$LOG" 2>&1; then
  say "      镜像重建完成"
else
  say "❌ 镜像构建失败，已中止，容器未动（旧镜像仍在）"
  exit 3
fi

say "[3/3] 重建容器并等待 API 就绪…"
if bash /root/recreate_ms.sh "$IMG" >>"$LOG" 2>&1; then
  say "✅ 更新完成，容器已切到新镜像"
else
  say "⚠️ 容器重建失败，请检查上方日志"
  exit 4
fi
