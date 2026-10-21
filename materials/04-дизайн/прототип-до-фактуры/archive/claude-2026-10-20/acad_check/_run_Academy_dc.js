
class DCLogic { constructor(props){ this.props = props; this.state = {}; } setState(p){ this.state = Object.assign({}, this.state, p); } }

class Component extends DCLogic {
  constructor(props) {
    super(props);
    this.state = { mode: 'anna', lib: 'all', sup: false, intro: false, rec: '', first: false, pro: false };
  }
  renderVals() {
    const s = this.state;
    const anna = s.mode === 'anna';
    const modeDefs = [
      { id: 'anna', label: 'Анна' },
      { id: 'new', label: 'Новичок (Егор: Первые шаги 1/5)' }
    ];
    const assistant = [
      { n: 1, title: 'Как устроено занятие', kind: 'article', typeLabel: 'Статья', st: 'done' },
      { n: 2, title: 'Работа с группой', kind: 'video', typeLabel: 'Видео', st: 'done' },
      { n: 3, title: 'Инклюзия: дети с особенностями развития', kind: 'article', typeLabel: 'Статья, видео, упражнение, тест', dur: '12 мин', href: 'Lesson.dc.html', st: 'done' },
      { n: 4, title: 'Тренажёр: трудные ситуации на занятии', kind: 'sim', typeLabel: 'Тренажёр, диалог с ребёнком', dur: '10–15 мин', href: 'Simulator.dc.html', st: 'now' },
      { n: 5, title: 'Практика: план своего мастер-класса', kind: 'task', typeLabel: 'Задание с проверкой', ai: true, aiNote: 'и координатор', st: 'locked', lockReason: 'После тренажёра' }
    ];
    const firstSteps = [
      { n: 1, title: 'О фонде и наших детях', kind: 'article', typeLabel: 'Статья', dur: '8 мин', st: 'done' },
      { n: 2, title: 'Правила безопасности и границы', kind: 'video', typeLabel: 'Видео и памятка PDF', dur: '12 мин', href: 'Lesson.dc.html', st: 'now' },
      { n: 3, title: 'Как говорить с ребёнком из учреждения', kind: 'article', typeLabel: 'Статья и тренажёр', st: 'next' },
      { n: 4, title: 'Если ребёнок рассказывает о насилии', kind: 'video', typeLabel: 'Видео и тренажёр', st: 'next' },
      { n: 5, title: 'Итоговый тест', kind: 'test', typeLabel: '12 вопросов, порог 70%', st: 'next' }
    ];
    const modules = (anna ? assistant : firstSteps).map((m) => ({
      ...m,
      rowCls: m.st === 'now' ? 'li mod is-now' : 'li mod',
      numCls: 'mod-n' + (m.st === 'done' ? ' is-done' : (m.st === 'now' ? ' is-now' : '')),
      isDone: m.st === 'done',
      isNow: m.st === 'now',
      isLocked: m.st === 'locked',
      showNum: m.st === 'now' || m.st === 'next',
      hasLink: !!m.href,
      noLink: !m.href,
      href: m.href || '',
      hasDur: !!m.dur,
      dur: m.dur || '',
      ai: !!m.ai,
      aiNote: m.aiNote || '',
      lockReason: m.lockReason || '',
      isArticle: m.kind === 'article',
      isVideo: m.kind === 'video',
      isSim: m.kind === 'sim',
      isTask: m.kind === 'task',
      isTest: m.kind === 'test'
    }));
    const recDefs = [
      { id: 'r1', title: 'Супервизия: когда ребёнок закрывается', when: '25 сентября', host: 'Ирина Власова', dur: '58 мин',
        points: ['Сначала контакт, потом просьба: сесть рядом и назвать то, что видишь.', 'Не спрашивать «почему»: для ребёнка это звучит как допрос.', 'Дать два приемлемых выбора: посмотреть или выбрать краски для фона.'] },
      { id: 'r2', title: 'Вводная встреча для новичков', when: '27 сентября', host: 'Ольга Лебедева', dur: '46 мин',
        points: ['Как устроены мастерские фонда и кто за что отвечает.', 'С ребёнком не остаёмся наедине, личные контакты детям не даём.', 'Не можешь прийти — скажи Ольге заранее, она найдёт замену.'] },
      { id: 'r3', title: 'Супервизия: прощания и паузы', when: '28 августа', host: 'Ирина Власова', dur: '1 ч 04 мин',
        points: ['О паузе говорить заранее и называть дату возвращения.', 'Не обещать «я никогда не уйду».', 'Последнюю встречу планировать вместе с координатором.'] }
    ];
    const libDefs = [
      { k: 'article', title: 'О фонде и наших детях', meta: 'Статья, 8 мин', href: 'Lesson.dc.html' },
      { k: 'article', title: 'Как говорить с ребёнком из учреждения', meta: 'Статья', href: 'Lesson.dc.html' },
      { k: 'article', title: 'Инклюзия: дети с особенностями развития', meta: 'Статья и видео, 12 мин', href: 'Lesson.dc.html' },
      { k: 'video', title: 'Правила безопасности и границы', meta: 'Видео, 12 мин', href: 'Lesson.dc.html' },
      { k: 'video', title: 'Если ребёнок рассказывает о насилии', meta: 'Видео', href: 'Lesson.dc.html' },
      { k: 'video', title: 'Сенсорная нагрузка на занятии', meta: 'Видео, 8:40', href: 'Lesson.dc.html' },
      { k: 'sim', title: 'Отказывается участвовать', meta: 'Тренажёр, 10–15 мин', href: 'Simulator.dc.html' },
      { k: 'sim', title: 'Ты придёшь ещё? Дай свой телефон', meta: 'Тренажёр, 10–15 мин', href: 'Simulator.dc.html' },
      { k: 'sim', title: 'Подросток грубит и провоцирует', meta: 'Тренажёр, 10–15 мин', href: 'Simulator.dc.html' },
      { k: 'memo', title: 'Памятка: инклюзивное занятие', meta: 'PDF, 1,2 МБ' },
      { k: 'memo', title: 'Памятка «Границы»', meta: 'PDF' },
      { k: 'memo', title: 'Кодекс волонтёра', meta: 'PDF' }
    ];
    const artFor = { article: 'art art-sm art-b', video: 'art art-sm art-v', sim: 'art art-sm art-o', memo: 'art art-sm art-y' };
    const library = libDefs
      .filter((x) => s.lib === 'all' || x.k === s.lib)
      .map((x) => ({
        ...x,
        art: artFor[x.k],
        isArticle: x.k === 'article',
        isVideo: x.k === 'video',
        isSim: x.k === 'sim',
        isMemo: x.k === 'memo',
        hasLink: !!x.href,
        noLink: !x.href,
        href: x.href || '',
        dlLabel: 'Скачать: ' + x.title
      }));
    const n = library.length;
    const word = n % 10 === 1 && n % 100 !== 11 ? 'материал' : (n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? 'материала' : 'материалов');
    const filterDefs = [
      { id: 'all', label: 'Все' },
      { id: 'article', label: 'Статьи' },
      { id: 'video', label: 'Видео' },
      { id: 'sim', label: 'Тренажёры' },
      { id: 'memo', label: 'Памятки' }
    ];
    return {
      modes: modeDefs.map((m) => ({
        ...m,
        cls: m.id === s.mode ? 'is-on' : '',
        pressed: m.id === s.mode ? 'true' : 'false',
        pick: () => this.setState({ mode: m.id, first: false })
      })),
      isAnna: anna,
      isNew: !anna,
      trackTitle: anna ? 'Ассистент мастерской' : 'Первые шаги',
      trackSub: anna ? 'Помогать ведущей на занятиях в мастерской' : 'Обязательный трек для всех волонтёров',
      trackCount: anna ? '3 из 5' : '1 из 5',
      barCls: anna ? 'w60' : 'w20',
      modules,
      firstOpen: s.first,
      firstExpanded: s.first ? 'true' : 'false',
      firstLabel: s.first ? 'Скрыть модули' : 'Модули',
      toggleFirst: () => this.setState({ first: !s.first }),
      firstDone: firstSteps.map((f) => ({ title: f.title })),
      proIdle: !s.pro,
      proOn: s.pro,
      startPro: () => this.setState({ pro: true }),
      stopPro: () => this.setState({ pro: false }),
      supOpen: !s.sup,
      supJoined: s.sup,
      joinSup: () => this.setState({ sup: true }),
      leaveSup: () => this.setState({ sup: false }),
      introOpen: !s.intro,
      introJoined: s.intro,
      joinedWord: anna ? 'Ты записана' : 'Ты записан',
      joinIntro: () => this.setState({ intro: true }),
      leaveIntro: () => this.setState({ intro: false }),
      records: recDefs.map((r) => ({
        ...r,
        open: s.rec === r.id,
        expanded: s.rec === r.id ? 'true' : 'false',
        toggle: () => this.setState({ rec: s.rec === r.id ? '' : r.id })
      })),
      filters: filterDefs.map((f) => ({
        ...f,
        cls: f.id === s.lib ? 'chip is-on' : 'chip',
        pressed: f.id === s.lib ? 'true' : 'false',
        pick: () => this.setState({ lib: f.id })
      })),
      library,
      libCount: n + ' ' + word
    };
  }
}

