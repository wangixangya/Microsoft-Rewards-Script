#!/usr/bin/env bash
# 用 GitHub Actions 产出的 :5-cn 镜像重建容器（不重新打补丁/不瘦身，约 1.3GB）
# 用法: update-remote.sh [--no-recreate]
set -uo pipefail
# systemd 服务里 HOME 可能不是 /root，docker 找不到 ghcr 凭据 → 显式指定
export HOME=/root
export DOCKER_CONFIG=/root/.docker

SRC="${SRC:-ghcr.io/wangixangya/microsoft-rewards-script:5-cn}"
TAG="${TAG:-ms-rewards:v5-ci}"
LOG=/root/.hermes/logs/ms-remote-image.log
NO_RECREATE="${1:-}"

mkdir -p "$(dirname "$LOG")"
: > "$LOG"
say() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }

say "=== 用远端镜像重建（$SRC → $TAG）==="
if ! docker pull "$SRC" >> "$LOG" 2>&1; then
  say "拉取失败（检查 docker login ghcr.io 与网络）"
  exit 1
fi
docker tag "$SRC" "$TAG" >> "$LOG" 2>&1 || { say "打标签失败"; exit 1; }
say "镜像就绪：$TAG（$(docker image inspect "$TAG" --format '{{.Size}}' 2>/dev/null | awk '{printf "%.0f MB", $1/1048576}')）"

if [ "$NO_RECREATE" = "--no-recreate" ]; then
  say "仅拉取模式，不动容器"
  exit 0
fi

say "重建容器（ms-rewards-api）"
if bash /root/recreate_ms.sh "$TAG" >> "$LOG" 2>&1; then
  say "=== 完成，当前运行镜像 $TAG ==="
else
  say "重建失败，容器可能仍在旧镜像上，见上方日志"
  exit 1
fi
