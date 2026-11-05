#!/bin/bash
# 重建 Microsoft Rewards 容器
#   默认：API 模式容器 ms-rewards-api（配合 panel/ Web 控制台）
#   回滚：加 --legacy 重建旧的 cron-only 容器 microsoft-rewards-script
# 用法:
#   bash recreate_ms.sh [镜像tag]
#   bash recreate_ms.sh [镜像tag] --legacy
# 可用环境变量覆盖：PANEL_DIR / ENV_FILE / PANEL_CONF / CFG_VOL / SES_VOL / API_PORT
set -e

IMAGE="${1:-wangixangya/microsoft-rewards-script:v4.3.3}"
MODE=api
[ "${2:-}" = "--legacy" ] && MODE=legacy

PANEL_DIR="${PANEL_DIR:-/root/ms-panel}"
CFG_VOL="${CFG_VOL:-/root/microsoft-rewards-script/config}"
SES_VOL="${SES_VOL:-/root/microsoft-rewards-script/sessions}"
ENV_FILE="${ENV_FILE:-$PANEL_DIR/env.list}"
PANEL_CONF="${PANEL_CONF:-$PANEL_DIR/panel.conf}"
API_PORT="${API_PORT:-3010}"

if [ "$MODE" = "legacy" ]; then
  docker stop microsoft-rewards-script 2>/dev/null || true
  docker rm microsoft-rewards-script 2>/dev/null || true
  docker run -d \
    --name microsoft-rewards-script \
    --network microsoft-rewards-script_default \
    --restart unless-stopped \
    -v "$CFG_VOL":/usr/src/microsoft-rewards-script/config \
    -v "$SES_VOL":/usr/src/microsoft-rewards-script/sessions \
    -e TZ=Asia/Shanghai -e NODE_ENV=production \
    -e CRON_SCHEDULE="0 7 * * *" -e RUN_ON_START=false -e SKIP_RANDOM_SLEEP=false \
    -e CONFIG_AUTO_SYNC=true \
    -e NODE_OPTIONS="--disable-warning=ExperimentalWarning" \
    --env-file "$ENV_FILE" \
    "$IMAGE"
  echo "已重建【legacy cron 容器】镜像: $IMAGE"
  sleep 6
  docker ps --filter name=microsoft-rewards-script --format "{{.Names}} | {{.Status}} | {{.Image}}"
  exit 0
fi

# ---- API 模式（面板后端）----
[ -f "$PANEL_CONF" ] || { echo "ERROR: 缺少 $PANEL_CONF"; exit 1; }
[ -f "$ENV_FILE" ] || { echo "ERROR: 缺少 $ENV_FILE"; exit 1; }
# shellcheck disable=SC1090
API_TOKEN=$(grep '^API_TOKEN=' "$PANEL_CONF" | cut -d= -f2-)
[ -n "$API_TOKEN" ] || { echo "ERROR: panel.conf 里没有 API_TOKEN"; exit 1; }

# 同一批 config/sessions 卷不能有两个容器同时跑
docker stop microsoft-rewards-script 2>/dev/null || true

docker stop ms-rewards-api 2>/dev/null || true
docker rm ms-rewards-api 2>/dev/null || true

docker run -d \
  --name ms-rewards-api \
  --restart unless-stopped \
  -p 127.0.0.1:"$API_PORT":3010 \
  --env-file "$ENV_FILE" \
  -e API_MODE=true -e API_PORT=3010 -e API_HOST=0.0.0.0 -e CRON_SCHEDULE= \
  -e API_TOKEN="$API_TOKEN" \
  -e API_ALLOW_CONFIG_WRITE=true -e API_ALLOW_CONFIG_REVEAL=true \
  -e API_RUN_HISTORY=50 -e API_LOG_BUFFER=4000 \
  -v "$CFG_VOL":/usr/src/microsoft-rewards-script/config \
  -v "$SES_VOL":/usr/src/microsoft-rewards-script/sessions \
  "$IMAGE" >/dev/null

echo "已重建【API 模式容器】，镜像: $IMAGE"

for i in $(seq 1 30); do
  if docker logs ms-rewards-api 2>&1 | grep -q "__API_READY__"; then break; fi
  sleep 1
done

code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $API_TOKEN" "http://127.0.0.1:$API_PORT/status" || true)
echo "API /status → HTTP $code"
systemctl is-active ms-panel >/dev/null 2>&1 && echo "面板: running" || echo "面板: 未运行（systemctl start ms-panel）"
docker ps --filter name=ms-rewards-api --format "{{.Names}} | {{.Status}} | {{.Image}}"
[ "$code" = "200" ] || { echo "⚠️ API 未就绪，检查 docker logs ms-rewards-api"; exit 2; }
