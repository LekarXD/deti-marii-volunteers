const { chromium } = require(process.env.PW);
(async () => {
  const b = await chromium.launch(); const pg = await b.newPage({ viewport: { width: 390, height: 800 } });
  for (const n of ['Lesson','Simulator','Mentor']) {
    await pg.goto('file://' + process.argv[2] + '/' + n + '.preview.html'); await pg.waitForTimeout(500);
    const k = await pg.evaluate(() => document.querySelectorAll('.demo button').length);
    for (let i = 0; i < k; i++) {
      await pg.evaluate((i) => document.querySelectorAll('.demo button')[i].click(), i); await pg.waitForTimeout(150);
      const r = await pg.evaluate(() => ({ sw: document.documentElement.scrollWidth, over: [...document.querySelectorAll('.shell *')].filter(e => e.getBoundingClientRect().right > 391 && !e.closest('.nav,.demo')).slice(0,3).map(e => e.tagName + '.' + e.className) }));
      console.log(n, i, JSON.stringify(r));
    }
  }
  await b.close();
})();
