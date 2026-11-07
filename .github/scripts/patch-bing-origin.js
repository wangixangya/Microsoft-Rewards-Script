#!/usr/bin/env node
/**
 * patch-bing-origin.js —— 让 v5 在国内可用：www.bing.com 被 302 到 cn.bing.com 后，
 * 脚本里对 `origin === URLs.bing.origin` 的严格比对会全部失败（waitForURL 超时、0 分）。
 *
 * 做法（只改源码，幂等）：
 *   1) 在 src/constants/urls.ts 追加 isBingHost(origin) —— 允许任意 *.bing.com
 *   2) 把浏览器页面侧的 origin 等值/不等值比对换成 isBingHost(...)
 *   3) HTTP 客户端（BingClient）与 API URL 拼接保持 www.bing.com 不动
 *
 * 找不到预期数量的替换点就退出码 1（上游改结构时立刻暴露，别静默生成坏镜像）。
 */
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const ROOT = process.cwd()
const URLS_FILE = path.join(ROOT, 'src/constants/urls.ts')

const HELPER = `
// cn.bing.com 兼容：国内访问 www.bing.com 会被 302 到 cn.bing.com，origin 不再是 www.bing.com
export function isBingHost(origin: string): boolean {
    return /^https:\\/\\/([a-z0-9-]+\\.)*bing\\.com$/i.test(origin)
}
`

const FILES = [
    'src/rewards/browser/search/HumanTyping.ts',
    'src/rewards/browser/search/BrowserSearchOnBing.ts',
    'src/rewards/browser/search/BingSearchPage.ts',
    'src/rewards/browser/visual/VisualSearchPage.ts',
    'src/rewards/browser/actions/BrowserRewardNavigator.ts',
    'src/rewards/shared/visual/VisualSearchCandidate.ts'
]

// 形如： X.origin === URLs.bing.origin  /  new URL(page.url()).origin !== URLs.bing.origin
const CMP =
    /((?:new\s+URL\((?:[^()]|\([^()]*\))*\)|[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*|\(\))*)\.origin)\s*(===|!==)\s*URLs\.bing\.origin/g

let total = 0
const report = []

// 1) helper
let urls = fs.readFileSync(URLS_FILE, 'utf8')
if (!urls.includes('export function isBingHost')) {
    urls = urls.replace(/\s*$/, '\n') + HELPER
    fs.writeFileSync(URLS_FILE, urls)
    report.push('urls.ts: 已注入 isBingHost')
} else {
    report.push('urls.ts: isBingHost 已存在（跳过）')
}

// 2) 逐文件替换
for (const rel of FILES) {
    const file = path.join(ROOT, rel)
    if (!fs.existsSync(file)) {
        report.push(`${rel}: 文件不存在（跳过）`)
        continue
    }
    let src = fs.readFileSync(file, 'utf8')
    let n = 0
    src = src.replace(CMP, (_m, lhs, op) => {
        n++
        return op === '===' ? `isBingHost(${lhs})` : `!isBingHost(${lhs})`
    })

    if (n > 0) {
        // 补 import；若该文件已不再使用 URLs.*，把 URLs 从 import 里去掉（否则 TS6133 未使用报错）
        if (!/import\s*{[^}]*\bisBingHost\b[^}]*}\s*from\s*'[^']*constants\/urls'/.test(src)) {
            src = src.replace(
                /import\s*\{([^}]*)\}\s*from\s*'((?:\.\.\/)+constants\/urls)'/,
                (_m, names, from) => `import {${names.replace(/\s*$/, '')}, isBingHost } from '${from}'`
            )
        }
        if (!/\bURLs\s*\./.test(src)) {
            src = src.replace(/import\s*\{([^}]*)\}\s*from\s*'((?:\.\.\/)+constants\/urls)'/, (_m, names, from) => {
                const kept = names
                    .split(',')
                    .map(s => s.trim())
                    .filter(s => s && s !== 'URLs')
                if (!kept.includes('isBingHost')) kept.push('isBingHost')
                return `import { ${kept.join(', ')} } from '${from}'`
            })
        }
        fs.writeFileSync(file, src)
        total += n
        report.push(`${rel}: 替换 ${n} 处`)
    } else {
        report.push(`${rel}: 无可替换（可能已打过补丁）`)
    }
}

console.log(report.map(l => `  ${l}`).join('\n'))
console.log(`  合计替换 ${total} 处`)

if (total === 0) {
    // 已打过补丁：目标文件里不再有 origin 与 URLs.bing.origin 的比对
    const leftover = FILES.filter(rel => {
        const f = path.join(ROOT, rel)
        return fs.existsSync(f) && /\.origin\s*(===|!==)\s*URLs\.bing\.origin/.test(fs.readFileSync(f, 'utf8'))
    })
    if (leftover.length === 0) {
        console.log('  ✔ 已打过补丁（幂等跳过）')
        process.exit(0)
    }
    console.error(`❌ 仍有未替换的比对点：${leftover.join(', ')}`)
    process.exit(1)
}

if (total < 5) {
    console.error('❌ 替换点少于 5 处：上游代码结构可能已变，请人工检查后再构建，避免产出坏镜像。')
    process.exit(1)
}
