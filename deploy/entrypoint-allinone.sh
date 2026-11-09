#!/usr/bin/env bash
# 一体化镜像入口：先拉起运行时（cron + Control API），再把面板放前台
set -uo pipefail

DATA="${PANEL_DATA:-/opt/data}"
APP=/opt/panel-app
SRC=/usr/src/microsoft-rewards-script

mkdir -p "$DATA"

# 1) 首次启动：面板代码铺到可写数据目录（升级镜像不覆盖用户 panel.conf / 历史统计）
if [ ! -f "$DATA/server.py" ]; then
    echo "[allinone] 初始化面板数据目录 $DATA"
    cp -a "$APP"/. "$DATA"/
fi

# 代码文件每次启动都从镜像刷新（数据文件不动：panel.conf / *.json / tmp）
CODE_FILES="server.py index.html notify.py stats.py rewards-center.js README.md env.example panel.conf.example recreate_ms.sh self-update.sh update-image.sh update-remote.sh"
for f in $CODE_FILES; do
    [ -f "$APP/$f" ] && cp -f "$APP/$f" "$DATA/$f"
done
for d in ql systemd; do
    [ -d "$APP/$d" ] && cp -a "$APP/$d" "$DATA/"
done

# 2) 账号清单：面板的「账号与会话」读 env.list，这里从容器环境变量生成
env | grep -E '^ACCOUNT_[0-9]+_[A-Z0-9_]+=' | sort > "$DATA/env.list" || true
[ -f "$DATA/env.list" ] && chmod 600 "$DATA/env.list"

# 3) 面板配置：API 与面板同容器，直连 127.0.0.1:3010
if [ ! -f "$DATA/panel.conf" ] || grep -q "replace-with-your-api-token" "$DATA/panel.conf"; then
    TOKEN="${API_TOKEN:-}"
    if [ -z "$TOKEN" ] && [ -f "$SRC/.env" ]; then
        TOKEN=$(grep -m1 '^API_TOKEN=' "$SRC/.env" | cut -d= -f2- || true)
    fi
    if [ -z "$TOKEN" ]; then
        echo "[allinone] 错误：需要 API_TOKEN（容器的 API 鉴权），请加 -e API_TOKEN=..." >&2
        exit 1
    fi
    umask 077
    {
        echo "API_BASE=http://127.0.0.1:${API_PORT:-3010}"
        echo "API_TOKEN=${TOKEN}"
        echo "PANEL_PASSWORD=${PANEL_PASSWORD:-admin}"
    } > "$DATA/panel.conf"
    echo "[allinone] 已生成 $DATA/panel.conf（面板端口 ${PANEL_PORT:-5310}）"
    
    # 一体化里没有独立容器可重建，默认关掉面板自带的计划任务，避免双调度
    if [ "${DISABLE_SCHEDULE:-1}" = "1" ]; then
        printf '{\n  "enabled": false,\n  "cron": "",\n  "accounts": {}\n}\n' > "$DATA/schedule.json"
        printf '{\n  "autoClaim": false,\n  "cron": "",\n  "accounts": [],\n  "lastRun": ""\n}\n' > "$DATA/rewards.json"
        echo "[allinone] 已禁用面板内置定时（运行时自己的 cron 仍在工作）"
    fi
fi

# 4) 拉起运行时（cron + API），它在后台跑并自己管理子进程
export API_MODE="${API_MODE:-true}"
export API_HOST="${API_HOST:-0.0.0.0}"
export API_PORT="${API_PORT:-3010}"
bash /usr/local/bin/entrypoint.sh &
RUNTIME_PID=$!

# 等 API 起来（401 也算起来了），最多 60s
code=000
for _ in $(seq 1 60); do
    code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${API_PORT}/" 2>/dev/null) || code=000
    [ "$code" != "000" ] && break
    sleep 1
done
echo "[allinone] 运行时已就绪（API http://127.0.0.1:${API_PORT}，HTTP $code），启动面板"

# 5) 运行时挂了就带崩容器（与运行时镜像的行为一致）
(
    while kill -0 "$RUNTIME_PID" 2>/dev/null; do sleep 10; done
    echo "[allinone] 运行时进程已退出，停止面板并结束容器" >&2
    kill -TERM 1 2>/dev/null
) &

# 6) 面板放前台
exec python3 "$DATA/server.py"
