class Component extends DCLogic {
  constructor(props) {
    super(props);
    this.summaryDefault = [
      'Граница — это забота. Тайный канал со взрослым — красный флаг.',
      'Говорить только то, что знаешь точно: «Я приду 15-го».',
      'Сначала признать чувство: «Тебе важно знать, что я не пропаду».',
      'Номера и соцсети детям не даём. Открытки — через координатора.',
      'Прощаться по ритуалу: назвать дату, когда вернёшься.'
    ];
    this.state = {
      role: 'part', view: 'slide', phase: 'live',
      tab: 'chat', all: false,
      mic: true, cam: true, screen: false, hand: false,
      reactOpen: false, reaction: '', leave: false,
      talk: 'word', draw: 'all', speaker: 'host', rec: 'on', slide: 4,
      tool: 'pen', color: 'orange',
      msgs: [], draft: '',
      summary: this.summaryDefault.slice(), sumEdit: false, sumText: '',
      sent: false, published: false
    };
  }

  sendMsg() {
    const text = String(this.state.draft || '').trim();
    if (!text) return;
    const host = this.state.role === 'host';
    const m = { ini: host ? 'ИВ' : 'АС', av: host ? 'av-v' : 'av-o', name: host ? 'Ирина Власова' : 'Анна Соколова', time: '19:18', text: text };
    this.setState({ msgs: this.state.msgs.concat([m]), draft: '' });
  }

