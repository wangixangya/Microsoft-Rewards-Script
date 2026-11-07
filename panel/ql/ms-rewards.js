#!/usr/bin/env node
/**
 * Microsoft Rewards · 青龙单文件版 (QingLong single-file runner)
 * ---------------------------------------------------------------
 * 复制到青龙 scripts 目录，定时任务填 `ms-rewards.js` 即可。
 * 首次运行自动：建工作区 → 拉上游源码 → 装依赖 → 下 chromium → 跑任务。
 * 之后每次运行会按间隔检查上游更新，源码变了自动重建（会话、配置、浏览器缓存都会保留）。
 *
 * 必填环境变量（青龙「环境变量」页）：
 *   ACCOUNT_1_EMAIL / ACCOUNT_1_PASSWORD [/ ACCOUNT_1_TOTP_SECRET]   ← 支持到 ACCOUNT_20_*
 * 常用可选项：
 *   MSR_HOME=/ql/data/msr        工作区（放源码/会话/浏览器缓存）
 *   MSR_AUTO_UPDATE=0            关闭在线更新，只跑本地版本
 *   MSR_CHECK_HOURS=12           每多少小时检查一次上游（默认 12）
 *   MSR_REF=v4                   上游分支/标签
 *   MSR_CLUSTERS=2               并发账号数 1-4
 *   MSR_HEADLESS=0               有头运行（青龙里请保持 1）
 *   MSR_PROXY=http://ip:port     全局代理
 *   MSR_WORKERS="doVisualSearch=0,doBonusSearches=1"   覆盖任务开关
 *   MSR_SELFTEST=1               只自检环境（装依赖 + 开浏览器 + 访问 bing），不跑任务
 *   MSR_NPM_REGISTRY=https://registry.npmmirror.com   npm 源
 */

'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const https = require('https');
const crypto = require('crypto');

const REF = process.env.MSR_REF || 'v4';
const HOME = process.env.MSR_HOME || '/ql/data/msr';
const SRC = path.join(HOME, 'upstream');
const STATE = path.join(HOME, 'state.json');
const RUNTIME = path.join(HOME, 'runtime');
const CONFIG_DIR = path.join(HOME, 'config');
const SESSIONS = path.join(HOME, 'sessions');
const AUTO_UPDATE = process.env.MSR_AUTO_UPDATE !== '0';
const CHECK_HOURS = Number(process.env.MSR_CHECK_HOURS || 12);
const REGISTRY = process.env.MSR_NPM_REGISTRY || 'https://registry.npmmirror.com';
const TARBALL = `https://codeload.github.com/TheNetsky/Microsoft-Rewards-Script/tar.gz/refs/heads/${REF}`;
const MIRRORS = [TARBALL, `https://ghfast.top/${TARBALL}`, `https://ghproxy.net/${TARBALL}`];

const log = (...a) => console.log('[msr]', ...a);
const warn = (...a) => console.warn('[msr][warn]', ...a);
const die = m => { console.error('[msr][error]', m); process.exit(1); };
const readJson = (p, d) => { try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch { return d; } };
function writeJson(p, o) {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(o, null, 4));
}

/* ---------- 下载 ---------- */
function download(url, dest, redirect = 0) {
  return new Promise((resolve, reject) => {
    if (redirect > 5) return reject(new Error('too many redirects'));
    const req = https.get(url, { headers: { 'User-Agent': 'msr-ql/1.0' }, timeout: 120000 }, res => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        res.resume();
        return download(res.headers.location, dest, redirect + 1).then(resolve, reject);
      }
      if (res.statusCode !== 200) { res.resume(); return reject(new Error('HTTP ' + res.statusCode)); }
      const total = Number(res.headers['content-length'] || 0);
      let got = 0, mark = -10;
      const out = fs.createWriteStream(dest);
      res.on('data', c => {
        got += c.length;
        const pct = total ? Math.floor(got / total * 100) : -1;
        if (pct >= 0 && pct - mark >= 25) { mark = pct; log(`  下载 ${pct}% (${(got / 1048576).toFixed(1)}MB)`); }
      });
      res.pipe(out);
      out.on('finish', () => out.close(() => resolve(got)));
      out.on('error', reject);
    });
    req.on('timeout', () => req.destroy(new Error('timeout')));
    req.on('error', reject);
  });
}

async function fetchTarball() {
  const tmp = path.join(HOME, `upstream-${Date.now()}.tar.gz`);
  for (const url of MIRRORS) {
    try {
      log(`拉取源码 ← ${url.split('/')[2]}`);
      const t0 = Date.now();
      const size = await download(url, tmp);
      log(`  完成 ${(size / 1048576).toFixed(1)}MB / ${((Date.now() - t0) / 1000).toFixed(0)}s`);
      return tmp;
    } catch (e) { warn(`  失败(${url.split('/')[2]}): ${e.message}`); }
  }
  throw new Error('所有下载源都失败');
}

