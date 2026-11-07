#!/usr/bin/env node
/**
 * Microsoft-Rewards-Script v5 · 单文件版（自解包内嵌运行时）
 * 由 build-single-v5.sh 生成，勿手改 payload。
 *
 * 环境变量：
 *   MSR_HOME     解包/运行目录（默认 /ql/data/msr5，非青龙环境默认 ~/.msr5）
 *   CHROME_PATH  指定 chromium 可执行文件（默认自动找 /usr/bin/chromium）
 *   MSR_WORKERS  任务开关覆盖，如 "doDesktopSearch=1,doMobileSearch=0"
 *   MSR_CLUSTERS 并发分片数
 *   ACCOUNT_N_EMAIL / ACCOUNT_N_PASSWORD / ACCOUNT_N_TOTP_SECRET  账号（照传入子进程）
 *   MSR_SELFTEST=1  只做自检：解包 + 启动浏览器访问 cn.bing.com，不执行任务
 */
'use strict'

const fs = require('fs')
const os = require('os')
const path = require('path')
const cp = require('child_process')

const PAYLOAD_HASH = '__PAYLOAD_HASH__'
const PAYLOAD_B64 = '__PAYLOAD__'

const HOME = process.env.MSR_HOME || (process.env.QL_DIR ? '/ql/data/msr5' : path.join(os.homedir(), '.msr5'))
const APP = path.join(HOME, 'app')
const STAMP = path.join(HOME, '.payload')

function log(msg) {
    console.log(`[msr5] ${msg}`)
}

function unpack() {
    let cur = ''
    try {
        cur = fs.readFileSync(STAMP, 'utf8').trim()
    } catch (e) {
        /* 首次运行 */
    }
    if (cur === PAYLOAD_HASH && fs.existsSync(path.join(APP, 'dist/index.js'))) return false
    log('解包内嵌运行时…')
    fs.rmSync(APP, { recursive: true, force: true })
    fs.mkdirSync(APP, { recursive: true })
    const tgz = path.join(HOME, '.payload.tgz')
    fs.writeFileSync(tgz, Buffer.from(PAYLOAD_B64, 'base64'))
    cp.execFileSync('tar', ['-xzf', tgz, '-C', APP], { stdio: 'inherit' })
    fs.unlinkSync(tgz)
    fs.writeFileSync(STAMP, PAYLOAD_HASH)
    log(`解包完成（${PAYLOAD_HASH.slice(0, 8)}）`)
    return true
}

function envFlags(prefix) {
    const out = {}
    for (const [k, v] of Object.entries(process.env)) {
        if (k.startsWith(prefix)) out[k.slice(prefix.length)] = v
    }
    return out
}

function truthy(v) {
    return /^(1|true|yes|on)$/i.test(String(v || ''))
}

function writeConfig() {
    const cfgDir = path.join(APP, 'config')
    const cfgFile = path.join(cfgDir, 'config.json')
    fs.mkdirSync(cfgDir, { recursive: true })

    let cfg = {}
    const example = path.join(APP, 'config.example.json')
    if (fs.existsSync(example)) cfg = JSON.parse(fs.readFileSync(example, 'utf8'))
    if (fs.existsSync(cfgFile)) {
        try {
            Object.assign(cfg, JSON.parse(fs.readFileSync(cfgFile, 'utf8')))
        } catch (e) {
            /* 损坏则用模板 */
        }
    }

    const workers = process.env.MSR_WORKERS ? envFlags('MSR_WORKERS_') : null
    if (workers && Object.keys(workers).length) {
        cfg.workers = cfg.workers || {}
        for (const [k, v] of Object.entries(workers)) cfg.workers[k] = truthy(v)
    }
    if (process.env.MSR_CLUSTERS) cfg.clusters = Number(process.env.MSR_CLUSTERS) || 1
    if (process.env.MSR_HEADLESS) cfg.headless = truthy(process.env.MSR_HEADLESS)
    else cfg.headless = true // 青龙/无显示器环境默认 headless
    if (process.env.MSR_SESSION_PATH) cfg.sessionPath = process.env.MSR_SESSION_PATH

    // MSR_WORKERS="doDesktopSearch=1,doMobileSearch=0" 这种逗号写法也支持
    if (process.env.MSR_WORKERS && process.env.MSR_WORKERS.includes('=')) {
        cfg.workers = cfg.workers || {}
        for (const pair of process.env.MSR_WORKERS.split(',')) {
            const [k, v] = pair.split('=').map(s => s.trim())
            if (k) cfg.workers[k] = truthy(v)
        }
    }

    fs.writeFileSync(cfgFile, JSON.stringify(cfg, null, 4))
    fs.writeFileSync(path.join(cfgDir, 'config.json.bak'), JSON.stringify(cfg, null, 4))
}

function selftest() {
    log('自检：启动浏览器访问 cn.bing.com')
    const script = `
    const { chromium } = require('patchright');
    (async () => {
      const b = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || '/usr/bin/chromium', args: ['--no-sandbox'] });
      const p = await b.newPage();
      await p.goto('https://cn.bing.com/', { waitUntil: 'domcontentloaded', timeout: 30000 });
      console.log('[msr5] bing title = ' + (await p.title()));
      await b.close();
    })().catch((e) => { console.error('[msr5] 自检失败: ' + e.message); process.exit(1); });
  `
    const r = cp.spawnSync(process.execPath, ['-e', script], { cwd: APP, stdio: 'inherit', env: process.env })
    process.exit(r.status === null ? 1 : r.status)
}

function main() {
    const major = Number(process.versions.node.split('.')[0])
    if (major < 24) {
        console.error(
            `[msr5] 需要 Node.js ≥ 24，当前 v${process.versions.node}。青龙请在「依赖管理 → Node.js」装 24 或改用容器版。`
        )
        process.exit(1)
    }
    const fresh = unpack()
    writeConfig()
    if (truthy(process.env.MSR_SELFTEST)) {
        selftest()
        return
    }
    if (fresh) log('首次解包完成，开始运行')
    const child = cp.spawn(process.execPath, ['dist/index.js', ...process.argv.slice(2)], {
        cwd: APP,
        stdio: 'inherit',
        env: process.env
    })
    child.on('exit', (code, signal) => {
        if (signal) {
            log(`被信号 ${signal} 终止`)
            process.exit(130)
        }
        process.exit(code === null ? 0 : code)
    })
}

main()
