class Component extends DCLogic {
  constructor(props) {
    super(props);
    this.state = { mode: 'answer', q: '', cite: '', sent: false, passed: false, reported: false, draft: '', asked: [] };
  }
  renderVals() {
    const s = this.state;
    const DEFQ = {
      answer: 'Ребёнок попросил мой номер телефона. Что ответить?',
      none: 'Можно ли взять детей из группы в музей в выходной?',
      urgent: 'Девочка после занятия сказала, что один взрослый делает ей плохо, и попросила никому не говорить. Что делать?'
    };
    const clean = { cite: '', sent: false, passed: false, reported: false };
    const route = (t) => {
      if (/насил|обижа|бьёт|бьет|наказыва|трога|делает .*плохо|никому не говорить/i.test(t)) return 'urgent';
      if (/телефон|номер|соцсет|друзья|переписк|контакт/i.test(t)) return 'answer';
      return 'none';
    };
    const modeDefs = [
      { id: 'answer', label: 'Ответ' },
      { id: 'none', label: 'Нет ответа' },
      { id: 'urgent', label: 'Срочная ситуация' }
    ];
    const ANS = [
      { id: 'code', label: 'Кодекс волонтёра, п. 4.2', title: 'Кодекс волонтёра, пункт 4.2',
        text: 'Волонтёр не даёт детям личные номера телефонов, адреса и ссылки на свои страницы в соцсетях и не переписывается с ними лично. Связь с ребёнком вне занятий — только через координатора.' },
      { id: 'memo', label: 'Памятка «Границы»', title: 'Памятка «Границы», раздел «Личные контакты»',
        text: 'Если ребёнок просит твой номер: признай, что ему важно не потерять связь, объясни, что правило одно для всех взрослых, и предложи открытку через координатора.' },
      { id: 'lesson', label: 'Урок «Правила безопасности»', title: 'Урок «Правила безопасности и границы»',
        text: 'Любое общение с ребёнком должно быть на виду у других взрослых. Никаких контактов один на один, в том числе в переписке.', href: 'Lesson.dc.html', link: 'Открыть урок' }
    ];
    const URG = [
      { id: 'nspcc', label: 'NSPCC: если ребёнок рассказал', title: 'NSPCC, «Recognising and responding to abuse», перевод фонда',
        text: 'Слушать, не перебивая. Сказать, что ребёнок правильно сделал, что рассказал, и что это не его вина. Не обещать сохранить тайну. Дословно записать слова ребёнка и как можно скорее действовать по процедурам организации.' },
      { id: 'reg', label: 'Регламент «Сигнал о ребёнке»', title: 'Регламент фонда «Сигнал о ребёнке», пункт 2',
        text: 'Волонтёр сообщает психологу или координатору в тот же день. Сам не выясняет обстоятельства, не обсуждает услышанное с тем, на кого указал ребёнок, и не расспрашивает других детей.' }
    ];
    const citeDefs = s.mode === 'urgent' ? URG : ANS;
    const open = citeDefs.find((c) => c.id === s.cite);
    const defaults = [
      { q: 'Ребёнок попросил мой номер телефона', mode: 'answer', custom: false },
      { q: 'Можно ли взять детей в музей в выходной?', mode: 'none', custom: false },
      { q: 'Девочка просит никому не говорить, что её обижают', mode: 'urgent', custom: false }
    ];
    const history = s.asked.map((a) => ({ q: a.q, mode: a.mode, custom: true })).concat(defaults).slice(0, 4).map((h) => {
      const on = h.custom ? s.q === h.q : (!s.q && s.mode === h.mode);
      return {
        q: h.q,
        cls: on ? 'hist is-on' : 'hist',
        pressed: on ? 'true' : 'false',
        pick: () => this.setState(Object.assign({ mode: h.mode, q: h.custom ? h.q : '' }, clean))
      };
    });
    return {
      modes: modeDefs.map((m) => ({
        ...m,
        cls: m.id === s.mode ? 'is-on' : '',
        pressed: m.id === s.mode ? 'true' : 'false',
        pick: () => this.setState(Object.assign({ mode: m.id, q: '' }, clean))
      })),
      isAnswer: s.mode === 'answer',
      isNone: s.mode === 'none',
      isUrgent: s.mode === 'urgent',
      question: s.q || DEFQ[s.mode],
      history,
      cites: citeDefs.map((c) => ({
        label: c.label,
        cls: s.cite === c.id ? 'cite is-on' : 'cite',
        expanded: s.cite === c.id ? 'true' : 'false',
        toggle: () => this.setState({ cite: s.cite === c.id ? '' : c.id })
      })),
      citeOpen: !!open,
      citeTitle: open ? open.title : '',
      citeText: open ? open.text : '',
      citeHasLink: !!(open && open.href),
      citeHref: open && open.href ? open.href : '',
      citeLinkLabel: open && open.link ? open.link : '',
      notSent: !s.sent,
      sent: s.sent,
      sendCoord: () => this.setState({ sent: true }),
      notPassed: !s.passed,
      passed: s.passed,
      passQ: () => this.setState({ passed: true }),
      notReported: !s.reported,
      reported: s.reported,
      report: () => this.setState({ reported: true }),
      draft: s.draft,
      typeDraft: (e) => this.setState({ draft: e.target.value }),
      ask: () => {
        const t = (s.draft || '').trim();
        if (!t) return;
        const m = route(t);
        this.setState(Object.assign({ mode: m, q: t, draft: '', asked: [{ q: t, mode: m }].concat(s.asked).slice(0, 4) }, clean));
      }
    };
  }
}
