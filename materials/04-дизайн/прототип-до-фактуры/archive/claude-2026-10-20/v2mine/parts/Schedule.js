class Component extends DCLogic {
  constructor(props) {
    super(props);
    this.state = { mode: 'normal', view: 'list', hero: 'idle', reason: '', past: false, month: 'oct', sel: 'oct-24' };
  }
  renderVals() {
    const s = this.state;
    const empty = s.mode === 'empty';
    const NEXT = { key: 'oct-24', title: 'Живопись, «Подсолнухи»', when: '12:00–14:00, Дмитровка', kind: 'shift' };
    const UP = [
      { key: 'oct-22', wd: 'чт', dn: '22', title: 'Супервизия с психологом', when: '19:00, онлайн', kind: 'webinar', href: 'Studio.dc.html' },
      { key: 'oct-31', wd: 'сб', dn: '31', title: 'Живопись, «Подсолнухи»', when: '12:00–14:00, Дмитровка', kind: 'shift', href: 'Opportunity.dc.html' },
      { key: 'nov-7', wd: 'сб', dn: '7', title: 'Живопись, «Подсолнухи»', when: '12:00–14:00, Дмитровка', kind: 'shift', href: 'Opportunity.dc.html' }
    ];
    const PAST = [
      { key: 'oct-17', wd: 'сб', dn: '17', title: 'Живопись, «Подсолнухи»', when: '12:00–14:00', hours: '2 ч', ok: true, refl: true },
      { key: 'oct-14', wd: 'ср', dn: '14', title: 'Клуб настольных игр, подмена', when: '18:30–20:00', hours: '1,5 ч', ok: false, refl: false },
      { key: 'oct-10', wd: 'сб', dn: '10', title: 'Живопись, «Подсолнухи»', when: '12:00–14:00', hours: '2 ч', ok: true, refl: false }
    ];
    const reasonDefs = [{ id: 'ill', label: 'Болезнь' }, { id: 'work', label: 'Работа' }, { id: 'other', label: 'Другое' }];
    // Календарь 2026: 1 октября — четверг, 1 ноября — воскресенье (сдвиг от понедельника).
    const MD = {
      oct: { label: 'Октябрь 2026', lead: 3, days: 31, gen: 'октября' },
      nov: { label: 'Ноябрь 2026', lead: 6, days: 30, gen: 'ноября' }
    };
    const WD = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье'];
    const marks = {};
    if (!empty) {
      marks[NEXT.key] = 'orange';
      UP.forEach((e) => { marks[e.key] = e.kind === 'webinar' ? 'blue' : 'orange'; });
      PAST.forEach((p) => { marks[p.key] = 'green'; });
    }
    const md = MD[s.month];
    const blankCell = { blank: true, real: false, n: '', cls: '', dotCls: '', pressed: 'false', aria: '', pick: () => {} };
    const cells = [];
    for (let i = 0; i < md.lead; i++) cells.push(blankCell);
    for (let d = 1; d <= md.days; d++) {
      const key = s.month + '-' + d;
      const mk = marks[key];
      const isSel = s.sel === key;
      const isToday = key === 'oct-20';
      cells.push({
        blank: false,
        real: true,
        n: String(d),
        cls: 'cal-day' + (isSel ? ' is-sel' : '') + (isToday ? ' is-today' : ''),
        dotCls: mk ? 'cdot cdot-' + mk : 'cdot',
        pressed: isSel ? 'true' : 'false',
        aria: d + ' ' + md.gen + (isToday ? ', сегодня' : '') + (mk ? ', есть занятие' : ''),
        pick: () => this.setState({ sel: key })
      });
    }
    while (cells.length % 7 !== 0) cells.push(blankCell);
    const selParts = s.sel.split('-');
    const smd = MD[selParts[0]];
    const sd = Number(selParts[1]);
    const allItems = empty ? [] : [NEXT].concat(UP, PAST);
    const dayItems = allItems.filter((e) => e.key === s.sel).map((e) => ({ title: e.title, when: e.when }));
    const isCal = s.view === 'cal';
    const modeDefs = [{ id: 'normal', label: 'Обычно' }, { id: 'empty', label: 'Нет смен' }];
    return {
      modes: modeDefs.map((m) => ({
        label: m.label,
        cls: m.id === s.mode ? 'is-on' : '',
        pressed: m.id === s.mode ? 'true' : 'false',
        pick: () => this.setState({ mode: m.id, view: 'list', hero: 'idle', reason: '', past: false })
      })),
      hasShifts: !empty,
      isEmpty: empty,
      listCls: isCal ? '' : 'is-on',
      calCls: isCal ? 'is-on' : '',
      listPressed: isCal ? 'false' : 'true',
      calPressed: isCal ? 'true' : 'false',
      toList: () => this.setState({ view: 'list' }),
      toCal: () => this.setState({ view: 'cal' }),
      heroPlain: s.hero === 'idle' || s.hero === 'yes',
      heroIdle: s.hero === 'idle',
      heroYes: s.hero === 'yes',
      heroAsk: s.hero === 'ask',
      heroSent: s.hero === 'sent',
      artPalette: s.hero !== 'sent',
      artSwap: s.hero === 'sent',
      confirm: () => this.setState({ hero: 'yes' }),
      cantGo: () => this.setState({ hero: 'ask', reason: '' }),
      reset: () => this.setState({ hero: 'idle', reason: '' }),
      send: () => this.setState({ hero: 'sent' }),
      reasons: reasonDefs.map((r) => ({
        label: r.label,
        cls: r.id === s.reason ? 'chip is-on' : 'chip',
        checked: r.id === s.reason ? 'true' : 'false',
        pick: () => this.setState({ reason: r.id })
      })),
      subs: [
        { av: 'avatar avatar-sm av-v', ini: 'СК', name: 'Светлана Ким' },
        { av: 'avatar avatar-sm av-p', ini: 'ПЗ', name: 'Полина Зайцева' },
        { av: 'avatar avatar-sm av-g', ini: 'ВН', name: 'Вера Новикова' }
      ],
      showList: !empty && !isCal,
      showCal: !empty && isCal,
      upcoming: UP.slice(0, 4).map((e) => ({
        wd: e.wd, dn: e.dn, title: e.title, when: e.when, href: e.href,
        dateCls: e.kind === 'webinar' ? 'date date-b' : 'date'
      })),
      showPast: s.past,
      pastExpanded: s.past ? 'true' : 'false',
      pastLabel: s.past ? 'Скрыть' : 'Показать',
      togglePast: () => this.setState({ past: !s.past }),
      past: PAST.map((p) => ({ wd: p.wd, dn: p.dn, title: p.title, when: p.when, hours: p.hours, ok: p.ok, wait: !p.ok, hasRefl: p.refl })),
      monthLabel: md.label,
      prevDis: s.month === 'oct' ? 'true' : 'false',
      nextDis: s.month === 'nov' ? 'true' : 'false',
      prevMonth: () => { if (this.state.month === 'nov') this.setState({ month: 'oct' }); },
      nextMonth: () => { if (this.state.month === 'oct') this.setState({ month: 'nov' }); },
      cells,
      selLabel: WD[(smd.lead + sd - 1) % 7] + ', ' + sd + ' ' + smd.gen,
      dayItems,
      dayHas: dayItems.length > 0,
      dayEmpty: dayItems.length === 0
    };
  }
}