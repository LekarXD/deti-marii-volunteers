class Component extends DCLogic {
  constructor(props) {
    super(props);
    this.letterDefault = 'Уважаемая Анна!\n\nФонд «Дети Марии» благодарит вас за работу в мастерской живописи. С 20 июня вы провели 19 занятий с группой «Подсолнухи» и девять недель подряд приходили без пропусков.\n\nДетям важно, что рядом есть взрослый, который приходит каждую неделю. Спасибо вам за это.\n\nНаталья Гордеева, руководитель программ';
    this.emptyDraft = { what: '', date: '2026-10-20', hours: '2' };
    this.state = {
      mode: 'usual',
      all: false,
      addOpen: false,
      draft: Object.assign({}, this.emptyDraft),
      draftErr: '',
      added: [],
      dobro: false,
      letterOpen: false,
      letter: 'idle',
      letterText: this.letterDefault,
      letterBackup: '',
      certFor: 'any',
      certPeriod: 'all',
      certDone: false
    };
  }

  plural(n, one, few, many) {
    const a = Math.abs(n) % 100;
    const b = a % 10;
    if (a > 10 && a < 20) return many;
    if (b > 1 && b < 5) return few;
    if (b === 1) return one;
    return many;
  }

  fmtHours(h) {
    return String(h).replace('.', ',') + ' ч';
  }

  heatCells(empty) {
    const months = [['апр', 30], ['мая', 31], ['июн', 30], ['июл', 31], ['авг', 31], ['сен', 30], ['окт', 31]];
    const days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
    const hours = {};
    for (let w = 7; w <= 24; w++) hours[w + '-5'] = 2;
    delete hours['15-5'];
    hours['11-5'] = 4;
    hours['24-5'] = 4;
    hours['12-6'] = 5;
    hours['24-2'] = 3;
    hours['25-0'] = 2;
    const today = 25 * 7 + 1;
    const out = [];
    let d = 27;
    let m = 0;
    for (let i = 0; i < 182; i++) {
      const w = Math.floor(i / 7);
      const wd = i % 7;
      const label = days[wd] + ', ' + d + ' ' + months[m][0];
      const h = empty ? 0 : (hours[w + '-' + wd] || 0);
      let cls = '';
      let title = label;
      if (i > today) {
        if (!empty && w === 25 && wd === 5) { cls = 'plan'; title = label + ': занятие'; } else { cls = 'fut'; }
      } else if (h >= 4) { cls = 'h4'; title = label + ': ' + h + ' ч'; }
      else if (h === 3) { cls = 'h3'; title = label + ': 3 ч'; }
      else if (h === 2) { cls = 'h2'; title = label + ': 2 ч'; }
      else if (h === 1) { cls = 'h1'; title = label + ': 1 ч'; }
      out.push({ cls: cls, title: title });
      d += 1;
      if (d > months[m][1]) { d = 1; m += 1; }
    }
    return out;
  }

  setDraft(key, val) {
    const next = Object.assign({}, this.state.draft);
    next[key] = val;
    this.setState({ draft: next, draftErr: '' });
  }

  submitAdd() {
    const d = this.state.draft;
    const what = String(d.what || '').trim();
    const h = parseFloat(String(d.hours || '').replace(',', '.'));
    if (!what) { this.setState({ draftErr: 'what' }); return; }
    if (!(h > 0 && h <= 12)) { this.setState({ draftErr: 'hours' }); return; }
    const parts = String(d.date || '').split('-');
    const mi = parseInt(parts[1], 10);
    const day = parseInt(parts[2], 10);
    const names = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
    const label = day && mi ? day + ' ' + names[mi - 1] : '20 окт';
    const row = { date: label, what: what, hours: h, ok: false, isNew: true };
    this.setState({
      added: [row].concat(this.state.added),
      addOpen: false,
      draft: Object.assign({}, this.emptyDraft),
      draftErr: ''
    });
  }

  renderVals() {
    const s = this.state;
    const modeDefs = [
      { id: 'usual', label: 'Обычно' },
      { id: 'cert', label: 'Справка' },
      { id: 'new', label: 'Новичок' }
    ];
    const paint = 'Живопись с «Подсолнухами»';
    const base = [
      { date: '19 окт', what: 'Каталог рисунков для сайта, онлайн', hours: 2, ok: false },
      { date: '17 окт', what: 'Живопись и открытие выставки', hours: 4, ok: true },
      { date: '14 окт', what: 'Готовили выставку рисунков', hours: 3, ok: true },
      { date: '10 окт', what: paint, hours: 2, ok: true },
      { date: '3 окт', what: paint, hours: 2, ok: true },
      { date: '26 сен', what: paint, hours: 2, ok: true },
      { date: '19 сен', what: paint, hours: 2, ok: true },
      { date: '12 сен', what: paint, hours: 2, ok: true },
      { date: '5 сен', what: paint, hours: 2, ok: true }
    ];
    const rows = s.added.concat(base);
    const shown = s.all ? rows : rows.slice(0, 4);

    const periods = [
      { id: 'all', label: 'Всё время', h: 46, n: 19, line: '13 июня — 20 октября 2026' },
      { id: 'sep', label: 'С 1 сентября', h: 19, n: 8, line: '1 сентября — 20 октября 2026' },
      { id: 'oct', label: 'Октябрь', h: 11, n: 4, line: '1–20 октября 2026' }
    ];
    const fors = [
      { id: 'uni', label: 'Вуз' },
      { id: 'work', label: 'Работа' },
      { id: 'any', label: 'По месту требования' }
    ];
    const p = periods.filter((x) => x.id === s.certPeriod)[0] || periods[0];
    const hoursWord = p.h + ' ' + this.plural(p.h, 'час', 'часа', 'часов');
    const lessonsWord = p.n + ' ' + this.plural(p.n, 'занятие', 'занятия', 'занятий');

    const ms = [
      { title: 'Первое занятие', st: 'got', icon: 'heart', tone: 'art-o' },
      { title: 'Месяц без пропусков', st: 'got', icon: 'flame', tone: 'art-y' },
      { title: '10 занятий', st: 'got', icon: 'star', tone: 'art-g' },
      { title: 'Полгода с нами', st: 'next', date: '13 декабря', pct: 70 },
      { title: 'Год с фондом', st: 'lock' }
    ];
    const msNew = [
      { title: '«Первые шаги»', st: 'next', pct: 20 },
      { title: 'Первое занятие', st: 'lock' },
      { title: 'Месяц без пропусков', st: 'lock' },
      { title: '10 занятий', st: 'lock' },
      { title: 'Полгода с нами', st: 'lock' }
    ];
    const mapMs = (m) => ({
      title: m.title,
      date: m.date || '',
      hasDate: !!m.date,
      cls: 'ms' + (m.st === 'lock' ? ' is-lock' : ''),
      isGot: m.st === 'got',
      isNext: m.st === 'next',
      isLock: m.st === 'lock',
      badgeCls: 'badge ' + (m.tone || ''),
      ringStyle: '--p:' + (m.pct || 0) + '%',
      ringLabel: m.title + ': пройдено ' + (m.pct || 0) + '%',
      isHeart: m.icon === 'heart',
      isFlame: m.icon === 'flame',
      isStar: m.icon === 'star'
    });

    return {
      isUsual: s.mode === 'usual',
      isCert: s.mode === 'cert',
      isNew: s.mode === 'new',
      modes: modeDefs.map((m) => ({
        label: m.label,
        cls: m.id === s.mode ? 'is-on' : '',
        pressed: m.id === s.mode ? 'true' : 'false',
        pick: () => this.setState({ mode: m.id, certDone: false, letterOpen: false })
      })),
      openCert: () => this.setState({ mode: 'cert', certDone: false, letterOpen: false }),
      openLetter: () => this.setState({ mode: 'cert', certDone: false, letterOpen: true }),
      backUsual: () => this.setState({ mode: 'usual' }),

      milestones: ms.map(mapMs),
      milestonesNew: msNew.map(mapMs),
      heat: this.heatCells(false),
      heatNew: this.heatCells(true),

      logRows: shown.map((r) => ({
        date: r.date,
        what: r.what,
        hoursLabel: this.fmtHours(r.hours),
        cls: 'log-row' + (r.isNew ? ' is-new' : ''),
        ok: !!r.ok,
        wait: !r.ok
      })),
      hasMore: rows.length > 4,
      allExpanded: s.all ? 'true' : 'false',
      allLabel: s.all ? 'Свернуть' : 'Показать все',
      toggleAll: () => this.setState({ all: !this.state.all }),
      addOpen: s.addOpen,
      addClosed: !s.addOpen,
      openAdd: () => this.setState({ addOpen: true, draftErr: '' }),
      closeAdd: () => this.setState({ addOpen: false, draftErr: '' }),
      draft: s.draft,
      errWhat: s.draftErr === 'what',
      errHours: s.draftErr === 'hours',
      typeWhat: (e) => this.setDraft('what', e.target.value),
      typeDate: (e) => this.setDraft('date', e.target.value),
      typeHours: (e) => this.setDraft('hours', e.target.value),
      submitAdd: () => this.submitAdd(),

      certTitle: hoursWord + ', ' + lessonsWord,
      sheet: { total: hoursWord, period: p.line },
      certPeriods: periods.map((x) => ({
        label: x.label,
        cls: x.id === s.certPeriod ? 'chip is-on' : 'chip',
        pressed: x.id === s.certPeriod ? 'true' : 'false',
        pick: () => this.setState({ certPeriod: x.id, certDone: false })
      })),
      certFors: fors.map((x) => ({
        label: x.label,
        cls: x.id === s.certFor ? 'chip is-on' : 'chip',
        pressed: x.id === s.certFor ? 'true' : 'false',
        pick: () => this.setState({ certFor: x.id, certDone: false })
      })),
      certIdle: !s.certDone,
      certDone: s.certDone,
      downloadCert: () => this.setState({ certDone: true }),
      resetCert: () => this.setState({ certDone: false }),

      dobroIdle: !s.dobro,
      dobroDone: s.dobro,
      exportDobro: () => this.setState({ dobro: true }),

      letterOpen: s.letterOpen,
      letterExpanded: s.letterOpen ? 'true' : 'false',
      letterToggleLabel: s.letterOpen ? 'Скрыть' : 'Открыть',
      toggleLetter: () => this.setState({ letterOpen: !this.state.letterOpen }),
      letterText: s.letterText,
      letterView: s.letter !== 'edit',
      letterIdle: s.letter === 'idle',
      letterEdit: s.letter === 'edit',
      letterSent: s.letter === 'sent',
      requestLetter: () => this.setState({ letter: 'sent' }),
      withdrawLetter: () => this.setState({ letter: 'idle' }),
      editLetter: () => this.setState({ letter: 'edit', letterBackup: this.state.letterText }),
      typeLetter: (e) => this.setState({ letterText: e.target.value }),
      saveLetter: () => this.setState({ letter: 'idle' }),
      cancelLetter: () => this.setState({ letter: 'idle', letterText: this.state.letterBackup })
    };
  }
}