function extract(tar, dest) {
  fs.rmSync(dest, { recursive: true, force: true });
  fs.mkdirSync(dest, { recursive: true });
  const r = spawnSync('tar', ['-xzf', tar, '-C', dest, '--strip-components=1'], { stdio: 'inherit' });
  if (r.status !== 0) throw new Error('tar 解压失败');
}

/* ---------- 依赖与构建 ---------- */
function run(cmd, args, opts = {}) {
  log(`$ ${cmd} ${args.join(' ')}`);
  const r = spawnSync(cmd, args, { stdio: 'inherit', ...opts });
  if (r.status !== 0) throw new Error(`${cmd} 退出码 ${r.status}`);
}

/** 找到系统 chromium：青龙 Alpine 版自带的 /usr/bin/chromium 就能用，省 270MB 下载 */
function detectSystemChromium() {
  if (process.env.MSR_CHROMIUM_PATH) return process.env.MSR_CHROMIUM_PATH;
  for (const p of ['/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/chrome', '/usr/bin/google-chrome']) {
    try { if (fs.existsSync(p)) return p; } catch {}
  }
  return null;
}

/** 把 dist 里的 launch() 指到系统 chromium（幂等，重复执行不会叠加） */
function patchChromiumPath(bin) {
  const file = path.join(SRC, 'dist', 'browser', 'Browser.js');
  if (!fs.existsSync(file)) return;
  let src = fs.readFileSync(file, 'utf8');
  if (src.includes('MSR_CHROMIUM_PATH')) { patchLogCount++; return; }
  const before = src;
  src = src.replace(/\.chromium\.launch\(\{/g,
    '.chromium.launch({ executablePath: process.env.MSR_CHROMIUM_PATH || undefined,');
  if (src !== before) {
    fs.writeFileSync(file, src);
    log(`已让浏览器使用系统 chromium：${bin}`);
  }
}
let patchLogCount = 0;

function ensureBuild(force) {
  const nm = path.join(SRC, 'node_modules');
  const dist = path.join(SRC, 'dist', 'index.js');
  const browsers = path.join(RUNTIME, 'browsers');
  fs.mkdirSync(browsers, { recursive: true });
  if (force || !fs.existsSync(nm)) {
    run('npm', ['ci', '--no-audit', '--no-fund', `--registry=${REGISTRY}`], {
      cwd: SRC,
      // 让 lock 里的 registry.npmjs.org 也走镜像，否则国内会很慢
      env: { ...process.env, NPM_CONFIG_REPLACE_REGISTRY_HOST: 'always', NPM_CONFIG_REGISTRY: REGISTRY },
    });
  }
  const sysChrome = detectSystemChromium();
  if (sysChrome) {
    log(`使用系统 chromium：${sysChrome}（跳过下载，省 ~270MB）`);
    process.env.MSR_CHROMIUM_PATH = sysChrome;
    if (!fs.existsSync(dist)) run('npm', ['run', 'build'], { cwd: SRC });
    patchChromiumPath(sysChrome);
    return;
  }
  const hasBrowser = fs.existsSync(browsers) && fs.readdirSync(browsers).length > 0;
  if (!hasBrowser) {
    run('npx', ['--yes', 'patchright', 'install', 'chromium'], {
      cwd: SRC, env: { ...process.env, PLAYWRIGHT_BROWSERS_PATH: browsers },
    });
  }
  if (force || !fs.existsSync(dist)) {
    run('npm', ['run', 'build'], { cwd: SRC });
  }
}

/* ---------- 账号与配置 ---------- */
function collectAccounts() {
  const out = [];
  for (let i = 1; i <= 20; i++) {
    const email = process.env[`ACCOUNT_${i}_EMAIL`];
    const password = process.env[`ACCOUNT_${i}_PASSWORD`] || process.env[`ACCOUNT_${i}_PASSWD`];
    if (email && password) out.push(`${email} (账号${i})`);
  }
  const extra = (process.env.MSR_ACCOUNTS || '').split('|').filter(Boolean);
  return { envCount: out.length + extra.length, names: out };
}

function buildConfig(envCount) {
  const cur = readJson(path.join(SRC, 'config.json'), readJson(path.join(CONFIG_DIR, 'config.json'), {}));
  const workers = { ...(cur.workers || {}) };
  for (const kv of (process.env.MSR_WORKERS || '').split(',')) {
    const [k, v] = kv.split('=').map(s => (s || '').trim());
    if (k && v !== undefined) workers[k] = v === '1' || v === 'true';
  }
  const cfg = {
    ...cur,
    sessionPath: SESSIONS,
    headless: (process.env.MSR_HEADLESS ?? '1') !== '0',
    clusters: Math.min(4, Math.max(1, Number(process.env.MSR_CLUSTERS || 1))),
    accountDelay: cur.accountDelay || { min: 1, max: 3 },
  };
  if (Object.keys(workers).length) cfg.workers = workers;
  if (process.env.MSR_PROXY) cfg.proxy = { ...(cfg.proxy || {}), url: process.env.MSR_PROXY };
  fs.mkdirSync(CONFIG_DIR, { recursive: true });
  // v4.x 只从项目根/dist/src 找 config.json，所以主写入位置是 upstream/config.json
  const target = path.join(SRC, 'config.json');
  if (fs.existsSync(target)) fs.copyFileSync(target, path.join(CONFIG_DIR, 'config.json.bak'));
  writeJson(target, cfg);
  writeJson(path.join(CONFIG_DIR, 'config.json'), cfg);  // 快照，方便面板/备份查看
  log(`配置已写入 ${target}（账号 ${envCount} 个走环境变量，不落盘密码）`);
}

/* ---------- 自检 ---------- */
function selftest() {
  log('自检：启动 chromium 访问 cn.bing.com');
  const tmp = path.join(SRC, '.selftest.js');
  fs.writeFileSync(tmp, `
const { chromium } = require('patchright');
(async () => {
  const b = await chromium.launch({ headless: true, executablePath: process.env.MSR_CHROMIUM_PATH || undefined, args: ['--no-sandbox'] });
  const p = await b.newPage();
  await p.goto('https://cn.bing.com/', { waitUntil: 'domcontentloaded', timeout: 60000 });
  console.log('[msr] bing title =', (await p.title()).slice(0, 60));
  await b.close();
})().catch(e => { console.error('[msr][error]', e.message.split('\\n')[0]); process.exit(1); });`);
  const r = spawnSync('node', [tmp], {
    cwd: SRC, stdio: 'inherit',
    env: { ...process.env, PLAYWRIGHT_BROWSERS_PATH: path.join(RUNTIME, 'browsers') },
  });
  fs.rmSync(tmp, { force: true });
  if (r.status !== 0) throw new Error('浏览器自检失败');
  log('自检通过 ✔');
}

/* ---------- 主流程 ---------- */
async function main() {
  for (const d of [HOME, CONFIG_DIR, SESSIONS, RUNTIME]) fs.mkdirSync(d, { recursive: true });

  const state = readJson(STATE, { version: null, hash: null, lastCheck: 0 });
  const acc = collectAccounts();
  if (!acc.envCount) die('没有账号：请配置环境变量 ACCOUNT_1_EMAIL / ACCOUNT_1_PASSWORD');

  const needCheck = AUTO_UPDATE &&
    (Date.now() - (state.lastCheck || 0) > CHECK_HOURS * 3600e3 || !fs.existsSync(path.join(SRC, 'package.json')));

  if (needCheck) {
    log(`检查上游更新（${REF}，每 ${CHECK_HOURS}h）`);
    let changed = false;
    try {
      const tar = await fetchTarball();
      const probe = path.join(HOME, '.probe');
      extract(tar, probe);
      const pkg = readJson(path.join(probe, 'package.json'), {});
      const h = crypto.createHash('sha1');
      for (const f of ['package.json', 'package-lock.json', 'src/index.ts']) {
        const p = path.join(probe, f);
        if (fs.existsSync(p)) h.update(fs.readFileSync(p));
      }
      const hash = h.digest('hex');
      changed = hash !== state.hash;
      log(`  本地 ${state.version || '-'} / 远端 ${pkg.version || '?'} → ${changed ? '有更新，准备重建' : '已是最新'}`);
      if (changed) {
        fs.rmSync(SRC, { recursive: true, force: true });
        fs.renameSync(probe, SRC);
      } else fs.rmSync(probe, { recursive: true, force: true });
      fs.rmSync(tar, { force: true });
      Object.assign(state, { version: pkg.version || state.version, hash, lastCheck: Date.now() });
      writeJson(STATE, state);
    } catch (e) {
      warn(`更新检查失败：${e.message}（继续用本地版本）`);
    }
    if (!fs.existsSync(path.join(SRC, 'package.json'))) die('没有本地源码且下载失败');
    ensureBuild(changed);
  } else {
    ensureBuild(false);
  }

  if (process.env.MSR_SELFTEST === '1') return selftest();

  buildConfig(acc.envCount);
  const ver = readJson(path.join(SRC, 'package.json'), {}).version || '?';
  log(`开始运行 · v${ver} · ${acc.envCount} 个账号 · 并发 ${process.env.MSR_CLUSTERS || 1}`);
  const r = spawnSync('node', ['dist/index.js'], {
    cwd: SRC, stdio: 'inherit',
    env: { ...process.env, PLAYWRIGHT_BROWSERS_PATH: path.join(RUNTIME, 'browsers') },
  });
  if (r.status !== 0) die(`任务退出码 ${r.status}`);
  log('任务结束 ✔');
}

main().catch(e => die(e && e.stack ? e.stack : String(e)));
