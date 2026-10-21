const { chromium } = require(process.env.PW);
(async () => {
  const b = await chromium.launch(); const pg = await b.newPage({ viewport: { width: 1440, height: 900 } });
  for (const n of ['Lesson','Simulator','Mentor']) {
    await pg.goto('file://' + process.argv[2] + '/' + n + '.preview.html'); await pg.waitForTimeout(500);
    const k = await pg.evaluate(() => document.querySelectorAll('.demo button').length);
    for (let i = 0; i < k; i++) {
      await pg.evaluate((i) => document.querySelectorAll('.demo button')[i].click(), i); await pg.waitForTimeout(150);
      const r = await pg.evaluate(() => {
        const prim = document.querySelectorAll('.btn-primary').length;
        const secs = [...document.querySelectorAll('section')].map(s => s.querySelectorAll(':scope .ai-tag').length).filter(x => x > 1);
        const small = [...document.querySelectorAll('.shell *')].filter(e => e.childNodes.length && [...e.childNodes].some(c => c.nodeType === 3 && c.textContent.trim()) && parseFloat(getComputedStyle(e).fontSize) < 15 && !e.closest('.demo,.top,.tag,.ai-tag')).map(e => e.className + ':' + e.textContent.trim().slice(0, 20));
        return { label: document.querySelector('.demo button.is-on').textContent, prim, aiTags: document.querySelectorAll('.ai-tag').length, multiAiSec: secs, small, h: document.documentElement.scrollHeight };
      });
      console.log(n, JSON.stringify(r));
    }
  }
  await b.close();
})();
