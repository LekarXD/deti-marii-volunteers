class Component extends DCLogic {
  constructor(props) {
    super(props);
    this.state = this.initial('open');
  }
  initial(mode) {
    return {
      sel: mode === 'board' ? null : 'max',
      step: mode === 'reject' ? 'reject' : 'none',
      stages: { alina: 'new', max: 'interview', oleg: 'docs', egor: 'training' },
      rejected: {},
      scheduled: {},
      nudged: {},
      slot: 'thu',
      moreQ: false
    };
  }
  renderVals() {
    const s = this.state;
    const people = {
      alina: { name: 'Алина Фёдорова', ini: 'АФ', av: 'av-p', date: '16 окт', dateFull: '16 октября', dat: 'Алине',
        line: 'Хочет помогать на мастер-классе по валянию.' },
      max: { name: 'Максим Ильин', ini: 'МИ', av: 'av-g', date: '18 окт', dateFull: '18 октября', dat: 'Максиму',
        about: '«Год вёл кружок звукозаписи для подростков. Хочу в музыкальную студию или киноклуб».', ai: true },
      oleg: { name: 'Олег Петров', ini: 'ОП', av: 'av-b', date: '5 окт', dateFull: '5 октября', dat: 'Олегу',
        line: 'Собеседование прошёл, ждём справку о несудимости.' },
      egor: { name: 'Егор Мельников', ini: 'ЕМ', av: 'av-y', date: '21 сен', dateFull: '21 сентября', dat: 'Егору',
        line: 'Проходит «Первые шаги», сейчас на втором модуле.' }
    };
    const slotDefs = [
      { id: 'thu', short: 'чт 22 окт, 19:30', full: 'чт 22 октября, 19:30', card: 'встреча 22 окт' },
      { id: 'sun', short: 'вс 25 окт, 12:00', full: 'вс 25 октября, 12:00', card: 'встреча 25 окт' },
      { id: 'mon', short: 'пн 26 окт, 19:30', full: 'пн 26 октября, 19:30', card: 'встреча 26 окт' }
    ];
    const slotById = {};
    slotDefs.forEach((x) => { slotById[x.id] = x; });
    const colDefs = [
      { id: 'new', label: 'Новая', hidden: 6 },
      { id: 'interview', label: 'Собеседование', hidden: 4 },
      { id: 'docs', label: 'Документы', hidden: 3 },
      { id: 'training', label: 'Обучение', hidden: 8 },
      { id: 'admitted', label: 'Допущен', hidden: 6 }
    ];
    const order = ['alina', 'max', 'oleg', 'egor'];
    const cardFor = (id) => {
      const p = people[id];
      const st = s.stages[id];
      const sel = s.sel === id;
      const sch = s.scheduled[id];
      let warn = '';
      if (id === 'alina' && st === 'new' && !sch) warn = '4 дня без ответа';
      if (id === 'egor' && st === 'training' && !s.nudged.egor) warn = '16 дней без прогресса';
      return {
        name: p.name, ini: p.ini,
        date: sch ? slotById[sch].card : p.date,
        avCls: 'avatar ' + p.av,
        cls: sel ? 'kcard is-sel' : 'kcard',
        pressed: sel ? 'true' : 'false',
        pick: () => this.setState({ sel: id, step: 'none', moreQ: false }),
        hasWarn: !!warn, warn: warn
      };
    };
    const cols = colDefs.map((c) => {
      const ids = order.filter((id) => s.stages[id] === c.id && !s.rejected[id]);
      return {
        label: c.label,
        count: c.hidden + ids.length,
        cards: ids.map(cardFor),
        hasMore: c.hidden > 0,
        more: c.hidden
      };
    });

    const id = s.sel;
    const p = id ? people[id] : people.max;
    const st = id ? s.stages[id] : 'interview';
    const sch = id ? s.scheduled[id] : null;
    const isRejected = !!(id && s.rejected[id]);
    const isRejecting = !!id && !isRejected && s.step === 'reject';
    const isPicking = !!id && !isRejected && s.step === 'pick';
    const inInterview = st === 'new' || st === 'interview';
    const nudgeable = st === 'docs' || st === 'training';
    const nudged = !!(id && s.nudged[id]);
    const idle = !!id && !isRejected && !isRejecting && !isPicking;
    const setStage = (val) => { const n = { ...s.stages }; n[id] = val; return n; };

    const modeNow = !s.sel ? 'board' : (s.step === 'reject' && s.sel === 'max' ? 'reject' : (s.sel === 'max' ? 'open' : ''));
    const modeDefs = [
      { id: 'board', label: 'Канбан' },
      { id: 'open', label: 'Кандидат открыт' },
      { id: 'reject', label: 'Отказ' }
    ];
    const roles = [
      { title: 'Киноклуб для выпускников', score: 86 },
      { title: 'Ассистент музыкальной студии', score: 74 },
      { title: 'Звук для спектакля', score: 61 }
    ];
    const Q = [
      'Ребёнок рассказывает о насилии и просит никому не говорить. Что сделаете?',
      'Подросток говорит: «Вы все приходите на пару раз». Что ответите?',
      'Ребёнок с аутизмом закрывает уши и кричит, на занятии стало громко. Что сделаете в первую минуту?',
      'Ребёнок просит ваш номер телефона. Ваши действия?',
      'Сколько месяцев готовы ходить к одной группе?'
    ];
    const shownQ = s.moreQ ? Q : Q.slice(0, 3);

    return {
      modes: modeDefs.map((m) => ({
        ...m,
        cls: m.id === modeNow ? 'is-on' : '',
        pressed: m.id === modeNow ? 'true' : 'false',
        pick: () => this.setState(this.initial(m.id))
      })),
      cols: cols,
      hasSel: !!id,
      candCls: p.ai ? 'cand' : 'cand is-solo',
      closePane: () => this.setState({ sel: null, step: 'none' }),
      cand: {
        name: p.name, ini: p.ini, dateFull: p.dateFull, dat: p.dat,
        avCls: 'avatar avatar-xl ' + p.av,
        hasAbout: !!p.about, about: p.about || '',
        hasLine: !p.about && !!p.line, line: p.line || '',
        hasAi: !!p.ai
      },
      showActs: idle && ((inInterview && !sch) || (nudgeable && !nudged) || st === 'admitted'),
      actInterview: inInterview && !sch,
      actNudge: nudgeable && !nudged,
      actAdmitted: st === 'admitted',
      canReject: st !== 'training' && st !== 'admitted',
      nudgeLabel: st === 'docs' ? 'Напомнить про справку' : 'Написать',
      nudge: () => { const n = { ...s.nudged }; n[id] = true; this.setState({ nudged: n }); },
      nudgeDone: idle && nudgeable && nudged,
      nudgeDoneLabel: st === 'docs' ? 'Напомнили про справку' : 'Написали, позвали на вводную',
      startPick: () => this.setState({ step: 'pick' }),
      isPicking: isPicking,
      slots: slotDefs.map((x) => ({
        label: x.short,
        cls: x.id === s.slot ? 'chip is-on' : 'chip',
        pressed: x.id === s.slot ? 'true' : 'false',
        pick: () => this.setState({ slot: x.id })
      })),
      schedule: () => {
        const n = { ...s.scheduled }; n[id] = s.slot;
        this.setState({ scheduled: n, stages: setStage('interview'), step: 'none' });
      },
      isScheduled: idle && inInterview && !!sch,
      scheduledLabel: sch ? 'Собеседование ' + slotById[sch].full : '',
      unschedule: () => { const n = { ...s.scheduled }; delete n[id]; this.setState({ scheduled: n, step: 'pick' }); },
      cancelStep: () => this.setState({ step: 'none' }),
      startReject: () => this.setState({ step: 'reject' }),
      isRejecting: isRejecting,
      sendReject: () => { const r = { ...s.rejected }; r[id] = true; this.setState({ rejected: r, step: 'none' }); },
      isRejected: isRejected,
      restore: () => { const r = { ...s.rejected }; delete r[id]; this.setState({ rejected: r, step: 'none' }); },
      roles: roles.map((r) => ({ ...r, aria: 'Совпадение ' + r.score + ' из 100' })),
      questions: shownQ.map((t, i) => ({ n: i + 1, text: t })),
      moreQLabel: s.moreQ ? 'Свернуть' : 'Ещё ' + (Q.length - 3),
      moreQExpanded: s.moreQ ? 'true' : 'false',
      toggleQ: () => this.setState({ moreQ: !s.moreQ })
    };
  }
}