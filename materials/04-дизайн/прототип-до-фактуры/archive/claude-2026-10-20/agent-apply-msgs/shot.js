// Full-page screenshots of static previews at 1440px; prints page heights.
const { chromium } = require('/Users/iliapetri/curator-bot/node_modules/.pnpm/playwright-core@1.59.1/node_modules/playwright-core');
const path = require('path');
(async () => {
  const names = process.argv.slice(2);
  const width = Number(process.env.W || 1440);
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width, height: 900 }, deviceScaleFactor: 1 });
  for (const n of names) {
    const file = path.resolve(__dirname, 'out', n + '.html');
    await page.goto('file://' + file, { waitUntil: 'load' });
    await page.waitForTimeout(300);
    const h = await page.evaluate(() => document.documentElement.scrollHeight);
    const sw = await page.evaluate(() => document.documentElement.scrollWidth);
    await page.screenshot({ path: path.resolve(__dirname, 'out', n + (width !== 1440 ? '-' + width : '') + '.png'), fullPage: true });
    console.log(n, 'height', h, 'scrollWidth', sw);
  }
  await browser.close();
})();
