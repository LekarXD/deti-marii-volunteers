class Component extends DCLogic {
  constructor(props) {
    super(props);
    this.state = this.preset('normal');
  }
  preset(mode) {
    const base = { mode: mode, voice: 'idle', sent: false, confirmed: false, sup: false, pause: false };
    if (mode === 'alarm') {
      return Object.assign(base, { mood: 'ok', sent: true,
        text: 'Л., 10 лет, сказала, что не хочет возвращаться в группу, потому что её обижают старшие, и попросила никому не говорить.' });
    }
    if (mode === 'hard') {
      return Object.assign(base, { mood: 'awful', sent: true,
        text: 'Третье занятие подряд не справляюсь с группой: шумят, не слушают, к концу я без сил.' });
    }
    return Object.assign(base, { mood: '', text: '' });
  }
  renderVals() {
    const s = this.state;
    const TRANSCRIPT = 'Рисовали осенние деревья акварелью. Миша, 9 лет, сначала отказывался, а включился, когда ему дали самому выбрать краски. Старшим малы фартуки.';
    const moodDefs = [
      { id: 'great', label: 'Отлично', icon: 'heart' },
      { id: 'good', label: 'Хорошо', icon: 'smile' },
      { id: 'ok', label: 'Нормально', icon: 'meh' },
      { id: 'hard', label: 'Тяжело', icon: 'frown' },
      { id: 'awful', label: 'Очень тяжело', icon: 'frown' }
    ];
    const moodObj = moodDefs.filter((m) => m.id === s.mood)[0];
    const moodLabel = moodObj ? moodObj.label : 'Не отмечено';
    const isAlarm = s.mode === 'alarm';
    const heavy = !isAlarm && (s.mode === 'hard' || s.mood === 'hard' || s.mood === 'awful');
    const flow = !s.sent ? 'form' : (isAlarm ? 'alarm' : (heavy ? 'hard' : 'done'));
    const undBy = {
      done: [
        { label: 'Настроение', value: moodLabel },
        { label: 'Получилось', value: 'М., 9 лет, включился, когда дали самому выбрать краски' },
        { label: 'Нужно', value: 'Фартуки побольше, передали Елене Карповой' }
      ],
      alarm: [
        { label: 'Сигнал', value: 'Л., 10 лет: её обижают старшие, просила никому не говорить' },
        { label: 'Нужно', value: 'Помощь психолога для Л., передали Ирине Власовой' },
        { label: 'Настроение', value: moodLabel }
      ],
      hard: [
        { label: 'Настроение', value: moodLabel },
        { label: 'Трудно', value: 'Третье занятие подряд не удаётся удержать группу' },
        { label: 'Нужно', value: 'Поддержка для тебя: разговор или супервизия' }
      ]
    };
    const modeDefs = [
      { id: 'normal', label: 'Обычное занятие' },
      { id: 'alarm', label: 'Тревожный сигнал' },
      { id: 'hard', label: 'Мне тяжело' }
    ];
    return {
      modes: modeDefs.map((m) => ({
        label: m.label,
        cls: m.id === s.mode ? 'is-on' : '',
        pressed: m.id === s.mode ? 'true' : 'false',
        pick: () => this.setState(this.preset(m.id))
      })),
      showForm: flow === 'form',
      showDone: flow === 'done',
      showAlarm: flow === 'alarm',
      showHard: flow === 'hard',
      showResult: flow !== 'form',
      moods: moodDefs.map((m) => ({
        label: m.label,
        isHeart: m.icon === 'heart',
        isSmile: m.icon === 'smile',
        isMeh: m.icon === 'meh',
        isFrown: m.icon === 'frown',
        cls: m.id === s.mood ? 'mood is-on' : 'mood',
        checked: m.id === s.mood ? 'true' : 'false',
        pick: () => this.setState({ mood: m.id })
      })),
      text: s.text,
      typeText: (e) => this.setState({ text: e.target.value }),
      voiceIdle: s.voice === 'idle',
      voiceRec: s.voice === 'rec',
      startRec: () => this.setState({ voice: 'rec' }),
      stopRec: () => this.setState({ voice: 'idle', text: this.state.text || TRANSCRIPT }),
      send: () => this.setState({ sent: true, confirmed: false, voice: 'idle' }),
      und: (undBy[flow] || undBy.done).map((u) => ({ label: u.label, value: u.value })),
      notConfirmed: !s.confirmed,
      confirmed: s.confirmed,
      confirm: () => this.setState({ confirmed: true }),
      edit: () => this.setState({ sent: false, confirmed: false }),
      supOpen: !s.sup,
      supJoined: s.sup,
      toggleSup: () => this.setState({ sup: !s.sup }),
      pauseOff: !s.pause,
      pauseOn: s.pause,
      togglePause: () => this.setState({ pause: !s.pause })
    };
  }
}