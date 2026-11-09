#!/usr/bin/env bash
# Microsoft Rewards v5 —— 一条命令安装（运行时 + 中文面板，同一容器）
#
# 用法：
#   curl -fsSL https://cdn.jsdelivr.net/gh/wangixangya/Microsoft-Rewards-Script@v5/deploy/install.sh | bash -s -- 邮箱 密码
#
# 可选参数（环境变量）：
#   PORT=5310            面板端口
#   DIR=$PWD/ms-rewards  数据目录（config / sessions 存放处）
#   PANEL_PASSWORD=admin 面板密码
#   TZ=Asia/Shanghai     时区
#   IMAGE=...            自定义镜像
#   FORCE=1              容器已存在时强制重建
set -euo pipefail

IMAGE="${IMAGE:-docker.io/wangxiangya/ms-rewards-v5:5-cn-allinone}"
PORT="${PORT:-5310}"
DIR="${DIR:-$PWD/ms-rewards}"
PANEL_PASSWORD="${PANEL_PASSWORD:-admin}"
TZ="${TZ:-Asia/Shanghai}"
NAME="${NAME:-ms-rewards}"

say() { printf '\033[1m%s\033[0m\n' "$*"; }
die() { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

EMAIL="${1:-}"
PASSWORD="${2:-}"
[ -n "${3:-}" ] && PANEL_PASSWORD="$3"

if [ -z "$EMAIL" ] || [ -z "$PASSWORD" ]; then
    say "用法: bash install.sh <微软账号邮箱> <密码> [面板密码]"
    exit 1
fi

command -v docker >/dev/null 2>&1 || die "没装 docker，请先安装：https://docs.docker.com/engine/install/"
docker info >/dev/null 2>&1 || die "docker 没运行，或当前用户没有权限（试试 sudo）"

if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
    if [ "${FORCE:-0}" = "1" ]; then
        say "删除已存在的容器 $NAME"
        docker rm -f "$NAME" >/dev/null
    else
        die "容器 $NAME 已存在。要重建请加 FORCE=1，例如：FORCE=1 bash install.sh ..."
    fi
fi

mkdir -p "$DIR/config" "$DIR/sessions"
API_TOKEN="$( (openssl rand -hex 24 2>/dev/null) || (head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n') )"

say "① 拉取镜像 $IMAGE（约 294 MB，首次会慢一点）"
docker pull "$IMAGE" >/dev/null || die "镜像拉取失败，检查网络或改用 IMAGE=<其他镜像> 重试"

say "② 启动容器（面板端口 $PORT）"
docker run -d --name "$NAME" --restart unless-stopped \
    -p "${PORT}:5310" \
    -e TZ="$TZ" \
    -e API_TOKEN="$API_TOKEN" \
    -e PANEL_PASSWORD="$PANEL_PASSWORD" \
    -e ACCOUNT_1_EMAIL="$EMAIL" \
    -e ACCOUNT_1_PASSWORD="$PASSWORD" \
    -e ACCOUNT_1_GEO_LOCALE="cn" \
    -v "$DIR/config:/usr/src/microsoft-rewards-script/config" \
    -v "$DIR/sessions:/usr/src/microsoft-rewards-script/sessions" \
    -v "$NAME-panel:/opt/data" \
    "$IMAGE" >/dev/null || die "容器启动失败，用 docker logs $NAME 看原因"

say "③ 等待面板就绪…"
ok=0
for _ in $(seq 1 60); do
    if curl -fsS -o /dev/null "http://127.0.0.1:${PORT}/" 2>/dev/null; then ok=1; break; fi
    sleep 2
done
[ "$ok" = "1" ] || { docker logs --tail 30 "$NAME" 2>&1; die "面板没起来，日志见上"; }

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
[ -z "$IP" ] && IP="<本机IP>"
cat <<EOF

✅ 安装完成

  面板地址   http://${IP}:${PORT}
  面板密码   ${PANEL_PASSWORD}
  数据目录   ${DIR}（config / sessions）
  容器名     ${NAME}
  账号       ${EMAIL}

常用操作
  docker logs -f ${NAME}           # 看日志
  docker restart ${NAME}           # 重启
  docker rm -f ${NAME}             # 删除（数据仍在 ${DIR}）
  升级镜像：docker pull ${IMAGE} && FORCE=1 bash install.sh ...

默认每天 ${TZ} 07:00 自动跑一次；面板里可以改时间、加账号、绑代理。
EOF
