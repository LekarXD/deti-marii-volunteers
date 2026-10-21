const { chromium } = require(process.env.PW);
(async () => {
  const browser = await chromium.launch();
  for (const f of process.argv.slice(2)) {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await page.goto('file://' + f); await page.waitForTimeout(500);
    const r = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth, h: document.documentElement.scrollHeight,
      wide: [...document.querySelectorAll('body *')].filter(e => e.getBoundingClientRect().right > document.documentElement.clientWidth + 1 && !e.closest('.nav')).slice(0,5).map(e => e.className || e.tagName) }));
    console.log(f.split('/').pop(), JSON.stringify(r));
    await page.screenshot({ path: f.replace('.preview.html', '.mobile.png'), fullPage: true });
    await page.close();
  }
  await browser.close();
})();
