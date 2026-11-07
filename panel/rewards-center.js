// Microsoft Rewards 奖励中心：读取积分/连胜/邀请/可领取，并可选自动领取
// 用法: node rewards-center.js /tmp/cookies.json [--claim] [--json]
const { chromium } = require('/usr/src/microsoft-rewards-script/node_modules/patchright-core');
const fs = require('fs');

const num = s => parseInt(String(s || '0').replace(/[^\d]/g, ''), 10) || 0;

(async () => {
  const cookieFile = process.argv[2];
  const doClaim = process.argv.includes('--claim');
  const cookies = JSON.parse(fs.readFileSync(cookieFile, 'utf8'));
  const out = { ok: false, points: null, claimable: 0, todayPoints: null, dailyStreak: null,
                streaks: [], upgrade: null, tasks: [], stamps: null,
                refer: { invites: null, earned: null, pending: null }, claimed: [], errors: [] };

  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  try {
    const ctx = await browser.newContext({ locale: 'zh-CN', userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0' });
    await ctx.addCookies(cookies);
    const page = await ctx.newPage();

    // ---- 首页：可用积分 / 可领取 ----
    await page.goto('https://rewards.bing.com/dashboard', { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForTimeout(6000);
    const dash = (await page.evaluate(() => document.body.innerText)) || '';
    let m = dash.match(/可用积分\s*[\n\s]*([\d,]+)/);
    if (m) out.points = num(m[1]);
    m = dash.match(/可领取\s*[\n\s]*([\d,]+)/);
    if (m) out.claimable = num(m[1]);
    if (out.points === null) {   // 兜底：页头积分
      m = dash.match(/([\d,]{2,})\s*积分/);
      if (m) out.points = num(m[1]);
    }

    // ---- 积分赚取页：今日积分 / 连胜 / 升级活动 / 任务 ----
    await page.goto('https://rewards.bing.com/earn', { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForTimeout(6000);
    const earn = (await page.evaluate(() => document.body.innerText)) || '';
    m = earn.match(/今日积分\s*[\n\s]*([\d,]+)/);       if (m) out.todayPoints = num(m[1]);
    m = earn.match(/每日连续打卡\s*[\n\s]*([\d,]+)/);   if (m) out.dailyStreak = num(m[1]);
    m = earn.match(/(\d+)\s*\/\s*12/);                 if (m) out.stamps = num(m[1]);

    // 三个连胜任务：名称 + 已完成连续打卡 X 天，共 7 天 + 下一档奖励
    const streakNames = ['必应搜索连续打卡', '每日连续打卡活动', '必应应用连续打卡'];
    for (const name of streakNames) {
      const re = new RegExp(name + '\\s*\\n([\\s\\S]{0,180}?)(?=\\n(?:必应搜索连续打卡|每日连续打卡活动|必应应用连续打卡|升级活动|任务|日常任务|Microsoft Rewards)|$)');
      const mm = earn.match(re);
      if (!mm) continue;
      const block = mm[1];
      const d = block.match(/已完成连续打卡\s*(\d+)\s*天/);
      const rw = block.match(/赚取\s*([\d,]+)\s*积分/);
      const cnt = block.match(/^([\d]+)$/m);
      out.streaks.push({ name, days: d ? num(d[1]) : null, total: 7, nextReward: rw ? num(rw[1]) : null,
                         progress: cnt ? num(cnt[1]) : null });
    }
    m = earn.match(/升级活动\s*\n\s*(\d+)\s*\/\s*(\d+)/);
    if (m) out.upgrade = { done: num(m[1]), need: num(m[2]) };

    // ---- 邀请 ----
    try {
      await page.goto('https://rewards.bing.com/refer', { waitUntil: 'domcontentloaded', timeout: 45000 });
      await page.waitForTimeout(4000);
      const refer = (await page.evaluate(() => document.body.innerText)) || '';
      const gi = refer.match(/邀请人数\s*[\n\s]*([\d,]+)/);
      const ge = refer.match(/已赚取积分\s*[\n\s]*([\d,]+)/);
      const gp = refer.match(/待定积分\s*[\n\s]*([\d,]+)/);
      out.refer = { invites: gi ? num(gi[1]) : null, earned: ge ? num(ge[1]) : null, pending: gp ? num(gp[1]) : null };
    } catch (e) { out.errors.push('refer: ' + String(e).slice(0, 120)); }

    // ---- 领取 ----
    if (doClaim) {
      await page.goto('https://rewards.bing.com/dashboard', { waitUntil: 'domcontentloaded', timeout: 60000 });
      await page.waitForTimeout(4000);
      for (let round = 0; round < 3; round++) {
        const btns = await page.evaluate(() => {
          const all = [...document.querySelectorAll('button,a,[role=button]')];
          return all.map((b, i) => ({ i, t: (b.innerText || '').trim() }))
                    .filter(x => /^(领取|领取积分|领取奖励|Claim|Collect)$/i.test(x.t));
        });
        if (!btns.length) break;
        for (const b of btns.slice(0, 8)) {
          try {
            const loc = page.locator('button,a,[role=button]').filter({ hasText: new RegExp('^' + b.t + '$') }).first();
            await loc.click({ timeout: 8000 });
            out.claimed.push(b.t);
            await page.waitForTimeout(2500);
          } catch (e) { out.errors.push('claim: ' + String(e).slice(0, 100)); }
        }
        await page.reload({ waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(3000);
      }
      // 领取后再读一次可领取
      const after = (await page.evaluate(() => document.body.innerText)) || '';
      const m2 = after.match(/可领取\s*[\n\s]*([\d,]+)/);
      if (m2) out.claimable = num(m2[1]);
      const m3 = after.match(/可用积分\s*[\n\s]*([\d,]+)/);
      if (m3) out.points = num(m3[1]);
    }
    out.ok = true;
  } catch (e) {
    out.errors.push(String(e).slice(0, 300));
  } finally {
    await browser.close().catch(() => {});
  }
  console.log(JSON.stringify(out));
})();
