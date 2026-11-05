const { chromium } = require(process.env.HOME + '/.npm/_npx/e41f203b7505f1fb/node_modules/playwright-core');
const dir = __dirname;
(async () => {
  const b = await chromium.launch({ executablePath: process.env.HOME + '/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing', args: ['--allow-file-access-from-files'] });
  const jobs = JSON.parse(process.argv[2]);
  for (const [d, w, h, out, extra] of jobs) {
    const p = await b.newPage({ viewport: { width: w, height: h } });
    await p.goto(`file://${dir}/art.html?d=${d}&w=${w}&h=${h}${extra || ''}`);
    await p.waitForFunction(() => document.title === 'done');
    const url = await p.evaluate(() => document.getElementById('c').toDataURL('image/png'));
    require('fs').writeFileSync(`${dir}/${out}`, Buffer.from(url.split(',')[1], 'base64'));
    await p.close();
  }
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });
