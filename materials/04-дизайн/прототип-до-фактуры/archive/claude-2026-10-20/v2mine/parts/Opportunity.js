class Component extends DCLogic {
  constructor(props) {
    super(props);
    this.state = { mode: 'open', step: 'idle', date: 'd24', parts: false };
  }
  renderVals() {
    const s = this.state;
    const isOpen = s.mode === 'open';
    const isFull = s.mode === 'full';
    const isUntrained = s.mode === 'untrained';
    const joined = isOpen && s.step === 'done';
    const dates = [
      { id: 'd24', title: 'Сб, 24 октября', long: 'сб, 24 октября' },
      { id: 'd31', title: 'Сб, 31 октября', long: 'сб, 31 октября' },
      { id: 'd07', title: 'Сб, 7 ноября', long: 'сб, 7 ноября' }
    ];
    const chosen = dates.filter((d) => d.id === s.date)[0] || dates[0];
    const modeDefs = [
      { id: 'open', label: 'Можно записаться' },
      { id: 'full', label: 'Нет мест' },
      { id: 'untrained', label: 'Нет обучения' }
    ];
    const parts = [
      { label: 'Навыки', got: 33, max: 35 },
      { label: 'Интересы', got: 18, max: 20 },
      { label: 'Время', got: 15, max: 15 },
      { label: 'Дорога', got: 8, max: 10 },
      { label: 'Нужны люди', got: 10, max: 10 },
      { label: 'Та же группа', got: 10, max: 10 }
    ];
    const team = [
      { av: 'avatar avatar-lg av-y', ini: 'ЕК', name: 'Елена Карпова', role: 'ведущая' },
      { av: 'avatar avatar-lg av-g', ini: 'ЛМ', name: 'Лиля Миронова', role: 'ассистент' },
      { av: 'avatar avatar-lg av-b', ini: 'ОЛ', name: 'Ольга Лебедева', role: 'координатор' }
    ];
    if (joined) team.push({ av: 'avatar avatar-lg av-o', ini: 'АС', name: 'Анна Соколова', role: 'это ты' });
    return {
      modes: modeDefs.map((m) => ({
        label: m.label,
        cls: m.id === s.mode ? 'is-on' : '',
        pressed: m.id === s.mode ? 'true' : 'false',
        pick: () => this.setState({ mode: m.id, step: 'idle', parts: false })
      })),
      showSignup: isOpen && s.step === 'idle',
      showPick: isOpen && s.step === 'pick',
      showDone: joined,
      showWaitOffer: isFull && s.step === 'idle',
      showWaiting: isFull && s.step === 'wait',
      showLocked: isUntrained,
      startPick: () => this.setState({ step: 'pick' }),
      back: () => this.setState({ step: 'idle' }),
      confirm: () => this.setState({ step: 'done' }),
      joinWait: () => this.setState({ step: 'wait' }),
      leaveWait: () => this.setState({ step: 'idle' }),
      dates: dates.map((d) => ({
        title: d.title,
        cls: d.id === s.date ? 'chip is-on' : 'chip',
        checked: d.id === s.date ? 'true' : 'false',
        pick: () => this.setState({ date: d.id })
      })),
      doneText: 'Ты в команде, первое занятие — ' + chosen.long,
      reqs: [
        { text: isUntrained ? '«Первые шаги»: 1 из 5' : '«Первые шаги» пройдены', ok: !isUntrained },
        { text: 'Справка о несудимости', ok: true },
        { text: 'От 3 месяцев, раз в неделю', ok: true }
      ].map((r) => ({ text: r.text, ok: r.ok, notOk: !r.ok })),
      reasons: ['Ты уже знаешь «Подсолнухов»', 'Рисуешь акварелью, была вожатой', 'Суббота днём свободна'],
      showParts: s.parts,
      partsExpanded: s.parts ? 'true' : 'false',
      partsLabel: s.parts ? 'Скрыть баллы' : 'Баллы подробно',
      toggleParts: () => this.setState({ parts: !s.parts }),
      parts: parts.map((p) => ({
        label: p.label,
        val: p.got + ' из ' + p.max,
        style: 'width: ' + Math.round((p.got / p.max) * 100) + '%'
      })),
      team: team
    };
  }
}