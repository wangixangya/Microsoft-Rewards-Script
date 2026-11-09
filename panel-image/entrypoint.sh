#!/bin/sh
# 面板容器入口：首次启动把代码铺到可写数据目录，并用环境变量生成 panel.conf
set -eu

DATA="${PANEL_DATA:-/opt/data}"
APP=/opt/panel-app

mkdir -p "$DATA"

# 首次启动：把只读代码复制到数据目录（之后升级镜像不会覆盖用户的 panel.conf / state.json）
if [ ! -f "$DATA/server.py" ]; then
    echo "[entrypoint] 初始化数据目录 $DATA"
    cp -a "$APP"/. "$DATA"/
fi

# 生成 panel.conf：环境变量优先，其次保留已有文件
if [ ! -f "$DATA/panel.conf" ]; then
    if [ -z "${API_TOKEN:-}" ]; then
        echo "[entrypoint] 错误：缺少 API_TOKEN（容器内 API 的鉴权 token，见运行容器的 .env）" >&2
        exit 1
    fi
    umask 077
    {
        echo "API_BASE=${API_BASE:-http://127.0.0.1:3010}"
        echo "API_TOKEN=${API_TOKEN}"
        echo "PANEL_PASSWORD=${PANEL_PASSWORD:-admin}"
        [ -n "${RECREATE_SCRIPT:-}" ] && echo "RECREATE_SCRIPT=${RECREATE_SCRIPT}"
        [ -n "${IMAGE:-}" ] && echo "IMAGE=${IMAGE}"
    } > "$DATA/panel.conf"
    echo "[entrypoint] 已生成 $DATA/panel.conf（API_BASE=${API_BASE:-http://127.0.0.1:3010}）"
    HAVE_CONF=1
else
    HAVE_CONF=0
fi

# 校验 API_TOKEN 是否还是模板值
if grep -q "replace-with-your-api-token" "$DATA/panel.conf" 2>/dev/null; then
    echo "[entrypoint] 错误：panel.conf 里的 API_TOKEN 还是模板值，请设置 API_TOKEN 环境变量或直接改文件" >&2
    exit 1
fi

# 首次初始化时按需禁用内置计划任务（调试 / 多实例场景，避免抢跑）
if [ "${DISABLE_SCHEDULE:-0}" = "1" ] && [ "${HAVE_CONF:-0}" = "1" ]; then
    printf '{\n  "enabled": false,\n  "cron": "",\n  "accounts": {}\n}\n' > "$DATA/schedule.json"
    printf '{\n  "autoClaim": false,\n  "cron": "",\n  "accounts": [],\n  "lastRun": ""\n}\n' > "$DATA/rewards.json"
    echo "[entrypoint] 已禁用内置计划任务 (DISABLE_SCHEDULE=1)"
fi

exec python3 "$DATA/server.py"