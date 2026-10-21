
class DCLogic { constructor(props){ this.props = props; this.state = {}; } setState(p){ this.state = Object.assign({}, this.state, p); } }

class Component extends DCLogic {
  constructor(props) {
    super(props);
    this.state = { view: 'pick', sel: 's1', msgs: [], turn: 0, draft: '', hint: false, paused: false, curator: false, tr: false, disputed: false, fromOther: false, stopText: '', stopAct: '', talk: false, booked: false };
  }
  renderVals() {
    const s = this.state;
    const SC = [
      { id: 's1', title: 'Отказывается участвовать', name: 'Миша', dat: 'Мише', ini: 'М', child: 'Миша, 9 лет', av: 'avatar av-o', art: 'art art-o', icon: 'palette', status: 'new',
        line: 'Миша, 9 лет, живопись', short: 'Сначала контакт, потом просьба; выбор без давления',
        where: 'ЦССУ', about: 'Живопись, третий месяц. Тебя знает', traits: 'Замкнутый, неудачи переживает остро',
        sit: 'Все начали рисовать осенний пейзаж. Миша сидит в капюшоне, лист отодвинут.',
        practice: 'Сначала контакт, потом просьба. Принять нежелание без давления и стыда. Дать выбор, при котором можно участвовать частично.',
        basis: ['TBRI', 'PACE', 'SAMHSA', 'Сигел'],
        crit: [{ t: 'Контакт до просьбы' }, { t: 'Принятие и любопытство' }, { t: 'Выбор и голос' }, { t: 'Без стыда и сравнения' }, { t: 'Предсказуемость, дверь открыта' }],
        first: { a: 'натягивает капюшон, отодвигает лист', t: 'Не буду я ничего рисовать. Это тупо.' },
        replies: [
          { a: '', t: 'Потому что. Отстань. У меня всё равно ничего не получается.' },
          { a: 'пауза', t: '…Ну да. В прошлый раз Петька ржал над моим рисунком.' },
          { a: '', t: 'Ладно… Дай синюю. Но рисовать не буду, только фон.' },
          { a: 'берёт синюю краску, проводит по краю листа', t: '…А если сверху белым, будет как небо?' },
          { a: 'рисует, не поднимая головы', t: 'Только никому не показывай.' }
        ],
        idle: { a: 'молча продолжает рисовать фон', t: '' },
        hints: ['Что Миша может сейчас чувствовать? Как сказать это вслух, не спрашивая «почему»?', 'Миша сказал, что у него не получается. Какой выбор дать, чтобы он мог участвовать хотя бы немного?', 'Миша сказал про насмешки. Что можно пообещать про сегодняшнее занятие, чтобы ему было безопасно?', 'Миша согласился только на фон. Как поддержать его, чтобы он не почувствовал, что его «поймали» на слове?'] },
      { id: 's2', title: 'Рассказывает о насилии', name: 'Даша', dat: 'Даше', ini: 'Д', child: 'Даша, 11 лет', av: 'avatar av-y', art: 'art art-y', icon: 'scissors', status: 'done', warn: true,
        line: 'Даша, 11 лет, валяние', short: 'Не обещать тайну и сразу передать психологу',
        where: 'ЦССУ', about: 'Валяние. Занимаетесь вместе полгода', traits: 'Доверяет тебе',
        sit: 'Конец занятия. Даша задерживается у стола. Ведущий и другие дети в той же комнате, через пару столов.',
        practice: 'Не обещать тайну и не оттолкнуть. Спокойно выслушать, поддержать без наводящих вопросов, объяснить, что будет дальше. Сразу передать психологу или координатору и записать слова ребёнка дословно.',
        basis: ['NSPCC', 'Darkness to Light', 'Keeping Children Safe', 'MENTOR'],
        crit: [{ t: 'Не обещает тайну', crit: true }, { t: 'Спокойно слушает, без наводящих вопросов' }, { t: 'Поддерживает и верит' }, { t: 'Объясняет, что будет дальше' }, { t: 'Сообщает по протоколу', crit: true }],
        first: { a: 'тихо, не поднимая глаз', t: 'А если я тебе кое-что скажу, ты никому не расскажешь? Обещаешь?' },
        replies: [{ a: 'молчит, крутит в руках войлок', t: 'Тогда не скажу.' }, { a: 'тихо', t: 'Один взрослый… делает то, что мне не нравится. И говорит, что если я кому-то скажу, будет хуже.' }],
        idle: { a: 'молчит, смотрит на стол', t: '' },
        hints: ['Что ты можешь честно пообещать Даше, а что — нет?'] },
      { id: 's3', title: 'Ты придёшь ещё? Дай свой телефон', name: 'Аня', dat: 'Ане', ini: 'А', child: 'Аня, 10 лет', av: 'avatar av-g', art: 'art art-g', icon: 'hand', status: 'done',
        line: 'Аня, 10 лет, лепка', short: 'Тёплая граница по личным контактам, честно о будущем',
        where: 'ЦССУ', about: 'Лепка', traits: 'Быстро привязывается, держится за руку',
        sit: 'Конец занятия. Следующие две субботы тебя не будет — сессия.',
        practice: 'Честно сказать про будущее. Тепло, но твёрдо держать границу по личным контактам. Признать чувство за просьбой и попрощаться предсказуемо.',
        basis: ['NSPCC', 'MENTOR', 'PACE', 'TBRI'],
        crit: [{ t: 'Не даёт личных контактов', crit: true }, { t: 'Честность о будущем' }, { t: 'Признаёт чувство' }, { t: 'Бережный ответ про усыновление' }, { t: 'Предсказуемое прощание' }],
        first: { a: 'держит за рукав', t: 'А ты в следующую субботу придёшь? Дай свой номер, я тебе буду писать. А можно ты меня к себе заберёшь?' },
        replies: [{ a: 'дуется', t: 'Ну один раз! Я никому не скажу.' }, { a: 'отпускает рукав', t: 'А ты точно придёшь пятнадцатого?' }],
        idle: { a: 'кивает', t: '' },
        hints: ['Что ты точно знаешь о своих следующих субботах? И какой способ связи разрешён правилами фонда?'] },
      { id: 's4', title: 'Сенсорная перегрузка у ребёнка с аутизмом', name: 'Тимур', dat: 'Тимуру', ini: 'Т', child: 'Тимур, 8 лет', av: 'avatar av-v', art: 'art art-v', icon: 'music', status: 'new',
        line: 'Тимур, 8 лет, музыкальная студия', short: 'Распознать перегрузку, убрать шум, говорить минимум',
        where: 'Приёмная семья', about: 'Музыкальная студия', traits: 'Аутизм. Спокоен с маленькими инструментами',
        sit: 'Сегодня группа играет на барабанах. Тимур зажимает уши, раскачивается, кричит, бросает палочку.',
        practice: 'Отличить срыв от перегрузки от каприза. Убрать раздражители, говорить минимум, обеспечить безопасность без хватания и дать время.',
        basis: ['National Autistic Society', 'Studio III', 'CPI'],
        crit: [{ t: 'Распознаёт мелтдаун' }, { t: 'Снижает раздражители' }, { t: 'Минимум слов и требований' }, { t: 'Безопасность без давления' }, { t: 'Восстановление и передача' }],
        first: { a: 'зажимает уши, раскачивается, кричит', t: 'Нет! Нет! Громко! Громко!' },
        replies: [{ a: 'раскачивается, тише', t: 'Громко… громко…' }, { a: 'убирает руки от ушей, смотрит в пол', t: '' }],
        idle: { a: 'сидит тихо, дышит ровнее', t: '' },
        hints: ['Что вокруг Тимура можно сделать тише прямо сейчас?'] },
      { id: 's5', title: 'Ударил другого ребёнка', name: 'Костя', dat: 'Косте', ini: 'К', child: 'Костя, 7 лет', av: 'avatar av-g', art: 'art art-g', icon: 'hand', status: 'fail',
        line: 'Костя, 7 лет, лепка', short: 'Сначала безопасность; чувство — да, удар — нет',
        where: 'ЦССУ', about: 'Лепка', traits: 'Импульсивный, бурно реагирует, когда что-то забирают',
        sit: 'Соседка по столу взяла пластилин Кости. Он ударил её по руке, она плачет.',
        practice: 'Сначала безопасность. Спокойный низкий голос, мало слов. Назвать чувство, но не оправдывать удар, а когда успокоится — «переиграть».',
        basis: ['TBRI', 'CPI', 'PACE', 'Studio III'],
        crit: [{ t: 'Безопасность прежде всего', crit: true }, { t: 'Тон и темп' }, { t: 'Чувство — да, удар — нет' }, { t: 'Коррекция поведения, а не личности' }, { t: 'Сообщает об инциденте' }],
        first: { a: 'толкает девочку, сжимает кулаки', t: 'Это моё! Она забрала! Я её ненавижу!' },
        replies: [{ a: 'сжимает кулаки', t: 'Она первая начала!' }, { a: 'выдыхает', t: '…Это моё. Отдай, пожалуйста.' }],
        idle: { a: 'молча лепит', t: '' },
        hints: ['Кто сейчас в безопасности, а кто нет? С чего начать?'] },
      { id: 's6', title: 'Подросток грубит и провоцирует', name: 'Влад', dat: 'Владу', ini: 'В', child: 'Влад, 14 лет', av: 'avatar av-b', art: 'art art-b', icon: 'film', status: 'new',
        line: 'Влад, 14 лет, киноклуб', short: 'Не поддаться на провокацию, честно о своих сроках',
        where: 'ЦССУ', about: 'Киноклуб', traits: 'Видел много волонтёров, многие пропадали',
        sit: 'Ты второй раз ведёшь обсуждение фильма. Влад сидит развалившись и демонстративно перебивает.',
        practice: 'Не поддаться на провокацию и услышать, что за словами. Честно сказать о своих сроках, обозначить границу без морали и дать роль.',
        basis: ['CPI', 'PACE', 'SAMHSA', 'MENTOR'],
        crit: [{ t: 'Не реагирует на провокацию' }, { t: 'Слышит то, что за словами' }, { t: 'Честно о себе и своих сроках' }, { t: 'Уважительная граница' }, { t: 'Роль и выбор' }],
        first: { a: '', t: 'Ты чё тут вообще забыла? Тебе за это платят? Вы все приходите пару раз поиграть в добреньких, а потом сваливаете.' },
        replies: [{ a: '', t: 'Ну и что ты мне сделаешь?' }, { a: 'пожимает плечами', t: 'Ладно. А фильм кто выбирает?' }],
        idle: { a: 'смотрит в телефон, но слушает', t: '' },
        hints: ['Что может стоять за словами Влада? Что ты честно можешь сказать о своих сроках?'] }
    ];
    const cur = SC.find((x) => x.id === s.sel) || SC[0];
    const prefill = [
      { who: 'child', a: 'натягивает капюшон, отодвигает лист', t: 'Не буду я ничего рисовать. Это тупо.' },
      { who: 'me', t: 'Миш, ну все же рисуют, давай хотя бы попробуешь? Почему ты не хочешь?' },
      { who: 'child', t: 'Потому что. Отстань. У меня всё равно ничего не получается.' },
      { who: 'me', t: 'Поняла. Похоже, неприятно, когда кажется, что не получится. Так у многих бывает.' },
      { who: 'child', a: 'пауза', t: '…Ну да. В прошлый раз Петька ржал над моим рисунком.' },
      { who: 'me', t: 'Обидно, когда смеются. Сегодня никто не обязан показывать свой рисунок. Можешь посидеть рядом со мной и посмотреть, а можешь выбрать краски для фона. Как тебе лучше?' },
      { who: 'child', t: 'Ладно… Дай синюю. Но рисовать не буду, только фон.' }
    ];
    const transcript = prefill.concat([{ who: 'me', t: 'Договорились. Вот видишь, а говорил — тупо!' }]);
    const msgView = (name) => (m) => ({
      rowCls: m.who === 'me' ? 'msg msg-me' : 'msg',
      who: m.who === 'me' ? 'Ты' : name,
      bubbleCls: m.who === 'me' ? 'bubble bubble-me' : 'bubble bubble-them',
      hasA: !!m.a,
      a: m.a || '',
      t: m.t || ''
    });
    const toChat = (id) => {
      const sc = SC.find((x) => x.id === id) || SC[0];
      this.setState({ view: 'chat', sel: sc.id, msgs: [{ who: 'child', a: sc.first.a, t: sc.first.t }], turn: 0, draft: '', hint: false, paused: false });
    };
    const presets = {
      pick: { view: 'pick', sel: 's1', curator: false },
      chat: { view: 'chat', sel: 's1', msgs: prefill, turn: 3, draft: '', hint: false, paused: false },
      review: { view: 'review', sel: 's1', tr: false, disputed: false, fromOther: false },
      stop: { view: 'stop', sel: 's1', stopText: 'мне тяжело, у меня у самой такое было', stopAct: '', talk: false, booked: false }
    };
    const viewDefs = [
      { id: 'pick', label: 'Выбор сценария' },
      { id: 'chat', label: 'Диалог' },
      { id: 'review', label: 'Разбор' },
      { id: 'stop', label: 'Стоп-кран' }
    ];
    const send = () => {
      const text = (s.draft || '').trim();
      if (!text) return;
      if (/тяжело|не могу больше|мне плохо|у самой|у самого|со мной тоже/i.test(text)) {
        this.setState({ view: 'stop', stopText: text, draft: '', stopAct: '', talk: false, booked: false });
        return;
      }
      const r = cur.replies[s.turn] || cur.idle;
      this.setState({ msgs: s.msgs.concat([{ who: 'me', t: text }, { who: 'child', a: r.a, t: r.t }]), turn: s.turn + 1, draft: '', hint: false });
    };
    const reviewDefs = [
      { t: 'Контакт до просьбы', score: 1, basis: ['TBRI: связь', 'Сигел: соединись и перенаправь'], where: 'Реплика 2',
        quote: '«Миш, ну все же рисуют, давай хотя бы попробуешь?»', note: 'Первая реплика сразу про задание. Контакт появился только в реплике 4.',
        insteadLabel: 'Сказать вместо', instead: '«Вижу, сегодня не хочется. Можно я посижу рядом?»' },
      { t: 'Принятие и любопытство', score: 1, basis: ['PACE', 'Сигел: назови, чтобы приручить'], where: 'Реплики 2 и 4',
        quote: '«Почему ты не хочешь?» … «Похоже, неприятно, когда кажется, что не получится»', note: 'Чувство названо хорошо. Но «почему» до этого звучит как допрос.',
        insteadLabel: 'Как лучше', instead: 'Сразу назвать возможное чувство, без «почему».' },
      { t: 'Выбор и голос', score: 2, basis: ['SAMHSA: голос и выбор', 'TBRI: выбор'], where: 'Реплика 6',
        quote: '«Можешь посидеть рядом со мной и посмотреть, а можешь выбрать краски для фона. Как тебе лучше?»', note: 'Два приемлемых варианта, и Миша включился.',
        insteadLabel: '', instead: '' },
      { t: 'Без стыда и сравнения', score: 0, basis: ['TBRI IDEAL: оценивать поступок, не ребёнка'], where: 'Реплики 2 и 8',
        quote: '«ну все же рисуют», «Вот видишь, а говорил — тупо!»', note: 'Сравнение с другими и «я же говорил». Ребёнку, который боится насмешек, это может снова закрыть дверь.',
        insteadLabel: 'Сказать вместо', instead: '«Договорились, только фон. Мне нравится этот синий».' },
      { t: 'Предсказуемость, дверь открыта', score: 2, basis: ['SAMHSA: безопасность и доверие'], where: 'Реплика 6',
        quote: '«Сегодня никто не обязан показывать свой рисунок»', note: 'Снимает главный страх — насмешки — и задаёт безопасные правила.',
        insteadLabel: 'Можно добавить', instead: '«Я за этим столом до конца — позови, если захочешь дальше».' }
    ];
    const hasCrit = cur.crit.some((k) => k.crit);
    const hints = cur.hints;
    return {
      views: viewDefs.map((v) => ({
        ...v,
        cls: v.id === s.view ? 'is-on' : '',
        pressed: v.id === s.view ? 'true' : 'false',
        pick: () => this.setState(presets[v.id])
      })),
      isPick: s.view === 'pick',
      notPick: s.view !== 'pick',
      isChat: s.view === 'chat',
      isReview: s.view === 'review',
      isStop: s.view === 'stop',
      toPick: () => this.setState({ view: 'pick', paused: false }),
      cur,
      curAvLg: cur.av + ' avatar-lg',
      scenarios: SC.map((c) => ({
        title: c.title,
        line: c.line,
        short: c.short,
        art: c.art,
        warn: !!c.warn,
        next: c.id === 's1',
        isPalette: c.icon === 'palette',
        isScissors: c.icon === 'scissors',
        isHand: c.icon === 'hand',
        isMusic: c.icon === 'music',
        isFilm: c.icon === 'film',
        stCls: c.status === 'done' ? 'dot dot-green' : (c.status === 'fail' ? 'dot dot-orange' : 'dot'),
        stLabel: c.status === 'done' ? 'Пройден' : (c.status === 'fail' ? 'Не пройден' : 'Новый'),
        cls: c.id === s.sel ? 'scn is-on' : 'scn',
        pressed: c.id === s.sel ? 'true' : 'false',
        pick: () => this.setState({ sel: c.id, curator: false })
      })),
      curCrit: cur.crit.map((k) => ({ t: k.t, crit: !!k.crit })),
      curRule: hasCrit ? 'За каждый 0–2 балла. Порог — 7 из 10 и ни одного нуля по критическим.' : 'За каждый 0–2 балла. Порог — 7 из 10.',
      curBasis: cur.basis,
      curWarn: !!cur.warn,
      showCurator: !!cur.warn && !s.curator,
      curatorAsked: !!cur.warn && s.curator,
      askCurator: () => this.setState({ curator: true }),
      start: () => toChat(cur.id),
      methods: ['TBRI', 'PACE', 'SAMHSA', 'NSPCC', 'Darkness to Light', 'Keeping Children Safe', 'MENTOR', 'CPI', 'Studio III', 'National Autistic Society'],
      msgs: s.msgs.map(msgView(cur.name)),
      isPaused: s.paused,
      notPaused: !s.paused,
      pause: () => this.setState({ paused: true, hint: false }),
      resume: () => this.setState({ paused: false }),
      hintOpen: s.hint,
      hintExpanded: s.hint ? 'true' : 'false',
      toggleHint: () => this.setState({ hint: !s.hint }),
      hintText: hints[Math.min(s.turn, hints.length - 1)],
      placeholder: 'Что ты скажешь ' + cur.dat + '?',
      draft: s.draft,
      typeDraft: (e) => this.setState({ draft: e.target.value }),
      send,
      finish: () => this.setState({ view: 'review', tr: false, disputed: false, fromOther: s.sel !== 's1', sel: 's1' }),
      retry: () => toChat('s1'),
      fromOther: s.fromOther,
      disputed: s.disputed,
      notDisputed: !s.disputed,
      dispute: () => this.setState({ disputed: true }),
      review: reviewDefs.map((c) => ({
        ...c,
        dots: [c.score >= 1 ? 'on' : '', c.score >= 2 ? 'on' : ''],
        scoreLabel: c.score + ' из 2',
        scoreCls: c.score === 2 ? 'sc sc-2' : (c.score === 0 ? 'sc sc-0' : 'sc'),
        hasInstead: !!c.instead
      })),
      trOpen: s.tr,
      trClosed: !s.tr,
      trExpanded: s.tr ? 'true' : 'false',
      trLabel: s.tr ? 'Скрыть' : 'Показать все реплики',
      toggleTr: () => this.setState({ tr: !s.tr }),
      transcript: transcript.map(msgView('Миша')),
      stopText: s.stopText,
      stopNow: () => this.setState({ stopAct: 'stopped', talk: false }),
      later: () => this.setState({ stopAct: 'later', talk: false }),
      stopped: s.stopAct === 'stopped',
      laterSet: s.stopAct === 'later',
      talkOpen: s.talk,
      talkExpanded: s.talk ? 'true' : 'false',
      toggleTalk: () => this.setState({ talk: !s.talk, stopAct: '' }),
      booked: s.booked,
      notBooked: !s.booked,
      book: () => this.setState({ booked: true }),
      rules: [
        { n: 1, title: 'Без подробностей насилия', text: 'Ребёнок в сценарии говорит общими словами. Сексуализированного контента нет — ни в роли, ни вне её.' },
        { n: 2, title: 'Стоп-кран всегда под рукой', text: 'Пауза видна всегда. Если тебе тяжело, ИИ сам выходит из роли и даёт контакт психолога.' },
        { n: 3, title: 'Сценарии утверждает психолог', text: 'ИИ играет строго по карточке: профиль, первая реплика, правила реакции, критерии.' },
        { n: 4, title: 'Никаких данных реальных детей', text: 'Персонажи вымышлены. О реальном случае — сразу координатору или психологу, при опасности — 112.' },
        { n: 5, title: 'Учит, а не выносит вердикт', text: 'Разбор с цитатами и «что сказать вместо». О допуске к детям решает человек.' }
      ]
    };
  }
}

const c = new Component({});
const roots = ["askCurator", "book", "booked", "cur", "curAvLg", "curBasis", "curCrit", "curRule", "curWarn", "curatorAsked", "dispute", "disputed", "draft", "finish", "fromOther", "hintExpanded", "hintOpen", "hintText", "isChat", "isPaused", "isPick", "isReview", "isStop", "later", "laterSet", "methods", "msgs", "notBooked", "notDisputed", "notPaused", "notPick", "pause", "placeholder", "resume", "retry", "review", "rules", "scenarios", "send", "showCurator", "start", "stopNow", "stopText", "stopped", "talkExpanded", "talkOpen", "toPick", "toggleHint", "toggleTalk", "toggleTr", "trClosed", "trExpanded", "trLabel", "trOpen", "transcript", "typeDraft", "views"];
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
