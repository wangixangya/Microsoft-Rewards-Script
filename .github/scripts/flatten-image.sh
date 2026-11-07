#!/usr/bin/env bash
# flatten-image.sh —— 把镜像拍扁成单层并保留原有运行配置
#
# 为什么需要它：Dockerfile 里 rm 掉的文件只会变成白洞，底层数据仍随镜像分发，
# 体积一点不降。docker export | docker import 会丢掉 Config（ENTRYPOINT/WORKDIR/
# ENV/HEALTHCHECK/LABEL），所以这里从源镜像里读出配置，自动生成 --change 参数，
# 避免硬编码在上游改 Dockerfile 后悄悄失配。
#
# 用法: flatten-image.sh <源镜像> <目标引用> [更多目标引用...]
set -euo pipefail

SRC=${1:?用法: flatten-image.sh <源镜像> <目标引用...>}
shift
[ $# -ge 1 ] || { echo "缺少目标引用" >&2; exit 1; }

CHANGES_FILE=$(mktemp)
python3 - "$SRC" > "$CHANGES_FILE" <<'PY'
import json
import shlex
import subprocess
import sys

raw = subprocess.check_output(["docker", "image", "inspect", sys.argv[1]])
cfg = json.loads(raw)[0]["Config"]

def emit(line):
    print(line)

ep = cfg.get("Entrypoint")
if ep:
    emit("ENTRYPOINT " + json.dumps(ep))
cmd = cfg.get("Cmd")
if cmd and cmd != ep:
    emit("CMD " + json.dumps(cmd))
wd = cfg.get("WorkingDir")
if wd:
    emit("WORKDIR " + wd)
user = cfg.get("User")
if user:
    emit("USER " + user)
for kv in cfg.get("Env") or []:
    k, _, v = kv.partition("=")
    emit(f'ENV {k}="{v}"')
hc = cfg.get("Healthcheck") or {}
test = hc.get("Test") or []
if test and test[0] == "CMD":
    ns = 1_000_000_000
    emit(
        "HEALTHCHECK --interval={}s --timeout={}s --start-period={}s --retries={} CMD {}".format(
            int((hc.get("Interval") or 60 * ns) // ns),
            int((hc.get("Timeout") or 5 * ns) // ns),
            int((hc.get("StartPeriod") or 0) // ns),
            int(hc.get("Retries") or 3),
            json.dumps(test[1:]),
        )
    )
for k, v in (cfg.get("Labels") or {}).items():
    emit(f"LABEL {k}={shlex.quote(str(v))}")
for port in (cfg.get("ExposedPorts") or {}):
    emit(f"EXPOSE {port}")
PY

ARGS=()
while IFS= read -r line; do
    [ -n "$line" ] && ARGS+=(--change "$line")
done < "$CHANGES_FILE"
echo "--- 继承的运行配置 ---"
cat "$CHANGES_FILE"
echo "----------------------"
rm -f "$CHANGES_FILE"

CID=$(docker create "$SRC")
trap 'docker rm -f "$CID" >/dev/null 2>&1 || true' EXIT

PRIMARY=$1
FIRST=1
for dst in "$@"; do
    if [ "$FIRST" = "1" ]; then
        docker export "$CID" | docker import "${ARGS[@]}" - "$dst"
        FIRST=0
    else
        docker tag "$PRIMARY" "$dst"
    fi
done

docker rm -f "$CID" >/dev/null
trap - EXIT

for dst in "$@"; do
    docker image inspect "$dst" --format '{{.Id}}  {{.Size}}' | awk -v n="$dst" '{printf "%s  %s  %.1f MB\n", n, $1, $2/1024/1024}'
done
