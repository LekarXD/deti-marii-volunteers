class Component extends DCLogic {
  constructor(props) {
    super(props);
    this.state = { fmt: 'all', why: false, blocked: false, allBlocked: false };
  }
  renderVals() {
    const s = this.state;
    const MATCHES = [
      { title: 'Дизайн афиши спектакля', when: 'Онлайн, до 9 ноября', score: 88, art: 'art art-o', icon: 'image', fmt: ['once', 'online'] },
      { title: 'Мастер-класс по валянию', when: 'Сб, 31 октября, 11:00', score: 81, art: 'art art-y', icon: 'scissors', fmt: ['once'] },
      { title: 'Наставник новичка', when: 'Откроется 13 декабря', score: 64, art: 'art art-v', icon: 'users', fmt: ['reg', 'online'] }
    ];
    const BLOCKED = [
      { title: 'Водитель: материалы на выезд в ЦССУ', reason: 'Нужен автомобиль', art: 'art art-g', icon: 'car' },
      { title: 'Помощник в инклюзивной театральной мастерской', reason: 'Вторник не в графике', art: 'art art-p', icon: 'mask' },
      { title: 'Ассистент музыкальной студии', reason: 'Четверг не в графике', art: 'art art-v', icon: 'music' },
      { title: 'Ведущий клуба настольных игр', reason: 'Нужен трек «Ведущий»', art: 'art art-b', icon: 'dice' },
      { title: 'Киноклуб для выпускников', reason: 'Пятница не в графике', art: 'art art-b', icon: 'film' },
      { title: 'Фотограф на осенней ярмарке', reason: 'Воскресенье не в графике', art: 'art art-g', icon: 'camera' },
      { title: 'Ассистент в мастерской витража', reason: 'Понедельник не в графике', art: 'art art-v', icon: 'palette' }
    ];
    const chipDefs = [
      { id: 'all', label: 'Все' },
      { id: 'reg', label: 'Регулярно' },
      { id: 'once', label: 'Разово' },
      { id: 'online', label: 'Онлайн' }
    ];
    const iconFlags = (icon) => ({
      isImage: icon === 'image', isScissors: icon === 'scissors', isUsers: icon === 'users',
      isCar: icon === 'car', isMask: icon === 'mask', isMusic: icon === 'music', isDice: icon === 'dice',
      isFilm: icon === 'film', isCamera: icon === 'camera', isPalette: icon === 'palette'
    });
    const shownBlocked = s.allBlocked ? BLOCKED : BLOCKED.slice(0, 4);
    return {
      showWhy: s.why,
      whyExpanded: s.why ? 'true' : 'false',
      whyLabel: s.why ? 'Скрыть' : 'Почему так',
      toggleWhy: () => this.setState({ why: !s.why }),
      chips: chipDefs.map((c) => ({
        label: c.label,
        cls: c.id === s.fmt ? 'chip is-on' : 'chip',
        pressed: c.id === s.fmt ? 'true' : 'false',
        pick: () => this.setState({ fmt: c.id })
      })),
      matches: MATCHES
        .filter((m) => s.fmt === 'all' || m.fmt.indexOf(s.fmt) >= 0)
        .map((m) => Object.assign({ title: m.title, when: m.when, score: m.score, art: m.art, scoreLabel: 'Совпадение ' + m.score + ' из 100' }, iconFlags(m.icon))),
      showBlocked: s.blocked,
      blockedExpanded: s.blocked ? 'true' : 'false',
      blockedLabel: s.blocked ? 'Скрыть' : 'Показать',
      toggleBlocked: () => this.setState({ blocked: !s.blocked, allBlocked: false }),
      blocked: shownBlocked.map((b) => Object.assign({ title: b.title, reason: b.reason, art: b.art }, iconFlags(b.icon))),
      hasMoreBlocked: !s.allBlocked && BLOCKED.length > 4,
      moreLabel: 'Ещё ' + (BLOCKED.length - 4),
      showAllBlocked: () => this.setState({ allBlocked: true })
    };
  }
}