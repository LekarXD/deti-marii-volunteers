const { chromium } = require(process.env.PW);
const P = process.argv[2];
const click = (t, sel='button') => `[...document.querySelectorAll('${sel}')].find(b=>b.textContent.trim().startsWith(${JSON.stringify(t)})).click()`;
const runs = {
  Catalog: [[], [click('Почему так'), click('Показать'), click('Ещё')]],
  Opportunity: [[], [click('Записаться')], [click('Записаться'), click('Подтвердить')], [click('Нет мест','.demo button')], [click('Нет мест','.demo button'), click('Встать')], [click('Нет обучения','.demo button')]],
  Schedule: [[], [click('Я приду')], [click('Не смогу')], [click('Не смогу'), click('Сообщить')], [click('Календарь')], [click('Нет смен','.demo button')]],
  Reflection: [[], [click('Отправить')], [click('Тяжело'), click('Отправить')], [click('Тревожный','.demo button')], [click('Мне тяжело','.demo button')]],
};
(async () => {
  const browser = await chromium.launch();
  for (const name of Object.keys(runs)) {
    for (const acts of runs[name]) {
      const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
      const errs = []; page.on('pageerror', e => errs.push(String(e)));
      await page.goto('file://' + P + '/' + name + '.preview.html'); await page.waitForTimeout(300);
      for (const a of acts) { await page.evaluate(a); await page.waitForTimeout(80); }
      const r = await page.evaluate(() => {
        const secs = [...document.querySelectorAll('section')].map(s => s.querySelectorAll('.ai-tag').length).filter(n => n > 1).length;
        const blocks = [...document.querySelectorAll('.card-hero,.card-alarm,.card,.ai-box,.hero-note')].map(b => b.querySelectorAll('.btn').length).filter(n => n > 2).length;
        return { primary: document.querySelectorAll('.btn-primary').length, hero: document.querySelectorAll('.card-hero,.card-alarm').length, sectionsWith2AiTags: secs, blocksWith3Btns: blocks, h: document.documentElement.scrollHeight };
      });
      console.log(name, acts.length ? acts.map(a => a.match(/"(.+?)"/)[1]).join(' > ') : 'default', JSON.stringify(r), errs.length ? errs : '');
      await page.close();
    }
  }
  await browser.close();
})();
