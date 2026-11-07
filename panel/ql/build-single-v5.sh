#!/bin/bash
# build-single-v5.sh — 把 v5 源码打成「单文件」自解包 JS（内嵌 dist + node_modules）
# 用法: build-single-v5.sh [输出路径]
#  1) 从 /root/repos/ms-rewards-v5 暂存源码
#  2) npm ci（含 dev，tsc 需要）→ npm run build → npm prune --omit=dev
#  3) 补 musl 版 impit（Alpine 青龙用）
#  4) 给 dist/browser/BrowserManager.js 的 launch 加 executablePath（用系统 chromium）
#  5) tar cz → base64 内嵌到模板 → node --check
# 输出末行: RESULT out=<路径> size=<字节> hash=<payload sha1>
set -euo pipefail
OUT="${1:-/root/ms-panel/ql/ms-rewards-single-v5.js}"
SRC=/root/repos/ms-rewards-v5
STAGE=/tmp/msr5-single-stage
APP=$STAGE/app
PAY=$STAGE/payload.tgz
TPL=/root/ms-panel/ql/template-single-v5.js

echo "[1/6] 暂存 v5 源码"
rm -rf "$STAGE"; mkdir -p "$APP"
cd "$SRC"
cp -r src scripts tsconfig.json package.json package-lock.json "$APP"/
[ -d assets ] && cp -r assets "$APP"/
[ -f config.example.json ] && cp config.example.json "$APP"/

echo "[2/6] 安装依赖并编译（npm ci → tsc）"
cd "$APP"
env -u http_proxy -u https_proxy -u all_proxy npm ci --no-audit --no-fund \
  --registry=https://registry.npmmirror.com >/dev/null 2>&1
env -u http_proxy -u https_proxy -u all_proxy npm run build >/dev/null 2>&1
[ -f dist/index.js ] || { echo "❌ 编译失败：dist/index.js 不存在"; exit 1; }
env -u http_proxy -u https_proxy -u all_proxy npm prune --omit=dev >/dev/null 2>&1
rm -rf src tsconfig.json
echo "      dist $(du -sh dist | cut -f1) · node_modules $(du -sh node_modules | cut -f1)"

echo "[3/6] 补 musl 版 impit"
MUSL_VER=$(python3 -c "import json;print(json.load(open('node_modules/impit/package.json'))['optionalDependencies']['impit-linux-x64-musl'])")
env -u http_proxy -u https_proxy -u all_proxy curl -sL -m 120 \
  "https://registry.npmmirror.com/impit-linux-x64-musl/-/impit-linux-x64-musl-$MUSL_VER.tgz" -o "$STAGE/musl.tgz"
mkdir -p node_modules/impit-linux-x64-musl
tar -xzf "$STAGE/musl.tgz" -C node_modules/impit-linux-x64-musl --strip-components=1
rm -f "$STAGE/musl.tgz"
echo "      impit-linux-x64-musl@$MUSL_VER"

echo "[4/6] 浏览器改为系统 chromium（Alpine/Debian 通用）"
python3 - "$APP/dist/browser/BrowserManager.js" <<'PY'
import sys, pathlib
p = pathlib.Path(sys.argv[1]); s = p.read_text()
old = "chromium.launch({\n                    headless: runtime.headless,"
new = ("chromium.launch({\n"
       "                    headless: runtime.headless,\n"
       "                    executablePath: (() => { const fs = require('fs');"
       " return process.env.CHROME_PATH || ['/usr/bin/chromium','/usr/bin/chromium-browser','/usr/bin/google-chrome-stable','/usr/bin/google-chrome']"
       ".find((p) => fs.existsSync(p)); })(),")
if old not in s:
    sys.exit("❌ 未找到 launch 调用点，源码结构可能变了：" + sys.argv[1])
p.write_text(s.replace(old, new, 1))
print("      patched BrowserManager.js")
PY

echo "[5/6] 打包内嵌 payload"
tar czf "$PAY" -C "$APP" .
SIZE=$(stat -c%s "$PAY"); HASH=$(sha1sum "$PAY" | cut -d' ' -f1)
echo "      ${SIZE} 字节 ($(awk "BEGIN{printf \"%.1f\", $SIZE/1048576}") MB) · sha1=$HASH"

echo "[6/6] 生成单文件并校验"
python3 - "$PAY" "$HASH" "$OUT" "$TPL" <<'PY'
import base64, sys, pathlib
pay, h, out, tpl = sys.argv[1:5]
t = pathlib.Path(tpl).read_text(encoding='utf-8')
b64 = base64.b64encode(pathlib.Path(pay).read_bytes()).decode()
assert '__PAYLOAD__' in t and '__PAYLOAD_HASH__' in t
res = t.replace('__PAYLOAD_HASH__', h).replace('__PAYLOAD__', b64)
pathlib.Path(out).write_text(res, encoding='utf-8')
print(f"      {out}  {len(res)} 字节 ({len(res)/1048576:.1f} MB)")
PY
node --check "$OUT"
rm -rf "$STAGE"
echo "RESULT out=$OUT size=$(stat -c%s "$OUT") hash=$HASH"
