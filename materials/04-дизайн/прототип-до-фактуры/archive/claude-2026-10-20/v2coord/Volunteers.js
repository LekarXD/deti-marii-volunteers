class Component extends DCLogic {
  constructor(props) {
    super(props);
    this.state = this.initial('dima');
  }
  initial(mode) {
    return {
      sel: mode === 'empty' ? null : (mode === 'anna' ? 'anna' : 'dima'),
      tab: 'overview',
      chip: 'all',
      query: mode === 'empty' ? 'Сергей' : '',
      all: false,
      done: {}
    };
  }
  renderVals() {
    const s = this.state;
    const D = s.done;
    const isDone = (k) => !!D[k];
    const mark = (k) => { const n = { ...D }; n[k] = true; this.setState({ done: n }); };
    const people = [
      { id: 'dima', name: 'Дмитрий Орлов', ini: 'ДО', av: 'av-p', ws: 'Театр', oct: '0', st: 'risk', dot: '2 пропуска', dotCls: 'dot dot-red',
        role: 'Помощник в инклюзивной театральной мастерской', total: '38', dat: 'Дмитрию',
        plaque: 'Два пропуска подряд, группе нужен второй взрослый',
        actions: [
          { key: 'dima-call', label: 'Позвонить', cls: 'btn btn-primary btn-sm', doneLabel: 'Звонок отмечен' },
          { key: 'dima-pause', label: 'Предложить паузу', cls: 'btn btn-secondary btn-sm', doneLabel: 'Пауза предложена' }
        ],
        ov: [
          { ic: 'cal', t: 'Театр, вторник 17:00–19:00' },
          { ic: 'star', t: 'Сценическое движение, импровизация, подростки' },
          { ic: 'clock', t: 'Вторник вечером, иногда суббота' },
          { ic: 'users', t: 'С фондом 7 месяцев' }
        ],
        shifts: [
          { d: 'вт 13 окт', w: 'Театр', miss: true },
          { d: 'вт 6 окт', w: 'Театр', miss: true },
          { d: 'вт 29 сен', w: 'Театр', h: '2 ч' },
          { d: 'вт 22 сен', w: 'Театр', h: '2 ч' }
        ],
        tracks: [
          { t: 'Первые шаги', p: '5 из 5', w: 100, done: true },
          { t: 'Ассистент мастерской', p: '5 из 5', w: 100, done: true }
        ],
        trainer: '«Подросток грубит и провоцирует»: 8 из 10',
        refl: [
          { d: 'вт 29 сен', mood: 'meh', text: 'Репетировали сцену с тенями. Л., 12 лет, не захотел на сцену, держал фонарь всю сцену.' },
          { d: 'вт 22 сен', mood: 'frown', text: 'Пришёл после работы уставшим, к концу тяжело было держать группу.' }
        ] },
      { id: 'marina', name: 'Марина Белова', ini: 'МБ', av: 'av-v', ws: 'Музыка', oct: '4,5', st: 'risk', dot: 'хочет уйти', dotCls: 'dot dot-red',
        role: 'Ассистент музыкальной студии', total: '15', dat: 'Марине',
        plaque: 'Третье занятие подряд не справляется с группой',
        actions: [
          { key: 'marina-call', label: 'Позвонить', cls: 'btn btn-primary btn-sm', doneLabel: 'Звонок отмечен' },
          { key: 'marina-sup', label: 'Записать на супервизию', cls: 'btn btn-secondary btn-sm', doneLabel: 'Записана на 22 октября' }
        ],
        ov: [
          { ic: 'cal', t: 'Музыка, четверг 17:00–18:30' },
          { ic: 'star', t: 'Фортепиано, вокал' },
          { ic: 'clock', t: 'Четверг вечером' },
          { ic: 'users', t: 'Наставника пока нет' }
        ],
        shifts: [
          { d: 'чт 15 окт', w: 'Музыка', h: '1,5 ч' },
          { d: 'чт 8 окт', w: 'Музыка', h: '1,5 ч' },
          { d: 'чт 1 окт', w: 'Музыка', h: '1,5 ч' }
        ],
        tracks: [
          { t: 'Первые шаги', p: '5 из 5', w: 100, done: true },
          { t: 'Ассистент мастерской', p: '2 из 5', w: 40 }
        ],
        trainer: '«Сенсорная перегрузка у ребёнка с аутизмом»: 5 из 10',
        refl: [
          { d: 'чт 15 окт', mood: 'frown', text: 'Третье занятие подряд не справляюсь с группой, хочу уйти.' },
          { d: 'чт 8 окт', mood: 'frown', text: 'Пока помогаю одному, остальные разбегаются.' },
          { d: 'чт 1 окт', mood: 'meh', text: 'Тяжело, но дети пели.' }
        ] },
      { id: 'egor', name: 'Егор Мельников', ini: 'ЕМ', av: 'av-y', ws: 'Пока нет', oct: '0', st: 'risk', dot: 'стоит в обучении', dotCls: 'dot dot-orange',
        role: 'Новичок, проходит «Первые шаги»', total: '0', dat: 'Егору',
        plaque: '16 дней без движения в «Первых шагах»',
        actions: [
          { key: 'egor-write', label: 'Написать', cls: 'btn btn-primary btn-sm', doneLabel: 'Сообщение отправлено' },
          { key: 'egor-invite', label: 'Позвать на вводную', cls: 'btn btn-secondary btn-sm', doneLabel: 'Позвали на 24 октября' }
        ],
        ov: [
          { ic: 'cal', t: 'Подобрано: клуб настольных игр, выезды водителем' },
          { ic: 'star', t: 'Настольные игры, есть автомобиль' },
          { ic: 'clock', t: 'Среда вечером, суббота утром' },
          { ic: 'users', t: 'Наставница — Светлана Ким' }
        ],
        shifts: [],
        tracks: [{ t: 'Первые шаги', p: '1 из 5', w: 20 }],
        trainer: '',
        refl: [] },
      { id: 'anna', name: 'Анна Соколова', ini: 'АС', av: 'av-o', ws: 'Живопись', oct: '11', st: 'ok', dat: 'Анне',
        role: 'Ассистент в мастерской живописи', total: '46',
        ov: [
          { ic: 'cal', t: '«Подсолнухи», суббота 12:00–14:00' },
          { ic: 'star', t: 'Акварель, графический дизайн, вожатая (дети 8–12)' },
          { ic: 'clock', t: 'Суббота днём, среда вечером' },
          { ic: 'pin', t: 'Савёловский' }
        ],
        shifts: [
          { d: 'сб 17 окт', w: 'Живопись', h: '2 ч' },
          { d: 'вс 11 окт', w: 'Выезд в ЦССУ', h: '3 ч' },
          { d: 'сб 10 окт', w: 'Живопись', h: '2 ч' },
          { d: 'ср 7 окт', w: 'Настольные игры', h: '2 ч' }
        ],
        tracks: [
          { t: 'Первые шаги', p: '5 из 5', w: 100, done: true },
          { t: 'Ассистент мастерской', p: '3 из 5', w: 60 }
        ],
        trainer: '«Ребёнок рассказывает о насилии»: 9 из 10',
        refl: [
          { d: 'сб 17 окт', mood: 'smile', text: 'Рисовали осенние листья. М., 9 лет, впервые закончил работу и попросил повесить её на стену.' },
          { d: 'сб 10 окт', mood: 'smile', text: 'Новенькая С., 8 лет, весь урок держалась рядом со мной.' },
          { d: 'сб 3 окт', mood: 'meh', text: 'Двое мальчиков спорили из-за кисточек, развела по разным столам.' }
        ] },
      { id: 'sveta', name: 'Светлана Ким', ini: 'СК', av: 'av-g', ws: 'Керамика', oct: '14', st: 'ok', dat: 'Светлане',
        role: 'Ассистент в керамике, наставница новичков', total: '168',
        ov: [
          { ic: 'cal', t: 'Керамика, среда и суббота' },
          { ic: 'star', t: 'Лепка, гончарный круг' },
          { ic: 'clock', t: 'Вторник вечером, среда и суббота днём' },
          { ic: 'users', t: 'Ведёт Анну Соколову и Егора Мельникова' }
        ],
        shifts: [
          { d: 'ср 14 окт', w: 'Керамика', h: '2 ч' },
          { d: 'сб 10 окт', w: 'Керамика', h: '3 ч' },
          { d: 'ср 7 окт', w: 'Керамика', h: '2 ч' }
        ],
        tracks: [
          { t: 'Первые шаги', p: '5 из 5', w: 100, done: true },
          { t: 'Ассистент мастерской', p: '5 из 5', w: 100, done: true }
        ],
        trainer: '«Ты придёшь ещё? Дай свой телефон»: 10 из 10',
        refl: [{ d: 'ср 14 окт', mood: 'smile', text: 'Лепили чашки. К., 10 лет, сам помог младшему центровать глину.' }] },
      { id: 'polina', name: 'Полина Зайцева', ini: 'ПЗ', av: 'av-v', ws: 'Валяние', oct: '8', st: 'ok', dat: 'Полине',
        role: 'Ассистент в мастерской валяния', total: '52',
        ov: [
          { ic: 'cal', t: 'Валяние, суббота; подменяет в театре' },
          { ic: 'star', t: 'Валяние, шитьё' },
          { ic: 'clock', t: 'Вторник вечером, суббота' }
        ],
        shifts: [
          { d: 'сб 17 окт', w: 'Валяние', h: '3 ч' },
          { d: 'вт 13 окт', w: 'Театр, замена', h: '2 ч' },
          { d: 'сб 10 окт', w: 'Валяние', h: '3 ч' }
        ],
        tracks: [
          { t: 'Первые шаги', p: '5 из 5', w: 100, done: true },
          { t: 'Ассистент мастерской', p: '5 из 5', w: 100, done: true }
        ],
        trainer: '«Ребёнок рассказывает о насилии»: 10 из 10',
        refl: [
          { d: 'сб 17 окт', mood: 'frown', text: 'Д., 11 лет, сказала, что дома её наказывают, просила никому не говорить.', flag: 'Передано Ирине Власовой' },
          { d: 'сб 10 окт', mood: 'smile', text: 'Валяли осенних лис. Одну подарили ведущей.' }
        ] },
      { id: 'kirill', name: 'Кирилл Смирнов', ini: 'КС', av: 'av-y', ws: 'Настольные игры', oct: '3', st: 'ok', dat: 'Кириллу',
        role: 'Ведущий клуба настольных игр', total: '140',
        ov: [
          { ic: 'cal', t: 'Клуб, среда 18:30–20:00' },
          { ic: 'star', t: 'Настольные игры, подростки 13–17' },
          { ic: 'clock', t: 'Вторник, среда и пятница вечером' }
        ],
        shifts: [
          { d: 'ср 14 окт', w: 'Настольные игры', h: '1,5 ч' },
          { d: 'ср 7 окт', w: 'Настольные игры', h: '1,5 ч' }
        ],
        tracks: [
          { t: 'Первые шаги', p: '5 из 5', w: 100, done: true },
          { t: 'Ведущий', p: '4 из 4', w: 100, done: true }
        ],
        trainer: '«Подросток грубит и провоцирует»: 9 из 10',
        refl: [{ d: 'ср 7 окт', mood: 'smile', text: 'Подростки сами придумали правила турнира на ноябрь.' }] },
      { id: 'timur', name: 'Тимур Ахмедов', ini: 'ТА', av: 'av-b', ws: 'Выезды', oct: '4', st: 'ok', dat: 'Тимуру',
        role: 'Водитель на выезды', total: '20',
        ov: [
          { ic: 'cal', t: 'Выезд в ЦССУ, суббота 24 октября, 9:00' },
          { ic: 'star', t: 'Свой автомобиль' },
          { ic: 'clock', t: 'Вторник вечером, суббота утром' }
        ],
        shifts: [
          { d: 'вс 11 окт', w: 'Выезд в ЦССУ', h: '3 ч' },
          { d: 'сб 3 окт', w: 'Материалы на Дмитровку', h: '1 ч' }
        ],
        tracks: [{ t: 'Первые шаги', p: '5 из 5', w: 100, done: true }],
        trainer: '',
        refl: [] },
      { id: 'vera', name: 'Вера Новикова', ini: 'ВН', av: 'av-o', ws: 'Выезды', oct: '3', st: 'ok', dat: 'Вере',
        role: 'Фотограф на событиях фонда', total: '18',
        ov: [
          { ic: 'cal', t: 'Осенняя ярмарка, воскресенье 8 ноября' },
          { ic: 'star', t: 'Репортажная съёмка' },
          { ic: 'clock', t: 'Вторник вечером, выходные' }
        ],
        shifts: [{ d: 'вс 11 окт', w: 'Выезд в ЦССУ, съёмка', h: '3 ч' }],
        tracks: [{ t: 'Первые шаги', p: '5 из 5', w: 100, done: true }],
        trainer: '«Ты придёшь ещё? Дай свой телефон»: 8 из 10',
        refl: [] },
      { id: 'ksenia', name: 'Ксения Рябова', ini: 'КР', av: 'av-g', ws: 'Киноклуб', oct: '0', st: 'pause', dot: 'пауза', dotCls: 'dot', dat: 'Ксении',
        role: 'Ведущая обсуждений в киноклубе', total: '56',
        ov: [
          { ic: 'cal', t: 'Киноклуб, пятница 19:00–21:00' },
          { ic: 'star', t: 'Кино, модерация обсуждений' },
          { ic: 'clock', t: 'Пятница вечером, с декабря' }
        ],
        shifts: [
          { d: 'пт 25 сен', w: 'Киноклуб', h: '2 ч' },
          { d: 'пт 18 сен', w: 'Киноклуб', h: '2 ч' }
        ],
        tracks: [
          { t: 'Первые шаги', p: '5 из 5', w: 100, done: true },
          { t: 'Ведущий', p: '4 из 4', w: 100, done: true }
        ],
        trainer: '«Подросток грубит и провоцирует»: 10 из 10',
        refl: [{ d: 'пт 25 сен', mood: 'smile', text: 'Обсуждали фильм про первую работу. Спорили до конца, никто не ушёл.' }] }
    ];

    const q = (s.query || '').trim().toLowerCase();
    const filtered = people.filter((p) => {
      if (s.chip === 'risk' && p.st !== 'risk') return false;
      if (s.chip === 'pause' && p.st !== 'pause') return false;
      if (q && p.name.toLowerCase().indexOf(q) < 0) return false;
      return true;
    });
    const shown = s.all ? filtered : filtered.slice(0, 4);
    const chipDefs = [
      { id: 'all', label: 'Все' },
      { id: 'risk', label: 'Нужно внимание' },
      { id: 'pause', label: 'На паузе' }
    ];
    const modeNow = s.query === 'Сергей' && !s.sel ? 'empty' : (s.sel === 'anna' ? 'anna' : (s.sel === 'dima' ? 'dima' : ''));
    const modeDefs = [
      { id: 'dima', label: 'Дмитрий, риск' },
      { id: 'anna', label: 'Анна' },
      { id: 'empty', label: 'Ничего не найдено' }
    ];
    const tabDefs = [
      { id: 'overview', label: 'Обзор' },
      { id: 'hours', label: 'Часы' },
      { id: 'learn', label: 'Обучение' },
      { id: 'refl', label: 'Рефлексии' }
    ];
    const cur = people.filter((p) => p.id === s.sel)[0] || people[0];
    const pid = cur.id;
    const actions = (cur.actions || []).map((a) => ({
      label: a.label, cls: a.cls, doneLabel: a.doneLabel,
      open: !isDone(a.key), done: isDone(a.key),
      run: () => mark(a.key)
    }));
    const moods = { smile: 'настроение хорошее', meh: 'настроение среднее', frown: 'тяжело' };

    return {
      modes: modeDefs.map((m) => ({
        ...m,
        cls: m.id === modeNow ? 'is-on' : '',
        pressed: m.id === modeNow ? 'true' : 'false',
        pick: () => this.setState(this.initial(m.id))
      })),
      query: s.query,
      typeQuery: (e) => this.setState({ query: e.target.value }),
      chips: chipDefs.map((c) => ({
        ...c,
        cls: c.id === s.chip ? 'chip is-on' : 'chip',
        pressed: c.id === s.chip ? 'true' : 'false',
        pick: () => this.setState({ chip: c.id, all: false })
      })),
      hasRows: filtered.length > 0,
      noRows: filtered.length === 0,
      resetFilters: () => this.setState({ query: '', chip: 'all' }),
      rows: shown.map((p) => ({
        name: p.name, ini: p.ini, ws: p.ws, oct: p.oct + ' ч',
        hasDot: !!p.dot, dot: p.dot || '', dotCls: p.dotCls || 'dot',
        avCls: 'avatar ' + p.av,
        cls: p.id === s.sel ? 'tbl-row vcols vrow is-sel' : 'tbl-row vcols vrow',
        pressed: p.id === s.sel ? 'true' : 'false',
        pick: () => this.setState({ sel: p.id, tab: 'overview' })
      })),
      hasMore: filtered.length > 4,
      moreLabel: s.all ? 'Свернуть' : 'Показать всех',
      moreExpanded: s.all ? 'true' : 'false',
      toggleMore: () => this.setState({ all: !s.all }),
      hasSel: !!s.sel,
      closePane: () => this.setState({ sel: null }),
      tabs: tabDefs.map((t) => ({
        ...t,
        cls: t.id === s.tab ? 'is-on' : '',
        selected: t.id === s.tab ? 'true' : 'false',
        pick: () => this.setState({ tab: t.id })
      })),
      tabOverview: s.tab === 'overview',
      tabHours: s.tab === 'hours',
      tabLearn: s.tab === 'learn',
      tabRefl: s.tab === 'refl',
      v: {
        name: cur.name, ini: cur.ini, role: cur.role,
        avCls: 'avatar avatar-xl ' + cur.av,
        isPaused: cur.st === 'pause',
        writeLabel: 'Написать ' + cur.dat,
        write: () => mark(pid + '-dm'),
        wroteNow: isDone(pid + '-dm'),
        hasPlaque: !!cur.plaque, plaque: cur.plaque || '',
        actions: actions,
        ov: cur.ov.map((o) => ({ t: o.t, isCal: o.ic === 'cal', isStar: o.ic === 'star', isClock: o.ic === 'clock', isUsers: o.ic === 'users', isPin: o.ic === 'pin' })),
        total: cur.total + ' ч', oct: cur.oct + ' ч',
        hasShifts: cur.shifts.length > 0,
        shifts: cur.shifts.map((x) => ({ d: x.d, w: x.w, h: x.h || '', miss: !!x.miss, ok: !x.miss })),
        tracks: cur.tracks.map((t) => ({ t: t.t, p: t.p, barCls: t.done ? 'bar bar-green' : 'bar', wCls: 'w' + t.w })),
        hasTrainer: !!cur.trainer, trainer: cur.trainer ? 'Тренажёр ' + cur.trainer : '',
        hasRefl: cur.refl.length > 0, noRefl: cur.refl.length === 0,
        refl: cur.refl.map((r) => ({
          d: r.d, text: r.text,
          isSmile: r.mood === 'smile', isMeh: r.mood === 'meh', isFrown: r.mood === 'frown',
          moodCls: 'mood mood-' + r.mood, moodLabel: moods[r.mood],
          hasFlag: !!r.flag, flag: r.flag || ''
        }))
      }
    };
  }
}