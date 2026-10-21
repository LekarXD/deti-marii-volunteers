
class DCLogic { constructor(props){ this.props = props; this.state = {}; } setState(p){ this.state = Object.assign({}, this.state, p); } }

class Component extends DCLogic {
  constructor(props) {
    super(props);
    this.state = { mode: 'read', sel: '', placed: {}, checked: false, answers: {}, tested: false, done: false, video: false, summary: false, toc: 'intro', notes: '', ask: '' };
  }
  renderVals() {
    const s = this.state;
    const STMTS = [
      { id: 'a', text: 'Предупредить о смене занятия заранее', ans: 'help', why: 'Предсказуемость снижает тревогу: ребёнок знает, что будет дальше.' },
      { id: 'b', text: 'Включить громкую музыку для настроения', ans: 'hurt', why: 'Громкий звук легко перегружает. Музыка — тихо и по договорённости.' },
      { id: 'c', text: 'Дать выбрать место за столом', ans: 'help', why: 'Выбор возвращает чувство контроля.' },
      { id: 'd', text: 'Торопить, если ребёнок медлит', ans: 'hurt', why: 'Спешка поднимает напряжение. Дай время на ответ.' },
      { id: 'e', text: 'Показать пример действием', ans: 'help', why: 'Показ понятнее длинных объяснений.' },
      { id: 'f', text: 'Трогать за руку без спроса', ans: 'hurt', why: 'Прикосновение без спроса может напугать. Сначала спроси.' }
    ];
    const QS = [
      { id: 'q1', text: 'Занятие переносят в другой зал. Как сказать об этом ребёнку с аутизмом?', right: 'b',
        opts: [{ k: 'a', t: 'В момент перехода, чтобы не тревожить заранее' }, { k: 'b', t: 'Заранее, и показать, куда пойдём' }, { k: 'c', t: 'Никак: ведущий сам всё объяснит' }],
        why: 'Предсказуемость снижает тревогу: заранее и наглядно, а не в момент перехода.' },
      { id: 'q2', text: 'Ребёнок зажал уши и раскачивается. Что сделать первым?', right: 'c',
        opts: [{ k: 'a', t: 'Спросить, что случилось и что ему не нравится' }, { k: 'b', t: 'Обнять, чтобы успокоить' }, { k: 'c', t: 'Убрать источник шума и говорить минимум' }],
        why: 'Это перегрузка, а не каприз. Вопросы и прикосновения её усиливают (National Autistic Society).' },
      { id: 'q3', text: 'Ребёнок долго выбирает цвет, группа уже рисует. Как поступить?', right: 'a',
        opts: [{ k: 'a', t: 'Подождать и предложить два цвета на выбор' }, { k: 'b', t: 'Выбрать за него, чтобы не задерживать' }, { k: 'c', t: 'Напомнить, что все уже начали' }],
        why: 'Выбор из двух и время на ответ. Без спешки и сравнения с другими.' }
    ];
    const allPlaced = { a: 'help', b: 'hurt', c: 'help', d: 'help', e: 'help', f: 'hurt' };
    const presets = {
      read: { sel: '', placed: {}, checked: false, answers: {}, tested: false, done: false, video: false, summary: false },
      pass: { sel: '', placed: allPlaced, checked: true, answers: { q1: 'b', q2: 'a', q3: 'a' }, tested: true, done: false, video: true, summary: false },
      fail: { sel: '', placed: allPlaced, checked: true, answers: { q1: 'a', q2: 'a', q3: 'a' }, tested: true, done: false, video: true, summary: false }
    };
    const modeDefs = [
      { id: 'read', label: 'Читаю' },
      { id: 'pass', label: 'Тест пройден' },
      { id: 'fail', label: 'Тест не пройден' }
    ];

    // упражнение
    const placedCount = Object.keys(s.placed).length;
    const left = STMTS.length - placedCount;
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
        isChecked: s.checked,
        right: s.checked && ok,
        wrong: s.checked && !ok,
        verdict: ok ? 'Верно.' : (x.ans === 'help' ? 'Скорее помогает.' : 'Скорее мешает.'),
        vCls: ok ? 'ok-t' : 'no-t',
        why: x.why,
        backLabel: 'Вернуть карточку: ' + x.text,
        unplace: () => {
          if (s.checked) return;
          const p = Object.assign({}, s.placed);
          delete p[x.id];
          this.setState({ placed: p });
        }
      };
    });
    const helpItems = binItems('help');
    const hurtItems = binItems('hurt');
    const exScore = STMTS.filter((x) => s.placed[x.id] === x.ans).length;

    // тест
    const letters = ['A', 'B', 'C'];
    const questions = QS.map((q, i) => {
      const chosen = s.answers[q.id] || '';
      const ok = chosen === q.right;
      return {
        n: i + 1,
        text: q.text,
        why: q.why,
        showVerdict: s.tested,
        verdict: ok ? 'Верно.' : 'Неверно.',
        vCls: ok ? 'ok-t' : 'no-t',
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

    // прогресс урока
    const stepDefs = [
      { label: 'Статья', done: true },
      { label: 'Видео', done: s.video },
      { label: 'Упражнение', done: s.checked },
      { label: 'Тест', done: passed }
    ];
    const doneSteps = stepDefs.filter((x) => x.done).length;
    const tocDefs = [
      { id: 'intro', label: 'Зачем это ассистенту' },
      { id: 'predict', label: 'Предсказуемость' },
      { id: 'sensory', label: 'Сенсорная нагрузка' },
      { id: 'choice', label: 'Выбор и темп' },
      { id: 'short', label: 'Как говорить коротко' },
      { id: 'video', label: 'Видео' },
      { id: 'exercise', label: 'Упражнение' },
      { id: 'files', label: 'Материалы' },
      { id: 'test', label: 'Тест' }
    ];

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
      summaryOpen: s.summary,
      summaryExpanded: s.summary ? 'true' : 'false',
      toggleSummary: () => this.setState({ summary: !s.summary }),
      summary: [
        { at: '0:40', text: 'Почему предсказуемость снижает тревогу' },
        { at: '2:15', text: 'Как предупредить о смене: заранее, картинкой и словами' },
        { at: '4:30', text: 'Свет, звук, запахи: что убрать до занятия' },
        { at: '6:50', text: 'Тихий угол: кто идёт с ребёнком и что говорить' }
      ],
      pool,
      hasSel: !!selObj,
      selText: selObj ? selObj.text : '',
      putHelp: () => place('help'),
      putHurt: () => place('hurt'),
      helpItems,
      hurtItems,
      helpCount: String(helpItems.length),
      hurtCount: String(hurtItems.length),
      canCheckEx: left === 0 && !s.checked,
      waitEx: left > 0,
      leftLabel: 'Осталось разложить: ' + left,
      exChecked: s.checked,
      exResult: exScore + ' из 6 верно',
      checkEx: () => this.setState({ checked: true }),
      resetEx: () => this.setState({ placed: {}, checked: false, sel: '' }),
      questions,
      canCheckTest: answered === QS.length && !s.tested,
      waitTest: answered < QS.length && !s.tested,
      answeredLabel: 'Отвечено ' + answered + ' из 3',
      checkTest: () => this.setState({ tested: true }),
      retryTest: () => this.setState({ answers: {}, tested: false }),
      testPassed: passed,
      testFailed: s.tested && !passed,
      scoreLine: score + ' из 3',
      canMark: passed && !s.done,
      cantMark: !passed && !s.done,
      isDone: s.done,
      notDone: !s.done,
      markDone: () => this.setState({ done: true }),
      undoDone: () => this.setState({ done: false }),
      toc: tocDefs.map((t) => ({
        ...t,
        href: '#' + t.id,
        cls: t.id === s.toc ? 'toc-a is-on' : 'toc-a',
        current: t.id === s.toc ? 'location' : 'false',
        pick: () => this.setState({ toc: t.id })
      })),
      progLabel: doneSteps + ' из 4',
      progCls: ['w25', 'w50', 'w75', 'w100'][doneSteps - 1],
      steps: stepDefs.map((x) => ({ label: x.label, done: x.done, todo: !x.done, cls: x.done ? 'stp is-done' : 'stp' })),
      ask: s.ask,
      typeAsk: (e) => this.setState({ ask: e.target.value }),
      askChips: ['Как предупредить о смене зала?', 'Не смотрит в глаза — что делать?'].map((t) => ({ text: t, pick: () => this.setState({ ask: t }) })),
      notes: s.notes,
      typeNotes: (e) => this.setState({ notes: e.target.value }),
      notesHelp: s.notes ? 'Сохранено. Видны только тебе' : 'Видны только тебе'
    };
  }
}

const c = new Component({});
const roots = ["answeredLabel", "ask", "askChips", "canCheckEx", "canCheckTest", "canMark", "cantMark", "checkEx", "checkTest", "exChecked", "exResult", "hasSel", "helpCount", "helpItems", "hurtCount", "hurtItems", "isDone", "leftLabel", "markDone", "modes", "notDone", "notes", "notesHelp", "playVideo", "pool", "progCls", "progLabel", "putHelp", "putHurt", "questions", "resetEx", "retryTest", "scoreLine", "selText", "steps", "summary", "summaryExpanded", "summaryOpen", "testFailed", "testPassed", "toc", "toggleSummary", "typeAsk", "typeNotes", "undoDone", "videoIdle", "videoOn", "waitEx", "waitTest"];
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