  renderVals() {
    const s = this.state;
    const live = s.phase === 'live';
    const host = s.role === 'host';
    const board = s.view === 'board';
    const annaSpeaks = s.speaker === 'as';
    const demoId = !live ? 'after' : (board ? 'board' : (host ? 'host' : 'part'));
    const demoDefs = [
      { id: 'part', label: 'Участник', set: { role: 'part', view: 'slide', phase: 'live', leave: false } },
      { id: 'host', label: 'Ведущий', set: { role: 'host', view: 'slide', phase: 'live', hand: true, speaker: 'host', leave: false } },
      { id: 'board', label: 'Доска', set: { role: 'part', view: 'board', phase: 'live', leave: false } },
      { id: 'after', label: 'После занятия', set: { role: 'host', phase: 'after', leave: false } }
    ];
    const slides = [
      { t: 'Супервизия: как мы говорим', s: 'Что звучит здесь, остаётся здесь.' },
      { t: 'Что такое границы', s: 'Правила, одинаковые для всех взрослых.' },
      { t: 'Почему детям важны предсказуемые взрослые', s: 'Любое исчезновение для них — потеря.' },
      { t: 'Границы с детьми: что говорить, когда просят телефон', s: '' },
      { t: 'Разбор: Аня, 10 лет, просит номер', s: 'Сценарий из тренажёра и ваши ответы.' },
      { t: 'Если ребёнок находит тебя в соцсетях', s: 'Не отвечать и сразу сказать координатору.' },
      { t: 'Если просит забрать домой', s: 'Без обещаний и без резкого «нет».' },
      { t: 'Как предупредить о пропуске', s: 'Назвать группе дату возвращения заранее.' },
      { t: 'Открытки и письма', s: 'Всё через координатора, в тот же день.' },
      { t: 'Ваши случаи', s: 'Разбираем вопросы из чата.' },
      { t: 'Что забрать с собой', s: 'Три фразы на субботу.' },
      { t: 'Вопросы', s: 'Ирина отвечает на закреплённые вопросы.' }
    ];
    const sl = slides[s.slide - 1];
    const people = [
      { id: 'iv', ini: 'ИВ', full: 'Ирина Власова', av: 'av-v' },
      { id: 'as', ini: 'АС', full: 'Анна Соколова', av: 'av-o' },
      { id: 'ol', ini: 'ОЛ', full: 'Ольга Лебедева', av: 'av-b' },
      { id: 'sk', ini: 'СК', full: 'Светлана Ким', av: 'av-g' },
      { id: 'mb', ini: 'МБ', full: 'Марина Белова', av: 'av-p' },
      { id: 'pz', ini: 'ПЗ', full: 'Полина Зайцева', av: 'av-y' },
      { id: 'do', ini: 'ДО', full: 'Дмитрий Орлов', av: 'av-v' },
      { id: 'em', ini: 'ЕМ', full: 'Егор Мельников', av: 'av-g' },
      { id: 'ks', ini: 'КС', full: 'Кирилл Смирнов', av: 'av-b' },
      { id: 'vn', ini: 'ВН', full: 'Вера Новикова', av: 'av-y' },
      { id: 'ta', ini: 'ТА', full: 'Тимур Ахмедов', av: 'av-o' }
    ];
    const ordered = people.filter((p) => p.id === 'as' && s.hand).concat(people.filter((p) => !(p.id === 'as' && s.hand)));
    const baseMsgs = [
      { ini: 'СК', av: 'av-g', name: 'Светлана Ким', time: '19:12', text: 'У нас в керамике так и договорились: открытки детям — только через Ольгу.' },
      { ini: 'ОЛ', av: 'av-b', name: 'Ольга Лебедева', time: '19:13', text: 'Да, всё через меня. Передаю в тот же день.' },
      { ini: 'ДО', av: 'av-v', name: 'Дмитрий Орлов', time: '19:15', text: 'А если ребёнок сам находит меня в соцсетях?' },
      { ini: 'ИВ', av: 'av-v', name: 'Ирина Власова', time: '19:16', text: 'Разберём через два слайда, Дмитрий.' }
    ];
    const drawWho = { me: 'Рисует Ирина', olga: 'Рисуют Ирина и Ольга', all: 'Рисуют все' };
    const ctl = (on, kind) => 'ctl' + (on ? (kind === 'off' ? '' : ' is-on') : (kind === 'off' ? ' is-off' : ''));
    const colorDefs = [
      { id: 'ink', label: 'Чёрный' },
      { id: 'orange', label: 'Оранжевый' },
      { id: 'blue', label: 'Синий' },
      { id: 'green', label: 'Зелёный' }
    ];
    const pick = (list, cur, key) => list.map((o) => ({
      label: o.label,
      cls: o.id === cur ? 'is-on' : '',
      pressed: o.id === cur ? 'true' : 'false',
      pick: () => { const st = {}; st[key] = o.id; this.setState(st); }
    }));

    return {
      isLive: live,
      isAfter: !live,
      isHost: host,
      isPart: !host,
      meIni: host ? 'ИВ' : 'АС',
      meName: host ? 'Вы: Ирина Власова' : 'Вы: Анна Соколова',
      meCls: host ? 'avatar av-v' : 'avatar av-o',
      modes: demoDefs.map((d) => ({
        label: d.label,
        cls: d.id === demoId ? 'is-on' : '',
        pressed: d.id === demoId ? 'true' : 'false',
        pick: () => this.setState(Object.assign({ reactOpen: false }, d.set))
      })),

      recCls: s.rec === 'pause' ? 'st-rec is-pause' : 'st-rec',
      recLabel: s.rec === 'pause' ? 'Пауза' : 'Запись',
      recPressed: s.rec === 'on' ? 'true' : 'false',
      toggleRec: () => this.setState({ rec: this.state.rec === 'on' ? 'pause' : 'on' }),

      stageCls: 'stage' + (board ? ' is-board' : ''),
      showSlide: !board,
      showBoard: board,
      slideTitle: sl.t,
      slideSub: sl.s,
      slideMain: s.slide === 4,
      slideOther: s.slide !== 4,
      slideCount: s.slide + ' / 12',
      prevSlide: () => this.setState({ slide: Math.max(1, this.state.slide - 1) }),
      nextSlide: () => this.setState({ slide: Math.min(12, this.state.slide + 1) }),

      canDraw: host || s.draw === 'all',
      cantDraw: !(host || s.draw === 'all'),
      drawWho: drawWho[s.draw],
      tools: pick([{ id: 'pen', label: 'Перо' }, { id: 'shape', label: 'Фигура' }, { id: 'text', label: 'Текст' }, { id: 'eraser', label: 'Ластик' }], s.tool, 'tool'),
      colors: colorDefs.map((c) => ({
        label: c.label,
        cls: 'swatch sw-' + c.id + (c.id === s.color ? ' is-on' : ''),
        pressed: c.id === s.color ? 'true' : 'false',
        pick: () => this.setState({ color: c.id })
      })),

      annaSpeaks: annaSpeaks,
      hostCamCls: 'cam cam-host' + (annaSpeaks ? '' : ' is-speaking'),
      hasReaction: !!s.reaction,
      rHeart: s.reaction === 'heart',
      rStar: s.reaction === 'star',
      rSmile: s.reaction === 'smile',
      reactAria: 'Твоя реакция',

      notLeaving: !s.leave,
      leaving: s.leave,
      leaveAria: host ? 'Завершить занятие' : 'Выйти из занятия',
      leaveText: host ? 'Завершить для всех?' : 'Выйти из занятия?',
      askLeave: () => this.setState({ leave: true, reactOpen: false }),
      stayHere: () => this.setState({ leave: false }),
      finish: () => this.setState({ phase: 'after', leave: false }),
      micCls: ctl(s.mic, 'off'),
      micPressed: s.mic ? 'false' : 'true',
      micAria: s.mic ? 'Выключить микрофон' : 'Включить микрофон',
      toggleMic: () => this.setState({ mic: !this.state.mic }),
      camCls: ctl(s.cam, 'off'),
      camPressed: s.cam ? 'false' : 'true',
      camAria: s.cam ? 'Выключить камеру' : 'Включить камеру',
      toggleCam: () => this.setState({ cam: !this.state.cam }),
      screenCls: ctl(s.screen, 'on'),
      screenPressed: s.screen ? 'true' : 'false',
      screenAria: s.screen ? 'Остановить показ экрана' : 'Показать экран',
      toggleScreen: () => this.setState({ screen: !this.state.screen }),
      boardCls: ctl(board, 'on'),
      boardPressed: board ? 'true' : 'false',
      toggleBoard: () => this.setState({ view: this.state.view === 'board' ? 'slide' : 'board' }),
      handCls: ctl(s.hand, 'on'),
      handPressed: s.hand ? 'true' : 'false',
      handAria: s.hand ? 'Опустить руку' : 'Поднять руку',
      toggleHand: () => this.setState({ hand: !this.state.hand }),
      reactCls: ctl(s.reactOpen, 'on'),
      reactExpanded: s.reactOpen ? 'true' : 'false',
      reactOpen: s.reactOpen,
      toggleReact: () => this.setState({ reactOpen: !this.state.reactOpen }),
      reactHeart: () => this.setState({ reaction: 'heart', reactOpen: false }),
      reactStar: () => this.setState({ reaction: 'star', reactOpen: false }),
      reactSmile: () => this.setState({ reaction: 'smile', reactOpen: false }),

      talkOpts: pick([{ id: 'all', label: 'Все' }, { id: 'word', label: 'По слову' }, { id: 'none', label: 'Никто' }], s.talk, 'talk'),
      drawOpts: pick([{ id: 'me', label: 'Я' }, { id: 'olga', label: 'С Ольгой' }, { id: 'all', label: 'Все' }], s.draw, 'draw'),
      hasRequest: s.hand && !annaSpeaks,
      giveWord: () => this.setState({ speaker: 'as', hand: false }),
      takeWord: () => this.setState({ speaker: 'host' }),

      tabs: [{ id: 'chat', label: 'Чат' }, { id: 'people', label: 'Участники' }, { id: 'ai', label: 'Конспект' }].map((t) => ({
        label: t.label,
        cls: t.id === s.tab ? 'is-on' : '',
        selected: t.id === s.tab ? 'true' : 'false',
        pick: () => this.setState({ tab: t.id })
      })),
      tabChat: s.tab === 'chat',
      tabPeople: s.tab === 'people',
      tabAi: s.tab === 'ai',
      msgs: baseMsgs.concat(s.msgs).map((m) => ({
        ini: m.ini, av: 'avatar avatar-sm ' + m.av, name: m.name, time: m.time, text: m.text
      })),
      draft: s.draft,
      typeDraft: (e) => this.setState({ draft: e.target.value }),
      sendMsg: () => this.sendMsg(),

      people: (s.all ? ordered : ordered.slice(0, 4)).map((p) => ({
        ini: p.ini,
        full: p.full,
        av: 'avatar avatar-sm ' + p.av,
        speaks: (p.id === 'iv' && !annaSpeaks) || (p.id === 'as' && annaSpeaks),
        hand: p.id === 'as' && s.hand
      })),
      allExpanded: s.all ? 'true' : 'false',
      allLabel: s.all ? 'Свернуть' : 'Показать всех',
      toggleAll: () => this.setState({ all: !this.state.all }),
      livePoints: [
        { t: '03:10', text: 'Тайный канал со взрослым — красный флаг' },
        { t: '07:45', text: 'Говорить только то, что знаешь точно' },
        { t: '09:30', text: 'Сначала признать чувство ребёнка' },
        { t: '12:20', text: 'Открытки — через координатора' }
      ],

      summary: s.summary.map((text, i) => ({ n: String(i + 1), text: text })),
      sumView: !s.sumEdit,
      sumEdit: s.sumEdit,
      sumText: s.sumText,
      editSum: () => this.setState({ sumEdit: true, sumText: this.state.summary.join('\n') }),
      typeSum: (e) => this.setState({ sumText: e.target.value }),
      saveSum: () => {
        const lines = String(this.state.sumText || '').split('\n').map((x) => x.trim()).filter((x) => x);
        this.setState({ sumEdit: false, summary: lines.length ? lines : this.state.summary });
      },
      cancelSum: () => this.setState({ sumEdit: false }),
      notSent: !s.sent,
      isSent: s.sent,
      sendAll: () => this.setState({ sent: true }),
      unsend: () => this.setState({ sent: false }),
      notPublished: !s.published,
      isPublished: s.published,
      publish: () => this.setState({ published: true })
    };
  }
}