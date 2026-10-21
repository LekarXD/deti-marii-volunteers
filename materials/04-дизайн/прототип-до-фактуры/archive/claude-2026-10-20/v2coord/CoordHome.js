class Component extends DCLogic {
  constructor(props) {
    super(props);
    this.state = { mode: 'coord', called: false, wrote: false, editing: false, custom: '', draft: '', sent: false, chart: 'hours' };
  }
  renderVals() {
    const s = this.state;
    const isCoord = s.mode === 'coord';
    const summary = [
      { lead: 'Что было.', text: 'Смены закрыты на 94%. Активных волонтёров 84, на шесть больше, чем в сентябре.' },
      { lead: 'Что горит.', text: 'Театру 27 октября нужен второй взрослый. Сигнал о ребёнке после валяния 17 октября в тот же день ушёл психологу.' },
      { lead: 'Хорошее.', text: 'Светлана Ким год с фондом. До первого занятия теперь 19 дней, в сентябре было 26.' }
    ];
    const plain = summary.map((p) => p.lead + ' ' + p.text).join('\n\n');
    const isHours = s.chart === 'hours';
    const modeDefs = [
      { id: 'coord', label: 'Координатор' },
      { id: 'lead', label: 'Руководитель' }
    ];
    return {
      isCoord: isCoord,
      isLead: !isCoord,
      meAvCls: isCoord ? 'avatar av-b' : 'avatar av-y',
      meInitials: isCoord ? 'ОЛ' : 'НГ',
      meLabel: isCoord ? 'Ольга Лебедева, координатор волонтёров' : 'Наталья Гордеева, руководитель программ',
      modes: modeDefs.map((m) => ({
        ...m,
        cls: m.id === s.mode ? 'is-on' : '',
        pressed: m.id === s.mode ? 'true' : 'false',
        pick: () => this.setState({ mode: m.id, editing: false })
      })),
      called: s.called,
      notCalled: !s.called,
      call: () => this.setState({ called: true }),
      wrote: s.wrote,
      notWrote: !s.wrote,
      write: () => this.setState({ wrote: true }),
      summary: summary,
      showParas: !s.custom && !s.editing,
      showCustom: !!s.custom && !s.editing,
      custom: s.custom,
      editing: isCoord && s.editing,
      draft: s.draft,
      typeDraft: (e) => this.setState({ draft: e.target.value }),
      startEdit: () => this.setState({ editing: true, draft: s.custom || plain }),
      saveEdit: () => this.setState({ editing: false, custom: s.draft }),
      cancelEdit: () => this.setState({ editing: false }),
      canSend: isCoord && !s.sent && !s.editing,
      showSent: isCoord && s.sent && !s.editing,
      send: () => this.setState({ sent: true }),
      isHours: isHours,
      isFunnel: !isHours,
      chartTitle: isHours ? 'Часы по неделям' : 'Воронка заявок',
      chartOther: isHours ? 'Воронка заявок' : 'Часы по неделям',
      toggleChart: () => this.setState({ chart: isHours ? 'funnel' : 'hours' })
    };
  }
}