class Component extends DCLogic {
  constructor(props) {
    super(props);
    this.state = { mode: 'read', sel: '', placed: {}, checked: false, answers: {}, tested: false, done: false, video: false };
  }
  renderVals() {
    const s = this.state;
    const STMTS = [
      { id: 'a', text: 'Предупредить о смене занятия заранее', ans: 'help', why: '' },
      { id: 'b', text: 'Включить громкую музыку для настроения', ans: 'hurt', why: 'Громкий звук легко перегружает.' },
      { id: 'c', text: 'Дать выбрать место за столом', ans: 'help', why: '' },
      { id: 'd', text: 'Торопить, если ребёнок медлит', ans: 'hurt', why: 'Спешка поднимает напряжение. Дай время.' },
      { id: 'e', text: 'Показать пример действием', ans: 'help', why: '' },
      { id: 'f', text: 'Трогать за руку без спроса', ans: 'hurt', why: 'Прикосновение без спроса может напугать.' }
    ];
    const WHY_HELP = { a: 'Предсказуемость снижает тревогу.', c: 'Выбор возвращает чувство контроля.', e: 'Показ понятнее длинных объяснений.' };
    const QS = [
      { id: 'q1', text: 'Занятие переносят в другой зал. Как сказать об этом ребёнку с аутизмом?', right: 'b',
        opts: [{ k: 'a', t: 'В момент перехода, чтобы не тревожить заранее' }, { k: 'b', t: 'Заранее, и показать, куда пойдём' }, { k: 'c', t: 'Никак: ведущий сам всё объяснит' }],
        why: 'Заранее и наглядно: предсказуемость снижает тревогу.' },
      { id: 'q2', text: 'Ребёнок зажал уши и раскачивается. Что сделать первым?', right: 'c',
        opts: [{ k: 'a', t: 'Спросить, что случилось и что ему не нравится' }, { k: 'b', t: 'Обнять, чтобы успокоить' }, { k: 'c', t: 'Убрать источник шума и говорить минимум' }],
        why: 'Это перегрузка, а не каприз. Вопросы и прикосновения её усиливают.' },
      { id: 'q3', text: 'Ребёнок долго выбирает цвет, группа уже рисует. Как поступить?', right: 'a',
        opts: [{ k: 'a', t: 'Подождать и предложить два цвета на выбор' }, { k: 'b', t: 'Выбрать за него, чтобы не задерживать' }, { k: 'c', t: 'Напомнить, что все уже начали' }],
        why: 'Выбор из двух и время на ответ, без сравнения с другими.' }
    ];
    const allPlaced = { a: 'help', b: 'hurt', c: 'help', d: 'help', e: 'help', f: 'hurt' };
    const presets = {
      read: { sel: '', placed: {}, checked: false, answers: {}, tested: false, done: false, video: false },
      pass: { sel: '', placed: allPlaced, checked: true, answers: { q1: 'b', q2: 'a', q3: 'a' }, tested: true, done: false, video: true },
      fail: { sel: '', placed: allPlaced, checked: true, answers: { q1: 'a', q2: 'a', q3: 'a' }, tested: true, done: false, video: true }
    };
    const modeDefs = [
      { id: 'read', label: 'Читаю' },
      { id: 'pass', label: 'Тест пройден' },
      { id: 'fail', label: 'Тест не пройден' }
    ];

    // упражнение
    const left = STMTS.filter((x) => !s.placed[x.id]).length;
    const selObj = STMTS.find((x) => x.id === s.sel && !s.placed[x.id]);
    const pool = STMTS.filter((x) => !s.placed[x.id]).map((x) => ({
      text: x.text,
      cls: s.sel === x.id ? 'stmt is-on' : 'stmt',
      pressed: s.sel === x.id ? 'true' : 'false',
      pick: () => this.setState({ sel: s.sel === x.id ? '' : x.id })
    }));
    const place = (bin) => {
      if (!selObj) return;
      const p = Object.assign({}, s.placed);
      p[selObj.id] = bin;
      this.setState({ placed: p, sel: '' });
    };
    const binItems = (bin) => STMTS.filter((x) => s.placed[x.id] === bin).map((x) => {
      const ok = x.ans === bin;
      return {
        text: x.text,
        plain: !s.checked,
        right: s.checked && ok,
        wrong: s.checked && !ok,
        why: x.ans === 'help' ? WHY_HELP[x.id] : x.why,
        backLabel: 'Вернуть карточку: ' + x.text,
        unplace: () => {
          const p = Object.assign({}, s.placed);
          delete p[x.id];
          this.setState({ placed: p });
        }
      };
    });
    const exRight = STMTS.filter((x) => s.placed[x.id] === x.ans).length;

    // тест
    const letters = ['A', 'B', 'C'];
    const questions = QS.map((q, i) => {
      const chosen = s.answers[q.id] || '';
      const ok = chosen === q.right;
      return {
        title: (i + 1) + '. ' + q.text,
        why: q.why,
        showWhy: s.tested && !ok,
        opts: q.opts.map((o, j) => {
          let cls = 'opt';
          if (s.tested) {
            if (o.k === q.right) cls = 'opt is-right';
            else if (o.k === chosen) cls = 'opt is-wrong';
          } else if (o.k === chosen) {
            cls = 'opt is-sel';
          }
          return {
            letter: letters[j],
            text: o.t,
            cls,
            pressed: o.k === chosen ? 'true' : 'false',
            pick: () => {
              if (s.tested) return;
              const a = Object.assign({}, s.answers);
              a[q.id] = o.k;
              this.setState({ answers: a });
            }
          };
        })
      };
    });
    const answered = QS.filter((q) => s.answers[q.id]).length;
    const score = QS.filter((q) => s.answers[q.id] === q.right).length;
    const passed = s.tested && score >= 2;

    // финал
    let heroTitle = 'Осталось пройти тест';
    let heroLead = 'Потом отметь урок, и откроется тренажёр';
    if (s.done) { heroTitle = 'Модуль пройден'; heroLead = 'Дальше — тренажёр трудных ситуаций'; }
    else if (passed) { heroTitle = 'Всё готово'; heroLead = 'Отметь урок, и откроется тренажёр'; }
    else if (s.tested) { heroLead = 'Перечитай про сенсорную нагрузку и попробуй ещё раз'; }

    // прогресс
    const stepDefs = [
      { id: 'text', label: 'Текст', done: true },
      { id: 'video', label: 'Видео', done: s.video },
      { id: 'exercise', label: 'Упражнение', done: s.checked },
      { id: 'test', label: 'Тест', done: passed }
    ];
    const doneSteps = stepDefs.filter((x) => x.done).length;
    const nowIdx = stepDefs.findIndex((x) => !x.done);

    return {
      modes: modeDefs.map((m) => ({
        ...m,
        cls: m.id === s.mode ? 'is-on' : '',
        pressed: m.id === s.mode ? 'true' : 'false',
        pick: () => this.setState(Object.assign({ mode: m.id }, presets[m.id]))
      })),
      videoIdle: !s.video,
      videoOn: s.video,
      playVideo: () => this.setState({ video: true }),
      hasPool: left > 0,
      pool,
      hasSel: !!selObj,
      putHelp: () => place('help'),
      putHurt: () => place('hurt'),
      helpItems: binItems('help'),
      hurtItems: binItems('hurt'),
      exWait: left > 0,
      exReady: left === 0 && !s.checked,
      exChecked: s.checked,
      exScore: exRight + ' из 6',
      checkEx: () => this.setState({ checked: true }),
      resetEx: () => this.setState({ placed: {}, checked: false, sel: '' }),
      questions,
      testWait: answered < QS.length && !s.tested,
      testReady: answered === QS.length && !s.tested,
      tested: s.tested,
      testScore: score + ' из 3',
      testFailed: s.tested && !passed,
      checkTest: () => this.setState({ tested: true }),
      retryTest: () => this.setState({ answers: {}, tested: false }),
      heroTitle,
      heroLead,
      canMark: passed && !s.done,
      cantMark: !passed && !s.done,
      isDone: s.done,
      notDone: !s.done,
      markDone: () => this.setState({ done: true }),
      undoDone: () => this.setState({ done: false }),
      progLabel: doneSteps + ' из 4',
      progStyle: 'width:' + (doneSteps * 25) + '%',
      steps: stepDefs.map((x, i) => ({
        label: x.label,
        href: '#' + x.id,
        n: String(i + 1),
        done: x.done,
        todo: !x.done,
        cls: i === nowIdx ? 'toc-a is-now' : 'toc-a',
        icCls: x.done ? 'state-ic st-done' : (i === nowIdx ? 'state-ic st-now' : 'state-ic st-next')
      }))
    };
  }
}
