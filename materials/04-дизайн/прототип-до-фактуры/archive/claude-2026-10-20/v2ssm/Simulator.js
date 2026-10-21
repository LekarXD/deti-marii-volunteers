class Component extends DCLogic {
  constructor(props) {
    super(props);
    this.state = { view: 'pick', sel: 's1', msgs: [], turn: 0, draft: '', hint: false, paused: false, curator: false, basis: false, open: 3, tr: false, disputed: false, stopText: '', act: '' };
  }
  renderVals() {
    const s = this.state;
    const SC = [
      { id: 's1', title: 'Отказывается участвовать', name: 'Миша', dat: 'Мише', ini: 'М', child: 'Миша, 9 лет', av: 'avatar av-o', art: 'art art-o', icon: 'palette',
        profile: 'Миша, 9 лет. Живёт в ЦССУ, третий месяц на живописи',
        sit: 'Все рисуют осенний пейзаж. Миша сидит в капюшоне, лист отодвинут.',
        first: { a: 'натягивает капюшон, отодвигает лист', t: 'Не буду я ничего рисовать. Это тупо.' },
        replies: [
          { a: '', t: 'Потому что. Отстань. У меня всё равно ничего не получается.' },
          { a: 'пауза', t: '…Ну да. В прошлый раз Петька ржал над моим рисунком.' },
          { a: '', t: 'Ладно… Дай синюю. Но рисовать не буду, только фон.' },
          { a: 'берёт синюю краску, проводит по краю листа', t: '…А если сверху белым, будет как небо?' },
          { a: 'рисует, не поднимая головы', t: 'Только никому не показывай.' }
        ],
        idle: { a: 'молча продолжает рисовать фон', t: '' },
        hints: ['Что Миша может сейчас чувствовать? Как сказать это вслух, не спрашивая «почему»?', 'Миша сказал, что у него не получается. Какой выбор дать, чтобы он мог участвовать хотя бы немного?', 'Миша сказал про насмешки. Что можно пообещать про сегодняшнее занятие?', 'Миша согласился только на фон. Как поддержать его, чтобы он не почувствовал, что его «поймали» на слове?'] },
      { id: 's2', title: 'Рассказывает о насилии', name: 'Даша', dat: 'Даше', ini: 'Д', child: 'Даша, 11 лет', av: 'avatar av-y', art: 'art art-y', icon: 'scissors', done: true, warn: true,
        profile: 'Даша, 11 лет. Живёт в ЦССУ, полгода ходит к тебе на валяние',
        sit: 'Конец занятия. Даша задерживается у стола, ведущий и дети через пару столов.',
        first: { a: 'тихо, не поднимая глаз', t: 'А если я тебе кое-что скажу, ты никому не расскажешь? Обещаешь?' },
        replies: [{ a: 'молчит, крутит в руках войлок', t: 'Тогда не скажу.' }, { a: 'тихо', t: 'Один взрослый… делает то, что мне не нравится. И говорит, что если я кому-то скажу, будет хуже.' }],
        idle: { a: 'молчит, смотрит на стол', t: '' },
        hints: ['Что ты можешь честно пообещать Даше, а что — нет?'] },
      { id: 's3', title: 'Ты придёшь ещё? Дай свой телефон', name: 'Аня', dat: 'Ане', ini: 'А', child: 'Аня, 10 лет', av: 'avatar av-g', art: 'art art-g', icon: 'phone', done: true,
        profile: 'Аня, 10 лет. Живёт в ЦССУ, ходит на лепку',
        sit: 'Конец занятия. Следующие две субботы тебя не будет — сессия.',
        first: { a: 'держит за рукав', t: 'А ты в следующую субботу придёшь? Дай свой номер, я тебе буду писать. А можно ты меня к себе заберёшь?' },
        replies: [{ a: 'дуется', t: 'Ну один раз! Я никому не скажу.' }, { a: 'отпускает рукав', t: 'А ты точно придёшь пятнадцатого?' }],
        idle: { a: 'кивает', t: '' },
        hints: ['Что ты точно знаешь о своих следующих субботах? И какой способ связи разрешён правилами фонда?'] },
      { id: 's4', title: 'Сенсорная перегрузка', name: 'Тимур', dat: 'Тимуру', ini: 'Т', child: 'Тимур, 8 лет', av: 'avatar av-v', art: 'art art-v', icon: 'music',
        profile: 'Тимур, 8 лет, аутизм. Живёт в приёмной семье, ходит в музыкальную студию',
        sit: 'Группа играет на барабанах. Тимур зажимает уши, раскачивается и кричит.',
        first: { a: 'зажимает уши, раскачивается, кричит', t: 'Нет! Нет! Громко! Громко!' },
        replies: [{ a: 'раскачивается, тише', t: 'Громко… громко…' }, { a: 'убирает руки от ушей, смотрит в пол', t: '' }],
        idle: { a: 'сидит тихо, дышит ровнее', t: '' },
        hints: ['Что вокруг Тимура можно сделать тише прямо сейчас?'] },
      { id: 's5', title: 'Ударил другого ребёнка', name: 'Костя', dat: 'Косте', ini: 'К', child: 'Костя, 7 лет', av: 'avatar av-p', art: 'art art-p', icon: 'hand',
        profile: 'Костя, 7 лет. Живёт в ЦССУ, ходит на лепку',
        sit: 'Соседка взяла пластилин Кости. Он ударил её по руке, она плачет.',
        first: { a: 'толкает девочку, сжимает кулаки', t: 'Это моё! Она забрала! Я её ненавижу!' },
        replies: [{ a: 'сжимает кулаки', t: 'Она первая начала!' }, { a: 'выдыхает', t: '…Это моё. Отдай, пожалуйста.' }],
        idle: { a: 'молча лепит', t: '' },
        hints: ['Кто сейчас в безопасности, а кто нет? С чего начать?'] },
      { id: 's6', title: 'Подросток грубит', name: 'Влад', dat: 'Владу', ini: 'В', child: 'Влад, 14 лет', av: 'avatar av-b', art: 'art art-b', icon: 'film',
        profile: 'Влад, 14 лет. Живёт в ЦССУ, ходит в киноклуб',
        sit: 'Ты второй раз ведёшь обсуждение фильма. Влад демонстративно перебивает.',
        first: { a: '', t: 'Ты чё тут вообще забыла? Тебе за это платят? Вы все приходите пару раз поиграть в добреньких, а потом сваливаете.' },
        replies: [{ a: '', t: 'Ну и что ты мне сделаешь?' }, { a: 'пожимает плечами', t: 'Ладно. А фильм кто выбирает?' }],
        idle: { a: 'смотрит в телефон, но слушает', t: '' },
        hints: ['Что может стоять за словами Влада? Что ты честно можешь сказать о своих сроках?'] }
    ];
    const iconFlags = (c) => ({ isPalette: c.icon === 'palette', isScissors: c.icon === 'scissors', isPhone: c.icon === 'phone', isMusic: c.icon === 'music', isHand: c.icon === 'hand', isFilm: c.icon === 'film' });
    const curRaw = SC.find((x) => x.id === s.sel) || SC[0];
    const cur = Object.assign({}, curRaw, iconFlags(curRaw));
    const prefill = [
      { who: 'kid', a: 'натягивает капюшон, отодвигает лист', t: 'Не буду я ничего рисовать. Это тупо.' },
      { who: 'me', t: 'Миш, ну все же рисуют, давай хотя бы попробуешь? Почему ты не хочешь?' },
      { who: 'kid', t: 'Потому что. Отстань. У меня всё равно ничего не получается.' },
      { who: 'me', t: 'Поняла. Похоже, неприятно, когда кажется, что не получится. Так у многих бывает.' },
      { who: 'kid', a: 'пауза', t: '…Ну да. В прошлый раз Петька ржал над моим рисунком.' },
      { who: 'me', t: 'Обидно, когда смеются. Сегодня никто не обязан показывать свой рисунок. Можешь посидеть рядом со мной, а можешь выбрать краски для фона. Как тебе лучше?' },
      { who: 'kid', t: 'Ладно… Дай синюю. Но рисовать не буду, только фон.' }
    ];
    const transcript = prefill.concat([{ who: 'me', t: 'Договорились. Вот видишь, а говорил — тупо!' }]);
    const msgView = (sc) => (m) => ({
      rowCls: m.who === 'me' ? 'msg msg-me' : 'msg',
      isKid: m.who !== 'me',
      av: sc.av,
      ini: sc.ini,
      who: m.who === 'me' ? 'Ты' : sc.name,
      bCls: m.who === 'me' ? 'bb bb-me' : 'bb bb-kid',
      hasA: !!m.a,
      a: m.a || '',
      t: m.t || ''
    });
    const toChat = (id) => {
      const sc = SC.find((x) => x.id === id) || SC[0];
      this.setState({ view: 'chat', sel: sc.id, msgs: [{ who: 'kid', a: sc.first.a, t: sc.first.t }], turn: 0, draft: '', hint: false, paused: false });
    };
    const presets = {
      pick: { view: 'pick', sel: 's1', curator: false, basis: false },
      chat: { view: 'chat', sel: 's1', msgs: prefill, turn: 3, draft: '', hint: false, paused: false },
      review: { view: 'review', sel: 's1', open: 3, tr: false, disputed: false },
      stop: { view: 'stop', sel: 's1', stopText: 'мне тяжело, у меня у самой такое было', act: '' }
    };
    const viewDefs = [
      { id: 'pick', label: 'Выбор' },
      { id: 'chat', label: 'Диалог' },
      { id: 'review', label: 'Разбор' },
      { id: 'stop', label: 'Стоп-кран' }
    ];
    const send = () => {
      const text = (s.draft || '').trim();
      if (!text) return;
      if (/тяжело|не могу больше|мне плохо|у самой|у самого|со мной тоже/i.test(text)) {
        this.setState({ view: 'stop', stopText: text, draft: '', act: '' });
        return;
      }
      const r = cur.replies[s.turn] || cur.idle;
      this.setState({ msgs: s.msgs.concat([{ who: 'me', t: text }, { who: 'kid', a: r.a, t: r.t }]), turn: s.turn + 1, draft: '', hint: false });
    };
    const reviewDefs = [
      { t: 'Контакт до просьбы', score: 1, quote: '«Миш, ну все же рисуют, давай хотя бы попробуешь?»',
        insteadLabel: 'Сказать вместо', instead: '«Вижу, сегодня не хочется. Можно я посижу рядом?»' },
      { t: 'Принятие и любопытство', score: 1, quote: '«Почему ты не хочешь?»',
        insteadLabel: 'Сказать вместо', instead: 'Сразу назвать чувство, без «почему»: «Похоже, неприятно, когда кажется, что не получится».' },
      { t: 'Выбор и голос', score: 2, quote: '«Можешь посидеть рядом со мной, а можешь выбрать краски для фона. Как тебе лучше?»',
        insteadLabel: 'Так и держи', instead: 'Два приемлемых варианта — и Миша включился.' },
      { t: 'Без стыда и сравнения', score: 0, quote: '«Ну все же рисуют», «Вот видишь, а говорил — тупо!»',
        insteadLabel: 'Сказать вместо', instead: '«Договорились, только фон. Мне нравится этот синий».' },
      { t: 'Предсказуемость, дверь открыта', score: 2, quote: '«Сегодня никто не обязан показывать свой рисунок»',
        insteadLabel: 'Можно добавить', instead: '«Я за этим столом до конца — позови, если захочешь дальше».' }
    ];
    const scoreWord = ['0 баллов из 2', '1 балл из 2', '2 балла из 2'];
    const actDefs = [
      { id: 'talk', title: 'Поговорить с психологом', art: 'art art-v' },
      { id: 'stop', title: 'Закончить на сегодня', art: 'art art-o' },
      { id: 'later', title: 'Вернуться позже', art: 'art art-b' }
    ];
    return {
      views: viewDefs.map((v) => ({
        ...v,
        cls: v.id === s.view ? 'is-on' : '',
        pressed: v.id === s.view ? 'true' : 'false',
        pick: () => this.setState(presets[v.id])
      })),
      isPick: s.view === 'pick',
      isChat: s.view === 'chat',
      isReview: s.view === 'review',
      isStop: s.view === 'stop',
      cur,
      curWarn: !!cur.warn,
      curPlain: !cur.warn,
      showCurator: !!cur.warn && !s.curator,
      curatorAsked: !!cur.warn && s.curator,
      askCurator: () => this.setState({ curator: true }),
      start: () => toChat(cur.id),
      scenarios: SC.map((c) => Object.assign({
        title: c.title,
        child: c.child,
        art: c.art,
        warn: !!c.warn,
        done: !!c.done,
        cls: c.id === s.sel ? 'card scn is-on' : 'card scn',
        pressed: c.id === s.sel ? 'true' : 'false',
        pick: () => this.setState({ sel: c.id, curator: false })
      }, iconFlags(c))),
      basisOpen: s.basis,
      basisExpanded: s.basis ? 'true' : 'false',
      basisChev: s.basis ? 'chev is-open' : 'chev',
      toggleBasis: () => this.setState({ basis: !s.basis }),
      methods: ['TBRI', 'PACE', 'SAMHSA', 'NSPCC', 'Darkness to Light', 'Keeping Children Safe', 'MENTOR', 'CPI', 'Studio III', 'National Autistic Society'],
      msgs: s.msgs.map(msgView(cur)),
      isPaused: s.paused,
      notPaused: !s.paused,
      pauseCls: s.paused ? 'pause is-on' : 'pause',
      pausePressed: s.paused ? 'true' : 'false',
      togglePause: () => this.setState({ paused: !s.paused, hint: false }),
      resume: () => this.setState({ paused: false }),
      toStop: () => this.setState({ view: 'stop', stopText: '', act: '', paused: false }),
      hintOpen: s.hint,
      hintExpanded: s.hint ? 'true' : 'false',
      toggleHint: () => this.setState({ hint: !s.hint }),
      hintText: cur.hints[Math.min(s.turn, cur.hints.length - 1)],
      placeholder: 'Что ты скажешь ' + cur.dat + '?',
      draft: s.draft,
      typeDraft: (e) => this.setState({ draft: e.target.value }),
      send,
      finish: () => this.setState({ view: 'review', sel: 's1', open: 3, tr: false, disputed: false }),
      retry: () => toChat('s1'),
      disputed: s.disputed,
      notDisputed: !s.disputed,
      dispute: () => this.setState({ disputed: true }),
      review: reviewDefs.map((c, i) => ({
        t: c.t,
        quote: c.quote,
        insteadLabel: c.insteadLabel,
        instead: c.instead,
        dotsCls: 'dots d' + c.score,
        d1: 'on',
        d2: c.score >= 1 ? 'on' : '',
        d3: c.score >= 2 ? 'on' : '',
        scoreLabel: scoreWord[c.score],
        open: s.open === i,
        expanded: s.open === i ? 'true' : 'false',
        chevCls: s.open === i ? 'chev is-open' : 'chev',
        toggle: () => this.setState({ open: s.open === i ? -1 : i })
      })),
      trOpen: s.tr,
      trExpanded: s.tr ? 'true' : 'false',
      trLabel: s.tr ? 'Скрыть диалог' : 'Весь диалог',
      toggleTr: () => this.setState({ tr: !s.tr }),
      transcript: transcript.map(msgView(SC[0])),
      careLead: cur.name + ' подождёт, попытка не считается. Разбираться с этим одной не нужно.',
      stopActs: actDefs.map((a) => ({
        ...a,
        isTalk: a.id === 'talk',
        isStop: a.id === 'stop',
        isLater: a.id === 'later',
        cls: s.act === a.id ? 'card tile is-on' : 'card tile',
        pressed: s.act === a.id ? 'true' : 'false',
        pick: () => this.setState({ act: s.act === a.id ? '' : a.id })
      })),
      actTalk: s.act === 'talk',
      actDone: s.act === 'stop' || s.act === 'later',
      actDoneText: s.act === 'later' ? 'Сохранили место, сценарий подождёт' : 'Сценарий остановлен, попытка не засчитана'
    };
  }
}
