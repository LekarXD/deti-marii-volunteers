const { chromium } = require(process.env.PW);
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
  for (const n of ['CoordHome','Pipeline','Volunteers','Shifts']) {
    await p.goto('file://' + process.argv[2] + '/' + n + '.preview.html'); await p.waitForTimeout(300);
    const k = await p.evaluate(() => document.querySelectorAll('.demo button').length);
    for (let i = 0; i < k; i++) {
      await p.evaluate((i) => document.querySelectorAll('.demo button')[i].click(), i); await p.waitForTimeout(100);
      const r = await p.evaluate(() => ({ st: document.querySelectorAll('.demo button')[0] && [...document.querySelectorAll('.demo button')].find(b=>b.classList.contains('is-on'))?.textContent, prim: document.querySelectorAll('.btn-primary,.btn-dark').length, ai: document.querySelectorAll('.ai-tag').length, h: document.documentElement.scrollHeight,
        small: [...document.querySelectorAll('.dm *')].filter(e => e.closest('.demo')==null && e.childNodes.length && [...e.childNodes].some(c=>c.nodeType===3&&c.textContent.trim()) && parseFloat(getComputedStyle(e).fontSize) < 15 && !e.closest('.avatar,.tag,.ai-tag,.count,.brand,.nav')).map(e=>e.className+':'+e.textContent.trim().slice(0,20)) }));
      console.log(n, JSON.stringify(r));
    }
  }
  await b.close();
})();
