const { chromium } = require(process.env.PW);
const flows = {
  'Builder.dc.html': [[], ['Новый урок','Собрать черновик','Добавить в урок','Опубликовать'], ['Добавить блок','Тест'], ['Ведущий','Роль ведущего'], ['Изменить']],
  'Knowledge.dc.html': [[], ['Ответить','Опубликовать','Ответить'], ['Спросить как волонтёр','Откуда фрагменты','Исправить ответ'], ['Заменить файл']],
  'Scenarios.dc.html': [[], ['Проверить и одобрить','Тестовый прогон','Плохой ход','Одобрить','Да, одобрить','Все сценарии'], ['Подросток грубит и провоцирует','Методики','Тестовый прогон']]
};
(async () => {
  const browser = await chromium.launch();
  for (const [file, list] of Object.entries(flows)) {
    for (const flow of list) {
      const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
      const errs = [];
      page.on('pageerror', e => errs.push(String(e)));
      page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
      await page.goto('file://' + __dirname + '/rt/' + file);
      await page.waitForTimeout(2500);
      for (const t of flow) {
        const ok = await page.evaluate((t) => { const b = [...document.querySelectorAll('button,a')].find(x => x.textContent.trim() === t || x.getAttribute('aria-label') === t || (x.textContent.trim().startsWith(t) && t.length > 6)); if (!b) return false; b.click(); return true; }, t);
        if (!ok) errs.push('no button ' + t);
        await page.waitForTimeout(250);
      }
      const dc = await page.evaluate(() => (window.__dcErrors || []).slice(0, 10));
      const h = await page.evaluate(() => document.documentElement.scrollHeight);
      const prim = await page.evaluate(() => document.querySelectorAll('.btn-primary').length);
      const txt = await page.evaluate(() => document.body.innerText.length);
      console.log(file, JSON.stringify(flow), 'h=' + h, 'primary=' + prim, 'text=' + txt, errs.length ? 'ERR ' + errs.join(' | ') : '', dc.length ? 'DC ' + dc.join(' | ') : '');
      await page.close();
    }
  }
  await browser.close();
})();