const c = new Component({});
const roots = ["barCls", "filters", "firstDone", "firstExpanded", "firstLabel", "firstOpen", "introJoined", "introOpen", "isAnna", "isNew", "joinIntro", "joinSup", "joinedWord", "leaveIntro", "leaveSup", "libCount", "library", "modes", "modules", "proIdle", "proOn", "records", "startPro", "stopPro", "supJoined", "supOpen", "toggleFirst", "trackCount", "trackSub", "trackTitle"];
const seen = new Set();
function mark(vals){ for (const r of roots) { if (vals[r] !== undefined) seen.add(r); } }
function fire(vals, label){
  for (const [fk, fv] of Object.entries(vals)) {
    if (typeof fv === 'function') {
      try { fv({ target: { value: 'тест' } }); mark(c.renderVals()); } catch (e) { console.log('ERR ' + label + '.' + fk + ': ' + e.message); }
    }
    if (Array.isArray(fv)) {
      for (const it of fv) {
        if (it && typeof it === 'object') {
          for (const [ik, iv] of Object.entries(it)) {
            if (typeof iv === 'function') {
              try { iv(); mark(c.renderVals()); } catch (e) { console.log('ERR ' + label + '.' + fk + '[].' + ik + ': ' + e.message); }
            }
          }
        }
      }
    }
  }
}
let v0 = c.renderVals();
mark(v0);
const modeKey = Object.keys(v0).find(k => /^(modes|views|demo)$/.test(k));
const modes = modeKey ? v0[modeKey] : [null];
for (let i = 0; i < modes.length; i++) {
  const cur = c.renderVals();
  if (modeKey) { cur[modeKey][i].pick(); }
  const v = c.renderVals();
  mark(v);
  fire(v, 'mode' + i);
  mark(c.renderVals());
}
console.log(JSON.stringify({ missing: roots.filter(r => !seen.has(r)) }));
