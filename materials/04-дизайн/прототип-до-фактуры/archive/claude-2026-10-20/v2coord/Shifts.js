class Component extends DCLogic {
  constructor(props) {
    super(props);
    this.state = this.initial('week');
  }
  initial(mode) {
    return {
      view: mode === 'hours' ? 'hours' : 'week',
      inviteOpen: mode === 'invite',
      inviteFor: 't1',
      picked: { t1: ['polina', 'sveta'], f2: ['polina', 'sveta', 'vera'], k1: ['kirill'] },
      invited: { t1: [], f2: [], k1: [] },
      att: {},
      confirmed: false
    };
  }
  renderVals() {
    const s = this.state;
    const P = {
      anna: { name: 'Анна Соколова', ini: 'АС', av: 'av-o', f: true },
      dima: { name: 'Дмитрий Орлов', ini: 'ДО', av: 'av-p', f: false },
      sveta: { name: 'Светлана Ким', ini: 'СК', av: 'av-g', f: true },
      polina: { name: 'Полина Зайцева', ini: 'ПЗ', av: 'av-v', f: true },
      timur: { name: 'Тимур Ахмедов', ini: 'ТА', av: 'av-b', f: false },
      vera: { name: 'Вера Новикова', ini: 'ВН', av: 'av-o', f: true },
      kirill: { name: 'Кирилл Смирнов', ini: 'КС', av: 'av-y', f: false }
    };
    const WS = [
      { key: 'paint', name: 'Живопись', art: 'art-o' },
      { key: 'theatre', name: 'Театр', art: 'art-p' },
      { key: 'music', name: 'Музыка', art: 'art-v' },
      { key: 'felt', name: 'Валяние', art: 'art-y' },
      { key: 'cer', name: 'Керамика', art: 'art-g' },
      { key: 'vitr', name: 'Витраж', art: 'art-v' },
      { key: 'film', name: 'Киноклуб', art: 'art-b' },
      { key: 'games', name: 'Настольные игры', art: 'art-b' }
    ];
    const DAYS = [
      { d: 'пн', n: '26', full: 'понедельник 26 октября' },
      { d: 'вт', n: '27', full: 'вторник 27 октября' },
      { d: 'ср', n: '28', full: 'среда 28 октября' },
      { d: 'чт', n: '29', full: 'четверг 29 октября' },
      { d: 'пт', n: '30', full: 'пятница 30 октября' },
      { d: 'сб', n: '31', full: 'суббота 31 октября' },
      { d: 'вс', n: '1', full: 'воскресенье 1 ноября' }
    ];
    const SL = [
      { id: 'p1', ws: 'paint', day: 0, time: '16:00', need: 2, base: 2 },
      { id: 'p2', ws: 'paint', day: 2, time: '16:00', need: 2, base: 2 },
      { id: 'p3', ws: 'paint', day: 5, time: '12:00', need: 2, base: 2 },
      { id: 'p4', ws: 'paint', day: 5, time: '15:00', need: 2, base: 2 },
      { id: 't1', ws: 'theatre', day: 1, time: '17:00', need: 3, base: 1, gap: true },
      { id: 't2', ws: 'theatre', day: 3, time: '17:00', need: 2, base: 2 },
      { id: 'm1', ws: 'music', day: 0, time: '17:00', need: 2, base: 2 },
      { id: 'm2', ws: 'music', day: 3, time: '17:00', need: 2, base: 2 },
      { id: 'f1', ws: 'felt', day: 2, time: '16:00', need: 2, base: 2 },
      { id: 'f2', ws: 'felt', day: 5, time: '11:00', need: 3, base: 0, gap: true },
      { id: 'c1', ws: 'cer', day: 2, time: '12:00', need: 2, base: 2 },
      { id: 'c2', ws: 'cer', day: 6, time: '12:00', need: 2, base: 2 },
      { id: 'v1', ws: 'vitr', day: 0, time: '16:00', need: 1, base: 1 },
      { id: 'k1', ws: 'film', day: 4, time: '19:00', need: 1, base: 0, gap: true },
      { id: 'g1', ws: 'games', day: 2, time: '18:30', need: 2, base: 2 },
      { id: 'g2', ws: 'games', day: 5, time: '14:00', need: 2, base: 2 }
    ];
    const C = {
      t1: [
        { id: 'polina', score: 88, why: 'знает группу, подменяла 13 октября', resp: 'yes' },
        { id: 'sveta', score: 81, why: 'свободна во вторник, прошла «Инклюзию»', resp: 'wait' },
        { id: 'kirill', score: 70, why: 'свободен во вторник, ведёт подростков', resp: 'no' },
        { id: 'vera', score: 58, why: 'свободна, но без «Инклюзии»', resp: 'wait' },
        { id: 'timur', score: 52, why: 'свободен, с детьми пока не занимался', resp: 'wait' }
      ],
      f2: [
        { id: 'polina', score: 92, why: 'ассистент в валянии', resp: 'yes' },
        { id: 'sveta', score: 78, why: 'суббота днём свободна, работает руками', resp: 'yes' },
        { id: 'vera', score: 64, why: 'выходные свободны, валяние не вела', resp: 'wait' }
      ],
      k1: [
        { id: 'kirill', score: 68, why: 'свободен в пятницу, ведёт подростков', resp: 'wait' }
      ]
    };
    const slotById = {};
    SL.forEach((x) => { slotById[x.id] = x; });
    const wsName = (k) => WS.filter((w) => w.key === k)[0].name;
    const invitedOf = (sid) => s.invited[sid] || [];
    const pickedOf = (sid) => s.picked[sid] || [];
    const filled = (sid) => {
      const yes = (C[sid] || []).filter((c) => invitedOf(sid).indexOf(c.id) >= 0 && c.resp === 'yes').length;
      return slotById[sid].base + yes;
    };
    const gapIds = ['t1', 'k1', 'f2'].filter((sid) => filled(sid) < slotById[sid].need);
    const sid = s.inviteFor;
    const word = (n) => (n === 1 ? 'смена' : (n >= 2 && n <= 4 ? 'смены' : 'смен'));
    const leadNames = { t1: 'театр во вторник', k1: 'киноклуб в пятницу', f2: 'валяние в субботу' };
    const heroLead = gapIds.map((g) => leadNames[g]).join(', ');

    const viewDefs = [{ id: 'week', label: 'Неделя' }, { id: 'hours', label: 'Подтверждение часов' }];
    const modeNow = s.view === 'hours' ? 'hours' : (s.inviteOpen ? 'invite' : 'week');
    const modeDefs = [{ id: 'week', label: 'Неделя' }, { id: 'invite', label: 'Кого позвать' }, { id: 'hours', label: 'Подтверждение часов' }];

    const wkRows = WS.map((w) => ({
      name: w.name,
      artCls: 'art art-sm ' + w.art,
      isPaint: w.key === 'paint', isTheatre: w.key === 'theatre', isMusic: w.key === 'music', isFelt: w.key === 'felt',
      isCer: w.key === 'cer', isVitr: w.key === 'vitr', isFilm: w.key === 'film', isGames: w.key === 'games',
      cells: DAYS.map((d, i) => ({
        slots: SL.filter((x) => x.ws === w.key && x.day === i).map((x) => {
          const f = filled(x.id);
          const bad = f < x.need;
          const sel = s.inviteOpen && x.id === sid;
          return {
            time: x.time,
            fill: f + '/' + x.need,
            ok: !bad, bad: bad,
            cls: 'slot slot-bad' + (f === 0 ? ' is-zero' : '') + (sel ? ' is-sel' : ''),
            pressed: sel ? 'true' : 'false',
            aria: w.name + ', ' + d.full + ', ' + x.time + ', записано ' + f + ' из ' + x.need,
            pick: () => this.setState({ inviteOpen: true, inviteFor: x.id })
          };
        })
      }))
    }));

    const isl = slotById[sid];
    const inv = invitedOf(sid);
    const pk = pickedOf(sid);
    const toInvite = pk.filter((id) => inv.indexOf(id) < 0);
    const left = isl.need - filled(sid);
    const leftWord = left <= 0 ? 'Все места заняты' : (left === 1 ? 'Нужен ещё один' : 'Нужны ещё ' + (left === 2 ? 'двое' : 'трое'));
    const cands = (C[sid] || []).map((c) => {
      const p = P[c.id];
      const invited = inv.indexOf(c.id) >= 0;
      const checked = pk.indexOf(c.id) >= 0;
      const respLabel = c.resp === 'yes' ? (p.f ? 'согласилась' : 'согласился') : (c.resp === 'no' ? (p.f ? 'отказалась' : 'отказался') : 'ждём ответа');
      return {
        name: p.name, ini: p.ini, avCls: 'avatar ' + p.av, why: c.why,
        score: c.score, scoreLabel: 'Совпадение ' + c.score + ' из 100',
        canPick: !invited,
        isYes: invited && c.resp === 'yes', isWait: invited && c.resp === 'wait', isNo: invited && c.resp === 'no',
        respLabel: p.name + ': ' + respLabel,
        isChecked: checked,
        checked: checked ? 'true' : 'false',
        cbxCls: checked ? 'cbx is-on' : 'cbx',
        cbxLabel: 'Пригласить: ' + p.name,
        toggle: () => {
          const np = { ...s.picked };
          np[sid] = checked ? pk.filter((x) => x !== c.id) : pk.concat([c.id]);
          this.setState({ picked: np });
        }
      };
    });

    const PAST = [
      { id: 's1', title: 'Живопись', when: 'сб 17 октября, 12:00–14:00', h: 2, people: [['anna', true], ['vera', true]] },
      { id: 's2', title: 'Валяние', when: 'сб 17 октября, 11:00–14:00', h: 3, people: [['polina', true], ['sveta', true]] },
      { id: 's3', title: 'Настольные игры', when: 'ср 14 октября, 18:30–20:00', h: 1.5, people: [['kirill', true], ['timur', true]] },
      { id: 's4', title: 'Театр', when: 'вт 13 октября, 17:00–19:00', h: 2, people: [['dima', false], ['polina', true]] }
    ];
    const fmt = (x) => String(x).replace('.', ',') + ' ч';
    let pendPeople = 0;
    let pendHours = 0;
    const past = PAST.map((ps) => {
      const people = ps.people.map((row) => {
        const pid = row[0];
        const p = P[pid];
        const k = ps.id + ':' + pid;
        const was = Object.prototype.hasOwnProperty.call(s.att, k) ? s.att[k] : row[1];
        if (was) { pendPeople += 1; pendHours += ps.h; }
        return {
          name: p.name, ini: p.ini, avCls: 'avatar ' + p.av,
          editable: !s.confirmed,
          tglCls: was ? 'toggle is-on' : 'toggle',
          pressed: was ? 'true' : 'false',
          tglAria: p.name + (was ? (p.f ? ': была' : ': был') : (p.f ? ': не была' : ': не был')),
          hours: was ? fmt(ps.h) : '0 ч',
          toggle: () => { const na = { ...s.att }; na[k] = !was; this.setState({ att: na }); }
        };
      });
      return { title: ps.title, when: ps.when, isConfirmed: s.confirmed, people: people };
    });
    const peopleWord = (n) => ((n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14)) ? 'человека' : 'человек');

    return {
      modes: modeDefs.map((m) => ({
        ...m,
        cls: m.id === modeNow ? 'is-on' : '',
        pressed: m.id === modeNow ? 'true' : 'false',
        pick: () => this.setState(this.initial(m.id))
      })),
      views: viewDefs.map((t) => ({
        ...t,
        cls: t.id === s.view ? 'is-on' : '',
        selected: t.id === s.view ? 'true' : 'false',
        pick: () => this.setState({ view: t.id })
      })),
      isWeek: s.view === 'week',
      isHours: s.view === 'hours',
      heroTitle: gapIds.length === 0 ? 'Все смены закрыты' : gapIds.length + ' ' + word(gapIds.length) + ' без людей',
      heroLead: gapIds.length === 0 ? 'На этой неделе всем хватает взрослых' : heroLead.charAt(0).toUpperCase() + heroLead.slice(1),
      heroCanOpen: !s.inviteOpen && gapIds.length > 0,
      inviteOpen: s.inviteOpen,
      openInvite: () => this.setState({ inviteOpen: true, inviteFor: gapIds[0] || 't1' }),
      closeInvite: () => this.setState({ inviteOpen: false }),
      days: DAYS,
      wkRows: wkRows,
      inv: {
        shift: wsName(isl.ws) + ', ' + DAYS[isl.day].full + ', ' + isl.time + '. ' + leftWord + '.',
        cands: cands,
        canSend: toInvite.length > 0,
        cantSend: toInvite.length === 0 && inv.length === 0,
        cantReason: 'Отметьте, кого позвать',
        sendLabel: 'Пригласить выбранных: ' + toInvite.length,
        send: () => { const ni = { ...s.invited }; ni[sid] = inv.concat(toInvite); this.setState({ invited: ni }); },
        hasSummary: inv.length > 0 && toInvite.length === 0,
        summary: 'Смена теперь ' + filled(sid) + ' из ' + isl.need
      },
      past: past,
      canConfirmAll: !s.confirmed,
      confirmAll: () => this.setState({ confirmed: true }),
      hoursTitle: s.confirmed ? 'Часы подтверждены' : '4 смены ждут подтверждения',
      hoursLead: s.confirmed ? 'Они уже в «Моём пути» у волонтёров' : pendPeople + ' ' + peopleWord(pendPeople) + ', ' + fmt(pendHours)
    };
  }
}