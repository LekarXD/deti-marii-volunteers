// usage: node shot.js <preview.html> <out.png> <width> [height|full] [jsActions...]
const { chromium } = require(process.env.PW);
(async () => {
  const [file, out, width, height, ...acts] = process.argv.slice(2);
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: +width, height: height && height !== 'full' ? +height : 900 } });
  const errs = [];
  page.on('pageerror', e => errs.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  await page.goto('file://' + file);
  await page.waitForTimeout(800);
  for (const a of acts) { await page.evaluate(a); await page.waitForTimeout(200); }
  const h = await page.evaluate(() => document.documentElement.scrollHeight);
  console.log('scrollHeight', h);
  await page.screenshot({ path: out, fullPage: height === 'full' });
  if (errs.length) console.log('ERRORS', errs);
  await browser.close();
})();
