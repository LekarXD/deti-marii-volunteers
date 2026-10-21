class Component extends DCLogic {
  constructor(props) {
    super(props);
    this.state = { shift: 'open', notif: true, here: false, mood: '', mic: 'idle', sent: false };
  }
  renderVals() {
    const s = this.state;
    const moods = [
      { id: 'great', label: 'Отлично', icon: 'star' },
      { id: 'good', label: 'Хорошо', icon: 'smile' },
      { id: 'ok', label: 'Ровно', icon: 'meh' },
      { id: 'hard', label: 'Трудно', icon: 'frown' },
      { id: 'heavy', label: 'Тяжело', icon: 'alert' }
    ];
    const cur = moods.filter((m) => m.id === s.mood)[0];
    return {
      p1Open: s.shift === 'open',
      p1IsYes: s.shift === 'yes',
      p1IsNo: s.shift === 'no',
      p1Yes: () => this.setState({ shift: 'yes' }),
      p1No: () => this.setState({ shift: 'no' }),
      p1Reset: () => this.setState({ shift: 'open' }),

      notifOn: s.notif,
      hideNotif: () => this.setState({ notif: false }),
      notHere: !s.here,
      isHere: s.here,
      checkIn: () => this.setState({ here: true }),
      undoCheck: () => this.setState({ here: false }),

      notSent: !s.sent,
      isSent: s.sent,
      moods: moods.map((m) => ({
        label: m.label,
        cls: m.id === s.mood ? 'is-on' : '',
        pressed: m.id === s.mood ? 'true' : 'false',
        pick: () => this.setState({ mood: m.id }),
        isStar: m.icon === 'star',
        isSmile: m.icon === 'smile',
        isMeh: m.icon === 'meh',
        isFrown: m.icon === 'frown',
        isAlert: m.icon === 'alert'
      })),
      hasMood: !!cur,
      moodLabel: cur ? cur.label : '',
      isHeavy: s.mood === 'heavy',
      micIdle: s.mic === 'idle',
      micRec: s.mic === 'rec',
      micDone: s.mic === 'done',
      micNotDone: s.mic !== 'done',
      startRec: () => this.setState({ mic: 'rec' }),
      stopRec: () => this.setState({ mic: 'done' }),
      resetRec: () => this.setState({ mic: 'idle' }),
      canSend: !!s.mood,
      cantSend: !s.mood,
      send: () => this.setState({ sent: true }),
      resetP3: () => this.setState({ sent: false, mood: '', mic: 'idle' })
    };
  }
}